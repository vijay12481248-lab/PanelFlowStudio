"""
Tests for production render audit endpoints (contact sheet and sample frame retrieval).
"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from engine.api.app import create_app
from engine.render.service import render_service
from engine.database.session import get_db


def test_contact_sheet_and_sample_endpoints(tmp_path):
    app = create_app()

    # Create dummy image files
    sheet_file = tmp_path / "contact_sheet.jpg"
    sheet_file.write_bytes(b"\xFF\xD8\xFF\xE0dummy_jpeg_sheet")

    sample_file_0 = tmp_path / "sample_0.jpg"
    sample_file_0.write_bytes(b"\xFF\xD8\xFF\xE0dummy_jpeg_sample_0")

    mock_job = {
        "render_id": "job_audit_test",
        "project_id": "proj_123",
        "status": "COMPLETE",
        "output_path": str(tmp_path / "out.mp4"),
        "contact_sheet_path": str(sheet_file),
        "validation_report": {
            "is_valid": True,
            "gate_status": "PRODUCTION_READY",
            "frame_samples": [
                {
                    "timestamp_sec": 5.2,
                    "frame_index": 150,
                    "is_black": False,
                    "mean_luminance": 210.5,
                    "sample_image_path": str(sample_file_0),
                }
            ],
        },
    }

    # Override render_service.get_render_job and db
    orig_get = render_service.get_render_job
    render_service.get_render_job = MagicMock(return_value=mock_job)

    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        client = TestClient(app)

        # 1. Test contact sheet retrieval
        res_sheet = client.get("/api/projects/proj_123/render/jobs/job_audit_test/contact-sheet")
        assert res_sheet.status_code == 200
        assert res_sheet.headers["content-type"] == "image/jpeg"
        assert res_sheet.content == b"\xFF\xD8\xFF\xE0dummy_jpeg_sheet"

        # 2. Test sample frame retrieval (valid index 0)
        res_sample = client.get("/api/projects/proj_123/render/jobs/job_audit_test/samples/0")
        assert res_sample.status_code == 200
        assert res_sample.headers["content-type"] == "image/jpeg"
        assert res_sample.content == b"\xFF\xD8\xFF\xE0dummy_jpeg_sample_0"

        # 3. Test out-of-bounds sample frame index
        res_oob = client.get("/api/projects/proj_123/render/jobs/job_audit_test/samples/99")
        assert res_oob.status_code == 404
        assert "out of range" in res_oob.json()["detail"].lower()
    finally:
        render_service.get_render_job = orig_get
        app.dependency_overrides.clear()
