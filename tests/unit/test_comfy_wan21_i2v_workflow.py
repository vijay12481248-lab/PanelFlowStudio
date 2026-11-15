"""Unit tests for Wan2.1 14B Image-to-Video ComfyUI workflow, model manifest, and download tooling."""
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from engine.comfyui.client import ComfyUIClient
from engine.comfyui.download_wan21 import (
    HF_BASE_URL,
    WAN_MODELS_MANIFEST,
    compute_sha256,
    download_model,
    inspect_manifest,
    main as download_main,
    verify_models,
)
from engine.comfyui.registry import ComfyWorkflowRegistry
from engine.comfyui.service import _patch_workflow


def test_wan21_workflow_registered_and_sha256_matches():
    """Verify wan21_14b_i2v is registered in workflow_registry.json with exact checksum."""
    registry = ComfyWorkflowRegistry()
    workflow, checksum = registry.load("wan21_14b_i2v")

    assert isinstance(workflow, dict)
    assert len(workflow) == 14

    # Verify sha256 matches exact bytes of workflow JSON file
    wf_path = Path(__file__).resolve().parents[2] / "engine" / "comfyui" / "workflows" / "wan21_14b_i2v.api.json"
    expected_sha = hashlib.sha256(wf_path.read_bytes()).hexdigest()
    assert checksum == expected_sha
    assert checksum == "ed361731f3d21fc09d3ff481d08a3a5d737e2a6bd58f1f3feffc2dc5189fc1e6"

    meta = registry.metadata("wan21_14b_i2v")
    assert meta["id"] == "wan21_14b_i2v"
    assert meta["purpose"] == "image_to_video"
    assert meta["gpu_vram_mb"] == 14000
    assert meta["requires_gpu"] is True
    assert meta["dimension_policy"] == {
        "mode": "exact",
        "min": 256,
        "max": 2048,
        "multiple_of": 16,
    }

    # Verify model files and required nodes
    assert "wan2.1_i2v_480p_14B_fp8_scaled.safetensors" in meta["model_files"]
    assert "umt5_xxl_fp8_e4m3fn_scaled.safetensors" in meta["model_files"]
    assert "wan_2.1_vae.safetensors" in meta["model_files"]
    assert "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors" in meta["model_files"]

    expected_nodes = {
        "UNETLoader",
        "ModelSamplingSD3",
        "CLIPLoader",
        "VAELoader",
        "CLIPVisionLoader",
        "LoadImage",
        "CLIPVisionEncode",
        "CLIPTextEncode",
        "WanImageToVideo",
        "KSampler",
        "VAEDecode",
        "CreateVideo",
        "SaveVideo",
    }
    assert expected_nodes.issubset(set(meta["required_nodes"]))


def test_wan21_workflow_patch_slots_substitution():
    """Verify all patch slots substitute into expected nodes without mutating source workflow."""
    registry = ComfyWorkflowRegistry()
    workflow, _ = registry.load("wan21_14b_i2v")
    meta = registry.metadata("wan21_14b_i2v")

    patched = _patch_workflow(
        workflow,
        meta["patch_slots"],
        prompt="A dynamic anime scene of a warrior swinging a sword, rain splattering, neon rim lighting",
        negative_prompt="blurry, distorted, jitter, bad anatomy, static shot",
        width=832,
        height=480,
        seed=12345678,
        prefix="video/panelflow_wan_test",
        reference_image="shot_001_panel.png",
    )

    # 1. reference_image -> Node 6 (LoadImage)
    assert patched["6"]["inputs"]["image"] == "shot_001_panel.png"

    # 2. prompt -> Node 8 (CLIPTextEncode positive)
    assert patched["8"]["inputs"]["text"] == "A dynamic anime scene of a warrior swinging a sword, rain splattering, neon rim lighting"

    # 3. negative_prompt -> Node 9 (CLIPTextEncode negative)
    assert patched["9"]["inputs"]["text"] == "blurry, distorted, jitter, bad anatomy, static shot"

    # 4. width & height -> Node 10 (WanImageToVideo)
    assert patched["10"]["inputs"]["width"] == 832
    assert patched["10"]["inputs"]["height"] == 480

    # 5. seed -> Node 11 (KSampler)
    assert patched["11"]["inputs"]["seed"] == 12345678

    # 6. filename_prefix -> Node 14 (SaveVideo)
    assert patched["14"]["inputs"]["filename_prefix"] == "video/panelflow_wan_test"

    # Verify original workflow immutability
    assert workflow["6"]["inputs"]["image"] == "panel_input.png"
    assert workflow["11"]["inputs"]["seed"] == 0
    assert workflow["14"]["inputs"]["filename_prefix"] == "video/panelflow_wan21"


def test_wan21_node_topology_and_wiring():
    """Verify the native node graph connections between all 14 nodes."""
    registry = ComfyWorkflowRegistry()
    wf, _ = registry.load("wan21_14b_i2v")

    # UNETLoader -> ModelSamplingSD3
    assert wf["2"]["inputs"]["model"] == ["1", 0]
    assert wf["2"]["inputs"]["shift"] == 8.0

    # ModelSamplingSD3 -> KSampler
    assert wf["11"]["inputs"]["model"] == ["2", 0]

    # CLIPLoader -> CLIPTextEncode (pos & neg)
    assert wf["8"]["inputs"]["clip"] == ["3", 0]
    assert wf["9"]["inputs"]["clip"] == ["3", 0]

    # CLIPVisionLoader & LoadImage -> CLIPVisionEncode
    assert wf["7"]["inputs"]["clip_vision"] == ["5", 0]
    assert wf["7"]["inputs"]["image"] == ["6", 0]
    assert wf["7"]["inputs"]["crop"] == "none"

    # WanImageToVideo wiring
    assert wf["10"]["inputs"]["positive"] == ["8", 0]
    assert wf["10"]["inputs"]["negative"] == ["9", 0]
    assert wf["10"]["inputs"]["vae"] == ["4", 0]
    assert wf["10"]["inputs"]["clip_vision_output"] == ["7", 0]
    assert wf["10"]["inputs"]["start_image"] == ["6", 0]
    assert wf["10"]["inputs"]["length"] == 81

    # KSampler receives WanImageToVideo conditionings & latent
    assert wf["11"]["inputs"]["positive"] == ["10", 0]
    assert wf["11"]["inputs"]["negative"] == ["10", 1]
    assert wf["11"]["inputs"]["latent_image"] == ["10", 2]
    assert wf["11"]["inputs"]["sampler_name"] == "uni_pc"
    assert wf["11"]["inputs"]["scheduler"] == "simple"

    # KSampler -> VAEDecode
    assert wf["12"]["inputs"]["samples"] == ["11", 0]
    assert wf["12"]["inputs"]["vae"] == ["4", 0]

    # VAEDecode -> CreateVideo -> SaveVideo
    assert wf["13"]["inputs"]["images"] == ["12", 0]
    assert wf["13"]["inputs"]["fps"] == 16.0
    assert wf["14"]["inputs"]["video"] == ["13", 0]


def test_wan21_model_manifest_structure():
    """Verify model manifest entries have exact hashes, byte sizes, and HuggingFace URLs."""
    assert len(WAN_MODELS_MANIFEST) == 5

    manifest_by_id = {m["id"]: m for m in WAN_MODELS_MANIFEST}
    assert "wan2.1_diffusion_480p" in manifest_by_id
    assert "wan2.1_text_encoder" in manifest_by_id
    assert "wan2.1_vae" in manifest_by_id
    assert "wan2.1_clip_vision_optional" in manifest_by_id
    assert "wan2.1_diffusion_720p_optional" in manifest_by_id

    dit480 = manifest_by_id["wan2.1_diffusion_480p"]
    assert dit480["filename"] == "wan2.1_i2v_480p_14B_fp8_scaled.safetensors"
    assert dit480["size_bytes"] == 16401356938
    assert dit480["sha256"] == "b2de21b99b2e72cb0ff15253b07e926f26e7cf1b7e229efc32f94ad1f1ed9395"
    assert dit480["subfolder"] == "diffusion_models"
    assert dit480["required"] is True

    text_enc = manifest_by_id["wan2.1_text_encoder"]
    assert text_enc["filename"] == "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
    assert text_enc["size_bytes"] == 6735906897
    assert text_enc["sha256"] == "c3355d30191f1f066b26d93fba017ae9809dce6c627dda5f6a66eaa651204f68"
    assert text_enc["subfolder"] == "text_encoders"
    assert text_enc["required"] is True

    vae = manifest_by_id["wan2.1_vae"]
    assert vae["filename"] == "wan_2.1_vae.safetensors"
    assert vae["size_bytes"] == 253815318
    assert vae["sha256"] == "2fc39d31359a4b0a64f55876d8ff7fa8d780956ae2cb13463b0223e15148976b"
    assert vae["subfolder"] == "vae"
    assert vae["required"] is True

    for m in WAN_MODELS_MANIFEST:
        assert m["url"].startswith(HF_BASE_URL)
        assert len(m["sha256"]) == 64
        assert int(m["sha256"], 16) > 0


def test_wan21_inspect_manifest(tmp_path):
    """Verify inspect_manifest calculations for total bytes and file counts."""
    res_480 = inspect_manifest(tmp_path, variant="480p")
    assert res_480["variant"] == "480p"
    assert res_480["total_files"] == 3
    assert res_480["total_bytes"] == 16401356938 + 6735906897 + 253815318
    assert res_480["total_gb"] == 21.78

    res_720 = inspect_manifest(tmp_path, variant="720p")
    assert res_720["variant"] == "720p"
    assert res_720["total_files"] == 3
    assert any(item["filename"] == "wan2.1_i2v_720p_14B_fp8_scaled.safetensors" for item in res_720["items"])



def test_wan21_verify_models_with_mock_filesystem(tmp_path):
    """Verify verify_models reports MISSING, SIZE_MISMATCH, and VERIFIED_OK."""
    models_dir = tmp_path / "models"
    diff_dir = models_dir / "diffusion_models"
    enc_dir = models_dir / "text_encoders"
    vae_dir = models_dir / "vae"
    diff_dir.mkdir(parents=True)
    enc_dir.mkdir(parents=True)
    vae_dir.mkdir(parents=True)

    # 1. Initially missing
    v1 = verify_models(tmp_path, variant="480p", quick=True)
    assert v1["ready"] is False
    assert all(r["status"] == "MISSING" for r in v1["results"])

    # 2. File exists with wrong size
    diff_file = diff_dir / "wan2.1_i2v_480p_14B_fp8_scaled.safetensors"
    diff_file.write_bytes(b"short content")
    v2 = verify_models(tmp_path, variant="480p", quick=True)
    assert v2["ready"] is False
    diff_res = next(r for r in v2["results"] if r["filename"] == diff_file.name)
    assert "SIZE_MISMATCH" in diff_res["status"]

    # 3. All files exist with exact size in quick mode
    enc_file = enc_dir / "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
    vae_file = vae_dir / "wan_2.1_vae.safetensors"

    with patch.object(Path, "stat") as mock_stat:
        manifest_map = {m["filename"]: m["size_bytes"] for m in WAN_MODELS_MANIFEST}

        def fake_stat(self):
            orig_stat = os.stat(tmp_path)
            if self.name in manifest_map:
                mock = MagicMock()
                mock.st_size = manifest_map[self.name]
                return mock
            return orig_stat

        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.stat", fake_stat):
                v3 = verify_models(tmp_path, variant="480p", quick=True)
                assert v3["ready"] is True
                assert all("OK" in r["status"] for r in v3["results"])


def test_wan21_download_cli_approval_protection(tmp_path):
    """Verify AGENTS.md rule: download without explicit --approve exits with code 2 in non-interactive environment."""
    # When --download is run without --approve in non-interactive mode:
    code = download_main(["--download", "--comfy-dir", str(tmp_path)])
    assert code == 2

    # --inspect returns 0
    code_inspect = download_main(["--inspect", "--comfy-dir", str(tmp_path)])
    assert code_inspect == 0

    # --verify on empty dir returns 1
    code_verify = download_main(["--verify", "--quick", "--comfy-dir", str(tmp_path)])
    assert code_verify == 1


def test_wan21_preserves_single_text_to_image_invariant():
    """Verify that Wan2.1 I2V does not violate the AGENTS.md single text_to_image rule."""
    reg_path = Path(__file__).resolve().parents[2] / "engine" / "comfyui" / "workflow_registry.json"
    entries = json.loads(reg_path.read_text(encoding="utf-8"))

    t2i = [e["id"] for e in entries if e.get("purpose") == "text_to_image"]
    assert t2i == ["qwen_image_21"]

    wan_entry = next((e for e in entries if e["id"] == "wan21_14b_i2v"), None)
    assert wan_entry is not None
    assert wan_entry["purpose"] == "image_to_video"
