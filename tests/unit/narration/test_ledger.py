import pytest

from engine.narration.artifacts import (
    LineMarks, NARRATOR_ID, PerformancePlan, ScriptIR, ScriptLine, VoiceTake,
)
from engine.narration.ledger import TakeLedger, outdated_lines


def _script(*speakers, revision=0):
    return ScriptIR(project_id="p", revision=revision, lines=[
        ScriptLine(line_id=f"L{i + 1}", panel_id=f"P{i + 1}", text=f"the line number {i + 1} is said out loud",
                   facts_used=["action"], kind="narration", speaker_id=sid)
        for i, sid in enumerate(speakers)])


def _take(line_id="L1", **kw):
    base = dict(line_id=line_id, audio_path=f"{line_id}.wav", duration=1.0, words=[], lead_ms=80, tail_ms=80,
                stt_text="", wer=0.0, tts_model="kokoro-82m", voice_id="am_michael", rate=1.0, attempt=1)
    return VoiceTake(**{**base, **kw})


def test_a_take_records_what_it_was_made_from():
    script = _script(NARRATOR_ID, "c1", revision=3)
    ledger = TakeLedger(script, direction_revision=3, voice_profile_ids={"narrator": "narrator", "c1": "aria"},
                        provider="kokoro-82m")
    line = script.lines[1]
    assert ledger.provenance(line) == {"script_revision": 3, "direction_revision": 3,
                                       "voice_profile_id": "aria", "provider": "kokoro-82m"}


def test_a_take_of_the_current_script_is_not_outdated():
    script = _script(NARRATOR_ID, "c1", revision=3)
    ledger = TakeLedger(script, direction_revision=3, voice_profile_ids={"narrator": "narrator", "c1": "aria"})
    take = _take("L2", script_revision=3, direction_revision=3, voice_profile_id="aria")
    assert ledger.is_outdated(take) is False


def test_a_take_of_an_older_script_is_outdated():
    """The line has moved on since the take was made, so the take is not the current one."""
    script = _script(NARRATOR_ID, "c1", revision=4)
    ledger = TakeLedger(script, direction_revision=4, voice_profile_ids={"narrator": "narrator", "c1": "aria"})
    take = _take("L2", script_revision=3, direction_revision=3, voice_profile_id="aria")
    assert ledger.is_outdated(take) is True


def test_a_take_of_an_older_direction_is_outdated():
    script = _script(NARRATOR_ID, "c1", revision=3)
    ledger = TakeLedger(script, direction_revision=4, voice_profile_ids={"narrator": "narrator", "c1": "aria"})
    take = _take("L2", script_revision=3, direction_revision=3, voice_profile_id="aria")
    assert ledger.is_outdated(take) is True


def test_a_take_read_by_another_voice_is_outdated():
    """The owner recast the character, so the old take no longer belongs to it."""
    script = _script(NARRATOR_ID, "c1", revision=3)
    ledger = TakeLedger(script, direction_revision=3, voice_profile_ids={"narrator": "narrator", "c1": "aria"})
    take = _take("L2", script_revision=3, direction_revision=3, voice_profile_id="bella")
    assert ledger.is_outdated(take) is True


def test_a_take_of_a_line_that_no_longer_exists_is_outdated():
    script = _script(NARRATOR_ID, revision=3)
    ledger = TakeLedger(script, direction_revision=3, voice_profile_ids={"narrator": "narrator"})
    take = _take("L9", script_revision=3, direction_revision=3, voice_profile_id="narrator")
    assert ledger.is_outdated(take) is True


def test_the_outdated_lines_are_listed():
    script = _script(NARRATOR_ID, "c1", revision=4)
    ledger = TakeLedger(script, direction_revision=4, voice_profile_ids={"narrator": "narrator", "c1": "aria"})
    takes = [_take("L1", script_revision=4, direction_revision=4, voice_profile_id="narrator"),
             _take("L2", script_revision=3, direction_revision=3, voice_profile_id="aria")]
    assert outdated_lines(takes, ledger) == ["L2"]
