"""FLUX.2 klein 4B (Apache-2.0) is the art model; Qwen Image 2.1 (non-commercial licence) is retired from the image workflows."""
import hashlib
import json
from pathlib import Path

import pytest

from engine.comfyui import art as art_mod
from engine.comfyui.art import ART_REF_WORKFLOW_ID, ART_WORKFLOW_ID, LEGACY_QWEN_WORKFLOW_ID, ArtEngine, ComfyImageGenerationError

COMFY = Path(art_mod.__file__).parent
REGISTRY = {e["id"]: e for e in json.loads((COMFY / "workflow_registry.json").read_text(encoding="utf-8"))}


def test_klein_is_the_one_text_to_image_workflow_and_qwen_is_not_selectable():
    assert ART_WORKFLOW_ID == "flux2_klein_4b" and REGISTRY[ART_WORKFLOW_ID]["purpose"] == "text_to_image"
    assert ART_WORKFLOW_ID in art_mod.IMAGE_WORKFLOW_IDS
    assert LEGACY_QWEN_WORKFLOW_ID not in art_mod.IMAGE_WORKFLOW_IDS
    assert REGISTRY[LEGACY_QWEN_WORKFLOW_ID]["purpose"] != "text_to_image"


@pytest.mark.parametrize("workflow_id", [ART_WORKFLOW_ID, ART_REF_WORKFLOW_ID])
def test_klein_graphs_have_matching_checksums_and_real_slots(workflow_id):
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

    def upload_image_bytes(self, data, filename=None):
        return f"ref_{data.decode()}.png"


def _submit(**kw):
    client = _Client()
    with pytest.raises(RuntimeError, match="stop after submit"):
        ArtEngine(client=client, registry=_Registry()).generate("the dad whistles", width=768, height=1344, seed=5, **kw)
    return client.submitted[0]


def test_klein_without_a_picture_runs_the_plain_graph_and_keeps_the_prompt():
    graph = _submit()
    assert "20" not in graph and graph["4"]["inputs"]["text"] == "the dad whistles"
    assert (graph["14"]["inputs"]["value"], graph["15"]["inputs"]["value"], graph["9"]["inputs"]["noise_seed"]) == (768, 1344, 5)


def test_klein_with_one_picture_runs_the_reference_graph_with_an_edit_style_prompt():
    graph = _submit(reference_image=b"a")
    assert graph["20"]["inputs"]["image"] == "ref_a.png"
    assert graph["4"]["inputs"]["text"].endswith("Show a new moment: the dad whistles") and "the reference picture." in graph["4"]["inputs"]["text"]
    assert graph["10"]["inputs"]["positive"] == ["23", 0]


def test_klein_chains_up_to_four_pictures_onto_the_guider():
    graph = _submit(reference_images=[b"a", b"b", b"c"])
    loads = [n["inputs"]["image"] for n in graph.values() if n["class_type"] == "LoadImage"]
    assert sorted(loads) == ["ref_a.png", "ref_b.png", "ref_c.png"]
    assert "the reference pictures." in graph["4"]["inputs"]["text"]
    pos = graph["10"]["inputs"]["positive"][0]  # walk the positive chain back to the text: three reference latents
    hops = 0
    while graph[pos]["class_type"] == "ReferenceLatent":
        pos, hops = graph[pos]["inputs"]["conditioning"][0], hops + 1
    assert (hops, graph[pos]["class_type"]) == (3, "CLIPTextEncode")


def test_klein_refuses_a_fifth_picture_before_any_gpu_time_is_spent():
    with pytest.raises(ComfyImageGenerationError, match="at most 4"):
        ArtEngine(client=_Client(), registry=_Registry()).generate("x", width=768, height=1344, reference_images=[b"1", b"2", b"3", b"4", b"5"])
