"""
Phase 5: Golden Verification on Real Target Project Fixture (Chapter 925).

Tests end-to-end diagnosis, dry-run repair planning, transactional application,
immutable snapshot creation, and 1-click rollback fidelity using the real
Magic Emperor Chapter 925 snapshot fixture.
"""
from pathlib import Path
import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from engine.database.models import Base, ProjectRecord
from engine.story.recovery import recovery_service


@pytest.fixture
def test_db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test_ch925_recovery.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _load_ch925_fixture():
    fixture_path = Path("tests/fixtures/project_925_snapshot.json")
    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    project_dict = data["tables"]["projects"][0]
    raw_settings = project_dict["settings"]
    settings_obj = json.loads(raw_settings) if isinstance(raw_settings, str) else raw_settings
    return project_dict["id"], project_dict["title"], settings_obj


def test_chapter_925_diagnosis():
    proj_id, _, settings = _load_ch925_fixture()
    story_state = settings["story_editor_state"]

    diag = recovery_service.diagnose_timeline(story_state, project_id=proj_id)

    assert diag["is_corrupted"] is True
    assert diag["total_timeline_duration_sec"] == pytest.approx(4493.414, abs=0.1)
    assert diag["voids_count"] == 46
    assert diag["total_void_duration_sec"] == pytest.approx(3887.714, abs=0.1)
    assert diag["unlinked_clips_count"] == 50
    assert diag["leaked_clips_count"] == 2


def test_chapter_925_repair_plan_dry_run():
    proj_id, _, settings = _load_ch925_fixture()
    story_state = settings["story_editor_state"]

    plan = recovery_service.create_repair_plan(story_state)

    # 1. Timeline compaction
    assert plan["duration_before_sec"] == pytest.approx(4493.414, abs=0.1)
    assert plan["duration_after_sec"] == pytest.approx(605.7, abs=0.1)
    assert plan["voids_collapsed_count"] == 46
    assert plan["void_seconds_removed"] == pytest.approx(3887.714, abs=0.1)

    # 2. Narration re-linking & leakage sanitization
    assert plan["relinked_clips_count"] == 50
    assert plan["sanitized_clips_count"] == 2

    # 3. Verify repaired state invariants
    repaired = plan["repaired_state"]
    scenes = repaired["scenes"]
    clips = repaired["narration_clips"]

    # Invariant: scenes must now be contiguous
    for i in range(len(scenes) - 1):
        sc_end = scenes[i]["start_time_sec"] + scenes[i]["duration_sec"]
        next_start = scenes[i + 1]["start_time_sec"]
        assert (next_start - sc_end) <= 0.034, f"Accidental void remains between scene {i} and {i+1}"

    # Invariant: all 50 previously unlinked clips are now linked to scenes
    for clip in clips:
        assert clip["linked_to_scene"] is True
        assert clip["scene_id"] is not None

    # Invariant: sanitized clips no longer contain prompt leakage
    leaked_ids = {s["id"] for s in plan["sanitized_clips"]}
    for clip in clips:
        if clip["id"] in leaked_ids:
            assert "Protagonist exclaims" not in clip["text"]
            assert "refusing to yield an inch" not in clip["text"]


def test_chapter_925_apply_and_rollback(test_db_session, tmp_path):
    proj_id, title, settings = _load_ch925_fixture()
    story_state = settings["story_editor_state"]
    workspace = tmp_path / "ch925_workspace"
    workspace.mkdir(parents=True)

    # Setup project in DB
    project = ProjectRecord(
        id=proj_id,
        title=title,
        workspace_path=str(workspace),
        source_type="MANGA_MANHUA",
        settings=settings,
    )
    test_db_session.add(project)
    test_db_session.commit()

    # 1. Plan repair
    plan = recovery_service.create_repair_plan(story_state)

    # 2. Apply repair
    apply_res = recovery_service.apply_repair_plan(
        db=test_db_session,
        project_id=proj_id,
        workspace_path=workspace,
        repair_plan=plan,
    )

    assert apply_res["success"] is True
    snapshot_filename = apply_res["snapshot_filename"]
    assert (workspace / "snapshots" / snapshot_filename).exists()

    # Verify project in DB has compact duration (~605.7s)
    test_db_session.refresh(project)
    applied_scenes = project.settings["story_editor_state"]["scenes"]
    last_scene = sorted(applied_scenes, key=lambda s: s["start_time_sec"])[-1]
    applied_dur = last_scene["start_time_sec"] + last_scene["duration_sec"]
    assert applied_dur == pytest.approx(605.7, abs=0.1)

    # 3. Rollback recovery
    rollback_res = recovery_service.rollback_recovery(
        db=test_db_session,
        project_id=proj_id,
        workspace_path=workspace,
        snapshot_filename=snapshot_filename,
    )

    assert rollback_res["success"] is True

    # Verify project in DB is restored to exact original corrupt state
    test_db_session.refresh(project)
    restored_scenes = project.settings["story_editor_state"]["scenes"]
    last_restored = sorted(restored_scenes, key=lambda s: s["start_time_sec"])[-1]
    restored_dur = last_restored["start_time_sec"] + last_restored["duration_sec"]
    assert restored_dur == pytest.approx(4493.414, abs=0.1)
    assert len(restored_scenes) == 51
