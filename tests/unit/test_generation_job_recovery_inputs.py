from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from engine.api.routers.audio import GenerateAudioRequest, generate_audio_job
from engine.api.routers.story import ScriptGenerateRequest, generate_script_job
from engine.story.models import NarrativeDocument


def _project_db(project_id: str = "project"):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(id=project_id)
    return db


def test_script_endpoint_persists_validated_snapshot_and_exact_provider_model(monkeypatch):
    narrative = NarrativeDocument(
        project_id="project",
        analysis_metadata={"engine": "vision-story-v1", "provider": "ollama"},
    )
    captured = {}
    submitted_operation = {}

    monkeypatch.setattr("engine.api.routers.story.story_service.get_narrative", lambda db, project_id: narrative)
    monkeypatch.setattr(
        "engine.api.routers.story.story_service.resolve_script_provider_identity",
        lambda value: ("ollama", "qwen-pinned:9b"),
    )

    def enqueue(project_id, job_type, operation, **kwargs):
        captured.update(kwargs["job_input"])
        submitted_operation["value"] = operation
        return "job-script"

    monkeypatch.setattr("engine.jobs.workflow.enqueue_project_operation", enqueue)

    result = generate_script_job("project", ScriptGenerateRequest(adaptation_profile="FAITHFUL"), _project_db())

    assert result == {"job_id": "job-script"}
    assert captured == {
        "adaptation_profile": "FAITHFUL",
        "narrative_snapshot": narrative.model_dump(mode="json"),
        "provider_id": "ollama",
        "model_name": "qwen-pinned:9b",
    }
    from engine.jobs.workflow import build_operation
    assert submitted_operation["value"] is not None
    assert build_operation("SCRIPT_GENERATION", "project", captured) is not None


def test_audio_endpoint_persists_approved_script_tts_identity_and_resolved_casting(monkeypatch):
    script_snapshot = {"script_id": "script", "segments": [{"id": "segment", "text": "Hello"}]}
    resolved_casting = {"NARRATOR": "Aria (The Narrator)", "char_one": "Marcus"}
    captured = {}
    submitted_operation = {}

    monkeypatch.setattr("engine.jobs.workflow.audio_script_snapshot", lambda db, project_id: script_snapshot)
    monkeypatch.setattr(
        "engine.api.routers.audio.audio_service.resolve_tts_provider_identity",
        lambda db, project_id: ("chatterbox_turbo", "ChatterboxTurboTTS"),
    )
    monkeypatch.setattr(
        "engine.api.routers.audio.audio_service.resolve_voice_casting",
        lambda casting: resolved_casting,
    )

    def enqueue(project_id, job_type, operation, **kwargs):
        captured.update(kwargs["job_input"])
        submitted_operation["value"] = operation
        return "job-audio"

    monkeypatch.setattr("engine.jobs.workflow.enqueue_project_operation", enqueue)

    result = generate_audio_job(
        "project",
        GenerateAudioRequest(voice_casting={"char_one": "Marcus"}),
        _project_db(),
    )

    assert result == {"job_id": "job-audio"}
    assert captured == {
        "script_snapshot": script_snapshot,
        "tts_provider_id": "chatterbox_turbo",
        "tts_model_name": "ChatterboxTurboTTS",
        "voice_casting": resolved_casting,
    }
    from engine.jobs.workflow import build_operation
    assert submitted_operation["value"] is not None
    assert build_operation("AUDIO_GENERATION", "project", captured) is not None


def test_script_rehydration_resolves_only_persisted_provider_and_model(monkeypatch):
    from engine.jobs.workflow import build_script_generation_operation
    from engine.story.service import story_service

    narrative = NarrativeDocument(project_id="project")
    called = []
    monkeypatch.setattr(story_service, "get_narrative", lambda db, project_id: narrative)

    def resolve(provider_id, model_name):
        called.append((provider_id, model_name))
        raise RuntimeError("Persisted script provider is unavailable")

    monkeypatch.setattr(story_service, "resolve_pinned_script_provider", resolve)
    monkeypatch.setattr(story_service, "generate_script", lambda *args, **kwargs: pytest.fail("generation ran"))
    operation = build_script_generation_operation("project", {
        "adaptation_profile": "FAITHFUL",
        "narrative_snapshot": narrative.model_dump(mode="json"),
        "provider_id": "persisted-provider",
        "model_name": "persisted-model",
    })

    with pytest.raises(RuntimeError, match="Persisted script provider"):
        operation(MagicMock(), lambda *args: None, lambda: False)
    assert called == [("persisted-provider", "persisted-model")]


def test_audio_rehydration_resolves_only_persisted_tts_identity(monkeypatch):
    from engine.audio.service import audio_service
    from engine.jobs.workflow import build_audio_generation_operation

    snapshot = {"script_id": "script", "segments": [{"id": "segment", "text": "Hello"}]}
    monkeypatch.setattr("engine.jobs.workflow.audio_script_snapshot", lambda db, project_id: snapshot)
    called = []

    def validate(provider_id, model_name):
        called.append((provider_id, model_name))
        raise RuntimeError("Persisted TTS provider is unavailable")

    monkeypatch.setattr(audio_service, "validate_pinned_tts_provider", validate)
    monkeypatch.setattr(audio_service, "generate_audio_timeline", lambda *args, **kwargs: pytest.fail("audio ran"))
    operation = build_audio_generation_operation("project", {
        "script_snapshot": snapshot,
        "tts_provider_id": "persisted-tts",
        "tts_model_name": "persisted-model",
        "voice_casting": {"NARRATOR": "Aria"},
    })

    with pytest.raises(RuntimeError, match="Persisted TTS provider"):
        operation(MagicMock(), lambda *args: None, lambda: False)
    assert called == [("persisted-tts", "persisted-model")]
