from engine.comfyui import ComfyWorkflowRegistry
from engine.comfyui.client import ComfyUIClient
from engine.comfyui.service import _patch_workflow


def test_bundled_anime_sdxl_workflow_is_registered_and_patchable():
    reg = ComfyWorkflowRegistry(ComfyUIClient())
    wf, _ = reg.load("anime_sdxl")  # checksum + patch-slot validation against the bundled file
    entry = reg.metadata("anime_sdxl")
    patched = _patch_workflow(wf, entry["patch_slots"], "1girl, test", "lowres", 832, 1216, 7, "unit")
    assert patched["2"]["inputs"]["text"] == "1girl, test" and patched["5"]["inputs"]["seed"] == 7
    assert (patched["4"]["inputs"]["width"], patched["4"]["inputs"]["height"]) == (832, 1216)
    assert wf["2"]["inputs"]["text"] == ""  # the approved template itself is never mutated


def test_ipadapter_workflow_declares_reference_slot_and_patches_it():
    reg = ComfyWorkflowRegistry(ComfyUIClient())
    wf, _ = reg.load("anime_sdxl_ipa")
    entry = reg.metadata("anime_sdxl_ipa")
    patched = _patch_workflow(wf, entry["patch_slots"], "p", "n", 1344, 768, 3, "x", reference_image="ref.png")
    assert patched["8"]["inputs"]["image"] == "ref.png" and patched["10"]["inputs"]["weight"] < 0.6
    import pytest
    with pytest.raises(Exception):  # a workflow that needs a reference refuses to run without one
        _patch_workflow(wf, entry["patch_slots"], "p", "n", 1344, 768, 3, "x")
    plain_entry = reg.metadata("anime_sdxl")
    plain, _ = reg.load("anime_sdxl")
    with pytest.raises(Exception):  # and a plain workflow refuses a reference
        _patch_workflow(plain, plain_entry["patch_slots"], "p", "n", 832, 1216, 3, "x", reference_image="ref.png")


def test_two_reference_workflow_masks_left_and_right_and_patches_both_references():
    import pytest
    reg = ComfyWorkflowRegistry(ComfyUIClient())
    wf, _ = reg.load("anime_sdxl_ipa2")
    entry = reg.metadata("anime_sdxl_ipa2")
    patched = _patch_workflow(wf, entry["patch_slots"], "p", "n", 1344, 768, 3, "x", reference_image="a.png", reference_image_b="b.png")
    assert patched["8"]["inputs"]["image"] == "a.png" and patched["11"]["inputs"]["image"] == "b.png"
    assert (wf["22"]["inputs"]["x"], wf["23"]["inputs"]["x"]) == (0, 672)  # first character left, second right
    assert wf["10"]["inputs"]["attn_mask"] == ["22", 0] and wf["12"]["inputs"]["attn_mask"] == ["23", 0] and wf["12"]["inputs"]["model"] == ["10", 0]
    with pytest.raises(Exception):  # both references are mandatory for this workflow
        _patch_workflow(wf, entry["patch_slots"], "p", "n", 1344, 768, 3, "x", reference_image="a.png")
