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
