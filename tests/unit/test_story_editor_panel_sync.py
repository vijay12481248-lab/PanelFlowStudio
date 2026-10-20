from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from engine.database.models import Base, PageRecord, PanelRecord, ProjectRecord
from engine.projects.service import reconcile_story_editor_state_with_panels, protected_panel_pages


def test_story_editor_source_layer_uses_current_panel_geometry(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'sync.db'}")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()

    session.add(ProjectRecord(
        id="project-sync",
        title="Sync",
        source_type="LOCAL_FOLDER",
        source_url="source",
        workspace_path=str(tmp_path),
        rights_status="PUBLIC_DOMAIN",
        current_stage="PANELS_DETECTED",
    ))
    session.add(PageRecord(
        id="page-sync",
        project_id="project-sync",
        sequence=1,
        filename="page.jpg",
        width=1000,
        height=1000,
        sha256="sha",
        status="READY",
    ))
    session.add(PanelRecord(
        id="panel-sync",
        project_id="project-sync",
        page_id="page-sync",
        sequence=1,
        page_sequence=1,
        x=120,
        y=240,
        width=640,
        height=360,
        crop_filename="panel_0001.jpg",
    ))
    session.commit()

    state = {
        "project_id": "project-sync",
        "scenes": [{
            "id": "scene-1",
            "layers": [{
                "id": "layer-1",
                "source_panel_id": "panel-sync",
                "crop": {"x": 0, "y": 0, "width": 10, "height": 10},
                "transform": {"x": 12, "y": 8, "scale": 1.2},
            }],
        }],
    }

    synced = reconcile_story_editor_state_with_panels(session, "project-sync", state)
    layer = synced["scenes"][0]["layers"][0]

    assert layer["crop"] == {"x": 120, "y": 240, "width": 640, "height": 360}
    assert layer["source_page_id"] == "page-sync"
    assert layer["transform"] == {"x": 12, "y": 8, "scale": 1.2}
    from engine.projects.service import align_panel_scenes
    state["scenes"][0]["duration_sec"] = 7
    aligned = align_panel_scenes(session, "project-sync", state)
    assert aligned["scenes"][0]["duration_sec"] == 7
    assert aligned["scenes"][0]["layers"][0]["transform"]["scale"] == 1.2
    session.add(PanelRecord(id="new-panel", project_id="project-sync", page_id="page-sync", sequence=0,
                            page_sequence=0, x=0, y=0, width=50, height=50, crop_filename="new.jpg"))
    session.commit()
    aligned = align_panel_scenes(session, "project-sync", state)
    assert [s["layers"][0]["source_panel_id"] for s in aligned["scenes"]] == ["new-panel", "panel-sync"]
    assert aligned["scenes"][1]["start_time_sec"] == 4
    session.delete(session.get(PanelRecord, "new-panel"))
    session.commit()

    # Linked or manually edited pages must survive redetection.
    project = session.get(ProjectRecord, "project-sync")
    project.settings = {"story_editor_state": state}
    session.commit()
    assert protected_panel_pages(session, "project-sync") == {"page-sync"}
    project.settings = {}
    session.commit()
    assert protected_panel_pages(session, "project-sync") == set()
    panel = session.get(PanelRecord, "panel-sync")
    panel.manually_modified = True
    session.commit()
    assert protected_panel_pages(session, "project-sync") == {"page-sync"}

    # Deleted sources preserve the user's authored scene and block export.
    session.delete(panel)
    session.commit()
    synced = reconcile_story_editor_state_with_panels(session, "project-sync", state)
    assert synced["scenes"] == state["scenes"]
    assert synced["panel_review_sync"]["removed_layers_count"] == 1
    from engine.render.compiler import TimelineCompiler
    import pytest
    with pytest.raises(ValueError, match="Source panels"):
        TimelineCompiler().compile(synced, "project-sync", tmp_path)
