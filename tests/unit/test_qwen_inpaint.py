"""Phase 4: the Qwen masked-redraw workflow is registered, its graph matches its patch slots, and the runner method validates its inputs (no GPU)."""
import hashlib
import io
import json
from pathlib import Path

import pytest
from PIL import Image

from engine.comfyui import art as comfy_art
from engine.original import art, review

WF_DIR = Path(comfy_art.__file__).parent
ENTRY = next(e for e in json.loads((WF_DIR / "workflow_registry.json").read_text(encoding="utf-8")) if e["id"] == art.QWEN_INPAINT_ID)
GRAPH = json.loads((WF_DIR / "workflows" / ENTRY["filename"]).read_text(encoding="utf-8"))


def png(size, color="red", mode="RGB"):
    buf = io.BytesIO()
    Image.new(mode, size, color).save(buf, "PNG")
    return buf.getvalue()


class FakeArt:
    def __init__(self, out):
        self.out, self.graphs = out, []

    def run(self, wf, **kw):
        self.graphs.append(wf)
        return self.out, "pid", {}


def runner(out):
    r = art.ComfyRunner.__new__(art.ComfyRunner)
    r.qwen_inpaint_wf = (GRAPH, ENTRY)
    r.art = FakeArt(out)
    r._upload_bytes = lambda data, suffix=".png": "up_" + hashlib.sha256(data).hexdigest()[:8] + suffix
    return r


def test_registry_entry_matches_the_file_and_is_not_a_second_text_to_image_workflow():
    assert hashlib.sha256((WF_DIR / "workflows" / ENTRY["filename"]).read_bytes()).hexdigest() == ENTRY["sha256"]
    assert ENTRY["purpose"] == "inpaint"
    assert ENTRY["model_files"] == next(e for e in json.loads((WF_DIR / "workflow_registry.json").read_text(encoding="utf-8"))
                                        if e["id"] == comfy_art.ART_WORKFLOW_ID)["model_files"]  # the art model's own files: nothing new to download
    assert {n["class_type"] for n in GRAPH.values()} <= set(ENTRY["required_nodes"])


def test_graph_is_a_masked_redraw_of_the_encoded_picture():
    sampler = GRAPH["9"]["inputs"]["latent_image"]
    assert GRAPH[sampler[0]]["class_type"] == "SetLatentNoiseMask"
    mask = GRAPH["16"]["inputs"]
    assert GRAPH[mask["samples"][0]]["class_type"] == "VAEEncode" and GRAPH[mask["mask"][0]]["class_type"] == "LoadImageMask"
    assert GRAPH["14"]["inputs"]["channel"] == "red"  # white = redraw, the convention of review.extract_defect_mask
    assert GRAPH["7"]["inputs"]["denoise"] == 1.0
    assert "images.image_1" not in GRAPH["4"]["inputs"] and "vae" not in GRAPH["4"]["inputs"]  # reference latents ignore the prompt (measured)


def test_inpaint_qwen_patches_every_slot_and_returns_the_result():
    out = png((64, 32), "blue")
    r = runner(out)
    base, mask = png((64, 32)), png((64, 32), 255, "L")
    assert r.inpaint_qwen(base, mask, "a whole-picture prompt", "blurry", 123) == out
    g = r.art.graphs[0]
    assert g["4"]["inputs"]["prompt"] == "a whole-picture prompt" and g["8"]["inputs"]["noise_seed"] == 123
    assert g["13"]["inputs"]["image"].startswith("up_") and g["14"]["inputs"]["image"].startswith("up_")
    assert g["13"]["inputs"]["image"] != g["14"]["inputs"]["image"]
    assert GRAPH["4"]["inputs"]["prompt"] != "a whole-picture prompt"  # the approved graph itself is never mutated


@pytest.mark.parametrize("base,mask,msg", [
    ((64, 33), (64, 33), "multiples of 16"),
    ((64, 32), (32, 32), "mask is"),
])
def test_inpaint_qwen_rejects_a_picture_the_model_cannot_honour(base, mask, msg):
    r = runner(png(base))
    with pytest.raises(ValueError, match=msg):
        r.inpaint_qwen(png(base), png(mask, 255, "L"), "p", "n", 1)
    assert r.art.graphs == []  # rejected before any GPU time


def test_inpaint_qwen_rejects_a_result_of_the_wrong_size_and_a_missing_workflow():
    with pytest.raises(RuntimeError, match="returned"):
        runner(png((32, 32))).inpaint_qwen(png((64, 32)), png((64, 32), 255, "L"), "p", "n", 1)
    r = runner(png((64, 32)))
    r.qwen_inpaint_wf = None
    with pytest.raises(RuntimeError, match="not available"):
        r.inpaint_qwen(png((64, 32)), png((64, 32), 255, "L"), "p", "n", 1)


def test_the_original_outside_the_mask_survives_the_redraw_exactly():
    base = Image.new("RGB", (64, 32), "red")
    redrawn = Image.new("RGB", (64, 32), "blue")  # a redraw that also drifted outside the mask
    mask = Image.new("L", (64, 32), 0)
    mask.paste(255, (24, 8, 40, 24))
    out = review.splice_repaired_image(base, redrawn, mask)
    assert out.getpixel((2, 2)) == (255, 0, 0) and out.getpixel((32, 16)) == (0, 0, 255)
