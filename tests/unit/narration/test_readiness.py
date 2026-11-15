"""The readiness report: what is still open before the project renders."""
from engine.narration.artifacts import (
    LineMarks, NARRATOR_ID, PerformancePlan, ScriptIR, ScriptLine, VoiceTake,
)
from engine.narration.casting import CastPlan
from engine.narration.qa import QaCheck, QaReport
from engine.narration.readiness import readiness


def _script(*statuses):
    return ScriptIR(project_id="p", revision=2, lines=[
        ScriptLine(line_id=f"L{i + 1}", panel_id=f"P{i + 1}", text=f"the line number {i + 1} is said out loud",
                   facts_used=["action"], kind="narration", status=status)
        for i, status in enumerate(statuses)])


def _take(line_id="L1"):
    return VoiceTake(line_id=line_id, audio_path=f"{line_id}.wav", duration=2.0, words=[], lead_ms=80, tail_ms=80,
                     stt_text="", wer=0.0, tts_model="kokoro-82m", voice_id="am_michael", rate=1.0, attempt=1)


def test_a_chapter_with_everything_done_is_ready():
    report = readiness(_script("passed", "passed"), [_take("L1"), _take("L2")], {}, None, [], music_tracks=2)
    assert report.ready is True
    assert report.issues == []


def test_a_line_still_waiting_for_review_blocks_the_render():
    report = readiness(_script("draft", "passed"), [_take("L1"), _take("L2")], {}, None, [], music_tracks=2)
    assert report.ready is False
    assert report.lines_awaiting_review == ["L1"]
    assert report.blockers[0].kind == "line"


def test_a_character_without_a_voice_blocks_the_render():
    plan = CastPlan(series_key="s", assignments=[], uncast=["c1"])
    report = readiness(_script("passed"), [_take()], {}, plan, [], music_tracks=2)
    assert report.ready is False
    assert report.characters_without_a_voice == ["c1"]
    assert any(i.kind == "voice" for i in report.issues)


def test_a_take_that_failed_the_qa_blocks_the_render():
    qa = {"L1": QaReport(line_id="L1", passed=False, checks=[
        QaCheck(rule="intelligibility", passed=False, severity="block", reason="word error rate 80%",
                repair="regenerate the line with a slower pace")])}
    report = readiness(_script("passed"), [_take()], qa, None, [], music_tracks=2)
    assert report.ready is False
    assert report.failed_qa_lines == ["L1"]


def test_an_outdated_take_is_a_warning_not_a_blocker():
    """A take that no longer matches its line needs attention, but it does not stop the render."""
    report = readiness(_script("passed"), [_take()], {}, None, ["L1"], music_tracks=2)
    assert report.ready is True
    assert report.outdated_take_lines == ["L1"]
    assert report.issues[0].severity == "warn"


def test_no_music_is_a_warning():
    report = readiness(_script("passed"), [_take()], {}, None, [], music_tracks=0)
    assert report.ready is True
    assert any(i.kind == "music" for i in report.issues)


def test_the_music_is_not_judged_when_it_is_not_known_yet():
    report = readiness(_script("passed"), [_take()], {}, None, [], music_tracks=None)
    assert not any(i.kind == "music" for i in report.issues)
