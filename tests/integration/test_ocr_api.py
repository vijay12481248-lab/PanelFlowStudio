import time
from pathlib import Path
from fastapi.testclient import TestClient

from engine.api.app import app
from engine.database.session import init_db

def test_full_ocr_workflow():
    init_db()
    client = TestClient(app)

    fixtures_dir = Path(__file__).parent.parent.parent / "fixtures"
    sample_folder = fixtures_dir / "sample_comic"

    # 1. Create project
    create_resp = client.post(
        "/api/projects",
        json={
            "title": "OCR Test Project",
            "source_type": "LOCAL_FOLDER",
            "source_url": str(sample_folder.resolve()),
            "rights_status": "PUBLIC_DOMAIN",
            "license_info": "Public Domain Mark 1.0",
        },
    )
    assert create_resp.status_code == 201
    project_id = create_resp.json()["id"]

    # 2. Acquire pages
    acq_resp = client.post(f"/api/projects/{project_id}/acquire")
    assert acq_resp.status_code == 200
    acq_job_id = acq_resp.json()["job_id"]
    for _ in range(30):
        j = client.get(f"/api/jobs/{acq_job_id}").json()
        if j["status"] in ("SUCCEEDED", "FAILED"):
            break
        time.sleep(0.1)
    assert j["status"] == "SUCCEEDED"

    # 3. Detect panels
    detect_resp = client.post(
        f"/api/projects/{project_id}/detect-panels",
        json={"reading_direction": "ltr", "min_area_ratio": 0.02},
    )
    assert detect_resp.status_code == 200
    detect_job_id = detect_resp.json()["job_id"]
    for _ in range(30):
        j = client.get(f"/api/jobs/{detect_job_id}").json()
        if j["status"] in ("SUCCEEDED", "FAILED"):
            break
        time.sleep(0.1)
    assert j["status"] == "SUCCEEDED"

    panels = client.get(f"/api/projects/{project_id}/panels").json()
    assert len(panels) >= 4

    # 4. Check available OCR engines
    engines_resp = client.get("/api/ocr/engines")
    assert engines_resp.status_code == 200
    engines = engines_resp.json()
    engine_ids = [e["engine_id"] for e in engines]
    assert "mock_ocr" in engine_ids

    # 5. Trigger OCR extraction using mock engine
    ocr_extract_resp = client.post(
        f"/api/projects/{project_id}/ocr/extract",
        json={"engine_id": "mock_ocr", "language": "en"},
    )
    assert ocr_extract_resp.status_code == 200
    ocr_job_id = ocr_extract_resp.json()["job_id"]

    for _ in range(30):
        j = client.get(f"/api/jobs/{ocr_job_id}").json()
        if j["status"] in ("SUCCEEDED", "FAILED"):
            break
        time.sleep(0.1)
    assert j["status"] == "SUCCEEDED"

    # 6. List and inspect OCR records
    ocr_list_resp = client.get(f"/api/projects/{project_id}/ocr")
    assert ocr_list_resp.status_code == 200
    ocr_records = ocr_list_resp.json()
    assert len(ocr_records) == len(panels)

    first_ocr = ocr_records[0]
    panel_id = first_ocr["panel_id"]
    assert len(first_ocr["raw_blocks"]) >= 1
    assert len(first_ocr["adapted_blocks"]) >= 1

    first_raw = first_ocr["raw_blocks"][0]
    raw_text = first_raw["detected_text"]
    block_id = first_raw["id"]

    # 7. Update adapted block (downstream text editing without mutating raw OCR)
    # Layer 2: Faithful error correction preserving source words
    corrected_text = raw_text.replace("0", "O")
    update_block_resp = client.put(
        f"/api/projects/{project_id}/panels/{panel_id}/ocr/blocks/{block_id}",
        json={
            "speaker": "Commander Alpha",
            "text": corrected_text,
            "classification": "dialogue",
            "notes": "Faithful typo correction preserving source words",
        },
    )
    assert update_block_resp.status_code == 200
    updated_ocr = update_block_resp.json()

    # Raw block must be unchanged!
    assert updated_ocr["raw_blocks"][0]["detected_text"] == raw_text
    # Adapted block must contain the edited text and speaker!
    assert updated_ocr["adapted_blocks"][0]["speaker"] == "Commander Alpha"
    assert (
        updated_ocr["adapted_blocks"][0]["text"]
        == corrected_text
    )
    assert updated_ocr["status"] == "EDITED"

    # 8. Confirm OCR
    confirm_ocr_resp = client.post(f"/api/projects/{project_id}/ocr/confirm")
    assert confirm_ocr_resp.status_code == 200
    assert confirm_ocr_resp.json()["current_stage"] == "OCR_APPROVED"

    # Check project stage
    proj_resp = client.get(f"/api/projects/{project_id}").json()
    assert proj_resp["current_stage"] == "OCR_APPROVED"
