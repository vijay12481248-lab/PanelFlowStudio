"""
Authoritative AudioMixer for PanelFlow Production Renderer.
Mixes dialogue, ACE-Step music, and sound effects with smooth ducking and broadcast safety checks.
"""
from typing import Dict, Any, Tuple, Optional, List
from pathlib import Path
import math
import numpy as np
import soundfile as sf

from engine.render.models.render_plan import RenderPlan, RenderAudioTrack
from engine.render.models.enums import MusicDurationPolicy


class AudioMixer:
    """
    Mixes multi-track audio assets into a broadcast-safe 48 kHz stereo master stream.
    """

    def __init__(self, sample_rate: int = 48000, channels: int = 2):
        self.sample_rate = sample_rate
        self.channels = channels

    def mix_timeline_audio(
        self,
        plan: RenderPlan,
        output_wav_path: Path,
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Executes complete audio mixdown according to the compiled RenderPlan.
        Returns (success, audit_metrics).
        """
        total_samples = int(round(plan.total_duration_sec * self.sample_rate))
        if total_samples <= 0:
            total_samples = self.sample_rate

        # Master mix buffer in float32
        master_buffer = np.zeros((total_samples, self.channels), dtype=np.float32)

        # 1. Identify dialogue and music tracks
        dialogue_tracks = [t for t in plan.audio_tracks if t.track_type == "dialogue"]
        music_tracks = [t for t in plan.audio_tracks if t.track_type == "music"]
        sfx_tracks = [t for t in plan.audio_tracks if t.track_type not in ("dialogue", "music")]

        # Collect speech intervals for ducking
        speech_intervals: List[Tuple[float, float]] = []
        for dt in dialogue_tracks:
            speech_intervals.append((dt.start_time, dt.end_time))

        # 2. Render and mix dialogue
        for dt in dialogue_tracks:
            self._mix_single_track(master_buffer, dt, total_samples)

        # 3. Render and mix SFX
        for sfx in sfx_tracks:
            self._mix_single_track(master_buffer, sfx, total_samples)

        # 4. Render and mix Music with smooth ducking
        for mt in music_tracks:
            self._mix_music_track(master_buffer, mt, speech_intervals, plan.music_policy, total_samples)

        # 5. Audio Safety Audit
        metrics = self._audit_and_sanitize_buffer(master_buffer)

        # 6. Write final 48 kHz stereo WAV
        output_wav_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(output_wav_path), master_buffer, self.sample_rate, subtype="PCM_16")

        return True, metrics

    def _load_audio_file(self, file_path: str) -> Tuple[np.ndarray, int]:
        """Loads and converts any audio file to 48 kHz stereo float32 array."""
        p = Path(file_path)
        if not p.exists() or not p.is_file():
            # Return brief silence
            return np.zeros((self.sample_rate, self.channels), dtype=np.float32), self.sample_rate

        data, sr = sf.read(str(p), dtype="float32")

        # Convert mono to stereo if needed
        if data.ndim == 1:
            data = np.column_stack([data, data])
        elif data.shape[1] > 2:
            data = data[:, :2]

        # Resample to 48 kHz if needed
        if sr != self.sample_rate:
            from scipy import signal
            num_samples = int(round(len(data) * float(self.sample_rate) / sr))
            data = signal.resample(data, num_samples)

        return data, self.sample_rate

    def _mix_single_track(self, master_buffer: np.ndarray, track: RenderAudioTrack, total_samples: int):
        data, _ = self._load_audio_file(track.file_path)
        start_idx = int(round(track.start_time * self.sample_rate))
        if start_idx >= total_samples:
            return

        # Apply gain in dB
        gain_lin = math.pow(10.0, track.gain_db / 20.0)
        scaled_data = data * gain_lin

        end_idx = min(total_samples, start_idx + len(scaled_data))
        mix_len = end_idx - start_idx
        if mix_len > 0:
            master_buffer[start_idx:end_idx] += scaled_data[:mix_len]

    def _mix_music_track(
        self,
        master_buffer: np.ndarray,
        track: RenderAudioTrack,
        speech_intervals: List[Tuple[float, float]],
        policy: MusicDurationPolicy,
        total_samples: int,
    ):
        data, _ = self._load_audio_file(track.file_path)
        if len(data) == 0:
            return

        # Handle music duration policy
        if policy == MusicDurationPolicy.LOOP and len(data) < total_samples:
            repeats = int(math.ceil(total_samples / len(data)))
            full_music = np.tile(data, (repeats, 1))[:total_samples]
        else:
            full_music = np.zeros((total_samples, self.channels), dtype=np.float32)
            copy_len = min(total_samples, len(data))
            full_music[:copy_len] = data[:copy_len]

        # Apply base gain
        base_gain = math.pow(10.0, track.gain_db / 20.0)
        full_music *= base_gain

        # Build smooth ducking envelope (-8 dB attenuation during speech)
        duck_envelope = self._build_ducking_envelope(total_samples, speech_intervals, duck_db=-8.0)
        full_music *= duck_envelope[:, np.newaxis]
        # Short ramps prevent clicks at chapter boundaries, including loop beds.
        fade_samples = min(len(full_music) // 2, int(self.sample_rate * 0.8))
        if fade_samples:
            full_music[:fade_samples] *= np.linspace(0, 1, fade_samples)[:, np.newaxis]
            full_music[-fade_samples:] *= np.linspace(1, 0, fade_samples)[:, np.newaxis]

        master_buffer += full_music

    def _build_ducking_envelope(
        self,
        total_samples: int,
        speech_intervals: List[Tuple[float, float]],
        duck_db: float = -8.0,
        attack_sec: float = 0.25,
        release_sec: float = 0.40,
    ) -> np.ndarray:
        """
        Constructs a smooth multiplier curve (1.0 = normal, ~0.4 = ducked) with attack/release fades.
        """
        envelope = np.ones(total_samples, dtype=np.float32)
        duck_factor = math.pow(10.0, duck_db / 20.0)

        attack_samples = max(1, int(round(attack_sec * self.sample_rate)))
        release_samples = max(1, int(round(release_sec * self.sample_rate)))

        for start_t, end_t in speech_intervals:
            s_idx = int(round(start_t * self.sample_rate))
            e_idx = int(round(end_t * self.sample_rate))

            # Smooth attack ramp down
            att_start = max(0, s_idx - attack_samples)
            att_len = s_idx - att_start
            if att_len > 0:
                ramp = np.linspace(1.0, duck_factor, att_len, dtype=np.float32)
                envelope[att_start:s_idx] = np.minimum(envelope[att_start:s_idx], ramp)

            # Hold ducking level during dialogue
            hold_end = min(total_samples, e_idx)
            if s_idx < hold_end:
                envelope[s_idx:hold_end] = np.minimum(envelope[s_idx:hold_end], duck_factor)

            # Smooth release ramp up
            rel_end = min(total_samples, hold_end + release_samples)
            rel_len = rel_end - hold_end
            if rel_len > 0:
                ramp_up = np.linspace(duck_factor, 1.0, rel_len, dtype=np.float32)
                envelope[hold_end:rel_end] = np.minimum(envelope[hold_end:rel_end], ramp_up)

        return envelope

    def _audit_and_sanitize_buffer(self, buffer: np.ndarray) -> Dict[str, Any]:
        """
        Audits buffer for clipping, NaN/Inf, and normalizes peaks to broadcast ceiling (-1.0 dBFS).
        """
        # Sanitize NaNs/Infs
        has_nan = np.isnan(buffer).any()
        has_inf = np.isinf(buffer).any()
        if has_nan or has_inf:
            np.nan_to_num(buffer, copy=False, nan=0.0, posinf=0.95, neginf=-0.95)

        peak_val = float(np.max(np.abs(buffer))) if len(buffer) > 0 else 0.0
        peak_dbfs = 20.0 * math.log10(max(peak_val, 1e-6))

        clipping_detected = peak_val > 0.99
        if clipping_detected:
            # Soft-limit normalize to -1.0 dBFS (approx 0.891)
            target_peak = 0.891
            buffer *= (target_peak / peak_val)
            peak_val = target_peak
            peak_dbfs = -1.0

        rms_val = float(np.sqrt(np.mean(buffer ** 2))) if len(buffer) > 0 else 0.0
        rms_dbfs = 20.0 * math.log10(max(rms_val, 1e-6))

        return {
            "peak_val": round(peak_val, 4),
            "peak_dbfs": round(peak_dbfs, 2),
            "rms_dbfs": round(rms_dbfs, 2),
            "clipping_detected": clipping_detected,
            "has_nan": bool(has_nan),
            "has_inf": bool(has_inf),
            "sample_rate": self.sample_rate,
            "channels": self.channels,
        }
