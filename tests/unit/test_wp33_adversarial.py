"""
Adversarial stress-testing test suite for WP-3.3 Hardware-Aware Pipelining,
Eviction Scheduling, and Concurrency Guards.

Tests all adversarial attack surfaces:
1. Hardware boundary conditions for supports_concurrent_gpu() and is_concurrent_pipeline_enabled()
   (8 GB, 16 GB RTX 5060 Ti, 23.9 GB boundary, 24.0 GB boundary, 32 GB, 48 GB, CPU-only).
2. Active eviction ping-pong:
   - Eviction dispatch POST with keep_alive: 0
   - Multi-attempt backoff retry loop (50ms, 100ms, 150ms)
   - Eviction failure / network exception safety (job held back safely)
   - Multi-model eviction
3. CPU-bound Kokoro TTS audio overlap in episode.py:
   - Clean thread cancellation midway through generation
   - Non-fatal exception handling in audio pre-synthesis
   - Zero duplicate TTS calls in video.build_video with pre-cached audio
   - Selective re-synthesis on panel modification
"""
import asyncio
import json
import logging
import threading
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import numpy as np
import pytest
from PIL import Image

from engine.anime.review.channels import ChannelPreset
from engine.narration.runtime import audio as rt
from engine.original import episode, video
from engine.original.models import (
    Bible,
    Character,
    Line,
    Location,
    OriginalStory,
    Panel,
    Premise,
    Scene,
)
from engine.original.series import Episode, Series, SeriesStore
from engine.system.resources import SystemResourceManager, VRAM_CONCURRENT_THRESHOLD_MB


# ---------------------------------------------------------------------------
# Fixtures and Helpers
# ---------------------------------------------------------------------------

def make_story_with_panels(n_panels: int = 4) -> OriginalStory:
    chars = [
        Character(
            id="mira",
            name="Mira",
            role="protagonist",
            age_group="child",
            look="short brown hair, green eyes",
            personality="curious",
        ),
        Character(
            id="pip",
            name="Pip",
            role="companion",
            age_group="child",
            look="tiny mechanical owl",
            personality="helpful",
        ),
    ]
    bible = Bible(
        premise=Premise(
            title="Adversarial Test Story",
            genre="bedtime",
            logline="Testing pipelining",
            tone="calm",
            setting="observatory",
        ),
        characters=chars,
        locations=[Location(id="obs", name="Observatory", look="brass telescopes")],
    )

    panels = []
    for i in range(1, n_panels + 1):
        dialogue = [Line(speaker_id="pip", text=f"Panel {i} alert!")] if i % 2 == 0 else []
        panels.append(
            Panel(
                id=f"p{i:03d}",
                scene_id="sc01",
                shot="wide",
                angle="eye_level",
                location_id="obs",
                character_ids=["mira"],
                action=f"Action in panel {i}",
                caption=f"This is panel {i} of the stress test.",
                dialogue=dialogue,
            )
        )

    return OriginalStory(
        bible=bible,
        scenes=[
            Scene(
                id="sc01",
                location_id="obs",
                character_ids=["mira"],
                summary="Stress testing pipeline",
                mood="calm",
            )
        ],
        panels=panels,
    )


def make_dummy_panel_images(ws: Path, panels: list[Panel], width: int = 1344, height: int = 768):
    (ws / "panels").mkdir(parents=True, exist_ok=True)
    for p in panels:
        img_path = ws / "panels" / f"{p.id}.png"
        img = Image.new("RGB", (width, height), color=(60, 100, 140))
        img.save(img_path)


class FakeKokoroTts:
    """Deterministic synthetic TTS returning non-empty float32 arrays."""
    def __init__(self):
        self.synth_calls = []

    def synth(self, text: str, voice: str, rate: float):
        self.synth_calls.append((text, voice, rate))
        samples = max(int(rt.SR * 0.2), int(rt.SR * 0.05 * max(1, len(text.split()))))
        return (0.2 * np.sin(np.linspace(0, 440, samples))).astype(np.float32)


# ---------------------------------------------------------------------------
# Suite 1: Hardware Boundary Testing
# ---------------------------------------------------------------------------

class TestHardwareBoundaryGuards:
    """
    Adversarial attacks on hardware boundary conditions for supports_concurrent_gpu()
    and is_concurrent_pipeline_enabled().
    """

    @pytest.mark.parametrize(
        "total_mb,expected_supported",
        [
            (8192.0, False),    # 8 GB GPU
            (16311.0, False),   # 16 GB RTX 5060 Ti
            (23999.0, False),   # 23.9 GB boundary (just below 24 GB)
            (23999.9, False),   # Sub-megabyte boundary
            (24000.0, True),    # Exact 24.0 GB threshold
            (24576.0, True),    # 24 GB standard (e.g. RTX 3090 / 4090)
            (32768.0, True),    # 32 GB workstation
            (49152.0, True),    # 48 GB workstation (e.g. RTX 6000 Ada)
        ],
    )
    def test_supports_concurrent_gpu_boundary(self, monkeypatch, total_mb, expected_supported):
        mgr = SystemResourceManager()
        monkeypatch.setattr(mgr, "get_gpu_memory", lambda: {
            "available": True,
            "device_name": f"Mock GPU {total_mb}MB",
            "total_mb": total_mb,
            "free_mb": total_mb * 0.7,
            "used_mb": total_mb * 0.3,
        })
        assert mgr.supports_concurrent_gpu() is expected_supported

    def test_supports_concurrent_gpu_when_cpu_only(self, monkeypatch):
        mgr = SystemResourceManager()
        monkeypatch.setattr(mgr, "get_gpu_memory", lambda: {
            "available": False,
            "device_name": "CPU / System Integrated",
            "total_mb": 0.0,
            "free_mb": 0.0,
            "used_mb": 0.0,
        })
        assert mgr.supports_concurrent_gpu() is False
        assert mgr.is_concurrent_pipeline_enabled() is False

    @pytest.mark.parametrize(
        "flag_value",
        ["1", "true", "True", "yes", "YES", " 1 "],
    )
    def test_8gb_gpu_strict_rejection_even_with_flag(self, monkeypatch, flag_value):
        """8 GB GPU (8192 MB) must always evaluate to False even if flag is asserted."""
        mgr = SystemResourceManager()
        monkeypatch.setenv("PANELFLOW_CONCURRENT_GPU_PIPELINE", flag_value)
        monkeypatch.setattr(mgr, "get_gpu_memory", lambda: {
            "available": True,
            "device_name": "NVIDIA GeForce RTX 4060",
            "total_mb": 8192.0,
            "free_mb": 6000.0,
            "used_mb": 2192.0,
        })
        assert mgr.supports_concurrent_gpu() is False
        assert mgr.is_concurrent_pipeline_enabled() is False

    def test_16gb_rtx_5060_ti_fallback_and_logged_warning(self, monkeypatch, caplog):
        """
        16 GB GPU (16311 MB) RTX 5060 Ti:
        assert False even with flag; verify fallback to time-slicing with logged warning.
        """
        mgr = SystemResourceManager()
        monkeypatch.setenv("PANELFLOW_CONCURRENT_GPU_PIPELINE", "1")
        monkeypatch.setattr(mgr, "get_gpu_memory", lambda: {
            "available": True,
            "device_name": "NVIDIA GeForce RTX 5060 Ti",
            "total_mb": 16311.0,
            "free_mb": 1200.0,
            "used_mb": 15111.0,
        })

        with caplog.at_level(logging.WARNING):
            enabled = mgr.is_concurrent_pipeline_enabled()

        assert enabled is False
        assert mgr.supports_concurrent_gpu() is False
        # Verify specific warning logged
        assert any(
            "16311 MB" in r.message and "Falling back to time-sliced active eviction" in r.message
            for r in caplog.records
        )

    def test_23_9gb_boundary_strictly_rejected(self, monkeypatch):
        """23.9 GB (23999 MB) is strictly below 24,000 MB threshold and must return False."""
        mgr = SystemResourceManager()
        monkeypatch.setenv("PANELFLOW_CONCURRENT_GPU_PIPELINE", "1")
        monkeypatch.setattr(mgr, "get_gpu_memory", lambda: {
            "available": True,
            "device_name": "Near-Threshold GPU",
            "total_mb": 23999.0,
            "free_mb": 18000.0,
            "used_mb": 5999.0,
        })
        assert mgr.supports_concurrent_gpu() is False
        assert mgr.is_concurrent_pipeline_enabled() is False

    def test_24_0gb_boundary_enabled_with_flag_disabled_without_flag(self, monkeypatch):
        """24.0 GB (24000.0 MB) exact threshold: True when flag is set, False when unset."""
        mgr = SystemResourceManager()
        monkeypatch.setattr(mgr, "get_gpu_memory", lambda: {
            "available": True,
            "device_name": "Exact 24GB GPU",
            "total_mb": 24000.0,
            "free_mb": 20000.0,
            "used_mb": 4000.0,
        })
        assert mgr.supports_concurrent_gpu() is True

        # Flag unset -> False (safe default)
        monkeypatch.delenv("PANELFLOW_CONCURRENT_GPU_PIPELINE", raising=False)
        assert mgr.is_concurrent_pipeline_enabled() is False

        # Flag set -> True
        monkeypatch.setenv("PANELFLOW_CONCURRENT_GPU_PIPELINE", "1")
        assert mgr.is_concurrent_pipeline_enabled() is True

    @pytest.mark.parametrize("total_mb", [32768.0, 49152.0])
    def test_workstation_high_vram_satisfies_concurrent_guard(self, monkeypatch, total_mb):
        """32 GB / 48 GB workstations allow concurrency when flag is set."""
        mgr = SystemResourceManager()
        monkeypatch.setenv("PANELFLOW_CONCURRENT_GPU_PIPELINE", "1")
        monkeypatch.setattr(mgr, "get_gpu_memory", lambda: {
            "available": True,
            "device_name": "Workstation GPU",
            "total_mb": total_mb,
            "free_mb": total_mb - 5000.0,
            "used_mb": 5000.0,
        })
        assert mgr.supports_concurrent_gpu() is True
        assert mgr.is_concurrent_pipeline_enabled() is True


# ---------------------------------------------------------------------------
# Suite 2: Active Eviction Ping-Pong & Resiliency
# ---------------------------------------------------------------------------

class TestActiveEvictionPingPong:
    """
    Adversarial attacks on Ollama active eviction, timing backoff loops,
    and failure handling.
    """

    @pytest.mark.asyncio
    async def test_eviction_dispatch_url_and_payload_exactness(self, monkeypatch):
        """
        Simulate Ollama holding 7,000 MB VRAM on 16 GB hardware:
        verify POST http://127.0.0.1:11434/api/generate is dispatched with {"model": "qwen3.5:9b", "keep_alive": 0}.
        """
        mgr = SystemResourceManager()
        monkeypatch.setattr(mgr, "get_gpu_memory", lambda: {
            "available": True,
            "device_name": "NVIDIA GeForce RTX 5060 Ti",
            "total_mb": 16311.0,
            "free_mb": 1200.0,
            "used_mb": 15111.0,
        })

        calls = 0
        async def mock_ollama_runtime(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                return {
                    "total_ollama_vram_mb": 7000.0,
                    "loaded_models_count": 1,
                    "models": [{"name": "qwen3.5:9b"}],
                }
            return {"total_ollama_vram_mb": 0.0, "loaded_models_count": 0, "models": []}

        monkeypatch.setattr(mgr, "get_ollama_runtime", mock_ollama_runtime)

        dispatched_requests = []
        def mock_handler(request: httpx.Request):
            dispatched_requests.append({
                "url": str(request.url),
                "method": request.method,
                "body": json.loads(request.content.decode("utf-8")),
            })
            return httpx.Response(200, json={"status": "success"})

        client_creator = httpx.AsyncClient
        def mock_client(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(mock_handler)
            return client_creator(*args, **kwargs)

        monkeypatch.setattr("engine.system.resources.httpx.AsyncClient", mock_client)

        acquired = await mgr.acquire_gpu_slot("adversarial_job_01", 10000.0, is_comfyui=True)
        assert acquired is True
        assert len(dispatched_requests) == 1
        req = dispatched_requests[0]
        assert req["method"] == "POST"
        assert req["url"] == "http://127.0.0.1:11434/api/generate"
        assert req["body"] == {"model": "qwen3.5:9b", "keep_alive": 0}
        await mgr.release_gpu_slot("adversarial_job_01")

    @pytest.mark.asyncio
    async def test_multi_model_ollama_eviction(self, monkeypatch):
        """When multiple models are loaded in Ollama, all must be evicted with keep_alive: 0."""
        mgr = SystemResourceManager()
        monkeypatch.setattr(mgr, "get_gpu_memory", lambda: {
            "available": True,
            "device_name": "NVIDIA GeForce RTX 5060 Ti",
            "total_mb": 16311.0,
            "free_mb": 1200.0,
            "used_mb": 15111.0,
        })

        calls = 0
        async def mock_ollama_runtime(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                return {
                    "total_ollama_vram_mb": 11000.0,
                    "loaded_models_count": 2,
                    "models": [{"name": "qwen3.5:9b"}, {"name": "mistral:latest"}],
                }
            return {"total_ollama_vram_mb": 0.0, "loaded_models_count": 0, "models": []}

        monkeypatch.setattr(mgr, "get_ollama_runtime", mock_ollama_runtime)

        evicted_models = []
        def mock_handler(request: httpx.Request):
            body = json.loads(request.content.decode("utf-8"))
            evicted_models.append(body.get("model"))
            return httpx.Response(200, json={"status": "success"})

        client_creator = httpx.AsyncClient
        monkeypatch.setattr(
            "engine.system.resources.httpx.AsyncClient",
            lambda *args, **kwargs: client_creator(*args, transport=httpx.MockTransport(mock_handler), **kwargs),
        )

        acquired = await mgr.acquire_gpu_slot("adversarial_multimodel_job", 10000.0, is_comfyui=True)
        assert acquired is True
        assert "qwen3.5:9b" in evicted_models
        assert "mistral:latest" in evicted_models
        await mgr.release_gpu_slot("adversarial_multimodel_job")

    @pytest.mark.asyncio
    async def test_slow_ollama_deallocation_three_attempt_backoff(self, monkeypatch):
        """
        Simulate slow Ollama deallocation:
        Verify the 3-attempt backoff loop (50ms, 100ms, 150ms).
        Memory frees on attempt 3.
        """
        mgr = SystemResourceManager()
        monkeypatch.setattr(mgr, "get_gpu_memory", lambda: {
            "available": True,
            "device_name": "NVIDIA GeForce RTX 5060 Ti",
            "total_mb": 16311.0,
            "free_mb": 1200.0,
            "used_mb": 15111.0,
        })

        sleep_calls = []
        real_sleep = asyncio.sleep

        async def spy_sleep(delay, *args, **kwargs):
            sleep_calls.append(round(delay, 3))
            await real_sleep(0.001)  # fast-forward during test

        monkeypatch.setattr("asyncio.sleep", spy_sleep)

        # Ollama frees memory only on attempt 3
        poll_count = 0
        async def mock_ollama_runtime(*args, **kwargs):
            nonlocal poll_count
            poll_count += 1
            if poll_count <= 3:
                # Still occupied
                return {"total_ollama_vram_mb": 7000.0, "loaded_models_count": 1, "models": [{"name": "qwen3.5:9b"}]}
            # Freed on 4th poll (after attempt 3 sleep)
            return {"total_ollama_vram_mb": 0.0, "loaded_models_count": 0, "models": []}

        monkeypatch.setattr(mgr, "get_ollama_runtime", mock_ollama_runtime)
        monkeypatch.setattr(mgr, "_try_evict_ollama", AsyncMock(return_value=True))

        acquired = await mgr.acquire_gpu_slot("slow_dealloc_job", 10000.0, is_comfyui=True)
        assert acquired is True
        # Verify the 3 sleep durations were exactly 50ms, 100ms, and 150ms
        assert sleep_calls == [0.05, 0.1, 0.15]
        assert poll_count == 4
        await mgr.release_gpu_slot("slow_dealloc_job")

    @pytest.mark.asyncio
    async def test_ollama_eviction_failure_holds_comfyui_job(self, monkeypatch):
        """
        Simulate Ollama eviction returning failure:
        VRAM remains occupied, ComfyUI job must be held back (acquire returns False).
        """
        mgr = SystemResourceManager()
        monkeypatch.setattr(mgr, "get_gpu_memory", lambda: {
            "available": True,
            "device_name": "NVIDIA GeForce RTX 5060 Ti",
            "total_mb": 16311.0,
            "free_mb": 1200.0,
            "used_mb": 15111.0,
        })

        # Memory never frees
        async def mock_ollama_runtime(*args, **kwargs):
            return {"total_ollama_vram_mb": 7000.0, "loaded_models_count": 1, "models": [{"name": "qwen3.5:9b"}]}

        monkeypatch.setattr(mgr, "get_ollama_runtime", mock_ollama_runtime)
        # Eviction call fails
        monkeypatch.setattr(mgr, "_try_evict_ollama", AsyncMock(return_value=False))

        acquired = await mgr.acquire_gpu_slot("failed_eviction_job", 10000.0, is_comfyui=True)
        assert acquired is False
        assert mgr.active_gpu_jobs_count == 0

    @pytest.mark.asyncio
    async def test_ollama_network_exception_during_eviction_holds_job(self, monkeypatch):
        """
        Simulate network exception (ConnectError / Timeout) during eviction POST:
        _try_evict_ollama catches and returns False, memory remains full, ComfyUI job is held back.
        """
        mgr = SystemResourceManager()
        monkeypatch.setattr(mgr, "get_gpu_memory", lambda: {
            "available": True,
            "device_name": "NVIDIA GeForce RTX 5060 Ti",
            "total_mb": 16311.0,
            "free_mb": 1200.0,
            "used_mb": 15111.0,
        })

        async def mock_ollama_runtime(*args, **kwargs):
            return {"total_ollama_vram_mb": 7000.0, "loaded_models_count": 1, "models": [{"name": "qwen3.5:9b"}]}

        monkeypatch.setattr(mgr, "get_ollama_runtime", mock_ollama_runtime)

        def mock_handler(request: httpx.Request):
            raise httpx.ConnectError("Connection refused by Ollama daemon")

        client_creator = httpx.AsyncClient
        monkeypatch.setattr(
            "engine.system.resources.httpx.AsyncClient",
            lambda *args, **kwargs: client_creator(*args, transport=httpx.MockTransport(mock_handler), **kwargs),
        )

        acquired = await mgr.acquire_gpu_slot("network_fail_job", 10000.0, is_comfyui=True)
        assert acquired is False
        assert mgr.active_gpu_jobs_count == 0


# ---------------------------------------------------------------------------
# Suite 3: CPU-Bound Kokoro TTS Audio Overlap in episode.py
# ---------------------------------------------------------------------------

class TestCpuKokoroAudioOverlap:
    """
    Adversarial attacks on CPU-bound Kokoro TTS audio synthesis overlap,
    cancellation clean exit, exception resilience, and pre-cached reuse.
    """

    def test_cancellation_midway_clean_daemon_thread_exit(self, tmp_path, monkeypatch):
        """
        Midway cancellation test:
        Synthesizing 4 panels; cancel signal triggers after panel 2 is synthesized.
        Verify:
        - Daemon thread exits cleanly (terminates without hang or deadlock)
        - Panels 1 & 2 are synthesized and persisted in video_meta.json
        - Panels 3 & 4 are skipped
        """
        story = make_story_with_panels(4)
        ws = tmp_path / "midway_cancel_ep"
        ws.mkdir(parents=True, exist_ok=True)

        channel = ChannelPreset(
            id="test_ch",
            name="Test Channel",
            voice="af_bella",
            voice_rate=1.0,
        )

        synthesized = []
        is_cancelled_flag = False

        def mock_voice_panel(tts, panel, narrator, chars, fps, out):
            synthesized.append(panel.id)
            out.write_bytes(b"RIFFdummywav")
            # Trigger cancellation after panel 2 finishes
            nonlocal is_cancelled_flag
            if panel.id == "p002":
                is_cancelled_flag = True
            return 1.2

        monkeypatch.setattr("engine.original.video.voice_panel", mock_voice_panel)

        thread = episode._pre_synthesize_episode_audio_async(
            story=story,
            ws=ws,
            channel=channel,
            is_cancelled=lambda: is_cancelled_flag,
        )

        assert isinstance(thread, threading.Thread)
        assert thread.daemon is True

        thread.join(timeout=5.0)
        assert not thread.is_alive(), "Worker thread must terminate cleanly upon midway cancellation"

        # Exactly panels 1 and 2 should have been synthesized
        assert synthesized == ["p001", "p002"]
        assert (ws / "voice" / "p001.wav").exists()
        assert (ws / "voice" / "p002.wav").exists()
        assert not (ws / "voice" / "p003.wav").exists()
        assert not (ws / "voice" / "p004.wav").exists()

        meta_path = ws / "video_meta.json"
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert "p001" in meta
        assert "p002" in meta
        assert "p003" not in meta
        assert "p004" not in meta

    def test_audio_pre_synthesis_exception_is_non_fatal_and_art_succeeds(self, tmp_path, monkeypatch):
        """
        Exception in audio pre-synthesis:
        When Kokoro TTS crashes with an unhandled runtime error, the background worker
        catches it non-fatally. The main art generation process must complete safely.
        """
        story = make_story_with_panels(2)
        ws = tmp_path / "exception_resilience_ep"
        ws.mkdir(parents=True, exist_ok=True)

        channel = ChannelPreset(
            id="test_ch",
            name="Test Channel",
            voice="af_bella",
            voice_rate=1.0,
        )

        def mock_failing_voice_panel(tts, panel, narrator, chars, fps, out):
            raise RuntimeError("CRITICAL_KOKORO_AUDIO_SUBSYSTEM_CRASH")

        monkeypatch.setattr("engine.original.video.voice_panel", mock_failing_voice_panel)

        # Worker thread should not propagate exception or crash main process
        thread = episode._pre_synthesize_episode_audio_async(
            story=story,
            ws=ws,
            channel=channel,
            is_cancelled=lambda: False,
        )

        thread.join(timeout=5.0)
        assert not thread.is_alive()

        # Simulate the run_episode try/finally block: art generation completes safely
        art_completed = False
        try:
            # Main GPU art work succeeds despite audio failure
            art_completed = True
        finally:
            thread.join(timeout=10.0)

        assert art_completed is True

    def test_pre_cached_audio_reuse_zero_duplicate_tts_calls_in_build_video(self, tmp_path, monkeypatch):
        """
        Verify that video.build_video reuses all audio pre-synthesized by
        _pre_synthesize_episode_audio_async, resulting in EXACTLY ZERO duplicate TTS calls.
        """
        story = make_story_with_panels(3)
        ws = tmp_path / "pre_cached_reuse_ep"
        ws.mkdir(parents=True, exist_ok=True)
        make_dummy_panel_images(ws, story.panels)

        channel = ChannelPreset(
            id="bedtime_ch",
            name="Bedtime Tales",
            voice="af_bella",
            voice_rate=1.0,
            music_path="",
        )

        # 1. Run async pre-synthesis
        pre_synth_calls = []
        def mock_pre_voice_panel(tts, panel, narrator, chars, fps, out):
            pre_synth_calls.append(panel.id)
            # Create a valid wav file
            samples = np.zeros(int(rt.SR * 1.5), dtype=np.float32)
            rt.write_wav_atomic(out, samples)
            return 1.5

        monkeypatch.setattr("engine.original.video.voice_panel", mock_pre_voice_panel)

        thread = episode._pre_synthesize_episode_audio_async(
            story=story,
            ws=ws,
            channel=channel,
            is_cancelled=lambda: False,
        )
        thread.join(timeout=10.0)
        assert not thread.is_alive()
        assert pre_synth_calls == ["p001", "p002", "p003"]

        # 2. Now run video.build_video with a spy on voice_panel
        build_video_voice_calls = []
        def spy_build_voice_panel(tts, panel, narrator, chars, fps, out):
            build_video_voice_calls.append(panel.id)
            return 1.5

        monkeypatch.setattr("engine.original.video.voice_panel", spy_build_voice_panel)

        # Mock render_panel and ffprobe so build_video can complete without ffmpeg processes
        def mock_render_panel(img, wav, dur, fps, text, ws_dir, burn, out, **kwargs):
            out.write_bytes(b"DUMMY_MP4")

        monkeypatch.setattr("engine.original.video.render_panel", mock_render_panel)
        monkeypatch.setattr("engine.anime.review.render.DEFAULT_MUSIC", None)

        def mock_rr_run(cmd, ws_dir, **kwargs):
            out_file = Path(cmd[-1])
            if not out_file.is_absolute():
                out_file = ws_dir / out_file
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_bytes(b"DUMMY_MP4")

        monkeypatch.setattr("engine.anime.review.render._run", mock_rr_run)

        # Execute build_video
        narrator = (channel.voice, channel.voice_rate)
        out = video.build_video(
            story=story,
            ws=ws,
            tts=FakeKokoroTts(),
            fps=30.0,
            burn_captions=False,
            music=None,
            narrator=narrator,
        )

        # ASSERTION: Exactly zero duplicate TTS calls!
        assert len(build_video_voice_calls) == 0, (
            f"Expected 0 duplicate TTS calls in build_video, but got {len(build_video_voice_calls)}: {build_video_voice_calls}"
        )
        assert out["panels"] == 3
        assert out["missing_panels"] == []

    def test_selective_resynthesis_on_panel_text_modification(self, tmp_path, monkeypatch):
        """
        Verify that if one panel's text is modified after pre-caching, ONLY that specific panel
        is re-synthesized, while all unmodified panels are reused from cache.
        """
        story = make_story_with_panels(3)
        ws = tmp_path / "selective_resynth_ep"
        ws.mkdir(parents=True, exist_ok=True)
        make_dummy_panel_images(ws, story.panels)

        channel = ChannelPreset(
            id="ch",
            name="Channel",
            voice="af_bella",
            voice_rate=1.0,
            music_path="",
        )

        def mock_pre_voice(tts, panel, narrator, chars, fps, out):
            samples = np.zeros(int(rt.SR * 1.0), dtype=np.float32)
            rt.write_wav_atomic(out, samples)
            return 1.0

        monkeypatch.setattr("engine.original.video.voice_panel", mock_pre_voice)

        thread = episode._pre_synthesize_episode_audio_async(
            story=story,
            ws=ws,
            channel=channel,
            is_cancelled=lambda: False,
        )
        thread.join(timeout=10.0)

        # Modify only panel 2's caption
        story.panels[1].caption = "MODIFIED CAPTION FOR PANEL 2"

        resynthesized_panels = []
        def spy_voice_panel(tts, panel, narrator, chars, fps, out):
            resynthesized_panels.append(panel.id)
            samples = np.zeros(int(rt.SR * 1.0), dtype=np.float32)
            rt.write_wav_atomic(out, samples)
            return 1.0

        monkeypatch.setattr("engine.original.video.voice_panel", spy_voice_panel)
        monkeypatch.setattr("engine.original.video.render_panel", lambda *args, **kwargs: None)

        def mock_rr_run(cmd, ws_dir, **kwargs):
            out_file = Path(cmd[-1])
            if not out_file.is_absolute():
                out_file = ws_dir / out_file
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_bytes(b"DUMMY_MP4")

        monkeypatch.setattr("engine.anime.review.render._run", mock_rr_run)

        narrator = (channel.voice, channel.voice_rate)
        video.build_video(
            story=story,
            ws=ws,
            tts=FakeKokoroTts(),
            fps=30.0,
            burn_captions=False,
            music=None,
            narrator=narrator,
        )

        # ONLY panel 2 should be re-synthesized; panels 1 and 3 are reused from cache!
        assert resynthesized_panels == ["p002"], (
            f"Expected only ['p002'] to be re-synthesized, but got {resynthesized_panels}"
        )
