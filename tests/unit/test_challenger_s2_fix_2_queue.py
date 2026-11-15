"""Adversarial challenger stress tests for Iteration 2 Backend Queue and Series execution.

Focus areas:
1. queue.py argument handling when preview=False (default) vs preview=True.
2. Positional and keyword argument stability, preventing positional overflows.
3. Extra / arbitrary parameters in payloads and job specs.
4. Single Art Workflow invariant preservation.
"""
from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from engine.anime.review.channels import ChannelPreset, ChannelStore
from engine.comfyui.art import ART_WORKFLOW_ID
from engine.original import episode, queue
from engine.original.episode import run_episode
from engine.original.queue import EpisodeJobSpec, build_episode_operation, enqueue_episodes
from engine.original.series import Episode, SeriesStore
from tests.unit.test_original_story import full_bible


def test_queue_spec_defaults_and_preview_flag():
    """Verify EpisodeJobSpec defaults preview to False, and properly validates boolean preview."""
    spec_default = EpisodeJobSpec(root="fake/root", series_id="s1", number=1)
    assert spec_default.preview is False
    assert spec_default.check is True
    assert spec_default.refine is False
    assert spec_default.animate is False

    spec_preview_true = EpisodeJobSpec(root="fake/root", series_id="s1", number=1, preview=True)
    assert spec_preview_true.preview is True

    spec_preview_false = EpisodeJobSpec(root="fake/root", series_id="s1", number=1, preview=False)
    assert spec_preview_false.preview is False


def test_queue_spec_extra_arbitrary_parameters_tolerance():
    """Verify EpisodeJobSpec tolerates extra / unexpected payload fields without crashing."""
    payload_with_extras = {
        "root": "fake/root",
        "series_id": "s1",
        "number": 2,
        "scenes": 4,
        "extra_field_1": "unexpected_data",
        "arbitrary_nested": {"foo": "bar", "count": 42},
        "preview": True,
        "title": "Episode 2",
    }
    # Pydantic v2 by default ignores extra fields
    spec = EpisodeJobSpec(**payload_with_extras)
    assert spec.series_id == "s1"
    assert spec.number == 2
    assert spec.scenes == 4
    assert spec.preview is True
    assert not hasattr(spec, "extra_field_1")


def test_queue_build_operation_invokes_legacy_run_with_12_args_when_preview_is_false(tmp_path, monkeypatch):
    """Stress test: When preview=False, operation MUST pass exactly 12 positional arguments,
    allowing legacy functions/mocks expecting at most 12 positional arguments to run without
    TypeError: takes from 10 to 12 positional arguments but 13 were given."""
    store = SeriesStore(tmp_path)
    series = store.create("Test Series", "bedtime", full_bible())

    called_args = []

    # A strict legacy runner mock that takes AT MOST 12 positional arguments and NO **kwargs
    def strict_legacy_fake_run(st_, sid, number, channel, provider, runner_factory, progress, is_cancelled,
                               scenes=None, check=True, refine=False, animate=False):
        called_args.append({
            "sid": sid,
            "number": number,
            "scenes": scenes,
            "check": check,
            "refine": refine,
            "animate": animate,
        })
        return {"episode": number, "status": "done"}

    monkeypatch.setattr(queue, "run_episode", strict_legacy_fake_run)

    class FakeProvider:
        async def health_check(self):
            return True

    from engine.llm.registry import llm_registry
    monkeypatch.setattr(llm_registry, "get_ollama_provider", lambda: FakeProvider())

    # Case A: payload without preview key (default preview=False)
    payload_no_preview = {
        "root": str(tmp_path),
        "series_id": series.id,
        "number": 1,
    }
    op1 = build_episode_operation("proj_1", payload_no_preview)
    res1 = op1(db=None, progress=lambda p, m: None, is_cancelled=lambda: False)
    assert res1["status"] == "done"
    assert len(called_args) == 1
    assert called_args[0]["number"] == 1

    # Case B: payload with preview=False explicitly
    payload_preview_false = {
        "root": str(tmp_path),
        "series_id": series.id,
        "number": 2,
        "preview": False,
        "extra_unknown_arg": "should_be_ignored",
    }
    op2 = build_episode_operation("proj_2", payload_preview_false)
    res2 = op2(db=None, progress=lambda p, m: None, is_cancelled=lambda: False)
    assert res2["status"] == "done"
    assert len(called_args) == 2
    assert called_args[1]["number"] == 2


def test_queue_build_operation_passes_preview_keyword_when_preview_is_true(tmp_path, monkeypatch):
    """Stress test: When preview=True, operation MUST pass preview=True via keyword argument."""
    store = SeriesStore(tmp_path)
    series = store.create("Test Series", "bedtime", full_bible())

    received_kwargs = {}

    def modern_fake_run(st_, sid, number, channel, provider, runner_factory, progress, is_cancelled,
                        scenes=None, check=True, refine=False, animate=False, **kwargs):
        received_kwargs.update(kwargs)
        received_kwargs["number"] = number
        return {"episode": number, "status": "draft", "preview": kwargs.get("preview", False)}

    monkeypatch.setattr(queue, "run_episode", modern_fake_run)

    class FakeProvider:
        async def health_check(self):
            return True

    from engine.llm.registry import llm_registry
    monkeypatch.setattr(llm_registry, "get_ollama_provider", lambda: FakeProvider())

    payload = {
        "root": str(tmp_path),
        "series_id": series.id,
        "number": 3,
        "preview": True,
    }
    op = build_episode_operation("proj_3", payload)
    res = op(db=None, progress=lambda p, m: None, is_cancelled=lambda: False)
    assert res["status"] == "draft"
    assert received_kwargs.get("preview") is True
    assert received_kwargs.get("number") == 3


def test_enqueue_episodes_preview_parameter_flow(tmp_path, monkeypatch):
    """Verify enqueue_episodes signature and spec generation for preview=False and preview=True."""
    store = SeriesStore(tmp_path)
    series = store.create("Test Series", "bedtime", full_bible())

    enqueued_jobs = []

    def fake_enqueue(project_id, job_type, operation, requires_gpu=False, max_retries=2, job_input=None):
        enqueued_jobs.append({"project_id": project_id, "job_input": job_input})
        return f"job-{len(enqueued_jobs)}"

    monkeypatch.setattr(queue, "enqueue_project_operation", fake_enqueue)

    class DummyProject:
        def __init__(self, pid):
            self.id = pid

    from engine.projects.service import project_service
    monkeypatch.setattr(project_service, "create_project", lambda *args, **kwargs: DummyProject(f"proj-{len(enqueued_jobs)+1}"))

    # Test default preview=False
    jobs_default = enqueue_episodes(None, store, series.id, count=1, publish_at=["2026-11-10T18:00:00"])
    assert len(jobs_default) == 1
    assert enqueued_jobs[0]["job_input"]["preview"] is False

    # Test explicit preview=True
    jobs_preview = enqueue_episodes(None, store, series.id, count=1, publish_at=["2026-11-11T18:00:00"], preview=True)
    assert len(jobs_preview) == 1
    assert enqueued_jobs[1]["job_input"]["preview"] is True


def test_run_episode_signature_contract():
    """Verify run_episode signature contract:
    - Exactly 13 parameters
    - 8 non-default parameters
    - 5 defaulted parameters: scenes=None, check=True, refine=False, animate=False, preview=False
    - preview default must be False."""
    sig = inspect.signature(run_episode)
    params = list(sig.parameters.values())

    param_names = [p.name for p in params]
    expected_names = [
        "store", "series_id", "number", "channel", "provider", "runner_factory",
        "progress", "is_cancelled", "scenes", "check", "refine", "animate", "preview"
    ]
    assert param_names == expected_names, f"Parameter mismatch: {param_names} vs {expected_names}"

    assert sig.parameters["scenes"].default is None
    assert sig.parameters["check"].default is True
    assert sig.parameters["refine"].default is False
    assert sig.parameters["animate"].default is False
    assert sig.parameters["preview"].default is False


def test_run_episode_preview_skips_video_and_marks_draft(tmp_path, monkeypatch):
    """Verify run_episode with preview=True marks episode as 'draft' and returns early
    without invoking video render or comic page generation."""
    store = SeriesStore(tmp_path)
    series = store.create("S", "bedtime", full_bible())
    ws = store.episode_dir(series.id, 1)

    from engine.original.models import OriginalStory
    dummy_story = OriginalStory(
        bible=full_bible(),
        scenes=[],
        panels=[],
    )

    import asyncio
    from engine.original import episode as ep_mod
    monkeypatch.setattr(ep_mod, "generate_story", lambda *args, **kwargs: asyncio.sleep(0, dummy_story))
    monkeypatch.setattr(ep_mod, "expand_story", lambda *args, **kwargs: asyncio.sleep(0, dummy_story))

    called_art = []
    def fake_generate_art(story, ws, runner, provider, progress, is_cancelled, refine=None, preview=False):
        called_art.append({"refine": refine, "preview": preview})
        return {"mean_score": 0.85, "below_threshold": []}

    monkeypatch.setattr(ep_mod.art, "generate_art", fake_generate_art)

    # Video & pages should NOT be called in preview mode
    video_called = []
    monkeypatch.setattr(ep_mod.video, "build_video", lambda *args, **kwargs: video_called.append(True))
    pages_called = []
    monkeypatch.setattr(ep_mod.pages, "build_pages", lambda *args, **kwargs: pages_called.append(True))

    progress_events = []
    res = run_episode(
        store=store,
        series_id=series.id,
        number=1,
        channel=None,
        provider=MagicMock(),
        runner_factory=lambda: MagicMock(),
        progress=lambda p, m: progress_events.append((p, m)),
        is_cancelled=lambda: False,
        preview=True,
    )

    assert res["preview"] is True
    assert res["episode"] == 1
    assert len(called_art) == 1
    assert called_art[0]["preview"] is True

    # Assert video and comic pages were skipped
    assert len(video_called) == 0
    assert len(pages_called) == 0

    # Assert episode status in store is 'draft'
    ep = store.get(series.id).episodes[0]
    assert ep.status == "draft"


def test_spec_coercion_and_validation_errors():
    """Verify EpisodeJobSpec validates types strictly and coerces truthy/falsy booleans."""
    spec_truthy = EpisodeJobSpec(root="r", series_id="s", number=1, preview=1)
    assert spec_truthy.preview is True

    spec_falsy = EpisodeJobSpec(root="r", series_id="s", number=1, preview=0)
    assert spec_falsy.preview is False

    with pytest.raises(ValidationError):
        EpisodeJobSpec(root="r", series_id="s", number=1, preview="not_a_boolean")

    with pytest.raises(ValidationError):
        # Missing required number
        EpisodeJobSpec(root="r", series_id="s")


def test_single_art_workflow_invariant_preservation():
    """Verify Single Art Workflow invariant: qwen_image_21 must remain the sole text_to_image workflow."""
    import json
    from engine.comfyui import art as comfy_art

    registry_path = Path(comfy_art.__file__).parent / "workflow_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))

    t2i_workflows = [w for w in registry if w.get("purpose") == "text_to_image"]
    assert len(t2i_workflows) == 1, f"Expected 1 text_to_image workflow, found {len(t2i_workflows)}: {t2i_workflows}"
    assert t2i_workflows[0]["id"] == "qwen_image_21"
    assert t2i_workflows[0]["id"] == ART_WORKFLOW_ID

    inpaint_workflows = [w for w in registry if w.get("purpose") == "inpaint"]
    inpaint_ids = [w["id"] for w in inpaint_workflows]
    assert "qwen_image_21_inpaint" in inpaint_ids


def test_run_episode_cancel_in_preview_mode(tmp_path, monkeypatch):
    """Verify cancellation during preview pass cleanly aborts and sets episode status to failed."""
    store = SeriesStore(tmp_path)
    series = store.create("S", "bedtime", full_bible())

    cancelled_state = [False]

    def check_cancel():
        return cancelled_state[0]

    from engine.original.models import OriginalStory
    dummy_story = OriginalStory(bible=full_bible(), scenes=[], panels=[])

    import asyncio
    from engine.original import episode as ep_mod
    monkeypatch.setattr(ep_mod, "generate_story", lambda *args, **kwargs: asyncio.sleep(0, dummy_story))
    monkeypatch.setattr(ep_mod, "expand_story", lambda *args, **kwargs: asyncio.sleep(0, dummy_story))

    def fake_generate_art(story, ws, runner, provider, progress, is_cancelled, refine=None, preview=False):
        cancelled_state[0] = True
        progress(0.5, "Triggering cancel")
        return {}

    monkeypatch.setattr(ep_mod.art, "generate_art", fake_generate_art)

    with pytest.raises(RuntimeError, match="cancelled"):
        run_episode(
            store=store,
            series_id=series.id,
            number=1,
            channel=None,
            provider=MagicMock(),
            runner_factory=lambda: MagicMock(),
            progress=lambda p, m: None,
            is_cancelled=check_cancel,
            preview=True,
        )

    ep = store.get(series.id).episodes[0]
    assert ep.status == "failed"


def test_run_episode_arbitrary_keyword_arguments_rejection(tmp_path):
    """Verify run_episode rejects unknown arbitrary keyword arguments with TypeError."""
    store = SeriesStore(tmp_path)
    series = store.create("S", "bedtime", full_bible())

    with pytest.raises(TypeError, match="unexpected keyword argument 'invalid_param'"):
        run_episode(
            store=store,
            series_id=series.id,
            number=1,
            channel=None,
            provider=MagicMock(),
            runner_factory=lambda: MagicMock(),
            progress=lambda p, m: None,
            is_cancelled=lambda: False,
            invalid_param=123,
        )

