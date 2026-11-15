import uuid
from pathlib import Path

from engine.database.models import ProjectRecord, ScriptSegmentRecord
from engine.database.session import SessionLocal, init_db
from engine.narration.artifacts import NARRATOR_ID
from engine.narration.project import apply_to_project
from engine.narration.steps.timeline import lock_timeline
from tests.unit.narration.test_timeline import _world


def _setup(tmp_path, speaker_names=None):
    init_db()
    pid = str(uuid.uuid4())
    script, plan, takes, sheet, ids = _world([(2.0, 300), (2.0, 300), (2.0, 300)])
    for t in takes:
        wav = tmp_path / f"k{t.line_id}.wav"
        wav.write_bytes(b"RIFFdata-" + t.line_id.encode())
        t.audio_path = str(wav)
    with SessionLocal() as db:
        db.add(ProjectRecord(id=pid, title="T", source_type="LOCAL_FOLDER", workspace_path=str(tmp_path),
                             settings={}))
        db.commit()
    tl = lock_timeline(script, plan, takes, sheet, ids)
    return pid, tl, script, sheet, takes, plan


def test_a_character_speaker_is_named_on_the_clip_and_the_segment(tmp_path):
    """A line read by a character names that character; the segment records who speaks it."""
    pid, tl, script, sheet, takes, plan = _setup(tmp_path)
    script.lines[1].speaker_id = "c7"
    with SessionLocal() as db:
        apply_to_project(db, pid, tl, script, sheet, takes, tmp_path, plan,
                         speaker_names={"c7": "Vex Ardent"})
        clips = db.get(ProjectRecord, pid).settings["story_editor_state"]["narration_clips"]
        segments = db.query(ScriptSegmentRecord).filter(ScriptSegmentRecord.project_id == pid).all()

    assert clips[0]["speaker"] == "Narrator" and clips[0]["voice"] == "Narrator"
    assert clips[1]["speaker"] == "Vex Ardent" and clips[1]["voice"] == "Vex Ardent"
    assert [s.type for s in segments] == ["NARRATOR", "CHARACTER_DIALOGUE", "NARRATOR"]
    assert [s.speaker_character_id for s in segments] == [None, "c7", None]


def test_a_narrator_line_records_no_speaker_character(tmp_path):
    pid, tl, script, sheet, takes, plan = _setup(tmp_path)
    with SessionLocal() as db:
        apply_to_project(db, pid, tl, script, sheet, takes, tmp_path, plan)
        segments = db.query(ScriptSegmentRecord).filter(ScriptSegmentRecord.project_id == pid).all()
    assert all(s.type == "NARRATOR" for s in segments)
    assert all(s.speaker_character_id is None for s in segments)


def test_the_performance_intent_reaches_the_segment(tmp_path):
    """The direction the performer wrote is kept with the segment it belongs to."""
    pid, tl, script, sheet, takes, plan = _setup(tmp_path)
    plan.lines[0].intent = "let the threat land before the answer"
    with SessionLocal() as db:
        apply_to_project(db, pid, tl, script, sheet, takes, tmp_path, plan)
        segments = db.query(ScriptSegmentRecord).filter(ScriptSegmentRecord.project_id == pid).all()
    assert segments[0].production_intent == "let the threat land before the answer"
