import asyncio
from datetime import timedelta
from pathlib import Path

import pytest

from engine.acquisition.models import (
    AcquisitionManifest,
    ChapterInfo,
    DownloadedPageResult,
    PageCandidate,
    PipelineStage,
    ManifestPage,
    SourceInspectionResult,
    SourceType,
)
from engine.database.models import Base, JobRecord, PageRecord, ProjectRecord
from engine.database.session import SessionLocal, engine, run_sqlite_migrations
from engine.jobs.manager import JobManager, utc_now
from engine.projects.service import ProjectService


class BlockingAdapter:
    adapter_id = "blocking_adapter"

    def __init__(self):
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.payload = b"new-page-bytes"

    def inspect(self, source):
        return SourceInspectionResult(adapter_id=self.adapter_id, is_valid=True, source_type=SourceType.LOCAL_FOLDER)

    def list_chapters(self, source):
        return [ChapterInfo(id="chapter", title="Chapter", source_uri=source)]

    def list_pages(self, chapter):
        return [PageCandidate(sequence=1, source_uri="blocked://page")]

    async def download_page(self, page, target_path, cancel_token):
        self.entered.set()
        await self.release.wait()
        Path(target_path).parent.mkdir(parents=True, exist_ok=True)
        Path(target_path).write_bytes(self.payload)
        return DownloadedPageResult(
            sequence=page.sequence,
            source_uri=page.source_uri,
            target_path=Path(target_path),
            filename=Path(target_path).name,
            content_type="image/jpeg",
            width=10,
            height=10,
            byte_size=len(self.payload),
            sha256="blocked-sha",
            success=True,
        )


class Registry:
    def __init__(self, adapter):
        self.adapter = adapter

    def get_adapter_for(self, source):
        return self.adapter


@pytest.fixture
def recovery_context(tmp_path, monkeypatch):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    run_sqlite_migrations(engine)
    workspace = tmp_path / "project"
    (workspace / "source").mkdir(parents=True)
    with SessionLocal() as db:
        db.add(ProjectRecord(
            id="project",
            title="Project",
            source_type="LOCAL_FOLDER",
            rights_status="PUBLIC_DOMAIN",
            source_url="blocked://chapter",
            workspace_path=str(workspace),
            current_stage=PipelineStage.RIGHTS_APPROVED.value,
        ))
        db.commit()
    manager = JobManager()
    service = ProjectService(tmp_path / "default")
    monkeypatch.setattr("engine.projects.service.job_manager", manager)
    return workspace, manager, service


def replace_lease(job_id: str):
    with SessionLocal() as db:
        job = db.query(JobRecord).filter(JobRecord.job_id == job_id).one()
        job.worker_lease_id = "replacement:lease"
        job.lease_expires_at = utc_now() + timedelta(minutes=5)
        db.commit()


@pytest.mark.asyncio
async def test_stale_acquisition_worker_cannot_publish_files_manifest_pages_or_stage(recovery_context):
    workspace, manager, service = recovery_context
    adapter = BlockingAdapter()
    with SessionLocal() as db:
        job_id = service.start_acquisition_job(db, "project", Registry(adapter))

    task = manager._active_tasks[job_id]
    await adapter.entered.wait()
    replace_lease(job_id)
    adapter.release.set()
    await task

    assert not (workspace / "source" / "page_0001.jpg").exists()
    assert not (workspace / "manifest.json").exists()
    with SessionLocal() as db:
        assert db.query(PageRecord).filter(PageRecord.project_id == "project").count() == 0
        assert db.get(ProjectRecord, "project").current_stage == PipelineStage.RIGHTS_APPROVED.value


@pytest.mark.asyncio
async def test_stale_retry_worker_cannot_replace_file_manifest_page_or_stage(recovery_context):
    workspace, manager, service = recovery_context
    old_bytes = b"old-authoritative-page"
    target = workspace / "source" / "page_0001.jpg"
    target.write_bytes(old_bytes)
    manifest = workspace / "manifest.json"
    old_manifest = AcquisitionManifest(
        project_id="project",
        created_at=utc_now().isoformat(),
        updated_at=utc_now().isoformat(),
        source={"type": "LOCAL_FOLDER", "url": "blocked://chapter"},
        rights={"status": "PUBLIC_DOMAIN"},
        chapter={},
        pages=[ManifestPage(
            id="page",
            sequence=1,
            filename="page_0001.jpg",
            source_url="blocked://page",
            sha256="old-sha",
            width=1,
            height=1,
            bytes=len(old_bytes),
            content_type="image/jpeg",
            status="FAILED",
        )],
    ).model_dump_json(indent=2)
    manifest.write_text(old_manifest, encoding="utf-8")
    with SessionLocal() as db:
        db.add(PageRecord(
            id="page",
            project_id="project",
            sequence=1,
            filename="page_0001.jpg",
            source_url="blocked://page",
            content_type="image/jpeg",
            width=1,
            height=1,
            byte_size=len(old_bytes),
            sha256="old-sha",
            status="FAILED",
        ))
        db.commit()

    adapter = BlockingAdapter()
    with SessionLocal() as db:
        job_id = service.retry_failed_pages(db, "project", Registry(adapter))

    task = manager._active_tasks[job_id]
    await adapter.entered.wait()
    replace_lease(job_id)
    adapter.release.set()
    await task

    assert target.read_bytes() == old_bytes
    assert manifest.read_text(encoding="utf-8") == old_manifest
    with SessionLocal() as db:
        page = db.get(PageRecord, "page")
        assert page.status == "FAILED"
        assert page.sha256 == "old-sha"
        assert db.get(ProjectRecord, "project").current_stage == PipelineStage.RIGHTS_APPROVED.value
