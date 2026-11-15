"""Adversarial stress-test suite for engine/comfyui/download_wan21.py.

Written by challenger_wan_m1_1 to stress-test:
1. Approval gate enforcement in non-interactive and interactive CLI invocations.
2. verify_models with corrupted files, size mismatches, and SHA256 mismatches.
3. Quick mode vs full SHA256 verification (silent corruption blind spot).
4. Edge cases: Windows Path.rename FileExistsError, corrupt file skip bug, HTTP 416 on retry.
5. Consistency between download manifest and ComfyUI workflow registry requirements.
"""
from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import urllib.error

import pytest

from engine.comfyui.download_wan21 import (
    DEFAULT_COMFY_ROOT,
    HF_BASE_URL,
    WAN_MODELS_MANIFEST,
    compute_sha256,
    download_model,
    inspect_manifest,
    main as download_main,
    verify_models,
)
from engine.comfyui.registry import ComfyWorkflowRegistry


# =====================================================================
# 1. APPROVAL ENFORCEMENT & CLI INVOCATION TESTS
# =====================================================================

def test_cli_non_interactive_download_without_approve_exits_code_2(tmp_path):
    """Verify that in non-interactive environment (CI/headless), --download without --approve returns 2."""
    with patch("sys.stdin.isatty", return_value=False):
        code = download_main(["--download", "--comfy-dir", str(tmp_path)])
        assert code == 2


def test_cli_subprocess_non_interactive_download_exits_code_2(tmp_path):
    """Empirically verify via subprocess that real OS process with non-tty stdin exits with 2 and downloads 0 bytes."""
    proc = subprocess.run(
        [sys.executable, "engine/comfyui/download_wan21.py", "--download", "--comfy-dir", str(tmp_path)],
        stdin=subprocess.PIPE,
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[2]),
    )
    assert proc.returncode == 2
    assert "Non-interactive download requires explicit --approve flag" in proc.stdout
    # Verify no files created
    assert not (tmp_path / "models").exists() or not list((tmp_path / "models").rglob("*"))


def test_challenge_eoferror_handled_gracefully(tmp_path):
    """Verify that if stdin is a TTY but reaches EOF or KeyboardInterrupt,
    it is handled gracefully and returns exit code 2.
    """
    with patch("sys.stdin.isatty", return_value=True):
        with patch("builtins.input", side_effect=EOFError("EOF when reading a line")):
            code = download_main(["--download", "--comfy-dir", str(tmp_path)])
            assert code == 2

    with patch("sys.stdin.isatty", return_value=True):
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            code = download_main(["--download", "--comfy-dir", str(tmp_path)])
            assert code == 2


@pytest.mark.parametrize("declined_input", ["n", "N", "no", "NO", "cancel", "", "random text"])
def test_cli_interactive_prompt_rejection_exits_code_0(tmp_path, declined_input):
    """Verify that when user declines interactive prompt, script exits with 0 and does not download."""
    with patch("sys.stdin.isatty", return_value=True):
        with patch("builtins.input", return_value=declined_input):
            code = download_main(["--download", "--comfy-dir", str(tmp_path)])
            assert code == 0
            # Ensure no download happened
            assert not (tmp_path / "models").exists()


def test_cli_invalid_arguments_exits_code_2(tmp_path):
    """Verify argparse rejects unknown flags with exit code 2."""
    with pytest.raises(SystemExit) as exc:
        download_main(["--nonexistent-flag"])
    assert exc.value.code == 2


def test_cli_invalid_variant_exits_code_2(tmp_path):
    """Verify argparse rejects invalid variants like 1080p with exit code 2."""
    with pytest.raises(SystemExit) as exc:
        download_main(["--variant", "1080p"])
    assert exc.value.code == 2


def test_cli_inspect_always_exits_code_0(tmp_path):
    """Verify --inspect reports manifest safely without downloading and returns 0."""
    code = download_main(["--inspect", "--comfy-dir", str(tmp_path)])
    assert code == 0


def test_cli_approve_without_download_defaults_to_inspect(tmp_path):
    """Verify passing --approve without --download does not trigger downloads; defaults to inspect."""
    code = download_main(["--approve", "--comfy-dir", str(tmp_path)])
    assert code == 0
    assert not (tmp_path / "models").exists()


# =====================================================================
# 2. VERIFY_MODELS ADVERSARIAL INTEGRITY TESTS
# =====================================================================

def test_verify_models_all_missing(tmp_path):
    """Verify completely empty directory returns ready=False and MISSING for all models."""
    res = verify_models(tmp_path, variant="480p", quick=False)
    assert res["ready"] is False
    assert len(res["results"]) == 3
    for r in res["results"]:
        assert r["status"] == "MISSING"


def test_verify_models_zero_byte_file(tmp_path):
    """Verify that a 0-byte corrupted file is detected as SIZE_MISMATCH in both quick and full modes."""
    diff_file = tmp_path / "models" / "diffusion_models" / "wan2.1_i2v_480p_14B_fp8_scaled.safetensors"
    diff_file.parent.mkdir(parents=True)
    diff_file.touch()

    # Quick mode
    res_quick = verify_models(tmp_path, variant="480p", quick=True)
    assert res_quick["ready"] is False
    r0 = next(r for r in res_quick["results"] if r["filename"] == diff_file.name)
    assert "SIZE_MISMATCH" in r0["status"]
    assert "got 0" in r0["status"]

    # Full mode
    res_full = verify_models(tmp_path, variant="480p", quick=False)
    assert res_full["ready"] is False
    r1 = next(r for r in res_full["results"] if r["filename"] == diff_file.name)
    assert "SIZE_MISMATCH" in r1["status"]


def test_verify_models_off_by_one_size_mismatch(tmp_path):
    """Verify off-by-one size (+1 and -1 byte) is rejected as SIZE_MISMATCH."""
    vae_meta = next(m for m in WAN_MODELS_MANIFEST if m["id"] == "wan2.1_vae")
    target_size = vae_meta["size_bytes"]
    vae_file = tmp_path / "models" / "vae" / "wan_2.1_vae.safetensors"
    vae_file.parent.mkdir(parents=True)

    # Test size - 1
    vae_file.write_bytes(b"x")
    with patch("pathlib.Path.stat") as mock_stat:
        mock = MagicMock()
        mock.st_size = target_size - 1
        mock_stat.return_value = mock
        res = verify_models(tmp_path, variant="480p", quick=True)
        vae_res = next(r for r in res["results"] if r["filename"] == vae_file.name)
        assert f"SIZE_MISMATCH (got {target_size - 1}, expected {target_size})" in vae_res["status"]

    # Test size + 1
    with patch("pathlib.Path.stat") as mock_stat:
        mock = MagicMock()
        mock.st_size = target_size + 1
        mock_stat.return_value = mock
        res = verify_models(tmp_path, variant="480p", quick=True)
        vae_res = next(r for r in res["results"] if r["filename"] == vae_file.name)
        assert f"SIZE_MISMATCH (got {target_size + 1}, expected {target_size})" in vae_res["status"]


def test_quick_mode_vs_full_mode_payload_corruption(tmp_path):
    """CRITICAL ADVERSARIAL TEST:
    Demonstrates that quick mode passes a corrupted file if file size matches,
    whereas full verification correctly catches SHA256 HASH_MISMATCH.
    """
    models_dir = tmp_path / "models"
    vae_meta = next(m for m in WAN_MODELS_MANIFEST if m["id"] == "wan2.1_vae")
    vae_file = models_dir / "vae" / vae_meta["filename"]
    vae_file.parent.mkdir(parents=True)

    # Create dummy content with wrong sha256
    dummy_payload = b"A" * 1024
    vae_file.write_bytes(dummy_payload)

    # Mock st_size to match expected_bytes, but real bytes on disk are corrupt
    with patch("pathlib.Path.stat") as mock_stat:
        mock = MagicMock()
        mock.st_size = vae_meta["size_bytes"]
        mock_stat.return_value = mock

        # 1. Quick mode: reports OK (size matched) -> BLIND SPOT
        res_quick = verify_models(tmp_path, variant="480p", quick=True)
        vae_res_q = next(r for r in res_quick["results"] if r["filename"] == vae_file.name)
        assert vae_res_q["status"] == "OK (size matched)"

        # 2. Full mode: calculates SHA256 and detects HASH_MISMATCH
        res_full = verify_models(tmp_path, variant="480p", quick=False)
        vae_res_f = next(r for r in res_full["results"] if r["filename"] == vae_file.name)
        assert "HASH_MISMATCH" in vae_res_f["status"]
        assert res_full["ready"] is False


def test_cli_verify_returns_1_on_corruption(tmp_path):
    """Verify CLI --verify returns exit code 1 when corrupted files exist."""
    diff_file = tmp_path / "models" / "diffusion_models" / "wan2.1_i2v_480p_14B_fp8_scaled.safetensors"
    diff_file.parent.mkdir(parents=True)
    diff_file.write_bytes(b"corrupt")

    code = download_main(["--verify", "--comfy-dir", str(tmp_path)])
    assert code == 1


# =====================================================================
# 3. DOWNLOAD RESUMPTION & FAILURE MODES (CHALLENGE ATTACKS)
# =====================================================================

def test_challenge_windows_rename_collision_resolved_by_replace(tmp_path):
    """Verify that when dest_path already exists (e.g. invalid size) and part_path
    is completed, dest_path is cleanly replaced without FileExistsError.
    """
    dest = tmp_path / "models" / "vae" / "wan_2.1_vae.safetensors"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"stale corrupted dest")

    part = dest.with_suffix(dest.suffix + ".part")
    valid_payload = b"new complete download"
    import hashlib
    valid_hash = hashlib.sha256(valid_payload).hexdigest()
    part.write_bytes(valid_payload)

    item = {
        "name": "Wan2.1 VAE",
        "filename": "wan_2.1_vae.safetensors",
        "size_bytes": len(valid_payload),
        "size_gb": 0.01,
        "expected_sha256": valid_hash,
        "url": "http://mock/vae.safetensors",
    }

    mock_resp = MagicMock()
    mock_resp.read.return_value = b""
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        success = download_model(item, dest)
        assert success is True
        assert dest.exists()
        assert dest.read_bytes() == valid_payload


def test_challenge_corrupt_existing_file_verified_and_redownloaded(tmp_path):
    """Verify that when dest_path exists with exact expected size but corrupted hash,
    download_model detects the mismatch, unlinks the corrupt file, and initiates re-download.
    """
    dest = tmp_path / "models" / "vae" / "wan_2.1_vae.safetensors"
    dest.parent.mkdir(parents=True)

    target_bytes = 253815318
    dest.write_bytes(b"corrupt dummy content")

    item = {
        "name": "Wan2.1 VAE",
        "filename": "wan_2.1_vae.safetensors",
        "size_bytes": target_bytes,
        "size_gb": 0.24,
        "expected_sha256": "2fc39d31359a4b0a64f55876d8ff7fa8d780956ae2cb13463b0223e15148976b",
        "url": "http://mock/vae.safetensors",
    }

    with patch("pathlib.Path.stat") as mock_stat:
        mock = MagicMock()
        mock.st_size = target_bytes
        mock_stat.return_value = mock

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.side_effect = [b"new_valid_bytes", b""]
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            with patch("engine.comfyui.download_wan21.compute_sha256") as mock_sha:
                # 1st call: verify existing dest -> corrupt
                # 2nd call: verify new part download -> valid
                mock_sha.side_effect = ["corrupt_hash_000", item["expected_sha256"]]
                success = download_model(item, dest)
                assert success is True
                # Re-download was triggered because corrupt file was detected
                mock_urlopen.assert_called_once()


def test_challenge_retry_after_hash_mismatch_avoids_http_416(tmp_path):
    """Verify that when a corrupt part_path with full size exists, download_model detects
    the corruption, unlinks the corrupt part, resets existing_bytes to 0, and avoids sending
    Range: bytes={total}- (which would cause HTTP 416).
    """
    dest = tmp_path / "models" / "vae" / "wan_2.1_vae.safetensors"
    dest.parent.mkdir(parents=True)
    part = dest.with_suffix(dest.suffix + ".part")

    corrupt_payload = b"Z" * 1000
    part.write_bytes(corrupt_payload)

    valid_payload = b"A" * 1000
    import hashlib
    valid_hash = hashlib.sha256(valid_payload).hexdigest()

    item = {
        "name": "Wan2.1 VAE",
        "filename": "wan_2.1_vae.safetensors",
        "size_bytes": 1000,
        "size_gb": 0.001,
        "expected_sha256": valid_hash,
        "url": "http://mock/vae.safetensors",
    }

    with patch("urllib.request.Request") as mock_req:
        mock_resp = MagicMock()
        mock_resp.read.side_effect = [valid_payload, b""]
        mock_resp.__enter__.return_value = mock_resp
        with patch("urllib.request.urlopen", return_value=mock_resp):
            success = download_model(item, dest)
            assert success is True
            # Verify Range header was NOT sent because corrupt part was cleared
            called_headers = mock_req.call_args[1]["headers"]
            assert "Range" not in called_headers
            assert dest.exists()
            assert dest.read_bytes() == valid_payload


def test_challenge_hash_mismatch_unlinks_part_file(tmp_path):
    """Verify that when a downloaded payload fails SHA256 checksum verification,
    the .part file is deleted immediately to prevent poisoning future retries.
    """
    dest = tmp_path / "models" / "vae" / "wan_2.1_vae.safetensors"
    dest.parent.mkdir(parents=True)
    part = dest.with_suffix(dest.suffix + ".part")

    corrupt_payload = b"corrupted bytes"

    item = {
        "name": "Wan2.1 VAE",
        "filename": "wan_2.1_vae.safetensors",
        "size_bytes": len(corrupt_payload),
        "size_gb": 0.001,
        "expected_sha256": "0" * 64,
        "url": "http://mock/vae.safetensors",
    }

    mock_resp = MagicMock()
    mock_resp.read.side_effect = [corrupt_payload, b""]
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        success = download_model(item, dest)
        assert success is False
        # Part file must have been deleted to avoid HTTP 416 on retry
        assert not part.exists()
        assert not dest.exists()


# =====================================================================
# 4. WORKFLOW & MANIFEST CONSISTENCY AUDIT
# =====================================================================

def test_manifest_vs_workflow_clip_vision_alignment():
    """Verify workflow and registry use CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors which
    is aligned with the user's ComfyUI installation.
    """
    registry = ComfyWorkflowRegistry()
    meta = registry.metadata("wan21_14b_i2v")
    assert "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors" in meta["model_files"]
    assert "clip_vision_h.safetensors" not in meta["model_files"]

    # Verify that ComfyUI possesses the aligned clip vision weights
    clip_path = DEFAULT_COMFY_ROOT / "models" / "clip_vision" / "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors"
    if (DEFAULT_COMFY_ROOT / "models" / "clip_vision").exists():
        assert clip_path.exists(), "Expected CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors to be present in ComfyUI"
