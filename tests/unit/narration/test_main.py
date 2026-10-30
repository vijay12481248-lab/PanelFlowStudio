from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from engine.narration import __main__ as cli


class _Provider:
    endpoint_url = "http://box:11434"

    def __init__(self, healthy):
        self.healthy = healthy

    async def health_check(self):
        return self.healthy


def _patch(monkeypatch, provider=None, loader=None):
    # the registry stub has no get_active_provider: any cloud/mock fallback would raise AttributeError
    monkeypatch.setattr(cli, "llm_registry", SimpleNamespace(get_ollama_provider=lambda: provider))
    db = SimpleNamespace(get=lambda *a: SimpleNamespace(workspace_path="."))
    monkeypatch.setattr(cli, "SessionLocal", lambda: nullcontext(db))
    monkeypatch.setattr(cli, "load_chapter_inputs", loader or (lambda d, p: object()))


def test_unhealthy_ollama_exits_1_with_one_line(monkeypatch, capsys):
    _patch(monkeypatch, _Provider(False))
    assert cli.main(["run", "abc"]) == 1
    assert capsys.readouterr().out.strip() == "Ollama is not reachable at http://box:11434"


@pytest.mark.parametrize("exc", [KeyError("abc"), ValueError("project abc has no usable panels")])
def test_unknown_project_or_no_panels_exits_1_without_traceback(monkeypatch, capsys, exc):
    def boom(d, p):
        raise exc

    _patch(monkeypatch, _Provider(True), boom)
    assert cli.main(["run", "abc"]) == 1
    out = capsys.readouterr().out.strip()
    assert "\n" not in out and "abc" in out

def test_cli_prints_line_stats(monkeypatch, capsys):
    from pathlib import Path

    from engine.narration.artifacts import CritiqueReport, ScriptIR, ScriptLine
    from engine.narration.compiler import CompileResult

    _patch(monkeypatch, _Provider(True))
    script = ScriptIR(project_id="p", lines=[
        ScriptLine(line_id=f"L{k}", panel_id=f"p{k}", text="some words go here", facts_used=[], kind="narration",
                   status="fallback" if k == 1 else "passed") for k in (1, 2, 3)])
    report = CritiqueReport(revision=0, lines=[], coverage=2 / 3, pace_estimate=1.0, repetition=0, gate="pass")
    seen = {}

    class _Compiler:
        def __init__(self, *a):
            pass

        async def run(self, inputs, workspace, stop_after):
            seen["stop_after"] = stop_after
            return CompileResult("r", "pass", [], Path("."), None, None, script, report)

    monkeypatch.setattr(cli, "NarrationCompiler", _Compiler)
    monkeypatch.setattr(cli, "load_roles", lambda: {})
    monkeypatch.setattr(cli, "ProviderModelClient", lambda *a: None)
    monkeypatch.setattr(cli, "ModelScheduler", lambda *a: None)
    assert cli.main(["run", "abc"]) == 0
    out = capsys.readouterr().out
    assert seen["stop_after"] == "write"
    assert "lines: 3" in out and "fallbacks: 1" in out and "coverage: 0.67" in out