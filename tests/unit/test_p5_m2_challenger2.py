"""Empirical Challenge & Stress Test Suite: Milestone M2.

Challenger 2 independent verification for:
1. ComfyWorkflowRegistry().load("anime_alpha_matting") across parameter variations and patch slots.
2. SHA256 checksum mismatch detection, file tampering, and structural integrity.
3. ComfyRunner matting preflight and graceful offline fallback:
   - Offline ComfyUI server
   - Missing model files (e.g. birefnet-general.safetensors)
   - Missing custom nodes (e.g. RemoveBackground, LoadBackgroundRemovalModel)
   - Runtime execution failures (URLError, timeout, download failure)
   - Delegation and fallback inside rigging.remove_background
4. _resolve_upload handling of bytes, paths, and PIL Images (RGB, RGBA, L, 1).
5. Edge cases: 1x1 pixels, solid color, odd dimensions, defringe toggling, and mask extraction.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch
from urllib.error import URLError

import numpy as np
from PIL import Image
import pytest

from engine.comfyui.client import ComfyUIClient, ComfyUIError
from engine.comfyui.registry import ComfyWorkflowRegistry, WorkflowRegistryError
from engine.comfyui.service import (
    ComfyImageGenerationError,
    _history_images,
    _patch_workflow,
    _validate_output_dimensions,
)
from engine.original import art
from engine.original import rigging
from engine.original.rigging import MattingResult


# ==============================================================================
# 1. ComfyWorkflowRegistry().load("anime_alpha_matting") & Patch Parameter Tests
# ==============================================================================

def test_registry_load_anime_alpha_matting_structure():
    """Verify registry loads anime_alpha_matting with exact node mapping and SHA256 integrity."""
    reg = ComfyWorkflowRegistry()
    assert "anime_alpha_matting" in reg._entries, "anime_alpha_matting not in registry entries"

    entry = reg.metadata("anime_alpha_matting")
    assert entry["id"] == "anime_alpha_matting"
    assert entry["filename"] == "anime_alpha_matting.api.json"
    assert "birefnet-general.safetensors" in entry["model_files"]
    assert entry["gpu_vram_mb"] == 4000
    assert entry["requires_gpu"] is True

    workflow, checksum = reg.load("anime_alpha_matting")
    assert checksum == entry["sha256"]
    assert len(workflow) == 8

    # Verify all expected nodes and their classes exist
    expected_nodes = {
        "1": "LoadImage",
        "2": "LoadBackgroundRemovalModel",
        "3": "RemoveBackground",
        "4": "JoinImageWithAlpha",
        "5": "SaveImage",
        "6": "CLIPTextEncode",
        "7": "CLIPTextEncode",
        "8": "RandomNoise",
    }
    for node_id, class_type in expected_nodes.items():
        assert node_id in workflow, f"Node {node_id} missing from workflow"
        assert workflow[node_id]["class_type"] == class_type, (
            f"Node {node_id} class_type {workflow[node_id]['class_type']} != {class_type}"
        )

    # Verify data pipeline links
    assert workflow["3"]["inputs"]["bg_removal_model"] == ["2", 0]
    assert workflow["3"]["inputs"]["image"] == ["1", 0]
    assert workflow["4"]["inputs"]["image"] == ["1", 0]
    assert workflow["4"]["inputs"]["alpha"] == ["3", 0]
    assert workflow["5"]["inputs"]["images"] == ["4", 0]


def test_workflow_registry_patching_all_parameters():
    """Verify _patch_workflow correctly patches prompt, neg, seed, prefix, reference_image."""
    reg = ComfyWorkflowRegistry()
    workflow, _ = reg.load("anime_alpha_matting")
    entry = reg.metadata("anime_alpha_matting")
    patch_slots = entry["patch_slots"]

    # Parameter permutation 1: Standard values
    patched1 = _patch_workflow(
        workflow,
        patch_slots,
        prompt="clean anime girl, transparent cutout",
        negative_prompt="background, artifacts, halos",
        width=0,
        height=0,
        seed=42,
        prefix="panelflow_alpha",
        reference_image="uploaded_frame_01.png",
    )
    assert patched1["1"]["inputs"]["image"] == "uploaded_frame_01.png"
    assert patched1["5"]["inputs"]["filename_prefix"] == "panelflow_alpha"
    assert patched1["6"]["inputs"]["text"] == "clean anime girl, transparent cutout"
    assert patched1["7"]["inputs"]["text"] == "background, artifacts, halos"
    assert patched1["8"]["inputs"]["noise_seed"] == 42

    # Parameter permutation 2: Unicode text, negative seed, large values, custom paths
    patched2 = _patch_workflow(
        workflow,
        patch_slots,
        prompt="キャラクター・透かし・日本語テスト ★ (Aria in cyber armor)",
        negative_prompt="余分な線, ぼやけ",
        width=1024,
        height=1024,
        seed=9223372036854775807,  # Max signed 64-bit int
        prefix="custom_subfolder/matting_test_99",
        reference_image="pf_abcdef1234567890.png",
    )
    assert patched2["1"]["inputs"]["image"] == "pf_abcdef1234567890.png"
    assert patched2["5"]["inputs"]["filename_prefix"] == "custom_subfolder/matting_test_99"
    assert "★" in patched2["6"]["inputs"]["text"]
    assert "余分な線" in patched2["7"]["inputs"]["text"]
    assert patched2["8"]["inputs"]["noise_seed"] == 9223372036854775807

    # Verify immutability: Original workflow must not be mutated
    assert workflow["1"]["inputs"]["image"] == "input.png"
    assert workflow["6"]["inputs"]["text"] == ""
    assert workflow["8"]["inputs"]["noise_seed"] == 0


def test_workflow_patching_missing_reference_image_fails():
    """Verify omitting reference_image fails since anime_alpha_matting declares it in patch_slots."""
    reg = ComfyWorkflowRegistry()
    workflow, _ = reg.load("anime_alpha_matting")
    entry = reg.metadata("anime_alpha_matting")
    patch_slots = entry["patch_slots"]

    with pytest.raises(ComfyImageGenerationError, match="Approved workflow does not declare every required patch slot"):
        _patch_workflow(
            workflow,
            patch_slots,
            prompt="",
            negative_prompt="",
            width=0,
            height=0,
            seed=0,
            prefix="test",
            reference_image=None,  # Not provided
        )


def test_registry_dimension_policy_validation():
    """Verify _validate_patch_slots strictly enforces exact dimension policy constraints."""
    reg = ComfyWorkflowRegistry()
    workflow, _ = reg.load("anime_alpha_matting")
    entry = reg.metadata("anime_alpha_matting")

    # Valid policy
    ComfyWorkflowRegistry._validate_patch_slots("anime_alpha_matting", workflow, entry)

    # Invalid policy: min > max
    bad_entry = copy.deepcopy(entry)
    bad_entry["dimension_policy"]["min"] = 3000
    bad_entry["dimension_policy"]["max"] = 1000
    with pytest.raises(WorkflowRegistryError, match="exact dimension policy"):
        ComfyWorkflowRegistry._validate_patch_slots("anime_alpha_matting", workflow, bad_entry)

    # Invalid policy: non-exact mode
    bad_entry = copy.deepcopy(entry)
    bad_entry["dimension_policy"]["mode"] = "approximate"
    with pytest.raises(WorkflowRegistryError, match="exact dimension policy"):
        ComfyWorkflowRegistry._validate_patch_slots("anime_alpha_matting", workflow, bad_entry)


# ==============================================================================
# 2. SHA256 Checksum Tampering & Structural Integrity Tests
# ==============================================================================

def test_tampering_workflow_file_content_rejected(tmp_path):
    """Verify bit-flip or alteration of workflow json content causes checksum mismatch."""
    # Create mock workflow dir with slightly modified anime_alpha_matting.api.json
    real_wf_path = Path("engine/comfyui/workflows/anime_alpha_matting.api.json")
    real_bytes = real_wf_path.read_bytes()

    # Tamper by appending a single byte (space)
    tampered_bytes = real_bytes + b" "
    mock_wf_file = tmp_path / "anime_alpha_matting.api.json"
    mock_wf_file.write_bytes(tampered_bytes)

    # Initialize client pointing to tmp_path as workflow dir
    mock_client = ComfyUIClient(workflow_dir=tmp_path)
    # Monkeypatch api_workflow_root to point to tmp_path
    mock_client.api_workflow_root = lambda: tmp_path

    reg = ComfyWorkflowRegistry(mock_client)
    with pytest.raises(WorkflowRegistryError, match="Workflow checksum mismatch for anime_alpha_matting"):
        reg.load("anime_alpha_matting")


def test_tampering_registry_sha256_rejected():
    """Verify altering entry sha256 checksum fails load validation."""
    reg = ComfyWorkflowRegistry()
    # Tamper entry sha256
    reg._entries["anime_alpha_matting"]["sha256"] = "0000000000000000000000000000000000000000000000000000000000000000"
    with pytest.raises(WorkflowRegistryError, match="Workflow checksum mismatch for anime_alpha_matting"):
        reg.load("anime_alpha_matting")


def test_tampering_corrupt_json_rejected(tmp_path):
    """Verify syntactically corrupt JSON is rejected with WorkflowRegistryError."""
    corrupt_file = tmp_path / "anime_alpha_matting.api.json"
    corrupt_file.write_bytes(b'{"1": {invalid_json_here!')
    # Compute sha256 of corrupt content so checksum check passes and json parser is exercised
    corrupt_sha = hashlib.sha256(corrupt_file.read_bytes()).hexdigest()

    mock_client = ComfyUIClient(workflow_dir=tmp_path)
    mock_client.api_workflow_root = lambda: tmp_path
    reg = ComfyWorkflowRegistry(mock_client)
    reg._entries["anime_alpha_matting"]["sha256"] = corrupt_sha

    with pytest.raises(WorkflowRegistryError, match="Workflow JSON is invalid"):
        reg.load("anime_alpha_matting")


def test_tampering_patch_slot_mismatch_rejected():
    """Verify tampering with patch slots (node_id, class_type, input) triggers validation failure."""
    reg = ComfyWorkflowRegistry()
    workflow, _ = reg.load("anime_alpha_matting")
    entry = reg.metadata("anime_alpha_matting")

    # 1. Missing node
    tampered_entry = copy.deepcopy(entry)
    tampered_entry["patch_slots"]["reference_image"]["node_id"] = "99"
    with pytest.raises(WorkflowRegistryError, match="node is missing"):
        ComfyWorkflowRegistry._validate_patch_slots("anime_alpha_matting", workflow, tampered_entry)

    # 2. Wrong class_type
    tampered_entry = copy.deepcopy(entry)
    tampered_entry["patch_slots"]["reference_image"]["class_type"] = "LoadImageMask"
    with pytest.raises(WorkflowRegistryError, match="class_type does not match approved metadata"):
        ComfyWorkflowRegistry._validate_patch_slots("anime_alpha_matting", workflow, tampered_entry)

    # 3. Missing input attribute
    tampered_entry = copy.deepcopy(entry)
    tampered_entry["patch_slots"]["reference_image"]["input"] = "nonexistent_input"
    with pytest.raises(WorkflowRegistryError, match="input is missing"):
        ComfyWorkflowRegistry._validate_patch_slots("anime_alpha_matting", workflow, tampered_entry)

    # 4. Missing required slot (e.g. filename_prefix removed)
    tampered_entry = copy.deepcopy(entry)
    del tampered_entry["patch_slots"]["filename_prefix"]
    with pytest.raises(WorkflowRegistryError, match="must declare exact patch slots"):
        ComfyWorkflowRegistry._validate_patch_slots("anime_alpha_matting", workflow, tampered_entry)


def test_tampering_path_traversal_rejected():
    """Verify path traversal in filename is rejected by security validator."""
    reg = ComfyWorkflowRegistry()
    reg._entries["anime_alpha_matting"]["filename"] = "../../../etc/passwd"
    with pytest.raises(WorkflowRegistryError, match="missing or unsafe"):
        reg.load("anime_alpha_matting")


# ==============================================================================
# 3. ComfyRunner Matting Preflight & Graceful Offline Fallback Tests
# ==============================================================================

class MockOfflineComfyClient:
    """Mock ComfyUI client that simulates server being offline."""
    base_url = "http://127.0.0.1:8188/"
    timeout_s = 5.0

    def api_workflow_root(self):
        return Path("engine/comfyui/workflows")

    def _workflow_root(self):
        return Path("engine/comfyui/workflows")

    def capabilities(self):
        return {
            "available": False,
            "endpoint": self.base_url.rstrip("/"),
            "workflow_dir": None,
            "workflow_files": [],
            "models": {},
            "errors": ["Connection refused: ComfyUI server is offline"],
        }

    def system_stats(self):
        raise URLError("Connection refused")

    def submit_prompt(self, wf):
        raise URLError("Connection refused: ComfyUI server is offline")


class MockBaseSdxlClient:
    """Mock client with standard SDXL generation ready, but matting workflow variations."""
    base_url = "http://127.0.0.1:8188/"
    timeout_s = 5.0

    def __init__(self, matting_model: bool = False, matting_node: bool = False):
        self.matting_model = matting_model
        self.matting_node = matting_node

    def api_workflow_root(self):
        return Path("engine/comfyui/workflows")

    def _workflow_root(self):
        return Path("engine/comfyui/workflows")

    def capabilities(self):
        nodes = [
            "CheckpointLoaderSimple", "CLIPTextEncode", "EmptyLatentImage",
            "KSampler", "VAEDecode", "SaveImage", "LoadImage", "RandomNoise",
        ]
        if self.matting_node:
            nodes.extend(["LoadBackgroundRemovalModel", "RemoveBackground", "JoinImageWithAlpha"])

        models = {
            "checkpoints": ["animagine-xl-4.0.safetensors"],
            "background_removal": ["birefnet-general.safetensors"] if self.matting_model else [],
        }
        return {
            "available": True,
            "endpoint": self.base_url.rstrip("/"),
            "workflow_dir": "E:/VIJAY SEKAR/ComfyUI/workflow",
            "workflow_files": ["anime_sdxl.api.json", "anime_alpha_matting.api.json"],
            "node_names": nodes,
            "models": models,
            "errors": [],
        }

    def system_stats(self):
        return {"system": {"os": "windows"}}


def test_registry_preflight_offline_comfyui():
    """Verify registry preflight returns ready=False when ComfyUI is completely offline."""
    client = MockOfflineComfyClient()
    reg = ComfyWorkflowRegistry(client)
    pre = reg.preflight("anime_alpha_matting")
    assert pre["workflow_id"] == "anime_alpha_matting"
    assert pre["ready"] is False
    assert "birefnet-general.safetensors" in pre["missing_models"]
    assert "RemoveBackground" in pre["missing_nodes"]


def test_runner_matting_preflight_missing_model():
    """Verify ComfyRunner detects missing matting model: matting_wf is None and matting_ready is False."""
    client = MockBaseSdxlClient(matting_model=False, matting_node=True)
    runner = art.ComfyRunner(client=client, engine="sdxl")
    assert runner.matting_wf is None
    assert runner.matting_ready is False

    reg = ComfyWorkflowRegistry(client)
    pre = reg.preflight("anime_alpha_matting")
    assert pre["ready"] is False
    assert "birefnet-general.safetensors" in pre["missing_models"]


def test_runner_matting_preflight_missing_node():
    """Verify ComfyRunner detects missing matting node: matting_wf is None and matting_ready is False."""
    client = MockBaseSdxlClient(matting_model=True, matting_node=False)
    runner = art.ComfyRunner(client=client, engine="sdxl")
    assert runner.matting_wf is None
    assert runner.matting_ready is False

    reg = ComfyWorkflowRegistry(client)
    pre = reg.preflight("anime_alpha_matting")
    assert pre["ready"] is False
    assert "RemoveBackground" in pre["missing_nodes"]


def test_runner_remove_background_offline_fallback(tmp_path):
    """Verify ComfyRunner.remove_background cleanly falls back to local Python engine when matting is offline."""
    client = MockBaseSdxlClient(matting_model=False, matting_node=False)
    runner = art.ComfyRunner(client=client, engine="sdxl")
    assert runner.matting_wf is None
    assert runner.matting_ready is False

    # Create synthetic test character image: white background with red square subject
    w, h = 80, 80
    rgb = np.full((h, w, 3), 255, dtype=np.uint8)
    rgb[20:60, 20:60] = [200, 30, 30]  # Red character subject
    img = Image.fromarray(rgb, "RGB")

    # Test with PIL.Image.Image
    res_bytes_pil = runner.remove_background(img, defringe=True)
    assert isinstance(res_bytes_pil, bytes)
    out_im = Image.open(io.BytesIO(res_bytes_pil))
    assert out_im.mode == "RGBA"
    assert out_im.size == (w, h)
    out_arr = np.array(out_im)
    assert np.any(out_arr[:, :, 3] < 255), "Expected transparent pixels in background"
    assert np.any(out_arr[:, :, 3] > 0), "Expected opaque pixels in subject"

    # Test with bytes
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    res_bytes_raw = runner.remove_background(buf.getvalue(), defringe=True)
    assert isinstance(res_bytes_raw, bytes)
    out_im_bytes = Image.open(io.BytesIO(res_bytes_raw))
    assert out_im_bytes.mode == "RGBA"

    # Test with Path
    test_path = tmp_path / "test_char.png"
    img.save(test_path)
    res_bytes_path = runner.remove_background(test_path, defringe=True)
    assert isinstance(res_bytes_path, bytes)
    out_im_path = Image.open(io.BytesIO(res_bytes_path))
    assert out_im_path.mode == "RGBA"


def test_runner_remove_background_execution_failure_fallback():
    """Verify if ComfyUI crashes during prompt execution, runner cleanly falls back to local engine."""
    class CrashingPromptClient:
        base_url = "http://127.0.0.1:8188/"
        def submit_prompt(self, wf):
            raise URLError("ComfyUI server crashed mid-execution!")

    class OnlinePreflightRunner:
        def __init__(self):
            self.client = CrashingPromptClient()
            reg = ComfyWorkflowRegistry()
            # Simulate matting_wf was loaded
            self.matting_wf = (reg.load("anime_alpha_matting")[0], reg.metadata("anime_alpha_matting"))
        def _resolve_upload(self, item):
            return "uploaded_input.png"

    runner = OnlinePreflightRunner()
    runner.remove_background = art.ComfyRunner.remove_background.__get__(runner, OnlinePreflightRunner)

    w, h = 60, 60
    rgb = np.full((h, w, 3), 255, dtype=np.uint8)
    rgb[15:45, 15:45] = [50, 150, 50]
    test_im = Image.fromarray(rgb, "RGB")

    # Calling remove_background should NOT raise URLError, but fall back cleanly
    result_bytes = runner.remove_background(test_im, defringe=True)
    assert isinstance(result_bytes, bytes)
    out_im = Image.open(io.BytesIO(result_bytes))
    assert out_im.mode == "RGBA"
    assert out_im.size == (w, h)


def test_rigging_remove_background_delegation_and_fallback():
    """Verify rigging.remove_background coordinates with runner and gracefully falls back if runner raises."""
    # 1. Runner that succeeds
    w, h = 50, 50
    rgba = np.full((h, w, 4), 255, dtype=np.uint8)
    rgba[:10, :, 3] = 0
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, format="PNG")
    mock_rgba_bytes = buf.getvalue()

    class SuccessfulRunner:
        matting_wf = ({}, {})
        def remove_background(self, img, defringe=True):
            return mock_rgba_bytes

    res1 = rigging.remove_background(Image.fromarray(rgba, "RGBA"), runner=SuccessfulRunner())
    assert isinstance(res1, MattingResult)
    assert res1.has_alpha is True
    assert res1.width == w
    assert res1.height == h
    assert res1.rgba_bytes == mock_rgba_bytes

    # 2. Runner that throws an unhandled exception
    class ExplodingRunner:
        matting_wf = ({}, {})
        def remove_background(self, img, defringe=True):
            raise RuntimeError("Fatal hardware failure in ComfyUI GPU backend")

    # Must catch exception and seamlessly fall back to _local_matting
    test_img = Image.new("RGB", (60, 60), (255, 255, 255))
    res2 = rigging.remove_background(test_img, runner=ExplodingRunner(), defringe=True)
    assert isinstance(res2, MattingResult)
    assert res2.has_alpha is True
    assert res2.width == 60
    assert res2.height == 60
    out_im = res2.to_image()
    assert out_im.mode == "RGBA"


# ==============================================================================
# 4. _resolve_upload Input Types & Behavior Tests
# ==============================================================================

def test_resolve_upload_with_bytes(tmp_path):
    """Verify _resolve_upload handles raw image bytes."""
    runner = art.ComfyRunner.__new__(art.ComfyRunner)
    uploaded_records = []

    def mock_upload_bytes(data: bytes, suffix: str = ".png") -> str:
        digest = hashlib.sha256(data).hexdigest()[:16]
        filename = f"pf_{digest}{suffix}"
        uploaded_records.append((filename, len(data)))
        return filename

    runner._upload_bytes = mock_upload_bytes

    raw_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    res = runner._resolve_upload(raw_bytes)
    assert res.startswith("pf_")
    assert res.endswith(".png")
    assert len(uploaded_records) == 1
    assert uploaded_records[0][0] == res


def test_resolve_upload_with_paths(tmp_path):
    """Verify _resolve_upload handles Path instances."""
    runner = art.ComfyRunner.__new__(art.ComfyRunner)
    uploaded_records = []

    def mock_upload_bytes(data: bytes, suffix: str = ".png") -> str:
        digest = hashlib.sha256(data).hexdigest()[:16]
        filename = f"pf_{digest}{suffix}"
        uploaded_records.append((filename, len(data)))
        return filename

    runner._upload_bytes = mock_upload_bytes
    runner._upload = art.ComfyRunner._upload.__get__(runner, art.ComfyRunner)

    sample_file = tmp_path / "sample_test.png"
    sample_file.write_bytes(b"sample_image_data_12345")

    res = runner._resolve_upload(sample_file)
    assert res.startswith("pf_")
    assert len(uploaded_records) == 1


def test_resolve_upload_with_pil_images():
    """Verify _resolve_upload handles PIL.Image.Image across modes (RGB, RGBA, L, 1)."""
    runner = art.ComfyRunner.__new__(art.ComfyRunner)
    uploaded_payloads = []

    def mock_upload_bytes(data: bytes, suffix: str = ".png") -> str:
        digest = hashlib.sha256(data).hexdigest()[:16]
        filename = f"pf_{digest}{suffix}"
        uploaded_payloads.append((filename, data))
        return filename

    runner._upload_bytes = mock_upload_bytes

    # RGB
    im_rgb = Image.new("RGB", (32, 32), (255, 0, 0))
    res_rgb = runner._resolve_upload(im_rgb)
    assert res_rgb.startswith("pf_")

    # RGBA
    im_rgba = Image.new("RGBA", (32, 32), (0, 255, 0, 128))
    res_rgba = runner._resolve_upload(im_rgba)
    assert res_rgba.startswith("pf_")

    # Grayscale L
    im_l = Image.new("L", (32, 32), 128)
    res_l = runner._resolve_upload(im_l)
    assert res_l.startswith("pf_")

    # 1-bit
    im_1 = Image.new("1", (32, 32), 1)
    res_1 = runner._resolve_upload(im_1)
    assert res_1.startswith("pf_")

    assert len(uploaded_payloads) == 4
    # Check that all payloads are valid PNGs readable by PIL
    for _, payload in uploaded_payloads:
        decoded = Image.open(io.BytesIO(payload))
        assert decoded.format == "PNG"


def test_resolve_upload_with_strings_and_none(tmp_path):
    """Verify _resolve_upload handles string paths, already uploaded names, and None."""
    runner = art.ComfyRunner.__new__(art.ComfyRunner)
    runner._upload_bytes = lambda data, suffix=".png": f"pf_{hashlib.sha256(data).hexdigest()[:16]}{suffix}"
    runner._upload = art.ComfyRunner._upload.__get__(runner, art.ComfyRunner)

    # 1. None
    assert runner._resolve_upload(None) is None

    # 2. Existing file path as string
    existing_file = tmp_path / "existing.png"
    existing_file.write_bytes(b"existing_file_content")
    res_existing = runner._resolve_upload(str(existing_file))
    assert res_existing.startswith("pf_")

    # 3. Already uploaded server filename string (does not exist as local file)
    server_filename = "pf_0123456789abcdef.png"
    res_server = runner._resolve_upload(server_filename)
    assert res_server == server_filename


# ==============================================================================
# 5. Stress Testing Edge Cases & Failure Modes
# ==============================================================================

def test_matting_edge_cases():
    """Stress test remove_background on 1x1, solid color, odd dimensions, and large images."""
    runner = art.ComfyRunner(client=MockBaseSdxlClient(matting_model=False, matting_node=False), engine="sdxl")

    # 1. 1x1 pixel image
    im_1x1 = Image.new("RGB", (1, 1), (255, 255, 255))
    res_1x1 = runner.remove_background(im_1x1, defringe=True)
    assert isinstance(res_1x1, bytes)
    out_1x1 = Image.open(io.BytesIO(res_1x1))
    assert out_1x1.size == (1, 1)
    assert out_1x1.mode == "RGBA"

    # 2. Solid color image (zero foreground contrast)
    im_solid = Image.new("RGB", (64, 64), (128, 128, 128))
    res_solid = runner.remove_background(im_solid, defringe=True)
    assert isinstance(res_solid, bytes)
    out_solid = Image.open(io.BytesIO(res_solid))
    assert out_solid.size == (64, 64)
    assert out_solid.mode == "RGBA"

    # 3. Odd dimensions (prime numbers: 73x119)
    im_odd = Image.new("RGB", (73, 119), (240, 240, 240))
    # Draw simple foreground box
    draw_arr = np.array(im_odd)
    draw_arr[20:80, 20:50] = [10, 10, 200]
    im_odd = Image.fromarray(draw_arr, "RGB")
    res_odd = runner.remove_background(im_odd, defringe=True)
    out_odd = Image.open(io.BytesIO(res_odd))
    assert out_odd.size == (73, 119)
    assert out_odd.mode == "RGBA"

    # 4. Defringe False vs True comparison
    res_no_defringe = runner.remove_background(im_odd, defringe=False)
    assert isinstance(res_no_defringe, bytes)
    out_no_def = Image.open(io.BytesIO(res_no_defringe))
    assert out_no_def.mode == "RGBA"


def test_defringe_alpha_eliminates_white_halo():
    """Verify defringe_alpha decontaminates white-halo-polluted edge pixels with foreground color."""
    # Create 20x20 image: center 10x10 is pure dark blue [0, 0, 180]
    # Border 1px surrounding center has semi-transparent alpha=128 and white-polluted RGB [128, 128, 218]
    # Outer area is alpha=0, white [255, 255, 255]
    h, w = 20, 20
    rgb = np.full((h, w, 3), 255, dtype=np.uint8)
    alpha = np.zeros((h, w), dtype=np.uint8)

    # Solid core
    rgb[6:14, 6:14] = [0, 0, 180]
    alpha[6:14, 6:14] = 255

    # Fringe gutter (polluted with white background)
    fringe_y, fringe_x = [5, 14], [5, 14]
    rgb[5:15, 5:15] = [128, 128, 218]
    alpha[5:15, 5:15] = 128
    # Reset solid core
    rgb[6:14, 6:14] = [0, 0, 180]
    alpha[6:14, 6:14] = 255

    # Defringe
    decon_rgb, decon_alpha = rigging.defringe_alpha(rgb, alpha, threshold=240)

    # Verification:
    # 1. Alpha channel must remain identical
    assert np.array_equal(decon_alpha, alpha), "Alpha channel was altered during defringing"
    # 2. Solid core RGB must remain identical
    assert np.all(decon_rgb[6:14, 6:14] == [0, 0, 180]), "Solid core color was modified"
    # 3. Fringe edge pixel at (5, 5) must be decontaminated to authentic blue [0, 0, 180] instead of [128, 128, 218]
    assert np.array_equal(decon_rgb[5, 5], [0, 0, 180]), (
        f"Fringe pixel not decontaminated: expected [0, 0, 180], got {decon_rgb[5, 5]}"
    )


def test_concurrency_thread_safety_matting():
    """Verify multiple concurrent threads can run remove_background without race conditions."""
    import concurrent.futures

    runner = art.ComfyRunner(client=MockBaseSdxlClient(matting_model=False, matting_node=False), engine="sdxl")

    def run_worker(worker_id: int):
        dim = 40 + (worker_id * 5)
        # Create unique colored square
        arr = np.full((dim, dim, 3), 255, dtype=np.uint8)
        arr[10:30, 10:30] = [(worker_id * 20) % 255, (worker_id * 40) % 255, 180]
        test_im = Image.fromarray(arr, "RGB")
        res_bytes = runner.remove_background(test_im, defringe=True)
        out_im = Image.open(io.BytesIO(res_bytes))
        assert out_im.size == (dim, dim)
        assert out_im.mode == "RGBA"
        return worker_id, out_im.size

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(run_worker, i) for i in range(12)]
        for f in concurrent.futures.as_completed(futures):
            worker_id, size = f.result()
            assert size == (40 + worker_id * 5, 40 + worker_id * 5)


def test_resolve_upload_palette_and_la_modes():
    """Verify _resolve_upload handles palette ('P') and luminance-alpha ('LA') images."""
    runner = art.ComfyRunner.__new__(art.ComfyRunner)
    uploaded = []
    runner._upload_bytes = lambda data, suffix=".png": (uploaded.append(data), f"pf_{len(uploaded)}.png")[1]

    # Palette mode
    im_p = Image.new("P", (24, 24))
    res_p = runner._resolve_upload(im_p)
    assert res_p.startswith("pf_")

    # LA mode (grayscale + alpha)
    im_la = Image.new("LA", (24, 24), (200, 128))
    res_la = runner._resolve_upload(im_la)
    assert res_la.startswith("pf_")

    assert len(uploaded) == 2
    for payload in uploaded:
        decoded = Image.open(io.BytesIO(payload))
        assert decoded.format == "PNG"


def test_matting_result_model_contract():
    """Verify MattingResult pydantic model methods and properties."""
    w, h = 30, 30
    rgba = Image.new("RGBA", (w, h), (100, 150, 200, 255))
    mask = Image.new("L", (w, h), 255)

    buf_rgba, buf_mask = io.BytesIO(), io.BytesIO()
    rgba.save(buf_rgba, format="PNG")
    mask.save(buf_mask, format="PNG")

    result = MattingResult(
        rgba_bytes=buf_rgba.getvalue(),
        mask_bytes=buf_mask.getvalue(),
        has_alpha=True,
        halo_free=True,
        width=w,
        height=h,
    )
    assert result.has_alpha is True
    assert result.halo_free is True
    assert result.width == w
    assert result.height == h

    im = result.to_image()
    assert im.mode == "RGBA"
    assert im.size == (w, h)

    m = result.to_mask_image()
    assert m.mode == "L"
    assert m.size == (w, h)


def test_extract_subject_and_prop_masks_edge_cases():
    """Verify extract_subject_and_prop_masks handles single, multiple, and empty components."""
    # 1. Image with two distinct objects: character (large) and sword/prop (small)
    h, w = 120, 120
    rgb = np.full((h, w, 3), 255, dtype=np.uint8)
    # Large subject (center)
    rgb[30:90, 40:80] = [30, 30, 200]
    # Small prop (isolated at right)
    rgb[40:70, 95:110] = [200, 150, 30]

    masks = rigging.extract_subject_and_prop_masks(Image.fromarray(rgb, "RGB"))
    assert "subject" in masks
    assert "prop" in masks
    assert "background" in masks
    assert "foreground" in masks
    for key, mask_im in masks.items():
        assert isinstance(mask_im, Image.Image)
        assert mask_im.mode == "L"
        assert mask_im.size == (w, h)

    # Subject mask has non-zero pixels
    sub_arr = np.array(masks["subject"])
    assert np.count_nonzero(sub_arr) > 0

    # Prop mask has non-zero pixels
    prop_arr = np.array(masks["prop"])
    assert np.count_nonzero(prop_arr) > 0

    # Prop and subject do not overlap
    assert np.count_nonzero(np.bitwise_and(sub_arr > 0, prop_arr > 0)) == 0
