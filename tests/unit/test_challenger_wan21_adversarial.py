"""Adversarial stress-testing suite for Wan2.1 14B I2V workflow and registry schema.

Authored by challenger_wan_m1_2.
Verifies checksum sensitivity, dimension policies, patch slot mutations,
immutability, and purpose invariants under adversarial edge cases.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from engine.comfyui.art import ComfyImageGenerationError, _validate_output_dimensions
from engine.comfyui.client import ComfyUIClient
from engine.comfyui.registry import ComfyWorkflowRegistry, WorkflowRegistryError
from engine.comfyui.service import _patch_workflow


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture
def registry() -> ComfyWorkflowRegistry:
    return ComfyWorkflowRegistry()


@pytest.fixture
def wan_workflow_path(repo_root: Path) -> Path:
    return repo_root / "engine" / "comfyui" / "workflows" / "wan21_14b_i2v.api.json"


@pytest.fixture
def wan_raw_bytes(wan_workflow_path: Path) -> bytes:
    return wan_workflow_path.read_bytes()


# ==============================================================================
# 1. CHECKSUM SENSITIVITY ADVERSARIAL TESTS
# ==============================================================================


def test_adversarial_checksum_single_byte_mutation_rejected(tmp_path: Path, wan_raw_bytes: bytes):
    """Mutate a single byte in wan21_14b_i2v.api.json and verify WorkflowRegistryError."""
    fake_api_dir = tmp_path / "workflows"
    fake_api_dir.mkdir(parents=True)
    wf_file = fake_api_dir / "wan21_14b_i2v.api.json"

    # 1. Flip a single character in the shift value: "shift": 8.0 -> "shift": 8.1
    mutated_bytes_1 = wan_raw_bytes.replace(b'"shift": 8.0', b'"shift": 8.1')
    assert mutated_bytes_1 != wan_raw_bytes
    assert len(mutated_bytes_1) == len(wan_raw_bytes)  # Exact same length, 1 byte difference ('0' -> '1')

    wf_file.write_bytes(mutated_bytes_1)

    client = ComfyUIClient()
    client.api_workflow_root = lambda: fake_api_dir
    reg = ComfyWorkflowRegistry(client=client)

    with pytest.raises(WorkflowRegistryError, match="Workflow checksum mismatch for wan21_14b_i2v"):
        reg.load("wan21_14b_i2v")

    # 2. Append a single trailing space byte
    mutated_bytes_2 = wan_raw_bytes + b" "
    wf_file.write_bytes(mutated_bytes_2)
    with pytest.raises(WorkflowRegistryError, match="Workflow checksum mismatch for wan21_14b_i2v"):
        reg.load("wan21_14b_i2v")

    # 3. Prepend a single leading space byte
    mutated_bytes_3 = b" " + wan_raw_bytes
    wf_file.write_bytes(mutated_bytes_3)
    with pytest.raises(WorkflowRegistryError, match="Workflow checksum mismatch for wan21_14b_i2v"):
        reg.load("wan21_14b_i2v")

    # 4. Truncate to 0 bytes
    wf_file.write_bytes(b"")
    with pytest.raises(WorkflowRegistryError, match="Workflow checksum mismatch for wan21_14b_i2v"):
        reg.load("wan21_14b_i2v")

    # 5. Restore original bytes -> verify load succeeds cleanly
    wf_file.write_bytes(wan_raw_bytes)
    wf, csum = reg.load("wan21_14b_i2v")
    assert len(wf) == 14
    assert csum == hashlib.sha256(wan_raw_bytes).hexdigest()


def test_adversarial_checksum_corrupted_json_syntax(tmp_path: Path, wan_raw_bytes: bytes):
    """Test registry behavior when workflow content is corrupt JSON with matching checksum."""
    fake_api_dir = tmp_path / "workflows"
    fake_api_dir.mkdir(parents=True)
    wf_file = fake_api_dir / "wan21_14b_i2v.api.json"

    corrupted = b"{\ninvalid_json: true\n"
    wf_file.write_bytes(corrupted)
    corrupted_sha = hashlib.sha256(corrupted).hexdigest()

    client = ComfyUIClient()
    client.api_workflow_root = lambda: fake_api_dir
    reg = ComfyWorkflowRegistry(client=client)
    # Monkeypatch the registry entry to have the corrupted sha to test JSON parsing failure
    reg._entries["wan21_14b_i2v"]["sha256"] = corrupted_sha

    with pytest.raises(WorkflowRegistryError, match="Workflow JSON is invalid for wan21_14b_i2v"):
        reg.load("wan21_14b_i2v")


# ==============================================================================
# 2. DIMENSION POLICY ENFORCEMENT & BOUNDARY CONDITIONS
# ==============================================================================


@pytest.mark.parametrize(
    "width,height,expected_err",
    [
        (831, 480, "alignment"),      # width not multiple of 16
        (832, 481, "alignment"),      # height not multiple of 16
        (833, 480, "alignment"),      # width odd
        (832, 479, "alignment"),      # height odd
        (721, 1280, "alignment"),     # width not multiple of 16
        (255, 256, "policy"),         # width below min (256)
        (256, 255, "policy"),         # height below min (256)
        (240, 240, "policy"),         # multiple of 16 (15*16), but below min (256)
        (0, 480, "policy"),           # zero dimension
        (-16, 480, "policy"),         # negative dimension
        (2049, 1024, "policy"),       # width above max (2048)
        (1024, 2049, "policy"),       # height above max (2048)
        (2064, 1024, "policy"),       # multiple of 16 (129*16), but above max (2048)
        (4096, 2048, "policy"),       # multiple of 16, well above max
    ],
)
def test_adversarial_dimension_policy_rejections(registry: ComfyWorkflowRegistry, width: int, height: int, expected_err: str):
    """Verify non-multiples of 16 and out-of-range boundaries are strictly rejected."""
    policy = registry.metadata("wan21_14b_i2v")["dimension_policy"]

    with pytest.raises(ComfyImageGenerationError, match=expected_err):
        _validate_output_dimensions(
            actual_width=width,
            actual_height=height,
            requested_width=width,
            requested_height=height,
            dimension_policy=policy,
        )


@pytest.mark.parametrize(
    "width,height",
    [
        (832, 480),    # Standard Wan2.1 480p landscape
        (480, 832),    # Standard Wan2.1 480p portrait
        (1280, 720),   # Standard 720p 16:9
        (720, 1280),   # Standard 720p 9:16
        (256, 256),    # Strict minimum boundary
        (2048, 2048),  # Strict maximum boundary
    ],
)
def test_valid_dimensions_pass_policy(registry: ComfyWorkflowRegistry, width: int, height: int):
    """Verify valid multiples of 16 within range pass without error."""
    policy = registry.metadata("wan21_14b_i2v")["dimension_policy"]
    # Should not raise
    _validate_output_dimensions(
        actual_width=width,
        actual_height=height,
        requested_width=width,
        requested_height=height,
        dimension_policy=policy,
    )


def test_adversarial_actual_vs_requested_dimension_mismatch(registry: ComfyWorkflowRegistry):
    """Verify ComfyUI producing dimensions differing from requested raises dimension mismatch."""
    policy = registry.metadata("wan21_14b_i2v")["dimension_policy"]
    with pytest.raises(ComfyImageGenerationError, match="do not match requested"):
        _validate_output_dimensions(
            actual_width=832,
            actual_height=480,
            requested_width=1280,
            requested_height=720,
            dimension_policy=policy,
        )


@pytest.mark.parametrize(
    "bad_policy",
    [
        {"mode": "non_exact", "min": 256, "max": 2048, "multiple_of": 16},
        {"mode": "exact", "min": 0, "max": 2048, "multiple_of": 16},
        {"mode": "exact", "min": 1024, "max": 512, "multiple_of": 16},
        {"mode": "exact", "min": 256, "max": 2048, "multiple_of": 0},
        {"mode": "exact", "min": 256, "max": 2048},  # missing multiple_of
    ],
)
def test_adversarial_registry_dimension_policy_schema(registry: ComfyWorkflowRegistry, bad_policy: dict):
    """Verify registry rejects invalid dimension policies during schema validation."""
    entry = copy.deepcopy(registry._entries["wan21_14b_i2v"])
    entry["dimension_policy"] = bad_policy
    wf, _ = registry.load("wan21_14b_i2v")

    with pytest.raises(WorkflowRegistryError, match="exact dimension policy"):
        ComfyWorkflowRegistry._validate_patch_slots("wan21_14b_i2v", wf, entry)


# ==============================================================================
# 3. PATCH SLOT MUTATIONS & BASE WORKFLOW IMMUTABILITY
# ==============================================================================


def test_adversarial_template_deep_immutability(registry: ComfyWorkflowRegistry):
    """Verify patched workflow does not mutate or leak references to base workflow."""
    workflow, _ = registry.load("wan21_14b_i2v")
    meta = registry.metadata("wan21_14b_i2v")

    snapshot_before = copy.deepcopy(workflow)

    patched = _patch_workflow(
        workflow,
        meta["patch_slots"],
        prompt="Adversarial Prompt A",
        negative_prompt="Adversarial Negative B",
        width=1280,
        height=720,
        seed=888888,
        prefix="video/adversarial_test",
        reference_image="adversarial_panel.png",
    )

    # Verify patched values
    assert patched["6"]["inputs"]["image"] == "adversarial_panel.png"
    assert patched["8"]["inputs"]["text"] == "Adversarial Prompt A"
    assert patched["9"]["inputs"]["text"] == "Adversarial Negative B"
    assert patched["10"]["inputs"]["width"] == 1280
    assert patched["10"]["inputs"]["height"] == 720
    assert patched["11"]["inputs"]["seed"] == 888888
    assert patched["14"]["inputs"]["filename_prefix"] == "video/adversarial_test"

    # Aggressively mutate the patched structure in place
    patched["6"]["inputs"]["image"] = "MUTATED_AFTERWARDS"
    patched["10"]["inputs"]["width"] = 99999
    patched["999"] = {"class_type": "InjectedNode"}

    # Base workflow MUST remain perfectly identical to snapshot
    assert workflow == snapshot_before
    assert "999" not in workflow
    assert workflow["6"]["inputs"]["image"] == "panel_input.png"
    assert workflow["10"]["inputs"]["width"] == 832
    assert workflow["10"]["inputs"]["height"] == 480
    assert workflow["11"]["inputs"]["seed"] == 0


def test_adversarial_patch_missing_required_slots(registry: ComfyWorkflowRegistry):
    """Verify registry and patch logic reject missing required slots."""
    entry = copy.deepcopy(registry._entries["wan21_14b_i2v"])
    wf, _ = registry.load("wan21_14b_i2v")

    # 1. Missing 'prompt'
    entry_no_prompt = copy.deepcopy(entry)
    del entry_no_prompt["patch_slots"]["prompt"]
    with pytest.raises(WorkflowRegistryError, match="must declare exact patch slots"):
        ComfyWorkflowRegistry._validate_patch_slots("wan21_14b_i2v", wf, entry_no_prompt)

    # 2. Missing 'seed'
    entry_no_seed = copy.deepcopy(entry)
    del entry_no_seed["patch_slots"]["seed"]
    with pytest.raises(WorkflowRegistryError, match="must declare exact patch slots"):
        ComfyWorkflowRegistry._validate_patch_slots("wan21_14b_i2v", wf, entry_no_seed)

    # 3. Missing 'filename_prefix'
    entry_no_prefix = copy.deepcopy(entry)
    del entry_no_prefix["patch_slots"]["filename_prefix"]
    with pytest.raises(WorkflowRegistryError, match="must declare exact patch slots"):
        ComfyWorkflowRegistry._validate_patch_slots("wan21_14b_i2v", wf, entry_no_prefix)

    # 4. Unknown extraneous slot
    entry_extra = copy.deepcopy(entry)
    entry_extra["patch_slots"]["unknown_slot"] = {
        "node_id": "1",
        "input": "unet_name",
        "class_type": "UNETLoader",
    }
    with pytest.raises(WorkflowRegistryError, match="must declare exact patch slots"):
        ComfyWorkflowRegistry._validate_patch_slots("wan21_14b_i2v", wf, entry_extra)


def test_adversarial_patch_omitted_reference_image(registry: ComfyWorkflowRegistry):
    """Verify that calling _patch_workflow without reference_image fails since it is a declared slot."""
    workflow, _ = registry.load("wan21_14b_i2v")
    meta = registry.metadata("wan21_14b_i2v")

    with pytest.raises(ComfyImageGenerationError, match="does not declare every required patch slot"):
        _patch_workflow(
            workflow,
            meta["patch_slots"],
            prompt="Prompt",
            negative_prompt="Negative",
            width=832,
            height=480,
            seed=1,
            prefix="prefix",
            reference_image=None,  # Not provided
        )


def test_adversarial_patch_slot_mismatched_node_targets(registry: ComfyWorkflowRegistry):
    """Verify registry rejects patch slots that target wrong node, class_type, or input."""
    entry = copy.deepcopy(registry._entries["wan21_14b_i2v"])
    wf, _ = registry.load("wan21_14b_i2v")

    # 1. Target non-existent node
    bad_node = copy.deepcopy(entry)
    bad_node["patch_slots"]["prompt"]["node_id"] = "99"
    with pytest.raises(WorkflowRegistryError, match="patch slot prompt node is missing"):
        ComfyWorkflowRegistry._validate_patch_slots("wan21_14b_i2v", wf, bad_node)

    # 2. Target wrong class_type
    bad_class = copy.deepcopy(entry)
    bad_class["patch_slots"]["prompt"]["class_type"] = "SaveVideo"
    with pytest.raises(WorkflowRegistryError, match="class_type does not match"):
        ComfyWorkflowRegistry._validate_patch_slots("wan21_14b_i2v", wf, bad_class)

    # 3. Target non-existent input parameter
    bad_input = copy.deepcopy(entry)
    bad_input["patch_slots"]["prompt"]["input"] = "non_existent_text_input"
    with pytest.raises(WorkflowRegistryError, match="patch slot prompt input is missing"):
        ComfyWorkflowRegistry._validate_patch_slots("wan21_14b_i2v", wf, bad_input)


# ==============================================================================
# 4. SINGLE TEXT_TO_IMAGE INVARIANT & PURPOSE INTEGRITY
# ==============================================================================


def test_adversarial_single_text_to_image_purpose_invariant(repo_root: Path):
    """Verify qwen_image_21 is the sole text_to_image workflow and wan21_14b_i2v is image_to_video."""
    reg_file = repo_root / "engine" / "comfyui" / "workflow_registry.json"
    entries = json.loads(reg_file.read_text(encoding="utf-8"))

    t2i = [e["id"] for e in entries if e.get("purpose") == "text_to_image"]
    assert t2i == ["qwen_image_21"], f"Violation of AGENTS.md single text_to_image invariant: {t2i}"

    wan = next(e for e in entries if e["id"] == "wan21_14b_i2v")
    assert wan["purpose"] == "image_to_video"
    assert wan["requires_gpu"] is True
    assert wan["gpu_vram_mb"] == 14000


# ==============================================================================
# 5. WORKFLOW TOPOLOGY COMPLETENESS & DAG INTEGRITY
# ==============================================================================


def test_adversarial_workflow_graph_has_no_orphaned_nodes(registry: ComfyWorkflowRegistry):
    """Verify every node in wan21_14b_i2v is connected in a valid DAG terminating at SaveVideo."""
    wf, _ = registry.load("wan21_14b_i2v")

    assert set(wf.keys()) == {str(i) for i in range(1, 15)}

    # Collect all outgoing connections
    consumers_by_node: dict[str, list[str]] = {node_id: [] for node_id in wf}
    for consumer_id, node_data in wf.items():
        inputs = node_data.get("inputs", {})
        for in_name, val in inputs.items():
            if isinstance(val, list) and len(val) == 2 and isinstance(val[0], str) and val[0] in wf:
                producer_id = val[0]
                consumers_by_node[producer_id].append(consumer_id)

    # Every node except node 14 (SaveVideo) MUST have at least one consumer
    for node_id in range(1, 14):
        consumers = consumers_by_node[str(node_id)]
        assert len(consumers) > 0, f"Node {node_id} ({wf[str(node_id)]['class_type']}) is orphaned with no consumers!"

    # Node 14 is the sink
    assert wf["14"]["class_type"] == "SaveVideo"
    assert len(consumers_by_node["14"]) == 0
