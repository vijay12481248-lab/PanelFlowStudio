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
    assert client.get("/api/narration/review").json() == []
    again = client.post(f"{base}/approve")  # stranded: approved, no timeline yet, so the continue job is queued again
    assert again.status_code == 200 and again.json()["job_id"] == "job-2" and len(jobs) == 2
    assert again.json()["bible_version"] == ok.json()["bible_version"]
    (res.run_dir / "continued.json").write_text('"script-1"', encoding="utf-8")
    done = client.post(f"{base}/approve")
    assert done.status_code == 400 and "already finished" in done.json()["detail"] and len(jobs) == 2


def test_regenerate_unknown_line_is_400_without_job(env):
    client, res, jobs, _ = env
    r = client.post(f"/api/narration/runs/proj-test/{res.run_id}/lines/L999", json={"action": "regenerate"})
    assert r.status_code == 400 and not jobs


def test_action_returns_inspector_shape_with_fresh_checks(env):
    client, res, *_ = env
    base = f"/api/narration/runs/proj-test/{res.run_id}"
    out = client.post(f"{base}/lines/L002", json={"action": "edit", "text": "He walks through the quiet hall slowly"}).json()
    assert set(out) == {"line_id", "panel_id", "text", "status", "kind", "checks", "facts", "take"}
    assert out["checks"] and "action:" in out["facts"]
    insp = next(ln for ln in client.get(base).json()["lines"] if ln["line_id"] == "L002")
    assert insp == out


def _lines(client, res):
    return {ln["line_id"]: ln for ln in client.get(f"/api/narration/runs/proj-test/{res.run_id}").json()["lines"]}


def test_inspector_keeps_judge_verdicts_for_unchanged_lines(env):
    client, res, *_ = env
    p = res.run_dir / "critique.json"
    report = json.loads(p.read_text(encoding="utf-8"))
    next(lc for lc in report["lines"] if lc["line_id"] == "L002")["checks"].append(
        {"rule": "grounded", "passed": False, "severity": "block", "reason": "invents a sword"})
    p.write_text(json.dumps(report), encoding="utf-8")
    grounded = [c for c in _lines(client, res)["L002"]["checks"] if c["rule"] == "grounded"]
    assert grounded == [{"rule": "grounded", "passed": False, "severity": "block", "reason": "invents a sword"}]
    url = f"/api/narration/runs/proj-test/{res.run_id}/lines/L002"
    edited = client.post(url, json={"action": "edit", "text": "He walks through the quiet hall slowly"}).json()
    assert not [c for c in edited["checks"] if c["rule"] == "grounded"]  # a new text has no verdict yet


def test_inspector_without_review_json_still_has_facts_and_beat_sheet(env):
    client, res, *_ = env
    (res.run_dir / "review.json").unlink()  # a passed run
    body = client.get(f"/api/narration/runs/proj-test/{res.run_id}").json()
    assert body["review"] is None and body["beat_sheet"] and body["beat_sheet"]["scenes"]
    assert all(ln["facts"] for ln in body["lines"])


def test_approved_run_with_timeline_but_no_continued_is_retried(env):
    client, res, jobs, _ = env
    base = f"/api/narration/runs/proj-test/{res.run_id}"
    assert client.post(f"{base}/approve").status_code == 200
    (res.run_dir / "timeline.json").write_text("{}", encoding="utf-8")  # continue died after the timeline was written
    again = client.post(f"{base}/approve")
    assert again.status_code == 200 and again.json()["job_id"] == "job-2" and len(jobs) == 2


def test_take_audio_route(env):
    client, res, _, tmp_path = env
    wav = tmp_path / "ws" / "take.wav"
    wav.write_bytes(b"RIFF")
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"RIFF")
    takes = [{"line_id": "L002", "audio_path": str(wav)}, {"line_id": "L003", "audio_path": str(outside)}]
    (res.run_dir / "takes.json").write_text(json.dumps(takes), encoding="utf-8")
    base = f"/api/narration/runs/proj-test/{res.run_id}/takes"
    assert client.get(f"{base}/L002/audio").status_code == 200
    assert client.get(f"{base}/L999/audio").status_code == 404  # not in takes.json
    assert client.get(f"{base}/L003/audio").status_code == 404  # outside the workspace


def test_missing_panel_facts_degrade_to_empty(env):
    client, res, *_ = env
    p = res.run_dir / "panel_facts.json"
    facts = json.loads(p.read_text(encoding="utf-8"))
    gone = next(ln for ln in client.get(f"/api/narration/runs/proj-test/{res.run_id}").json()["lines"] if ln["line_id"] == "L002")["panel_id"]
    p.write_text(json.dumps([f for f in facts if f["panel_id"] != gone]), encoding="utf-8")
    r = client.get(f"/api/narration/runs/proj-test/{res.run_id}")
    assert r.status_code == 200
    assert next(ln for ln in r.json()["lines"] if ln["line_id"] == "L002")["facts"] == ""
