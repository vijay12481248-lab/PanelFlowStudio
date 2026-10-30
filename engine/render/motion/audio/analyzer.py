"""
Deterministic Audio Feature Extractor for Audio-Reactive Motion Graphics.
Extracts RMS energy, spectral frequency bands (Bass, Mid, Treble), and transient beat spikes
using Python's standard wave library and fast vectorized NumPy operations.
"""

from typing import Dict, Optional, Union, Tuple
from pathlib import Path
import wave
import math
import numpy as np


class AudioFeatureExtractor:
    """
    Analyzes WAV audio files to provide real-time audio modulation signals
    for procedural particle emitters, equalizers, and camera trauma.
    """

    def __init__(self, wav_path: Optional[Union[str, Path]] = None):
        self.sample_rate: int = 44100
        self.samples: np.ndarray = np.array([], dtype=np.float32)
        self.duration_sec: float = 0.0
        self.has_audio: bool = False

        if wav_path:
            self.load_audio(wav_path)

    def load_audio(self, wav_path: Union[str, Path]) -> bool:
        """Loads and normalizes WAV audio into a single-channel float32 array in [-1.0, 1.0]."""
        p = Path(wav_path)
        if not p.exists() or not p.is_file():
            self.has_audio = False
            return False

        try:
            with wave.open(str(p), "rb") as wf:
                n_channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                self.sample_rate = wf.getframerate()
                n_frames = wf.getnframes()
                raw_bytes = wf.readframes(n_frames)

            if sampwidth == 2:
                # 16-bit PCM
                raw_samples = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            elif sampwidth == 4:
                # 32-bit float or PCM
                raw_samples = np.frombuffer(raw_bytes, dtype=np.int32).astype(np.float32) / 2147483648.0
            else:
                raw_samples = np.frombuffer(raw_bytes, dtype=np.uint8).astype(np.float32) / 128.0 - 1.0

            # Mix down to mono if stereo/multi-channel
            if n_channels > 1:
                raw_samples = raw_samples.reshape(-1, n_channels).mean(axis=1)

            self.samples = raw_samples
            self.duration_sec = len(self.samples) / float(self.sample_rate)
            self.has_audio = True
            return True
        except Exception:
            self.has_audio = False
            return False

    def get_rms_at(self, t: float, window_sec: float = 0.05) -> float:
        """
        Computes Root-Mean-Square (RMS) loudness energy in [0.0, 1.0] at timestamp t.
        Falls back to dynamic procedural harmonic pulse if no audio is loaded.
        """
        if not self.has_audio or len(self.samples) == 0:
            # Procedural fallback pulse
            return 0.3 + 0.2 * math.sin(t * 4.0) + 0.1 * math.cos(t * 9.2)

        center_idx = int(t * self.sample_rate)
        half_win = int(window_sec * self.sample_rate / 2)
        start = max(0, center_idx - half_win)
        end = min(len(self.samples), center_idx + half_win)

        if start >= end:
            return 0.0

        segment = self.samples[start:end]
        rms = float(np.sqrt(np.mean(segment ** 2)))
        return min(1.0, rms * 3.5)  # Scaled for visual responsiveness

    def get_frequency_bands_at(self, t: float, window_sec: float = 0.05) -> Dict[str, float]:
        """
        Computes 3-band spectral energy (Bass, Mid, Treble) normalized to [0.0, 1.0].
        """
        if not self.has_audio or len(self.samples) == 0:
            # Procedural rhythmic fallback
            f_bass = abs(math.sin(t * 3.5))
            f_mid = abs(math.cos(t * 5.2))
            f_treble = abs(math.sin(t * 8.8 + 1.2))
            return {"bass": f_bass, "mid": f_mid, "treble": f_treble}

        center_idx = int(t * self.sample_rate)
        win_size = int(window_sec * self.sample_rate)
        start = max(0, center_idx - win_size // 2)
        end = min(len(self.samples), start + win_size)

        if end - start < 64:
            return {"bass": 0.0, "mid": 0.0, "treble": 0.0}

        segment = self.samples[start:end]
        # Fast Fourier Transform
        fft_vals = np.abs(np.fft.rfft(segment))
        freqs = np.fft.rfftfreq(len(segment), 1.0 / self.sample_rate)

        # Band masks
        bass_mask = (freqs >= 20) & (freqs < 250)
        mid_mask = (freqs >= 250) & (freqs < 4000)
        treble_mask = (freqs >= 4000) & (freqs < 16000)

        bass = float(np.mean(fft_vals[bass_mask])) if np.any(bass_mask) else 0.0
        mid = float(np.mean(fft_vals[mid_mask])) if np.any(mid_mask) else 0.0
        treble = float(np.mean(fft_vals[treble_mask])) if np.any(treble_mask) else 0.0

        # Normalization
        norm_bass = min(1.0, bass / 15.0)
        norm_mid = min(1.0, mid / 10.0)
        norm_treble = min(1.0, treble / 5.0)

        return {"bass": norm_bass, "mid": norm_mid, "treble": norm_treble}

    def get_beat_envelope_at(self, t: float) -> float:
        """
        Detects sharp energy transients (drum hits, bass drops, speech plosives)
        by comparing instantaneous energy to preceding short-term average.
        """
        e_curr = self.get_rms_at(t, window_sec=0.03)
        e_prev = self.get_rms_at(max(0.0, t - 0.06), window_sec=0.06)

        delta = max(0.0, e_curr - e_prev)
        return min(1.0, delta * 2.5)
