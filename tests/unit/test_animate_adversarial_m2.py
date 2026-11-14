"""Adversarial stress-testing suite for Wan2.1 Image-to-Video animation pipeline (Milestone M2).

Focus areas:
1. Caching & mtime boundary conditions (equal mtime, newer mtime, touched panel, 0-byte corrupted clip).
2. Failure recovery & isolation (odd beats fail, even beats succeed, animate.json contents).
3. Cancellation handling (is_cancelled triggered before, between, or during engine.run).
4. Workspace & directory creation (missing clips directory, parent creation, corrupted metadata).
"""
import hashlib
import json
import os
import time
from pathlib import Path

import pytest

from engine.comfyui import art as comfy_art
from engine.comfyui.art import ComfyImageGenerationError
from engine.original import animate
from engine.original.models import Bible, Character, Location, OriginalStory, Panel, Premise, Scene
from engine.original.shotspec import CharPose, ShotSpec

COMFY = Path(comfy_art.__file__).parent
ENTRY_WAN = next(e for e in json.loads((COMFY / "workflow_registry.json").read_text(encoding="utf-8")) if e["id"] == animate.WAN21_I2V_ID)
GRAPH_WAN = json.loads((COMFY / "workflows" / ENTRY_WAN["filename"]).read_text(encoding="utf-8"))


def make_story(n_scenes=2, per_scene=2):
    bible = Bible(
        premise=Premise(title="AdversarialStory", genre="cyberpunk", logline="A gritty tale", tone="dark", setting="Neo-Tokyo"),
        characters=[
            Character(id="hero", name="Kaelen", role="protagonist", age_group="adult", look="cybernetic arm, leather coat, silver hair", personality="cynical"),
            Character(id="ally", name="Nyx", role="companion", age_group="adult", look="neon visor, braided cables, green jacket", personality="energetic"),
        ],
        locations=[Location(id="alley", name="Back Alley", look="rain-slicked neon alleyway")]
    )
    panels, k = [], 0
    for s in range(1, n_scenes + 1):
        for j in range(per_scene):
            k += 1
            action = f"sprint through rain {k}"
            spec = ShotSpec(
                shot="medium", camera="tracking" if k % 2 else "static",
                setting="rain-soaked pavement", lighting="flickering pink neon", mood="tense",
                key_visuals=["smoke", "flying sparks"],
                characters=[CharPose(id="hero", side="center", pose="running", expression="determined", action=action)]
            )
            panels.append(Panel(
                id=f"p{k:02d}", scene_id=f"sc{s}", shot=spec.shot, angle="eye_level",
                location_id="alley", character_ids=["hero"], action="action",
                caption=f"Kaelen evades drone {k}", director=spec.model_dump()
            ))
    scenes = [Scene(id=f"sc{s}", location_id="alley", character_ids=["hero"], summary="chase", mood="frantic") for s in range(1, n_scenes + 1)]
    return OriginalStory(bible=bible, scenes=scenes, panels=panels)


class AdvFakeClient:
    def __init__(self):
        self.uploads = []

    def upload_image(self, path: Path):
        self.uploads.append(path.name)
        return "up_" + path.name


class AdvFakeEngine:
    def __init__(self, fail_on=(), cancel_during=False, cancel_on_beat=None, delay=0.0):
        self.fail_on = set(fail_on)
        self.cancel_during = cancel_during
        self.cancel_on_beat = cancel_on_beat
        self.delay = delay
        self.graphs = []
        self.call_count = 0

    def run(self, wf, **kw):
        self.graphs.append(wf)
        self.call_count += 1
        img = wf.get("6", {}).get("inputs", {}).get("image") or wf.get("136", {}).get("inputs", {}).get("image")
        
        # Check if cancellation requested during run
        is_cancelled = kw.get("is_cancelled", lambda: False)
        if self.cancel_during or (self.cancel_on_beat and self.cancel_on_beat in str(img)):
            if is_cancelled():
                raise ComfyImageGenerationError("Image generation cancelled; ComfyUI execution may still finish")

        if img in self.fail_on:
            raise RuntimeError(f"ComfyUI simulated failure for {img}")

        if self.delay > 0:
            time.sleep(self.delay)

        return b"MP4_HEADER_VALID_VIDEO_CONTENT", f"pid_{self.call_count}", {}


@pytest.fixture
def adv_rig(tmp_path, monkeypatch):
    story = make_story(n_scenes=2, per_scene=2)  # p01, p02, p03, p04
    ws = tmp_path / "story_ws"
    panels_dir = ws / "panels"
    panels_dir.mkdir(parents=True)
    for p in story.panels:
        (panels_dir / f"{p.id}.png").write_bytes(b"VALID_PNG_DATA")

    client = AdvFakeClient()
    engine_instances = []
    released = []

    class Registry:
        def __init__(self, c):
            pass

        def preflight(self, wid):
            return {"ready": True, "missing_nodes": [], "missing_models": []}

        def load(self, wid):
            return GRAPH_WAN, "wan21_sha256_mock"

        def metadata(self, wid):
            return ENTRY_WAN

    def engine_factory(fail_on=(), cancel_during=False, cancel_on_beat=None, delay=0.0):
        def _factory(c, r):
            e = AdvFakeEngine(fail_on=fail_on, cancel_during=cancel_during, cancel_on_beat=cancel_on_beat, delay=delay)
            engine_instances.append(e)
            return e
        return _factory

    monkeypatch.setattr(animate, "ComfyWorkflowRegistry", Registry)
    monkeypatch.setattr(animate, "release_ollama", lambda: released.append(1))

    return story, ws, client, engine_factory, released, monkeypatch


# ==============================================================================
# 1. Caching & mtime boundary conditions
# ==============================================================================

def test_caching_equal_mtime_is_skipped(adv_rig):
    """When clip mtime exactly equals panel picture mtime, clip should be reused (>= condition)."""
    story, ws, client, engine_factory, released, monkeypatch = adv_rig
    monkeypatch.setattr(animate, "ArtEngine", engine_factory())

    # Pre-create clips folder and clip
    clips = ws / "clips"
    clips.mkdir()
    clip_p01 = clips / "p01.mp4"
    clip_p01.write_bytes(b"EXISTING_CLIP")

    # Align mtime exactly
    pic_mtime = (ws / "panels" / "p01.png").stat().st_mtime
    os.utime(clip_p01, (pic_mtime, pic_mtime))

    res = animate.animate_beats(story, ws, ["p01"], client=client)
    assert res["reused"] == ["p01"]
    assert res["animated"] == []
    assert clip_p01.read_bytes() == b"EXISTING_CLIP"


def test_caching_panel_touched_regenerates(adv_rig):
    """When panel picture mtime is newer than clip mtime, clip must be regenerated."""
    story, ws, client, engine_factory, released, monkeypatch = adv_rig
    monkeypatch.setattr(animate, "ArtEngine", engine_factory())

    clips = ws / "clips"
    clips.mkdir()
    clip_p01 = clips / "p01.mp4"
    clip_p01.write_bytes(b"OLD_CLIP")

    # Set clip to past mtime
    past_mtime = time.time() - 3600
    os.utime(clip_p01, (past_mtime, past_mtime))
    now = time.time()
    os.utime(ws / "panels" / "p01.png", (now, now))

    res = animate.animate_beats(story, ws, ["p01"], client=client)
    assert res["animated"] == ["p01"]
    assert res["reused"] == []
    assert clip_p01.read_bytes() == b"MP4_HEADER_VALID_VIDEO_CONTENT"


def test_caching_zero_byte_clip_behavior(adv_rig):
    """Test behavior when an existing clip file is 0 bytes (corrupted / truncated).
    animate.py must NOT treat 0-byte clips as valid cached clips, but regenerate them."""
    story, ws, client, engine_factory, released, monkeypatch = adv_rig
    monkeypatch.setattr(animate, "ArtEngine", engine_factory())

    clips = ws / "clips"
    clips.mkdir()
    corrupt_clip = clips / "p01.mp4"
    corrupt_clip.write_bytes(b"")  # 0 bytes

    # Set mtime newer than panel picture
    now = time.time() + 10
    os.utime(corrupt_clip, (now, now))

    res = animate.animate_beats(story, ws, ["p01"], client=client)
    print(f"\n[EMPIRICAL] 0-byte clip test: reused={res['reused']}, animated={res['animated']}, size={corrupt_clip.stat().st_size}")
    # 0-byte file must be regenerated, not reused
    assert res["reused"] == []
    assert res["animated"] == ["p01"]
    assert corrupt_clip.stat().st_size > 0
    assert corrupt_clip.read_bytes() == b"MP4_HEADER_VALID_VIDEO_CONTENT"


def test_corrupted_animate_json_error_handling(adv_rig):
    """Test behavior when animate.json on disk contains invalid/corrupted JSON.
    animate.py must safely handle JSONDecodeError/OSError and overwrite with valid metadata."""
    story, ws, client, engine_factory, released, monkeypatch = adv_rig
    monkeypatch.setattr(animate, "ArtEngine", engine_factory())

    clips = ws / "clips"
    clips.mkdir()
    (clips / "animate.json").write_text("{corrupted: invalid_json[[", encoding="utf-8")

    res = animate.animate_beats(story, ws, ["p01"], client=client)
    assert res["animated"] == ["p01"]
    log = json.loads((clips / "animate.json").read_text(encoding="utf-8"))
    assert "p01" in log


# ==============================================================================
# 2. Partial beat failure isolation
# ==============================================================================

def test_odd_beat_failures_isolation_and_animate_json(adv_rig):
    """Simulate ComfyUI raising exceptions on odd-numbered beats (p01, p03).
    Verify even-numbered beats (p02, p04) still write MP4 clips and check animate.json logging."""
    story, ws, client, engine_factory, released, monkeypatch = adv_rig

    # Odd beats fail: up_p01.png and up_p03.png
    fail_on = {"up_p01.png", "up_p03.png"}
    monkeypatch.setattr(animate, "ArtEngine", engine_factory(fail_on=fail_on))

    res = animate.animate_beats(story, ws, ["p01", "p02", "p03", "p04"], client=client)

    # 1. Verification of return dictionary
    assert sorted(res["animated"]) == ["p02", "p04"]
    assert len(res["failed"]) == 2
    failed_beats = {f["beat"]: f["error"] for f in res["failed"]}
    assert "p01" in failed_beats and "simulated failure" in failed_beats["p01"]
    assert "p03" in failed_beats and "simulated failure" in failed_beats["p03"]

    # 2. Verification of disk MP4 artifacts
    clips = ws / "clips"
    assert not (clips / "p01.mp4").exists()
    assert (clips / "p02.mp4").exists() and (clips / "p02.mp4").stat().st_size > 0
    assert not (clips / "p03.mp4").exists()
    assert (clips / "p04.mp4").exists() and (clips / "p04.mp4").stat().st_size > 0

    # 3. Verification of animate.json metadata
    log = json.loads((clips / "animate.json").read_text(encoding="utf-8"))
    print(f"\n[EMPIRICAL] animate.json keys: {list(log.keys())}")
    print(f"[EMPIRICAL] return dict failed: {res['failed']}")
    assert "p02" in log
    assert "p04" in log
    # Crucial empirical observation: failed beats are NOT recorded in animate.json!
    assert "p01" not in log
    assert "p03" not in log


# ==============================================================================
# 3. Cancellation handling
# ==============================================================================

def test_cancellation_before_loop_starts(adv_rig):
    """If is_cancelled() is True before execution, raises immediately without running beats."""
    story, ws, client, engine_factory, released, monkeypatch = adv_rig
    monkeypatch.setattr(animate, "ArtEngine", engine_factory())

    with pytest.raises(RuntimeError, match="cancelled"):
        animate.animate_beats(story, ws, ["p01", "p02"], client=client, is_cancelled=lambda: True)


def test_cancellation_midway_between_beats(adv_rig):
    """If is_cancelled() returns True after beat 1 completes but before beat 2 starts."""
    story, ws, client, engine_factory, released, monkeypatch = adv_rig
    monkeypatch.setattr(animate, "ArtEngine", engine_factory())

    cancel_flag = False

    def check_cancel():
        return cancel_flag

    # Hook progress or client upload to set cancel_flag after p01
    orig_upload = client.upload_image

    def upload_hook(path):
        res = orig_upload(path)
        if "p01" in path.name:
            # cancel right after first upload completes
            nonlocal cancel_flag
            cancel_flag = True
        return res

    client.upload_image = upload_hook

    with pytest.raises(RuntimeError, match="cancelled"):
        animate.animate_beats(story, ws, ["p01", "p02"], client=client, is_cancelled=check_cancel)

    # p01 was completed, p02 was never started
    clips = ws / "clips"
    assert (clips / "p01.mp4").exists()
    assert not (clips / "p02.mp4").exists()


def test_cancellation_during_engine_run_swallowed_or_raised(adv_rig):
    """Test what happens if is_cancelled() returns True during engine.run on the LAST beat.
    Cancellation must NOT be swallowed; it must raise RuntimeError('cancelled').
    """
    story, ws, client, engine_factory, released, monkeypatch = adv_rig

    cancel_triggered = False

    def is_cancelled():
        return cancel_triggered

    # Trigger cancellation when ComfyUI engine is called for p01
    def engine_with_cancel(c, r):
        class CancellingEngine(AdvFakeEngine):
            def run(self, wf, **kw):
                nonlocal cancel_triggered
                cancel_triggered = True
                raise ComfyImageGenerationError("Image generation cancelled; ComfyUI execution may still finish")
        return CancellingEngine()

    monkeypatch.setattr(animate, "ArtEngine", engine_with_cancel)

    # Run for single beat ["p01"] (which is the last beat)
    # Must raise RuntimeError("cancelled")
    try:
        res = animate.animate_beats(story, ws, ["p01"], client=client, is_cancelled=is_cancelled)
        swallowed = True
    except RuntimeError as r:
        swallowed = False
        res = str(r)

    print(f"\n[EMPIRICAL] Cancellation during engine.run on last beat: swallowed={swallowed}, res={res}")
    assert swallowed is False
    assert "cancelled" in res


def test_cancellation_during_engine_run_first_of_multiple_beats(adv_rig):
    """Test what happens if is_cancelled() returns True during engine.run on beat 1 when beat 2 is queued.
    Beat 1 ComfyImageGenerationError is caught by except Exception, but beat 2 hits `if is_cancelled(): raise`."""
    story, ws, client, engine_factory, released, monkeypatch = adv_rig

    cancel_triggered = False

    def is_cancelled():
        return cancel_triggered

    def engine_with_cancel(c, r):
        class CancellingEngine(AdvFakeEngine):
            def run(self, wf, **kw):
                nonlocal cancel_triggered
                cancel_triggered = True
                raise ComfyImageGenerationError("Image generation cancelled; ComfyUI execution may still finish")
        return CancellingEngine()

    monkeypatch.setattr(animate, "ArtEngine", engine_with_cancel)

    with pytest.raises(RuntimeError, match="cancelled"):
        animate.animate_beats(story, ws, ["p01", "p02"], client=client, is_cancelled=is_cancelled)


def test_duplicate_beat_ids_handling(adv_rig):
    """Calling animate_beats with duplicate IDs in beat_ids."""
    story, ws, client, engine_factory, released, monkeypatch = adv_rig
    monkeypatch.setattr(animate, "ArtEngine", engine_factory())

    res = animate.animate_beats(story, ws, ["p01", "p01"], client=client)
    # The first p01 is animated, the second p01 finds the newly written clip and reuses it!
    assert res["animated"] == ["p01"]
    assert res["reused"] == ["p01"]


def test_wan_motion_prompt_extreme_edge_cases():
    """Test wan_motion_prompt with None/empty character fields, weird Unicode, and special characters."""
    bible = Bible(
        premise=Premise(title="T", genre="g", logline="l", tone="t", setting="s"),
        characters=[
            Character(id="c1", name="ZeroLookChar", role="extra", age_group="adult", look="", personality="p"),
            Character(id="c2", name="UnicodeChar_日本語_🐱", role="extra", age_group="adult", look="spiky hair, <special_tags>", personality="p"),
        ],
        locations=[Location(id="loc1", name="Loc", look="l")]
    )
    # Panel with None director, empty action, empty caption
    panel_empty = Panel(id="p01", scene_id="sc1", shot="close", angle="eye_level", location_id="loc1", character_ids=["c1"], action="", caption="")
    story = OriginalStory(bible=bible, scenes=[Scene(id="sc1", location_id="loc1", character_ids=["c1"], summary="s", mood="m")], panels=[panel_empty])
    prompt = animate.wan_motion_prompt(story, panel_empty)
    assert "The camera is static" in prompt
    assert "Natural cloth and hair physics" in prompt
    assert "<Picture 1>" not in prompt

    # Panel with special unicode characters and tags in director
    spec = ShotSpec(
        shot="close", camera="dolly in", setting="void", lighting="dim", mood="eerie",
        characters=[CharPose(id="c2", side="center", pose="standing", expression='smiling "mischievously"', action="waving <hand>")]
    )
    panel_special = Panel(id="p02", scene_id="sc1", shot="close", angle="eye_level", location_id="loc1", character_ids=["c2"], action="", caption="He speaks.", director=spec.model_dump())
    prompt_special = animate.wan_motion_prompt(story, panel_special)
    assert "UnicodeChar_日本語_🐱" in prompt_special
    assert 'expression smiling "mischievously"' in prompt_special
    assert "<hand>" in prompt_special
    assert "<Picture 1>" not in prompt_special


# ==============================================================================
# 4. Workspace & directory creation
# ==============================================================================

def test_missing_clips_directory_auto_created(adv_rig):
    """Verify that when ws / 'clips' directory does not exist initially, it is created automatically."""
    story, ws, client, engine_factory, released, monkeypatch = adv_rig
    monkeypatch.setattr(animate, "ArtEngine", engine_factory())

    clips = ws / "clips"
    assert not clips.exists()

    res = animate.animate_beats(story, ws, ["p01"], client=client)
    assert clips.exists() and clips.is_dir()
    assert (clips / "p01.mp4").exists()
    assert (clips / "animate.json").exists()


def test_nested_nonexistent_workspace_parent(tmp_path, monkeypatch):
    """Test behavior if ws parent structure does not exist yet when animate_beats is called."""
    story = make_story(n_scenes=1, per_scene=1)
    deep_ws = tmp_path / "deep" / "nested" / "ws"
    # Create panels in deep_ws
    (deep_ws / "panels").mkdir(parents=True)
    (deep_ws / "panels" / "p01.png").write_bytes(b"PNG")

    client = AdvFakeClient()
    class Registry:
        def __init__(self, c): pass
        def preflight(self, wid): return {"ready": True, "missing_nodes": [], "missing_models": []}
        def load(self, wid): return GRAPH_WAN, "wan_sha"
        def metadata(self, wid): return ENTRY_WAN

    monkeypatch.setattr(animate, "ComfyWorkflowRegistry", Registry)
    monkeypatch.setattr(animate, "ArtEngine", lambda c, r: AdvFakeEngine())
    monkeypatch.setattr(animate, "release_ollama", lambda: None)

    # clips folder does not exist, but deep_ws exists because panels was created
    res = animate.animate_beats(story, deep_ws, ["p01"], client=client)
    assert (deep_ws / "clips" / "p01.mp4").exists()
