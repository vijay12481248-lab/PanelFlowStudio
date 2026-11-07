"""Clip evaluation and correction-loop routes (no GPU: the loop and the art runner are replaced)."""
import importlib.util
import json
import time
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from engine.api.routers import original
from engine.original import clip_loop

SRC = Path(__file__).resolve().parents[2] / "stories" / "dawn_gate_source.py"


@pytest.fixture()
def ws(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("dg", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    story = mod.story
    d = tmp_path / "dg"
    (d / "film" / "clips").mkdir(parents=True)
    (d / "story.json").write_text(story.model_dump_json(), encoding="utf-8")
    sid = story.panels[0].id
    rng = np.random.default_rng(2)
    img = cv2.GaussianBlur(rng.integers(0, 255, (432, 768, 3), dtype=np.uint8), (0, 0), 2)
    vw = cv2.VideoWriter(str(d / "film" / "clips" / f"{sid}.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 24, (384, 216))
    for i in range(40):
        s = 1 + 0.15 * i / 39  # a 15% push-in
        m = np.array([[s, 0, 192 - s * 192], [0, s, 108 - s * 108]], np.float32)
        vw.write(cv2.warpAffine(img[108:324, 192:576], m, (384, 216), borderMode=cv2.BORDER_REFLECT))
    vw.release()
    monkeypatch.setattr(original, "STORY_ROOT", tmp_path)
    app = FastAPI()
    app.include_router(original.router)
    return TestClient(app), d, sid


def test_eval_reports_the_push_in_as_a_camera_flag_and_static_vs_any(ws):
    c, _, sid = ws
    r = c.get(f"/api/original/story/dg/film/clip/{sid}/eval").json()
    assert r["camera"]["zoom_pct"] > 8 and any(f["axis"] == "camera" for f in r["flags"]) and "score" not in r
    assert not any(f["axis"] == "camera" for f in c.get(f"/api/original/story/dg/film/clip/{sid}/eval?camera=any").json()["flags"])
    assert c.get(f"/api/original/story/dg/film/clip/{sid}/eval?camera=wild").status_code == 422


def test_eval_404s(ws):
    c, d, sid = ws
    assert c.get("/api/original/story/dg/film/clip/nope/eval").status_code == 404
    assert c.get("/api/original/story/missing/film/clip/p001/eval").status_code == 404
    (d / "film" / "clips" / f"{sid}.mp4").unlink()
    assert c.get(f"/api/original/story/dg/film/clip/{sid}/eval").status_code == 404


def test_improve_starts_a_job_and_passes_the_options_through(ws, monkeypatch):
    c, d, sid = ws
    seen = {}

    def fake_improve(shot, wsd, gen, settings, **kw):
        seen.update(kw, shot=shot)
        return {"best": "x.mp4", "settings": settings, "report": {}, "applied": False, "stopped": "no confirmed defect left", "defects_left": [], "needs_look": [],
                "history": [{"attempt": 0, "lever": None, "decision": "baseline", "reason": "r", "changed": {}}]}

    monkeypatch.setattr(clip_loop, "improve_clip", fake_improve)
    monkeypatch.setattr(clip_loop, "film_generate", lambda *a, **k: None)
    r = c.post(f"/api/original/story/dg/film/clip/{sid}/improve?attempts=2&suspected=true&redraw=false")
    assert r.status_code == 202
    for _ in range(50):
        job = c.get(f"/api/original/film/job/{r.json()['id']}").json()
        if job["status"] != "running":
            break
        time.sleep(0.1)
    assert job["status"] == "done" and job["result"]["stopped"] == "no confirmed defect left"
    assert seen["attempts"] == 2 and seen["act_on_suspected"] is True and seen["apply"] is False and "redraw_frame" not in seen["levers"] and seen["shot"] == sid


def test_improve_validates_and_history_reads_the_file(ws):
    c, d, sid = ws
    assert c.post(f"/api/original/story/dg/film/clip/{sid}/improve?attempts=99").status_code == 422
    assert c.post(f"/api/original/story/dg/film/clip/{sid}/improve?camera=zig").status_code == 422
    assert c.get(f"/api/original/story/dg/film/clip/{sid}/history").json() == []
    (d / "film" / "history").mkdir()
    (d / "film" / "history" / f"{sid}.json").write_text(json.dumps([{"attempt": 0}]), encoding="utf-8")
    assert c.get(f"/api/original/story/dg/film/clip/{sid}/history").json() == [{"attempt": 0}]
