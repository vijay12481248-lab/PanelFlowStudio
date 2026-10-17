import time
import httpx
import hashlib
from pathlib import Path
import sys

BASE_URL = "http://127.0.0.1:8765"

def run_e2e_verification():
    sys.path.insert(0, str(Path(__file__).parent.parent))
    client = None
    try:
        live_client = httpx.Client(base_url=BASE_URL, timeout=2.0)
        h = live_client.get("/api/system/health").json()
        if h.get("status") == "healthy":
            client = live_client
            print(f"Connected to live server at {BASE_URL}: {h}")
    except Exception:
        pass

    if client is None:
        from fastapi.testclient import TestClient
        from engine.api.app import app
        from engine.database.session import init_db
        init_db()
        client = TestClient(app)
        print("Using in-process TestClient(app) for E2E verification.")

    print("=== [1] Verifying System Health ===")
    health = client.get("/api/system/health").json()
    assert health["status"] == "healthy"
    print(f"Engine healthy: {health}")

    # Paths to fixtures
    fixtures_dir = Path(__file__).parent.parent / "fixtures"
    sample_folder = fixtures_dir / "sample_comic"
    sample_zip = fixtures_dir / "sample_comic.cbz"

    print("\n=== [2] Testing Source Inspection ===")
    inspect_resp = client.post("/api/adapters/inspect", json={"source": str(sample_folder.resolve())})
    assert inspect_resp.status_code == 200
    inspect_data = inspect_resp.json()
    print(f"Folder inspection result: {inspect_data}")
    assert inspect_data["is_valid"] is True
    assert inspect_data["total_pages_detected"] == 5

    inspect_zip = client.post("/api/adapters/inspect", json={"source": str(sample_zip.resolve())})
    assert inspect_zip.status_code == 200
    assert inspect_zip.json()["is_valid"] is True
    assert inspect_zip.json()["total_pages_detected"] == 5
    print("Zip inspection verified: 5 pages discovered.")

    print("\n=== [3] Testing Rights Enforcement Guard ===")
    res_bad = client.post("/api/projects", json={
        "title": "Bad Rights Project",
        "source_type": "LOCAL_FOLDER",
        "source_url": str(sample_folder.resolve()),
        "rights_status": "UNKNOWN",
    })
    assert res_bad.status_code == 201
    bad_id = res_bad.json()["id"]
    bad_acq = client.post(f"/api/projects/{bad_id}/acquire")
    assert bad_acq.status_code == 400
    print(f"Acquisition correctly blocked for UNKNOWN rights: {bad_acq.json()['detail']}")

    print("\n=== [4] Creating Project with Valid Rights ===")
    create_resp = client.post("/api/projects", json={
        "title": "Captain Cosmos Vol 1",
        "source_type": "LOCAL_FOLDER",
        "source_url": str(sample_folder.resolve()),
        "rights_status": "PUBLIC_DOMAIN",
        "license_info": "Public Domain Mark 1.0 (US 1928)",
    })
    assert create_resp.status_code == 201
    project = create_resp.json()
    project_id = project["id"]
    print(f"Created project ID: {project_id}, Stage: {project['current_stage']}")

    print("\n=== [5] Starting Acquisition Pipeline ===")
    acq_resp = client.post(f"/api/projects/{project_id}/acquire")
    assert acq_resp.status_code == 200
    job_id = acq_resp.json()["job_id"]
    print(f"Acquisition Job ID: {job_id}")

    # Poll until job completes
    print("Watching live job progress...")
    for _ in range(30):
        job = client.get(f"/api/jobs/{job_id}").json()
        print(f"  Progress: {job['progress']*100:.0f}% - Message: {job['message']} (Status: {job['status']})")
        if job["status"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(0.3)

    assert job["status"] == "SUCCEEDED"
    print("Acquisition job succeeded!")

    print("\n=== [5B] Testing Deterministic Job Cancellation (QUEUED -> RUNNING -> CANCELLED) ===")
    cancel_proj_resp = client.post("/api/projects", json={
        "title": "Deterministic Cancellation Test Project",
        "source_type": "LOCAL_FOLDER",
        "source_url": str(sample_folder.resolve()),
        "rights_status": "PUBLIC_DOMAIN",
        "license_info": "Public Domain Mark 1.0",
        "settings": {"simulated_page_delay_sec": 0.25},
    })
    assert cancel_proj_resp.status_code == 201
    cancel_proj_id = cancel_proj_resp.json()["id"]

    acq_cancel_resp = client.post(f"/api/projects/{cancel_proj_id}/acquire")
    assert acq_cancel_resp.status_code == 200
    cancel_job_id = acq_cancel_resp.json()["job_id"]

    # Poll until job enters RUNNING state
    is_running = False
    for _ in range(25):
        j_cancel = client.get(f"/api/jobs/{cancel_job_id}").json()
        if j_cancel["status"] == "RUNNING":
            is_running = True
            break
        time.sleep(0.04)
    assert is_running is True, "Job failed to enter RUNNING state"
    print(f"  Job transitioned to RUNNING state: Progress={j_cancel['progress']*100:.0f}%")

    # Wait until page 1 finishes downloading (page 1 takes ~0.25s)
    time.sleep(0.35)

    # Issue cancellation request while RUNNING
    cancel_req = client.post(f"/api/jobs/{cancel_job_id}/cancel")
    assert cancel_req.status_code == 200
    print(f"  Cancellation requested while RUNNING: {cancel_req.json()}")

    # Wait for job to finalize
    for _ in range(30):
        j_cancel = client.get(f"/api/jobs/{cancel_job_id}").json()
        if j_cancel["status"] in ("CANCELLED", "SUCCEEDED", "FAILED"):
            break
        time.sleep(0.1)

    # Wait for background runner to complete cleanup and database writes
    from engine.jobs.manager import job_manager
    for _ in range(40):
        if not job_manager.is_job_active(cancel_job_id):
            break
        time.sleep(0.05)

    # 1. Assert final status == CANCELLED (Never SUCCEEDED)
    assert j_cancel["status"] == "CANCELLED", f"Job status was {j_cancel['status']}, expected CANCELLED!"
    print(f"  Job status successfully finalized as CANCELLED (Never SUCCEEDED): {j_cancel}")

    # 2. Verify completed work before cancellation remains valid
    cancel_pages = client.get(f"/api/projects/{cancel_proj_id}/pages").json()
    ready_pages = [p for p in cancel_pages if p["status"] == "READY"]
    failed_pages = [p for p in cancel_pages if p["status"] == "FAILED"]
    assert len(ready_pages) >= 1, "Expected at least 1 completed page prior to cancellation"
    print(f"  Completed work preserved: {len(ready_pages)} page(s) READY on disk and in database.")

    # 3. Verify unfinished work is NOT marked successful
    assert len(failed_pages) >= 1, "Expected unfinished pages to not be marked READY"
    for fp in failed_pages:
        assert fp["status"] == "FAILED"
        assert "cancelled" in (fp.get("error_message") or "").lower()
    print(f"  Unfinished work properly marked FAILED with cancellation reason: {len(failed_pages)} page(s).")

    # 4. Verify project current_stage was NOT promoted to ACQUIRED
    cancel_p_rec = client.get(f"/api/projects/{cancel_proj_id}").json()
    assert cancel_p_rec["current_stage"] != "ACQUIRED"
    print(f"  Project current stage preserved safely: {cancel_p_rec['current_stage']} (Not promoted to ACQUIRED).")

    # 5. Verify simulated application restart does not resume the cancelled job
    from engine.jobs.manager import job_manager
    job_manager.recover_interrupted_jobs()
    post_restart_j = client.get(f"/api/jobs/{cancel_job_id}").json()
    assert post_restart_j["status"] == "CANCELLED", "Engine restart mutated or resumed cancelled job!"
    print("  Engine crash recovery verified: CANCELLED job remains CANCELLED across restarts.")

    print("\n=== [6] Listing and Verifying Acquired Pages ===")
    pages = client.get(f"/api/projects/{project_id}/pages").json()
    assert len(pages) == 5
    for p in pages:
        print(f"  Page #{p['sequence']}: {p['filename']} ({p['width']}x{p['height']}) - SHA256: {p['sha256'][:12]}... Status: {p['status']}")
        assert p["status"] == "READY"
        assert p["width"] > 0
        assert p["height"] > 0

        # Verify image serving endpoint
        img_resp = client.get(f"/api/projects/{project_id}/pages/{p['id']}/file")
        assert img_resp.status_code == 200
        assert img_resp.headers["content-type"] == "image/jpeg"

    print("\n=== [7] Testing Page Rotation ===")
    page1 = pages[0]
    orig_w, orig_h = page1["width"], page1["height"]
    rot_resp = client.post(f"/api/projects/{project_id}/pages/{page1['id']}/rotate", json={"degrees": 90})
    assert rot_resp.status_code == 200
    rot_page = rot_resp.json()
    print(f"  Rotated Page 1 90 deg: {orig_w}x{orig_h} -> {rot_page['width']}x{rot_page['height']}")
    assert rot_page["width"] == orig_h
    assert rot_page["height"] == orig_w

    print("\n=== [8] Testing Page Reordering ===")
    # Swap page 1 and page 2
    new_order = [pages[1]["id"], pages[0]["id"], pages[2]["id"], pages[3]["id"], pages[4]["id"]]
    reorder_resp = client.post(f"/api/projects/{project_id}/pages/reorder", json={"page_ids": new_order})
    assert reorder_resp.status_code == 200
    reordered = reorder_resp.json()
    assert reordered[0]["id"] == pages[1]["id"]
    assert reordered[0]["sequence"] == 1
    assert reordered[1]["id"] == pages[0]["id"]
    assert reordered[1]["sequence"] == 2
    print("  Pages successfully reordered!")

    print("\n=== [9] Testing Page Deletion and Resequencing ===")
    del_page_id = pages[4]["id"] # remove last page
    del_resp = client.delete(f"/api/projects/{project_id}/pages/{del_page_id}")
    assert del_resp.status_code == 204
    remaining = client.get(f"/api/projects/{project_id}/pages").json()
    assert len(remaining) == 4
    for idx, p in enumerate(remaining, start=1):
        assert p["sequence"] == idx
    print(f"  Page deleted. Remaining {len(remaining)} pages resequenced 1..{len(remaining)}.")

    print("\n=== [10] Confirming Acquisition and Verifying Manifest ===")
    conf_resp = client.post(f"/api/projects/{project_id}/confirm")
    assert conf_resp.status_code == 200
    updated_proj = conf_resp.json()
    assert updated_proj["current_stage"] == "ACQUIRED"
    print(f"  Project confirmed. Current Stage: {updated_proj['current_stage']}")

    manifest = client.get(f"/api/projects/{project_id}/manifest").json()
    assert len(manifest["pages"]) == 4
    assert manifest["project_id"] == project_id
    assert manifest["rights"]["status"] == "PUBLIC_DOMAIN"
    print(f"  Canonical manifest verified with {len(manifest['pages'])} pages.")

    # Record baseline source hashes for immutability verification
    workspace_path = Path(updated_proj["workspace_path"])
    source_dir = workspace_path / "source"
    initial_source_hashes = {}
    for sf in sorted(source_dir.glob("page_*.*")):
        initial_source_hashes[sf.name] = hashlib.sha256(sf.read_bytes()).hexdigest()
    print(f"  Recorded baseline SHA-256 for {len(initial_source_hashes)} source files: {list(initial_source_hashes.keys())}")

    print("\n=== [11] Testing ZIP Archive Acquisition ===")
    zip_proj = client.post("/api/projects", json={
        "title": "Captain Cosmos from CBZ",
        "source_type": "ZIP_ARCHIVE",
        "source_url": str(sample_zip.resolve()),
        "rights_status": "CREATIVE_COMMONS",
        "license_info": "CC-BY-4.0",
    }).json()
    zip_job = client.post(f"/api/projects/{zip_proj['id']}/acquire").json()
    for _ in range(30):
        j = client.get(f"/api/jobs/{zip_job['job_id']}").json()
        if j["status"] in ("SUCCEEDED", "FAILED"):
            break
        time.sleep(0.3)
    assert j["status"] == "SUCCEEDED"
    zip_pages = client.get(f"/api/projects/{zip_proj['id']}/pages").json()
    assert len(zip_pages) == 5
    print("  ZIP/CBZ acquisition verified successfully with 5 pages.")

    print("\n=== [12] Testing Job Cancellation ===")
    # Start acquisition on zip again and cancel it immediately
    cancel_proj = client.post("/api/projects", json={
        "title": "To Be Cancelled",
        "source_type": "LOCAL_FOLDER",
        "source_url": str(sample_folder.resolve()),
        "rights_status": "USER_OWNED",
        "license_info": "Original work",
    }).json()
    c_job_id = client.post(f"/api/projects/{cancel_proj['id']}/acquire").json()["job_id"]
    client.post(f"/api/jobs/{c_job_id}/cancel")
    time.sleep(0.5)
    c_status = client.get(f"/api/jobs/{c_job_id}").json()
    print(f"  Cancelled job status: {c_status['status']}")
    assert c_status["status"] in ("CANCELLED", "SUCCEEDED")

    print("\n=== [13] Testing Page Normalization ===")
    norm_resp = client.post(f"/api/projects/{project_id}/normalize", json={"target_width": 1920})
    assert norm_resp.status_code == 200
    norm_job_id = norm_resp.json()["job_id"]
    print(f"  Normalization Job ID: {norm_job_id}")
    for _ in range(30):
        j = client.get(f"/api/jobs/{norm_job_id}").json()
        if j["status"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(0.3)
    assert j["status"] == "SUCCEEDED"
    print("  Normalization completed successfully!")

    # Verify source immutability after normalization
    for sf_name, orig_hash in initial_source_hashes.items():
        curr_hash = hashlib.sha256((source_dir / sf_name).read_bytes()).hexdigest()
        assert curr_hash == orig_hash, f"Source file {sf_name} modified during normalization!"
    print("  Source files verified 100% immutable after normalization.")

    # Verify normalized image endpoint
    norm_img_resp = client.get(f"/api/projects/{project_id}/pages/{remaining[0]['id']}/normalized")
    assert norm_img_resp.status_code == 200
    assert norm_img_resp.headers["content-type"] == "image/jpeg"
    print("  Normalized image endpoint verified.")

    print("\n=== [14] Testing Panel Detection ===")
    detect_resp = client.post(f"/api/projects/{project_id}/detect-panels", json={"reading_direction": "ltr", "min_area_ratio": 0.02})
    assert detect_resp.status_code == 200
    detect_job_id = detect_resp.json()["job_id"]
    print(f"  Panel Detection Job ID: {detect_job_id}")
    for _ in range(30):
        j = client.get(f"/api/jobs/{detect_job_id}").json()
        if j["status"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(0.3)
    assert j["status"] == "SUCCEEDED"

    panels = client.get(f"/api/projects/{project_id}/panels").json()
    print(f"  Detected {len(panels)} panels across project.")
    assert len(panels) >= 4
    for p in panels:
        assert p["width"] > 0
        assert p["height"] > 0
        assert p["reading_direction"] == "ltr"

    print("\n=== [15] Testing Panel Crop Retrieval ===")
    panel1 = panels[0]
    crop_resp = client.get(f"/api/projects/{project_id}/panels/{panel1['id']}/file")
    assert crop_resp.status_code == 200
    assert crop_resp.headers["content-type"] == "image/jpeg"
    print(f"  Panel #1 crop retrieved successfully ({len(crop_resp.content)} bytes).")

    print("\n=== [16] Testing Panel CRUD and Resequencing ===")
    # Add a manual panel
    first_page_id = remaining[0]["id"]
    add_resp = client.post(f"/api/projects/{project_id}/panels", json={
        "page_id": first_page_id,
        "x": 60,
        "y": 60,
        "width": 300,
        "height": 200,
    })
    assert add_resp.status_code == 201
    new_panel = add_resp.json()
    assert new_panel["status"] == "MANUAL"
    print(f"  Manual panel created: ID {new_panel['id']}")

    # Update panel
    update_resp = client.put(f"/api/projects/{project_id}/panels/{new_panel['id']}", json={
        "x": 70,
        "y": 70,
        "width": 320,
        "height": 220,
    })
    assert update_resp.status_code == 200
    assert update_resp.json()["width"] == 320

    # Delete manual panel
    del_p_resp = client.delete(f"/api/projects/{project_id}/panels/{new_panel['id']}")
    assert del_p_resp.status_code == 204
    print("  Manual panel updated and deleted successfully.")

    print("\n=== [17] Confirming Panels and Syncing panels.json ===")
    confirm_p_resp = client.post(f"/api/projects/{project_id}/panels/confirm")
    assert confirm_p_resp.status_code == 200
    confirmed_proj = client.get(f"/api/projects/{project_id}").json()
    assert confirmed_proj["current_stage"] == "PANELS_DETECTED"
    print(f"  Panels confirmed! Current project stage: {confirmed_proj['current_stage']}")

    # Verify source immutability after panel detection
    for sf_name, orig_hash in initial_source_hashes.items():
        curr_hash = hashlib.sha256((source_dir / sf_name).read_bytes()).hexdigest()
        assert curr_hash == orig_hash, f"Source file {sf_name} modified during panel detection!"
    print("  Source files verified 100% immutable after panel detection.")

    print("\n=== [18] Testing OCR Extraction & Normalized Provider Status Semantics ===")
    engines_resp = client.get("/api/ocr/engines")
    assert engines_resp.status_code == 200
    engines = engines_resp.json()
    print("  === OCR Provider Status Matrix ===")
    print(f"  {'Provider ID':<16} | {'Registered':<10} | {'Installed':<10} | {'Configured':<10} | {'Available':<10} | {'Verified':<10} | {'Status Label':<22} | Diagnostic")
    print("  " + "-" * 115)
    for e in engines:
        print(f"  {e['engine_id']:<16} | {str(e.get('registered', True)):<10} | {str(e.get('installed', False)):<10} | {str(e.get('configured', False)):<10} | {str(e.get('is_available', False)):<10} | {str(e.get('is_verified', False)):<10} | {e.get('status_label', ''):<22} | {e.get('diagnostic_message', '')}")

    provider_map = {e["engine_id"]: e for e in engines}
    assert "mock_ocr" in provider_map
    assert provider_map["mock_ocr"]["is_available"] is True
    assert provider_map["mock_ocr"]["status_label"] == "Verified"

    if "windows_media" in provider_map:
        assert provider_map["windows_media"]["is_available"] is True
        print("  Windows Media OCR available and active natively via WinRT.")
        # Execute real OCR benchmark fixture
        from engine.ocr.providers.windows_media_provider import WindowsMediaOCREngine
        wm_engine = WindowsMediaOCREngine()
        benchmark_fixture = fixtures_dir / "ocr_benchmarks" / "en_dialogue_01.jpg"
        if benchmark_fixture.exists():
            wm_res = wm_engine.extract_text(benchmark_fixture, "fixture_panel")
            print(f"  Windows Media OCR real fixture execution: extracted '{wm_res.full_text}' ({len(wm_res.regions)} regions, conf={wm_res.confidence_avg})")
            assert len(wm_res.full_text) > 0
            assert wm_res.regions[0].confidence > 0.0
            wm_engine.set_verified(True)

    for unconfigured_id in ("paddle_ocr", "manga_ocr", "vision_llm"):
        if unconfigured_id in provider_map:
            assert provider_map[unconfigured_id]["status_label"] == "Configuration required", \
                f"Expected '{unconfigured_id}' to have 'Configuration required' label, got '{provider_map[unconfigured_id]['status_label']}'"
            assert provider_map[unconfigured_id]["is_available"] is False, \
                f"Expected '{unconfigured_id}' to not be available in unconfigured state"

    # Run OCR extraction job using mock engine
    ocr_job_resp = client.post(f"/api/projects/{project_id}/ocr/extract", json={"engine_id": "mock_ocr", "language": "en"})
    assert ocr_job_resp.status_code == 200
    ocr_job_id = ocr_job_resp.json()["job_id"]
    print(f"  OCR Extraction Job ID: {ocr_job_id}")

    for _ in range(30):
        j = client.get(f"/api/jobs/{ocr_job_id}").json()
        if j["status"] in ("SUCCEEDED", "FAILED"):
            break
        time.sleep(0.3)
    assert j["status"] == "SUCCEEDED"

    ocr_records = client.get(f"/api/projects/{project_id}/ocr").json()
    print(f"  OCR extracted across {len(ocr_records)} panels.")
    assert len(ocr_records) == len(panels)
    first_ocr = ocr_records[0]
    assert len(first_ocr["raw_blocks"]) >= 1

    print("\n=== [19] Testing Human Text Error Correction & Immutability Guard ===")
    first_raw = first_ocr["raw_blocks"][0]
    raw_text = first_raw["detected_text"]
    block_id = first_raw["id"]

    # Layer 2: Human correction of OCR errors only, preserving source wording & meaning
    # Example: Raw "St0p right therel" -> Corrected "Stop right there!"
    corrected_block_text = raw_text.replace("0", "O")
    edit_resp = client.put(f"/api/projects/{project_id}/panels/{first_ocr['panel_id']}/ocr/blocks/{block_id}", json={
        "speaker": "Commander Alpha",
        "text": corrected_block_text,
        "classification": "dialogue",
        "notes": "Faithful typo correction preserving source words",
    })
    assert edit_resp.status_code == 200
    updated_ocr = edit_resp.json()
    # Raw machine OCR block must remain strictly immutable!
    assert updated_ocr["raw_blocks"][0]["detected_text"] == raw_text
    assert updated_ocr["adapted_blocks"][0]["speaker"] == "Commander Alpha"
    assert updated_ocr["adapted_blocks"][0]["text"] == corrected_block_text
    print("  Human typo correction verified: Layer 1 raw OCR block strictly immutable; Layer 2 corrected text preserved.")

    print("\n=== [20] Testing Canonical Text Region Subsystem & 3-Layer Data Model ===")
    detect_tr_resp = client.post(f"/api/projects/{project_id}/detect-text-regions")
    assert detect_tr_resp.status_code == 200
    text_regions = detect_tr_resp.json()
    assert len(text_regions) >= 1
    print(f"  Detected {len(text_regions)} canonical text regions across panels.")

    first_tr = text_regions[0]
    tr_id = first_tr["id"]
    assert first_tr["panel_id"] is not None
    assert first_tr["region_type"] in ("SPEECH", "NARRATION", "THOUGHT", "SFX", "CAPTION", "UNKNOWN")
    print(f"  Text Region #1: Type={first_tr['region_type']}, Status={first_tr['status']}, Raw OCR='{first_tr.get('raw_text', '')}'")

    # Update Text Region (Human Correction Layer 2 & Speaker Layer 3)
    # Layer 1: Machine OCR provenance (immutable)
    orig_raw_tr = first_tr.get("raw_text", "")
    # Layer 2: Faithful human error correction (fixes typos, preserves source wording and meaning)
    # Not narrative script rewriting
    source_faithful_correction = orig_raw_tr.replace("0", "O") if orig_raw_tr else "Stop right there!"
    tr_update_resp = client.put(f"/api/projects/{project_id}/text-regions/{tr_id}", json={
        "corrected_text": source_faithful_correction,
        "corrected_by": "LEAD_DIRECTOR",
        "correction_status": "VERIFIED",
        "status": "CONFIRMED",
        "speaker_character_id": "char_lumina",
        "speaker_confidence": 0.98,
        "speaker_assignment_method": "RULE_TAIL",
    })
    assert tr_update_resp.status_code == 200
    updated_tr = tr_update_resp.json()
    assert updated_tr["raw_text"] == orig_raw_tr  # Layer 1 untouched machine provenance
    assert updated_tr["corrected_text"] == source_faithful_correction  # Layer 2 faithful error correction
    assert updated_tr["speaker_character_id"] == "char_lumina"  # Layer 3 preparatory speaker
    assert updated_tr["status"] == "CONFIRMED"
    print("  Text Region 3-layer architecture verified: Layer 1 immutable, Layer 2 source-faithful correction, Layer 3 speaker mapped.")

    print("\n=== [21] Testing Strict Approval Gate (Rejection of NEEDS_REVIEW) ===")
    # Temporarily set a text region to NEEDS_REVIEW
    flag_resp = client.put(f"/api/projects/{project_id}/text-regions/{tr_id}", json={
        "status": "NEEDS_REVIEW",
    })
    assert flag_resp.status_code == 200

    # Attempt to confirm OCR -> must be strictly blocked with HTTP 400
    bad_confirm = client.post(f"/api/projects/{project_id}/ocr/confirm")
    assert bad_confirm.status_code == 400
    assert "NEEDS_REVIEW" in bad_confirm.json()["detail"]
    print(f"  Approval gate successfully blocked unreviewed region: {bad_confirm.json()['detail']}")

    # Resolve all text regions to CONFIRMED and approve
    for r in text_regions:
        client.put(f"/api/projects/{project_id}/text-regions/{r['id']}", json={
            "status": "CONFIRMED",
            "corrected_text": r.get("corrected_text") or "Dialogue line",
        })
    conf_ocr = client.post(f"/api/projects/{project_id}/ocr/confirm")
    assert conf_ocr.status_code == 200
    p_final = client.get(f"/api/projects/{project_id}").json()
    assert p_final["current_stage"] == "OCR_APPROVED"
    print(f"  All regions confirmed! Current project stage: {p_final['current_stage']}")

    print("\n=== [22] Testing Canonical Downstream Contract Export (Milestone 4 Ready) ===")
    export_resp = client.get(f"/api/projects/{project_id}/export/contract")
    assert export_resp.status_code == 200
    contract = export_resp.json()
    assert contract["project_id"] == project_id
    assert contract["current_stage"] == "OCR_APPROVED"
    assert contract["rights"]["status"] == "PUBLIC_DOMAIN"
    assert len(contract["pages"]) == 4
    assert len(contract["panels"]) >= 4
    assert len(contract["text_regions"]) >= 1
    # Verify structured fields in text_regions
    sample_tr = contract["text_regions"][0]
    assert "raw_ocr" in sample_tr
    assert "corrected_text" in sample_tr
    assert "speaker" in sample_tr
    print(f"  Canonical export verified with {len(contract['panels'])} panels and {len(contract['text_regions'])} text regions.")

    print("\n=== [23] Testing SQLite WAL Persistence Across Session Close & Reopen ===")
    from engine.database.session import SessionLocal
    from engine.database.models import ProjectRecord, PageRecord, NormalizationRecord, PanelRecord, TextRegionRecord
    db_verify = SessionLocal()
    try:
        p_db = db_verify.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
        assert p_db is not None
        assert p_db.current_stage == "OCR_APPROVED"
        page_count = db_verify.query(PageRecord).filter(PageRecord.project_id == project_id).count()
        norm_count = db_verify.query(NormalizationRecord).filter(NormalizationRecord.project_id == project_id).count()
        panel_count = db_verify.query(PanelRecord).filter(PanelRecord.project_id == project_id).count()
        tr_count = db_verify.query(TextRegionRecord).filter(TextRegionRecord.project_id == project_id).count()
        assert page_count == 4
        assert norm_count == 4
        assert panel_count >= 4
        assert tr_count >= 1
        print(f"  SQLite persistence verified: {page_count} pages, {norm_count} normalizations, {panel_count} panels, {tr_count} text regions.")
    finally:
        db_verify.close()

    print("\n=== [24] Final Source Immutability Audit (Post-Workflow) ===")
    for sf_name, orig_hash in initial_source_hashes.items():
        curr_hash = hashlib.sha256((source_dir / sf_name).read_bytes()).hexdigest()
        assert curr_hash == orig_hash, f"Source file {sf_name} changed at end of pipeline!"
    print("  Zero source modification: 100% of acquired source files are byte-for-byte identical to original.")

    print("\n=== ALL E2E LIFECYCLE TESTS (ACQUISITION + NORMALIZATION + PANELS + OCR + PERSISTENCE) PASSED PERFECTLY! ===")

if __name__ == "__main__":
    run_e2e_verification()
