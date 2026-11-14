"""The MiniMax-H3-Image edit endpoint: edit a project picture from a written instruction."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from engine.api.routers import comfyui
from engine.database.models import AssetRecord, Base, ProjectRecord
from engine.database.session import get_db


@pytest.fixture
def edit_client(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'edit.sqlite'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(ProjectRecord(id="p1", title="T", source_type="LOCAL_FOLDER", workspace_path=str(tmp_path)))
        db.add(AssetRecord(id="a1", project_id="p1", asset_type="COMFYUI_GENERATED_IMAGE", filename="a.png",
                           relative_path="generated/comfyui/a.png", content_type="image/png", width=64, height=64,
                           byte_size=1, sha256="x", status="READY", provenance={}))
        db.add(AssetRecord(id="a2", project_id="p1", asset_type="COMFYUI_GENERATED_IMAGE", filename="b.png",
                           relative_path="generated/comfyui/b.png", content_type="image/png", width=64, height=64,
                           byte_size=1, sha256="y", status="READY", provenance={}))
        db.commit()

    class Registry:
        def metadata(self, wid):
            return {"requires_gpu": True, "gpu_vram_mb": 16000}

        def load(self, wid):
            return {}, "x"

        def preflight(self, wid):
            return {"ready": True, "missing_nodes": [], "missing_models": []}

    queued = {}

    def fake_enqueue(**kw):
        queued.update(kw)
        return "job-1"

    monkeypatch.setattr(comfyui, "ComfyWorkflowRegistry", Registry)
    monkeypatch.setattr(comfyui, "enqueue_project_operation", fake_enqueue)
    app = FastAPI()
    app.include_router(comfyui.project_router)
    app.dependency_overrides[get_db] = lambda: Session(engine)
    return TestClient(app), queued


def test_the_edit_endpoint_queues_an_edit_job(edit_client):
    c, queued = edit_client
    res = c.post("/api/projects/p1/comfyui/edit",
                 json={"asset_id": "a1", "prompt": "make the sky stormy"})
    assert res.status_code == 200
    body = res.json()
    assert body["job_id"] == "job-1"
    assert body["workflow_id"] == "minimax_h3_image_edit"
    assert queued["job_input"]["asset_id"] == "a1"
    assert queued["job_input"]["prompt"] == "make the sky stormy"


def test_the_edit_endpoint_passes_the_reference_pictures(edit_client):
    c, queued = edit_client
    res = c.post("/api/projects/p1/comfyui/edit",
                 json={"asset_id": "a1", "prompt": "put the hero in the forest", "reference_asset_ids": ["a2"]})
    assert res.status_code == 200
    assert queued["job_input"]["reference_asset_ids"] == ["a2"]


def test_the_edit_endpoint_refuses_an_asset_from_another_project(edit_client):
    c, _ = edit_client
    res = c.post("/api/projects/p1/comfyui/edit",
                 json={"asset_id": "not-mine", "prompt": "make the sky stormy"})
    assert res.status_code == 400
    assert "not found" in res.json()["detail"].lower()


def test_the_edit_endpoint_needs_a_picture(edit_client):
    c, _ = edit_client
    res = c.post("/api/projects/p1/comfyui/edit", json={"prompt": "make the sky stormy"})
    assert res.status_code == 422  # asset_id is required


def test_the_edit_endpoint_refuses_an_unknown_project(edit_client):
    c, _ = edit_client
    assert c.post("/api/projects/nope/comfyui/edit", json={"asset_id": "a1", "prompt": "make it stormy"}).status_code == 404
