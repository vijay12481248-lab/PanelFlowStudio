"""FL2VA / L2VA / T2VA: registered workflows load with matching checksums and wiring; prompts follow the official skeleton."""
import hashlib
import json
from pathlib import Path

import pytest

from engine.comfyui import registry as regmod
from engine.original import h3_modes as hm

ROOT = Path(hm.__file__).resolve().parents[1] / "comfyui"


def _entries():
    return {w["id"]: w for w in json.loads((ROOT / "workflow_registry.json").read_text(encoding="utf-8"))}


@pytest.mark.parametrize("mode", ["fl2va", "l2va", "t2va"])
def test_workflow_is_registered_checksummed_and_wired(mode):
    wid = hm.WORKFLOWS[mode]
    e = _entries()[wid]
    raw = (ROOT / "workflows" / e["filename"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == e["sha256"]
    g = json.loads(raw)
    regmod.ComfyWorkflowRegistry._validate_patch_slots(wid, g, e)  # slots exist, class types match, names are allowed
    inp = g["105:104"]["inputs"]
    assert ("first_frame" in inp, "last_frame" in inp) == {"fl2va": (True, True), "l2va": (False, True), "t2va": (False, False)}[mode]
    assert g["105:91"]["inputs"]["fps"] == 24
    assert set(e["required_nodes"]) >= {"MiniMaxH3ImageToVideo", "SamplerCustomAdvanced"}
    if mode == "t2va":
        assert {"GetImageSize", "LoadImage"}.isdisjoint(e["required_nodes"]) and (inp["width"], inp["height"]) == hm.T2VA_SIZE


def test_clip_length_is_the_frame_grid_not_the_length_asked_for():
    assert hm.clip_seconds(4.0) == pytest.approx(107 / 24) and hm.clip_seconds(3.75) == pytest.approx(90 / 24)


def test_prompts_follow_the_official_skeleton():
    fl = hm.fl2va_prompt("the cup rises to her lips", 3.75)
    assert fl.startswith("How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; "
                         "Picture 2 (from Shot 1) aligns with the 3.75-second mark of the target video.\nintegrated_multimodal_description: [Shot 1] ")
    assert "Static Shot" in fl and "last frame is reached" in fl and fl.endswith("non_diegetic_music: none")
    l2 = hm.l2va_prompt("a hand reaches for the door", 4.0)
    assert "<Picture 1> (from [Shot 1]) aligns with the 4.46-second mark" in l2  # 4.0 s snaps up to 107 frames
    t2 = hm.t2va_prompt("a stick figure on a white background", "it walks right")
    assert t2.startswith("integrated_multimodal_description: [Shot 1] a stick figure") and "How the reference" not in t2 and "[Shot 2]" not in t2


def test_i2va_prompt_is_the_film_pipelines_shape():
    p = hm.i2va_prompt("she lifts the cup")
    assert p.startswith("For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.\nintegrated_multimodal_description: [Shot 1] she lifts the cup.")
    assert "Static Shot" in p and hm.WORKFLOWS["i2va"] == "fastvideo_h3_film_free"


def test_make_clip_refuses_missing_frames():
    with pytest.raises(ValueError):
        hm.make_clip("fl2va", "p", seed=1, seconds=3, first=Path("a.png"))
    with pytest.raises(ValueError):
        hm.make_clip("l2va", "p", seed=1, seconds=3)
    with pytest.raises(ValueError):
        hm.make_clip("i2va", "p", seed=1, seconds=3)


def test_ref2va_workflow_is_the_omniref_graph_with_two_reference_slots():
    e = _entries()["fastvideo_h3_omniref"]
    raw = (ROOT / "workflows" / e["filename"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == e["sha256"]
    g = json.loads(raw)
    regmod.ComfyWorkflowRegistry._validate_patch_slots("fastvideo_h3_omniref", g, e)
    node = g["105:104"]
    assert node["class_type"] == "MiniMaxH3ReferenceToVideo" and {"ref_images.ref_image_0", "ref_images.ref_image_1"} <= set(node["inputs"])
    assert g["105:6"]["inputs"]["unet_name"] == "fasth3_omniref_8step_pruned_int8_convrot.safetensors" in e["model_files"]
    assert g["105:9"]["inputs"]["steps"] == 8 and g["105:17"]["inputs"]["sampler_name"] == "euler"  # the template's sampler, 8 steps
    assert (g["105:143"]["inputs"]["shift_video"], g["105:143"]["inputs"]["shift_audio"]) == (12, 3)
    assert g["105:127"]["inputs"]["selection"] == "vsa" and g["105:127"]["inputs"]["selection.keep_percent"] == 10  # FastH3 must run VSA, never plain block-sparse
    assert {"reference_image", "reference_image_b", "width", "height"} <= set(e["patch_slots"]) and "MiniMaxH3ImageToVideo" not in e["required_nodes"]


def test_ref2va_prompt_has_the_six_official_sections_in_order():
    p = hm.ref2va_prompt([("the girl with copper-red hair and a green scarf", 1, "fully_preserved", "face, hair and outfit colours"),
                          ("the sky over floating rocks", 2, "partially_preserved", "the rock spire and the light")], "she flies the glider around the spire")
    order = ["subject_definitions:", "summary:", "retention_analysis:", "detailed_description:", "overall_soundscape:", "non_diegetic_music:"]
    assert [p.index(k) for k in order] == sorted(p.index(k) for k in order)
    assert "<Subject 1> is the girl with copper-red hair and a green scarf in <Picture 1>." in p and "<Subject 2> is the sky over floating rocks in <Picture 2>." in p
    assert "<Subject 1> (appears in [Shot 1]): fully_preserved - face, hair and outfit colours." in p and "[reference generation]" in p
    assert "[Shot 1] she flies the glider around the spire." in p and "Static Shot" in p
    with pytest.raises(ValueError):
        hm.ref2va_prompt([("x", 1, "kept", "y")], "a")  # not an official retention word
    with pytest.raises(ValueError):
        hm.ref2va_prompt([], "a")


def test_ref2va_needs_one_or_two_references():
    with pytest.raises(ValueError):
        hm.make_clip("ref2va", "p", seed=1, seconds=3)
    with pytest.raises(ValueError):
        hm.make_clip("ref2va", "p", seed=1, seconds=3, refs=[Path("a.png"), Path("b.png"), Path("c.png")])
