"""The audio QA: what is wrong with a take, and the repair that would fix it."""
import wave

import numpy as np
import pytest

from engine.narration.artifacts import VoiceTake
from engine.narration.qa import (
    CLIPPED_SAMPLES, INTELLIGIBLE_LIMIT, QaReport, qa_report, qa_take, repairs,
)
from engine.narration.runtime.audio import SR


def _wav(path, samples, rate=SR):
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return str(path)


def _tone(seconds=2.0, amp=0.5, rate=SR):
    t = np.arange(int(rate * seconds)) / rate
    return (amp * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def _take(tmp_path, **kw):
    base = dict(line_id="L1", audio_path=_wav(tmp_path / "a.wav", _tone()), duration=2.0, words=[],
                lead_ms=80, tail_ms=80, stt_text="the hero draws his sword", wer=0.0,
                tts_model="kokoro-82m", voice_id="am_michael", rate=1.0, attempt=1)
    return VoiceTake(**{**base, **kw})


def test_a_good_take_passes_every_check(tmp_path):
    report = qa_take(_take(tmp_path), "the hero draws his sword", "the hero draws his sword")
    assert report.passed is True
    assert all(c.passed for c in report.checks)
    assert repairs(report) == []


def test_a_line_that_was_not_said_as_written_is_flagged_with_a_repair(tmp_path):
    take = _take(tmp_path, wer=0.6, stt_text="something else entirely")
    report = qa_take(take, "the hero draws his sword", "the hero draws his sword")
    check = next(c for c in report.checks if c.rule == "intelligibility")
    assert check.passed is False and check.severity == "block"
    assert "slower pace" in check.repair
    assert report.passed is False


def test_a_name_heard_wrongly_is_a_pronunciation_repair(tmp_path):
    take = _take(tmp_path, wer=0.45, stt_text="the hero draws his sword")
    report = qa_take(take, "Kai draws his sword", "Kai draws his sword")
    check = next(c for c in report.checks if c.rule == "pronunciation")
    assert check.passed is False
    assert "pronunciation" in check.repair


def test_a_take_of_the_wrong_length_is_flagged(tmp_path):
    take = _take(tmp_path, duration=12.0)
    report = qa_take(take, "the hero draws his sword", "the hero draws his sword")
    check = next(c for c in report.checks if c.rule == "duration")
    assert check.passed is False and "expected" in check.reason


def test_a_clipped_take_is_flagged(tmp_path):
    clipped = np.clip(_tone(amp=1.0) * 4, -1, 1)
    take = _take(tmp_path, audio_path=_wav(tmp_path / "clip.wav", clipped))
    report = qa_take(take, "the hero draws his sword", "the hero draws his sword")
    check = next(c for c in report.checks if c.rule == "clipping")
    assert check.passed is False and "full scale" in check.reason
    assert "lower level" in check.repair


def test_a_take_that_is_mostly_silence_is_flagged(tmp_path):
    quiet = np.zeros(SR, np.float32)
    quiet[: SR // 10] = _tone(0.1)
    take = _take(tmp_path, audio_path=_wav(tmp_path / "quiet.wav", quiet))
    report = qa_take(take, "the hero draws his sword", "the hero draws his sword")
    check = next(c for c in report.checks if c.rule == "silence")
    assert check.passed is False and check.severity == "block"
    assert "mostly silence" in check.repair


def test_a_take_with_silence_around_it_is_flagged_for_timing(tmp_path):
    take = _take(tmp_path, lead_ms=900, tail_ms=700)
    report = qa_take(take, "the hero draws his sword", "the hero draws his sword")
    check = next(c for c in report.checks if c.rule == "timing")
    assert check.passed is False and "silence before" in check.reason
    assert "trim the silence" in check.repair


def test_the_report_lists_the_repairs_in_order(tmp_path):
    take = _take(tmp_path, wer=0.8, lead_ms=900)
    report = qa_take(take, "the hero draws his sword", "the hero draws his sword")
    assert len(repairs(report)) >= 2


def test_the_qa_of_a_chapter_is_reported_by_line(tmp_path):
    takes = [_take(tmp_path, line_id="L1"), _take(tmp_path, line_id="L2", wer=0.9)]
    reports = qa_report(takes, {"L1": "the hero draws his sword", "L2": "the villain laughs aloud"})
    assert set(reports) == {"L1", "L2"}
    assert reports["L1"].passed is True
    assert reports["L2"].passed is False


def test_a_missing_audio_file_does_not_crash_the_check(tmp_path):
    take = _take(tmp_path, audio_path=str(tmp_path / "gone.wav"))
    report = qa_take(take, "the hero draws his sword", "the hero draws his sword")
    assert [c.rule for c in report.checks] == ["intelligibility", "pronunciation", "duration", "clipping",
                                               "silence", "timing"]
