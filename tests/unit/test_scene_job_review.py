"""Task 7 of the review-page plan: the generation job saves a reviewable run and runs the two judges (fake engine, fake judges, temp database)."""
import io
import uuid

import pytest
from PIL import Image

from engine.database.models import Base, ProjectRecord
from engine.database.session import SessionLocal, ensure_scene_fts, engine as db_engine
from engine.llm.registry import llm_registry
from engine.original import scene_job, scene_store
from engine.original.judges import JudgeAnswer
from scene_fixtures import fight_plan


def png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 18), "grey").save(buf, "PNG")
    return buf.getvalue()


class FakeProvider:
    async def health_check(self):
        return True


class FakeResult:
    def __init__(self, ws, key):
        (ws / "panels").mkdir(parents=True, exist_ok=True)
        (ws / "panels" / f"{key}.png").write_bytes(png())
        self.d = {"image_path": f"panels/{key}.png", "status": "accept", "unmet": [], "unverified": False, "seconds": 12.0, "iterations": [{"n": 1, "kind": "generate"}], "review": None,
                  "final": {"prompt": "the delivered prompt", "seed": 123, "lessons": "a lesson"}}

    def model_dump(self, **kw):
        return dict(self.d)


class Judge:
    def __init__(self, name, camera="looks_up"):
        self.name, self.camera = name, camera

    async def read(self, image, states):
        return JudgeAnswer(judge=self.name, ok=True, camera=self.camera, people=2, actions=["striking", "blocking"], evidence="faces seen from below")

    async def reread(self, image, topic, index, other, states):
        return JudgeAnswer(judge=self.name, ok=False)


@pytest.fixture
def env(tmp_path, monkeypatch):
    Base.metadata.create_all(db_engine)
    ensure_scene_fts(db_engine)
    db = SessionLocal()
    pid = f"proj-{uuid.uuid4().hex[:8]}"
    db.add(ProjectRecord(id=pid, title="Scene Director", source_type="CHRONOFLOW_AI", rights_status="USER_OWNED", workspace_path="x"))
    db.commit()
    monkeypatch.setattr(scene_job, "SCENE_ROOT", tmp_path)
    monkeypatch.setattr(scene_job, "ArtEngine", lambda: object())
    monkeypatch.setattr(scene_job, "release_local_model", lambda: None)
    monkeypatch.setattr(llm_registry, "get_ollama_provider", lambda: FakeProvider())

    def fake_generate(art, provider, plan, *, ws, key, **kw):
        return FakeResult(ws, key)

    monkeypatch.setattr(scene_job, "generate_scene", fake_generate)
    monkeypatch.setattr(scene_job, "default_judges", lambda provider: [Judge("A"), Judge("B")])
    yield db, pid
    db.rollback()
    project = db.get(ProjectRecord, pid)
    if project:
        db.delete(project)
        db.commit()
    db.close()


def run_job(db, pid):
    op = scene_job.build_scene_operation(pid, {"plan": fight_plan().model_dump(), "seed": 3})
    return op(db, lambda p, m: None, lambda: False)


def test_job_saves_a_pending_run_and_returns_its_id(env):
    db, pid = env
    out = run_job(db, pid)
    run = scene_store.get_run(db, out["run_id"])
    assert run["review_state"] == "pending" and run["project_id"] == pid and run["brief"] == fight_plan().brief and run["status"] == "accept"
    assert out["image_file"].endswith(".png")


def test_job_stores_the_crosscheck_analysis(env):
    db, pid = env
    out = run_job(db, pid)
    analysis = scene_store.get_run(db, out["run_id"])["analysis"]
    assert analysis["judges"] == ["A", "B"] and analysis["single_judge"] is False and analysis["error"] is None
    assert {i["key"] for i in analysis["crosscheck"]["items"]} >= {"camera", "people", "action:0", "action:1"}
    assert all(i["status"] == "agreed" for i in analysis["crosscheck"]["items"])


def test_judging_failure_is_stored_and_the_job_still_succeeds(env, monkeypatch):
    db, pid = env

    def boom(provider):
        raise RuntimeError("judges exploded")

    monkeypatch.setattr(scene_job, "default_judges", boom)
    out = run_job(db, pid)
    analysis = scene_store.get_run(db, out["run_id"])["analysis"]
    assert out["status"] == "accept" and "judges exploded" in analysis["error"] and analysis["crosscheck"] == {}


def test_second_judge_missing_gives_single_judge_analysis(env, monkeypatch):
    db, pid = env
    monkeypatch.setattr(scene_job, "default_judges", lambda provider: [Judge("A")])
    analysis = scene_store.get_run(db, run_job(db, pid)["run_id"])["analysis"]
    assert analysis["single_judge"] is True and analysis["judges"] == ["A"]


def test_saving_the_run_failing_does_not_fail_the_picture(env, monkeypatch):
    db, pid = env

    def boom(*a, **k):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(scene_job.scene_store, "create_run", boom)
    out = run_job(db, pid)
    assert out["status"] == "accept" and "database is locked" in out["run_error"] and "run_id" not in out


def test_default_judges_can_be_switched_to_the_single_judge(monkeypatch):
    import asyncio

    from engine.original import judges

    async def fake_available(provider, client):
        return [Judge("A"), Judge("B")]

    monkeypatch.setattr(judges, "available_judges", fake_available)
    monkeypatch.setenv("SCENE_CROSSCHECK", "0")
    assert [j.name for j in judges.default_judges(object(), client=object())] == ["A"]
    monkeypatch.delenv("SCENE_CROSSCHECK")
    assert [j.name for j in judges.default_judges(object(), client=object())] == ["A", "B"]


def test_job_passes_the_owners_complaints_to_the_next_picture_as_lessons(env, monkeypatch):
    db, pid = env
    for _ in range(2):  # two pictures of this scene type the owner marked "camera" wrong, liked under 60%
        r = scene_store.create_run(db, project_id=pid, job_id=None, brief="b", plan=fight_plan().model_dump(mode="json"), image_path="panels/a.png",
                                   result={"status": "accept", "iterations": [], "seconds": 1})
        scene_store.submit_feedback(db, r["id"], liked=20, agrees_with_ai=False, good_tags=[], wrong_tags=["camera"])
    seen = {}

    def spy(art, provider, plan, *, ws, key, **kw):
        seen.update(kw)
        return FakeResult(ws, key)

    monkeypatch.setattr(scene_job, "generate_scene", spy)
    run_job(db, pid)
    assert "horizon sits below the people" in seen["lessons"]


def test_lessons_lookup_failing_never_stops_the_picture(env, monkeypatch):
    db, pid = env

    def boom(*a, **k):
        raise RuntimeError("db gone")

    monkeypatch.setattr(scene_job, "lessons_from_feedback", boom)
    assert run_job(db, pid)["status"] == "accept"



def test_the_saved_run_keeps_the_prompt_seed_and_lessons_that_made_the_picture(env):
    db, pid = env
    out = run_job(db, pid)
    final = scene_store.get_run(db, out["run_id"])["system_review"]["final"]
    assert final == {"prompt": "the delivered prompt", "seed": 123, "lessons": "a lesson"}
