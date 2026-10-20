"""Recovery must reject incomplete snapshots before operation side effects."""

import pytest

from engine.jobs.workflow import (build_audio_generation_operation,
                                  build_script_generation_operation,
                                  build_story_analysis_operation)


@pytest.mark.parametrize(('factory', 'payload'), [
    (build_story_analysis_operation, {'preferred_provider': 'mock_llm'}),
    (build_story_analysis_operation, {'panel_ids': ['p']}),
    (build_script_generation_operation, {'adaptation_profile': 'FAITHFUL'}),
    (build_audio_generation_operation, {'voice_casting': {}}),
])
def test_incomplete_factory_snapshot_rejected(factory, payload):
    with pytest.raises(ValueError, match='Persisted'):
        factory('project', payload)


def test_story_recovery_refuses_provider_fallback(monkeypatch):
    import asyncio
    from engine.llm.registry import llm_registry
    from engine.story.service import story_service

    async def fallback(_):
        return type('Provider', (), {'provider_id': 'replacement'})()
    monkeypatch.setattr(llm_registry, 'get_active_provider', fallback)
    with pytest.raises((KeyError, ValueError, RuntimeError), match='provider|Provider'):
        asyncio.run(story_service._resolve_pinned_provider('unavailable-provider'))


def test_story_factory_rejects_duplicate_panels():
    with pytest.raises(ValueError, match='panel_ids'):
        build_story_analysis_operation('project', {'panel_ids': ['p', 'p'], 'preferred_provider': 'mock_llm'})

