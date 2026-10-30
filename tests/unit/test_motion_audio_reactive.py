"""
Unit tests for the Audio-Reactive Feature Extractor and Beat Synchronizer.
"""

from pathlib import Path
import wave
import math
import struct
import pytest
from engine.render.motion.audio import AudioFeatureExtractor


@pytest.fixture
def sample_wav(tmp_path) -> Path:
    """Generates a deterministic 1.0s synthetic 44.1kHz WAV file with a drum transient at t=0.5s."""
    wav_path = tmp_path / "test_synth_audio.wav"
    sample_rate = 44100
    duration = 1.0
    num_samples = int(sample_rate * duration)

    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)

        frames = []
        for i in range(num_samples):
            t = i / sample_rate
            # 220Hz baseline sine
            val = math.sin(2.0 * math.pi * 220.0 * t) * 0.3
            # Add sharp transient at t=0.5s (duration 0.04s)
            if 0.50 <= t <= 0.54:
                val += math.sin(2.0 * math.pi * 60.0 * t) * 0.6  # Heavy bass punch

            int_val = int(max(-1.0, min(1.0, val)) * 32767.0)
            frames.append(struct.pack("<h", int_val))

        wf.writeframes(b"".join(frames))

    return wav_path


def test_audio_feature_extractor_with_file(sample_wav):
    extractor = AudioFeatureExtractor(sample_wav)
    assert extractor.has_audio is True
    assert extractor.duration_sec >= 0.99
    assert len(extractor.samples) == 44100

    # RMS loudness
    rms_mid = extractor.get_rms_at(0.52)
    rms_quiet = extractor.get_rms_at(0.10)
    assert rms_mid > rms_quiet

    # Frequency bands
    bands = extractor.get_frequency_bands_at(0.52)
    assert "bass" in bands and "mid" in bands and "treble" in bands
    assert bands["bass"] > 0.0

    # Beat transient onset detection
    beat = extractor.get_beat_envelope_at(0.51)
    assert beat > 0.0


def test_audio_feature_extractor_fallback():
    # Fallback when no audio is provided
    extractor = AudioFeatureExtractor(None)
    assert extractor.has_audio is False

    rms = extractor.get_rms_at(1.5)
    assert 0.0 <= rms <= 1.0

    bands = extractor.get_frequency_bands_at(1.5)
    assert "bass" in bands and "mid" in bands and "treble" in bands

    beat = extractor.get_beat_envelope_at(1.5)
    assert 0.0 <= beat <= 1.0
