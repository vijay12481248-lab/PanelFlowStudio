"""Unit test for Phase 0: Environment, Hardware, and Commercial Licensing Audit."""
from __future__ import annotations

import json
from pathlib import Path

from tools.inspector.audit_environment import run_full_audit


def test_phase_0_environment_audit(tmp_path):
    """Verifies that Phase 0 audit executes cleanly and confirms environment readiness."""
    report_path = tmp_path / "test_audit_report.json"
    report = run_full_audit(output_json_path=str(report_path))

    assert report["overall_ready"] is True
    assert report["hardware"]["cuda_available"] is True
    assert len(report["hardware"]["devices"]) > 0
    assert "RTX 5060 Ti" in report["hardware"]["devices"][0]["name"]

    # Check commercial licensing clearance
    assert report["licensing_summary"]["all_models_commercial_cleared"] is True

    # Check model presence
    models = report["comfyui"]["models"]
    for model_key in ("yunet", "sface", "dwpose_body", "dwpose_det", "animagine_inpaint"):
        assert model_key in models
        assert models[model_key]["present"] is True
        assert models[model_key]["commercial_cleared"] is True

    # Check report file written
    assert report_path.is_file()
    saved_data = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved_data["overall_ready"] is True
