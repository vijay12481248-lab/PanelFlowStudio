"""Studio music and speech jobs: persisted as project assets, queued with the right gate numbers, rehydrated after a restart."""
import io
import sys
import types
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from engine import studio_audio
from engine.database.models import AssetRecord, Base, ProjectRecord


@pytest.fixture
def db_and_workspace(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.add(ProjectRecord(id="project", title="t", source_type="LOCAL_FOLDER", workspace_path=str(tmp_path)))
    db.commit()
    yield db, tmp_path
    db.close()
    engine.dispose()


def _tone(seconds, sr):
    return (0.1 * np.sin(np.linspace(0, 440 * seconds, int(sr * seconds)))).astype("float32")


def test_speech_is_persisted_as_an_audio_asset_with_its_provenance(db_and_workspace, monkeypatch):
    db, workspace = db_and_workspace
    seen = {}

    class FakePipeline:
        def __init__(self, lang_code):
            seen["lang"] = lang_code

        def __call__(self, text, voice, speed):
            seen.update(text=text, voice=voice, speed=speed)
            yield None, None, _tone(0.5, studio_audio.KOKORO_SR)
            yield None, None, _tone(0.5, studio_audio.KOKORO_SR)

    monkeypatch.setitem(sys.modules, "kokoro", types.SimpleNamespace(KPipeline=FakePipeline))
    out = studio_audio.generate_speech_operation(db, lambda *a: None, lambda: False, project_id="project", text="Mind the ledge.", voice="bm_george", speed=0.9)
    assert seen == {"lang": "b", "text": "Mind the ledge.", "voice": "bm_george", "speed": 0.9}  # 'b' = British, from the voice name
    asset = db.query(AssetRecord).filter(AssetRecord.id == out["asset_id"]).one()
    assert asset.asset_type == "STUDIO_SPEECH" and asset.content_type == "audio/wav" and asset.status == "READY"
    assert asset.provenance["voice"] == "bm_george" and asset.provenance["seconds"] == pytest.approx(1.0, abs=0.01) and asset.provenance["sample_rate"] == 24000
    data = (workspace / asset.relative_path).read_bytes()
    assert len(data) == asset.byte_size and sf.info(io.BytesIO(data)).frames == 24000


def test_a_speech_job_that_produces_nothing_fails_and_leaves_no_asset(db_and_workspace, monkeypatch):
    db, workspace = db_and_workspace
    monkeypatch.setitem(sys.modules, "kokoro", types.SimpleNamespace(KPipeline=lambda lang_code: (lambda text, voice, speed: iter([]))))
    with pytest.raises(studio_audio.StudioAudioError, match="no audio"):
        studio_audio.generate_speech_operation(db, lambda *a: None, lambda: False, project_id="project", text="hello", voice="bm_george", speed=0.95)
    assert db.query(AssetRecord).count() == 0 and not (workspace / "generated" / "studio_audio").exists()


def test_music_is_persisted_and_a_provider_failure_becomes_one_clear_job_error(db_and_workspace, monkeypatch):
    db, workspace = db_and_workspace
    take = workspace / "take.wav"
    sf.write(str(take), _tone(2.0, 48000), 48000, subtype="PCM_16")
    calls = {}

    class FakeProvider:
        def generate_music_take(self, **kw):
            calls.update(kw)
            if kw["seed"] == 13:
                raise ConnectionError("ACE-Step 1.5 API server is unreachable")
            return types.SimpleNamespace(audio_file_path=str(take))

    import engine.audio.providers.ace_step as ace

    monkeypatch.setattr(ace, "ACEStepProvider", FakeProvider)
    out = studio_audio.generate_music_operation(db, lambda *a: None, lambda: False, project_id="project", prompt="calm folk", seconds=24, bpm=84, key_scale="D Major", seed=7)
    asset = db.query(AssetRecord).filter(AssetRecord.id == out["asset_id"]).one()
    assert asset.asset_type == "STUDIO_MUSIC" and asset.provenance["bpm"] == 84 and asset.provenance["seed"] == 7 and out["seconds"] == pytest.approx(2.0, abs=0.01)
    assert calls["use_random_seed"] is False and calls["audio_duration"] == 24  # the seed is honoured, so a take can be reproduced
    with pytest.raises(studio_audio.StudioAudioError, match="ACE-Step: ACE-Step 1.5 API server is unreachable"):
        studio_audio.generate_music_operation(db, lambda *a: None, lambda: False, project_id="project", prompt="calm folk", seconds=24, bpm=84, key_scale="D Major", seed=13)
    assert db.query(AssetRecord).count() == 1


def test_routes_validate_input_refuse_unknown_projects_and_queue_with_the_gate_numbers(db_and_workspace, monkeypatch):
    from fastapi import HTTPException
    from pydantic import ValidationError

    from engine.api.routers import studio_audio as routes

    db, _ = db_and_workspace
    queued = []
    monkeypatch.setattr(routes, "enqueue_project_operation", lambda **kw: queued.append(kw) or "job-1")
    assert routes.queue_studio_music("project", routes.StudioMusicRequest(prompt="calm folk music"), db=db) == {"job_id": "job-1", "status": "QUEUED"}
    assert routes.queue_studio_speech("project", routes.StudioSpeechRequest(text="hello", voice="bm_george"), db=db)["job_id"] == "job-1"
    assert [(q["job_type"], q["requires_gpu"], q["gpu_vram_mb"], q["max_retries"]) for q in queued] == [
        ("STUDIO_MUSIC_GENERATION", True, studio_audio.MUSIC_VRAM_MB, 0), ("STUDIO_SPEECH_GENERATION", True, studio_audio.SPEECH_VRAM_MB, 0)]
    with pytest.raises(HTTPException) as e:
        routes.queue_studio_music("missing", routes.StudioMusicRequest(prompt="calm folk music"), db=db)
    assert e.value.status_code == 404 and len(queued) == 2
    for bad in ("../etc", "BM_GEORGE", "bm", ""):  # a voice name is never a path
        with pytest.raises(ValidationError):
            routes.StudioSpeechRequest(text="hello", voice=bad)
    with pytest.raises(ValidationError):
        routes.StudioMusicRequest(prompt="calm folk music", seconds=999)


def test_both_job_types_are_rehydrated_after_a_restart(monkeypatch):
    from engine.jobs import workflow

    seen = {}
    monkeypatch.setattr(studio_audio, "generate_music_operation", lambda *a, **k: seen.update(music=k))
    monkeypatch.setattr(studio_audio, "generate_speech_operation", lambda *a, **k: seen.update(speech=k))
    workflow.build_operation(studio_audio.MUSIC_JOB_TYPE, "project", {"prompt": "calm folk", "seconds": 24, "bpm": 84, "key_scale": "D Major", "seed": 7})(None, None, None)
    workflow.build_operation(studio_audio.SPEECH_JOB_TYPE, "project", {"text": "hi", "voice": "bm_george", "speed": 0.9})(None, None, None)
    assert seen["music"]["seed"] == 7 and seen["music"]["model"] == "acestep-v15-turbo" and seen["speech"]["voice"] == "bm_george"


def _qwen_setup(monkeypatch, tmp_path, voices=("marcus_male",)):
    refs = tmp_path / "refs"
    refs.mkdir()
    for v in voices:
        (refs / f"{v}.wav").write_bytes(b"ref")
    (refs / "notes.txt").write_text("not a voice")
    fake_py, fake_runner = tmp_path / "python.exe", tmp_path / "runner.py"
    fake_py.write_text("")
    fake_runner.write_text("")
    monkeypatch.setattr(studio_audio, "VOICE_REFERENCE_DIR", refs)
    monkeypatch.setattr(studio_audio, "QWEN3_TTS_PYTHON", fake_py)
    monkeypatch.setattr(studio_audio, "QWEN3_TTS_RUNNER", fake_runner)
    return refs


def test_qwen3_voices_are_the_reference_recordings_on_disk(monkeypatch, tmp_path):
    _qwen_setup(monkeypatch, tmp_path, voices=("marcus_male", "aria_female"))
    assert sorted(studio_audio.qwen3_voices()) == ["aria_female", "marcus_male"]  # the text file is not a voice
    monkeypatch.setattr(studio_audio, "VOICE_REFERENCE_DIR", tmp_path / "missing")
    assert studio_audio.qwen3_voices() == {}


def test_qwen3_speech_runs_the_runner_with_the_reference_voice_and_persists_the_result(db_and_workspace, monkeypatch, tmp_path):
    import subprocess

    db, workspace = db_and_workspace
    refs = _qwen_setup(monkeypatch, tmp_path)
    seen = {}

    def fake_run(argv, **kw):
        seen["argv"], seen["env"] = argv, kw["env"]
        out = Path(argv[argv.index("--output") + 1])
        sf.write(str(out), _tone(1.5, 24000), 24000, subtype="PCM_16")
        return subprocess.CompletedProcess(argv, 0, stdout='{"success": true}', stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)
    out = studio_audio.generate_speech_operation(db, lambda *a: None, lambda: False, project_id="project", text="Mind the ledge.", voice="marcus_male",
                                                 speed=0.95, provider="qwen3_tts", language="English")
    argv = seen["argv"]
    assert argv[2] == "synth" and argv[argv.index("--ref-audio") + 1] == str(refs / "marcus_male.wav") and argv[argv.index("--language") + 1] == "English"
    assert seen["env"]["HF_HUB_OFFLINE"] == "1"  # a missing weight is an error, never a download
    asset = db.query(AssetRecord).filter(AssetRecord.id == out["asset_id"]).one()
    assert asset.provenance["provider"] == "qwen3_tts" and asset.provenance["voice"] == "marcus_male" and out["seconds"] == pytest.approx(1.5, abs=0.01)


def test_qwen3_refuses_an_unknown_voice_and_reports_a_runner_failure_without_leaving_an_asset(db_and_workspace, monkeypatch, tmp_path):
    import subprocess

    db, _ = db_and_workspace
    _qwen_setup(monkeypatch, tmp_path)
    with pytest.raises(studio_audio.StudioAudioError, match="no voice 'ghost'.*marcus_male"):
        studio_audio.generate_speech_operation(db, lambda *a: None, lambda: False, project_id="project", text="hi", voice="ghost", speed=0.95, provider="qwen3_tts")
    monkeypatch.setattr("subprocess.run", lambda argv, **kw: subprocess.CompletedProcess(argv, 1, stdout="", stderr="CUDA out of memory"))
    with pytest.raises(studio_audio.StudioAudioError, match="Qwen3-TTS: CUDA out of memory"):
        studio_audio.generate_speech_operation(db, lambda *a: None, lambda: False, project_id="project", text="hi", voice="marcus_male", speed=0.95, provider="qwen3_tts")
    with pytest.raises(studio_audio.StudioAudioError, match="unknown speech provider"):
        studio_audio.generate_speech_operation(db, lambda *a: None, lambda: False, project_id="project", text="hi", voice="bm_george", speed=0.95, provider="nope")
    assert db.query(AssetRecord).count() == 0


def test_the_speech_route_picks_the_provider_and_its_gate_number_and_rehydrates_it(db_and_workspace, monkeypatch, tmp_path):
    from pydantic import ValidationError

    from engine.api.routers import studio_audio as routes
    from engine.jobs import workflow

    db, _ = db_and_workspace
    queued = []
    monkeypatch.setattr(routes, "enqueue_project_operation", lambda **kw: queued.append(kw) or "job-1")
    routes.queue_studio_speech("project", routes.StudioSpeechRequest(text="hi", voice="marcus_male", provider="qwen3_tts"), db=db)
    routes.queue_studio_speech("project", routes.StudioSpeechRequest(text="hi", voice="bm_george"), db=db)
    assert [q["gpu_vram_mb"] for q in queued] == [studio_audio.QWEN3_TTS_VRAM_MB, studio_audio.SPEECH_VRAM_MB]
    assert queued[0]["job_input"]["provider"] == "qwen3_tts" and queued[1]["job_input"]["provider"] == "kokoro"
    for bad in ("../x", "marcus male", "C:\a_b"):
        with pytest.raises(ValidationError):
            routes.StudioSpeechRequest(text="hi", voice=bad, provider="qwen3_tts")
    with pytest.raises(ValidationError):
        routes.StudioSpeechRequest(text="hi", voice="bm_george", provider="elevenlabs")
    seen = {}
    monkeypatch.setattr(studio_audio, "generate_speech_operation", lambda *a, **k: seen.update(k))
    workflow.build_operation(studio_audio.SPEECH_JOB_TYPE, "project", {"text": "hi", "voice": "marcus_male", "speed": 0.95, "provider": "qwen3_tts", "language": "German"})(None, None, None)
    assert seen["provider"] == "qwen3_tts" and seen["language"] == "German"
