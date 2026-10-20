"""A recovered acquisition must not rediscover a changed source page list."""

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from engine.acquisition.models import ChapterInfo, PageCandidate, SourceInspectionResult, SourceType
from engine.database.models import Base, ProjectRecord
from engine.jobs.workflow import build_acquisition_operation
from engine.projects.service import ProjectService


class ChangingAdapter:
    adapter_id = "snapshot_adapter"

    def __init__(self):
        self.list_pages_calls = 0

    def inspect(self, source):
        return SourceInspectionResult(adapter_id=self.adapter_id, is_valid=True, source_type=SourceType.LOCAL_FOLDER)

    def list_chapters(self, source):
        return [ChapterInfo(id="chapter", title="Chapter", source_uri=source)]

    def list_pages(self, chapter):
        self.list_pages_calls += 1
        return [PageCandidate(sequence=self.list_pages_calls, source_uri=f"/source/page-{self.list_pages_calls}.jpg")]


class Registry:
    def __init__(self, adapter):
        self.adapter = adapter

    def get_adapter_for(self, source):
        return self.adapter


@pytest.fixture
def context(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        workspace = tmp_path / "project"
        workspace.mkdir()
        db.add(ProjectRecord(id="project", title="Project", source_type="LOCAL_FOLDER", rights_status="PUBLIC_DOMAIN", source_url="/source", workspace_path=str(workspace)))
        db.commit()
        yield db, ProjectService(tmp_path / "default"), ChangingAdapter()
    engine.dispose()


def test_acquisition_job_persists_selected_candidates(context, monkeypatch):
    db, service, adapter = context
    captured = {}

    class Job:
        job_id = "job"

    def create_job(**kwargs):
        captured.update(kwargs)
        return Job()

    monkeypatch.setattr("engine.projects.service.job_manager.create_job", create_job)
    monkeypatch.setattr("engine.projects.service.job_manager.enqueue_async", lambda *args: None)
    assert service.start_acquisition_job(db, "project", Registry(adapter)) == "job"
    assert captured["job_input"]["candidates"] == [
        {"sequence": 1, "source_uri": "/source/page-1.jpg", "suggested_filename": None, "extra_metadata": {}}
    ]
    assert captured["job_input"]["chapter"]["id"] == "chapter"


def test_operation_only_uses_snapshot_without_rediscovery(context):
    db, service, adapter = context
    snapshot = [PageCandidate(sequence=1, source_uri="/source/original.jpg").model_dump(mode="json")]
    chapter = ChapterInfo(id="chapter", title="Chapter", source_uri="/source").model_dump(mode="json")
    runner = service.start_acquisition_job(
        db, "project", Registry(adapter), source_override="/source", chapter_id="chapter",
        adapter_id=adapter.adapter_id, page_delay_sec=0.0, candidate_snapshot=snapshot,
        chapter_snapshot=chapter, operation_only=True,
    )
    assert callable(runner)
    assert adapter.list_pages_calls == 0


def test_rehydration_rejects_missing_snapshot():
    with pytest.raises(ValueError, match="snapshot"):
        build_acquisition_operation("project", {
            "source": "/source", "chapter_id": "chapter", "adapter_id": "snapshot_adapter", "page_delay_sec": 0.0,
        })
