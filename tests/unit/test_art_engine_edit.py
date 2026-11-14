"""The MiniMax-H3-Image edit path: one checkpoint that edits a picture from a written instruction.

The edit runs through the same submit -> poll -> download step as the art workflow
(`ArtEngine.run`), so there is no second submit/poll loop, and it is registered as
`image_edit`, not `text_to_image`: the art workflow stays qwen_image_21.
"""
import io

import pytest
from PIL import Image

from engine.comfyui import art as art_mod
from engine.comfyui.art import EDIT_WORKFLOW_ID, ArtEngine, ComfyImageGenerationError
from engine.comfyui.edit_prompt import compose_edit_prompt
from engine.comfyui.service import h3_edit_size

# The approved MiniMax-H3-Image graph: a MiniMax conditioning node that takes its
# reference pictures through autogrow images.image_<n> slots.
EDIT_WORKFLOW = {
    "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "h3.safetensors", "weight_dtype": "default"}},
    "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen3vl.safetensors", "type": "minimax"}},
    "3": {"class_type": "VAELoader", "inputs": {"vae_name": "h3_image_vae.safetensors"}},
    "4": {"class_type": "MiniMaxH3ImageConditioning",
          "inputs": {"clip": ["2", 0], "vae": ["3", 0], "prompt": "", "width": 2048, "height": 2048,
                     "images.image_1": "", "images.image_2": ""}},
    "5": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["4", 0]}},
    "6": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "seed": 0, "steps": 6, "cfg": 1.0,
                                               "sampler_name": "euler", "scheduler": "simple",
                                               "positive": ["4", 0], "negative": ["5", 0],
                                               "latent_image": ["4", 1], "denoise": 1.0}},
    "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["3", 0]}},
    "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "h3"}},
}
EDIT_SLOTS = {
    "prompt": {"node_id": "4", "input": "prompt", "class_type": "MiniMaxH3ImageConditioning"},
    "seed": {"node_id": "6", "input": "seed", "class_type": "KSampler"},
    "filename_prefix": {"node_id": "8", "input": "filename_prefix", "class_type": "SaveImage"},
    "width": {"node_id": "4", "input": "width", "class_type": "MiniMaxH3ImageConditioning"},
    "height": {"node_id": "4", "input": "height", "class_type": "MiniMaxH3ImageConditioning"},
    "reference_image": {"node_id": "4", "input": "images.image_1", "class_type": "MiniMaxH3ImageConditioning"},
    "reference_image_b": {"node_id": "4", "input": "images.image_2", "class_type": "MiniMaxH3ImageConditioning"},
}


def png(w, h):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), "teal").save(buf, format="PNG")
    return buf.getvalue()


class FakeClient:
    def __init__(self, image=None):
        self.image = image if image is not None else png(2048, 2048)
        self.submitted = []
        self.uploaded = []

    def submit_prompt(self, workflow, client_id=None):
        self.submitted.append((workflow, client_id))
        return "pid-1"

    def history(self, prompt_id):
        return {prompt_id: {"outputs": {"8": {"images": [{"filename": "o.png", "subfolder": "", "type": "output"}]}}}}

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
        return EDIT_WORKFLOW, "c" * 64

    def metadata(self, workflow_id):
        return {"patch_slots": EDIT_SLOTS, "model_files": ["h3.safetensors", "qwen3vl.safetensors"],
                "dimension_policy": {"mode": "exact", "min": 256, "max": 4096, "multiple_of": 32}}

    def preflight(self, workflow_id):
        return {"ready": self.ready, "missing_nodes": [], "missing_models": [] if self.ready else ["h3.safetensors"]}


def _engine(ready=True, image=None):
    client = FakeClient(image)
    return ArtEngine(client, FakeRegistry(ready)), client


def test_editing_needs_a_picture_to_edit():
    engine, _ = _engine()
    with pytest.raises(ComfyImageGenerationError, match="at least one picture"):
        engine.edit("make the sky stormy", [])


def test_the_edit_binds_the_picture_to_the_conditioning_node():
    """The picture being edited is loaded and wired into the conditioning node's reference slot."""
    engine, client = _engine()
    engine.edit("make the sky stormy", [b"raw picture bytes"])
    graph = client.submitted[0][0]
    loads = {nid: n for nid, n in graph.items() if n.get("class_type") == "LoadImage"}
    assert len(loads) == 1
    load_id = next(iter(loads))
    assert graph["4"]["inputs"]["images.image_1"] == [load_id, 0]
    assert loads[load_id]["inputs"]["image"] == "uploaded.png"


def test_the_edit_sends_the_instruction_and_the_size():
    engine, client = _engine()
    engine.edit("make the sky stormy", [b"raw"], width=2048, height=2048, seed=7)
    graph = client.submitted[0][0]
    assert graph["4"]["inputs"]["prompt"] == "make the sky stormy"
    assert graph["4"]["inputs"]["width"] == 2048
    assert graph["4"]["inputs"]["height"] == 2048
    assert graph["6"]["inputs"]["seed"] == 7


def test_a_second_picture_fills_the_next_reference_slot():
    """A picture the instruction refers to goes in the next slot, not on top of the first."""
    engine, client = _engine()
    engine.edit("put the hero in the forest", [b"first", b"second"])
    graph = client.submitted[0][0]
    loads = {nid: n["inputs"]["image"] for nid, n in graph.items() if n.get("class_type") == "LoadImage"}
    assert len(loads) == 2
    assert graph["4"]["inputs"]["images.image_2"] in ([[nid, 0] for nid in loads])
    assert graph["4"]["inputs"]["images.image_1"] in ([[nid, 0] for nid in loads])


def test_the_edit_uses_the_approved_edit_workflow():
    engine, _ = _engine()
    engine.edit("make the sky stormy", [b"raw"])
    assert engine.registry.asked == [EDIT_WORKFLOW_ID]


def test_an_unused_reference_slot_is_removed_from_the_graph():
    """A slot with no picture must not reach ComfyUI as an empty reference."""
    engine, client = _engine()
    engine.edit("make the sky stormy", [b"only one"])
    graph = client.submitted[0][0]
    assert "images.image_2" not in graph["4"]["inputs"]


def test_the_edit_checks_the_size_before_spending_gpu_time():
    engine, client = _engine()
    with pytest.raises(ComfyImageGenerationError, match="dimensions"):
        engine.edit("make the sky stormy", [b"raw"], width=100, height=100)
    assert client.submitted == []  # nothing was submitted


def test_the_edit_reports_the_workflow_it_used():
    engine, _ = _engine()
    art = engine.edit("make the sky stormy", [b"raw"])
    assert art.workflow_id == EDIT_WORKFLOW_ID
    assert art.seed is not None
    assert art.width == 2048 and art.height == 2048


# The size the edit runs at, and the caption it runs on.


def test_a_small_picture_is_scaled_up_to_the_working_size():
    """Below about 4 megapixels the model gives a soft edit, so the picture is scaled up."""
    width, height = h3_edit_size(1024, 1024)
    assert (width, height) == (2048, 2048)


def test_the_edit_keeps_the_shape_of_the_picture():
    width, height = h3_edit_size(1920, 1080)
    assert abs(width / height - 1920 / 1080) < 0.05
    assert width * height > 3.5 * 1024 * 1024


def test_the_edit_size_lands_on_the_canvas_grid():
    for source in ((1000, 777), (3333, 999), (640, 480)):
        width, height = h3_edit_size(*source)
        assert width % 32 == 0 and height % 32 == 0


def test_a_very_wide_picture_stays_inside_the_limit():
    width, height = h3_edit_size(8000, 1000)
    assert width <= 4096 and height <= 4096


def test_a_picture_too_wide_to_edit_says_so():
    with pytest.raises(ComfyImageGenerationError, match="too wide or too tall"):
        h3_edit_size(20000, 200)


def test_the_caption_falls_back_to_the_instruction_when_the_local_model_is_away(monkeypatch):
    """The local model is a convenience, never a gate: the edit runs without it."""
    import httpx

    class BrokenClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            raise httpx.ConnectError("the local model is not running")

    monkeypatch.setattr(httpx, "Client", BrokenClient)
    assert compose_edit_prompt("make the sky stormy", png(64, 64)) == "make the sky stormy"


def test_the_caption_uses_the_local_model_when_it_answers(monkeypatch):
    import httpx

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"response": "The street of <Picture 1> is lit by a low orange sunset."}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, json=None, **kwargs):
            assert url.endswith("/api/generate")
            assert json["images"], "the picture has to be sent, the caption is about it"
            return FakeResponse()

    monkeypatch.setattr(httpx, "Client", FakeClient)
    caption = compose_edit_prompt("make the sky stormy", png(64, 64))
    assert caption == "The street of <Picture 1> is lit by a low orange sunset."
