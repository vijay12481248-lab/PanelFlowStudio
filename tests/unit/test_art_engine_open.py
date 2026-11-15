"""FLUX.2 klein 4B (Apache-2.0) as an image workflow next to Qwen: registered, checksummed, text to image only."""
import hashlib
import json
from pathlib import Path

import pytest

from engine.comfyui import art as art_mod
from engine.comfyui.art import OPEN_ART_WORKFLOW_ID, ArtEngine

COMFY = Path(art_mod.__file__).parent
ENTRY = next(e for e in json.loads((COMFY / "workflow_registry.json").read_text(encoding="utf-8")) if e["id"] == OPEN_ART_WORKFLOW_ID)


def test_klein_is_a_selectable_image_workflow_with_a_matching_checksum():
    assert OPEN_ART_WORKFLOW_ID in art_mod.IMAGE_WORKFLOW_IDS
    assert ENTRY["purpose"] != "text_to_image"  # the registry keeps exactly one text_to_image entry (see test_art_engine)
    assert hashlib.sha256((COMFY / "workflows" / ENTRY["filename"]).read_bytes()).hexdigest() == ENTRY["sha256"]


def test_klein_slots_point_at_real_nodes_of_its_graph():
    graph = json.loads((COMFY / "workflows" / ENTRY["filename"]).read_text(encoding="utf-8"))
    for name, slot in ENTRY["patch_slots"].items():
        node = graph[slot["node_id"]]
        assert node["class_type"] == slot["class_type"], name
        assert slot["input"] in node["inputs"], name


REGISTRY = {e["id"]: e for e in json.loads((COMFY / "workflow_registry.json").read_text(encoding="utf-8"))}


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
        return "ref.png"


def test_klein_with_a_picture_runs_the_reference_graph_with_an_edit_style_prompt():
    client = _Client()
    engine = ArtEngine(client=client, registry=_Registry())
    assert engine.accepts_reference(OPEN_ART_WORKFLOW_ID)
    with pytest.raises(RuntimeError, match="stop after submit"):
        engine.generate("the dad whistles", width=768, height=1344, seed=5, workflow_id=OPEN_ART_WORKFLOW_ID, reference_image=b"x")
    graph = client.submitted[0]
    assert graph["20"]["inputs"]["image"] == "ref.png"
    assert graph["4"]["inputs"]["text"].endswith("Show a new moment: the dad whistles")
    assert (graph["14"]["inputs"]["value"], graph["15"]["inputs"]["value"], graph["9"]["inputs"]["noise_seed"]) == (768, 1344, 5)


def test_klein_without_a_picture_runs_the_plain_graph_and_keeps_the_prompt():
    client = _Client()
    with pytest.raises(RuntimeError, match="stop after submit"):
        ArtEngine(client=client, registry=_Registry()).generate("a cat", width=768, height=1344, workflow_id=OPEN_ART_WORKFLOW_ID)
    assert "20" not in client.submitted[0] and client.submitted[0]["4"]["inputs"]["text"] == "a cat"
