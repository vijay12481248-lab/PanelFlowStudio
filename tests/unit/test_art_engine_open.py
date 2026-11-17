"""HiDream-I1 Fast is the default art model, Z-Image Turbo the second; FLUX.2 klein (removed from disk) and Qwen Image 2.1 are retired."""
import hashlib
import json
from pathlib import Path

import pytest

from engine.comfyui import art as art_mod
from engine.comfyui.art import ART_WORKFLOW_ID, LEGACY_QWEN_WORKFLOW_ID, ZIMAGE_WORKFLOW_ID, ArtEngine, ComfyImageGenerationError

COMFY = Path(art_mod.__file__).parent
REGISTRY = {e["id"]: e for e in json.loads((COMFY / "workflow_registry.json").read_text(encoding="utf-8"))}
TEXT_TO_IMAGE = (ART_WORKFLOW_ID, ZIMAGE_WORKFLOW_ID)


def test_hidream_is_the_default_zimage_the_second_and_klein_and_qwen_are_not_selectable():
    assert ART_WORKFLOW_ID == "hidream_i1_fast" and ZIMAGE_WORKFLOW_ID == "zimage_turbo"
    assert REGISTRY[ART_WORKFLOW_ID]["purpose"] == "text_to_image" and REGISTRY[ZIMAGE_WORKFLOW_ID]["purpose"] == "text_to_image_alt"
    for wid in TEXT_TO_IMAGE:
        assert wid in art_mod.IMAGE_WORKFLOW_IDS
    for retired in (LEGACY_QWEN_WORKFLOW_ID, "flux2_klein_4b", "flux2_klein_4b_ref"):
        assert retired not in art_mod.IMAGE_WORKFLOW_IDS and REGISTRY[retired]["purpose"].startswith("retired")


@pytest.mark.parametrize("workflow_id", TEXT_TO_IMAGE)
def test_graphs_have_matching_checksums_and_real_slots(workflow_id):
    entry = REGISTRY[workflow_id]
    raw = (COMFY / "workflows" / entry["filename"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == entry["sha256"]
    graph = json.loads(raw)
    for name, slot in entry["patch_slots"].items():
        node = graph[slot["node_id"]]
        assert node["class_type"] == slot["class_type"] and slot["input"] in node["inputs"], name


class _Registry:
    def preflight(self, workflow_id):
        return {"ready": True, "missing_nodes": [], "missing_models": []}

    def load(self, workflow_id):
        return json.loads((COMFY / "workflows" / REGISTRY[workflow_id]["filename"]).read_text(encoding="utf-8")), "0" * 64

    def metadata(self, workflow_id):
        e = REGISTRY[workflow_id]
        return {"patch_slots": e["patch_slots"], "dimension_policy": e["dimension_policy"], "model_files": e["model_files"]}


class _Client:
    def __init__(self):
        self.submitted = []

    def submit_prompt(self, workflow, client_id=None):
        self.submitted.append(workflow)
        raise RuntimeError("stop after submit")


def _submit(**kw):
    client = _Client()
    with pytest.raises(RuntimeError, match="stop after submit"):
        ArtEngine(client=client, registry=_Registry()).generate("the dad whistles", width=768, height=1344, seed=5, **kw)
    return client.submitted[0]


@pytest.mark.parametrize("workflow_id,text_node,latent_node,seed_node", [(ART_WORKFLOW_ID, "85", "84", "94"), (ZIMAGE_WORKFLOW_ID, "5", "7", "8")])
def test_prompt_size_and_seed_reach_the_graph(workflow_id, text_node, latent_node, seed_node):
    graph = _submit(workflow_id=workflow_id)
    assert graph[text_node]["inputs"]["text"] == "the dad whistles"
    assert (graph[latent_node]["inputs"]["width"], graph[latent_node]["inputs"]["height"], graph[seed_node]["inputs"]["seed"]) == (768, 1344, 5)


@pytest.mark.parametrize("workflow_id", TEXT_TO_IMAGE)
def test_text_to_image_models_refuse_reference_pictures_before_any_gpu_time(workflow_id):
    with pytest.raises(ComfyImageGenerationError, match="text to image only"):
        ArtEngine(client=_Client(), registry=_Registry()).generate("x", width=768, height=1344, reference_image=b"a", workflow_id=workflow_id)


def test_hidream_prompt_loses_its_text_negations_but_zimage_keeps_the_prompt_as_written():
    styled = "flat cartoon, thick outlines, no text, no letters, no numbers, no words, no speech bubbles. Scene: a guy"
    for wf, node, expect in ((ART_WORKFLOW_ID, "85", "flat cartoon, thick outlines. Scene: a guy"), (ZIMAGE_WORKFLOW_ID, "5", styled)):
        client = _Client()
        with pytest.raises(RuntimeError, match="stop after submit"):
            ArtEngine(client=client, registry=_Registry()).generate(styled, width=768, height=1344, seed=5, workflow_id=wf)
        assert client.submitted[0][node]["inputs"]["text"] == expect


def test_trim_corner_and_scale_returns_the_asked_size_and_drops_the_corner():
    import io

    from PIL import Image

    im = Image.new("RGB", (96, 192), "white")
    im.paste((255, 0, 0), (80, 180, 96, 192))  # a red "signature" in the bottom-right corner
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    out = Image.open(io.BytesIO(art_mod._trim_corner_and_scale(buf.getvalue(), 96, 192, trim=16)))
    assert out.size == (96, 192)
    assert out.getpixel((95, 191)) == (255, 255, 255)  # the red corner is gone
