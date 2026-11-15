"""The ChronoFlow library: videos from every producer folder show up, import lands them as a studio project, and jobs never touch the git vault."""
import os
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from engine.api.routers import chronoflow as cf
from engine.api.routers import chronoflow_library as lib
from engine.chronoflow import supervisor as sup_mod


@pytest.fixture
def world(tmp_path, monkeypatch):
    root = tmp_path / "output"
    studio = root / "chronoflow"
    for d in (studio, root / "reels", root / "Original_Stories" / "story_1", root / "_scratch"):
        d.mkdir(parents=True)
    (root / "reels" / "reel_a.mp4").write_bytes(b"a" * 10)
    (root / "Original_Stories" / "story_1" / "shot_01.mp4").write_bytes(b"b" * 10)
    (root / "Original_Stories" / "story_1" / "notes.txt").write_text("x")
    (root / "Original_Stories" / "story_1" / "concat_tmp.mp4").write_bytes(b"c" * 10)
    (root / "reels" / "empty.mp4").write_bytes(b"")
    (root / "_scratch" / "hidden.mp4").write_bytes(b"d" * 10)
    old = time.time() - 3600
    os.utime(root / "Original_Stories" / "story_1" / "shot_01.mp4", (old, old))
    monkeypatch.setattr(lib, "LIBRARY_ROOT", root)
    monkeypatch.setattr(lib, "STUDIO_OUTPUT_DIR", studio)
    monkeypatch.setattr(lib.media_tools, "probe", lambda p: {"duration": 4.5, "fps": 24.0, "width": 1, "height": 1, "has_audio": True, "is_image": False})
    monkeypatch.setattr(cf, "load_storage_locations", lambda: [])
    monkeypatch.setattr(cf.supervisor, "_save_jobs_to_disk", lambda: None)
    lib._scan_cache["t"] = 0.0
    app = FastAPI()
    app.include_router(lib.router)
    before = set(cf.active_jobs)
    yield TestClient(app), root, studio
    for k in set(cf.active_jobs) - before:
        cf.active_jobs.pop(k)


def test_recent_videos_come_from_every_producer_folder_newest_first(world):
    client, _root, _studio = world
    body = client.get("/api/chronoflow/library/videos").json()
    names = [i["name"] for i in body["items"]]
    assert names == ["reel_a.mp4", "shot_01.mp4"], "newest first; temp concat files, empty files, non-video and _private folders are left out"
    assert {s["id"] for s in client.get("/api/chronoflow/library/sources").json()["sources"]} == {"reels", "Original_Stories"}
    assert [i["name"] for i in client.get("/api/chronoflow/library/videos?source=Original_Stories").json()["items"]] == ["shot_01.mp4"]
    assert client.get("/api/chronoflow/library/videos?q=REEL").json()["total"] == 1


def test_import_creates_a_project_whose_clips_the_player_can_find(world):
    client, root, studio = world
    r = client.post("/api/chronoflow/library/import", json={"paths": [str(root / "reels" / "reel_a.mp4"), str(root / "Original_Stories" / "story_1" / "notes.txt")]})
    body = r.json()
    assert r.status_code == 200 and body["job_id"].startswith("imp_")
    assert [a["name"] for a in body["added"]] == ["reel_a.mp4"] and body["skipped"][0]["reason"].startswith("not a")
    job = cf.active_jobs[body["job_id"]]
    assert job["workflow_mode"] == "imported" and job["status"] == "completed" and job["total_duration"] == 4.5
    name = job["chunks"][0].rsplit("/", 1)[1]
    assert (studio / name).is_file() and name == f"{body['job_id']}_chunk_1.mp4", "named like a generated chunk so resolve_media and the reconciler see it"
    assert (root / "reels" / "reel_a.mp4").exists(), "the original is left alone"


def test_more_videos_can_be_added_to_an_imported_project_but_not_to_a_generated_one(world):
    client, root, _studio = world
    first = client.post("/api/chronoflow/library/import", json={"paths": [str(root / "reels" / "reel_a.mp4")]}).json()["job_id"]
    again = client.post("/api/chronoflow/library/import", json={"job_id": first, "paths": [str(root / "Original_Stories" / "story_1" / "shot_01.mp4")]}).json()
    assert again["job_id"] == first and len(cf.active_jobs[first]["chunks"]) == 2 and cf.active_jobs[first]["total_duration"] == 9.0
    cf.active_jobs["gen_1"] = {"id": "gen_1", "workflow_mode": "storyboard", "chunks": []}
    assert client.post("/api/chronoflow/library/import", json={"job_id": "gen_1", "paths": [str(root / "reels" / "reel_a.mp4")]}).status_code == 400


def test_nothing_importable_is_an_error_that_says_why(world):
    client, root, _ = world
    r = client.post("/api/chronoflow/library/import", json={"paths": [str(root / "missing.mp4")]})
    assert r.status_code == 400 and r.json()["detail"]["skipped"][0]["reason"] == "file not found"
    assert client.post("/api/chronoflow/library/import", json={"paths": []}).status_code == 400


def test_jobs_are_stored_in_app_data_never_in_the_git_tracked_vault():
    assert sup_mod.JOBS_FILE.parent == sup_mod.JOBS_DIR
    assert sup_mod.VAULT_DIR not in sup_mod.JOBS_FILE.parents, "the vault is tracked by git and was being rewritten by test runs"
    assert Path(os.environ["PANELFLOW_APP_DATA"]) in sup_mod.JOBS_FILE.parents, "tests must get a temp dir, not the owner's real jobs"


def test_sync_for_a_job_with_a_lone_surrogate_in_its_text_is_still_valid_json():
    import asyncio, json
    sup = cf.supervisor
    sup.active_jobs["sur_1"] = {"id": "sur_1", "prompt": "he said \udc9d", "status": "completed", "chunks": [], "created_at": 1}
    try:
        state = asyncio.run(sup.get_unified_sync_state(0, "sur_1"))
        json.dumps(state).encode("utf-8")        # the real response path: this raised and /sync returned 500
        assert state["active_job"]["prompt"].startswith("he said")
        assert state["jobs_summary"][0]["title"]
    finally:
        sup.active_jobs.pop("sur_1", None)
