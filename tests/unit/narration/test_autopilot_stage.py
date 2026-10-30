import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.config.settings import Settings, settings
from engine.narration import autopilot_stage as stage
from engine.narration.compiler import CompileResult
from engine.pipeline.autopilot import AutoPilotRunner


def test_flag_default_is_legacy(monkeypatch):
    monkeypatch.delenv("PANELFLOW_NARRATION_ENGINE", raising=False)
    assert Settings().narration_engine == "legacy"
    monkeypatch.setenv("PANELFLOW_NARRATION_ENGINE", "compiler")
    assert Settings().narration_engine == "compiler"


def _patch(monkeypatch, gate, reasons=()):
    seen = {}

    class _Compiler:
        async def run(self, inputs, workspace, stop_after):
            seen["stop_after"] = stop_after
            return CompileResult("r", gate, list(reasons), Path("."), None, "sheet", "script", None, "tl", {}, "plan", ["take"])

    async def provider():
        return object()

    monkeypatch.setattr(stage, "SessionLocal", lambda: __import__("contextlib").nullcontext(
        SimpleNamespace(get=lambda *a: SimpleNamespace(workspace_path="ws"))))
    monkeypatch.setattr(stage, "load_chapter_inputs", lambda db, pid: "inputs")
    monkeypatch.setattr(stage, "_local_provider", provider)
    monkeypatch.setattr(stage, "_make_compiler", lambda *a: _Compiler())
    monkeypatch.setattr(stage, "apply_to_project", lambda *a: seen.setdefault("apply", a) and "vs-1")
    return seen


def test_compiler_stage_applies_on_pass(monkeypatch):
    seen = _patch(monkeypatch, "pass")
    asyncio.run(stage.run_compiler_stage("proj"))
    assert seen["stop_after"] == "timeline"
    assert seen["apply"][1:] == ("proj", "tl", "script", "sheet", ["take"], Path("ws"), "plan")


@pytest.mark.parametrize("gate,exc,text", [("review", stage.NarrationNeedsReview, "Narration needs review: a; b"),
                                           ("failed", RuntimeError, "a; b")])
def test_compiler_stage_review_raises(monkeypatch, gate, exc, text):
    seen = _patch(monkeypatch, gate, ["a", "b"])
    with pytest.raises(exc) as info:
        asyncio.run(stage.run_compiler_stage("proj"))
    assert str(info.value) == text and "apply" not in seen


def test_autopilot_story_script_skipped_under_flag(monkeypatch):
    monkeypatch.setattr(settings, "narration_engine", "compiler")
    ran = []
    runner = SimpleNamespace(project_id="proj", log=lambda m: ran.append(("log", m)),
                             update_stage=lambda sid, **kw: ran.append((sid, kw["status"])))
    asyncio.run(AutoPilotRunner._run_stage_story(runner, True))
    asyncio.run(AutoPilotRunner._run_stage_script(runner, True))
    assert ran == [("log", "skipped: narration compiler"), ("story", "SKIPPED"),
                   ("log", "skipped: narration compiler"), ("script", "SKIPPED")]


def test_autopilot_audio_runs_compiler_under_flag(monkeypatch):
    monkeypatch.setattr(settings, "narration_engine", "compiler")
    ran = []

    async def fake(pid):
        ran.append(pid)
        raise stage.NarrationNeedsReview(["x"])

    monkeypatch.setattr(stage, "run_compiler_stage", fake)
    runner = SimpleNamespace(project_id="proj", log=lambda m: None, update_stage=lambda sid, **kw: None)
    with pytest.raises(stage.NarrationNeedsReview, match="Narration needs review: x"):
        asyncio.run(AutoPilotRunner._run_stage_audio(runner, True))
    assert ran == ["proj"]
