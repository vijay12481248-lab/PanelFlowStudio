"""The fast H3 animate stage: registry entry, patching, motion prompt, beat choice and the stage itself (fake ComfyUI, no GPU)."""
import hashlib
import json
import os
import time
from pathlib import Path

import pytest

from engine.comfyui import art as comfy_art
from engine.comfyui.registry import ComfyWorkflowRegistry
from engine.original import animate
from engine.original.models import Bible, Character, Location, OriginalStory, Panel, Premise, Scene
from engine.original.shotspec import CharPose, ShotSpec

COMFY = Path(comfy_art.__file__).parent
ENTRY = next(e for e in json.loads((COMFY / "workflow_registry.json").read_text(encoding="utf-8")) if e["id"] == animate.FAST_H3_ID)
GRAPH = json.loads((COMFY / "workflows" / ENTRY["filename"]).read_text(encoding="utf-8"))

ENTRY_WAN = next(e for e in json.loads((COMFY / "workflow_registry.json").read_text(encoding="utf-8")) if e["id"] == animate.WAN21_I2V_ID)
GRAPH_WAN = json.loads((COMFY / "workflows" / ENTRY_WAN["filename"]).read_text(encoding="utf-8"))



def story(n_scenes=3, per_scene=2):
    bible = Bible(premise=Premise(title="T", genre="vox", logline="l", tone="t", setting="s"),
                  characters=[Character(id="biscuit", name="Biscuit", role="protagonist", age_group="adult", look="chubby orange tabby, white paws, green eyes, blue collar",
                                        personality="p", species="cat"),
                              Character(id="maya", name="Maya", role="companion", age_group="adult", look="black bob, round glasses, yellow hoodie, blue jeans", personality="p")],
                  locations=[Location(id="room", name="Room", look="dark room")])
    panels, k = [], 0
    for s in range(1, n_scenes + 1):
        for j in range(per_scene):
            k += 1
            action = "x" * (5 + 7 * ((k * 3) % 5))  # distinct, deterministic 'amounts of action'
            spec = ShotSpec(shot="close" if k % 2 else "medium", camera="eye_level", setting="a dark living room", lighting="blue moonlight", mood="tense",
                            key_visuals=["a phone"], characters=[CharPose(id="biscuit", side="center", pose="crouching", expression="focused", action=action)])
            panels.append(Panel(id=f"p{k:02d}_1", scene_id=f"sc{s}", shot=spec.shot, angle="eye_level", location_id="room", character_ids=["biscuit"],
                                action="a cat", caption=f"Biscuit does thing number {k}.", director=spec.model_dump()))
    scenes = [Scene(id=f"sc{s}", location_id="room", character_ids=["biscuit"], summary="s", mood="m") for s in range(1, n_scenes + 1)]
    return OriginalStory(bible=bible, scenes=scenes, panels=panels)


def test_registry_entry_is_the_approved_graph_with_no_negative_prompt_and_the_models_it_needs():
    assert hashlib.sha256((COMFY / "workflows" / ENTRY["filename"]).read_bytes()).hexdigest() == ENTRY["sha256"]
    assert ENTRY["purpose"] == "image_to_video" and "negative_prompt" not in ENTRY["patch_slots"]
    assert {n["class_type"] for n in GRAPH.values()} == set(ENTRY["required_nodes"])
    assert GRAPH["105:6"]["inputs"]["unet_name"] in ENTRY["model_files"] and GRAPH["105:13"]["inputs"]["clip_name"] in ENTRY["model_files"]
    ComfyWorkflowRegistry._validate_patch_slots(animate.FAST_H3_ID, GRAPH, ENTRY)  # every slot points at a real node and input


def test_patching_sets_prompt_seed_picture_prefix_and_duration_and_never_touches_the_approved_graph():
    before = json.dumps(GRAPH, sort_keys=True)
    out = comfy_art._patch_workflow(GRAPH, ENTRY["patch_slots"], "a prompt", None, 0, 0, 42, "video/x", reference_image="pic.png", duration=3.6)
    assert out["105:104"]["inputs"]["prompt"] == "a prompt" and out["105:15"]["inputs"]["noise_seed"] == 42
    assert out["136"]["inputs"]["image"] == "pic.png" and out["105:111"]["inputs"]["value"] == 3.6 and out["92"]["inputs"]["filename_prefix"] == "video/x"
    assert json.dumps(GRAPH, sort_keys=True) == before
    keep = comfy_art._patch_workflow(GRAPH, ENTRY["patch_slots"], "p", None, 0, 0, 1, "v", reference_image="pic.png")  # duration not given: the graph's own value stays
    assert keep["105:111"]["inputs"]["value"] == GRAPH["105:111"]["inputs"]["value"]


def test_the_negative_prompt_slot_is_still_required_to_be_honoured_where_a_graph_declares_one():
    slots = {"prompt": {"node_id": "4", "input": "text", "class_type": "T"}, "negative_prompt": {"node_id": "5", "input": "text", "class_type": "T"},
             "seed": {"node_id": "6", "input": "seed", "class_type": "S"}, "filename_prefix": {"node_id": "7", "input": "p", "class_type": "V"}}
    wf = {"4": {"class_type": "T", "inputs": {"text": ""}}, "5": {"class_type": "T", "inputs": {"text": ""}}, "6": {"class_type": "S", "inputs": {"seed": 0}},
          "7": {"class_type": "V", "inputs": {"p": ""}}}
    out = comfy_art._patch_workflow(wf, slots, "pos", "neg", 0, 0, 3, "pre")
    assert out["4"]["inputs"]["text"] == "pos" and out["5"]["inputs"]["text"] == "neg"


def test_motion_prompt_comes_from_the_shot_spec_and_the_narration_and_asks_for_everything_else_to_stay():
    s = story()
    text = animate.motion_prompt(s, s.panels[0])
    assert "Biscuit (chubby orange tabby, white paws, green eyes) crouching" in text and "Biscuit does thing number 1." in text
    assert "a dark living room" in text and "everything else stays exactly as drawn" in text
    assert "Static Shot" in text and "push-in" not in text  # the default camera is static (a push-in in every shot zoomed 38% on average)
    moved = s.panels[1].model_copy(update={"camera": "a slow, steady push-in"})
    assert "The camera does a slow, steady push-in." in animate.motion_prompt(s, moved) and "Static Shot" not in animate.motion_prompt(s, moved)  # opt-in per panel
    plain = s.panels[0].model_copy(update={"director": {}, "action": "a cat sits"})
    assert "a cat sits" in animate.motion_prompt(s, plain)  # an undirected panel still gets a prompt


def test_pick_beats_takes_the_most_active_beat_of_each_scene_and_respects_the_cap():
    s = story(n_scenes=4, per_scene=3)
    pick = animate.pick_beats(s)
    assert len(pick) == max(1, round(12 / 4.5)) == 3
    scenes = [next(p.scene_id for p in s.panels if p.id == i) for i in pick]
    assert len(set(scenes)) == 3  # one per scene
    assert pick == sorted(pick)  # story order
    assert len(animate.pick_beats(s, max_clips=1)) == 1 and len(animate.pick_beats(s, max_clips=6)) == 6
    assert pick == animate.pick_beats(s)  # deterministic


class FakeClient:
    def __init__(self):
        self.uploads = []

    def upload_image(self, path):
        self.uploads.append(path.name)
        return "up_" + path.name


class FakeEngine:
    def __init__(self, client, registry, fail_on=()):
        self.fail_on, self.graphs = fail_on, []

    def run(self, wf, **kw):
        self.graphs.append(wf)
        img = wf.get("6", {}).get("inputs", {}).get("image") or wf.get("136", {}).get("inputs", {}).get("image")
        if img in self.fail_on:
            raise RuntimeError("ComfyUI did not produce a video")
        assert kw["collect"] is not None  # the video collector, not the image one
        return b"MP4", f"pid{len(self.graphs)}", {}


FAIL: set = set()  # uploaded picture names the fake ComfyUI should fail on


@pytest.fixture
def rig(tmp_path, monkeypatch):
    FAIL.clear()
    s = story(n_scenes=2, per_scene=2)
    ws = tmp_path / "ws"
    (ws / "panels").mkdir(parents=True)
    for p in s.panels:
        (ws / "panels" / f"{p.id}.png").write_bytes(b"png")
    client, engines, released = FakeClient(), [], []

    class Registry:
        def __init__(self, c):
            pass

        def preflight(self, wid):
            return {"ready": True, "missing_nodes": [], "missing_models": []}

        def load(self, wid):
            if wid == animate.WAN21_I2V_ID:
                return GRAPH_WAN, "wan_sha"
            return GRAPH, "sha"

        def metadata(self, wid):
            if wid == animate.WAN21_I2V_ID:
                return ENTRY_WAN
            return ENTRY

    def make_engine(c, r):
        e = FakeEngine(c, r, fail_on=tuple(FAIL))
        engines.append(e)
        return e

    monkeypatch.setattr(animate, "ComfyWorkflowRegistry", Registry)
    monkeypatch.setattr(animate, "ArtEngine", make_engine)
    monkeypatch.setattr(animate, "release_ollama", lambda: released.append(1))
    return s, ws, client, engines, released


def test_the_stage_writes_a_clip_per_beat_logs_how_it_was_made_and_frees_the_llm_first(rig):
    s, ws, client, engines, released = rig
    out = animate.animate_beats(s, ws, ["p01_1", "p03_1"], client=client, workflow_id=animate.FAST_H3_ID)
    assert out["animated"] == ["p01_1", "p03_1"] and out["failed"] == [] and released == [1]
    assert (ws / "clips" / "p01_1.mp4").read_bytes() == b"MP4"
    g = engines[0].graphs[0]
    assert g["136"]["inputs"]["image"] == "up_p01_1.png" and g["105:111"]["inputs"]["value"] == animate.DEFAULT_SECONDS
    assert "Biscuit does thing number 1." in g["105:104"]["inputs"]["prompt"] and g["92"]["inputs"]["filename_prefix"] == "video/panelflow_p01_1"
    log = json.loads((ws / "clips" / "animate.json").read_text())
    assert log["p01_1"]["workflow"] == animate.FAST_H3_ID and log["p01_1"]["workflow_sha256"] == "sha" and log["p01_1"]["seed"] != log["p03_1"]["seed"]


def test_a_fresh_clip_is_reused_and_a_clip_older_than_its_picture_is_made_again(rig):
    s, ws, client, engines, released = rig
    animate.animate_beats(s, ws, ["p01_1"], client=client, workflow_id=animate.FAST_H3_ID)
    again = animate.animate_beats(s, ws, ["p01_1"], client=client, workflow_id=animate.FAST_H3_ID)
    assert again["reused"] == ["p01_1"] and again["animated"] == []
    old = time.time() - 100
    os.utime(ws / "clips" / "p01_1.mp4", (old, old))  # the picture was redrawn after the clip was made
    assert animate.animate_beats(s, ws, ["p01_1"], client=client, workflow_id=animate.FAST_H3_ID)["animated"] == ["p01_1"]


def test_one_failed_beat_does_not_stop_the_others(rig):
    s, ws, client, engines, released = rig
    FAIL.add("up_p01_1.png")
    out = animate.animate_beats(s, ws, ["p01_1", "p02_1"], client=client, workflow_id=animate.FAST_H3_ID)
    assert out["animated"] == ["p02_1"] and out["failed"][0]["beat"] == "p01_1" and "did not produce a video" in out["failed"][0]["error"]
    assert not (ws / "clips" / "p01_1.mp4").exists()  # that beat simply stays a still


def test_unknown_beats_and_missing_pictures_are_refused_before_any_gpu_time(rig):
    s, ws, client, engines, released = rig
    with pytest.raises(ValueError, match="unknown beats"):
        animate.animate_beats(s, ws, ["nope"], client=client)
    (ws / "panels" / "p02_1.png").unlink()
    with pytest.raises(ValueError, match="no picture yet"):
        animate.animate_beats(s, ws, ["p02_1"], client=client)
    assert released == [] and engines == []


def test_cancel_stops_between_beats(rig):
    s, ws, client, engines, released = rig
    with pytest.raises(RuntimeError, match="cancelled"):
        animate.animate_beats(s, ws, ["p01_1"], client=client, is_cancelled=lambda: True)


def test_the_episode_animate_stage_reports_clip_failures_and_never_stops_the_episode(monkeypatch):
    from engine.original import episode

    steps = []
    ok = {"animated": ["p01_1"], "reused": [], "failed": [{"beat": "p02_1", "error": "no video"}]}
    monkeypatch.setattr(episode, "animate_beats", lambda story, ws, **kw: (kw["progress"](0.5, "half"), ok)[1])
    notes = episode.animate_stage("STORY", "WS", lambda p, m: steps.append((round(p, 2), m)), lambda: False)
    assert notes == ["clip failed for p02_1: no video"] and steps[0] == (0.55, "Animating key moments") and steps[1] == (0.6, "half")

    def broken(story, ws, **kw):
        raise RuntimeError("ComfyUI is not reachable")

    monkeypatch.setattr(episode, "animate_beats", broken)
    assert episode.animate_stage("STORY", "WS", lambda p, m: None, lambda: False) == ["animation skipped: ComfyUI is not reachable"]  # the stills still make a video

    def cancelled(story, ws, **kw):
        raise RuntimeError("cancelled")

    monkeypatch.setattr(episode, "animate_beats", cancelled)
    with pytest.raises(RuntimeError, match="cancelled"):
        episode.animate_stage("STORY", "WS", lambda p, m: None, lambda: True)  # a cancel is never swallowed


def test_wan21_animate_beats_generates_clips(rig):
    """Verifies animate_beats with Wan2.1 workflow generates clips and records metadata."""
    s, ws, client, engines, released = rig
    out = animate.animate_beats(s, ws, ["p01_1", "p03_1"], client=client)  # default is WAN21_I2V_ID
    assert out["workflow"] == animate.WAN21_I2V_ID
    assert out["animated"] == ["p01_1", "p03_1"]
    assert out["failed"] == []
    assert released == [1]  # Ollama released before GPU work
    assert (ws / "clips" / "p01_1.mp4").read_bytes() == b"MP4"
    assert (ws / "clips" / "p03_1.mp4").read_bytes() == b"MP4"

    # Verify ComfyUI graph patching
    g = engines[0].graphs[0]
    assert g["6"]["inputs"]["image"] == "up_p01_1.png"
    assert "Biscuit" in g["8"]["inputs"]["text"]
    assert "<Picture 1>" not in g["8"]["inputs"]["text"]
    assert g["9"]["inputs"]["text"] == animate.UNIVERSAL_VIDEO_NEGATIVE_PROMPT
    assert g["10"]["inputs"]["width"] == animate.DEFAULT_WIDTH
    assert g["10"]["inputs"]["height"] == animate.DEFAULT_HEIGHT
    assert g["11"]["inputs"]["seed"] != 0
    assert g["14"]["inputs"]["filename_prefix"] == "video/panelflow_p01_1"

    # Verify metadata logged to animate.json
    log = json.loads((ws / "clips" / "animate.json").read_text())
    assert log["p01_1"]["workflow"] == animate.WAN21_I2V_ID
    assert log["p01_1"]["workflow_sha256"] == "wan_sha"
    assert log["p01_1"]["seed"] != log["p03_1"]["seed"]
    assert log["p01_1"]["clip"] == "clips/p01_1.mp4"
    assert log["p01_1"]["prompt"] == g["8"]["inputs"]["text"]


def test_wan21_motion_prompt_natural_prose():
    """Verifies prompt lacks MiniMax XML tags and contains natural kinematic descriptions."""
    s = story()
    text = animate.wan_motion_prompt(s, s.panels[0])

    # No MiniMax XML or multimodal header scaffolding
    assert "<Picture 1>" not in text
    assert "integrated_multimodal_description:" not in text
    assert "overall_soundscape:" not in text
    assert "non_diegetic_music:" not in text
    assert "[Shot 1]" not in text

    # Natural kinematic and character descriptions
    assert "Biscuit (chubby orange tabby, white paws, green eyes) crouching" in text
    assert "expression focused" in text
    assert "a dark living room" in text
    assert "blue moonlight lighting, tense atmosphere" in text
    assert "Action of the moment: Biscuit does thing number 1." in text
    assert "Natural cloth and hair physics" in text
    assert "identity and environment stay consistent as drawn" in text
    assert "static, fixed on a tripod" in text and "push-in" not in text

    # Camera move opt-in
    moved = s.panels[1].model_copy(update={"camera": "a slow, steady push-in"})
    moved_text = animate.wan_motion_prompt(s, moved)
    assert "The camera does a slow, steady push-in" in moved_text
    assert "static" not in moved_text

    # Undirected panel
    plain = s.panels[0].model_copy(update={"director": {}, "action": "a cat sits on a rug"})
    plain_text = animate.wan_motion_prompt(s, plain)
    assert "a cat sits on a rug" in plain_text
    assert "<Picture 1>" not in plain_text

    # motion_prompt dispatch matches wan_motion_prompt
    dispatched = animate.motion_prompt(s, s.panels[0], workflow_id=animate.WAN21_I2V_ID)
    assert dispatched == text


def test_wan21_patch_slots_and_negative_prompt():
    """Verifies _patch_workflow injects negative_prompt, width, height, and reference_image."""
    before = json.dumps(GRAPH_WAN, sort_keys=True)
    out = comfy_art._patch_workflow(
        GRAPH_WAN,
        ENTRY_WAN["patch_slots"],
        prompt="A dynamic motion prompt",
        negative_prompt="blurry, distorted, morphing",
        width=832,
        height=480,
        seed=424242,
        prefix="video/wan_test",
        reference_image="uploaded_frame.png",
    )
    # Check all slots
    assert out["6"]["inputs"]["image"] == "uploaded_frame.png"
    assert out["8"]["inputs"]["text"] == "A dynamic motion prompt"
    assert out["9"]["inputs"]["text"] == "blurry, distorted, morphing"
    assert out["10"]["inputs"]["width"] == 832
    assert out["10"]["inputs"]["height"] == 480
    assert out["11"]["inputs"]["seed"] == 424242
    assert out["14"]["inputs"]["filename_prefix"] == "video/wan_test"

    # Immutability check
    assert json.dumps(GRAPH_WAN, sort_keys=True) == before


def test_wan21_animate_beats_mtime_caching(rig):
    """Verifies existing newer clips are not regenerated."""
    s, ws, client, engines, released = rig
    first = animate.animate_beats(s, ws, ["p01_1"], client=client)
    assert first["animated"] == ["p01_1"]
    assert first["reused"] == []

    # Second run without touching picture: clip is reused
    again = animate.animate_beats(s, ws, ["p01_1"], client=client)
    assert again["reused"] == ["p01_1"]
    assert again["animated"] == []

    # Picture touched after clip: clip is regenerated
    old = time.time() - 100
    os.utime(ws / "clips" / "p01_1.mp4", (old, old))
    regenerated = animate.animate_beats(s, ws, ["p01_1"], client=client)
    assert regenerated["animated"] == ["p01_1"]
    assert regenerated["reused"] == []


def test_wan21_error_resilience(rig):
    """Verifies individual beat failures log to failed list and don't stop other beats."""
    s, ws, client, engines, released = rig
    FAIL.add("up_p01_1.png")
    out = animate.animate_beats(s, ws, ["p01_1", "p02_1"], client=client)
    assert out["workflow"] == animate.WAN21_I2V_ID
    assert out["animated"] == ["p02_1"]
    assert len(out["failed"]) == 1
    assert out["failed"][0]["beat"] == "p01_1"
    assert "did not produce a video" in out["failed"][0]["error"]
    assert not (ws / "clips" / "p01_1.mp4").exists()
    assert (ws / "clips" / "p02_1.mp4").exists()


def test_wan21_custom_parameters(rig):
    """Verifies custom dimensions and negative prompt override."""
    s, ws, client, engines, released = rig
    custom_neg = "ugly, oversaturated, deformed"
    out = animate.animate_beats(
        s,
        ws,
        ["p01_1"],
        width=1280,
        height=720,
        negative_prompt=custom_neg,
        client=client,
    )
    assert out["animated"] == ["p01_1"]
    g = engines[0].graphs[0]
    assert g["10"]["inputs"]["width"] == 1280
    assert g["10"]["inputs"]["height"] == 720
    assert g["9"]["inputs"]["text"] == custom_neg
