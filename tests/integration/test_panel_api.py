import time
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from engine.api.app import app
from engine.config.settings import settings
from engine.database.models import Base
from engine.database.session import engine
from tests.fixtures.helpers import create_test_image_bytes

@pytest.fixture(autouse=True)
def setup_api_env(tmp_path: Path, monkeypatch):
    test_ws = tmp_path / "workspaces"
    monkeypatch.setattr(settings, "workspace_root", test_ws)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

def test_normalization_and_panel_api_workflow(tmp_path: Path):
    client = TestClient(app)

    # 1. Setup sample project with a comic page
    sample_page = Path(__file__).parent.parent.parent / "fixtures" / "sample_comic" / "page_01.jpg"
    assert sample_page.exists()

    source_dir = tmp_path / "test_comic_src"
    source_dir.mkdir()
    (source_dir / "01.jpg").write_bytes(sample_page.read_bytes())

    # Create project & acquire
    proj = client.post("/api/projects", json={
        "title": "Panel Test Project",
        "source_type": "LOCAL_FOLDER",
        "source_url": str(source_dir),
        "rights_status": "PUBLIC_DOMAIN",
    }).json()
    project_id = proj["id"]

    acq_job = client.post(f"/api/projects/{project_id}/acquire").json()
    for _ in range(20):
        j = client.get(f"/api/jobs/{acq_job['job_id']}").json()
        if j["status"] in ("SUCCEEDED", "FAILED"):
            break
        time.sleep(0.1)
    assert j["status"] == "SUCCEEDED"

    pages = client.get(f"/api/projects/{project_id}/pages").json()
    assert len(pages) == 1
    page1_id = pages[0]["id"]

    # 2. Test Normalization
    norm_resp = client.post(f"/api/projects/{project_id}/normalize", json={"target_width": 1920})
    assert norm_resp.status_code == 200
    norm_job_id = norm_resp.json()["job_id"]

    for _ in range(20):
        j = client.get(f"/api/jobs/{norm_job_id}").json()
        if j["status"] in ("SUCCEEDED", "FAILED"):
            break
        time.sleep(0.1)
    assert j["status"] == "SUCCEEDED"

    # Verify normalized file endpoint
    norm_file_resp = client.get(f"/api/projects/{project_id}/pages/{page1_id}/normalized-file")
    assert norm_file_resp.status_code == 200
    assert norm_file_resp.headers["content-type"] == "image/jpeg"

    # 3. Test Panel Detection
    detect_resp = client.post(f"/api/projects/{project_id}/detect-panels", json={"reading_direction": "ltr"})
    assert detect_resp.status_code == 200
    detect_job_id = detect_resp.json()["job_id"]

    for _ in range(20):
        j = client.get(f"/api/jobs/{detect_job_id}").json()
        if j["status"] in ("SUCCEEDED", "FAILED"):
            break
        time.sleep(0.1)
    assert j["status"] == "SUCCEEDED"

    # 4. List Detected Panels
    panels_resp = client.get(f"/api/projects/{project_id}/panels")
    assert panels_resp.status_code == 200
    panels = panels_resp.json()
    assert len(panels) >= 3
    print(f"Detected {len(panels)} panels via API")

    # Verify panel crop file serving
    crop_resp = client.get(f"/api/projects/{project_id}/panels/{panels[0]['id']}/file")
    assert crop_resp.status_code == 200
    assert crop_resp.headers["content-type"] == "image/jpeg"

    # 5. Add Manual Panel
    add_resp = client.post(f"/api/projects/{project_id}/panels", json={
        "page_id": page1_id,
        "x": 100,
        "y": 100,
        "width": 300,
        "height": 200,
    })
    assert add_resp.status_code == 201
    manual_panel = add_resp.json()
    assert manual_panel["status"] == "MANUAL"
    assert manual_panel["width"] == 300

    # 6. Update Panel Box
    update_resp = client.put(f"/api/projects/{project_id}/panels/{manual_panel['id']}", json={
        "x": 120,
        "y": 120,
        "width": 350,
        "height": 220,
    })
    assert update_resp.status_code == 200
    assert update_resp.json()["width"] == 350

    # 7. Delete Panel
    del_resp = client.delete(f"/api/projects/{project_id}/panels/{manual_panel['id']}")
    assert del_resp.status_code == 204

    # 8. Confirm Panels
    confirm_resp = client.post(f"/api/projects/{project_id}/panels/confirm")
    assert confirm_resp.status_code == 200
    assert confirm_resp.json()["current_stage"] == "PANELS_DETECTED"
