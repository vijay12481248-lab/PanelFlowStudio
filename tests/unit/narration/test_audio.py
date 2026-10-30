import wave

import numpy as np
import pytest

from engine.narration.runtime.audio import SR, normalize_silence, wer, write_wav_atomic
from engine.narration.runtime.roles import load_stt_config, load_tts_config


def _tone(sec):
    t = np.arange(int(SR * sec)) / SR
    return (0.5 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def _z(sec):
    return np.zeros(int(SR * sec), dtype=np.float32)


def test_normalize_trims_and_pads_to_80ms():
    audio = np.concatenate([_z(0.3), _tone(0.5), _z(0.2)])
    out, lead, tail = normalize_silence(audio)
    assert abs(lead - 300) <= 20 and abs(tail - 200) <= 20
    assert abs(len(out) - (int(SR * 0.5) + 2 * int(SR * 0.08))) <= SR * 0.02
    assert not out[: int(SR * 0.08)].any() and not out[-int(SR * 0.08):].any()


def test_normalize_no_silence_still_pads():
    out, lead, tail = normalize_silence(_tone(0.5))
    assert lead == 0 and tail == 0
    assert len(out) == int(SR * 0.5) + 2 * int(SR * 0.08)


def test_normalize_all_silent_raises():
    with pytest.raises(ValueError, match="take is silent"):
        normalize_silence(_z(0.5))


def test_wer_cases():
    assert wer("the quick brown fox", "The quick, brown fox!") == 0
    assert wer("the quick brown fox", "the quick red fox") == 0.25
    assert wer("the quick brown fox", "") == 1.0
    with pytest.raises(ValueError):
        wer("", "x")


def test_write_wav_atomic_duration(tmp_path):
    p = tmp_path / "a.wav"
    assert write_wav_atomic(p, _tone(0.5)) == pytest.approx(0.5)
    with wave.open(str(p)) as w:
        assert w.getframerate() == SR and w.getnchannels() == 1
    assert [f.name for f in tmp_path.iterdir()] == ["a.wav"]


def test_audio_config_loads():
    assert load_tts_config().model == "kokoro-82m" and load_tts_config().voice == "am_michael"
    s = load_stt_config()
    assert (s.model, s.device, s.compute_type) == ("base", "cpu", "int8")


def test_normalize_sub_frame_input_still_pads():
    out, _, _ = normalize_silence(np.full(100, 0.5, np.float32))
    assert len(out) == 100 + 2 * int(SR * 0.08)
    with pytest.raises(ValueError):
        normalize_silence(np.zeros(100, np.float32))


def test_to_16k_resamples_wav(tmp_path):
    import numpy as np
    from engine.narration.runtime.audio import to_16k, write_wav_atomic
    p = tmp_path / "a.wav"
    write_wav_atomic(p, np.ones(24000, dtype=np.float32) * 0.5)
    out = to_16k(p)
    assert out.dtype == np.float32 and abs(out.size - 16000) <= 1 and abs(float(out.mean()) - 0.5) < 1e-3
