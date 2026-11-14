"""Task 9 of the scene-director plan: HTTP surface (fake provider, fake job queue, temp files)."""
import pytest
from fastapi.testclient import TestClient

from engine.database.models import Base
from engine.database.session import engine as db_engine
from engine.llm.registry import llm_registry
from scene_fixtures import fight_plan

FIGHT_ANSWER = {
    "actors": [{"id": "hero", "description": "short black hair, scarred cheek", "gender": "male", "side": "left", "action_state": "striking"},
               {"id": "villain", "description": "tall, black armour", "gender": "male", "side": "right", "action_state": "blocking"}],
    "contacts": [{"source": "hero", "target": "villain", "body_part": "sword", "direction": "down-right"}],
    "camera": {"angle": "eye_level", "distance": "wide"}, "light": {"direction": "front"}, "mood": "tense", "setting": "a stone courtyard",
}


class FakeProvider:
    def __init__(self, healthy=True):
        self.healthy = healthy

    async def health_check(self):
        return self.healthy

    async def generate_structured(self, text, model, **kw):
        return FIGHT_ANSWER


@pytest.fixture
def client(tmp_path, monkeypatch):
    from engine.api.app import create_app
    from engine.api.routers import scene as scene_router

    Base.metadata.create_all(db_engine)
    monkeypatch.setattr(scene_router, "ratings_path", lambda: tmp_path / "ratings.json")
    monkeypatch.setattr(llm_registry, "get_ollama_provider", lambda: FakeProvider())
    return TestClient(create_app(allow_insecure=True), base_url="http://localhost"), scene_router


def test_propose_returns_summary_and_at_most_three_questions(client):
    c, _ = client
    r = c.post("/api/original/scene/propose", json={"brief": "the hero fights the villain"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["plan"]["scene_type"] == "fight" and "hero" in body["summary"] and 0 < len(body["questions"]) <= 3


def test_empty_brief_is_422(client):
    c, _ = client
    assert c.post("/api/original/scene/propose", json={"brief": "   "}).status_code == 422
    assert c.post("/api/original/scene/propose", json={"brief": ""}).status_code == 422


def test_propose_is_503_when_ollama_is_down(client, monkeypatch):
    c, _ = client
    monkeypatch.setattr(llm_registry, "get_ollama_provider", lambda: FakeProvider(healthy=False))
    assert c.post("/api/original/scene/propose", json={"brief": "the hero fights the villain"}).status_code == 503


def test_correct_changes_the_plan_and_a_contradiction_is_422_with_problems(client):
    c, _ = client
    plan = fight_plan().model_dump()
    ok = c.post("/api/original/scene/correct", json={"plan": plan, "corrections": {"camera.angle": "high"}})
    assert ok.status_code == 200 and ok.json()["plan"]["camera"]["angle"] == "high" and "high angle" in ok.json()["summary"]
    bad = c.post("/api/original/scene/correct", json={"plan": plan, "corrections": {"actors.villain.side": "left"}})
    assert bad.status_code == 422 and "opposite sides" in bad.json()["detail"]


def test_generate_enqueues_a_gpu_job_and_returns_its_id(client, monkeypatch):
    c, router = client
    seen = {}

    def fake_enqueue(project_id, job_type, operation, **kw):
        seen.update(project_id=project_id, job_type=job_type, **kw)
        return "job-123"

    monkeypatch.setattr(router, "enqueue_project_operation", fake_enqueue)
    r = c.post("/api/original/scene/generate", json={"project_id": "p1", "plan": fight_plan().model_dump(), "seed": 5})
    assert r.status_code == 200 and r.json()["job_id"] == "job-123"
    assert seen["project_id"] == "p1" and seen["job_type"] == "SCENE_GENERATION" and seen["requires_gpu"] is True


def test_generate_rejects_an_invalid_plan(client, monkeypatch):
    c, router = client
    monkeypatch.setattr(router, "enqueue_project_operation", lambda *a, **k: pytest.fail("must not enqueue an invalid plan"))
    plan = fight_plan().model_dump()
    plan["actors"][1]["side"] = "left"
    r = c.post("/api/original/scene/generate", json={"project_id": "p1", "plan": plan})
    assert r.status_code == 422 and "opposite sides" in r.json()["detail"]


def test_rate_then_summary_counts_it(client):
    c, _ = client
    assert c.get("/api/original/scene/ratings/summary").json()["n"] == 0
    assert c.post("/api/original/scene/rate", json={"brief_id": "fight-01", "good": True, "seconds": 20}).status_code == 200
    r = c.post("/api/original/scene/rate", json={"brief_id": "fight-02", "good": False, "reason": "pose", "seconds": 40})
    assert r.status_code == 200 and r.json()["n"] == 2
    s = c.get("/api/original/scene/ratings/summary").json()
    assert s["good_rate"] == 0.5 and s["by_reason"] == {"pose": 1} and s["mean_seconds"] == 30.0


def test_rate_rejects_an_unknown_reason(client):
    c, _ = client
    assert c.post("/api/original/scene/rate", json={"brief_id": "x", "good": False, "reason": "vibes"}).status_code == 422


def test_job_operation_runs_generate_scene_with_the_lessons_ledger(tmp_path, monkeypatch):
    from engine.original import scene_job

    captured = {}

    class Result:
        def model_dump(self, **kw):
            return {"status": "accept", "image_path": "panels/k.png"}

    def fake_generate(art, provider, plan, **kw):
        captured.update(kw, plan=plan)
        return Result()

    monkeypatch.setattr(scene_job, "generate_scene", fake_generate)
    monkeypatch.setattr(scene_job, "ArtEngine", lambda: object())
    monkeypatch.setattr(scene_job, "SCENE_ROOT", tmp_path)
    monkeypatch.setattr(llm_registry, "get_ollama_provider", lambda: FakeProvider())
    op = scene_job.build_scene_operation("p1", {"plan": fight_plan().model_dump(), "seed": 9})
    out = op(None, lambda p, m: None, lambda: False)
    assert out["status"] == "accept" and captured["seed"] == 9 and captured["ledger"] is not None
    assert str(captured["ws"]).startswith(str(tmp_path))


def test_scene_jobs_are_admitted_like_comfyui_jobs():
    # a scene job draws on ComfyUI and the local model, which already hold ~13 GB: without this the GPU gate would hold it back forever
    from engine.jobs.manager import COMFYUI_JOB_TYPES
    from engine.original import scene_job

    assert scene_job.JOB_TYPE in COMFYUI_JOB_TYPES
