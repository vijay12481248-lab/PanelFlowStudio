"""
Unit tests for Smart Panel Slicing, Saliency-Aware 16:9 Framing,
Semantic Storytelling Synchronization, and AI Visual Self-Review.
"""
import pytest
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw

from engine.imaging.panels.smart_slicer import SmartPanelSlicer
from engine.imaging.panels.smart_framer import SmartFramer
from engine.pipeline.semantic_sync import SemanticStorySync
from engine.imaging.panel_quality_reviewer import PanelQualityReviewer, PanelAuditResult, TimelineAuditResult


def test_smart_slicer_avoids_text_boxes_and_finds_energy_valleys(tmp_path: Path):
    """
    Verifies that the slicer identifies gutter valleys and never cuts through text bounding boxes.
    """
    # Create a 600x3000 tall strip with two illustration blocks and a text bubble
    img = np.full((3000, 600, 3), 255, dtype=np.uint8)

    # Block 1 art at y: 100 to 1200
    img[100:1200, 50:550] = (40, 40, 180)

    # Text bubble at y: 1350 to 1550 (x: 100 to 500)
    img[1350:1550, 100:500] = (240, 240, 240)
    text_boxes = [(100, 1350, 400, 200)]

    # Block 2 art at y: 1700 to 2800
    img[1700:2800, 50:550] = (180, 40, 40)

    slicer = SmartPanelSlicer(min_panel_height=300, max_panel_height=2000)
    cut_lines = slicer.find_safe_horizontal_cut_lines(img, text_boxes=text_boxes)

    assert len(cut_lines) >= 1
    for cut in cut_lines:
        # Crucial: cut MUST NOT fall inside the text box [1350, 1550]!
        assert not (1350 <= cut <= 1550), f"Cut at y={cut} intersected the dialogue text bubble!"

    # Save and test slice_tall_image
    test_img_path = tmp_path / "tall_strip.jpg"
    Image.fromarray(img).save(test_img_path)

    slices = slicer.slice_tall_image(test_img_path, tmp_path / "slices", "strip", text_boxes=text_boxes)
    assert len(slices) >= 2
    for s in slices:
        assert Path(s["file_path"]).exists()
        assert s["height"] >= 300


def test_smart_framer_cinematic_motion_for_tall_panels(tmp_path: Path):
    """
    Verifies that tall vertical panels receive dynamic Ken-Burns vertical panning plans.
    """
    framer = SmartFramer(target_width=1920, target_height=1080)

    # Create a tall portrait panel (600x1600, aspect ~ 0.375)
    img_path = tmp_path / "tall_panel.jpg"
    pil_img = Image.new("RGB", (600, 1600), (245, 245, 245))
    draw = ImageDraw.Draw(pil_img)
    # Character head at top (y: 200)
    draw.ellipse([200, 150, 400, 350], fill=(220, 180, 140))
    # Character sword/action at bottom (y: 1200)
    draw.rectangle([250, 1100, 350, 1500], fill=(70, 70, 70))
    pil_img.save(img_path)

    plan = framer.compute_framing_plan(img_path, duration_sec=5.0)

    assert plan["is_tall"] is True
    assert plan["motion_type"] == "CINEMATIC_VERTICAL_PAN"
    assert "start_transform" in plan
    assert "end_transform" in plan
    # Start y should differ from end y for vertical camera glide
    assert plan["start_transform"]["y"] != plan["end_transform"]["y"]


def test_semantic_sync_anchors_visual_panels_to_narration_evidence():
    """
    Verifies that panels are strictly locked to spoken narration evidence and enforce >= 2.5s pacing.
    """
    sync = SemanticStorySync(min_panel_duration_sec=2.5)

    scenes = [
        {
            "id": "scene_01",
            "duration_sec": 12.0,
            "layers": [
                {"id": "ly_0", "source_panel_id": "panel_alpha", "duration_sec": 4.0},
                {"id": "ly_1", "source_panel_id": "panel_beta", "duration_sec": 4.0},
                {"id": "ly_2", "source_panel_id": "panel_gamma", "duration_sec": 4.0},
            ],
        }
    ]

    # Narration explicitly references panel_beta for 7 seconds and panel_gamma for 5 seconds
    narration_clips = [
        {
            "id": "clip_01",
            "scene_id": "scene_01",
            "duration_sec": 7.0,
            "source_evidence": {"panel_ids": ["panel_beta"]},
        },
        {
            "id": "clip_02",
            "scene_id": "scene_01",
            "duration_sec": 5.0,
            "source_evidence": {"panel_ids": ["panel_gamma"]},
        },
    ]

    synced = sync.synchronize_scenes_to_narration(scenes, narration_clips)
    sc = synced[0]

    # Total duration should match scene duration
    assert sc["duration_sec"] >= 12.0
    layers = sc["layers"]

    # Visual layers must be allocated to panel_beta and panel_gamma according to speech length
    pids = [ly["source_panel_id"] for ly in layers]
    assert "panel_beta" in pids
    assert "panel_gamma" in pids

    for ly in layers:
        assert ly["duration_sec"] >= 2.5, f"Layer {ly['id']} duration {ly['duration_sec']} is below minimum 2.5s hold time"


def test_quality_reviewer_flags_ad_watermarks_and_heals_pacing(tmp_path: Path):
    """
    Verifies that the AI Quality Reviewer flags ad watermarks and auto-heals fast or duplicate layers.
    """
    reviewer = PanelQualityReviewer()

    # 1. Test ad panel detection
    panel_img = tmp_path / "panel_ad.jpg"
    Image.new("RGB", (800, 600), (255, 255, 255)).save(panel_img)

    ad_audit = reviewer.audit_panel(
        panel_img,
        panel_id="ad_panel_01",
        sequence=1,
        ocr_text="Read first on ManhuaPlus! Support our translation on Patreon and join Discord!",
    )
    assert ad_audit.is_ad_or_credit is True
    assert ad_audit.is_valid is False
    assert any("discord" in issue.lower() or "patreon" in issue.lower() for issue in ad_audit.issues)

    # 2. Test timeline pacing and duplicate healing
    scenes_with_flaws = [
        {
            "id": "sc_flawed",
            "duration_sec": 10.0,
            "layers": [
                {"id": "l1", "source_panel_id": "p1", "start_offset_sec": 0.0, "duration_sec": 0.8},   # Too fast! (< 2.0s)
                {"id": "l2", "source_panel_id": "p1", "start_offset_sec": 0.8, "duration_sec": 0.8},   # Duplicate!
                {"id": "l3", "source_panel_id": "p2", "start_offset_sec": 1.6, "duration_sec": 8.4},
            ],
        }
    ]

    report, healed_scenes = reviewer.audit_and_heal_timeline(scenes_with_flaws, auto_heal=True)

    assert report.auto_healed is True
    assert report.fast_switching_count >= 1
    assert report.duplicate_layer_count >= 1

    # In the healed scene, consecutive duplicates must be merged
    healed_sc = healed_scenes[0]
    healed_pids = [ly["source_panel_id"] for ly in healed_sc["layers"]]
    assert len(healed_pids) == 2  # p1 duplicate merged!
    assert healed_pids == ["p1", "p2"]
    for ly in healed_sc["layers"]:
        assert ly["duration_sec"] >= 2.0, "Healed layer duration must meet minimum pacing threshold"
