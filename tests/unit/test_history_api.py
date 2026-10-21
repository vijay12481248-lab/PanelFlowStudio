from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from engine.database.models import Base, ProjectRecord
from engine.database.session import get_db


@pytest.fixture
def client(tmp_path):
    from engine.api.routers import projects, history
    engine = create_engine(f"sqlite:///{tmp_path / 'api.sqlite'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(ProjectRecord(id="p", title="API history", source_type="LOCAL_FOLDER", workspace_path=str(tmp_path), settings={"story_editor_state": {"project_id": "p", "scenes": [], "aspect_ratio": "16:9"}}))
        db.commit()
    app = FastAPI(); app.include_router(projects.router); app.include_router(history.router)
    def database():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db] = database
    with TestClient(app) as client:
        yield client
    engine.dispose()


def operation(revision):
    return {"operation_id": str(uuid4()), "expected_revision": revision}


def test_existing_editor_save_and_new_undo_redo_share_one_durable_journal(client):
    initial = client.get("/api/projects/p/story-editor").json()
    assert initial["history"]["revision"] == 0
    state = {**initial["state"], "aspect_ratio": "9:16"}
    saved = client.put("/api/projects/p/story-editor", json={"state": state, **operation(0)})
    assert saved.status_code == 200, saved.text
    assert saved.json()["history"]["undoCount"] == 1
    undone = client.post("/api/projects/p/history/undo", json=operation(1))
    assert undone.status_code == 200, undone.text
    assert client.get("/api/projects/p/story-editor").json()["state"]["aspect_ratio"] == "16:9"
    redone = client.post("/api/projects/p/history/redo", json=operation(2))
    assert redone.status_code == 200
    assert client.get("/api/projects/p/story-editor").json()["state"]["aspect_ratio"] == "9:16"


def test_stale_or_unversioned_editor_save_is_rejected_after_history_exists(client):
    state = {"project_id": "p", "scenes": [], "aspect_ratio": "9:16"}
    assert client.put("/api/projects/p/story-editor", json={"state": state, **operation(0)}).status_code == 200
    for extra in [operation(0), {}]:
        response = client.put("/api/projects/p/story-editor", json={"state": {**state, "aspect_ratio": "1:1"}, **extra})
        assert response.status_code == 409, response.text
    assert client.get("/api/projects/p/history").json()["state"]["aspect_ratio"] == "9:16"


def test_history_requests_validate_scope_versions_and_strict_revisions(client):
    assert client.get("/api/projects/missing/history").status_code == 404
    assert client.post("/api/projects/p/history/undo", json={**operation(0), "expected_revision": True}).status_code == 422
    assert client.post("/api/projects/p/history/commands", json={**operation(0), "type": "unsupported", "version": 99, "label": "Unknown", "input": {}}).status_code == 422
    assert client.get("/api/projects/p/history").json()["history"]["revision"] == 0


def test_history_routes_are_protected_by_local_api_authentication():
    from engine.api.app import create_app
    app = create_app(engine_token="history-test-only", allowed_origins={"http://localhost:5173"}, allow_insecure=False)
    # No lifespan context: never initialize or mutate a user's database.
    client = TestClient(app, base_url="http://127.0.0.1:8765")
    assert client.get("/api/projects/p/history").status_code == 401
    assert client.post("/api/projects/p/history/undo", json=operation(0)).status_code == 401
