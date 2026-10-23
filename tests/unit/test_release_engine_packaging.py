"""Fail closed before publishing an incomplete standalone runtime."""
import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def packaging():
    script = Path(__file__).resolve().parents[2] / "scripts/build_standalone_engine.py"
    spec = importlib.util.spec_from_file_location("engine_packaging", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_internal_directory_without_bootloader_is_not_a_runtime(packaging, tmp_path):
    (tmp_path / "_internal").mkdir()
    with pytest.raises(RuntimeError, match="panelflow-engine"):
        packaging.validate_runtime(tmp_path)


def test_coldstart_gate_refuses_missing_executable(packaging, tmp_path):
    with pytest.raises(RuntimeError, match="panelflow-engine"):
        packaging.smoke_runtime(tmp_path, scratch_root=tmp_path / "smoke")


def test_failed_coldstart_does_not_replace_installer_resources(packaging, tmp_path, monkeypatch):
    from types import SimpleNamespace

    dist = tmp_path / "dist"
    runtime = dist / "panelflow-engine"
    (runtime / "_internal").mkdir(parents=True)
    (runtime / "panelflow-engine.exe").write_bytes(b"unit-test-placeholder")
    (runtime / "_internal/dependency").write_bytes(b"unit-test-placeholder")
    resources = tmp_path / "resources"
    target = resources / "engine_runtime"
    target.mkdir(parents=True)
    sentinel = target / "existing-runtime"
    sentinel.write_text("preserve")
    monkeypatch.setattr(packaging, "DIST_DIR", dist)
    monkeypatch.setattr(packaging, "RESOURCES_DIR", resources)
    monkeypatch.setattr(packaging, "RELEASE_DIR", tmp_path / "release")
    monkeypatch.setattr(packaging.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0))

    def fail_coldstart(*args, **kwargs):
        raise RuntimeError("coldstart gate failed")

    monkeypatch.setattr(packaging, "smoke_runtime", fail_coldstart)
    with pytest.raises(RuntimeError, match="coldstart gate failed"):
        packaging.main([])
    assert sentinel.read_text() == "preserve"


def test_empty_dependency_directory_is_rejected(packaging, tmp_path):
    (tmp_path / "panelflow-engine.exe").write_bytes(b"MZ")
    (tmp_path / "_internal").mkdir()
    with pytest.raises(RuntimeError, match="dependencies"):
        packaging.validate_runtime(tmp_path)
