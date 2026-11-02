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
