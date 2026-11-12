"""Adversarial stress testing of reference_image slot validation across ALL approved workflows.

Mission requirements:
1. qwen_image_21 (TextEncodeQwenImage21):
   - reference_image=None succeeds and cleans node 4 inputs (removes images.image_1 placeholder).
   - reference_image='path.png' uploads and dynamically injects LoadImage node.
2. Every other approved workflow declaring reference_image where class_type != TextEncodeQwenImage21:
   - omitting reference_image strictly raises ComfyImageGenerationError("Approved workflow does not declare every required patch slot").
3. Adversarial edge cases:
   - empty strings, None, mock workflows with fake class types, missing patch_slots entry,
   - node ID collision avoidance, corrupted inputs, unsupported types in ArtEngine.generate.
"""
from copy import deepcopy
import io
import json
from pathlib import Path
from PIL import Image
import pytest

from engine.comfyui import art as art_mod
from engine.comfyui.art import (
    ART_WORKFLOW_ID,
    ArtEngine,
    ComfyImageGenerationError,
    _patch_workflow,
)
from engine.comfyui.client import ComfyUIClient
from engine.comfyui.registry import ComfyWorkflowRegistry


def _make_dummy_png(w: int = 1344, h: int = 768) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), "purple").save(buf, format="PNG")
    return buf.getvalue()


class MockClient(ComfyUIClient):
    def __init__(self, output_bytes: bytes | None = None):
        super().__init__()
        self.output_bytes = output_bytes or _make_dummy_png()
        self.uploaded_files: list[str] = []
        self.uploaded_bytes_list: list[str] = []
        self.submitted_workflows: list[dict] = []

    def node_catalog(self):
        # Return all required nodes for qwen_image_21 preflight
        return {
            "TextEncodeQwenImage21": {},
            "RandomNoise": {},
            "SaveImage": {},
            "EmptySD3LatentImage": {},
            "LoadImage": {},
            "KSampler": {},
            "VAEDecode": {},
        }

    def system_stats(self):
        return {"devices": [{"name": "mock_gpu"}]}

    def submit_prompt(self, workflow, client_id=None):
        self.submitted_workflows.append(workflow)
        return "mock-prompt-100"

    def history(self, prompt_id):
        return {
            prompt_id: {
                "outputs": {
                    "11": {
                        "images": [
                            {"filename": "out.png", "subfolder": "", "type": "output"}
                        ]
                    }
                }
            }
        }

    def download_output(self, filename, subfolder="", folder_type="output"):
        return self.output_bytes

    def upload_image(self, path):
        filename = getattr(path, "name", str(path))
        self.uploaded_files.append(filename)
        return filename

    def upload_image_bytes(self, data: bytes, filename: str | None = None) -> str:
        name = filename or "uploaded_from_bytes.png"
        self.uploaded_bytes_list.append(name)
        return name


# ---------------------------------------------------------------------------
# Requirement 1: qwen_image_21 (TextEncodeQwenImage21)
# ---------------------------------------------------------------------------

def test_qwen_image_21_none_reference_image_succeeds_and_cleans_node4():
    """Verify that qwen_image_21 with reference_image=None cleans images.image_1 from node 4."""
    reg = ComfyWorkflowRegistry()
    wf, _ = reg.load(ART_WORKFLOW_ID)
    meta = reg.metadata(ART_WORKFLOW_ID)

    # Base workflow node 4 contains 'images.image_1': None
    assert "images.image_1" in wf["4"]["inputs"]

    patched = _patch_workflow(
        wf,
        meta["patch_slots"],
        prompt="A tranquil shrine in the mist",
        negative_prompt="blurry, low quality",
        width=1344,
        height=768,
        seed=12345,
        prefix="panelflow_test",
        reference_image=None,
    )

    # Check node 4: images.image_1 must have been popped
    assert "images.image_1" not in patched["4"]["inputs"]
    assert patched["4"]["inputs"]["prompt"] == "A tranquil shrine in the mist"
    assert patched["4"]["inputs"]["negative_prompt"] == "blurry, low quality"

    # Verify no LoadImage node 13 was injected
    assert "13" not in patched


def test_qwen_image_21_supplied_reference_image_injects_load_image_node():
    """Verify that qwen_image_21 with reference_image string injects LoadImage node 13."""
    reg = ComfyWorkflowRegistry()
    wf, _ = reg.load(ART_WORKFLOW_ID)
    meta = reg.metadata(ART_WORKFLOW_ID)

    patched = _patch_workflow(
        wf,
        meta["patch_slots"],
        prompt="A tranquil shrine in the mist",
        negative_prompt="blurry, low quality",
        width=1344,
        height=768,
        seed=12345,
        prefix="panelflow_test",
        reference_image="mira_turnaround.png",
    )

    # Node 13 must be injected as LoadImage
    assert "13" in patched
    assert patched["13"]["class_type"] == "LoadImage"
    assert patched["13"]["inputs"]["image"] == "mira_turnaround.png"

    # Node 4 must wire images.image_1 to ['13', 0]
    assert patched["4"]["inputs"]["images.image_1"] == ["13", 0]


def test_art_engine_generate_with_reference_image_uploads_file_and_bytes(tmp_path):
    """Verify ArtEngine.generate handles Path, str, and bytes reference images."""
    client = MockClient()
    reg = ComfyWorkflowRegistry(client)
    # Mock preflight readiness
    reg._ready = True
    reg.preflight = lambda wf_id: {"ready": True, "missing_nodes": [], "missing_models": []}
    engine = ArtEngine(client, reg)

    # 1. Path input
    ref_file = tmp_path / "char_turnaround.png"
    ref_file.write_bytes(_make_dummy_png(1536, 768))

    img1 = engine.generate("portrait 1", reference_image=ref_file)
    assert "char_turnaround.png" in client.uploaded_files
    wf1 = client.submitted_workflows[-1]
    assert "13" in wf1
    assert wf1["13"]["inputs"]["image"] == "char_turnaround.png"
    assert wf1["4"]["inputs"]["images.image_1"] == ["13", 0]

    # 2. Bytes input
    raw_bytes = _make_dummy_png(1536, 768)
    img2 = engine.generate("portrait 2", reference_image=raw_bytes)
    assert len(client.uploaded_bytes_list) == 1
    uploaded_name = client.uploaded_bytes_list[0]
    wf2 = client.submitted_workflows[-1]
    assert wf2["13"]["inputs"]["image"] == uploaded_name
    assert wf2["4"]["inputs"]["images.image_1"] == ["13", 0]

    # 3. None reference image
    img3 = engine.generate("portrait 3", reference_image=None)
    wf3 = client.submitted_workflows[-1]
    assert "13" not in wf3
    assert "images.image_1" not in wf3["4"]["inputs"]


def test_qwen_image_21_node_id_collision_increments_dynamically():
    """Verify that if node '13' and '14' already exist, LoadImage gets the next free ID ('15')."""
    reg = ComfyWorkflowRegistry()
    wf, _ = reg.load(ART_WORKFLOW_ID)
    meta = reg.metadata(ART_WORKFLOW_ID)

    # Pre-occupy nodes 13 and 14
    wf_collision = deepcopy(wf)
    wf_collision["13"] = {"class_type": "DummyCustomNode", "inputs": {}}
    wf_collision["14"] = {"class_type": "DummyCustomNode2", "inputs": {}}

    patched = _patch_workflow(
        wf_collision,
        meta["patch_slots"],
        prompt="collision test",
        negative_prompt="",
        width=1344,
        height=768,
        seed=1,
        prefix="test",
        reference_image="avatar.png",
    )

    # Original nodes must NOT be overwritten
    assert patched["13"]["class_type"] == "DummyCustomNode"
    assert patched["14"]["class_type"] == "DummyCustomNode2"

    # LoadImage must be injected at '15'
    assert "15" in patched
    assert patched["15"]["class_type"] == "LoadImage"
    assert patched["15"]["inputs"]["image"] == "avatar.png"
    assert patched["4"]["inputs"]["images.image_1"] == ["15", 0]


def test_qwen_image_21_direct_wiring_tuple_or_list():
    """Verify that passing [node_id, output_idx] directly binds without injecting LoadImage."""
    reg = ComfyWorkflowRegistry()
    wf, _ = reg.load(ART_WORKFLOW_ID)
    meta = reg.metadata(ART_WORKFLOW_ID)

    patched = _patch_workflow(
        wf,
        meta["patch_slots"],
        prompt="direct wire test",
        negative_prompt="",
        width=1344,
        height=768,
        seed=1,
        prefix="test",
        reference_image=["99", 0],  # Pre-existing upstream node output
    )

    assert "13" not in patched
    assert patched["4"]["inputs"]["images.image_1"] == ["99", 0]


# ---------------------------------------------------------------------------
# Requirement 2: All 16 other approved workflows declaring reference_image
# ---------------------------------------------------------------------------

ALL_NON_QWEN_REFERENCE_WORKFLOWS = [
    "anime_sdxl_ipa",
    "anime_sdxl_ipa2",
    "minimax_h3_turbo_i2v",
    "minimax_h3_facerefine_i2v",
    "minimax_h3_upscale_2k",
    "anime_sdxl_inpaint",
    "anime_alpha_matting",
    "qwen_image_21_inpaint",
    "fastvideo_h3_i2v",
    "fastvideo_h3_film_free",
    "fastvideo_h3_film_voice",
    "fastvideo_h3_film_fl2va",
    "fastvideo_h3_omniref",
    "fastvideo_h3_film_fl2va_voice",
    "wan21_14b_i2v",
    "herrgott_h3_chain_start",
]


def test_registry_contains_exactly_16_non_qwen_reference_image_workflows():
    """Verify our list of 16 workflows matches every non-qwen workflow with reference_image slot."""
    with open("engine/comfyui/workflow_registry.json", "r", encoding="utf-8") as f:
        raw = json.load(f)
    workflows = raw if isinstance(raw, list) else raw.get("workflows", [])
    found = [
        w["id"]
        for w in workflows
        if "reference_image" in w.get("patch_slots", {})
        and w["patch_slots"]["reference_image"].get("class_type") != "TextEncodeQwenImage21"
    ]
    assert sorted(found) == sorted(ALL_NON_QWEN_REFERENCE_WORKFLOWS)


@pytest.mark.parametrize("workflow_id", ALL_NON_QWEN_REFERENCE_WORKFLOWS)
def test_all_non_qwen_reference_workflows_strictly_fail_when_reference_image_omitted(workflow_id):
    """Verify that EVERY non-Qwen workflow declaring reference_image strictly fails on reference_image=None."""
    reg = ComfyWorkflowRegistry()
    wf, _ = reg.load(workflow_id)
    meta = reg.metadata(workflow_id)
    slots = meta["patch_slots"]

    # Slot exists and is NOT TextEncodeQwenImage21
    assert "reference_image" in slots
    assert slots["reference_image"].get("class_type") == "LoadImage"

    with pytest.raises(ComfyImageGenerationError, match="Approved workflow does not declare every required patch slot"):
        _patch_workflow(
            wf,
            slots,
            prompt="Prompt",
            negative_prompt="Negative",
            width=512,
            height=512,
            seed=42,
            prefix="test",
            reference_image=None,  # Intentionally omitted
        )


def test_non_qwen_workflow_succeeds_when_all_required_slots_including_reference_image_are_supplied():
    """Verify that supplying reference_image and all declared slots allows patching without error."""
    reg = ComfyWorkflowRegistry()

    # Test anime_sdxl_ipa
    wf_ipa, _ = reg.load("anime_sdxl_ipa")
    meta_ipa = reg.metadata("anime_sdxl_ipa")
    patched_ipa = _patch_workflow(
        wf_ipa,
        meta_ipa["patch_slots"],
        prompt="1girl in kimono",
        negative_prompt="bad quality",
        width=1344,
        height=768,
        seed=1,
        prefix="ipa_test",
        reference_image="mira_ref.png",
    )
    assert patched_ipa["8"]["inputs"]["image"] == "mira_ref.png"

    # Test anime_alpha_matting
    wf_mat, _ = reg.load("anime_alpha_matting")
    meta_mat = reg.metadata("anime_alpha_matting")
    patched_mat = _patch_workflow(
        wf_mat,
        meta_mat["patch_slots"],
        prompt="matting prompt",
        negative_prompt="",
        width=1024,
        height=1024,
        seed=1,
        prefix="mat_test",
        reference_image="char_to_cutout.png",
    )
    assert patched_mat["1"]["inputs"]["image"] == "char_to_cutout.png"


# ---------------------------------------------------------------------------
# Requirement 3: Adversarial Edge Cases
# ---------------------------------------------------------------------------

def test_adversarial_mock_workflow_with_fake_class_types():
    """Test mock workflows with fake, spoofed, empty, or None class_types."""
    fake_wf = {
        "1": {"class_type": "PromptNode", "inputs": {"text": ""}},
        "2": {"class_type": "FakeNode", "inputs": {"ref": None}},
        "3": {"class_type": "SeedNode", "inputs": {"seed": 0}},
        "4": {"class_type": "PrefixNode", "inputs": {"prefix": ""}},
    }

    # Case A: Spoofed class_type 'TextEncodeQwenImage21_Spoof'
    slots_spoof = {
        "prompt": {"node_id": "1", "input": "text", "class_type": "PromptNode"},
        "seed": {"node_id": "3", "input": "seed", "class_type": "SeedNode"},
        "filename_prefix": {"node_id": "4", "input": "prefix", "class_type": "PrefixNode"},
        "reference_image": {"node_id": "2", "input": "ref", "class_type": "TextEncodeQwenImage21_Spoof"},
    }
    with pytest.raises(ComfyImageGenerationError, match="does not declare every required patch slot"):
        _patch_workflow(fake_wf, slots_spoof, "p", "", 512, 512, 1, "test", reference_image=None)

    # Case B: Empty string class_type ''
    slots_empty_class = deepcopy(slots_spoof)
    slots_empty_class["reference_image"]["class_type"] = ""
    with pytest.raises(ComfyImageGenerationError, match="does not declare every required patch slot"):
        _patch_workflow(fake_wf, slots_empty_class, "p", "", 512, 512, 1, "test", reference_image=None)

    # Case C: None class_type
    slots_none_class = deepcopy(slots_spoof)
    slots_none_class["reference_image"]["class_type"] = None
    with pytest.raises(ComfyImageGenerationError, match="does not declare every required patch slot"):
        _patch_workflow(fake_wf, slots_none_class, "p", "", 512, 512, 1, "test", reference_image=None)

    # Case D: Missing 'class_type' key altogether
    slots_missing_class = deepcopy(slots_spoof)
    del slots_missing_class["reference_image"]["class_type"]
    with pytest.raises(ComfyImageGenerationError, match="does not declare every required patch slot"):
        _patch_workflow(fake_wf, slots_missing_class, "p", "", 512, 512, 1, "test", reference_image=None)


def test_adversarial_workflow_without_reference_image_slot_rejects_unwanted_reference():
    """Verify that passing reference_image to a workflow that does NOT declare reference_image is rejected."""
    reg = ComfyWorkflowRegistry()
    wf_sdxl, _ = reg.load("anime_sdxl")
    meta_sdxl = reg.metadata("anime_sdxl")

    assert "reference_image" not in meta_sdxl["patch_slots"]

    # When reference_image=None, it succeeds
    patched = _patch_workflow(
        wf_sdxl,
        meta_sdxl["patch_slots"],
        prompt="a portrait",
        negative_prompt="blurry",
        width=832,
        height=1216,
        seed=10,
        prefix="sdxl_test",
        reference_image=None,
    )
    assert patched["5"]["inputs"]["seed"] == 10

    # When reference_image='unwanted.png', it MUST raise because the workflow did not declare it
    with pytest.raises(ComfyImageGenerationError, match="does not declare every required patch slot"):
        _patch_workflow(
            wf_sdxl,
            meta_sdxl["patch_slots"],
            prompt="a portrait",
            negative_prompt="blurry",
            width=832,
            height=1216,
            seed=10,
            prefix="sdxl_test",
            reference_image="unwanted.png",
        )


def test_adversarial_qwen_workflow_corrupted_inputs_handled_safely():
    """Verify that when reference_image=None, if node 4 inputs is missing or not a dict, it does not crash unhandled."""
    reg = ComfyWorkflowRegistry()
    wf, _ = reg.load(ART_WORKFLOW_ID)
    meta = reg.metadata(ART_WORKFLOW_ID)

    # 1. Corrupt node 4 inputs to None
    wf_corrupt = deepcopy(wf)
    wf_corrupt["4"]["inputs"] = None
    # Omitting reference_image will fail during slot validation (node 4 input missing)
    # but must NOT crash with AttributeError in cleanup
    with pytest.raises(ComfyImageGenerationError):
        _patch_workflow(
            wf_corrupt,
            meta["patch_slots"],
            prompt="p",
            negative_prompt="n",
            width=1344,
            height=768,
            seed=1,
            prefix="test",
            reference_image=None,
        )

    # 2. Corrupt node 4 entirely (missing node 4)
    wf_missing_node = deepcopy(wf)
    del wf_missing_node["4"]
    with pytest.raises(ComfyImageGenerationError):
        _patch_workflow(
            wf_missing_node,
            meta["patch_slots"],
            prompt="p",
            negative_prompt="n",
            width=1344,
            height=768,
            seed=1,
            prefix="test",
            reference_image=None,
        )


def test_adversarial_art_engine_generate_invalid_types():
    """Verify ArtEngine.generate rejects invalid types for reference_image."""
    client = MockClient()
    reg = ComfyWorkflowRegistry(client)
    reg.preflight = lambda wf_id: {"ready": True, "missing_nodes": [], "missing_models": []}
    engine = ArtEngine(client, reg)

    invalid_inputs = [
        12345,
        3.14159,
        {"key": "value"},
        [1, 2, 3],
        ("tuple", "item"),
        True,
    ]

    for inv in invalid_inputs:
        with pytest.raises(ValueError, match="Unsupported reference_image type"):
            engine.generate("test prompt", reference_image=inv)


def test_adversarial_empty_string_reference_image_behavior():
    """Document and verify behavior when reference_image is empty string ''."""
    reg = ComfyWorkflowRegistry()
    wf, _ = reg.load(ART_WORKFLOW_ID)
    meta = reg.metadata(ART_WORKFLOW_ID)

    # In Python, '' is not None.
    # When passed to _patch_workflow, it is treated as a supplied string and injects LoadImage with image=""
    patched = _patch_workflow(
        wf,
        meta["patch_slots"],
        prompt="empty string test",
        negative_prompt="",
        width=1344,
        height=768,
        seed=1,
        prefix="test",
        reference_image="",
    )
    assert "13" in patched
    assert patched["13"]["class_type"] == "LoadImage"
    assert patched["13"]["inputs"]["image"] == ""
    assert patched["4"]["inputs"]["images.image_1"] == ["13", 0]


def test_adversarial_optional_slots_do_not_mask_missing_reference_image():
    """Verify that optional slots like denoise or reference_weight do not prevent missing reference_image from raising."""
    reg = ComfyWorkflowRegistry()

    # 1. anime_sdxl_ipa has optional reference_weight and required reference_image
    wf_ipa, _ = reg.load("anime_sdxl_ipa")
    meta_ipa = reg.metadata("anime_sdxl_ipa")
    # Omitting reference_image with reference_weight=None must still raise
    with pytest.raises(ComfyImageGenerationError, match="does not declare every required patch slot"):
        _patch_workflow(
            wf_ipa,
            meta_ipa["patch_slots"],
            prompt="p",
            negative_prompt="n",
            width=1344,
            height=768,
            seed=1,
            prefix="test",
            reference_image=None,
            reference_weight=None,
        )

    # 2. anime_sdxl_inpaint has optional denoise, required mask_image, and required reference_image
    wf_inp, _ = reg.load("anime_sdxl_inpaint")
    meta_inp = reg.metadata("anime_sdxl_inpaint")
    with pytest.raises(ComfyImageGenerationError, match="does not declare every required patch slot"):
        _patch_workflow(
            wf_inp,
            meta_inp["patch_slots"],
            prompt="p",
            negative_prompt="n",
            width=1024,
            height=1024,
            seed=1,
            prefix="test",
            reference_image=None,  # Missing!
            mask_image="mask.png",
            denoise=None,
        )


def test_adversarial_dual_reference_workflows_partial_omission():
    """Verify anime_sdxl_ipa2 requires BOTH reference_image and reference_image_b."""
    reg = ComfyWorkflowRegistry()
    wf, _ = reg.load("anime_sdxl_ipa2")
    meta = reg.metadata("anime_sdxl_ipa2")

    # Omitting reference_image
    with pytest.raises(ComfyImageGenerationError, match="does not declare every required patch slot"):
        _patch_workflow(
            wf,
            meta["patch_slots"],
            prompt="p",
            negative_prompt="n",
            width=1344,
            height=768,
            seed=1,
            prefix="test",
            reference_image=None,
            reference_image_b="b.png",
        )

    # Omitting reference_image_b
    with pytest.raises(ComfyImageGenerationError, match="does not declare every required patch slot"):
        _patch_workflow(
            wf,
            meta["patch_slots"],
            prompt="p",
            negative_prompt="n",
            width=1344,
            height=768,
            seed=1,
            prefix="test",
            reference_image="a.png",
            reference_image_b=None,
        )


def test_single_art_workflow_invariant_strictly_enforced():
    """Verify that qwen_image_21 is the sole text_to_image workflow across the entire registry."""
    with open("engine/comfyui/workflow_registry.json", "r", encoding="utf-8") as f:
        registry_data = json.load(f)
    workflows = registry_data if isinstance(registry_data, list) else registry_data.get("workflows", [])
    t2i = [w["id"] for w in workflows if isinstance(w, dict) and w.get("purpose") == "text_to_image"]
    assert len(t2i) == 1, f"Found {len(t2i)} text_to_image workflows: {t2i}"
    assert t2i[0] == "qwen_image_21", f"Expected qwen_image_21, found: {t2i[0]}"

