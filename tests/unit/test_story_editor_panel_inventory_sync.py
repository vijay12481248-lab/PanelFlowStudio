"""Inventory synchronization must not infer membership from custom timelines."""
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from engine.database.models import Base, PageRecord, PanelRecord, ProjectRecord
from engine.projects.service import align_panel_scenes, reconcile_story_editor_state_with_panels


@pytest.fixture
def inventory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        project_id, page_id = uuid4().hex, uuid4().hex
        db.add(ProjectRecord(id=project_id, title="Inventory", source_type="LOCAL_FOLDER",
                             workspace_path="unused", rights_status="PUBLIC_DOMAIN"))
        db.add(PageRecord(id=page_id, project_id=project_id, sequence=1,
                          filename="unused.jpg", sha256="unused", width=100, height=100))
        panels = [PanelRecord(id=uuid4().hex, project_id=project_id, page_id=page_id,
                              sequence=i, page_sequence=i, x=i, y=i, width=50, height=50,
                              crop_filename=f"{i}.jpg", status="CONFIRMED") for i in range(1, 4)]
        db.add_all(panels)
        db.commit()
        yield db, project_id, page_id, panels
    engine.dispose()


def panel_scene(panel, index=1):
    return {"id": f"scene-{index}", "duration_sec": 7.5, "start_time_sec": 2.0,
            "sequence": index, "custom": {"keep": True}, "layers": [{
                "id": f"layer-{index}", "source_panel_id": panel.id,
                "transform": {"x": 9, "scale": 1.7}, "motion_preset": "pan_right",
                "motion_keyframes": [{"time": 1.0, "x": 22}], "duration_sec": 6.5}]}


def assert_clean(state):
    assert state["panels_stale"] is False
    assert state["panel_sync_required"] is False
    assert state["panel_review_sync"]["panels_stale"] is False


@pytest.mark.parametrize("kind", ["subset", "page-only", "empty", "editor-order"])
def test_intentional_editor_composition_does_not_imply_inventory_change(inventory, kind):
    db, project_id, page_id, panels = inventory
    scenes = {
        "subset": [panel_scene(panels[0]), {"id": "page", "layers": [{"id": "page-layer", "source_page_id": page_id}]}, {"id": "empty", "layers": []}],
        "page-only": [{"id": "page", "layers": [{"id": "page-layer", "source_page_id": page_id}]}],
        "empty": [],
        "editor-order": [panel_scene(p, i) for i, p in enumerate(reversed(panels))],
    }[kind]
    state = {"scenes": scenes, "narration_clips": [{"id": "audio", "start_time_sec": 3}],
             "music_tracks": [{"id": "music", "volume": 0.3}]}
    before = deepcopy(state)
    result = reconcile_story_editor_state_with_panels(db, project_id, state)
    assert_clean(result)
    assert result["panel_review_sync"]["panel_ids"] == [p.id for p in panels]
    assert [s["id"] for s in result["scenes"]] == [s["id"] for s in scenes]
    for key in ("narration_clips", "music_tracks"):
        assert result[key] == state[key]
    for old, new in zip(scenes, result["scenes"]):
        assert {k: v for k, v in new.items() if k != "layers"} == {k: v for k, v in old.items() if k != "layers"}
        for old_layer, new_layer in zip(old["layers"], new["layers"]):
            for key in ("transform", "motion_preset", "motion_keyframes", "duration_sec"):
                assert new_layer.get(key) == old_layer.get(key)
    assert state == before
    assert_clean(reconcile_story_editor_state_with_panels(db, project_id, result))


def assert_stale(state):
    assert state["panels_stale"] is True
    assert state["panel_sync_required"] is True
    assert state["panel_review_sync"]["panels_stale"] is True


@pytest.mark.parametrize("change", ["add", "delete-unused", "reorder"])
@pytest.mark.parametrize("composition", ["subset", "empty"])
def test_saved_inventory_detects_real_changes_without_rebuilding_composition(inventory, change, composition):
    db, project_id, page_id, panels = inventory
    state = {"scenes": [panel_scene(panels[0])] if composition == "subset" else [],
             "panel_review_sync": {"panel_ids": [p.id for p in panels], "panels_stale": False}}
    before = deepcopy(state)
    if change == "add":
        db.add(PanelRecord(id=uuid4().hex, project_id=project_id, page_id=page_id,
                           sequence=4, page_sequence=4, x=0, y=0, width=20, height=20,
                           crop_filename="new.jpg", status="CONFIRMED"))
    elif change == "delete-unused":
        db.delete(panels[2])
    else:
        panels[1].sequence, panels[2].sequence = 3, 2
    db.commit()
    result = reconcile_story_editor_state_with_panels(db, project_id, state)
    assert_stale(result)
    assert state == before
    assert [s["id"] for s in result["scenes"]] == [s["id"] for s in state["scenes"]]
    expected_ids = [p.id for p in db.query(PanelRecord).filter_by(project_id=project_id).order_by(PanelRecord.sequence)]
    assert result["panel_review_sync"]["panel_ids"] == expected_ids
    # Observing the new baseline must not silently acknowledge a pending change.
    again = reconcile_story_editor_state_with_panels(db, project_id, result)
    assert_stale(again)
    again["panel_review_sync"]["synced_at"] = result["panel_review_sync"]["synced_at"]
    assert again == result


def test_deleted_source_preserves_authored_layers_and_reports_missing_on_every_read(inventory):
    db, project_id, _, panels = inventory
    state = reconcile_story_editor_state_with_panels(db, project_id, {"scenes": [panel_scene(panels[0])]})
    scenes = deepcopy(state["scenes"])
    missing_id = panels[0].id
    db.delete(panels[0])
    db.commit()
    for _ in range(2):
        state = reconcile_story_editor_state_with_panels(db, project_id, state)
        assert_stale(state)
        assert state["scenes"] == scenes
        assert state["panel_review_sync"]["removed_layers"] == [{
            "scene_id": scenes[0]["id"], "layer_id": scenes[0]["layers"][0]["id"], "panel_id": missing_id}]
        assert state["panel_review_sync"]["removed_layers_count"] == 1


def test_missing_source_without_baseline_is_not_treated_as_an_intentional_subset(inventory):
    db, project_id, _, panels = inventory
    state = {"scenes": [panel_scene(panels[0])]}
    db.delete(panels[0])
    db.commit()
    result = reconcile_story_editor_state_with_panels(db, project_id, state)
    assert_stale(result)
    assert result["scenes"] == state["scenes"]


def test_geometry_refresh_preserves_motion_and_pending_confirmation(inventory):
    db, project_id, _, panels = inventory
    state = reconcile_story_editor_state_with_panels(
        db, project_id, {"scenes": [panel_scene(p, i) for i, p in enumerate(panels)],
                         "panels_stale": False, "panel_sync_required": False})
    assert state is not None
    assert_clean(state)
    original_layer = deepcopy(state["scenes"][0]["layers"][0])
    panels[0].x, panels[0].width = 12, 32
    db.commit()
    # Panel confirmation marks pending changes in nested metadata, not top-level flags.
    state["panel_review_sync"].update({"last_panel_confirm": "2026-10-22T00:00:00+00:00", "panels_stale": True})
    state["panels_stale"] = state["panel_sync_required"] = False
    for _ in range(2):
        state = reconcile_story_editor_state_with_panels(db, project_id, state)
        assert_stale(state)
        assert state["panel_review_sync"]["last_panel_confirm"] == "2026-10-22T00:00:00+00:00"
        layer = state["scenes"][0]["layers"][0]
        assert layer["crop"] == {"x": 12, "y": 1, "width": 32, "height": 50}
        for field in ("transform", "motion_preset", "motion_keyframes", "duration_sec"):
            assert layer[field] == original_layer[field]


def test_explicit_alignment_acknowledges_inventory_and_confirmation(inventory):
    db, project_id, _, panels = inventory
    state = {"scenes": [panel_scene(panels[0])],
             "panel_review_sync": {"panel_ids": [p.id for p in reversed(panels)],
                                   "last_panel_confirm": "confirmed", "panels_stale": True},
             "panels_stale": True, "panel_sync_required": True}
    result = align_panel_scenes(db, project_id, state)
    assert_clean(result)
    assert result["panel_review_sync"]["panel_ids"] == [p.id for p in panels]
    assert result["scenes"][0]["custom"] == {"keep": True}
    assert result["scenes"][0]["duration_sec"] == 7.5
    assert_clean(reconcile_story_editor_state_with_panels(db, project_id, result))


@pytest.mark.parametrize("baseline", [None, "not-an-inventory", [None], ["duplicate", "duplicate"]])
def test_invalid_legacy_baseline_is_initialized_from_db_not_scenes(inventory, baseline):
    db, project_id, _, panels = inventory
    state = {"scenes": [panel_scene(panels[0])], "panel_review_sync": {"panel_ids": baseline}}
    result = reconcile_story_editor_state_with_panels(db, project_id, state)
    assert_clean(result)
    assert result["panel_review_sync"]["panel_ids"] == [p.id for p in panels]


def test_saved_empty_inventory_detects_first_added_panel(inventory):
    db, project_id, _, _ = inventory
    state = {"scenes": [], "panel_review_sync": {"panel_ids": []}}
    assert_stale(reconcile_story_editor_state_with_panels(db, project_id, state))


def test_repeated_sources_and_editor_reordering_do_not_change_saved_inventory(inventory):
    db, project_id, _, panels = inventory
    state = {"scenes": [panel_scene(panels[2], 1), panel_scene(panels[0], 2), panel_scene(panels[2], 3)],
             "panel_review_sync": {"panel_ids": [p.id for p in panels]}}
    result = reconcile_story_editor_state_with_panels(db, project_id, state)
    assert_clean(result)
    assert [s["layers"][0]["source_panel_id"] for s in result["scenes"]] == [panels[2].id, panels[0].id, panels[2].id]
