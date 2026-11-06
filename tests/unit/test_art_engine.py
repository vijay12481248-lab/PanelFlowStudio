"""The central art engine (engine/comfyui/art.py): the only text-to-image path in PanelFlow."""
import io

import pytest
from PIL import Image

from engine.comfyui import art as art_mod
from engine.comfyui.art import ART_WORKFLOW_ID, ArtEngine, ArtTimeoutError, ComfyImageGenerationError

WORKFLOW = {
    "4": {"class_type": "TextEncodeQwenImage21", "inputs": {"prompt": "", "negative_prompt": ""}},
    "8": {"class_type": "RandomNoise", "inputs": {"noise_seed": 0}},
    "11": {"class_type": "SaveImage", "inputs": {"filename_prefix": "x"}},
    "12": {"class_type": "EmptySD3LatentImage", "inputs": {"width": 1, "height": 1}},
}
SLOTS = {
    "prompt": {"node_id": "4", "input": "prompt", "class_type": "TextEncodeQwenImage21"},
    "negative_prompt": {"node_id": "4", "input": "negative_prompt", "class_type": "TextEncodeQwenImage21"},
    "seed": {"node_id": "8", "input": "noise_seed", "class_type": "RandomNoise"},
    "width": {"node_id": "12", "input": "width", "class_type": "EmptySD3LatentImage"},
    "height": {"node_id": "12", "input": "height", "class_type": "EmptySD3LatentImage"},
    "filename_prefix": {"node_id": "11", "input": "filename_prefix", "class_type": "SaveImage"},
}


def png(w, h):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), "orange").save(buf, format="PNG")
    return buf.getvalue()


class FakeClient:
    def __init__(self, image=None, history_ready=True):
        self.image, self.history_ready, self.submitted = image, history_ready, []

    def submit_prompt(self, workflow, client_id=None):
        self.submitted.append((workflow, client_id))
        return "pid-1"

    def history(self, prompt_id):
        if not self.history_ready:
            return {}
        return {prompt_id: {"outputs": {"11": {"images": [{"filename": "o.png", "subfolder": "", "type": "output"}]}}}}

    def download_output(self, *args, **kwargs):
        return self.image


class FakeRegistry:
    def __init__(self, ready=True):
        self.ready = ready
        self.asked = []

    def load(self, workflow_id):
        self.asked.append(workflow_id)
        return WORKFLOW, "b" * 64

    def metadata(self, workflow_id):
        return {"patch_slots": SLOTS, "model_files": ["qwen.safetensors"],
                "dimension_policy": {"mode": "exact", "min": 256, "max": 2048, "multiple_of": 16}}

    def preflight(self, workflow_id):
        return {"ready": self.ready, "missing_nodes": [], "missing_models": [] if self.ready else ["qwen.safetensors"]}


def test_generate_patches_the_request_into_the_one_approved_workflow():
    client, reg = FakeClient(png(1344, 768)), FakeRegistry()
    img = ArtEngine(client, reg).generate("a cat on a table", "blurry", 1344, 768, 7, "panel_p1", client_id="c1")
    sent, client_id = client.submitted[0]
    assert reg.asked == [ART_WORKFLOW_ID] and client_id == "c1"
    assert sent["4"]["inputs"] == {"prompt": "a cat on a table", "negative_prompt": "blurry"}
    assert (sent["12"]["inputs"]["width"], sent["12"]["inputs"]["height"], sent["8"]["inputs"]["noise_seed"]) == (1344, 768, 7)
    assert sent["11"]["inputs"]["filename_prefix"] == "panel_p1" and WORKFLOW["8"]["inputs"]["noise_seed"] == 0  # the approved graph is not mutated
    assert (img.width, img.height, img.workflow_id, img.seed, img.model_files) == (1344, 768, ART_WORKFLOW_ID, 7, ["qwen.safetensors"])


def test_a_size_the_workflow_cannot_honour_is_rejected_before_any_gpu_work():
    client = FakeClient(png(1000, 768))
    with pytest.raises(ComfyImageGenerationError, match="alignment"):
        ArtEngine(client, FakeRegistry()).generate("p", "", 1000, 768)  # not a multiple of 16
    with pytest.raises(ComfyImageGenerationError, match="policy"):
        ArtEngine(client, FakeRegistry()).generate("p", "", 4096, 768)
    assert client.submitted == []


def test_output_of_the_wrong_size_or_not_an_image_is_rejected():
    with pytest.raises(ComfyImageGenerationError, match="dimensions"):
        ArtEngine(FakeClient(png(512, 512)), FakeRegistry()).generate("p", "", 1024, 768)
    with pytest.raises(ComfyImageGenerationError, match="invalid image"):
        ArtEngine(FakeClient(b"not a png"), FakeRegistry()).generate("p", "", 1024, 768)


def test_a_workflow_that_is_not_ready_fails_with_what_is_missing():
    with pytest.raises(ComfyImageGenerationError, match="qwen.safetensors"):
        ArtEngine(FakeClient(png(1024, 768)), FakeRegistry(ready=False)).generate("p", "", 1024, 768)


def test_cancel_and_timeout(monkeypatch):
    monkeypatch.setattr(art_mod.time, "sleep", lambda s: None)
    with pytest.raises(ComfyImageGenerationError, match="cancelled"):
        ArtEngine(FakeClient(history_ready=False), FakeRegistry()).run({}, is_cancelled=lambda: True)
    with pytest.raises(ArtTimeoutError) as exc:
        ArtEngine(FakeClient(history_ready=False), FakeRegistry()).run({}, timeout=0.0)
    assert isinstance(exc.value, TimeoutError)  # callers that already catch TimeoutError keep working


def test_there_is_exactly_one_text_to_image_workflow_in_the_registry():
    from engine.comfyui.registry import ComfyWorkflowRegistry

    reg = ComfyWorkflowRegistry.__new__(ComfyWorkflowRegistry)
    entries = ComfyWorkflowRegistry._load_entries(reg) if hasattr(ComfyWorkflowRegistry, "_load_entries") else None
    if entries is None:  # registry API differs: read the approved list file directly
        import json
        from pathlib import Path

        entries = json.loads((Path(art_mod.__file__).parent / "workflow_registry.json").read_text(encoding="utf-8"))
    text_to_image = [w["id"] for w in entries if w.get("purpose") == "text_to_image"]
    assert text_to_image == [ART_WORKFLOW_ID], text_to_image
