"""Real SQLite and image persistence for Setup selector edits."""
import json
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from fastapi import FastAPI
from fastapi.testclient import TestClient

from engine.database.models import Base, PageRecord, PanelRecord, ProjectRecord
from engine.database.session import get_db
from engine.projects.panel_selections import Selection, save_selections
from engine.api.routers.panels import router


@pytest.fixture
def fixture(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'qa.sqlite'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    (tmp_path / "source").mkdir()
    (tmp_path / "panels").mkdir()
    Image.new("RGB", (120, 100), "red").save(tmp_path / "source" / "page.png")
    Image.new("RGB", (100, 80), "red").save(tmp_path / "panels" / "original.png")
    with Session(engine) as db:
        db.add(ProjectRecord(id="project", title="Selectors", source_type="LOCAL_FOLDER", workspace_path=str(tmp_path), rights_status="PUBLIC_DOMAIN"))
        db.add(PageRecord(id="page", project_id="project", sequence=1, filename="page.png", sha256="qa", width=120, height=100))
        db.add(PanelRecord(id="panel", project_id="project", page_id="page", sequence=1, page_sequence=1,
                           x=10, y=10, width=100, height=80, crop_filename="original.png", status="DETECTED"))
        db.add(PanelRecord(id="later", project_id="project", page_id="page", sequence=2, page_sequence=2,
                           x=0, y=0, width=10, height=10, crop_filename="later.png", status="DETECTED"))
        db.commit()
        yield db, tmp_path
    engine.dispose()


def test_multiple_splits_persist_exact_crops_order_and_existing_identity(fixture):
    db, workspace = fixture
    selections = [Selection(x=10, y=10, width=33, height=80), Selection(x=43, y=10, width=34, height=80), Selection(x=77, y=10, width=33, height=80)]
    result = save_selections(db, "project", "panel", selections)
    db.expire_all()
    assert len(result) == 4
    assert result[0].id == "panel"
    assert result[-1].id == "later"
    assert [p.sequence for p in result] == [1, 2, 3, 4]
    assert [p.page_sequence for p in result] == [1, 2, 3, 4]
    for p, s in zip(result, selections):
        assert (p.x, p.y, p.width, p.height) == (s.x, s.y, s.width, s.height)
        with Image.open(workspace / "panels" / p.crop_filename) as image:
            assert image.size == (s.width, s.height)
            assert image.getpixel((0, 0)) == (255, 0, 0, 255)
        assert p.manually_modified and p.status == "MANUAL"
    assert (workspace / "panels" / "original.png").is_file(), "previous crop remains recoverable"


def test_polygon_alpha_and_contour_survive_reopen(fixture):
    db, workspace = fixture
    points = [(10, 10), (60, 10), (60, 60)]
    result = save_selections(db, "project", "panel", [Selection(x=10, y=10, width=50, height=50, points=points)])
    db.expire_all()
    persisted = db.get(PanelRecord, "panel")
    assert json.loads(persisted.polygon_json) == [list(p) for p in points]
    with Image.open(workspace / "panels" / persisted.crop_filename) as image:
        assert image.mode == "RGBA"
        assert image.getpixel((40, 5))[3] == 255
        assert image.getpixel((0, 49))[3] == 0
    from engine.render.compiler import TimelineCompiler
    path, already_cropped = TimelineCompiler()._resolve_image_path("", "panel", "page", workspace)
    assert Path(path) == workspace / "panels" / persisted.crop_filename
    assert already_cropped is True, "video export resolves the saved alpha-masked crop"


@pytest.mark.parametrize("selection", [
    dict(x=0, y=0, width=30, height=30),
    dict(x=10, y=10, width=101, height=80),
    dict(x=10, y=10, width=50, height=50, points=[(10, 10), (60, 60), (10, 60), (60, 10)]),
    dict(x=10, y=10, width=50, height=50, points=[(10, 10), (60, 10), (70, 70)]),
])
def test_invalid_shape_never_changes_database_or_creates_crops(fixture, selection):
    db, workspace = fixture
    with pytest.raises(ValueError):
        save_selections(db, "project", "panel", [Selection(**selection)])
    assert db.get(PanelRecord, "panel").crop_filename == "original.png"
    assert len(list((workspace / "panels").glob("selector_*"))) == 0


def test_image_failure_rolls_back_all_panels_and_generated_files(fixture, monkeypatch):
    db, workspace = fixture
    original_save = Image.Image.save
    calls = 0
    def fail_second(image, target, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("disk fixture failure")
        return original_save(image, target, *args, **kwargs)
    monkeypatch.setattr(Image.Image, "save", fail_second)
    with pytest.raises(OSError):
        save_selections(db, "project", "panel", [Selection(x=10, y=10, width=50, height=80), Selection(x=60, y=10, width=50, height=80)])
    assert db.get(PanelRecord, "panel").width == 100
    assert db.get(PanelRecord, "panel").crop_filename == "original.png"
    assert db.query(PanelRecord).count() == 2
    assert len(list((workspace / "panels").glob("selector_*"))) == 0


def test_commit_failure_restores_crop_and_renderer_inventory(fixture, monkeypatch):
    db, workspace = fixture
    manifest = workspace / "panels" / "panels.json"
    manifest.write_text('{"preserve": "previous inventory"}', encoding="utf-8")
    previous = manifest.read_bytes()
    def fail():
        raise RuntimeError("commit fixture failure")
    monkeypatch.setattr(db, "commit", fail)
    with pytest.raises(RuntimeError):
        save_selections(db, "project", "panel", [Selection(x=10, y=10, width=50, height=80)])
    assert db.get(PanelRecord, "panel").width == 100
    assert manifest.read_bytes() == previous
    assert len(list((workspace / "panels").glob("selector_*"))) == 0


def test_route_serializes_real_saved_panels_and_validates_requests(fixture):
    db, _ = fixture
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        url = "/api/projects/project/panels/panel/selections"
        assert client.put(url, json={"selections": []}).status_code == 422
        assert client.put(url, json={"selections": [{"x": 0, "y": 0, "width": 30, "height": 30}]}).status_code == 400
        response = client.put(url, json={"selections": [{"x": 10, "y": 10, "width": 50, "height": 80}]})
        assert response.status_code == 200, response.text
        assert response.json()[0]["width"] == 50
        assert response.json()[0]["id"] == "panel"


def test_page_editor_can_expand_panel_within_source_image_but_not_outside(fixture):
    db, _ = fixture
    result = save_selections(db, "project", "panel", [Selection(x=0, y=0, width=120, height=100)], page_bounds=True)
    assert (result[0].x, result[0].y, result[0].width, result[0].height) == (0, 0, 120, 100)
    with pytest.raises(ValueError):
        save_selections(db, "project", "panel", [Selection(x=0, y=0, width=121, height=100)], page_bounds=True)
    assert db.get(PanelRecord, "panel").width == 120


def test_empty_page_can_create_multiple_selectors_through_real_route(fixture):
    db, workspace = fixture
    app = FastAPI(); app.include_router(router); app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        url = "/api/projects/project/pages/page/selections"
        response = client.post(url, json={"selections": [{"x": 0, "y": 0, "width": 60, "height": 100}, {"x": 60, "y": 0, "width": 60, "height": 100}]})
        assert response.status_code == 201, response.text
        assert len(response.json()) == 4, "creation preserves previously detected panels"
        assert db.query(PanelRecord).count() == 4
        assert len(list((workspace / "panels").glob("selector_*.png"))) == 2
        assert client.post("/api/projects/other/pages/page/selections", json={"selections": [{"x": 0, "y": 0, "width": 60, "height": 100}]}).status_code == 404
