"""The cast endpoints: what the project sounds like, and what the owner can change."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from engine.api.routers import narration
from engine.database.models import Base, ProjectRecord
from engine.database.session import get_db
from engine.narration.bible.store import BibleStore
from engine.narration.casting import save_cast


CATALOG = [
    {"id": "narrator", "name": "The Narrator", "voice": "am_michael", "gender": "male"},
    {"id": "aria", "name": "Aria", "voice": "af_heart", "gender": "female"},
]


@pytest.fixture
def cast_env(tmp_path, monkeypatch):
    monkeypatch.setattr("engine.narration.casting.settings.app_data_dir", tmp_path)
    bibles = BibleStore(tmp_path / "series")
    bible = bibles.load("cast-project")  # the key the title derives
    bible.characters = []
    bibles.save(bible, "proj-cast", ["seed"])

    engine = create_engine(f"sqlite:///{tmp_path / 'cast.sqlite'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(ProjectRecord(id="proj-cast", title="Cast Project", source_type="LOCAL_FOLDER",
                             workspace_path=str(tmp_path / "ws"), rights_status="PUBLIC_DOMAIN"))
        db.commit()
    app = FastAPI()
    app.include_router(narration.router)

    def get_session():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = get_session
    monkeypatch.setattr(narration, "_bibles", lambda: bibles)
    monkeypatch.setattr(narration, "load_voice_catalog", lambda: _catalog())
    return TestClient(app), tmp_path


def _catalog():
    from engine.narration.runtime.roles import VoiceProfile
    return [VoiceProfile.model_validate(p) for p in CATALOG]


def test_the_cast_endpoint_lists_the_voices_and_the_narrator(cast_env):
    client, _ = cast_env
    body = client.get("/api/narration/projects/proj-cast/cast").json()
    assert body["series_key"] == "cast-project"  # derived from the project title
    assert [p["id"] for p in body["catalog"]] == ["narrator", "aria"]
    assert body["assigned"] == {}
    assert body["uncast"] == []


def test_casting_a_character_is_kept(cast_env):
    client, tmp_path = cast_env
    res = client.post("/api/narration/projects/proj-cast/cast",
                      json={"character_id": "c1", "profile_id": "aria"})
    assert res.status_code == 200 and res.json()["assigned"] == {"c1": "aria"}
    body = client.get("/api/narration/projects/proj-cast/cast").json()
    assert body["assigned"] == {"c1": "aria"}


def test_casting_to_a_voice_that_is_not_approved_is_refused(cast_env):
    client, _ = cast_env
    res = client.post("/api/narration/projects/proj-cast/cast",
                      json={"character_id": "c1", "profile_id": "not-a-voice"})
    assert res.status_code == 400


def test_a_casting_can_be_cleared(cast_env):
    client, _ = cast_env
    client.post("/api/narration/projects/proj-cast/cast", json={"character_id": "c1", "profile_id": "aria"})
    res = client.post("/api/narration/projects/proj-cast/cast", json={"character_id": "c1", "profile_id": ""})
    assert res.status_code == 200 and res.json()["assigned"] == {}


def test_the_cast_of_an_unknown_project_is_404(cast_env):
    client, _ = cast_env
    assert client.get("/api/narration/projects/nope/cast").status_code == 404
