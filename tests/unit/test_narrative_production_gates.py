from copy import deepcopy
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from engine.database.models import Base, NarrativeRecord, ProjectRecord, VideoScriptRecord
from engine.pipeline.autopilot import AutoPilotRunner
from engine.story.models import NarrativeDocument, PanelObservationEntity, ProvenanceReference, ScriptSegment, VideoScript
from engine.story.service import story_service


@pytest.fixture
def production_db(tmp_path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(ProjectRecord(id="p", title="Grounded", source_type="local", workspace_path=str(tmp_path), settings={}))
        db.add(VideoScriptRecord(id="script", project_id="p", status="DRAFT"))
        db.commit()
        yield db
    engine.dispose()


def test_missing_narrative_cannot_approve_script(production_db):
    with pytest.raises(ValueError, match="Narrative IR"):
        story_service.approve_script(production_db, "p", "script")
    assert production_db.get(VideoScriptRecord, "script").status == "DRAFT"


def test_history_missing_narrative_cannot_validate(production_db):
    from engine.history.story import _validate_script
    with pytest.raises(ValueError, match="Narrative IR"):
        _validate_script(production_db, "p", "script")


def test_empty_script_is_not_validated_or_approved(production_db):
    doc = NarrativeDocument(project_id="p")
    production_db.add(NarrativeRecord(id="n", project_id="p", document=doc.model_dump()))
    production_db.commit()
    assert not story_service.validate_script(production_db, "p", "script").passed
    with pytest.raises(ValueError):
        story_service.approve_script(production_db, "p", "script")


def test_history_validates_nonempty_script_with_narrative(production_db):
    from engine.history.story import _validate_script
    production_db.add(NarrativeRecord(id="n", project_id="p", document=NarrativeDocument(project_id="p").model_dump()))
    production_db.commit()
    assert not _validate_script(production_db, "p", "script").passed


def test_unrelated_panel_cannot_supply_lexical_support():
    from engine.story.script.validator import script_validator
    script, narrative, _ = fixture_script()
    narrative.observations[0].visual_summary = ""
    narrative.observations.append(PanelObservationEntity(panel_id="p2", sequence_global=2, visual_summary=script.segments[0].text))
    report = script_validator.validate(script, narrative)
    assert not report.passed
    assert report.unsupported_segments == 1


def test_grounded_adapter_speech_and_blank_pause_can_validate():
    from engine.story.script.adapter import script_adapter
    from engine.story.script.validator import script_validator
    from engine.story.models import SceneEntity, StoryBeatEntity, UtteranceEntity
    _, narrative, _ = fixture_script()
    narrative.scenes = [SceneEntity(scene_id="s", sequence=1, panel_start="p1", panel_end="p1")]
    narrative.beats = [StoryBeatEntity(beat_id="b", scene_id="s", sequence=1, panel_ids=["p1"])]
    narrative.utterances = [UtteranceEntity(utterance_id="u", text_region_id="r", panel_id="p1",
                                           corrected_text="Maya enters the room.")]
    script = script_adapter.adapt(narrative)
    assert any(segment.type == "PAUSE" and not segment.text for segment in script.segments)
    assert script_validator.validate(script, narrative).passed


def test_reused_narration_must_match_approved_script_preserving_creator_voice():
    from engine.pipeline.narration import reconcile_narration_clips
    script, narrative, scenes = fixture_script()
    clips = [{"id": "manual", "scene_id": "editor-scene", "text": script.segments[0].text,
              "voice": "creator-selected", "audio_url": "audio/dialogue/old.wav"}]
    result = reconcile_narration_clips(script, narrative, scenes, clips)
    assert result[0]["voice"] == "creator-selected"
    assert result[0]["id"] == "manual"
    assert result[0]["audio_url"] == clips[0]["audio_url"]
    assert result[0]["source_segment_ids"] == ["seg"]
    assert "source_segment_ids" not in clips[0]
    clips[0]["text"] = "A nonexistent battle begins."
    with pytest.raises(ValueError, match="approved script"):
        reconcile_narration_clips(script, narrative, scenes, clips)


@pytest.mark.asyncio
async def test_audio_without_source_script_stops_before_synthesis(production_db):
    project = production_db.get(ProjectRecord, "p")
    project.settings = {"story_editor_state": {"scenes": [{"id": "one"}]}}
    production_db.commit()
    runner = AutoPilotRunner("p")
    with patch("engine.pipeline.autopilot.SessionLocal", return_value=production_db), patch.object(
        runner, "_persist_status"
    ), patch("engine.audio.synthesis.local_synthesizer.synthesize_batch") as synth:
        with pytest.raises(ValueError, match="script|Narrative"):
            await runner._run_stage_audio(True)
        synth.assert_not_called()


@pytest.mark.asyncio
async def test_script_failure_stops_autopilot_instead_of_approving(production_db):
    runner = AutoPilotRunner("p")
    with patch("engine.pipeline.autopilot.SessionLocal", return_value=production_db), patch.object(
        story_service, "generate_script", side_effect=RuntimeError("provider unavailable")
    ), patch.object(runner, "_persist_status"):
        with pytest.raises(RuntimeError, match="provider unavailable"):
            await runner._run_stage_script(False)
    assert runner.get_stage("script").status != "COMPLETED"


@pytest.mark.asyncio
async def test_generated_script_uses_domain_id_and_approval(production_db):
    runner = AutoPilotRunner("p")
    script = VideoScript(script_id="script", project_id="p")
    with patch("engine.pipeline.autopilot.SessionLocal", return_value=production_db), patch.object(
        story_service, "generate_script", return_value=script
    ), patch.object(story_service, "approve_script") as approve, patch.object(runner, "_persist_status"):
        await runner._run_stage_script(False)
    approve.assert_called_once_with(production_db, "p", "script")


def fixture_script():
    narrative = NarrativeDocument(project_id="p", observations=[PanelObservationEntity(panel_id="p1", sequence_global=1,
                                                                                   visual_summary="Maya enters the room.")])
    script = VideoScript(script_id="script", project_id="p", status="APPROVED", segments=[
        ScriptSegment(segment_id="seg", scene_id="story-scene", type="NARRATOR", text="Maya enters the room.",
                      source_evidence=ProvenanceReference(panel_ids=["p1"]))
    ])
    scenes = [{"id": "editor-scene", "start_time_sec": 0, "layers": [{"source_panel_id": "p1"}]}]
    return script, narrative, scenes


def test_approved_script_maps_by_evidence_preserves_text_and_ids():
    from engine.pipeline.narration import compile_narration_clips
    script, narrative, scenes = fixture_script()
    before = deepcopy(scenes)
    clips = compile_narration_clips(script, narrative, scenes)
    assert clips[0]["scene_id"] == "editor-scene"
    assert clips[0]["text"] == script.segments[0].text
    assert clips[0]["source_segment_ids"] == ["seg"]
    assert clips[0]["source_evidence"]["panel_ids"] == ["p1"]
    assert scenes == before


@pytest.mark.parametrize("defect", ["missing_panel", "ambiguous_scene", "uncovered_scene", "draft", "unsupported"])
def test_compiler_rejects_unusable_grounding(defect):
    from engine.pipeline.narration import compile_narration_clips
    script, narrative, scenes = fixture_script()
    if defect == "missing_panel":
        script.segments[0].source_evidence.panel_ids = ["unknown"]
    elif defect == "ambiguous_scene":
        scenes.append({"id": "other", "layers": [{"source_panel_id": "p1"}]})
    elif defect == "uncovered_scene":
        scenes.append({"id": "other", "layers": [{"source_panel_id": "p2"}]})
    elif defect == "draft":
        script.status = "DRAFT"
    else:
        script.segments[0].faithfulness_status = "UNSUPPORTED"
    with pytest.raises(ValueError):
        compile_narration_clips(script, narrative, scenes)


def test_actual_speech_timing_keeps_all_lines_and_short_clips():
    from engine.pipeline.narration import synchronize_narration
    scenes = [{"id": "one"}, {"id": "two"}]
    clips = [{"id": "a", "scene_id": "one", "duration_sec": 0.5},
             {"id": "b", "scene_id": "one", "duration_sec": 0.75},
             {"id": "c", "scene_id": "two", "duration_sec": 1.0}]
    synchronize_narration(scenes, clips)
    assert clips[0]["start_time_sec"] == 0
    assert clips[1]["start_time_sec"] == 0.5
    assert scenes[0]["duration_sec"] == pytest.approx(1.6)
    assert clips[2]["start_time_sec"] == pytest.approx(1.6)
    assert scenes[1]["duration_sec"] == pytest.approx(1.35)


@pytest.mark.parametrize("duration", [0, -1, float("nan"), float("inf")])
def test_invalid_speech_duration_cannot_retime_scenes(duration):
    from engine.pipeline.narration import synchronize_narration
    scenes = [{"id": "one", "start_time_sec": 7}]
    clips = [{"id": "a", "scene_id": "one", "duration_sec": duration}]
    with pytest.raises(ValueError):
        synchronize_narration(scenes, clips)
    assert scenes[0]["start_time_sec"] == 7


def test_balloon_geometry_populates_utterances_from_raw_blocks():
    from pathlib import Path
    from engine.story.service import story_service
    from engine.story.models import CharacterEntity, CharacterRole, CharacterStatus
    from types import SimpleNamespace
    p = SimpleNamespace(id="p1", sequence=1, crop_filename=None, ocr_result=SimpleNamespace(raw_blocks=[
        {"id": "b1", "detected_text": "Look out!", "bbox": [100, 100, 200, 50]}
    ]))
    chars = [CharacterEntity(character_id="c1", display_name="Maya", role=CharacterRole.PROTAGONIST, status=CharacterStatus.CONFIRMED)]
    regions = [SimpleNamespace(
        id="b1", project_id="proj", panel_id="p1", sequence_global=1, region_type="DIALOGUE",
        raw_text="Look out!", corrected_text="Look out!", x=100, y=100, width=200, height=50,
        speaker_assignment_method="BALLOON_GEOMETRY", speaker_character_id=None,
    )]
    utts, attrs = story_service._attribute_dialogue_geometry([p], regions, chars, Path("."))
    assert len(utts) == 1
    assert utts[0].source_text == "Look out!"
    assert utts[0].panel_id == "p1"
    assert len(attrs) == 1
