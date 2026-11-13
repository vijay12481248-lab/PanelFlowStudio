"""The central art engine (engine/comfyui/art.py): the only text-to-image path in PanelFlow."""
import io

import pytest
from PIL import Image

from engine.comfyui import art as art_mod
from engine.comfyui.art import ART_WORKFLOW_ID, EDIT_WORKFLOW_ID, ArtEngine, ArtTimeoutError, ComfyImageGenerationError

WORKFLOW = {
    "4": {"class_type": "TextEncodeQwenImage21", "inputs": {"prompt": "", "negative_prompt": "", "images.image_1": None}},
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
    "reference_image": {"node_id": "4", "input": "images.image_1", "class_type": "TextEncodeQwenImage21"},
}


def png(w, h):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), "orange").save(buf, format="PNG")
    return buf.getvalue()


class FakeClient:
    def __init__(self, image=None, history_ready=True):
        self.image, self.history_ready, self.submitted = image, history_ready, []
        self.uploaded = []

    def submit_prompt(self, workflow, client_id=None):
        self.submitted.append((workflow, client_id))
        return "pid-1"

    def history(self, prompt_id):
        if not self.history_ready:
            return {}
        return {prompt_id: {"outputs": {"11": {"images": [{"filename": "o.png", "subfolder": "", "type": "output"}]}}}}

    def download_output(self, *args, **kwargs):
        return self.image

    def upload_image_bytes(self, data, filename=None):
        name = filename or "uploaded.png"
        self.uploaded.append(name)
        return name

    def upload_image(self, path):
        name = getattr(path, "name", str(path))
        self.uploaded.append(name)
        return name


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


def test_run_fails_fast_on_comfyui_execution_error():
    class ErrorClient(FakeClient):
        def history(self, prompt_id):
            return {
                prompt_id: {
                    "outputs": {},
                    "status": {
                        "status_str": "error",
                        "completed": False,
                        "messages": [
                            [
                                "execution_error",
                                {
                                    "exception_message": "torch.cuda.OutOfMemoryError: CUDA out of memory. Tried to allocate 2.40 GiB",
                                    "exception_type": "torch.cuda.OutOfMemoryError",
                                    "node_id": "5",
                                    "node_type": "KSampler",
                                },
                            ]
                        ],
                    },
                }
            }

    with pytest.raises(ComfyImageGenerationError) as exc_info:
        ArtEngine(ErrorClient(), FakeRegistry()).run({})
    assert "CUDA out of memory" in str(exc_info.value)
    assert "KSampler" in str(exc_info.value)


def test_run_fails_fast_on_execution_interrupted():
    class InterruptedClient(FakeClient):
        def history(self, prompt_id):
            return {
                prompt_id: {
                    "outputs": {},
                    "status": {
                        "status_str": "error",
                        "completed": False,
                        "messages": [["execution_interrupted", {"node_id": "8", "node_type": "RandomNoise"}]],
                    },
                }
            }

    with pytest.raises(ComfyImageGenerationError) as exc_info:
        ArtEngine(InterruptedClient(), FakeRegistry()).run({})
    assert "interrupted" in str(exc_info.value)


def test_run_fails_fast_on_malformed_error_status():
    class MalformedErrorClient(FakeClient):
        def history(self, prompt_id):
            return {
                prompt_id: {
                    "outputs": {},
                    "status": {
                        "status_str": "error",
                        "completed": False,
                        "messages": [],
                    },
                }
            }

    with pytest.raises(ComfyImageGenerationError) as exc_info:
        ArtEngine(MalformedErrorClient(), FakeRegistry()).run({})
    assert "ComfyUI execution failed" in str(exc_info.value)


def test_generate_with_reference_image_uploads_and_binds_to_text_encode_node(tmp_path):
    from pathlib import Path
    dummy_ref = tmp_path / "mira_turnaround.png"
    dummy_ref.write_bytes(png(1536, 768))

    client, reg = FakeClient(png(1344, 768)), FakeRegistry()
    engine = ArtEngine(client, reg)
    img = engine.generate("portrait of Mira", reference_image=dummy_ref)

    assert "mira_turnaround.png" in client.uploaded
    sent, _ = client.submitted[0]
    # Verify LoadImage node 13 was dynamically injected
    assert "13" in sent
    assert sent["13"]["class_type"] == "LoadImage"
    assert sent["13"]["inputs"]["image"] == "mira_turnaround.png"
    # Verify node 4 images.image_1 wires into [13, 0]
    assert sent["4"]["inputs"]["images.image_1"] == ["13", 0]


def test_generate_without_reference_image_leaves_graph_unconditioned():
    client, reg = FakeClient(png(1344, 768)), FakeRegistry()
    engine = ArtEngine(client, reg)
    img = engine.generate("portrait without ref", reference_image=None)

    assert client.uploaded == []
    sent, _ = client.submitted[0]
    # Verify no LoadImage node was injected
    assert "13" not in sent
    # Verify images.image_1 was popped from node 4
    assert "images.image_1" not in sent["4"]["inputs"]


def test_real_qwen_image_21_registry_loads_and_validates_reference_image_slot():
    from engine.comfyui.registry import ComfyWorkflowRegistry
    reg = ComfyWorkflowRegistry()
    wf, sha = reg.load(ART_WORKFLOW_ID)
    meta = reg.metadata(ART_WORKFLOW_ID)
    assert sha == meta["sha256"]
    assert "reference_image" in meta["patch_slots"]
    slot = meta["patch_slots"]["reference_image"]
    assert slot["node_id"] == "4"
    assert slot["input"] == "images.image_1"
    assert slot["class_type"] == "TextEncodeQwenImage21"
    assert "LoadImage" in meta["required_nodes"]




def test_the_h3_image_graph_draws_from_text_when_no_picture_is_bound():
    """The second image model is the registered H3-Image graph with its picture slots left out, not a second text_to_image entry."""
    import json
    from pathlib import Path

    root = Path(art_mod.__file__).parent
    entry = next(w for w in json.loads((root / "workflow_registry.json").read_text(encoding="utf-8")) if w["id"] == EDIT_WORKFLOW_ID)
    graph = json.loads((root / "workflows" / entry["filename"]).read_text(encoding="utf-8"))

    class Registry(FakeRegistry):
        def load(self, workflow_id):
            self.asked.append(workflow_id)
            return graph, "c" * 64

        def metadata(self, workflow_id):
            return entry

    client, reg = FakeClient(png(2048, 2048)), Registry()
    img = ArtEngine(client, reg).generate("a lantern on a stone stair", None, 2048, 2048, 7, "p", workflow_id=EDIT_WORKFLOW_ID)
    node = client.submitted[0][0]["4"]["inputs"]
    assert reg.asked == [EDIT_WORKFLOW_ID] and img.workflow_id == EDIT_WORKFLOW_ID
    assert node["prompt"] == "a lantern on a stone stair" and (node["width"], node["height"]) == (2048, 2048)
    assert not [name for name in node if name.startswith("images.")]  # no picture bound: text to image
    with pytest.raises(ComfyImageGenerationError, match="Image workflows"):
        ArtEngine(client, reg).generate("p", "", 1024, 768, workflow_id="anime_sdxl")
