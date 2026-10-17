import numpy as np
from PIL import Image, ImageDraw
from engine.imaging.text_regions import (
    ClassicalTextRegionDetector,
    TextRegionType,
    TextRegionStatus,
)

def test_speech_and_narration_detection():
    # Create a 800x600 panel image with a speech balloon and a narration box
    img = Image.new("RGB", (800, 600), (120, 140, 180)) # Colored artwork background
    d = ImageDraw.Draw(img)

    # 1. Narration box at top (rectangular)
    d.rectangle([50, 40, 450, 140], fill=(255, 255, 255), outline=(0, 0, 0), width=3)
    # Draw text-like lines inside narration box
    d.line([80, 70, 400, 70], fill=(0, 0, 0), width=4)
    d.line([80, 95, 350, 95], fill=(0, 0, 0), width=4)

    # 2. Speech balloon at bottom right (elliptical)
    d.ellipse([450, 320, 750, 520], fill=(255, 255, 255), outline=(0, 0, 0), width=3)
    # Draw text-like lines inside speech balloon
    d.line([500, 380, 700, 380], fill=(0, 0, 0), width=4)
    d.line([520, 415, 680, 415], fill=(0, 0, 0), width=4)
    d.line([540, 450, 650, 450], fill=(0, 0, 0), width=4)

    np_img = np.array(img)
    detector = ClassicalTextRegionDetector()
    regions = detector.detect(
        panel_image=np_img,
        panel_id="panel_1",
        page_id="page_1",
        project_id="proj_1",
        panel_x=100,
        panel_y=200,
        page_w=1200,
        page_h=1800,
        reading_direction="ltr",
    )

    assert len(regions) >= 2
    # Verify both narration and speech regions exist
    types = [r.region_type for r in regions]
    assert TextRegionType.NARRATION.value in types or TextRegionType.CAPTION.value in types
    assert TextRegionType.SPEECH.value in types

    # Check top narration region sequence
    narration_reg = [r for r in regions if r.y < 200][0]
    assert narration_reg.sequence_in_panel == 1
    assert narration_reg.status == TextRegionStatus.DETECTED.value
    # Normalized coordinates check
    assert 0.0 <= narration_reg.normalized_x <= 1.0
    assert 0.0 <= narration_reg.normalized_y <= 1.0

def test_fallback_on_blank_or_pure_art_panel():
    # Create a 800x600 panel image with no text bubbles or text strokes
    img = Image.new("RGB", (800, 600), (40, 40, 60))
    d = ImageDraw.Draw(img)
    # Draw pure graphic background gradient/shape
    d.ellipse([100, 100, 700, 500], fill=(60, 80, 120))

    np_img = np.array(img)
    detector = ClassicalTextRegionDetector()
    regions = detector.detect(
        panel_image=np_img,
        panel_id="panel_art",
        page_id="page_1",
        panel_x=50,
        panel_y=150,
    )

    # Fallback path MUST trigger: 1 UNKNOWN region covering whole panel with NEEDS_REVIEW
    assert len(regions) == 1
    r = regions[0]
    assert r.region_type == TextRegionType.UNKNOWN.value
    assert r.status == TextRegionStatus.NEEDS_REVIEW.value
    assert r.detection_method == "FALLBACK_PANEL"
    assert r.width == 800
    assert r.height == 600
    assert r.normalized_width == 1.0
    assert r.normalized_height == 1.0
    assert r.page_x == 50
    assert r.page_y == 150
