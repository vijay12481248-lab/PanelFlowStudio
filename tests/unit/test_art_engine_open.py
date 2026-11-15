"""FLUX.2 klein 4B (Apache-2.0) as an image workflow next to Qwen: registered, checksummed, text to image only."""
import hashlib
import json
from pathlib import Path

import pytest

from engine.comfyui import art as art_mod
from engine.comfyui.art import OPEN_ART_WORKFLOW_ID, ArtEngine, ComfyImageGenerationError

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


class _Registry:
    def preflight(self, workflow_id):
        return {"ready": True, "missing_nodes": [], "missing_models": []}

    def load(self, workflow_id):
        return {}, "0" * 64

    def metadata(self, workflow_id):
        return {"patch_slots": ENTRY["patch_slots"], "dimension_policy": ENTRY["dimension_policy"], "model_files": ENTRY["model_files"]}


def test_klein_refuses_reference_pictures_instead_of_failing_late():
    engine = ArtEngine(client=object(), registry=_Registry())
    with pytest.raises(ComfyImageGenerationError, match="text to image only"):
        engine.generate("a cat", width=768, height=1344, workflow_id=OPEN_ART_WORKFLOW_ID, reference_image=b"x")
