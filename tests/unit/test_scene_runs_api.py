"""Task 6 of the review-page plan: run, feedback and knowledge endpoints (temp database from conftest, real FastAPI app)."""
import uuid

import pytest
from fastapi.testclient import TestClient

from engine.database.models import Base, ProjectRecord
from engine.database.session import SessionLocal, ensure_scene_fts, engine as db_engine
from engine.original import scene_job, scene_store

RESULT = {"status": "accept", "unmet": [], "unverified": False, "seconds": 20.0, "iterations": [{"kind": "generate"}], "review": None}
PLAN = {"scene_type": "fight", "brief": "two samurai at dusk"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    from engine.api.app import create_app

    Base.metadata.create_all(db_engine)
    ensure_scene_fts(db_engine)
    monkeypatch.setattr(scene_job, "SCENE_ROOT", tmp_path)
    db = SessionLocal()
    pid = f"proj-{uuid.uuid4().hex[:8]}"
    db.add(ProjectRecord(id=pid, title="Scene Director", source_type="CHRONOFLOW_AI", rights_status="USER_OWNED", workspace_path="x"))
    db.commit()
    (tmp_path / pid / "panels").mkdir(parents=True)
    (tmp_path / pid / "panels" / "a.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    client = TestClient(create_app(allow_insecure=True), base_url="http://localhost")
    yield client, db, pid, tmp_path
    db.rollback()
    project = db.get(ProjectRecord, pid)
    if project:
        db.delete(project)
        db.commit()
    db.close()


def make_run(db, pid, brief="two samurai at dusk", image="panels/a.png"):
    return scene_store.create_run(db, project_id=pid, job_id="j", brief=brief, plan={**PLAN, "brief": brief}, image_path=image, result=RESULT)


def test_list_and_get_runs(env):
    c, db, pid, _ = env
    run = make_run(db, pid)
    listing = c.get("/api/original/scene/runs", params={"unreviewed": True, "limit": 5}).json()
    assert listing["total_unreviewed"] >= 1 and any(r["id"] == run["id"] for r in listing["items"])
    got = c.get(f"/api/original/scene/runs/{run['id']}")
    assert got.status_code == 200 and got.json()["brief"] == "two samurai at dusk" and got.json()["feedback"] is None
    assert c.get("/api/original/scene/runs/nope").status_code == 404


def test_feedback_roundtrip_and_validation(env):
    c, db, pid, _ = env
    run = make_run(db, pid)
    url = f"/api/original/scene/runs/{run['id']}/feedback"
    ok = c.post(url, json={"liked": 80, "agrees_with_ai": True, "good_tags": ["mood"], "wrong_tags": ["camera"], "note": "close"})
    assert ok.status_code == 200 and ok.json()["review_state"] == "reviewed" and ok.json()["feedback"]["liked"] == 80
    assert c.post(url, json={"liked": 101, "agrees_with_ai": True, "good_tags": [], "wrong_tags": [], "note": ""}).status_code == 422
    assert c.post(url, json={"liked": -1, "agrees_with_ai": True, "good_tags": [], "wrong_tags": [], "note": ""}).status_code == 422
    assert c.post(url, json={"liked": 50, "agrees_with_ai": True, "good_tags": ["t"] * 50, "wrong_tags": [], "note": ""}).status_code == 422
    assert c.post("/api/original/scene/runs/nope/feedback", json={"liked": 50, "agrees_with_ai": True, "good_tags": [], "wrong_tags": [], "note": ""}).status_code == 404


def test_a_huge_note_is_rejected_by_the_request_model(env):
    c, db, pid, _ = env
    run = make_run(db, pid)
    r = c.post(f"/api/original/scene/runs/{run['id']}/feedback", json={"liked": 50, "agrees_with_ai": True, "good_tags": [], "wrong_tags": [], "note": "n" * 100_000})
    assert r.status_code == 422


def test_dismiss(env):
    c, db, pid, _ = env
    run = make_run(db, pid)
    assert c.post(f"/api/original/scene/runs/{run['id']}/dismiss").json()["review_state"] == "dismissed"
    assert c.post("/api/original/scene/runs/nope/dismiss").status_code == 404


def test_image_is_served_and_a_path_outside_the_root_is_404(env):
    c, db, pid, tmp = env
    run = make_run(db, pid)
    r = c.get(f"/api/original/scene/runs/{run['id']}/image")
    assert r.status_code == 200 and r.content.startswith(b"\x89PNG")
    (tmp / "secret.txt").write_text("secret")
    sneaky = make_run(db, pid, image="../../secret.txt")
    assert c.get(f"/api/original/scene/runs/{sneaky['id']}/image").status_code == 404
    missing = make_run(db, pid, image="panels/missing.png")
    assert c.get(f"/api/original/scene/runs/{missing['id']}/image").status_code == 404


def test_knowledge_stats_and_search(env):
    c, db, pid, _ = env
    run = make_run(db, pid, brief="a dragon over a frozen canyon")
    c.post(f"/api/original/scene/runs/{run['id']}/feedback", json={"liked": 20, "agrees_with_ai": False, "good_tags": [], "wrong_tags": ["style"], "note": "too cartoonish"})
    s = c.get("/api/original/scene/knowledge/stats").json()
    assert s["runs"] >= 1 and s["wrong_tags"]["style"] >= 1 and "ai_agreement" in s
    hits = c.get("/api/original/scene/knowledge/search", params={"q": "cartoonish"}).json()
    assert [h["id"] for h in hits] == [run["id"]]
    assert c.get("/api/original/scene/knowledge/search", params={"q": '"'}).status_code == 200
    assert c.get("/api/original/scene/knowledge/search").status_code in (200, 422)


def test_mcp_tools_for_runs_and_knowledge_are_registered():
    from engine.mcp.registry import registry
    import engine.mcp.tools.original_story_tools  # noqa: F401

    for name in ("panelflow_scene_runs", "panelflow_scene_knowledge_stats", "panelflow_scene_knowledge_search"):
        assert registry.get_tool(name) is not None, name


def test_feedback_accepts_owner_choices_for_disputed_items_and_bounds_them(env):
    c, db, pid, _ = env
    run = make_run(db, pid)
    url = f"/api/original/scene/runs/{run['id']}/feedback"
    base = {"liked": 50, "agrees_with_ai": False, "good_tags": [], "wrong_tags": [], "note": ""}
    ok = c.post(url, json={**base, "item_verdicts": {"camera": "looks_up"}})
    assert ok.status_code == 200 and ok.json()["feedback"]["item_verdicts"] == {"camera": "looks_up"}
    assert c.post(url, json={**base, "item_verdicts": {f"action:{i}": "x" for i in range(30)}}).status_code == 422
