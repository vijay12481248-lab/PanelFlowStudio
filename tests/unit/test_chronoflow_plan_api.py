"""Plan endpoints: kit download, check, import, picture job."""
import copy
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from engine.api.app import app
from engine.api.routers import chronoflow as router
from engine.chronoflow import plan_check as pc
from engine.chronoflow import plan_import as pi
from engine.original import film

EXAMPLE = json.loads((Path(pc.__file__).parent / "plan_kit" / "example_plan.json").read_text(encoding="utf-8"))
BASE = "/api/chronoflow/plan"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(pi, "OUTPUT_ROOT", tmp_path / "out")
    monkeypatch.setattr(router, "COMFY_INPUT_DIR", tmp_path / "inputs")
    (tmp_path / "inputs").mkdir()
    router.PLAN_JOBS.clear()
    with TestClient(app) as c:
        yield c


def test_kit_downloads_as_a_file_with_the_example_inside(client):
    r = client.get(f"{BASE}/kit")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"] and "PANELFLOW_VIDEO_PLAN_KIT.md" in r.headers["content-disposition"]
    assert r.text.startswith("# PanelFlow Video Plan Kit") and "Why Do Rainbows Appear?" in r.text


def test_checker_downloads_exactly_the_code_the_app_runs(client):
    r = client.get(f"{BASE}/checker")
    assert r.status_code == 200 and "check_plan.py" in r.headers["content-disposition"]
    assert r.text.strip() == Path(pc.__file__).read_text(encoding="utf-8").strip()


def test_validate_a_good_plan_summarises_it(client):
    r = client.post(f"{BASE}/validate", json={"text": "```json\n" + json.dumps(EXAMPLE) + "\n```"})
    body = r.json()
    assert r.status_code == 200 and body["ok"] is True and body["problems"] == []
    assert body["summary"] == {"title": "Why Do Rainbows Appear?", "target": "film", "takes": 4, "pictures": 6, "seconds": 20.0, "format": "16:9", "clip_seconds": 5, "narration": "narrator"}


def test_validate_lists_every_problem_in_plain_words(client):
    bad = copy.deepcopy(EXAMPLE)
    bad["takes"][0]["narration"] = "Too short."
    bad["takes"][1]["motion"] = "Mira walks across the meadow while Pip follows slowly behind her."
    body = client.post(f"{BASE}/validate", json={"text": json.dumps(bad)}).json()
    assert body["ok"] is False and len(body["problems"]) >= 2 and body["summary"] is None
    assert any("narration has 2 words" in p for p in body["problems"]) and any("direction" in p for p in body["problems"])


@pytest.mark.parametrize("text", ["", "hello", '{"a": '])
def test_validate_garbage_is_a_problem_not_a_crash(client, text):
    body = client.post(f"{BASE}/validate", json={"text": text}).json()
    assert body["ok"] is False and len(body["problems"]) == 1


def test_import_returns_the_storyboard_and_saves_the_workspace(client, tmp_path):
    r = client.post(f"{BASE}/import", json={"text": json.dumps(EXAMPLE)})
    body = r.json()
    assert r.status_code == 200 and body["success"] is True and len(body["screenplay"]["scenes"]) == 4
    ws = tmp_path / "out" / body["slug"]
    assert (ws / "plan.json").exists() and (ws / "story.json").exists() and body["screenplay"]["anchor_images"]["plan"]["slug"] == body["slug"]


def test_import_refuses_a_bad_plan_with_the_problem_list(client, tmp_path):
    bad = copy.deepcopy(EXAMPLE)
    bad["takes"][0]["end_picture"] = "Too short."
    r = client.post(f"{BASE}/import", json={"text": json.dumps(bad)})
    assert r.status_code == 400 and any("end_picture" in p for p in r.json()["problems"])
    assert not (tmp_path / "out").exists() or not list((tmp_path / "out").iterdir())  # nothing half-imported


def wait_done(client, slug, secs=10):
    end = time.time() + secs
    while time.time() < end:
        s = client.get(f"{BASE}/pictures/status", params={"slug": slug}).json()
        if s["status"] in ("done", "failed"):
            return s
        time.sleep(0.05)
    raise AssertionError("picture job did not finish")


def test_picture_job_runs_and_reports(client, tmp_path, monkeypatch):
    slug = client.post(f"{BASE}/import", json={"text": json.dumps(EXAMPLE)}).json()["slug"]

    def fake(story, ws):
        def draw(progress):
            fd = film.film_dir(ws)
            for p in story.panels:
                (fd / "frames" / f"{p.id}.png").write_bytes(b"s")
                (fd / "frames" / f"{p.id}_end.png").write_bytes(b"e")
                progress(f"  {p.id}: ok")
            return {p.id: {"problems": {}} for p in story.panels}
        return draw

    monkeypatch.setattr(router, "_draw_fn", fake)
    assert client.post(f"{BASE}/pictures/start", json={"slug": slug}).json()["success"] is True
    s = wait_done(client, slug)
    assert s["status"] == "done" and s["done_takes"] == 4 and (tmp_path / "inputs" / f"{slug}_t01_start.png").exists()


def test_picture_job_failure_is_visible(client, monkeypatch):
    slug = client.post(f"{BASE}/import", json={"text": json.dumps(EXAMPLE)}).json()["slug"]

    def broken(story, ws):
        def draw(progress):
            raise RuntimeError("ComfyUI is down")
        return draw

    monkeypatch.setattr(router, "_draw_fn", broken)
    client.post(f"{BASE}/pictures/start", json={"slug": slug})
    s = wait_done(client, slug)
    assert s["status"] == "failed" and "ComfyUI is down" in s["error"]


def test_picture_job_guards(client, monkeypatch):
    assert client.post(f"{BASE}/pictures/start", json={"slug": "nope"}).status_code == 404
    assert client.post(f"{BASE}/pictures/start", json={"slug": "../etc"}).status_code == 400
    assert client.get(f"{BASE}/pictures/status", params={"slug": "nope"}).status_code == 404
    slug = client.post(f"{BASE}/import", json={"text": json.dumps(EXAMPLE)}).json()["slug"]
    gate = {"open": False}

    def slow(story, ws):
        def draw(progress):
            while not gate["open"]:
                time.sleep(0.02)
            return {}
        return draw

    monkeypatch.setattr(router, "_draw_fn", slow)
    assert client.post(f"{BASE}/pictures/start", json={"slug": slug}).status_code == 200
    assert client.post(f"{BASE}/pictures/start", json={"slug": slug}).status_code == 409  # already drawing
    gate["open"] = True
    wait_done(client, slug)
