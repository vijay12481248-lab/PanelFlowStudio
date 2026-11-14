import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from engine.api.routers import chronoflow


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(chronoflow.router)
    return TestClient(app)


def test_api_status(client):
    with patch.object(chronoflow.pipeline, "check_comfy_status") as mock_status:
        mock_status.return_value = {
            "connected": True,
            "gpu": "RTX 5060 Ti",
            "vram_free_gb": 12.0,
            "vram_total_gb": 16.0,
            "queue": {"busy": False},
        }
        res = client.get("/api/chronoflow/status")
        assert res.status_code == 200
        data = res.json()
        assert data["comfy"]["connected"] is True
        assert data["comfy"]["gpu"] == "RTX 5060 Ti"
        assert "models" in data


def test_api_characters_crud(client):
    # GET list
    res = client.get("/api/chronoflow/characters")
    assert res.status_code == 200
    assert "characters" in res.json()

    # POST new character
    new_char = {
        "id": "char_test_agent",
        "name": "Special Agent Whiskers",
        "role": "Detective",
        "image": "whiskers.png",
        "description": "Orange ginger tabby with sunglasses.",
    }
    post_res = client.post("/api/chronoflow/characters", json=new_char)
    assert post_res.status_code == 200
    assert post_res.json()["success"] is True

    # Verify added
    res2 = client.get("/api/chronoflow/characters")
    chars = res2.json()["characters"]
    matched = [c for c in chars if c["id"] == "char_test_agent"]
    assert len(matched) == 1
    assert matched[0]["name"] == "Special Agent Whiskers"

    # DELETE character
    del_res = client.delete("/api/chronoflow/characters/char_test_agent")
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True


def test_api_ai_director_plan(client):
    payload = {
        "idea": "Cyberpunk runner escapes across neon rooftops",
        "duration": 15,
    }
    res = client.post("/api/chronoflow/ai_director/plan", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert len(data["scenes"]) == 3
    assert data["scenes"][0]["shot_index"] == 1
    assert "subject_definitions:" in data["scenes"][0]["prompt"] or "detailed_description:" in data["scenes"][0]["prompt"]


def test_api_jobs_and_sync(client):
    res = client.get("/api/chronoflow/jobs")
    assert res.status_code == 200
    assert "jobs" in res.json()

    sync_res = client.get("/api/chronoflow/sync?v=0")
    assert sync_res.status_code == 200
    sync_data = sync_res.json()
    assert "version" in sync_data
    assert "comfy" in sync_data


def test_api_gallery(client):
    res = client.get("/api/chronoflow/gallery")
    assert res.status_code == 200
    data = res.json()
    assert "masters" in data
    assert "chunks" in data
    assert "images" in data
    assert "stats" in data


def test_api_ui_route(client):
    res = client.get("/api/chronoflow/ui")
    assert res.status_code == 200
    assert "<!DOCTYPE html>" in res.text or "<html" in res.text

def test_full_app_chronoflow_ui_routes():
    from engine.api.app import create_app
    full_client = TestClient(create_app(allow_insecure=True))
    for endpoint in ["/chronoflow/ui", "/chronoflow", "/api/chronoflow/ui"]:
        r = full_client.get(endpoint)
        assert r.status_code == 200
        assert "<!DOCTYPE html>" in r.text or "<html" in r.text


def test_api_storage_drives(client):
    res = client.get("/api/chronoflow/storage/drives")
    assert res.status_code == 200
    data = res.json()
    assert "drives" in data
    assert len(data["drives"]) >= 1
    assert "drive" in data["drives"][0]


def test_api_storage_locations_crud_and_asset_save(client, tmp_path, monkeypatch):
    custom_dir = tmp_path / "MyCustomArt"
    custom_dir.mkdir()

    loc_file = tmp_path / "storage_locations.json"
    monkeypatch.setattr(chronoflow, "STORAGE_LOCATIONS_FILE", loc_file)
    monkeypatch.setattr(chronoflow, "COMFY_INPUT_DIR", tmp_path / "input")
    (tmp_path / "input").mkdir()

    # GET locations (empty initially)
    res = client.get("/api/chronoflow/storage/locations")
    assert res.status_code == 200
    assert res.json()["locations"] == []

    # POST create location
    create_payload = {
        "name": "Project Cyberpunk",
        "path": str(custom_dir),
    }
    res = client.post("/api/chronoflow/storage/locations", json=create_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    loc_id = data["location"]["id"]
    assert data["location"]["name"] == "Project Cyberpunk"

    # GET locations (enriched with image_count and exists)
    res = client.get("/api/chronoflow/storage/locations")
    assert res.status_code == 200
    locs = res.json()["locations"]
    assert len(locs) == 1
    assert locs[0]["id"] == loc_id
    assert locs[0]["exists"] is True
    assert locs[0]["image_count"] == 0

    # Browse storage directory
    browse_res = client.get(f"/api/chronoflow/storage/browse?path={custom_dir}")
    assert browse_res.status_code == 200
    assert browse_res.json()["current"] == str(custom_dir)
    assert browse_res.json()["not_found"] is False

    # Browse non-existent child path falls back to parent with not_found=True
    non_existent = custom_dir / "does_not_exist_yet"
    browse_non_ex = client.get(f"/api/chronoflow/storage/browse?path={non_existent}")
    assert browse_non_ex.status_code == 200
    b_data = browse_non_ex.json()
    assert b_data["current"] == str(custom_dir)
    assert b_data["not_found"] is True
    assert b_data["can_create"] is True
    assert b_data["requested_path"] == str(non_existent)

    # Test mkdir endpoint
    mkdir_res = client.post("/api/chronoflow/storage/mkdir", json={"path": str(non_existent)})
    assert mkdir_res.status_code == 200
    assert mkdir_res.json()["success"] is True
    assert non_existent.exists() and non_existent.is_dir()

    # Save asset to location
    test_img = tmp_path / "input" / "art_test_123.png"
    test_img.write_bytes(b"fake-png-data")

    save_payload = {
        "filenames": ["art_test_123.png"],
        "location_id": loc_id,
        "action": "copy",
    }
    res = client.post("/api/chronoflow/storage/save_asset", json=save_payload)
    assert res.status_code == 200
    save_data = res.json()
    assert save_data["success"] is True
    assert len(save_data["results"]) == 1
    assert save_data["results"][0]["success"] is True
    assert (custom_dir / "art_test_123.png").exists()

    # Verify image count updated
    res = client.get("/api/chronoflow/storage/locations")
    assert res.json()["locations"][0]["image_count"] == 1

    # Verify gallery includes location and image
    monkeypatch.setattr(chronoflow, "STUDIO_OUTPUT_DIR", tmp_path / "output")
    (tmp_path / "output").mkdir()
    gal_res = client.get("/api/chronoflow/gallery")
    assert gal_res.status_code == 200
    gal_data = gal_res.json()
    assert "locations" in gal_data
    assert any(img.get("location_id") == loc_id for img in gal_data["images"])

    # DELETE location
    del_res = client.delete(f"/api/chronoflow/storage/locations/{loc_id}")
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True

    # Confirm removed
    res = client.get("/api/chronoflow/storage/locations")
    assert res.json()["locations"] == []


def test_api_generate_image_with_custom_location(client, tmp_path, monkeypatch):
    custom_dest = tmp_path / "MyProjectImages"
    custom_dest.mkdir()

    loc_file = tmp_path / "storage_locations.json"
    monkeypatch.setattr(chronoflow, "STORAGE_LOCATIONS_FILE", loc_file)
    monkeypatch.setattr(chronoflow, "COMFY_INPUT_DIR", tmp_path / "input")
    (tmp_path / "input").mkdir()

    loc_res = client.post("/api/chronoflow/storage/locations", json={"name": "Story 1", "path": str(custom_dest)})
    loc_id = loc_res.json()["location"]["id"]

    # Mock pipeline.generate_art_image_ex to create a file in input dir
    async def fake_gen(*args, **kwargs):
        test_fn = "art_mock_777.png"
        (tmp_path / "input" / test_fn).write_bytes(b"image-data-bytes")
        return test_fn, None

    monkeypatch.setattr(chronoflow.pipeline, "generate_art_image_ex", fake_gen)

    gen_payload = {
        "prompt": "Test prompt",
        "location_id": loc_id,
    }
    res = client.post("/api/chronoflow/generate_image", json=gen_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "saved_location" in data
    assert (custom_dest / "art_mock_777.png").exists()
    assert (custom_dest / "art_mock_777.png").read_bytes() == b"image-data-bytes"


def test_api_screenplay_folders_and_export(client, tmp_path, monkeypatch):
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    monkeypatch.setattr(chronoflow, "VAULT_DIR", vault_dir)
    monkeypatch.setattr(chronoflow, "COMFY_INPUT_DIR", tmp_path / "input")
    monkeypatch.setattr(chronoflow, "STUDIO_OUTPUT_DIR", tmp_path / "output")
    (tmp_path / "input").mkdir()
    (tmp_path / "output").mkdir()

    # Create dummy keyframe
    (tmp_path / "input" / "shot_1_keyframe.png").write_bytes(b"keyframe-bytes")

    # 1. Save screenplay with folders
    save_payload = {
        "title": "Epic Cyberpunk Odyssey",
        "duration": 20.8,
        "protagonist": {"name": "Maya"},
        "folders": [
            {
                "id": "scene_1",
                "name": "Scene 1: Infiltration",
                "description": "Maya penetrates security.",
                "shot_indices": [1, 2],
                "path": str(tmp_path / "ExportedScene1")
            }
        ],
        "scenes": [
            {
                "shot_index": 1,
                "folder_id": "scene_1",
                "title": "Shot 1: The Gate",
                "first_frame": "shot_1_keyframe.png",
                "duration": 5.2,
                "prompt": "summary: Maya stands at the gate."
            },
            {
                "shot_index": 2,
                "folder_id": "scene_1",
                "title": "Shot 2: The Hallway",
                "duration": 5.2,
                "prompt": "summary: Maya slips through the corridor."
            }
        ]
    }
    save_res = client.post("/api/chronoflow/screenplay/save", json=save_payload)
    assert save_res.status_code == 200
    save_data = save_res.json()
    assert save_data["success"] is True
    saved_fn = save_data["filename"]

    # 2. Get screenplay and verify folders are retrieved
    get_res = client.get(f"/api/chronoflow/screenplay/{saved_fn}")
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert "folders" in get_data
    assert len(get_data["folders"]) == 1
    assert get_data["folders"][0]["name"] == "Scene 1: Infiltration"
    assert get_data["scenes"][0]["folder_id"] == "scene_1"

    # 3. Export Scene 1 to disk
    export_dir = tmp_path / "ExportedScene1"
    export_payload = {
        "destination_path": str(export_dir),
        "folder_id": "scene_1",
        "folder_name": "Scene 1: Infiltration",
        "screenplay_title": "Epic Cyberpunk Odyssey",
        "scenes": get_data["scenes"]
    }
    exp_res = client.post("/api/chronoflow/storyboard/export_folder", json=export_payload)
    assert exp_res.status_code == 200
    exp_data = exp_res.json()
    assert exp_data["success"] is True
    assert exp_data["shots_count"] == 2
    assert exp_data["files_copied"] == 1

    # Verify destination files
    assert export_dir.exists()
    assert (export_dir / "scene_manifest.json").exists()
    assert (export_dir / "keyframes" / "shot_1_shot_1_keyframe.png").exists()

    manifest_json = json.loads((export_dir / "scene_manifest.json").read_text(encoding="utf-8"))
    assert manifest_json["scene_name"] == "Scene 1: Infiltration"
    assert manifest_json["total_shots"] == 2
    assert len(manifest_json["shots"]) == 2


def test_import_scene_to_studio(client):
    """Test importing a scene folder with shots directly into Video Studio as an active job."""
    payload = {
        "folder_name": "Scene 1: Infiltration",
        "folder_id": "scene_1",
        "screenplay_title": "Epic Cyberpunk Odyssey",
        "shots": [
            {
                "shot_index": 1,
                "title": "Shot 1: The Breach",
                "prompt": "Cinematic breach",
                "duration": 5.2,
                "rendered_video": "/outputs/test_chunk_1.mp4",
            },
            {
                "shot_index": 2,
                "title": "Shot 2: Hallway Sweep",
                "prompt": "Cinematic hallway",
                "duration": 5.2,
                "rendered_video": "/outputs/test_chunk_2.mp4",
            },
            {
                "shot_index": 3,
                "title": "Shot 3: Cyber Terminal",
                "prompt": "Cinematic terminal",
                "duration": 5.2,
                "rendered_video": None,
            },
        ],
    }
    res = client.post("/api/chronoflow/storyboard/import_scene_to_studio", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    job_id = data["job_id"]
    assert job_id.startswith("scene_")
    assert data["chunks_count"] == 2
    assert data["shots_count"] == 3
    assert data["job"]["status"] == "completed_chunks"
    assert len(data["job"]["chunks"]) == 2

    # Verify sync endpoint locks on this job without reverting
    sync_res = client.get(f"/api/chronoflow/sync?job_id={job_id}")
    assert sync_res.status_code == 200
    sync_data = sync_res.json()
    assert sync_data["active_job"]["id"] == job_id
    assert len(sync_data["active_job"]["chunks"]) == 2




