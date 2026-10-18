from pathlib import Path
import uuid

import pytest
from PIL import Image

from engine.database.session import init_db, SessionLocal
from engine.database.models import ProjectRecord, PageRecord, PanelRecord, TextRegionRecord
from engine.projects.service import project_service
from engine.jobs.manager import job_manager
from engine.acquisition.downloader.pipeline import PipelineCancellationToken


@pytest.mark.asyncio
async def test_bulk_ocr_populates_review_regions_without_overwriting_human_text(tmp_path, monkeypatch):
    init_db()
    pid = str(uuid.uuid4())
    page_id, panel_id = str(uuid.uuid4()), str(uuid.uuid4())
    (tmp_path / "panels").mkdir()
    (tmp_path / "text_regions").mkdir()
    Image.new("RGB", (200, 300), "white").save(tmp_path / "panels/panel.jpg")
    Image.new("RGB", (100, 100), "white").save(tmp_path / "text_regions/region.jpg")
    captured = []
    monkeypatch.setattr(job_manager, "enqueue_async", lambda job, runner: captured.append(runner))
    with SessionLocal() as db:
        db.add(ProjectRecord(id=pid, title="OCR test", source_type="LOCAL_FOLDER", workspace_path=str(tmp_path)))
        db.flush()
        db.add(PageRecord(id=page_id, project_id=pid, sequence=1, filename="page.jpg"))
        db.flush()
        db.add(PanelRecord(id=panel_id, project_id=pid, page_id=page_id, sequence=1, page_sequence=1,
                           x=0, y=0, width=200, height=300, crop_filename="panel.jpg"))
        db.flush()
        region = TextRegionRecord(project_id=pid, page_id=page_id, panel_id=panel_id,
                                  x=0, y=0, width=100, height=100, crop_filename="region.jpg",
                                  corrected_text="Human correction", correction_status="VERIFIED", status="CONFIRMED")
        db.add(region)
        db.commit()
        region_id = region.id
        project_service.extract_ocr_project(db, pid, "mock_ocr")
    await captured[0](PipelineCancellationToken(), lambda *args: None)
    with SessionLocal() as db:
        region = db.get(TextRegionRecord, region_id)
        assert region.ocr_extracted_at is not None
        assert region.raw_text
        assert region.ocr_engine == "mock_ocr"
        assert region.corrected_text == "Human correction"
        assert region.status == "CONFIRMED"

        rejected = TextRegionRecord(project_id=pid, page_id=page_id, panel_id=panel_id,
                                    x=0, y=0, width=20, height=20,
                                    corrected_text="Excluded decorative text", status="REJECTED")
        db.add(rejected)
        db.commit()
        export = project_service.get_canonical_export(db, pid)
        assert rejected.id not in [item["id"] for item in export["text_regions"]]
