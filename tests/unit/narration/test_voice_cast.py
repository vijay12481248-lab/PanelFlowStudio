import asyncio

import numpy as np

from engine.narration.artifacts import (
    LineMarks, NARRATOR_ID, PerformancePlan, ScriptIR, ScriptLine, SeriesBible,
)
from engine.narration.runtime.audio import SR
from engine.narration.steps.voice import voice_lines


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
    """Returns no words: every take is flagged, but the voice that read it is still recorded."""

    def words(self, wav_path):
        return "", []


def _script(*speakers):
    return ScriptIR(project_id="p", lines=[
        ScriptLine(line_id=f"L{i}", panel_id=f"P{i}", text=f"the line number {i} is said out loud now",
                   facts_used=["action"], kind="narration", speaker_id=sid)
        for i, sid in enumerate(speakers)])


def _plan(n):
    return PerformancePlan(project_id="p", script_revision=0, lines=[
        LineMarks(line_id=f"L{i}", emotion="calm", energy="med", rate=1.0, pause_after_ms=200) for i in range(n)])


def test_each_character_is_read_with_its_own_voice(tmp_path):
    """The cast decides the voice: the narrator keeps the narrator's, a character keeps its own."""
    script = _script(NARRATOR_ID, "c1")
    tts = FakeTts()
    takes, _ = asyncio.run(voice_lines(script, _plan(2), SeriesBible(series_key="s"), tts, FakeStt(),
                                       tmp_path, "am_michael", cast={"c1": "af_heart"}))
    assert [t.voice_id for t in takes] == ["am_michael", "af_heart"]


def test_a_character_without_a_cast_voice_is_read_by_the_narrator(tmp_path):
    script = _script(NARRATOR_ID, "c1")
    tts = FakeTts()
    takes, _ = asyncio.run(voice_lines(script, _plan(2), SeriesBible(series_key="s"), tts, FakeStt(),
                                       tmp_path, "am_michael", cast={}))
    assert [t.voice_id for t in takes] == ["am_michael", "am_michael"]


def test_a_take_records_the_voice_that_read_it(tmp_path):
    script = _script("c1")
    tts = FakeTts()
    takes, _ = asyncio.run(voice_lines(script, _plan(1), SeriesBible(series_key="s"), tts, FakeStt(),
                                       tmp_path, "am_michael", cast={"c1": "af_heart"}))
    assert takes[0].voice_id == "af_heart"


def test_two_characters_are_voiced_apart(tmp_path):
    """The same words read by two voices are two different takes."""
    script = _script("c1", "c2")
    tts = FakeTts()
    takes, _ = asyncio.run(voice_lines(script, _plan(2), SeriesBible(series_key="s"), tts, FakeStt(),
                                       tmp_path, "am_michael", cast={"c1": "af_heart", "c2": "am_adam"}))
    assert [t.voice_id for t in takes] == ["af_heart", "am_adam"]
    assert takes[0].audio_path != takes[1].audio_path
