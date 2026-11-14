"""Image Studio colour grade: a graded picture is kept as a project asset with the grade as provenance."""
import base64
import io

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from engine.api.routers import comfyui
from engine.database.models import AssetRecord, Base, ProjectRecord
from engine.database.session import get_db


def _data_url(width=64, height=48, color=(120, 40, 200)) -> str:
    out = io.BytesIO()
    Image.new("RGB", (width, height), color).save(out, format="PNG")
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode()


@pytest.fixture
def client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'g.sqlite'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    (tmp_path / "generated" / "comfyui").mkdir(parents=True)
    with Session(engine) as db:
        db.add(ProjectRecord(id="p1", title="T", source_type="LOCAL_FOLDER", workspace_path=str(tmp_path)))
        db.add(AssetRecord(id="src", project_id="p1", asset_type="COMFYUI_GENERATED_IMAGE", filename="src.png",
                           relative_path="generated/comfyui/src.png", content_type="image/png", width=64, height=48,
                           byte_size=1, sha256="s", status="READY", provenance={}))
        db.commit()
    app = FastAPI()
    app.include_router(comfyui.project_router)
    app.dependency_overrides[get_db] = lambda: Session(engine)
    return TestClient(app), engine, tmp_path


def test_a_graded_picture_becomes_an_asset_that_remembers_its_grade(client):
    c, engine, tmp_path = client
    grade = {"v": 1, "on": True, "nodes": [{"id": "n1", "label": "Warm film", "temp": 18}]}
    res = c.post("/api/projects/p1/assets/graded", json={"image_data": _data_url(), "source_asset_id": "src", "grade": grade})
    assert res.status_code == 200
    body = res.json()
    assert body["asset_type"] == "GRADED_IMAGE" and (body["width"], body["height"]) == (64, 48)
    assert body["provenance"]["role"] == "color_grade" and body["provenance"]["source_asset_id"] == "src"
    assert body["provenance"]["grade"] == grade
    assert (tmp_path / body["relative_path"]).is_file()
    with Session(engine) as db:
        assert db.query(AssetRecord).filter(AssetRecord.id == body["id"]).one().sha256 == body["sha256"]
    listed = c.get("/api/projects/p1/assets").json()["assets"]
    assert body["id"] in {a["id"] for a in listed}  # the list endpoint shares the same row shape


@pytest.mark.parametrize("body,code", [
    ({"image_data": "not base64 at all!!!!!!", "source_asset_id": "src"}, 400),
    ({"image_data": _data_url(), "source_asset_id": "someone-elses"}, 400),
    ({"image_data": _data_url()}, 422),
    ({"image_data": _data_url(), "source_asset_id": "src", "grade": {"x": "y" * 500_000}}, 422),
])
def test_bad_graded_requests_are_refused(client, body, code):
    c, _, _ = client
    assert c.post("/api/projects/p1/assets/graded", json=body).status_code == code


def test_an_unknown_project_is_a_404(client):
    c, _, _ = client
    assert c.post("/api/projects/nope/assets/graded", json={"image_data": _data_url(), "source_asset_id": "src"}).status_code == 404
