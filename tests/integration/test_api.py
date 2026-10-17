import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from engine.api.app import app
from engine.config.settings import settings
from engine.database.session import init_db
from tests.fixtures.helpers import create_test_image_bytes

@pytest.fixture(autouse=True)
def setup_api_env(tmp_path: Path, monkeypatch):
    from engine.database.models import Base
    from engine.database.session import engine
    test_ws = tmp_path / "workspaces"
    monkeypatch.setattr(settings, "workspace_root", test_ws)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

def test_full_api_workflow(tmp_path: Path):
    client = TestClient(app)

    # 1. Create temporary source images
    source_dir = tmp_path / "my_comic"
    source_dir.mkdir()
    (source_dir / "01.jpg").write_bytes(create_test_image_bytes(100, 200, "red"))
    (source_dir / "02.jpg").write_bytes(create_test_image_bytes(100, 200, "blue"))

    # 2. Test project creation
    create_payload = {
        "title": "My Test Comic",
        "source_type": "LOCAL_FOLDER",
        "source_url": str(source_dir),
        "rights_status": "PUBLIC_DOMAIN",
        "license_info": "Public Domain Mark 1.0",
        "settings": {"reading_mode": "webtoon"},
    }
    resp = client.post("/api/projects", json=create_payload)
    assert resp.status_code == 201
    proj_data = resp.json()
    project_id = proj_data["id"]
    assert proj_data["title"] == "My Test Comic"
    assert proj_data["rights_status"] == "PUBLIC_DOMAIN"

    # 3. Test source inspection endpoint
    inspect_resp = client.post("/api/adapters/inspect", json={"source": str(source_dir)})
    assert inspect_resp.status_code == 200
    inspect_data = inspect_resp.json()
    assert inspect_data["is_valid"] is True
    assert inspect_data["total_pages_detected"] == 2

    # 4. Trigger acquisition job
    acquire_resp = client.post(f"/api/projects/{project_id}/acquire")
    assert acquire_resp.status_code == 200
    job_id = acquire_resp.json()["job_id"]
    assert job_id

    # Wait briefly or poll job status
    import time
    for _ in range(20):
        job_check = client.get(f"/api/jobs/{job_id}").json()
        if job_check["status"] in ("SUCCEEDED", "FAILED"):
            break
        time.sleep(0.1)

    assert job_check["status"] == "SUCCEEDED"

    # 5. List acquired pages
    pages_resp = client.get(f"/api/projects/{project_id}/pages")
    assert pages_resp.status_code == 200
    pages = pages_resp.json()
    assert len(pages) == 2
    assert pages[0]["sequence"] == 1
    assert pages[1]["sequence"] == 2
    page1_id = pages[0]["id"]
    page2_id = pages[1]["id"]

    # 6. Test reordering pages
    reorder_resp = client.post(
        f"/api/projects/{project_id}/pages/reorder",
        json={"page_ids": [page2_id, page1_id]}
    )
    assert reorder_resp.status_code == 200
    reordered_pages = reorder_resp.json()
    assert reordered_pages[0]["id"] == page2_id
    assert reordered_pages[0]["sequence"] == 1
    assert reordered_pages[1]["id"] == page1_id
    assert reordered_pages[1]["sequence"] == 2

    # 7. Test rotating page 90 degrees
    rotate_resp = client.post(
        f"/api/projects/{project_id}/pages/{page2_id}/rotate",
        json={"degrees": 90}
    )
    assert rotate_resp.status_code == 200
    rot_data = rotate_resp.json()
    # Width was 100, height was 200 -> after 90 deg rotation, width=200, height=100
    assert rot_data["width"] == 200
    assert rot_data["height"] == 100

    # 8. Test deleting page
    del_resp = client.delete(f"/api/projects/{project_id}/pages/{page1_id}")
    assert del_resp.status_code == 204

    # Verify remaining page resequenced to 1
    pages_after_del = client.get(f"/api/projects/{project_id}/pages").json()
    assert len(pages_after_del) == 1
    assert pages_after_del[0]["sequence"] == 1

    # 9. Test manifest endpoint
    manifest_resp = client.get(f"/api/projects/{project_id}/manifest")
    assert manifest_resp.status_code == 200
    manifest_data = manifest_resp.json()
    assert len(manifest_data["pages"]) == 1

    # 10. Confirm acquisition
    confirm_resp = client.post(f"/api/projects/{project_id}/confirm")
    assert confirm_resp.status_code == 200
    assert confirm_resp.json()["current_stage"] == "ACQUIRED"
