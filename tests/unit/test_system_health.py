"""Unit tests for System Health, Capability Auditor, and Production Readiness."""
from __future__ import annotations

from fastapi.testclient import TestClient

from engine.api.app import app
from engine.system.health import (
    check_audio_studio_engines,
    check_ffmpeg,
    check_production_readiness,
    check_reels_autocut_pipeline,
    check_system_resources,
)


def test_check_ffmpeg():
    check = check_ffmpeg()
    assert check.available is True
    assert check.status in ("ok", "warning")
    assert "libx264" in check.details or "FFmpeg" in check.details


def test_check_audio_studio_engines():
    check = check_audio_studio_engines()
    assert check.available is True
    assert check.status == "ok"
    assert "foley" in check.details
    assert "ambient" in check.details
    assert "synth" in check.details


def test_check_reels_autocut_pipeline():
    check = check_reels_autocut_pipeline()
    assert check.available is True
    assert check.status == "ok"
    assert "PlayResY: 1920" not in check.details or "operational" in check.details


def test_check_system_resources():
    check = check_system_resources()
    assert check.available is True
    assert "Disk:" in check.details
    assert "RAM:" in check.details


def test_check_production_readiness():
    report = check_production_readiness()
    assert isinstance(report.ready, bool)
    assert len(report.checks) >= 6
    assert "ffmpeg" in report.checks
    assert "audio_studio" in report.checks
    assert "reels" in report.checks
    assert "resources" in report.checks


def test_api_system_readiness_endpoint():
    client = TestClient(app)
    res = client.get("/api/system/readiness")
    assert res.status_code == 200
    data = res.json()
    assert "ready" in data
    assert "checks" in data
    assert "summary" in data
    assert "recommendations" in data
