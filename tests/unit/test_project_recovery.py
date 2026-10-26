"""
Unit tests for ProjectRecoveryService (Phase 4).
Tests diagnosis of voids/unlinked clips, dry-run repair plan generation,
immutable snapshot creation, and 1-click rollback fidelity.
"""
from pathlib import Path
import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from engine.database.models import Base, ProjectRecord
from engine.story.recovery import ProjectRecoveryService, recovery_service


@pytest.fixture
def test_db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test_recovery.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _make_corrupted_state():
    return {
        "scenes": [
            {
                "id": "scene_0",
                "start_time_sec": 0.0,
                "duration_sec": 10.0,
                "layers": [{"source_panel_id": "panel_01"}],
            },
            {
                "id": "scene_1",
                "start_time_sec": 210.0,  # 200s accidental black void!
                "duration_sec": 15.0,
                "layers": [{"source_panel_id": "panel_02"}],
            },
            {
                "id": "scene_silent",
                "start_time_sec": 225.0,
                "duration_sec": 5.0,
                "layers": [{"source_panel_id": "panel_silent_48"}],
            },
        ],
        "narration_clips": [
            {
                "id": "clip_0",
                "scene_id": "scene_0",
                "start_time_sec": 0.0,
                "duration_sec": 9.5,
                "linked_to_scene": True,
                "text": "The kingdom stood firm.",
                "source_panel_ids": ["panel_01"],
            },
            {
                "id": "clip_1",
                "scene_id": None,  # Unlinked!
                "start_time_sec": 210.0,
                "duration_sec": 14.0,
                "linked_to_scene": False,
                "text": "A dark cloaked figure approached.",
                "source_panel_ids": ["panel_02"],
            },
            {
                "id": "clip_orphan",
                "scene_id": "deleted_scene_999",  # Orphan!
                "start_time_sec": 220.0,
                "duration_sec": 3.0,
                "linked_to_scene": False,
                "text": "Floating line.",
                "source_panel_ids": [],
            },
            {
                "id": "clip_dummy",
                "scene_id": "scene_silent",
                "start_time_sec": 225.0,
                "duration_sec": 5.0,
                "linked_to_scene": True,
                "text": "The silence settled once more...",  # Boilerplate dummy!
                "source_panel_ids": ["panel_silent_48"],
            },
        ],
    }


def test_diagnose_timeline_detects_corruptions():
    state = _make_corrupted_state()
    diag = recovery_service.diagnose_timeline(state, project_id="proj_test_1")

    assert diag["is_corrupted"] is True
    assert diag["voids_count"] == 1
    assert diag["total_void_duration_sec"] == pytest.approx(200.0, abs=0.1)
    assert diag["unlinked_clips_count"] == 2  # clip_1 and clip_orphan
    assert diag["orphan_clips_count"] == 1    # clip_orphan
    assert diag["dummy_clips_count"] == 1     # clip_dummy
    assert diag["total_timeline_duration_sec"] == 230.0


def test_create_repair_plan_dry_run_preserves_input():
    state = _make_corrupted_state()
    plan = recovery_service.create_repair_plan(state)

    # 1. Input state must NOT be mutated
    assert state["scenes"][1]["start_time_sec"] == 210.0
    assert len(state["narration_clips"]) == 4

    # 2. Repair plan metrics
    assert plan["duration_before_sec"] == 230.0
    # After collapsing 200s void: scenes are [0-10s], [10-25s], [25-30s] -> 30s
    assert plan["duration_after_sec"] == 30.0
    assert plan["void_seconds_removed"] == pytest.approx(200.0, abs=0.1)
    assert plan["removed_dummy_clips_count"] == 1
    assert plan["relinked_clips_count"] == 1  # clip_1 re-linked to scene_1

    # 3. Repaired state inspection
    repaired = plan["repaired_state"]
    scenes = repaired["scenes"]
    assert scenes[0]["start_time_sec"] == 0.0
    assert scenes[1]["start_time_sec"] == 10.0  # Void collapsed!
    assert scenes[2]["start_time_sec"] == 25.0
    assert scenes[2].get("is_silent") is True   # Converted to silent pacing scene!

    clips = repaired["narration_clips"]
    assert len(clips) == 3  # Dummy clip removed
    clip_1 = next(c for c in clips if c["id"] == "clip_1")
    assert clip_1["scene_id"] == "scene_1"
    assert clip_1["linked_to_scene"] is True
    assert clip_1["start_time_sec"] == 10.0     # Pulled left with scene_1!


def test_apply_and_rollback_recovery(test_db_session, tmp_path):
    # Setup dummy project in DB and workspace
    proj_id = "test_recov_proj"
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)

    initial_state = _make_corrupted_state()
    project = ProjectRecord(
        id=proj_id,
        title="Recovery Test Project",
        workspace_path=str(workspace),
        source_type="MANGA_MANHUA",
        settings={"story_editor_state": initial_state},
    )
    test_db_session.add(project)
    test_db_session.commit()

    # Create repair plan
    plan = recovery_service.create_repair_plan(initial_state)

    # Apply repair plan
    apply_res = recovery_service.apply_repair_plan(
        db=test_db_session,
        project_id=proj_id,
        workspace_path=workspace,
        repair_plan=plan,
    )

    assert apply_res["success"] is True
    assert Path(apply_res["snapshot_path"]).exists()
    snapshot_filename = apply_res["snapshot_filename"]

    # Verify project in DB has new repaired timeline duration (30s)
    test_db_session.refresh(project)
    applied_scenes = project.settings["story_editor_state"]["scenes"]
    assert applied_scenes[1]["start_time_sec"] == 10.0

    # Execute 1-click rollback
    rollback_res = recovery_service.rollback_recovery(
        db=test_db_session,
        project_id=proj_id,
        workspace_path=workspace,
        snapshot_filename=snapshot_filename,
    )

    assert rollback_res["success"] is True

    # Verify project in DB is restored to exact byte-identical pre-repair state (210s)
    test_db_session.refresh(project)
    restored_scenes = project.settings["story_editor_state"]["scenes"]
    assert restored_scenes[1]["start_time_sec"] == 210.0
    assert len(project.settings["story_editor_state"]["narration_clips"]) == 4
