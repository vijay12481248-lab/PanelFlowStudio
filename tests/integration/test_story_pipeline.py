import time
from pathlib import Path
from fastapi.testclient import TestClient

from engine.api.app import app
from engine.database.session import init_db, SessionLocal
from engine.database.models import CharacterRecord, utc_now


def test_story_and_script_full_lifecycle():
    init_db()
    client = TestClient(app)

    fixtures_dir = Path(__file__).parent.parent.parent / "fixtures"
    sample_folder = fixtures_dir / "sample_comic"

    # 1. Create project
    create_resp = client.post(
        "/api/projects",
        json={
            "title": "Story & Script Lifecycle E2E Test",
            "source_type": "LOCAL_FOLDER",
            "source_url": str(sample_folder.resolve()),
            "rights_status": "PUBLIC_DOMAIN",
            "license_info": "Public Domain Mark 1.0",
        },
    )
    assert create_resp.status_code == 201
    project_id = create_resp.json()["id"]

    # Gate check: analyzing story before OCR_APPROVED must fail
    premature_story_resp = client.post(
        f"/api/projects/{project_id}/story/analyze",
        json={"provider_id": "mock"},
    )
    assert premature_story_resp.status_code == 400
    assert "OCR_APPROVED" in premature_story_resp.json()["detail"]

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

    # 3. Detect panels & confirm
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

    confirm_panels_resp = client.post(f"/api/projects/{project_id}/panels/confirm")
    assert confirm_panels_resp.status_code == 200

    # 4. Detect text regions
    tr_resp = client.post(f"/api/projects/{project_id}/detect-text-regions")
    assert tr_resp.status_code == 200
    regions = tr_resp.json()
    assert len(regions) >= 4

    # Run OCR and confirm all regions
    for reg in regions:
        client.post(
            f"/api/projects/{project_id}/text-regions/{reg['id']}/ocr",
            json={"engine_id": "mock_ocr", "language": "en"},
        )
        client.put(
            f"/api/projects/{project_id}/text-regions/{reg['id']}",
            json={
                "status": "CONFIRMED",
                "corrected_text": "Sample dialogue line for narrative analysis.",
                "speaker_character_id": "char_hero",
            },
        )

    # Approve OCR
    ocr_confirm_resp = client.post(f"/api/projects/{project_id}/ocr/confirm")
    assert ocr_confirm_resp.status_code == 200
    assert ocr_confirm_resp.json()["current_stage"] == "OCR_APPROVED"

    # 5. Trigger Story Analysis
    story_job_resp = client.post(
        f"/api/projects/{project_id}/story/analyze",
        json={"provider_id": "mock"},
    )
    assert story_job_resp.status_code == 200
    job_id = story_job_resp.json()["job_id"]
    assert job_id is not None

    # Wait for story analysis job to complete
    for _ in range(40):
        job_stat = client.get(f"/api/jobs/{job_id}").json()
        if job_stat["status"] in ("SUCCEEDED", "FAILED"):
            break
        time.sleep(0.1)
    assert job_stat["status"] == "SUCCEEDED"

    # 6. Retrieve Narrative Document
    narr_resp = client.get(f"/api/projects/{project_id}/narrative")
    assert narr_resp.status_code == 200
    narrative = narr_resp.json()
    assert narrative["project_id"] == project_id
    assert len(narrative["characters"]) >= 1
    assert len(narrative["scenes"]) >= 1
    assert len(narrative["utterances"]) >= 1

    hero_char = narrative["characters"][0]
    hero_id = hero_char["character_id"]
    assert hero_id is not None

    # 7. Character Management (List, Update)
    chars_resp = client.get(f"/api/projects/{project_id}/characters")
    assert chars_resp.status_code == 200
    chars = chars_resp.json()
    assert len(chars) >= 1

    # Update character
    update_char_resp = client.put(
        f"/api/projects/{project_id}/characters/{hero_id}",
        json={
            "display_name": "Valerian",
            "canonical_name": "Valerian",
            "role": "PROTAGONIST",
            "status": "CONFIRMED",
            "aliases": ["Val", "Explorer"],
        },
    )
    assert update_char_resp.status_code == 200
    assert update_char_resp.json()["canonical_name"] == "Valerian"

    # Insert a secondary character into DB to test merge
    with SessionLocal() as db:
        dup_char = CharacterRecord(
            id="char_temp_dup",
            project_id=project_id,
            display_name="Valerian Shadow",
            canonical_name="Valerian Shadow",
            aliases=["The Shadow"],
            description="Duplicate record for merge testing",
            role="SUPPORTING",
            status="LIKELY",
            manual_override=False,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db.add(dup_char)
        db.commit()

    # Merge characters
    merge_resp = client.post(
        f"/api/projects/{project_id}/characters/merge",
        json={
            "source_character_id": "char_temp_dup",
            "target_character_id": hero_id,
        },
    )
    assert merge_resp.status_code == 200
    merged_data = merge_resp.json()
    assert merged_data["id"] == hero_id
    assert "The Shadow" in merged_data["aliases"] or "Valerian Shadow" in merged_data["aliases"]

    # Split character test
    first_panel_id = narrative["scenes"][0]["panel_start"]
    split_resp = client.post(
        f"/api/projects/{project_id}/characters/{hero_id}/split",
        json={
            "new_name": "Aria",
            "panel_ids": [first_panel_id],
        },
    )
    assert split_resp.status_code == 200
    split_char = split_resp.json()
    assert split_char["display_name"] == "Aria"

    # 8. Scene Management (List, Merge if >= 2 scenes exist, or verify scenes)
    scenes_resp = client.get(f"/api/projects/{project_id}/scenes")
    assert scenes_resp.status_code == 200
    scenes = scenes_resp.json()
    assert len(scenes) >= 1

    # 9. Story Confirmation Gate
    confirm_story_resp = client.post(f"/api/projects/{project_id}/story/confirm")
    assert confirm_story_resp.status_code == 200
    assert confirm_story_resp.json()["current_stage"] == "STORY_APPROVED"

    # 10. Script Generation (Layer C)
    gen_script_resp = client.post(
        f"/api/projects/{project_id}/scripts/generate",
        json={"adaptation_profile": "FAITHFUL"},
    )
    assert gen_script_resp.status_code == 200
    script = gen_script_resp.json()
    assert script["project_id"] == project_id
    assert script["adaptation_profile"] == "FAITHFUL"
    assert len(script["segments"]) >= 1
    script_id = script["script_id"]

    # 11. Script Retrieval & Segment Update
    get_script_resp = client.get(f"/api/projects/{project_id}/scripts")
    assert get_script_resp.status_code == 200
    active_script = get_script_resp.json()
    assert active_script["script_id"] == script_id

    first_segment = script["segments"][0]
    segment_id = first_segment["segment_id"]

    grounded_text = first_segment.get("text", "Sample dialogue line for narrative analysis.")
    update_seg_resp = client.put(
        f"/api/projects/{project_id}/scripts/{script_id}/segments/{segment_id}",
        json={
            "text": grounded_text,
            "emotion": "DETERMINED",
            "intensity": 0.8,
        },
    )
    assert update_seg_resp.status_code == 200
    updated_seg = update_seg_resp.json()
    assert updated_seg["text"] == grounded_text
    assert updated_seg["manual_override"] is True

    # 12. Script Validation
    val_resp = client.post(f"/api/projects/{project_id}/scripts/{script_id}/validate")
    assert val_resp.status_code == 200, f"Validation failed: {val_resp.json()}"
    val_report = val_resp.json()
    assert val_report["script_id"] == script_id
    assert "supported_segments" in val_report
    assert val_report["supported_segments"] >= 1

    # 13. Script Approval Gate
    approve_script_resp = client.post(f"/api/projects/{project_id}/scripts/{script_id}/approve")
    assert approve_script_resp.status_code == 200
    assert approve_script_resp.json()["status"] == "APPROVED"

    # 14. Verify v1 Non-Goals (Strict Guardrails: No YouTube publishing, No cloud rendering)
    yt_resp = client.post(f"/api/projects/{project_id}/publish/youtube", json={})
    assert yt_resp.status_code in (404, 405)

    cloud_resp = client.post(f"/api/projects/{project_id}/cloud/render", json={})
    assert cloud_resp.status_code in (404, 405)
