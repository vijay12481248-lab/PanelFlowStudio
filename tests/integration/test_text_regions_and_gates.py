import time
from pathlib import Path
from fastapi.testclient import TestClient

from engine.api.app import app
from engine.database.session import init_db, SessionLocal
from engine.database.models import OCRCacheRecord, TextRegionRecord

def test_text_regions_lifecycle_and_strict_gate():
    init_db()
    client = TestClient(app)

    fixtures_dir = Path(__file__).parent.parent.parent / "fixtures"
    sample_folder = fixtures_dir / "sample_comic"

    # 1. Create project
    create_resp = client.post(
        "/api/projects",
        json={
            "title": "Text Region & Strict Gate Test",
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

    # 4. Detect text regions
    tr_resp = client.post(f"/api/projects/{project_id}/detect-text-regions")
    assert tr_resp.status_code == 200
    regions = tr_resp.json()
    assert len(regions) >= len(panels)  # Every panel yields at least fallback or balloon regions

    # Verify fields on first region
    first_tr = regions[0]
    assert "id" in first_tr
    assert "panel_id" in first_tr
    assert "sequence_global" in first_tr
    assert "normalized_x" in first_tr
    assert "image_url" in first_tr

    # 5. List text regions with filtering
    panel_id = first_tr["panel_id"]
    panel_regions_resp = client.get(f"/api/projects/{project_id}/text-regions?panel_id={panel_id}")
    assert panel_regions_resp.status_code == 200
    assert len(panel_regions_resp.json()) >= 1

    # 6. Extract OCR for a single region (Layer 1 test & Deterministic Cache)
    region_id = first_tr["id"]
    ocr_tr_resp = client.post(
        f"/api/projects/{project_id}/text-regions/{region_id}/ocr",
        json={"engine_id": "mock_ocr", "language": "en"},
    )
    assert ocr_tr_resp.status_code == 200
    ocr_res = ocr_tr_resp.json()
    assert ocr_res["raw_text"] is not None
    assert ocr_res["ocr_engine"] == "mock_ocr"
    assert ocr_res["corrected_text"] == ocr_res["raw_text"]  # initially unedited

    # Verify deterministic cache entry was created
    with SessionLocal() as db:
        cache_entry = db.query(OCRCacheRecord).filter(OCRCacheRecord.crop_sha256 == ocr_res["crop_sha256"]).first()
        assert cache_entry is not None
        assert cache_entry.raw_text == ocr_res["raw_text"]
        initial_created_at = cache_entry.created_at

    # Call OCR extraction again - should hit deterministic cache
    ocr_tr_resp2 = client.post(
        f"/api/projects/{project_id}/text-regions/{region_id}/ocr",
        json={"engine_id": "mock_ocr", "language": "en"},
    )
    assert ocr_tr_resp2.status_code == 200
    assert ocr_tr_resp2.json()["raw_text"] == ocr_res["raw_text"]

    # 7. Strict Approval Gate Failure Test (Part 11)
    # Set a region to status NEEDS_REVIEW
    client.put(
        f"/api/projects/{project_id}/text-regions/{region_id}",
        json={"status": "NEEDS_REVIEW"},
    )

    confirm_fail_resp = client.post(f"/api/projects/{project_id}/ocr/confirm")
    assert confirm_fail_resp.status_code == 400
    assert "NEEDS_REVIEW" in confirm_fail_resp.json()["detail"]

    # 8. Human Correction & Status Resolution (Part 9 & Part 11)
    # Layer 2: Human correction of OCR errors only, preserving source wording & meaning
    faithful_correction = ocr_res["raw_text"].replace("0", "O")
    update_tr_resp = client.put(
        f"/api/projects/{project_id}/text-regions/{region_id}",
        json={
            "status": "CONFIRMED",
            "corrected_text": faithful_correction,
            "corrected_by": "HUMAN_OPERATOR",
            "correction_status": "EDITED",
            "speaker_character_id": "char_navigator_01",
            "speaker_confidence": 0.95,
            "speaker_assignment_method": "RULE_TAIL",
        },
    )
    assert update_tr_resp.status_code == 200
    updated_tr = update_tr_resp.json()
    assert updated_tr["status"] == "CONFIRMED"
    assert updated_tr["corrected_text"] == faithful_correction
    assert updated_tr["raw_text"] == ocr_res["raw_text"]  # Layer 1 raw OCR is preserved intact!
    assert updated_tr["speaker_character_id"] == "char_navigator_01"

    # Make sure all other regions in project are CONFIRMED
    all_regs = client.get(f"/api/projects/{project_id}/text-regions").json()
    for reg in all_regs:
        if reg["status"] == "NEEDS_REVIEW":
            client.put(f"/api/projects/{project_id}/text-regions/{reg['id']}", json={"status": "CONFIRMED"})

    # 9. Strict Approval Gate Resolution (Part 11)
    confirm_success_resp = client.post(f"/api/projects/{project_id}/ocr/confirm")
    assert confirm_success_resp.status_code == 200
    assert confirm_success_resp.json()["current_stage"] == "OCR_APPROVED"

    # 10. Canonical Downstream M4 Export Contract (Part 12)
    contract_resp = client.get(f"/api/projects/{project_id}/export/contract")
    assert contract_resp.status_code == 200
    contract = contract_resp.json()

    assert contract["project_id"] == project_id
    assert contract["current_stage"] == "OCR_APPROVED"
    assert "rights" in contract
    assert len(contract["pages"]) >= 1
    assert len(contract["panels"]) >= 4
    assert len(contract["text_regions"]) >= 1

    # Verify text region 3-layer architecture in export
    target_export_tr = next(tr for tr in contract["text_regions"] if tr["id"] == region_id)
    assert target_export_tr["raw_ocr"]["text"] == ocr_res["raw_text"]
    assert target_export_tr["corrected_text"]["text"] == faithful_correction
    assert target_export_tr["corrected_text"]["corrected_by"] == "HUMAN_OPERATOR"
    assert target_export_tr["speaker"]["character_id"] == "char_navigator_01"
