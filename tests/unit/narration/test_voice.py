import asyncio

import numpy as np
import pytest

from engine.narration.artifacts import (
    BibleCharacter, LineMarks, PerformancePlan, ScriptIR, ScriptLine, SeriesBible, Word,
)
from engine.narration.runtime.audio import SR
from engine.narration.steps.voice import tts_text, voice_lines


class FakeTts:
    def __init__(self):
        self.calls = []

    def synth(self, text, voice, rate):
        self.calls.append((text, voice, rate))
        n = len(text.split())
        t = np.arange(int(SR * 0.3 * n)) / SR
        tone = (0.5 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
        return np.concatenate([np.zeros(int(SR * 0.2), np.float32), tone])


class FakeStt:
    """Returns scripted texts in order (the last repeats); None echoes the reference."""

    def __init__(self, texts):
        self.texts = list(texts)
        self.n = 0

    def words(self, wav_path):
        text = self.texts[min(self.n, len(self.texts) - 1)]
        self.n += 1
        ws = text.split()
        return text, [Word(text=w, start=0.1 + 0.3 * i, end=0.1 + 0.3 * i + 0.25) for i, w in enumerate(ws)]


def _script(*texts):
    return ScriptIR(project_id="p", lines=[
        ScriptLine(line_id=f"L{i}", panel_id=f"P{i}", text=t, facts_used=["action"], kind="narration")
        for i, t in enumerate(texts)])


def _plan(n, rate=1.0):
    return PerformancePlan(project_id="p", script_revision=0, lines=[
        LineMarks(line_id=f"L{i}", emotion="calm", energy="med", rate=rate, pause_after_ms=200) for i in range(n)])


BIBLE = SeriesBible(series_key="s")


def _run(script, plan, stt, tts, tmp_path, bible=BIBLE):
    return asyncio.run(voice_lines(script, plan, bible, tts, stt, tmp_path, "am_michael"))


def test_take_has_80ms_lead_and_words(tmp_path):
    script = _script("the hero draws his sword")
    tts = FakeTts()
    takes, reasons = _run(script, _plan(1), FakeStt([script.lines[0].text]), tts, tmp_path)
    t = takes[0]
    assert reasons == [] and not t.flagged and t.wer == 0 and t.attempt == 1
    assert abs(t.lead_ms - 200) <= 20 and t.words and len(t.words) == 5
    import wave
    with wave.open(t.audio_path) as w:
        head = np.frombuffer(w.readframes(int(SR * 0.08)), dtype="<i2")
        assert not head.any() and w.getnframes() / SR == pytest.approx(t.duration)


def test_bad_wer_retries_slower_then_flags(tmp_path):
    tts = FakeTts()
    takes, reasons = _run(_script("the hero draws his sword"), _plan(1, 1.0), FakeStt(["nothing like it at all"]), tts, tmp_path)
    assert [c[2] for c in tts.calls] == pytest.approx([1.0, 0.95, 0.9])
    assert takes[0].attempt == 3 and takes[0].flagged
    assert reasons == ["1 of 1 takes failed the speech check"]


def test_retry_that_passes_is_kept(tmp_path):
    tts = FakeTts()
    takes, _ = _run(_script("the hero draws his sword"), _plan(1), FakeStt(["wrong words entirely here", "the hero draws his sword"]), tts, tmp_path)
    assert takes[0].attempt == 2 and not takes[0].flagged and takes[0].rate == pytest.approx(0.95)


def test_zero_words_from_stt_is_flag_not_crash(tmp_path):
    takes, _ = _run(_script("the hero draws his sword"), _plan(1), FakeStt([""]), FakeTts(), tmp_path)
    assert takes[0].flagged and takes[0].words == [] and takes[0].wer == 1.0


def test_rerun_reuses_wavs(tmp_path):
    script = _script("one two three", "four five six")
    stt = FakeStt([script.lines[0].text, script.lines[1].text])
    first = FakeTts()
    a, _ = _run(script, _plan(2), stt, first, tmp_path)
    second = FakeTts()
    b, _ = _run(script, _plan(2), stt, second, tmp_path)
    assert len(first.calls) == 2 and second.calls == []
    assert a == b


def test_pronunciation_only_in_tts_text(tmp_path):
    bible = SeriesBible(series_key="s", characters=[
        BibleCharacter(id="c", name="Shangguan", aliases=["Guan"], pronunciation="Shang-gwahn")])
    assert tts_text("Shangguan nods. Guanxi stays.", bible) == "Shang-gwahn nods. Guanxi stays."
    script = _script("Shangguan nods")
    tts = FakeTts()
    takes, _ = _run(script, _plan(1), FakeStt([script.lines[0].text]), tts, tmp_path, bible)
    assert tts.calls[0][0] == "Shang-gwahn nods" and takes[0].stt_text == "Shangguan nods"


def test_too_many_flags_reason(tmp_path):
    script = _script(*[f"line number {i}" for i in range(4)])
    stt = FakeStt(["line number 0", "line number 1", "zzz", "zzz", "zzz", "line number 3"])
    takes, reasons = _run(script, _plan(4), stt, FakeTts(), tmp_path)
    assert [t.flagged for t in takes] == [False, False, True, False]
    assert reasons == ["1 of 4 takes failed the speech check"]

