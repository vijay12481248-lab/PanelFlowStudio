"""Empirical Adversarial Test Suite for Sprint 3: WP-3.1 & WP-3.2.

Covers:
1. Dynamic LoadImage DAG injection: node ID collision handling, sequential allocations, corrupt/missing paths, type checks.
2. Graph cleanliness when reference_image=None: zero residual keys, no dummy nodes, base graph immutability.
3. Sequential calls: generate with ref -> without ref -> with ref to verify zero state leakage across calls.
4. Character turnaround dimensions: strict 1536x768 (2:1 ratio, exact multiples of 16), preview 768x384 (exact multiples of 16).
5. Pure white background pixel audit: verifying (255, 255, 255) across canvas borders, margins, and non-subject areas to eliminate DiT attention bleed.
6. Character turnaround sheet automation: missing sheet generation, multi-character isolation, and selective panel reference forwarding.
7. Single Art Workflow Invariant: exactly one text_to_image workflow (qwen_image_21), verified against schema and filesystem.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from engine.comfyui import art as art_mod
from engine.comfyui.art import (
    ART_WORKFLOW_ID,
    ArtEngine,
    ComfyImageGenerationError,
    _patch_workflow,
)
from engine.comfyui.registry import ComfyWorkflowRegistry
from engine.original import art, shotspec
from engine.original.models import Bible, Character, OriginalStory, Panel, Premise, Scene
from engine.original.rigging import (
    RiggingSpec,
    _create_offline_turnaround_image,
    compile_turnaround_prompt,
)
from engine.original.story import init_bible_turnarounds, init_character_turnaround

BASE_WORKFLOW = {
    "4": {
        "class_type": "TextEncodeQwenImage21",
        "inputs": {"prompt": "", "negative_prompt": "", "images.image_1": None},
    },
    "8": {"class_type": "RandomNoise", "inputs": {"noise_seed": 0}},
    "11": {"class_type": "SaveImage", "inputs": {"filename_prefix": "x"}},
    "12": {"class_type": "EmptySD3LatentImage", "inputs": {"width": 1, "height": 1}},
}

PATCH_SLOTS = {
    "prompt": {"node_id": "4", "input": "prompt", "class_type": "TextEncodeQwenImage21"},
    "negative_prompt": {"node_id": "4", "input": "negative_prompt", "class_type": "TextEncodeQwenImage21"},
    "seed": {"node_id": "8", "input": "noise_seed", "class_type": "RandomNoise"},
    "width": {"node_id": "12", "input": "width", "class_type": "EmptySD3LatentImage"},
    "height": {"node_id": "12", "input": "height", "class_type": "EmptySD3LatentImage"},
    "filename_prefix": {"node_id": "11", "input": "filename_prefix", "class_type": "SaveImage"},
    "reference_image": {"node_id": "4", "input": "images.image_1", "class_type": "TextEncodeQwenImage21"},
}


def make_png_bytes(w: int, h: int, color: str = "white") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


class MockAdversarialClient:
    """Mock ComfyUI client recording submitted graphs, uploaded files, and call sequences."""

    def __init__(self, return_image_bytes: bytes | None = None):
        self.return_image = return_image_bytes or make_png_bytes(1344, 768)
        self.submitted_graphs: list[dict[str, Any]] = []
        self.uploaded_files: list[str] = []
        self.uploaded_bytes: list[tuple[bytes, str | None]] = []

    def submit_prompt(self, workflow: dict[str, Any], client_id: str | None = None) -> str:
        self.submitted_graphs.append(json.loads(json.dumps(workflow)))
        return f"prompt_{len(self.submitted_graphs)}"

    def history(self, prompt_id: str) -> dict[str, Any]:
        return {
            prompt_id: {
                "outputs": {
                    "11": {
                        "images": [
                            {"filename": f"{prompt_id}.png", "subfolder": "", "type": "output"}
                        ]
                    }
                }
            }
        }

    def download_output(self, *args: Any, **kwargs: Any) -> bytes:
        return self.return_image

    def upload_image_bytes(self, data: bytes, filename: str | None = None) -> str:
        name = filename or f"pf_{hashlib.sha256(data).hexdigest()[:16]}.png"
        self.uploaded_bytes.append((data, filename))
        self.uploaded_files.append(name)
        return name

    def upload_image(self, path: Path) -> str:
        data = path.read_bytes()
        return self.upload_image_bytes(data, path.name)


class MockAdversarialRegistry:
    def __init__(self, workflow: dict[str, Any] | None = None, slots: dict[str, Any] | None = None):
        self.workflow = workflow or json.loads(json.dumps(BASE_WORKFLOW))
        self.slots = slots or dict(PATCH_SLOTS)

    def load(self, workflow_id: str) -> tuple[dict[str, Any], str]:
        return json.loads(json.dumps(self.workflow)), "a" * 64

    def metadata(self, workflow_id: str) -> dict[str, Any]:
        return {
            "patch_slots": self.slots,
            "model_files": ["qwen.safetensors"],
            "dimension_policy": {
                "mode": "exact",
                "min": 256,
                "max": 2048,
                "multiple_of": 16,
            },
        }

    def preflight(self, workflow_id: str) -> dict[str, Any]:
        return {"ready": True, "missing_nodes": [], "missing_models": []}


def make_test_story() -> OriginalStory:
    mira = Character(
        id="mira",
        name="Mira",
        role="protagonist",
        age_group="child",
        look="short brown hair, green eyes, yellow raincoat, red boots",
        personality="curious",
    )
    lucas = Character(
        id="lucas",
        name="Lucas",
        role="companion",
        age_group="child",
        look="black hair, blue jacket, gray pants, sneakers",
        personality="loyal",
    )
    bible = Bible(
        premise=Premise(title="T", genre="bedtime", logline="L", tone="T", setting="S"),
        characters=[mira, lucas],
        locations=[],
    )
    panels = [
        Panel(
            id="p001",
            scene_id="sc01",
            shot="medium",
            angle="eye_level",
            location_id="attic",
            character_ids=["mira"],
            action="Mira discovers a glowing book.",
        ),
        Panel(
            id="p002",
            scene_id="sc01",
            shot="close",
            angle="eye_level",
            location_id="attic",
            character_ids=["lucas"],
            action="Lucas gasps in surprise.",
        ),
        Panel(
            id="p003",
            scene_id="sc01",
            shot="wide",
            angle="eye_level",
            location_id="attic",
            character_ids=[],
            action="The dusty attic room bathed in warm amber moonlight.",
        ),
    ]
    return OriginalStory(
        bible=bible,
        scenes=[
            Scene(
                id="sc01",
                location_id="attic",
                character_ids=["mira", "lucas"],
                summary="Attic discovery",
                mood="Wonder",
            )
        ],
        panels=panels,
    )


# ==============================================================================
# Group 1: Dynamic LoadImage DAG Injection & Node Allocation
# ==============================================================================

def test_dag_injection_node_id_collision_increments_sequentially():
    """When nodes '13', '14', and '15' already exist, allocator must select '16'."""
    crowded_workflow = json.loads(json.dumps(BASE_WORKFLOW))
    crowded_workflow["13"] = {"class_type": "ExistingNodeA", "inputs": {}}
    crowded_workflow["14"] = {"class_type": "ExistingNodeB", "inputs": {}}
    crowded_workflow["15"] = {"class_type": "ExistingNodeC", "inputs": {}}

    patched = _patch_workflow(
        crowded_workflow,
        PATCH_SLOTS,
        prompt="portrait",
        negative_prompt="",
        width=1344,
        height=768,
        seed=42,
        prefix="pf",
        reference_image="mira_turnaround.png",
    )

    # 1. Verify original nodes 13, 14, 15 were NOT overwritten
    assert patched["13"]["class_type"] == "ExistingNodeA"
    assert patched["14"]["class_type"] == "ExistingNodeB"
    assert patched["15"]["class_type"] == "ExistingNodeC"

    # 2. Verify LoadImage was assigned node ID '16'
    assert "16" in patched
    assert patched["16"]["class_type"] == "LoadImage"
    assert patched["16"]["inputs"]["image"] == "mira_turnaround.png"

    # 3. Verify node 4 inputs point to ['16', 0]
    assert patched["4"]["inputs"]["images.image_1"] == ["16", 0]


def test_dag_injection_with_existing_list_input():
    """If reference_image is already a wired tuple/list [node_id, slot], it binds directly."""
    patched = _patch_workflow(
        BASE_WORKFLOW,
        PATCH_SLOTS,
        prompt="portrait",
        negative_prompt="",
        width=1344,
        height=768,
        seed=42,
        prefix="pf",
        reference_image=["99", 0],  # type: ignore[arg-type]
    )

    assert patched["4"]["inputs"]["images.image_1"] == ["99", 0]
    assert "13" not in patched


def test_art_engine_generate_input_types_bytes(tmp_path):
    """Raw bytes passed to reference_image are uploaded via upload_image_bytes."""
    client = MockAdversarialClient()
    registry = MockAdversarialRegistry()
    engine = ArtEngine(client, registry)

    raw_bytes = make_png_bytes(1536, 768, "blue")
    engine.generate("portrait of Mira", reference_image=raw_bytes)

    assert len(client.uploaded_bytes) == 1
    assert client.uploaded_bytes[0][0] == raw_bytes
    submitted = client.submitted_graphs[0]
    assert "13" in submitted
    assert submitted["13"]["class_type"] == "LoadImage"
    assert submitted["4"]["inputs"]["images.image_1"] == ["13", 0]


def test_art_engine_generate_input_types_path(tmp_path):
    """Existing Path passed to reference_image is uploaded via upload_image."""
    client = MockAdversarialClient()
    registry = MockAdversarialRegistry()
    engine = ArtEngine(client, registry)

    ref_path = tmp_path / "ref_mira.png"
    ref_path.write_bytes(make_png_bytes(1536, 768, "green"))

    engine.generate("portrait of Mira", reference_image=ref_path)

    assert "ref_mira.png" in client.uploaded_files
    submitted = client.submitted_graphs[0]
    assert submitted["13"]["inputs"]["image"] == "ref_mira.png"
    assert submitted["4"]["inputs"]["images.image_1"] == ["13", 0]


def test_art_engine_generate_input_types_existing_file_str(tmp_path):
    """String pointing to an existing file is uploaded via upload_image."""
    client = MockAdversarialClient()
    registry = MockAdversarialRegistry()
    engine = ArtEngine(client, registry)

    ref_path = tmp_path / "ref_str.png"
    ref_path.write_bytes(make_png_bytes(1536, 768, "yellow"))

    engine.generate("portrait of Mira", reference_image=str(ref_path))

    assert "ref_str.png" in client.uploaded_files
    submitted = client.submitted_graphs[0]
    assert submitted["13"]["inputs"]["image"] == "ref_str.png"


def test_art_engine_generate_input_types_server_filename_str():
    """String containing server filename (non-file) is used directly without re-upload."""
    client = MockAdversarialClient()
    registry = MockAdversarialRegistry()
    engine = ArtEngine(client, registry)

    engine.generate("portrait of Mira", reference_image="already_on_server_123.png")

    assert client.uploaded_files == []
    submitted = client.submitted_graphs[0]
    assert submitted["13"]["inputs"]["image"] == "already_on_server_123.png"


def test_art_engine_generate_input_types_non_existent_path(tmp_path):
    """Path to non-existent file raises FileNotFoundError when upload_image attempts to read."""
    client = MockAdversarialClient()
    registry = MockAdversarialRegistry()
    engine = ArtEngine(client, registry)

    non_existent = tmp_path / "ghost.png"
    with pytest.raises(FileNotFoundError):
        engine.generate("portrait of Mira", reference_image=non_existent)


def test_art_engine_generate_unsupported_types():
    """Unsupported types (int, list, dict, float) raise ValueError."""
    client = MockAdversarialClient()
    registry = MockAdversarialRegistry()
    engine = ArtEngine(client, registry)

    for invalid_val in [123, 45.67, ["invalid"], {"image": "test"}]:
        with pytest.raises(ValueError, match="Unsupported reference_image type"):
            engine.generate("portrait", reference_image=invalid_val)  # type: ignore[arg-type]


# ==============================================================================
# Group 2: Graph Cleanliness, Immutability & Zero State Leakage
# ==============================================================================

def test_graph_cleanliness_reference_none():
    """When reference_image=None, node 4 has zero images.image_1 and no LoadImage node exists."""
    client = MockAdversarialClient()
    registry = MockAdversarialRegistry()
    engine = ArtEngine(client, registry)

    engine.generate("portrait without ref", reference_image=None)

    submitted = client.submitted_graphs[0]
    assert "images.image_1" not in submitted["4"]["inputs"]
    assert "13" not in submitted
    # Verify no LoadImage node in entire submitted DAG
    for node_id, node in submitted.items():
        assert node.get("class_type") != "LoadImage", f"Unexpected LoadImage at node {node_id}"


def test_sequential_calls_zero_state_leakage(tmp_path):
    """Calling generate with reference -> without reference -> with reference must have zero state leakage."""
    client = MockAdversarialClient()
    registry = MockAdversarialRegistry()
    engine = ArtEngine(client, registry)

    ref_1 = tmp_path / "ref_1.png"
    ref_1.write_bytes(make_png_bytes(1536, 768))
    ref_2 = tmp_path / "ref_2.png"
    ref_2.write_bytes(make_png_bytes(1536, 768))

    # 1. Call WITH reference 1
    engine.generate("call 1 with ref", reference_image=ref_1)
    g1 = client.submitted_graphs[0]
    assert "13" in g1
    assert g1["13"]["inputs"]["image"] == "ref_1.png"
    assert g1["4"]["inputs"]["images.image_1"] == ["13", 0]

    # 2. Call WITHOUT reference
    engine.generate("call 2 without ref", reference_image=None)
    g2 = client.submitted_graphs[1]
    assert "13" not in g2
    assert "images.image_1" not in g2["4"]["inputs"]

    # 3. Call WITH reference 2
    engine.generate("call 3 with ref", reference_image=ref_2)
    g3 = client.submitted_graphs[2]
    assert "13" in g3
    assert g3["13"]["inputs"]["image"] == "ref_2.png"
    assert g3["4"]["inputs"]["images.image_1"] == ["13", 0]

    # 4. Verify original BASE_WORKFLOW was not mutated
    assert "images.image_1" in BASE_WORKFLOW["4"]["inputs"]
    assert BASE_WORKFLOW["4"]["inputs"]["images.image_1"] is None
    assert "13" not in BASE_WORKFLOW


# ==============================================================================
# Group 3: Turnaround Dimensions & Preview Assertions
# ==============================================================================

def test_turnaround_dimensions_strict_2_to_1_and_multiples_of_16():
    """Assert strict 1536x768 (2:1 ratio, exact integer multiples of 16)."""
    dim_full = shotspec.SHOT_DIMENSIONS["turnaround"]
    dim_full_sheet = shotspec.SHOT_DIMENSIONS["turnaround_sheet"]

    assert dim_full == (1536, 768)
    assert dim_full_sheet == (1536, 768)

    w, h = dim_full
    assert w / h == 2.0, "Aspect ratio must be strictly 2:1"
    assert w % 16 == 0, f"Width {w} must be a multiple of 16"
    assert h % 16 == 0, f"Height {h} must be a multiple of 16"
    assert w == 16 * 96
    assert h == 16 * 48

    # 4-view slice width verification
    slice_w = w // 4
    assert slice_w == 384
    assert slice_w % 16 == 0
    assert slice_w == 16 * 24


def test_turnaround_preview_dimensions_strict():
    """Assert strict preview dimensions 768x384 (2:1 ratio, exact integer multiples of 16)."""
    dim_prev = shotspec.SHOT_DIMENSIONS_PREVIEW["turnaround"]
    dim_prev_sheet = shotspec.SHOT_DIMENSIONS_PREVIEW["turnaround_sheet"]

    assert dim_prev == (768, 384)
    assert dim_prev_sheet == (768, 384)

    w, h = dim_prev
    assert w / h == 2.0, "Preview aspect ratio must be strictly 2:1"
    assert w % 16 == 0, f"Preview width {w} must be a multiple of 16"
    assert h % 16 == 0, f"Preview height {h} must be a multiple of 16"
    assert w == 16 * 48
    assert h == 16 * 24

    # Preview 4-view slice width verification
    slice_prev_w = w // 4
    assert slice_prev_w == 192
    assert slice_prev_w % 16 == 0
    assert slice_prev_w == 16 * 12


def test_resolve_dimensions_turnaround_full_and_preview():
    """shotspec.resolve_dimensions correctly resolves turnaround and turnaround_sheet."""
    assert shotspec.resolve_dimensions("turnaround") == (1536, 768)
    assert shotspec.resolve_dimensions("turnaround_sheet") == (1536, 768)
    assert shotspec.resolve_dimensions("turnaround", preview=True) == (768, 384)
    assert shotspec.resolve_dimensions("turnaround_sheet", preview=True) == (768, 384)


# ==============================================================================
# Group 4: Pure White Background Pixel & Attention Bleed Auditing
# ==============================================================================

def test_offline_turnaround_image_pixel_audit_pure_white():
    """Inspect _create_offline_turnaround_image pixels across canvas borders and background."""
    story = make_test_story()
    mira = story.bible.characters[0]
    spec = RiggingSpec(pose="a_pose")
    img = _create_offline_turnaround_image(mira, spec, (1536, 768))

    assert img.size == (1536, 768)
    pixels = img.load()

    # 1. Check all 4 extreme outer corners
    assert pixels[0, 0] == (255, 255, 255), "Top-left corner must be pure white"
    assert pixels[1535, 0] == (255, 255, 255), "Top-right corner must be pure white"
    assert pixels[0, 767] == (255, 255, 255), "Bottom-left corner must be pure white"
    assert pixels[1535, 767] == (255, 255, 255), "Bottom-right corner must be pure white"

    # 2. Check upper empty margin row (y = 4) across sample points
    for x in [10, 100, 384, 768, 1152, 1500]:
        assert pixels[x, 4] == (255, 255, 255), f"Pixel at ({x}, 4) must be pure white"

    # 3. Check bottom empty margin row (y = 764) across sample points
    for x in [10, 100, 384, 768, 1152, 1500]:
        assert pixels[x, 764] == (255, 255, 255), f"Pixel at ({x}, 764) must be pure white"

    # 4. Check between-view divider margins
    for x in [380, 388, 764, 772, 1148, 1156]:
        # At y=50 (above head, inside border line)
        assert pixels[x, 50] in [(255, 255, 255), (220, 220, 220)]


def test_turnaround_prompt_directives_against_attention_bleed():
    """Turnaround prompt must specify clean pure white background and suppress scenery/props."""
    story = make_test_story()
    mira = story.bible.characters[0]

    # Natural prompt
    nat_prompt = compile_turnaround_prompt(mira, story, style_kind="natural")
    assert isinstance(nat_prompt, str)
    assert "Solid, seamless clean pure white background" in nat_prompt
    assert "zero environment, zero scenery, zero shadows, and no props" in nat_prompt
    assert "to prevent background attention bleed" in nat_prompt
    assert "no text, no captions, no speech bubbles, no watermark" in nat_prompt.lower()

    # Negative prompt
    _, neg_prompt = compile_turnaround_prompt(mira, story, style_kind="tags", return_negative=True)
    assert "complex background" in neg_prompt
    assert "background clutter" in neg_prompt
    assert "scenery, props, furniture" in neg_prompt


# ==============================================================================
# Group 5: Turnaround Sheet Automation & Reference Forwarding
# ==============================================================================

def test_init_character_turnaround_creates_file_and_updates_model(tmp_path):
    """init_character_turnaround automatically creates turnaround file and sets turnaround_sheet."""
    story = make_test_story()
    mira = story.bible.characters[0]
    assert mira.turnaround_sheet is None

    updated_mira = init_character_turnaround(mira, story, tmp_path)
    expected_sheet = tmp_path / "sheets" / "mira_turnaround.png"

    assert expected_sheet.exists()
    assert updated_mira.turnaround_sheet == "sheets/mira_turnaround.png"

    # Verify generated image has correct dimensions
    with Image.open(expected_sheet) as im:
        assert im.size == (1536, 768)


def test_init_character_turnaround_idempotent_no_overwrite(tmp_path):
    """If turnaround sheet already exists, init_character_turnaround reuses it without re-synthesis."""
    story = make_test_story()
    mira = story.bible.characters[0]

    sheets_dir = tmp_path / "sheets"
    sheets_dir.mkdir(parents=True, exist_ok=True)
    custom_sheet = sheets_dir / "mira_turnaround.png"
    sentinel_bytes = b"CUSTOM_PRE_EXISTING_TURNAROUND_SHEET_DATA"
    custom_sheet.write_bytes(sentinel_bytes)

    updated_mira = init_character_turnaround(mira, story, tmp_path)
    assert updated_mira.turnaround_sheet == "sheets/mira_turnaround.png"
    assert custom_sheet.read_bytes() == sentinel_bytes, "Pre-existing sheet must not be overwritten"


def test_init_bible_turnarounds_multi_character(tmp_path):
    """init_bible_turnarounds initializes distinct turnaround sheets for all characters in bible."""
    story = make_test_story()
    story_json = tmp_path / "story.json"
    story_json.write_text(story.model_dump_json(indent=2), encoding="utf-8")

    updated_story = init_bible_turnarounds(story, tmp_path)

    mira = updated_story.bible.characters[0]
    lucas = updated_story.bible.characters[1]

    assert mira.turnaround_sheet == "sheets/mira_turnaround.png"
    assert lucas.turnaround_sheet == "sheets/lucas_turnaround.png"
    assert (tmp_path / mira.turnaround_sheet).exists()
    assert (tmp_path / lucas.turnaround_sheet).exists()

    # Verify story.json was persisted
    persisted_data = json.loads(story_json.read_text(encoding="utf-8"))
    persisted_chars = persisted_data["bible"]["characters"]
    assert persisted_chars[0]["turnaround_sheet"] == "sheets/mira_turnaround.png"
    assert persisted_chars[1]["turnaround_sheet"] == "sheets/lucas_turnaround.png"


def test_generate_art_reference_forwarding_granularity(tmp_path):
    """generate_art forwards character turnaround sheet to panels featuring that character, and None to scenery panels."""
    class TrackingQwenRunner:
        engine = "qwen"
        style = "natural"

        def __init__(self):
            self.calls: list[tuple[str, Any]] = []

        def generate(self, pos, neg, seed, w, h, prefix, reference=None, **kw):
            self.calls.append((prefix, reference))
            buf = io.BytesIO()
            Image.new("RGB", (w, h), "white").save(buf, "PNG")
            return buf.getvalue()

    story = make_test_story()
    runner = TrackingQwenRunner()

    art.generate_art(story, tmp_path, runner)

    # 1. Panel 1 features 'mira' -> must bind mira_turnaround.png
    p1_call = next(c for c in runner.calls if c[0] == "panel_p001")
    assert p1_call[1] is not None
    assert "mira_turnaround.png" in str(p1_call[1])

    # 2. Panel 2 features 'lucas' -> must bind lucas_turnaround.png
    p2_call = next(c for c in runner.calls if c[0] == "panel_p002")
    assert p2_call[1] is not None
    assert "lucas_turnaround.png" in str(p2_call[1])

    # 3. Panel 3 has no characters (scenery) -> reference must be None
    p3_call = next(c for c in runner.calls if c[0] == "panel_p003")
    assert p3_call[1] is None, f"Panel p003 should have no reference, got {p3_call[1]}"


# ==============================================================================
# Group 6: Single Art Workflow Invariant & Schema Integrity
# ==============================================================================

def test_single_art_workflow_invariant_strict():
    """Verify Single Art Workflow invariant: exactly one text_to_image workflow (qwen_image_21)."""
    registry_file = Path(art_mod.__file__).parent / "workflow_registry.json"
    entries = json.loads(registry_file.read_text(encoding="utf-8"))

    t2i_entries = [e for e in entries if e.get("purpose") == "text_to_image"]
    assert len(t2i_entries) == 1, f"Expected exactly 1 text_to_image workflow, found {len(t2i_entries)}: {[e['id'] for e in t2i_entries]}"
    assert t2i_entries[0]["id"] == ART_WORKFLOW_ID
    assert t2i_entries[0]["id"] == "qwen_image_21"


def test_qwen_image_21_schema_and_checksum_integrity():
    """Verify qwen_image_21.api.json SHA-256 matches registry, defines null slot, and has LoadImage."""
    registry = ComfyWorkflowRegistry()
    meta = registry.metadata(ART_WORKFLOW_ID)
    wf, actual_sha = registry.load(ART_WORKFLOW_ID)

    # Checksum matches
    assert actual_sha == meta["sha256"]

    # Required nodes include LoadImage
    assert "LoadImage" in meta["required_nodes"]

    # Patch slot reference_image targeting node 4 images.image_1
    assert "reference_image" in meta["patch_slots"]
    slot = meta["patch_slots"]["reference_image"]
    assert slot["node_id"] == "4"
    assert slot["input"] == "images.image_1"
    assert slot["class_type"] == "TextEncodeQwenImage21"

    # Node 4 in raw JSON defines images.image_1: null
    assert "4" in wf
    assert wf["4"]["class_type"] == "TextEncodeQwenImage21"
    assert "images.image_1" in wf["4"]["inputs"]
    assert wf["4"]["inputs"]["images.image_1"] is None


# ==============================================================================
# Group 7: Adversarial Edge Cases & Stress Scenarios
# ==============================================================================

def test_art_engine_generate_path_with_spaces_and_unicode(tmp_path):
    """Paths with spaces and Unicode characters are handled cleanly by upload and DAG wiring."""
    client = MockAdversarialClient()
    registry = MockAdversarialRegistry()
    engine = ArtEngine(client, registry)

    unicode_dir = tmp_path / "sp ace dir" / "アニメ"
    unicode_dir.mkdir(parents=True, exist_ok=True)
    ref_file = unicode_dir / "character sheet 2026.png"
    ref_file.write_bytes(make_png_bytes(1536, 768))

    engine.generate("portrait with unicode path", reference_image=ref_file)

    assert "character sheet 2026.png" in client.uploaded_files
    submitted = client.submitted_graphs[0]
    assert submitted["13"]["inputs"]["image"] == "character sheet 2026.png"


def test_offline_turnaround_image_preview_dimensions_pixel_audit():
    """Preview turnaround image (768x384) must also strictly maintain pure white background."""
    story = make_test_story()
    mira = story.bible.characters[0]
    spec = RiggingSpec(pose="t_pose")
    img = _create_offline_turnaround_image(mira, spec, (768, 384))

    assert img.size == (768, 384)
    pixels = img.load()

    # All 4 outer corners
    assert pixels[0, 0] == (255, 255, 255)
    assert pixels[767, 0] == (255, 255, 255)
    assert pixels[0, 383] == (255, 255, 255)
    assert pixels[767, 383] == (255, 255, 255)

    # Empty margins at top and bottom
    for x in [5, 100, 384, 500, 760]:
        assert pixels[x, 2] == (255, 255, 255)
        assert pixels[x, 381] == (255, 255, 255)


def test_turnaround_slice_edge_cases(tmp_path):
    """slice_turnaround_sheet handles various input types, odd view counts, and empty view lists."""
    from engine.original.rigging import slice_turnaround_sheet

    raw_bytes = make_png_bytes(1536, 768)
    sheet_path = tmp_path / "sheet.png"
    sheet_path.write_bytes(raw_bytes)

    # 1. From Path
    slices_path = slice_turnaround_sheet(sheet_path)
    assert len(slices_path) == 4
    for view_img in slices_path.values():
        assert view_img.size == (384, 768)

    # 2. From bytes
    slices_bytes = slice_turnaround_sheet(raw_bytes)
    assert len(slices_bytes) == 4

    # 3. Custom 3-view list
    slices_3 = slice_turnaround_sheet(sheet_path, views=["front", "side", "back"])
    assert len(slices_3) == 3
    assert set(slices_3.keys()) == {"front", "side", "back"}

    # 4. Empty views list returns {}
    assert slice_turnaround_sheet(sheet_path, views=[]) == {}

    # 5. Invalid input type raises TypeError
    with pytest.raises(TypeError):
        slice_turnaround_sheet(12345)  # type: ignore[arg-type]


def test_patch_workflow_unsupported_slot_rejection():
    """Passing reference_image to a workflow that does not declare the slot raises ComfyImageGenerationError."""
    slots_without_ref = {k: v for k, v in PATCH_SLOTS.items() if k != "reference_image"}
    with pytest.raises(ComfyImageGenerationError, match="Approved workflow does not declare every required patch slot"):
        _patch_workflow(
            BASE_WORKFLOW,
            slots_without_ref,
            prompt="portrait",
            negative_prompt="",
            width=1344,
            height=768,
            seed=42,
            prefix="pf",
            reference_image="mira.png",
        )

