import asyncio
import json

from engine.narration.artifacts import SeriesBible
from engine.narration.bible.store import BibleStore
from engine.narration.cache import ArtifactCache
from engine.narration.compiler import NarrationCompiler
from engine.narration.runtime.client import StepModelError
from engine.narration.runtime.roles import RoleConfig
from engine.narration.runtime.scheduler import ModelScheduler
from engine.narration.steps import understand
from engine.narration.steps.perceive import PanelFactsDraft
from engine.narration.steps.understand import (
    MergeDraft, WindowBeatDraft, WindowDraft, WindowSceneDraft,
)
from tests.unit.narration.fakes import FakeModelClient, RecordingUnloader, make_chapter_inputs


def _draft(is_story=True):
    return PanelFactsDraft(is_story=is_story, shot="medium", characters_visible=[], action="A man stands.",
                           emotion="tense", speakers=[], sfx=[], setting="hall", importance=3, confidence=0.9)


def _window():
    return WindowDraft(scenes=[WindowSceneDraft(
        first=1, last=3, goal="g", conflict="c", turn="t",
        beats=[WindowBeatDraft(panels=[1, 2, 3], what_happens="w", function="setup", intensity=0.5)])])


def _merge():
    return MergeDraft(hook="h", chapter_summary="s", character_resolutions={}, bible_proposals=[])


def _compiler(tmp_path, responses):
    client = FakeModelClient(responses)
    roles = {r: RoleConfig(model="qwen3.5:9b", temperature=0.1, max_tokens=512, concurrency=1)
             for r in ("vision", "planner")}
    sched = ModelScheduler(roles, RecordingUnloader())
    comp = NarrationCompiler(client, sched, ArtifactCache(tmp_path / "cache"), BibleStore(tmp_path / "bibles"))
    return comp


def _go(tmp_path, comp, **kw):
    inputs = make_chapter_inputs(tmp_path, 3, {})
    return asyncio.run(comp.run(inputs, tmp_path / "ws", **kw))


def _ok():
    return {"vision": [_draft()] * 3, "planner": [_window(), _merge()]}


def test_full_run_writes_artifacts_and_passes(tmp_path):
    result = _go(tmp_path, _compiler(tmp_path, _ok()))
    assert result.gate == "pass"
    for name in ("panel_facts.json", "beat_sheet.json", "run.json"):
        assert (result.run_dir / name).exists()
    run = json.loads((result.run_dir / "run.json").read_text(encoding="utf-8"))
    assert [s["step"] for s in run["steps"]] == ["perceive", "understand"]
    assert {s["model"] for s in run["steps"]} == {"qwen3.5:9b"}
    assert run["gate"] == "pass"


def test_stop_after_perceive_writes_no_beat_sheet(tmp_path):
    result = _go(tmp_path, _compiler(tmp_path, {"vision": [_draft()] * 3}), stop_after="perceive")
    assert result.beat_sheet is None and result.gate == "pass"
    assert not (result.run_dir / "beat_sheet.json").exists()
    assert (result.run_dir / "panel_facts.json").exists()


def test_needs_review_sets_review_gate_with_reasons(tmp_path):
    result = _go(tmp_path, _compiler(tmp_path, {"vision": [_draft(False)] * 3}))
    assert result.gate == "review" and result.reasons == ["no story panels"]
    assert not (result.run_dir / "beat_sheet.json").exists()


def test_model_failure_marks_run_failed_and_rerun_resumes_from_cache(tmp_path):
    first = _go(tmp_path, _compiler(tmp_path, {"vision": [_draft()] * 3,
                                               "planner": [StepModelError("planner", "boom")]}))
    assert first.gate == "failed" and first.reasons[0].startswith("planner")
    assert not (first.run_dir / "beat_sheet.json").exists()

    second = _go(tmp_path, _compiler(tmp_path, {"vision": [], "planner": [_window(), _merge()]}))
    assert second.gate == "pass"
    perceive = json.loads((second.run_dir / "run.json").read_text(encoding="utf-8"))["steps"][0]
    assert perceive["model_calls"] == 0 and perceive["cache_hits"] == 3


def test_run_json_is_valid_after_each_step(tmp_path, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(understand, "understand_chapter", boom)
    comp = _compiler(tmp_path, {"vision": [_draft()] * 3})
    inputs = make_chapter_inputs(tmp_path, 3, {})
    try:
        asyncio.run(comp.run(inputs, tmp_path / "ws"))
    except RuntimeError:
        pass
    (run_json,) = (tmp_path / "ws" / "narration").glob("*/run.json")
    run = json.loads(run_json.read_text(encoding="utf-8"))
    assert run["steps"][0]["step"] == "perceive"
    assert run["gate"] == "failed" and run["reasons"] == ["kaboom"]
