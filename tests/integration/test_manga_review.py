import uuid
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf

from engine.database.session import init_db, SessionLocal
from engine.database.models import VideoScriptRecord, ScriptSegmentRecord, AudioTimelineRecord, VisualTimelineRecord, NarrativeRecord, CharacterRecord
from engine.projects.service import ProjectService
from engine.story.script.review import apply_script_action
from engine.audio.service import AudioService


@pytest.fixture
def chapter(tmp_path):
    init_db()
    with SessionLocal() as db:
        project = ProjectService(tmp_path).create_project(db, "Review chapter", "LOCAL_FOLDER", "USER_OWNED")
        script = VideoScriptRecord(id=uuid.uuid4().hex, project_id=project.id, status="APPROVED")
        db.add(script)
        db.flush()
        for index in (1, 2):
            db.add(ScriptSegmentRecord(id=uuid.uuid4().hex, script_id=script.id, project_id=project.id,
                                       scene_id="scene", sequence=index, type="NARRATOR", text=f"Sentence {index}. A second sentence.",
                                       estimated_duration=4, estimated_start=(index - 1) * 4, estimated_end=index * 4,
                                       source_evidence={"panel_ids": [f"p{index}"]}))
        db.commit()
        yield db, project, script


def test_split_remove_persists_correct_clocks_after_reopen(chapter):
    db, project, script = chapter
    first_id = script.segments[0].id
    updated = apply_script_action(db, project.id, script.id, first_id, "split")
    assert len(updated.segments) == 3
    assert updated.estimated_duration == pytest.approx(sum(s.estimated_duration for s in updated.segments))
    assert updated.segments[-1].estimated_end == pytest.approx(updated.estimated_duration)
    removed = apply_script_action(db, project.id, script.id, updated.segments[1].segment_id, "remove")
    assert len(removed.segments) == 2
    assert removed.segments[-1].estimated_end == pytest.approx(removed.estimated_duration)
    assert removed.status == "DRAFT"


def test_audio_has_explicit_pause_and_preserves_gap_on_regeneration(chapter, monkeypatch):
    db, project, script = chapter
    service = AudioService()
    def synthesize(directory, text, voice, **kwargs):
        path = Path(directory) / f"{uuid.uuid4().hex}.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(path), np.zeros(48000 * (3 if kwargs.get("force") else 2)), 48000)
        return path
    service.synthesizer = SimpleNamespace(synthesize=synthesize)
    first = script.segments[0]
    second = script.segments[1]
    second.sequence = 3
    pause = ScriptSegmentRecord(id=uuid.uuid4().hex, script_id=script.id, project_id=project.id,
                                scene_id="scene", sequence=2, type="PAUSE", text="", estimated_duration=4)
    db.add(pause)
    db.commit()
    db.expire(script, ["segments"])
    generated = service.generate_audio_timeline(db, project.id)
    intervals = generated["timeline"]["intervals"]
    assert len(intervals) == 3
    assert intervals[1]["is_speech"] is False
    assert intervals[1]["end_time"] - intervals[1]["start_time"] == 4
    before = intervals[-1]["start_time"]
    motion = VisualTimelineRecord(project_id=project.id, status="APPROVED")
    db.add(motion)
    db.commit()
    regenerated = service.regenerate_segment_audio(db, project.id, first.id)
    after_intervals = regenerated["timeline"]["intervals"]
    assert after_intervals[-1]["start_time"] == pytest.approx(before + 1)
    assert after_intervals[1]["end_time"] - after_intervals[1]["start_time"] == 4
    db.refresh(motion)
    assert motion.status == "STALE"


def test_visual_narrative_reads_reviewed_character_registry(chapter):
    from engine.story.service import story_service
    from engine.story.models import NarrativeDocument, CharacterEntity
    db, project, script = chapter
    identifier = uuid.uuid4().hex
    document = NarrativeDocument(project_id=project.id,
        characters=[CharacterEntity(character_id=identifier, display_name="Unknown Man A")],
        analysis_metadata={"engine": "vision-story-v1"})
    db.add(NarrativeRecord(project_id=project.id, document=document.model_dump()))
    db.add(CharacterRecord(id=identifier, project_id=project.id, display_name="Reviewed name", manual_override=True))
    db.commit()
    refreshed = story_service.get_narrative(db, project.id)
    assert refreshed.characters[0].display_name == "Reviewed name"
    assert refreshed.characters[0].manual_override
