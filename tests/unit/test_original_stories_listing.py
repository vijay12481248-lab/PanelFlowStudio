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
