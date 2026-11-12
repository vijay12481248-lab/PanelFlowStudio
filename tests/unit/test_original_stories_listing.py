"""The dashboard lists file-based Original Stories; opening one is confined to its own folder."""

import json
import os
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from engine.api.routers import original


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(original, "STORY_ROOT", tmp_path)
    app = FastAPI()
    app.include_router(original.router)
    return TestClient(app), tmp_path


def _story(root, slug, title="T", panels=3, video=False, old=False):
    d = root / slug
    d.mkdir()
    (d / "story.json").write_text(json.dumps({"bible": {"premise": {"title": title, "genre": "horror"}}, "panels": [{}] * panels}), encoding="utf-8")
    if video:
        (d / "story_1080p.mp4").write_bytes(b"x")
        (d / "v2_backup_story_1080p.mp4").write_bytes(b"x")     # backups must not count as the render
    if old:
        os.utime(d / "story.json", (1, 1))
    return d


def test_lists_stories_newest_first_with_video_flag_and_skips_broken_ones(client):
    c, root = client
    _story(root, "old_one", "Old", old=True)
    _story(root, "vox_new", "Vox", panels=21, video=True)
    (root / "broken").mkdir()
    (root / "broken" / "story.json").write_text("{not json", encoding="utf-8")
    (root / "no_story_file").mkdir()
    rows = c.get("/api/original/stories").json()
    assert [r["slug"] for r in rows] == ["vox_new", "old_one"]
    assert rows[0] == {**rows[0], "title": "Vox", "genre": "horror", "panels": 21, "has_video": True, "video": "story_1080p.mp4"}
    assert rows[1]["has_video"] is False and rows[1]["video"] is None


def test_open_uses_the_story_folder_or_newest_video_and_refuses_anything_else(client, monkeypatch):
    c, root = client
    d = _story(root, "vox_new", video=True)
    opened = []
    monkeypatch.setattr(os, "startfile", lambda p: opened.append(p), raising=False)
    assert c.post("/api/original/story/vox_new/open", json={}).json()["opened"] is True
    assert c.post("/api/original/story/vox_new/open", json={"target": "video"}).status_code == 200
    assert opened == [str(d), str(d / "story_1080p.mp4")]
    assert c.post("/api/original/story/missing/open", json={}).status_code == 404
    assert c.post("/api/original/story/..%2Fetc/open", json={}).status_code == 404       # slug is reduced to a bare name
    _story(root, "no_video")
    assert c.post("/api/original/story/no_video/open", json={"target": "video"}).status_code == 404
    assert len(opened) == 2


def test_inpaint_endpoint_success(client, monkeypatch):
    import base64
    c, root = client
    d = _story(root, "inpaint_story")
    panels = d / "panels"
    panels.mkdir()
    (panels / "p001.png").write_bytes(b"dummy_png_bytes")

    class FakeRunner:
        pass

    monkeypatch.setattr(original.art_mod, "ComfyRunner", FakeRunner)

    mock_called = []
    def fake_inpaint(ws, panel_id, mask_bytes, prompt, neg, seed, runner):
        mock_called.append((ws, panel_id, mask_bytes, prompt, neg, seed))
        return {
            "panel_id": panel_id,
            "candidate_file": f"panels/_candidates/{panel_id}/c001.png",
            "candidate_n": 1,
            "seed": 999,
            "sha256": "def456",
            "image": f"panels/{panel_id}.png",
            "iterations": [],
        }

    monkeypatch.setattr(original.art_mod, "inpaint_panel", fake_inpaint)

    valid_mask_b64 = base64.b64encode(b"fake_mask_bytes").decode("utf-8")
    resp = c.post(
        "/api/original/story/inpaint_story/panel/p001/inpaint",
        json={"mask_png_base64": valid_mask_b64, "prompt": "fix eyes", "negative_prompt": "blurry", "seed": 999},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["panel_id"] == "p001"
    assert data["candidate_n"] == 1
    assert data["seed"] == 999
    assert data["sha256"] == "def456"
    assert len(mock_called) == 1


def test_inpaint_endpoint_errors(client):
    c, root = client
    # 1. Missing mask
    res_empty_mask = c.post("/api/original/story/s1/panel/p001/inpaint", json={"mask_png_base64": ""})
    assert res_empty_mask.status_code == 422

    # 2. Invalid base64 mask
    res_bad_b64 = c.post("/api/original/story/s1/panel/p001/inpaint", json={"mask_png_base64": "!!!not_b64"})
    assert res_bad_b64.status_code == 422

    # 3. Missing story
    res_no_story = c.post("/api/original/story/nonexistent/panel/p001/inpaint", json={"mask_png_base64": "AAAA"})
    assert res_no_story.status_code == 404

    # 4. Missing panel
    _story(root, "exists_but_no_panel")
    res_no_panel = c.post("/api/original/story/exists_but_no_panel/panel/p001/inpaint", json={"mask_png_base64": "AAAA"})
    assert res_no_panel.status_code == 404

