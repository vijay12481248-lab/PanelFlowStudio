import pytest

from engine.narration.artifacts import (
    Beat, BeatSheet, LineMarks, LockedTimeline, PerformancePlan, Scene, ScriptIR, ScriptLine, VoiceTake, Word,
)
from engine.narration.steps.timeline import lock_timeline, sync_metrics


def _world(specs):
    """specs: [(duration, pause_ms)]; every line is 5 words, first word at 0.08 s, last ends 0.16 s before the end."""
    ids = [f"p{i}" for i in range(len(specs))]
    script = ScriptIR(project_id="x", lines=[
        ScriptLine(line_id=f"l{i}", panel_id=p, text="one two three four five", facts_used=["action"], kind="narration")
        for i, p in enumerate(ids)])
    plan = PerformancePlan(project_id="x", script_revision=0, lines=[
        LineMarks(line_id=f"l{i}", emotion="neutral", energy="med", rate=1.0, pause_after_ms=pause)
        for i, (_, pause) in enumerate(specs)])
    takes = [VoiceTake(line_id=f"l{i}", audio_path=f"/a/l{i}.wav", duration=d,
                       words=[Word(text="one", start=0.08, end=0.3), Word(text="five", start=d - 0.4, end=d - 0.16)],
                       lead_ms=80, tail_ms=80, stt_text="", wer=0.0, tts_model="k", voice_id="v", rate=1.0, attempt=1)
             for i, (d, _) in enumerate(specs)]
    sheet = BeatSheet(project_id="x", hook="h", chapter_summary="s", scenes=[Scene(
        scene_id="s1", first_panel_id=ids[0], last_panel_id=ids[-1], goal="g", conflict="c", turn="t",
        beats=[Beat(beat_id="b1", panel_ids=ids, what_happens="w", function="setup", intensity=0.5)])])
    return script, plan, takes, sheet, ids


def _lock(specs):
    script, plan, takes, sheet, ids = _world(specs)
    return lock_timeline(script, plan, takes, sheet, ids), script, takes


def test_onset_lands_120ms_after_cut():
    tl, _, _ = _lock([(2.0, 300), (2.0, 300)])
    for clip, panel in zip(tl.clips, tl.panels):
        assert clip.start + 0.08 - panel.start == pytest.approx(0.12)
    assert tl.panels[0].start == 0 and tl.clips[0].start == pytest.approx(0.04)


def test_short_lines_are_held_to_1_2s():
    tl, _, _ = _lock([(0.5, 150), (0.5, 150), (0.5, 150)])
    assert [round(p.end - p.start, 6) for p in tl.panels[:2]] == [1.2, 1.2]
    assert tl.clips[0].end <= tl.clips[1].start and tl.clips[1].end <= tl.clips[2].start


def test_pause_after_respected():
    tl, _, _ = _lock([(2.0, 700), (2.0, 150)])
    assert tl.clips[1].start - tl.clips[0].end == pytest.approx(0.7)


def test_long_take_reported_over_6s():
    tl, script, takes = _lock([(7.0, 300), (2.0, 300)])
    assert tl.panels[0].end - tl.panels[0].start > 6
    assert sync_metrics(tl, takes, script)["holds_over_6"] == 1


def test_metrics_targets():
    tl, script, takes = _lock([(2.0, 300)] * 3)
    m = sync_metrics(tl, takes, script)
    assert m["speech_rate"] == pytest.approx(5 / 1.76)
    assert m["cut_median"] == pytest.approx(2.30)
    assert (m["holds_under_1_2"], m["holds_over_6"]) == (0, 0)
    assert m["onset_ok_share"] == 1.0
    assert (m["wer_median"], m["wer_max"]) == (0.0, 0.0)
    assert m["targets_met"] == {"speech_rate": True, "cut_median": True, "hold_range": True,
                                "onset": True, "wer_median": True, "wer_max": True}
    assert tl.duration == pytest.approx(7.14)


def test_timeline_validates():
    tl, _, _ = _lock([(0.5, 150), (7.0, 800), (2.0, 300)])
    LockedTimeline.model_validate(tl.model_dump())
    assert [p.scene_id for p in tl.panels] == ["s1"] * 3
