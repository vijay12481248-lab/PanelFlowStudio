import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from engine.api.routers import narration
from engine.database.models import Base, ProjectRecord
from engine.database.session import get_db
from tests.unit.narration.test_compiler import _compiler, _go, _write_responses


@pytest.fixture
def env(tmp_path, monkeypatch):
    comp = _compiler(tmp_path, _write_responses(bad="number 2"))
    res = _go(tmp_path, comp, stop_after="write")
    assert res.gate == "review"
    (tmp_path / "ws2").mkdir()
    engine = create_engine(f"sqlite:///{tmp_path / 'api.sqlite'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        for pid, ws in (("proj-test", "ws"), ("other", "ws2")):
            db.add(ProjectRecord(id=pid, title=f"Title {pid}", source_type="LOCAL_FOLDER",
                                 workspace_path=str(tmp_path / ws), rights_status="PUBLIC_DOMAIN"))
        db.commit()
    app = FastAPI()
    app.include_router(narration.router)

    def get_session():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = get_session
    jobs = []
    monkeypatch.setattr(narration, "_bibles", lambda: comp.bibles)
    monkeypatch.setattr(narration, "enqueue_project_operation",
                        lambda project_id, job_type, op, **kw: jobs.append((project_id, job_type, kw)) or f"job-{len(jobs)}")
    yield TestClient(app), res, jobs, tmp_path
    engine.dispose()


def test_review_list_skips_corrupt(env):
    client, res, _, tmp_path = env
    bad = tmp_path / "ws" / "narration" / "20250101T000000-abcdef"
    bad.mkdir()
    (bad / "review.json").write_text("{not json", encoding="utf-8")
    foreign = tmp_path / "ws" / "narration" / "20250102T000000-abcdef"
    foreign.mkdir()
    (foreign / "review.json").write_text(
        (res.run_dir / "review.json").read_text(encoding="utf-8"), encoding="utf-8")  # run_dir points elsewhere
    out = client.get("/api/narration/review").json()
    assert [(i["run_id"], i["project_id"], i["project_title"], i["line_ids"]) for i in out] == [
        (res.run_id, "proj-test", "Title proj-test", ["L002"])]
    assert out[0]["reasons"] and out[0]["created"]


@pytest.mark.parametrize("run_id", ["..%5C..%5Cx", "C:%5Cx", "not-a-run", "20250101T000000-ZZZZZZ"])
def test_run_id_traversal_rejected(env, run_id):
    client, *_ = env
    assert client.get(f"/api/narration/runs/proj-test/{run_id}").status_code == 400
    assert client.post(f"/api/narration/runs/proj-test/{run_id}/approve").status_code == 400


def test_run_resolution_errors(env):
    client, res, *_ = env
    assert client.get(f"/api/narration/runs/other/{res.run_id}").status_code == 404  # another project's run
    assert client.get(f"/api/narration/runs/nope/{res.run_id}").status_code == 404
    assert client.get("/api/narration/runs/nope").status_code == 404
    assert client.get("/api/narration/runs/proj-test/20250101T000000-abcdef").status_code == 404


def test_inspector_payload_shape(env):
    client, res, _, tmp_path = env
    runs = client.get("/api/narration/runs/proj-test").json()
    assert [r["run_id"] for r in runs] == [res.run_id] and runs[0]["gate"] == "review"
    assert {"step", "status", "seconds", "model_calls"} <= set(runs[0]["steps"][0])
    assert client.get("/api/narration/runs/other").json() == []
    body = client.get(f"/api/narration/runs/proj-test/{res.run_id}").json()
    assert body["run"]["run_id"] == res.run_id
    l2 = next(ln for ln in body["lines"] if ln["line_id"] == "L002")
    assert set(l2) == {"line_id", "panel_id", "text", "status", "kind", "checks", "facts", "take"}
    assert l2["take"] is None and "action:" in l2["facts"]
    assert l2["checks"]
    assert set(l2["checks"][0]) == {"rule", "passed", "severity", "reason"}
    assert set(body["beat_sheet"]) == {"hook", "chapter_summary", "scenes"}
    assert set(body["beat_sheet"]["scenes"][0]) == {"scene_id", "goal", "first_panel_id", "last_panel_id"}
    assert body["review"]["line_ids"] == ["L002"]
    (res.run_dir / "takes.json").write_text(json.dumps([{"line_id": "L002", "wer": 0.4, "flagged": True,
                                                         "stt_text": "heard"}]), encoding="utf-8")
    l2 = next(ln for ln in client.get(f"/api/narration/runs/proj-test/{res.run_id}").json()["lines"] if ln["line_id"] == "L002")
    assert l2["take"] == {"wer": 0.4, "flagged": True, "stt_text": "heard"}


def test_edit_rejected_by_rules_is_400_and_unchanged(env):
    client, res, *_ = env
    url = f"/api/narration/runs/proj-test/{res.run_id}/lines/L002"
    before = (res.run_dir / "script.json").read_text(encoding="utf-8")
    r = client.post(url, json={"action": "edit", "text": "In this panel the man stands"})
    assert r.status_code == 400 and "banned_phrase" in r.json()["detail"]
    assert (res.run_dir / "script.json").read_text(encoding="utf-8") == before
    ok = client.post(url, json={"action": "edit", "text": "He walks through the quiet hall slowly"})
    assert ok.status_code == 200 and ok.json()["text"] == "He walks through the quiet hall slowly"
    assert ok.json()["status"] == "passed"
    assert client.post(url, json={"action": "edit"}).status_code == 400  # edit needs text
    assert client.post(url.replace("L002", "L999"), json={"action": "accept"}).status_code == 400
    assert client.post(url, json={"action": "fallback"}).json()["status"] == "fallback"


def test_regenerate_starts_job(env):
    client, res, jobs, _ = env
    r = client.post(f"/api/narration/runs/proj-test/{res.run_id}/lines/L002", json={"action": "regenerate", "hint": "shorter"})
    assert r.status_code == 200 and r.json() == {"job_id": "job-1"}
    assert jobs[0][:2] == ("proj-test", "NARRATION_REGENERATE")
    assert jobs[0][2]["job_input"] == {"run_id": res.run_id, "line_id": "L002", "hint": "shorter"}


def test_approve_starts_continue_job(env):
    client, res, jobs, _ = env
    base = f"/api/narration/runs/proj-test/{res.run_id}"
    ok = client.post(f"{base}/approve")
    assert ok.status_code == 200 and ok.json()["job_id"] == "job-1" and isinstance(ok.json()["bible_version"], int)
    assert jobs[0][:2] == ("proj-test", "NARRATION_CONTINUE") and jobs[0][2]["job_input"] == {"run_id": res.run_id}
    again = client.post(f"{base}/approve")
    assert again.status_code == 400 and len(jobs) == 1  # approving twice starts nothing
    assert client.get("/api/narration/review").json() == []
