from unittest.mock import MagicMock

from engine.jobs.workflow import build_story_analysis_operation


def test_story_operation_rejects_changed_panel_set_before_side_effects(tmp_path):
    import pytest
    from engine.database.models import Base, ProjectRecord, PageRecord, PanelRecord
    from engine.database.session import SessionLocal, engine, run_sqlite_migrations
    from engine.story.service import story_service
    from engine.acquisition.models import PipelineStage

    Base.metadata.create_all(bind=engine)
    run_sqlite_migrations(engine)
    with SessionLocal() as db:
        db.add(ProjectRecord(id='story-snapshot-boundary', title='Snapshot', source_type='LOCAL_FOLDER',
                             rights_status='PUBLIC_DOMAIN', workspace_path=str(tmp_path),
                             current_stage=PipelineStage.OCR_COMPLETE.value))
        db.add(PageRecord(id='story-page', project_id='story-snapshot-boundary', sequence=1,
                          filename='page.jpg', status='READY'))
        for idx in range(2):
            db.add(PanelRecord(id=f'story-panel-{idx}', project_id='story-snapshot-boundary',
                               page_id='story-page', sequence=idx + 1, page_sequence=idx + 1,
                               x=0, y=0, width=100, height=100, crop_filename=f'{idx}.jpg'))
        db.commit()
        with pytest.raises(ValueError, match='panel set'):
            story_service.analyze_story_project(db, 'story-snapshot-boundary',
                                                panel_ids=['story-panel-0'], operation_only=True)


def test_story_submission_pins_selected_provider_before_queue(tmp_path, monkeypatch):
    import asyncio
    from engine.llm.registry import llm_registry
    from engine.database.models import Base, ProjectRecord, PageRecord, PanelRecord
    from engine.database.session import SessionLocal, engine, run_sqlite_migrations
    from engine.story.service import story_service
    from engine.acquisition.models import PipelineStage
    Base.metadata.create_all(bind=engine)
    run_sqlite_migrations(engine)
    with SessionLocal() as db:
        db.add(ProjectRecord(id='story-provider-snapshot', title='Pinned', source_type='LOCAL_FOLDER',
                             rights_status='PUBLIC_DOMAIN', workspace_path=str(tmp_path),
                             current_stage=PipelineStage.OCR_COMPLETE.value))
        db.add(PageRecord(id='provider-page', project_id='story-provider-snapshot', sequence=1, filename='p.jpg', status='READY'))
        db.add(PanelRecord(id='provider-panel', project_id='story-provider-snapshot', page_id='provider-page',
                           sequence=1, page_sequence=1, x=0, y=0, width=100, height=100, crop_filename='p.jpg'))
        db.commit()
        async def select(_):
            return type('Provider', (), {'provider_id': 'mock_llm'})()
        monkeypatch.setattr(llm_registry, 'get_active_provider', select)
        captured = {}
        class Job:
            job_id = 'job'
        monkeypatch.setattr('engine.story.service.job_manager.create_job', lambda **kw: (captured.update(kw) or Job()))
        monkeypatch.setattr('engine.story.service.job_manager.enqueue_async', lambda *a: None)
        assert story_service.analyze_story_project(db, 'story-provider-snapshot') == 'job'
        assert captured['job_input']['preferred_provider'] == 'mock_llm'


def test_story_recovery_passes_persisted_panel_snapshot(monkeypatch):
    from engine.story.service import story_service
    seen = {}
    def analyze(db, project_id, **kwargs):
        seen.update(kwargs)
        return lambda token, progress: None
    monkeypatch.setattr(story_service, 'analyze_story_project', analyze)
    operation = build_story_analysis_operation('project', {'panel_ids': ['panel-one'], 'preferred_provider': 'mock_llm'})
    try:
        operation(MagicMock(), lambda *args: None, lambda: False)
    except TypeError:
        pass  # A dummy coroutine return is not relevant to the argument contract.
    assert seen['panel_ids'] == ['panel-one']
    assert seen['operation_only'] is True
