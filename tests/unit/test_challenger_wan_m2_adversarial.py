"""Empirical Adversarial Stress-Testing Suite for Milestone M2.

Authored by challenger_wan_m2_1.
Empirically stress-tests:
1. Empty, missing, and malformed panel inputs (missing director, empty action, empty caption, empty camera).
2. Complex kinematic camera moves, multi-character poses, and strict proscription of MiniMax XML tags.
3. Custom resolution overrides, negative prompt overrides (including empty string), and seed determinism.
4. Beat picking boundary conditions (0 beats, all static beats, single panel, max_clips extremes).
5. Error isolation, cancellation, mtime caching, and pipeline resilience.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from engine.comfyui import art as comfy_art
from engine.comfyui.registry import ComfyWorkflowRegistry
from engine.original import animate
from engine.original.models import (
    Bible,
    Character,
    Location,
    OriginalStory,
    Panel,
    Premise,
    Scene,
)
from engine.original.prompt import UNIVERSAL_VIDEO_NEGATIVE_PROMPT
from engine.original.shotspec import CharPose, ShotSpec

COMFY_DIR = Path(comfy_art.__file__).parent
ENTRY_WAN = next(
    e
    for e in json.loads((COMFY_DIR / "workflow_registry.json").read_text(encoding="utf-8"))
    if e["id"] == animate.WAN21_I2V_ID
)
GRAPH_WAN = json.loads((COMFY_DIR / "workflows" / ENTRY_WAN["filename"]).read_text(encoding="utf-8"))

ENTRY_H3 = next(
    e
    for e in json.loads((COMFY_DIR / "workflow_registry.json").read_text(encoding="utf-8"))
    if e["id"] == animate.FAST_H3_ID
)
GRAPH_H3 = json.loads((COMFY_DIR / "workflows" / ENTRY_H3["filename"]).read_text(encoding="utf-8"))


def make_test_story(
    n_scenes: int = 2,
    per_scene: int = 2,
    custom_panels: list[Panel] | None = None,
    premise_title: str = "Adversarial Stress Test",
) -> OriginalStory:
    """Construct deterministic story for adversarial testing."""
    bible = Bible(
        premise=Premise(title=premise_title, genre="action", logline="l", tone="dark", setting="city"),
        characters=[
            Character(
                id="hero",
                name="Kael",
                role="protagonist",
                age_group="adult",
                look="black spiky hair, cybernetic red eye, combat vest, cargo pants",
                personality="stoic",
            ),
            Character(
                id="ally",
                name="Lyra",
                role="companion",
                age_group="adult",
                look="silver twin-tails, blue optics goggles, trench coat",
                personality="witty",
            ),
            Character(
                id="drone",
                name="Unit-7",
                role="companion",
                age_group="adult",
                look="metallic orb drone, glowing blue sensor aperture",
                personality="analytical",
                species="machine",
            ),
            Character(
                id="ghost",
                name="Phantom",
                role="extra",
                age_group="adult",
                look="",
                personality="mysterious",
            ),
        ],
        locations=[Location(id="rooftop", name="Neo Rooftop", look="neon rain slicked concrete")],
    )

    if custom_panels is not None:
        scenes = [Scene(id=f"sc{s}", location_id="rooftop", character_ids=["hero"], summary="s", mood="m")
                  for s in range(1, n_scenes + 1)]
        return OriginalStory(bible=bible, scenes=scenes, panels=custom_panels)

    panels, k = [], 0
    for s in range(1, n_scenes + 1):
        for _ in range(per_scene):
            k += 1
            spec = ShotSpec(
                shot="medium",
                camera="eye_level",
                setting="neon rooftop in heavy rain",
                lighting="flickering blue neon",
                mood="tense and cinematic",
                characters=[
                    CharPose(id="hero", pose="kneeling", expression="grim", action="aiming rifle"),
                    CharPose(id="ally", pose="standing", expression="alert", action="monitoring scanner"),
                ],
            )
            panels.append(
                Panel(
                    id=f"p{k:02d}",
                    scene_id=f"sc{s}",
                    shot="medium",
                    angle="eye_level",
                    location_id="rooftop",
                    character_ids=["hero", "ally"],
                    action="two operatives take positions",
                    caption=f"Operatives prepare for breach {k}.",
                    director=spec.model_dump(),
                )
            )
    scenes = [Scene(id=f"sc{s}", location_id="rooftop", character_ids=["hero"], summary="s", mood="m")
              for s in range(1, n_scenes + 1)]
    return OriginalStory(bible=bible, scenes=scenes, panels=panels)


class FakeClient:
    def __init__(self):
        self.uploads: list[str] = []

    def upload_image(self, path: Path) -> str:
        self.uploads.append(path.name)
        return f"uploaded_{path.name}"


class FakeEngine:
    def __init__(self, client, registry, fail_on=()):
        self.fail_on = fail_on
        self.graphs: list[dict] = []

    def run(self, wf, **kw):
        self.graphs.append(copy.deepcopy(wf))
        img = wf.get("6", {}).get("inputs", {}).get("image") or wf.get("136", {}).get("inputs", {}).get("image")
        if img in self.fail_on:
            raise RuntimeError(f"Simulated ComfyUI failure on {img}")
        assert kw.get("collect") is not None
        return b"SIMULATED_WAN_MP4_BYTES", f"prompt_{len(self.graphs)}", {"filename": "clip.mp4"}


@pytest.fixture
def fake_rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    story = make_test_story(n_scenes=2, per_scene=2)
    ws = tmp_path / "workspace"
    (ws / "panels").mkdir(parents=True)
    for p in story.panels:
        (ws / "panels" / f"{p.id}.png").write_bytes(b"PNG_DATA")

    client = FakeClient()
    engines: list[FakeEngine] = []
    released: list[int] = []
    fail_set: set[str] = set()

    class MockRegistry:
        def __init__(self, c):
            pass

        def preflight(self, wid):
            return {"ready": True, "missing_nodes": [], "missing_models": []}

        def load(self, wid):
            if wid == animate.WAN21_I2V_ID:
                return GRAPH_WAN, "wan_sha256_mock"
            return GRAPH_H3, "h3_sha256_mock"

        def metadata(self, wid):
            if wid == animate.WAN21_I2V_ID:
                return ENTRY_WAN
            return ENTRY_H3

    def mock_art_engine(c, r):
        eng = FakeEngine(c, r, fail_on=tuple(fail_set))
        engines.append(eng)
        return eng

    monkeypatch.setattr(animate, "ComfyWorkflowRegistry", MockRegistry)
    monkeypatch.setattr(animate, "ArtEngine", mock_art_engine)
    monkeypatch.setattr(animate, "release_ollama", lambda: released.append(1))

    return story, ws, client, engines, released, fail_set


# ==============================================================================
# GROUP 1: EMPTY / MISSING DIRECTOR & PANEL INPUT CORNER CASES
# ==============================================================================


def test_wan_motion_prompt_completely_empty_panel():
    """Adversarial Test: Panel with all empty string / dict fields."""
    story = make_test_story()
    empty_panel = Panel(
        id="empty_p",
        scene_id="sc1",
        shot="close",
        angle="eye_level",
        location_id="rooftop",
        character_ids=[],
        action="",
        caption="",
        director={},
        camera="",
        motion="",
    )
    prompt = animate.wan_motion_prompt(story, empty_panel)

    # Must produce valid English sentence
    assert prompt.startswith("The camera is static, fixed on a tripod")
    assert "Natural cloth and hair physics" in prompt
    assert prompt.endswith(".")
    assert not prompt.endswith("..")
    # Must NOT contain empty parentheses, double spaces, or XML tags
    assert "()" not in prompt
    assert "<" not in prompt
    assert ">" not in prompt


def test_wan_motion_prompt_missing_director_with_fallback_action():
    """Adversarial Test: Panel without director dict, relying on raw action."""
    story = make_test_story()
    panel = Panel(
        id="p_no_dir",
        scene_id="sc1",
        shot="wide",
        angle="eye_level",
        location_id="rooftop",
        character_ids=["hero"],
        action="Kael stands silently under pouring rain",
        caption="",
        director={},
        camera="",
        motion="",
    )
    prompt = animate.wan_motion_prompt(story, panel)

    assert "The camera is static" in prompt
    assert "Kael stands silently under pouring rain" in prompt
    assert "Natural cloth and hair physics" in prompt
    assert "Action of the moment:" not in prompt  # caption was empty


def test_wan_motion_prompt_empty_action_and_caption_with_director():
    """Adversarial Test: Panel with director data but zero action/caption/motion."""
    story = make_test_story()
    spec = ShotSpec(
        shot="close",
        setting="a dimly lit corridor",
        lighting="flickering fluorescent",
        mood="oppressive",
        characters=[CharPose(id="hero", pose="standing", expression="focused", action="")],
    )
    panel = Panel(
        id="p_dir_only",
        scene_id="sc1",
        shot="close",
        angle="eye_level",
        location_id="rooftop",
        character_ids=["hero"],
        action="",
        caption="",
        director=spec.model_dump(),
        camera="",
        motion="",
    )
    prompt = animate.wan_motion_prompt(story, panel)

    assert "Kael (black spiky hair, cybernetic red eye, combat vest) standing, expression focused" in prompt
    assert "in a dimly lit corridor" in prompt
    assert "flickering fluorescent lighting, oppressive atmosphere" in prompt
    assert "Action of the moment:" not in prompt
    assert prompt.endswith(".")


def test_wan_motion_prompt_motion_takes_precedence_over_caption():
    """Adversarial Test: When motion is provided, it must take precedence over caption."""
    story = make_test_story()
    panel = Panel(
        id="p_motion_prec",
        scene_id="sc1",
        shot="medium",
        angle="eye_level",
        location_id="rooftop",
        character_ids=["hero"],
        action="action text",
        caption="This is the narration caption.",
        motion="The drone accelerates rapidly into the sky.",
        director={},
        camera="camera zooms out",
    )
    prompt = animate.wan_motion_prompt(story, panel)

    assert "The drone accelerates rapidly into the sky" in prompt
    assert "This is the narration caption" not in prompt
    assert "Action of the moment:" not in prompt


def test_wan_motion_prompt_caption_when_motion_is_empty():
    """Adversarial Test: When motion is empty, caption must be formatted with Action of the moment."""
    story = make_test_story()
    panel = Panel(
        id="p_caption_fall",
        scene_id="sc1",
        shot="medium",
        angle="eye_level",
        location_id="rooftop",
        character_ids=["hero"],
        action="action text",
        caption="A distant siren wails through the fog.",
        motion="",
        director={},
        camera="",
    )
    prompt = animate.wan_motion_prompt(story, panel)

    assert "Action of the moment: A distant siren wails through the fog" in prompt


def test_wan_motion_prompt_character_look_token_limits():
    """Adversarial Test: Character look with >3 comma-separated tokens must be truncated to 3."""
    story = make_test_story()
    story.bible.characters[0].look = "trait1, trait2, trait3, trait4, trait5, trait6"

    spec = ShotSpec(
        shot="medium",
        characters=[CharPose(id="hero", pose="standing", expression="calm", action="waiting")],
    )
    panel = Panel(
        id="p_traits",
        scene_id="sc1",
        shot="medium",
        angle="eye_level",
        location_id="rooftop",
        character_ids=["hero"],
        action="",
        caption="test",
        director=spec.model_dump(),
    )
    prompt = animate.wan_motion_prompt(story, panel)

    assert "Kael (trait1, trait2, trait3)" in prompt
    assert "trait4" not in prompt
    assert "trait5" not in prompt


def test_wan_motion_prompt_character_not_in_bible():
    """Adversarial Test: Character in director spec missing from bible must fall back to character ID."""
    story = make_test_story()
    spec = ShotSpec(
        shot="medium",
        characters=[CharPose(id="unregistered_bystander", pose="crouching", expression="terrified", action="fleeing")],
    )
    panel = Panel(
        id="p_unknown_char",
        scene_id="sc1",
        shot="medium",
        angle="eye_level",
        location_id="rooftop",
        character_ids=[],
        action="",
        caption="Panic ensues.",
        director=spec.model_dump(),
    )
    prompt = animate.wan_motion_prompt(story, panel)

    assert "unregistered_bystander crouching, expression terrified, fleeing" in prompt


def test_wan_motion_prompt_character_with_empty_or_whitespace_look():
    """Adversarial Test: Character with empty look must not output empty parentheses '()'."""
    story = make_test_story()
    # Ghost has look=""
    spec = ShotSpec(
        shot="close",
        characters=[CharPose(id="ghost", pose="drifting", expression="hollow", action="gliding past")],
    )
    panel = Panel(
        id="p_ghost",
        scene_id="sc1",
        shot="close",
        angle="eye_level",
        location_id="rooftop",
        character_ids=["ghost"],
        action="",
        caption="A specter appears.",
        director=spec.model_dump(),
    )
    prompt = animate.wan_motion_prompt(story, panel)

    assert "Phantom drifting, expression hollow, gliding past" in prompt
    assert "()" not in prompt
    assert "Phantom ()" not in prompt


@pytest.mark.parametrize(
    "pose,expression,action,expected_substr",
    [
        ("standing", "", "", "Kael (black spiky hair, cybernetic red eye, combat vest) standing"),
        ("", "furious", "", "Kael (black spiky hair, cybernetic red eye, combat vest) expression furious"),
        ("", "", "drawing katana", "Kael (black spiky hair, cybernetic red eye, combat vest) drawing katana"),
        ("", "", "", "Kael (black spiky hair, cybernetic red eye, combat vest)"),
    ],
)
def test_wan_motion_prompt_pose_expression_action_subsets(pose: str, expression: str, action: str, expected_substr: str):
    """Adversarial Test: Sparse CharPose fields must not produce invalid commas or artifacts."""
    story = make_test_story()
    spec = ShotSpec(
        shot="medium",
        characters=[CharPose(id="hero", pose=pose, expression=expression, action=action)],
    )
    panel = Panel(
        id="p_sparse",
        scene_id="sc1",
        shot="medium",
        angle="eye_level",
        location_id="rooftop",
        character_ids=["hero"],
        action="",
        caption="test",
        director=spec.model_dump(),
    )
    prompt = animate.wan_motion_prompt(story, panel)

    assert expected_substr in prompt
    assert ", ," not in prompt
    assert "  " not in prompt


# ==============================================================================
# GROUP 2: COMPLEX SHOT KINEMATICS & PROMPT INVARIANTS
# ==============================================================================


@pytest.mark.parametrize(
    "camera_input,expected_cam_desc",
    [
        ("push_in", "The camera does push_in"),
        ("slow push-in", "The camera does slow push-in"),
        ("tilt_up", "The camera does tilt_up"),
        ("orbit", "The camera does orbit"),
        ("pan_left", "The camera does pan_left"),
        ("The camera tracks forward smoothly", "The camera tracks forward smoothly"),
        ("the camera pans right slowly", "the camera pans right slowly"),
        ("Camera cranes upward 45 degrees", "Camera cranes upward 45 degrees"),
        ("CAMERA ZOOMS IN RAPIDLY", "CAMERA ZOOMS IN RAPIDLY"),
        ("slow push-in.", "The camera does slow push-in"),
        ("  rapid whip pan to the skyline...  ", "The camera does rapid whip pan to the skyline"),
    ],
)
def test_wan_motion_prompt_camera_moves_kinematics(camera_input: str, expected_cam_desc: str):
    """Adversarial Test: Kinematic camera moves with diverse casing, prefixes, and punctuation."""
    story = make_test_story()
    panel = Panel(
        id="p_cam",
        scene_id="sc1",
        shot="medium",
        angle="eye_level",
        location_id="rooftop",
        character_ids=["hero"],
        action="action",
        caption="caption",
        director={},
        camera=camera_input,
    )
    prompt = animate.wan_motion_prompt(story, panel)

    assert prompt.startswith(f"{expected_cam_desc}. ")


def test_wan_motion_prompt_multi_character_poses():
    """Adversarial Test: Multi-character shot with diverse poses and interactions."""
    story = make_test_story()
    spec = ShotSpec(
        shot="wide",
        characters=[
            CharPose(id="hero", pose="crouched on the ledge", expression="calculating", action="surveying streets"),
            CharPose(id="ally", pose="standing back-to-back", expression="focused", action="typing on terminal"),
            CharPose(id="drone", pose="hovering overhead", expression="", action="emitting infrared scan"),
        ],
        setting="sprawling neon metropolis under stormy skies",
        lighting="high contrast neon and lightning flashes",
        mood="electrifying",
    )
    panel = Panel(
        id="p_multi",
        scene_id="sc1",
        shot="wide",
        angle="eye_level",
        location_id="rooftop",
        character_ids=["hero", "ally", "drone"],
        action="",
        caption="The infiltration team holds the perimeter.",
        director=spec.model_dump(),
        camera="The camera slowly orbits clockwise around the trio",
    )
    prompt = animate.wan_motion_prompt(story, panel)

    assert "The camera slowly orbits clockwise around the trio" in prompt
    assert "Kael (black spiky hair, cybernetic red eye, combat vest) crouched on the ledge, expression calculating, surveying streets" in prompt
    assert "Lyra (silver twin-tails, blue optics goggles, trench coat) standing back-to-back, expression focused, typing on terminal" in prompt
    assert "Unit-7 (metallic orb drone, glowing blue sensor aperture) hovering overhead, emitting infrared scan" in prompt
    assert "in sprawling neon metropolis under stormy skies" in prompt
    assert "high contrast neon and lightning flashes lighting, electrifying atmosphere" in prompt
    assert "Action of the moment: The infiltration team holds the perimeter" in prompt
    assert "Natural cloth and hair physics" in prompt


@pytest.mark.parametrize(
    "setting,lighting,mood,expected_clauses",
    [
        ("a subway tunnel", "amber emergency", "suffocating", ["in a subway tunnel", "amber emergency lighting, suffocating atmosphere"]),
        ("a subway tunnel", "", "", ["in a subway tunnel"]),
        ("", "dim candle", "", ["dim candle lighting"]),
        ("", "", "eerie", ["eerie atmosphere"]),
        ("", "", "", []),
    ],
)
def test_wan_motion_prompt_setting_and_atmosphere_permutations(
    setting: str, lighting: str, mood: str, expected_clauses: list[str]
):
    """Adversarial Test: Permutations of setting, lighting, and mood clauses."""
    story = make_test_story()
    spec = ShotSpec(shot="close", setting=setting, lighting=lighting, mood=mood, characters=[])
    panel = Panel(
        id="p_atmo",
        scene_id="sc1",
        shot="close",
        angle="eye_level",
        location_id="rooftop",
        character_ids=[],
        action="",
        caption="test",
        director=spec.model_dump(),
    )
    prompt = animate.wan_motion_prompt(story, panel)

    for clause in expected_clauses:
        assert clause in prompt
    assert prompt.endswith(".")


def test_wan_motion_prompt_strict_proscription_of_minimax_xml():
    """Adversarial Test: Verify zero MiniMax XML or multimodal headers appear in Wan2.1 prompts."""
    forbidden_tokens = [
        "<Picture 1>",
        "<Picture",
        "</Picture>",
        "integrated_multimodal_description:",
        "overall_soundscape:",
        "non_diegetic_music:",
        "[Shot 1]",
        "[Shot",
        "For the target video",
        "into the target video",
    ]

    story = make_test_story(n_scenes=3, per_scene=3)
    for p in story.panels:
        prompt_wan = animate.wan_motion_prompt(story, p)
        prompt_dispatched = animate.motion_prompt(story, p, workflow_id=animate.WAN21_I2V_ID)

        assert prompt_wan == prompt_dispatched
        for tok in forbidden_tokens:
            assert tok not in prompt_wan, f"Forbidden MiniMax token '{tok}' leaked into Wan2.1 prompt!"

    # Verify FAST_H3_ID still produces MiniMax XML tags
    prompt_h3 = animate.motion_prompt(story, story.panels[0], workflow_id=animate.FAST_H3_ID)
    assert "<Picture 1>" in prompt_h3
    assert "integrated_multimodal_description:" in prompt_h3
    assert "overall_soundscape:" in prompt_h3


# ==============================================================================
# GROUP 3: CUSTOM PARAMETERS & WORKFLOW GRAPH PATCHING
# ==============================================================================


@pytest.mark.parametrize(
    "custom_width,custom_height",
    [
        (832, 480),   # Native Wan2.1 480p landscape
        (480, 832),   # Native Wan2.1 480p portrait
        (1280, 720),  # 720p 16:9
        (720, 1280),  # 720p 9:16
        (1024, 1024), # 1:1 square
        (256, 256),   # Minimum valid boundary
        (2048, 2048), # Maximum valid boundary
    ],
)
def test_wan21_custom_resolutions_patching(fake_rig, custom_width: int, custom_height: int):
    """Adversarial Test: Custom resolution parameter overrides wired to WanImageToVideo node 10."""
    story, ws, client, engines, released, _ = fake_rig

    out = animate.animate_beats(
        story,
        ws,
        ["p01"],
        width=custom_width,
        height=custom_height,
        client=client,
    )
    assert out["animated"] == ["p01"]
    assert len(engines[0].graphs) == 1
    patched_graph = engines[0].graphs[0]

    assert patched_graph["10"]["inputs"]["width"] == custom_width
    assert patched_graph["10"]["inputs"]["height"] == custom_height


@pytest.mark.parametrize(
    "neg_input,expected_neg",
    [
        (None, UNIVERSAL_VIDEO_NEGATIVE_PROMPT),
        ("ugly, blurry, distorted, morphing, low quality", "ugly, blurry, distorted, morphing, low quality"),
        ("", ""),  # Explicit empty negative prompt must be preserved
        ("   spaced tokens   ", "   spaced tokens   "),
    ],
)
def test_wan21_negative_prompt_overrides(fake_rig, neg_input: str | None, expected_neg: str):
    """Adversarial Test: Negative prompt override handling (default vs custom vs empty)."""
    story, ws, client, engines, released, _ = fake_rig

    out = animate.animate_beats(
        story,
        ws,
        ["p01"],
        negative_prompt=neg_input,
        client=client,
    )
    assert out["animated"] == ["p01"]
    patched_graph = engines[0].graphs[0]

    assert patched_graph["9"]["inputs"]["text"] == expected_neg


def test_wan21_seed_determinism_and_entropy(fake_rig):
    """Adversarial Test: Seed generation determinism across runs and divergence across beats."""
    story, ws, client, engines, released, _ = fake_rig

    out1 = animate.animate_beats(story, ws, ["p01", "p02"], client=client)
    log1 = json.loads((ws / "clips" / "animate.json").read_text())

    seed_p01 = log1["p01"]["seed"]
    seed_p02 = log1["p02"]["seed"]

    # 1. Seeds must be non-zero and distinct across beats
    assert seed_p01 != 0
    assert seed_p02 != 0
    assert seed_p01 != seed_p02

    # 2. Seed must fit within unsigned 48-bit range (KSampler compatible)
    assert 0 <= seed_p01 < (2**48)
    assert 0 <= seed_p02 < (2**48)

    # 3. Determinism check: recalculating seed yields exact same value
    expected_seed_p01 = int(hashlib.sha256(f"{story.bible.premise.title}|p01".encode()).hexdigest()[:12], 16)
    assert seed_p01 == expected_seed_p01

    # 4. Different story title produces completely distinct seed
    story_diff_title = make_test_story(premise_title="Completely Different Premise")
    other_seed = int(hashlib.sha256(f"{story_diff_title.bible.premise.title}|p01".encode()).hexdigest()[:12], 16)
    assert seed_p01 != other_seed


def test_wan21_graph_patching_node_isolation_and_immutability():
    """Adversarial Test: Verify patched graph touches only declared slots and leaves others intact."""
    base_graph_before = copy.deepcopy(GRAPH_WAN)
    slots = ENTRY_WAN["patch_slots"]

    patched = comfy_art._patch_workflow(
        GRAPH_WAN,
        slots,
        prompt="Adversarial positive motion text",
        negative_prompt="Adversarial negative text",
        width=1280,
        height=720,
        seed=123456789,
        prefix="video/adversarial_prefix",
        reference_image="uploaded_panel_image.png",
        duration=5.0,  # Note: duration is not in Wan2.1 patch slots
    )

    # 1. Original graph is unchanged
    assert GRAPH_WAN == base_graph_before

    # 2. Patched nodes match
    assert patched["6"]["inputs"]["image"] == "uploaded_panel_image.png"
    assert patched["8"]["inputs"]["text"] == "Adversarial positive motion text"
    assert patched["9"]["inputs"]["text"] == "Adversarial negative text"
    assert patched["10"]["inputs"]["width"] == 1280
    assert patched["10"]["inputs"]["height"] == 720
    assert patched["11"]["inputs"]["seed"] == 123456789
    assert patched["14"]["inputs"]["filename_prefix"] == "video/adversarial_prefix"

    # 3. Unpatched nodes (e.g., node 1 UNETLoader, node 4 VAELoader, node 12 VAEDecode) are identical
    for unpatched_id in ["1", "2", "3", "4", "5", "7", "12", "13"]:
        assert patched[unpatched_id] == base_graph_before[unpatched_id]


# ==============================================================================
# GROUP 4: BEAT PICKING BOUNDARY CONDITIONS
# ==============================================================================


def test_pick_beats_zero_panels():
    """Adversarial Test: pick_beats on story with 0 panels returns empty list without error."""
    story = OriginalStory(
        bible=Bible(premise=Premise(title="Empty", genre="vox", logline="l", tone="t", setting="s"), characters=[], locations=[]),
        scenes=[],
        panels=[],
    )
    assert animate.pick_beats(story) == []
    assert animate.pick_beats(story, max_clips=0) == []
    assert animate.pick_beats(story, max_clips=5) == []


def test_pick_beats_all_static_beats():
    """Adversarial Test: All panels have 0 action and empty director."""
    panels = [
        Panel(id=f"p{i:02d}", scene_id=f"sc{i % 2 + 1}", shot="close", angle="eye_level", location_id="r", character_ids=[], action="", caption="", director={})
        for i in range(6)
    ]
    story = make_test_story(n_scenes=2, custom_panels=panels)

    picks = animate.pick_beats(story, max_clips=3)
    assert len(picks) == 3
    assert picks == sorted(picks)  # Returned in story order


def test_pick_beats_single_panel_story():
    """Adversarial Test: Story with exactly 1 panel."""
    single_panel = Panel(
        id="only_one",
        scene_id="sc1",
        shot="close",
        angle="eye_level",
        location_id="r",
        character_ids=[],
        action="cat sleeps",
        caption="A sleepy cat.",
        director={},
    )
    story = make_test_story(n_scenes=1, custom_panels=[single_panel])

    assert animate.pick_beats(story) == ["only_one"]
    assert animate.pick_beats(story, max_clips=1) == ["only_one"]
    assert animate.pick_beats(story, max_clips=10) == ["only_one"]


@pytest.mark.parametrize(
    "max_clips,expected_count",
    [
        (0, 1),   # max_clips 0 clamped to max(1, 0) -> 1
        (1, 1),
        (2, 2),
        (4, 4),
        (100, 4), # Exceeds panel count (4) -> capped at panel count
        (None, 1),# 4 / 4.5 = 0.88 -> round = 1
    ],
)
def test_pick_beats_max_clips_extremes(max_clips: int | None, expected_count: int):
    """Adversarial Test: max_clips parameter boundaries and clamping."""
    story = make_test_story(n_scenes=2, per_scene=2)  # 4 panels total
    picks = animate.pick_beats(story, max_clips=max_clips)
    assert len(picks) == expected_count


def test_pick_beats_action_score_prioritization():
    """Adversarial Test: Verify _action_score prioritizes characters with actions and key visuals."""
    spec_high = ShotSpec(
        shot="close",
        characters=[CharPose(id="hero", action="fires rocket launcher across the valley")],
        key_visuals=["massive explosion", "smoke plume"],
    )
    spec_low = ShotSpec(
        shot="close",
        characters=[CharPose(id="hero", action="blinks")],
    )

    p_high = Panel(id="p_high", scene_id="sc1", shot="close", angle="eye_level", location_id="r", character_ids=[], action="", caption="", director=spec_high.model_dump())
    p_low = Panel(id="p_low", scene_id="sc1", shot="close", angle="eye_level", location_id="r", character_ids=[], action="", caption="", director=spec_low.model_dump())

    assert animate._action_score(p_high) > animate._action_score(p_low)

    story = make_test_story(n_scenes=1, custom_panels=[p_low, p_high])
    picks = animate.pick_beats(story, max_clips=1)
    assert picks == ["p_high"]


# ==============================================================================
# GROUP 5: PIPELINE RESILIENCE, ERROR ISOLATION, & RUNTIME LIFECYCLE
# ==============================================================================


def test_animate_beats_zero_panels_lifecycle(fake_rig):
    """Adversarial Test: Running animate_beats on an empty story succeeds without GPU calls."""
    _, ws, client, engines, released, _ = fake_rig
    empty_story = OriginalStory(
        bible=Bible(premise=Premise(title="T", genre="vox", logline="l", tone="t", setting="s"), characters=[], locations=[]),
        scenes=[],
        panels=[],
    )

    out = animate.animate_beats(empty_story, ws, client=client)
    assert out["animated"] == []
    assert out["reused"] == []
    assert out["failed"] == []
    assert out["workflow"] == animate.WAN21_I2V_ID
    assert out["seconds_each"] == []
    assert len(engines[0].graphs) == 0  # No engine runs submitted


def test_animate_beats_unknown_beat_rejected_before_gpu(fake_rig):
    """Adversarial Test: Unknown beat id raises ValueError before Ollama release or engine call."""
    story, ws, client, engines, released, _ = fake_rig

    with pytest.raises(ValueError, match="unknown beats: \\['non_existent_beat'\\]"):
        animate.animate_beats(story, ws, ["non_existent_beat"], client=client)

    assert released == []
    assert len(engines) == 0


def test_animate_beats_missing_panel_image_rejected_before_gpu(fake_rig):
    """Adversarial Test: Missing panel PNG file on disk raises ValueError before GPU call."""
    story, ws, client, engines, released, _ = fake_rig
    # Delete panel p01.png
    (ws / "panels" / "p01.png").unlink()

    with pytest.raises(ValueError, match="no picture yet for: \\['p01'\\]"):
        animate.animate_beats(story, ws, ["p01"], client=client)

    assert released == []
    assert len(engines) == 0


def test_animate_beats_multi_beat_failure_isolation(fake_rig):
    """Adversarial Test: Second beat fails in ComfyUI; first and third succeed."""
    story, ws, client, engines, released, fail_set = fake_rig
    fail_set.add("uploaded_p02.png")

    out = animate.animate_beats(story, ws, ["p01", "p02", "p03"], client=client)

    # p01 and p03 must succeed
    assert out["animated"] == ["p01", "p03"]
    assert (ws / "clips" / "p01.mp4").is_file()
    assert (ws / "clips" / "p03.mp4").is_file()

    # p02 must be in failed list with error message and no file on disk
    assert len(out["failed"]) == 1
    assert out["failed"][0]["beat"] == "p02"
    assert "Simulated ComfyUI failure" in out["failed"][0]["error"]
    assert not (ws / "clips" / "p02.mp4").exists()

    # animate.json metadata must record only successful beats
    log = json.loads((ws / "clips" / "animate.json").read_text())
    assert "p01" in log
    assert "p03" in log
    assert "p02" not in log


def test_animate_beats_cancellation_during_pipeline(fake_rig):
    """Adversarial Test: Cancellation callback triggered before or during pipeline."""
    story, ws, client, engines, released, _ = fake_rig

    # Cancel immediately
    with pytest.raises(RuntimeError, match="cancelled"):
        animate.animate_beats(story, ws, ["p01", "p02"], client=client, is_cancelled=lambda: True)

    assert not (ws / "clips" / "p01.mp4").exists()

    # Cancel after first beat
    call_count = 0

    def cancel_after_first():
        nonlocal call_count
        call_count += 1
        return call_count > 1

    with pytest.raises(RuntimeError, match="cancelled"):
        animate.animate_beats(story, ws, ["p01", "p02"], client=client, is_cancelled=cancel_after_first)

    # First beat was completed before second beat cancelled
    assert (ws / "clips" / "p01.mp4").is_file()
    assert not (ws / "clips" / "p02.mp4").exists()


def test_animate_beats_free_llm_memory_flag(fake_rig):
    """Adversarial Test: free_llm_memory=False bypasses release_ollama call."""
    story, ws, client, engines, released, _ = fake_rig

    animate.animate_beats(story, ws, ["p01"], client=client, free_llm_memory=False)
    assert released == []

    animate.animate_beats(story, ws, ["p02"], client=client, free_llm_memory=True)
    assert released == [1]


def test_animate_beats_mtime_caching_and_staleness(fake_rig):
    """Adversarial Test: Mtime timestamp comparison edge cases."""
    story, ws, client, engines, released, _ = fake_rig

    # 1. Initial generation
    out1 = animate.animate_beats(story, ws, ["p01"], client=client)
    assert out1["animated"] == ["p01"]
    assert out1["reused"] == []

    # 2. Re-run without touching panel -> reused
    out2 = animate.animate_beats(story, ws, ["p01"], client=client)
    assert out2["animated"] == []
    assert out2["reused"] == ["p01"]

    # 3. Touch panel image to be newer than clip -> clip must be regenerated
    panel_file = ws / "panels" / "p01.png"
    newer_time = time.time() + 100
    os.utime(panel_file, (newer_time, newer_time))

    out3 = animate.animate_beats(story, ws, ["p01"], client=client)
    assert out3["animated"] == ["p01"]
    assert out3["reused"] == []


def test_animate_beats_appends_to_existing_animate_json(fake_rig):
    """Adversarial Test: animate.json preserves pre-existing entries across separate batches."""
    story, ws, client, engines, released, _ = fake_rig

    # Batch 1: p01
    animate.animate_beats(story, ws, ["p01"], client=client)
    log1 = json.loads((ws / "clips" / "animate.json").read_text())
    assert set(log1.keys()) == {"p01"}

    # Batch 2: p02
    animate.animate_beats(story, ws, ["p02"], client=client)
    log2 = json.loads((ws / "clips" / "animate.json").read_text())
    assert set(log2.keys()) == {"p01", "p02"}
    assert log2["p01"] == log1["p01"]
