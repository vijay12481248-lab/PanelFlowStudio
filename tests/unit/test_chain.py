"""H3 chain driver: registered workflows, continuation prompts, plan checks, and the clip order / latent wiring (fake ComfyUI, no GPU)."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from engine.comfyui import registry as regmod
from engine.original import chain

ROOT = Path(chain.__file__).resolve().parents[1] / "comfyui"
SRC = Path(__file__).resolve().parents[2] / "stories" / "dawn_gate_source.py"


@pytest.fixture(scope="module")
def story():
    spec = importlib.util.spec_from_file_location("dawn_gate_source", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.story


@pytest.fixture
def ws(tmp_path, story):
    (tmp_path / "film" / "frames").mkdir(parents=True)
    for p in story.panels:
        (tmp_path / "film" / "frames" / f"{p.id}.png").write_bytes(b"png")
    return tmp_path


@pytest.mark.parametrize("wid", [chain.START, chain.CONTINUE, chain.STITCH])
def test_workflow_is_registered_checksummed_and_wired(wid):
    e = {w["id"]: w for w in json.loads((ROOT / "workflow_registry.json").read_text(encoding="utf-8"))}[wid]
    raw = (ROOT / "workflows" / e["filename"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == e["sha256"]
    regmod.ComfyWorkflowRegistry._validate_patch_slots(wid, json.loads(raw), e)
    assert (e["purpose"] == "latent_stitch") == (wid == chain.STITCH)
    if wid != chain.STITCH:
        assert {"latent_prefix", "clip_index", "last_image"} <= set(e["patch_slots"]) and ("reference_image" in e["patch_slots"]) == (wid == chain.START)


def test_only_a_stitch_graph_may_skip_prompt_and_seed():
    g = {"4": {"class_type": "X", "inputs": {"filename_prefix": "a"}}}
    slots = {"filename_prefix": {"node_id": "4", "input": "filename_prefix", "class_type": "X"}}
    entry = {"patch_slots": slots, "dimension_policy": {"mode": "exact", "min": 1, "max": 9, "multiple_of": 1}}
    regmod.ComfyWorkflowRegistry._validate_patch_slots("abc", g, {**entry, "purpose": "latent_stitch"})
    with pytest.raises(regmod.WorkflowRegistryError):
        regmod.ComfyWorkflowRegistry._validate_patch_slots("abc", g, {**entry, "purpose": "image_to_video"})


def test_continuation_prompt_keeps_the_panels_motion_and_adds_the_carry_over(story):
    p = next(p for p in story.panels if p.id == "p034")
    t = chain.continuation_prompt(story, p)
    assert t.startswith("integrated_multimodal_description:\n[Shot 1] Continue directly from the incoming H3 Motion Context.")
    assert "plunge into the canyon" in t and "Static Shot" in t and "<Picture" not in t and t.endswith("non_diegetic_music:\nNo non-diegetic music.")


def test_plan_uses_the_first_panels_prompt_for_clip_1_and_warns_on_shot_size_changes(story, ws):
    first, links, warn = chain.plan_chain(story, ws, ["p032", "p033", "p034"])
    assert first.name == "p032.png" and [l.panel_id for l in links] == ["p033", "p034"]
    assert links[0].prompt.startswith("For the target video") and links[1].prompt.startswith("integrated_multimodal_description:\n[Shot 1] Continue")
    assert links[0].seed != links[1].seed and chain.plan_chain(story, ws, ["p032", "p033"])[1][0].seed == links[0].seed  # deterministic
    assert warn == []  # p032 -> p033 -> p034 are all wide
    assert chain.plan_chain(story, ws, ["p031", "p032"])[2]  # extreme_close -> wide is reported


def test_plan_refuses_bad_input(story, ws):
    with pytest.raises(ValueError):
        chain.plan_chain(story, ws, ["p032"])
    with pytest.raises(ValueError):
        chain.plan_chain(story, ws, ["p032", "nope"])
    (ws / "film" / "frames" / "p033.png").unlink()
    with pytest.raises(FileNotFoundError):
        chain.plan_chain(story, ws, ["p032", "p033"])


class _Client:
    """Records what the driver submits; every submit 'finishes' at once with a fake mp4."""

    def __init__(self):
        self.submitted, self.uploads = [], []

    def upload_image(self, path):
        self.uploads.append(Path(path).name)
        return f"up_{Path(path).name}"

    def capabilities(self):
        graphs = [json.loads((ROOT / "workflows" / f"herrgott_h3_chain_{w}.api.json").read_text()) for w in ("start", "continue", "stitch")]
        return {"available": True, "node_names": [n["class_type"] for g in graphs for n in g.values()],
                "models": {"all": ["fastvideo_fasth3_8step_v2_pruned_int8_convrot.safetensors", "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
                                   "minimax_h3_video_vae_int8_convrot.safetensors", "minimax_h3_audio_vae_fp32.safetensors"]}}

    def api_workflow_root(self):
        return ROOT / "workflows"

    def submit_prompt(self, workflow, **_):
        self.submitted.append(workflow)
        return f"pid{len(self.submitted)}"

    def history(self, pid):
        if "8" not in self.submitted[int(pid[3:]) - 1]:  # the stitch node reports only its file path (through PreviewAny)
            return {pid: {"outputs": {"5": {"text": ["E:\\ComfyUI\\output\\video\\pf_unit_run_stitched_00001_.mp4"]}}}}
        return {pid: {"outputs": {"9": {"videos": [{"filename": f"{pid}.mp4", "subfolder": "video", "type": "output"}]}}}}

    def download_output(self, filename, subfolder="", folder_type="output"):
        return f"{subfolder}/{filename}".encode()


def test_run_chain_renders_in_order_and_wires_each_clip_to_the_previous_latent(story, ws, monkeypatch):
    monkeypatch.setattr("engine.comfyui.art.POLL_SECONDS", 0)
    c = _Client()
    r = chain.run_chain(story, ws, ["p032", "p033", "p034", "p037"], "unit_run", client=c)
    assert [w["8"]["class_type"] for w in c.submitted[:3]] == ["H3ContinuousStartV14", "H3ContinuousContinueV14", "H3ContinuousContinueV14"]
    assert len(c.submitted) == 4 and "8" not in c.submitted[3]  # three clips + the stitch
    start, c2, c3, stitch = c.submitted
    assert start["5"]["inputs"]["image"] == "up_p032.png" and start["6"]["inputs"]["image"] == "up_p033.png"
    assert (start["21"]["inputs"]["filename_prefix"], start["21"]["inputs"]["clip_index"]) == ("h3_continuous/pf_unit_run/clip", 1)
    assert (c2["5"]["inputs"]["latent_path"], c2["5"]["inputs"]["clip_index"], c2["21"]["inputs"]["clip_index"], c2["6"]["inputs"]["image"]) == ("h3_continuous/pf_unit_run", 1, 2, "up_p034.png")
    assert (c3["5"]["inputs"]["clip_index"], c3["21"]["inputs"]["clip_index"], c3["6"]["inputs"]["image"]) == (2, 3, "up_p037.png")
    assert start["8"]["inputs"]["width"] == 960 and c3["8"]["inputs"]["duration"] == chain.SECONDS
    assert stitch["4"]["inputs"]["latent_prefix"] == "h3_continuous/pf_unit_run/clip" and (stitch["4"]["inputs"]["first_clip"], stitch["4"]["inputs"]["last_clip"]) == (1, 3)
    assert r["final"].read_bytes() == b"video/pf_unit_run_stitched_00001_.mp4" and r["clips"][0].read_bytes() == b"video/pid1.mp4" and [p.name for p in r["clips"]] == ["clip_1.mp4", "clip_2.mp4", "clip_3.mp4"]


def test_run_chain_refuses_a_bad_run_name(story, ws):
    with pytest.raises(ValueError):
        chain.run_chain(story, ws, ["p032", "p033"], "../evil", client=_Client())
