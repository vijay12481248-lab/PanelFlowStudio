"""
Unit tests for AudioMixer (Milestone 7).
Verifies speech mixing, smooth ducking envelope, peak normalization, NaN sanitization, and 48 kHz mixdown.
"""
import math
from pathlib import Path
import numpy as np
import pytest
import soundfile as sf

from engine.render.audio import AudioMixer
from engine.render.models.render_plan import RenderPlan, RenderShotPlan, RenderAudioTrack
from engine.render.models.enums import MusicDurationPolicy, ScalePolicy
from engine.render.models.profiles import RenderProfile
from engine.motion.models.camera import CameraState


def test_ducking_envelope_geometry():
    mixer = AudioMixer(sample_rate=48000, channels=2)
    total_samples = 48000 * 5  # 5 seconds
    # Speech from 1.0s to 3.0s
    speech_intervals = [(1.0, 3.0)]

    envelope = mixer._build_ducking_envelope(
        total_samples=total_samples,
        speech_intervals=speech_intervals,
        duck_db=-8.0,
        attack_sec=0.25,
        release_sec=0.40,
    )

    assert len(envelope) == total_samples

    # Non-speech region (e.g. at 0.2s = sample 9600) -> 1.0
    assert pytest.approx(envelope[9600], abs=0.01) == 1.0

    # During speech (e.g. at 2.0s = sample 96000) -> ducked (-8 dB = 0.398)
    duck_val = math.pow(10.0, -8.0 / 20.0)
    assert pytest.approx(envelope[96000], abs=0.01) == duck_val

    # Ramp up release region (e.g. at 3.2s = sample 153600) -> between duck_val and 1.0
    rel_sample = int(3.2 * 48000)
    assert duck_val < envelope[rel_sample] < 1.0

    # After release (e.g. at 4.0s = sample 192000) -> back to 1.0
    assert pytest.approx(envelope[192000], abs=0.01) == 1.0


def test_audio_buffer_audit_and_sanitize():
    mixer = AudioMixer(sample_rate=48000, channels=2)

    # 1. Test NaN and Inf sanitization
    buf_corrupt = np.array([[0.1, np.nan], [np.inf, -np.inf], [0.2, 0.3]], dtype=np.float32)
    metrics_corrupt = mixer._audit_and_sanitize_buffer(buf_corrupt)
    assert metrics_corrupt["has_nan"] is True
    assert metrics_corrupt["has_inf"] is True
    assert not np.isnan(buf_corrupt).any()
    assert not np.isinf(buf_corrupt).any()

    # 2. Test clipping prevention and soft-limiting to -1.0 dBFS
    buf_hot = np.ones((4800, 2), dtype=np.float32) * 1.5  # Hot signal > 1.0
    metrics_hot = mixer._audit_and_sanitize_buffer(buf_hot)
    assert metrics_hot["clipping_detected"] is True
    assert metrics_hot["peak_val"] <= 0.895
    assert pytest.approx(metrics_hot["peak_dbfs"], abs=0.1) == -1.0


def test_audio_mixer_end_to_end_mix(tmp_path: Path):
    mixer = AudioMixer(sample_rate=48000, channels=2)

    # Create dummy speech WAV (1.0s sine wave at 440 Hz)
    speech_path = tmp_path / "speech_test.wav"
    t_speech = np.linspace(0, 1.0, 48000, endpoint=False)
    sine_speech = (0.5 * np.sin(2 * np.pi * 440 * t_speech)).astype(np.float32)
    sf.write(str(speech_path), sine_speech, 48000)

    # Create dummy music WAV (2.0s sine wave at 220 Hz)
    music_path = tmp_path / "music_test.wav"
    t_music = np.linspace(0, 2.0, 48000 * 2, endpoint=False)
    sine_music = (0.2 * np.sin(2 * np.pi * 220 * t_music)).astype(np.float32)
    sf.write(str(music_path), sine_music, 48000)

    # Plan with 3.0s total duration
    shot = RenderShotPlan(
        shot_id="shot_01",
        scene_id="sc_01",
        sequence_global=1,
        source_asset_path="dummy.jpg",
        start_frame=0,
        end_frame=90,
        total_frames=90,
        start_time=0.0,
        end_time=3.0,
        duration=3.0,
        camera_start=CameraState(center_x=0.5, center_y=0.5, zoom=1.0),
        camera_end=CameraState(center_x=0.5, center_y=0.5, zoom=1.0),
    )

    tracks = [
        RenderAudioTrack(
            track_type="dialogue",
            file_path=str(speech_path),
            start_time=0.5,
            end_time=1.5,
            gain_db=0.0,
        ),
        RenderAudioTrack(
            track_type="music",
            file_path=str(music_path),
            start_time=0.0,
            end_time=3.0,
            gain_db=-3.0,
        ),
    ]

    plan = RenderPlan(
        plan_id="plan_mix_test",
        project_id="proj_01",
        total_duration_sec=3.0,
        total_frames=90,
        profile=RenderProfile.standard_1080p(),
        shots=[shot],
        audio_tracks=tracks,
        music_policy=MusicDurationPolicy.LOOP,
        hash="test_mix_hash",
    )

    out_wav = tmp_path / "output_master.wav"
    success, metrics = mixer.mix_timeline_audio(plan, out_wav)

    assert success is True
    assert out_wav.exists()
    assert out_wav.stat().st_size > 0

    # Verify output audio properties
    data, sr = sf.read(str(out_wav))
    assert sr == 48000
    assert data.ndim == 2
    assert data.shape[1] == 2
    assert len(data) == 48000 * 3
    assert not metrics["clipping_detected"]
    assert metrics["peak_val"] > 0.05
