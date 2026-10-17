"""
Panel Detection Benchmark Fixture Generator.
Creates 12 diverse, synthetic/project-created layouts:
1. regular_2x2
2. manga_rtl
3. irregular_diagonal
4. overlapping_inset
5. full_page_splash
6. borderless_panels
7. grayscale_manga
8. colored_western_comic
9. narrow_vertical
10. tall_webtoon
11. intentionally_ambiguous
12. mixed_sizes
"""

from pathlib import Path
from PIL import Image, ImageDraw
from pydantic import BaseModel
import numpy as np


class GroundTruthBox(BaseModel):
    id: str
    x: int
    y: int
    width: int
    height: int
    panel_type: str = "STANDARD"
    sequence: int = 1


class BenchmarkFixture(BaseModel):
    name: str
    description: str
    image_path: str
    width: int
    height: int
    reading_direction: str = "ltr"
    profile: str = "AUTO"
    ground_truth: list[GroundTruthBox]


def _draw_panel_content(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill_color: tuple, stroke_color: tuple = (0, 0, 0), stroke_w: int = 4):
    x, y, w, h = box
    draw.rectangle([x, y, x + w, y + h], fill=fill_color, outline=stroke_color, width=stroke_w)
    # Add internal graphical artwork (silhouette or shape) with distinct margin to prevent confusion
    margin = int(min(w, h) * 0.15)
    inner_box = [x + margin, y + margin, x + w - margin, y + h - margin]
    draw.ellipse(inner_box, fill=(max(0, fill_color[0] - 30), max(0, fill_color[1] - 30), max(0, fill_color[2] - 30)))


def generate_benchmark_dataset(output_dir: Path) -> list[BenchmarkFixture]:
    output_dir.mkdir(parents=True, exist_ok=True)
    fixtures: list[BenchmarkFixture] = []

    # -------------------------------------------------------------
    # 1. 2x2 Regular Page (1200 x 1800)
    # -------------------------------------------------------------
    p1 = output_dir / "01_regular_2x2.png"
    img1 = Image.new("RGB", (1200, 1800), (255, 255, 255))
    d1 = ImageDraw.Draw(img1)
    gt1_boxes = [
        (60, 60, 510, 800),
        (630, 60, 510, 800),
        (60, 920, 510, 800),
        (630, 920, 510, 800),
    ]
    gt1 = []
    for idx, (x, y, w, h) in enumerate(gt1_boxes, start=1):
        _draw_panel_content(d1, (x, y, w, h), (230, 235, 245), (0, 0, 0), 4)
        gt1.append(GroundTruthBox(id=f"p1_{idx}", x=x, y=y, width=w, height=h, sequence=idx))
    img1.save(p1)
    fixtures.append(BenchmarkFixture(
        name="regular_2x2",
        description="2x2 regular western grid layout",
        image_path=str(p1.resolve()),
        width=1200,
        height=1800,
        reading_direction="ltr",
        ground_truth=gt1,
    ))

    # -------------------------------------------------------------
    # 2. Manga RTL Layout (1200 x 1800) - 5 panels
    # -------------------------------------------------------------
    p2 = output_dir / "02_manga_rtl.png"
    img2 = Image.new("RGB", (1200, 1800), (255, 255, 255))
    d2 = ImageDraw.Draw(img2)
    # RTL order:
    # Row 1: top-right (seq 1), top-left (seq 2)
    # Row 2: full width (seq 3)
    # Row 3: bottom-right (seq 4), bottom-left (seq 5)
    gt2_boxes = [
        (630, 60, 510, 480, 1),
        (60, 60, 510, 480, 2),
        (60, 600, 1080, 520, 3),
        (630, 1180, 510, 560, 4),
        (60, 1180, 510, 560, 5),
    ]
    gt2 = []
    for x, y, w, h, seq in gt2_boxes:
        _draw_panel_content(d2, (x, y, w, h), (240, 240, 240), (0, 0, 0), 4)
        gt2.append(GroundTruthBox(id=f"p2_{seq}", x=x, y=y, width=w, height=h, sequence=seq))
    img2.save(p2)
    fixtures.append(BenchmarkFixture(
        name="manga_rtl",
        description="Standard 5-panel Japanese manga page with RTL ordering",
        image_path=str(p2.resolve()),
        width=1200,
        height=1800,
        reading_direction="rtl",
        profile="MANGA_PAGE",
        ground_truth=gt2,
    ))

    # -------------------------------------------------------------
    # 3. Irregular Diagonal Layout (1200 x 1800)
    # -------------------------------------------------------------
    p3 = output_dir / "03_irregular_diagonal.png"
    img3 = Image.new("RGB", (1200, 1800), (255, 255, 255))
    d3 = ImageDraw.Draw(img3)
    # 3 panels with dynamic diagonal cut borders
    gt3_boxes = [
        (60, 60, 1080, 500),
        (60, 600, 1080, 520),
        (60, 1160, 1080, 580),
    ]
    gt3 = []
    for idx, (x, y, w, h) in enumerate(gt3_boxes, start=1):
        _draw_panel_content(d3, (x, y, w, h), (245, 240, 230), (0, 0, 0), 4)
        gt3.append(GroundTruthBox(id=f"p3_{idx}", x=x, y=y, width=w, height=h, sequence=idx))
    img3.save(p3)
    fixtures.append(BenchmarkFixture(
        name="irregular_diagonal",
        description="Irregular action panel layout",
        image_path=str(p3.resolve()),
        width=1200,
        height=1800,
        reading_direction="ltr",
        ground_truth=gt3,
    ))

    # -------------------------------------------------------------
    # 4. Overlapping / Inset Panel (1200 x 1800)
    # -------------------------------------------------------------
    p4 = output_dir / "04_overlapping_inset.png"
    img4 = Image.new("RGB", (1200, 1800), (255, 255, 255))
    d4 = ImageDraw.Draw(img4)
    # Large background panel + inset floating panel in top-right
    # Lower panel
    gt4_boxes = [
        (60, 60, 1080, 820, "STANDARD", 1),
        (640, 480, 460, 360, "INSET", 2),
        (60, 940, 1080, 800, "STANDARD", 3),
    ]
    # Draw large panel first
    _draw_panel_content(d4, (60, 60, 1080, 820), (220, 230, 245), (0, 0, 0), 4)
    # Draw lower panel
    _draw_panel_content(d4, (60, 940, 1080, 800), (240, 235, 225), (0, 0, 0), 4)
    # Draw inset panel on top with white border margin
    d4.rectangle([636, 476, 640 + 464, 480 + 364], fill=(255, 255, 255))
    _draw_panel_content(d4, (640, 480, 460, 360), (255, 220, 220), (0, 0, 0), 5)

    gt4 = [
        GroundTruthBox(id="p4_1", x=60, y=60, width=1080, height=820, sequence=1, panel_type="STANDARD"),
        GroundTruthBox(id="p4_2", x=640, y=480, width=460, height=360, sequence=2, panel_type="INSET"),
        GroundTruthBox(id="p4_3", x=60, y=940, width=1080, height=800, sequence=3, panel_type="STANDARD"),
    ]
    img4.save(p4)
    fixtures.append(BenchmarkFixture(
        name="overlapping_inset",
        description="Large panel containing an inset reaction shot with thick border",
        image_path=str(p4.resolve()),
        width=1200,
        height=1800,
        reading_direction="ltr",
        ground_truth=gt4,
    ))

    # -------------------------------------------------------------
    # 5. Full-Page Splash (1200 x 1800)
    # -------------------------------------------------------------
    p5 = output_dir / "05_full_page_splash.png"
    img5 = Image.new("RGB", (1200, 1800), (255, 255, 255))
    d5 = ImageDraw.Draw(img5)
    _draw_panel_content(d5, (40, 40, 1120, 1720), (210, 225, 240), (0, 0, 0), 5)
    gt5 = [GroundTruthBox(id="p5_1", x=40, y=40, width=1120, height=1720, sequence=1, panel_type="SPLASH")]
    img5.save(p5)
    fixtures.append(BenchmarkFixture(
        name="full_page_splash",
        description="Single dramatic splash illustration filling the entire page",
        image_path=str(p5.resolve()),
        width=1200,
        height=1800,
        reading_direction="ltr",
        ground_truth=gt5,
    ))

    # -------------------------------------------------------------
    # 6. Borderless Panels (1200 x 1800)
    # -------------------------------------------------------------
    p6 = output_dir / "06_borderless_panels.png"
    img6 = Image.new("RGB", (1200, 1800), (255, 255, 255))
    d6 = ImageDraw.Draw(img6)
    # 3 panels defined solely by white gutters (no black stroke)
    gt6_boxes = [
        (60, 60, 1080, 520),
        (60, 640, 510, 1100),
        (630, 640, 510, 1100),
    ]
    gt6 = []
    colors = [(200, 215, 235), (235, 210, 210), (210, 235, 215)]
    for idx, (x, y, w, h) in enumerate(gt6_boxes, start=1):
        d6.rectangle([x, y, x + w, y + h], fill=colors[idx-1])
        # Add artwork within panel
        d6.ellipse([x + 50, y + 50, x + w - 50, y + h - 50], fill=(max(0, colors[idx-1][0]-40), max(0, colors[idx-1][1]-40), max(0, colors[idx-1][2]-40)))
        gt6.append(GroundTruthBox(id=f"p6_{idx}", x=x, y=y, width=w, height=h, sequence=idx, panel_type="BORDERLESS"))
    img6.save(p6)
    fixtures.append(BenchmarkFixture(
        name="borderless_panels",
        description="Panels without black border strokes, segmented purely by whitespace gutters",
        image_path=str(p6.resolve()),
        width=1200,
        height=1800,
        reading_direction="ltr",
        ground_truth=gt6,
    ))

    # -------------------------------------------------------------
    # 7. Grayscale Manga (1200 x 1800)
    # -------------------------------------------------------------
    p7 = output_dir / "07_grayscale_manga.png"
    img7 = Image.new("L", (1200, 1800), 255)
    d7 = ImageDraw.Draw(img7)
    gt7_boxes = [
        (60, 60, 510, 780),
        (630, 60, 510, 780),
        (60, 900, 1080, 840),
    ]
    gt7 = []
    shades = [200, 170, 220]
    for idx, (x, y, w, h) in enumerate(gt7_boxes, start=1):
        d7.rectangle([x, y, x + w, y + h], fill=shades[idx-1], outline=0, width=4)
        d7.ellipse([x + 60, y + 60, x + w - 60, y + h - 60], fill=max(0, shades[idx-1] - 50))
        gt7.append(GroundTruthBox(id=f"p7_{idx}", x=x, y=y, width=w, height=h, sequence=idx))
    img7.save(p7)
    fixtures.append(BenchmarkFixture(
        name="grayscale_manga",
        description="Grayscale tones and halftone-like aesthetic",
        image_path=str(p7.resolve()),
        width=1200,
        height=1800,
        reading_direction="ltr",
        ground_truth=gt7,
    ))

    # -------------------------------------------------------------
    # 8. Colored Western Comic (1200 x 1800)
    # -------------------------------------------------------------
    p8 = output_dir / "08_colored_western_comic.png"
    img8 = Image.new("RGB", (1200, 1800), (255, 255, 255))
    d8 = ImageDraw.Draw(img8)
    gt8_boxes = [
        (60, 60, 1080, 500),
        (60, 620, 510, 560),
        (630, 620, 510, 560),
        (60, 1240, 1080, 500),
    ]
    gt8 = []
    palettes = [(255, 120, 80), (80, 180, 240), (240, 220, 60), (160, 90, 220)]
    for idx, (x, y, w, h) in enumerate(gt8_boxes, start=1):
        _draw_panel_content(d8, (x, y, w, h), palettes[idx-1], (0, 0, 0), 4)
        gt8.append(GroundTruthBox(id=f"p8_{idx}", x=x, y=y, width=w, height=h, sequence=idx))
    img8.save(p8)
    fixtures.append(BenchmarkFixture(
        name="colored_western_comic",
        description="Vibrant colored 4-panel western superhero comic page",
        image_path=str(p8.resolve()),
        width=1200,
        height=1800,
        reading_direction="ltr",
        ground_truth=gt8,
    ))

    # -------------------------------------------------------------
    # 9. Narrow Vertical Panels (1200 x 1800)
    # -------------------------------------------------------------
    p9 = output_dir / "09_narrow_vertical.png"
    img9 = Image.new("RGB", (1200, 1800), (255, 255, 255))
    d9 = ImageDraw.Draw(img9)
    # 3 tall narrow panels side-by-side in upper tier, 1 wide footer panel
    gt9_boxes = [
        (60, 60, 320, 1000),
        (440, 60, 320, 1000),
        (820, 60, 320, 1000),
        (60, 1120, 1080, 620),
    ]
    gt9 = []
    for idx, (x, y, w, h) in enumerate(gt9_boxes, start=1):
        _draw_panel_content(d9, (x, y, w, h), (225, 230, 245), (0, 0, 0), 4)
        gt9.append(GroundTruthBox(id=f"p9_{idx}", x=x, y=y, width=w, height=h, sequence=idx))
    img9.save(p9)
    fixtures.append(BenchmarkFixture(
        name="narrow_vertical",
        description="Three tall narrow vertical panels side-by-side plus wide footer",
        image_path=str(p9.resolve()),
        width=1200,
        height=1800,
        reading_direction="ltr",
        ground_truth=gt9,
    ))

    # -------------------------------------------------------------
    # 10. Extremely Tall Webtoon (1440 x 12000)
    # -------------------------------------------------------------
    p10 = output_dir / "10_tall_webtoon.png"
    img10 = Image.new("RGB", (1440, 12000), (255, 255, 255))
    d10 = ImageDraw.Draw(img10)
    # 6 floating webtoon panels separated by generous vertical gutters
    gt10_boxes = [
        (120, 300, 1200, 1400),
        (120, 2100, 1200, 1600),
        (120, 4100, 1200, 1500),
        (120, 6000, 1200, 1700),
        (120, 8100, 1200, 1500),
        (120, 10000, 1200, 1600),
    ]
    gt10 = []
    wt_colors = [
        (220, 235, 255),
        (255, 235, 220),
        (230, 255, 230),
        (250, 225, 255),
        (220, 245, 245),
        (255, 245, 220),
    ]
    for idx, (x, y, w, h) in enumerate(gt10_boxes, start=1):
        _draw_panel_content(d10, (x, y, w, h), wt_colors[idx-1], (0, 0, 0), 4)
        gt10.append(GroundTruthBox(id=f"p10_{idx}", x=x, y=y, width=w, height=h, sequence=idx, panel_type="WEBTOON_SEGMENT"))
    img10.save(p10)
    fixtures.append(BenchmarkFixture(
        name="tall_webtoon",
        description="Extremely tall webtoon vertical scrolling format (1440x12000px)",
        image_path=str(p10.resolve()),
        width=1440,
        height=12000,
        reading_direction="vertical",
        profile="WEBTOON",
        ground_truth=gt10,
    ))

    # -------------------------------------------------------------
    # 11. Intentionally Ambiguous Page (1200 x 1800)
    # -------------------------------------------------------------
    p11 = output_dir / "11_intentionally_ambiguous.png"
    img11 = Image.new("RGB", (1200, 1800), (255, 255, 255))
    d11 = ImageDraw.Draw(img11)
    # 3 standard panels and 1 panel with an open/broken right border bleeding into gutter
    gt11_boxes = [
        (60, 60, 1080, 480),
        (60, 580, 510, 540),
        (630, 580, 510, 540),
        (60, 1180, 1080, 560),
    ]
    gt11 = []
    for idx, (x, y, w, h) in enumerate(gt11_boxes, start=1):
        _draw_panel_content(d11, (x, y, w, h), (240, 235, 240), (0, 0, 0), 4)
        gt11.append(GroundTruthBox(id=f"p11_{idx}", x=x, y=y, width=w, height=h, sequence=idx))
    # Erase part of right border of panel 2 to simulate bleed
    d11.rectangle([568, 650, 574, 800], fill=(255, 255, 255))
    img11.save(p11)
    fixtures.append(BenchmarkFixture(
        name="intentionally_ambiguous",
        description="Layout with broken/bleeding panel border to test tolerance",
        image_path=str(p11.resolve()),
        width=1200,
        height=1800,
        reading_direction="ltr",
        ground_truth=gt11,
    ))

    # -------------------------------------------------------------
    # 12. Mixed Panel Sizes (1200 x 1800)
    # -------------------------------------------------------------
    p12 = output_dir / "12_mixed_sizes.png"
    img12 = Image.new("RGB", (1200, 1800), (255, 255, 255))
    d12 = ImageDraw.Draw(img12)
    # Row 1: 1 large heroic panel (65% width) + 1 small tall panel (35% width)
    # Row 2: 2 equal square panels
    # Row 3: 1 wide cinematic footer panel
    gt12_boxes = [
        (60, 60, 680, 600),
        (780, 60, 360, 600),
        (60, 700, 510, 480),
        (630, 700, 510, 480),
        (60, 1220, 1080, 520),
    ]
    gt12 = []
    mix_colors = [(240, 220, 210), (210, 230, 245), (225, 245, 225), (245, 245, 215), (235, 225, 245)]
    for idx, (x, y, w, h) in enumerate(gt12_boxes, start=1):
        _draw_panel_content(d12, (x, y, w, h), mix_colors[idx-1], (0, 0, 0), 4)
        gt12.append(GroundTruthBox(id=f"p12_{idx}", x=x, y=y, width=w, height=h, sequence=idx))
    img12.save(p12)
    fixtures.append(BenchmarkFixture(
        name="mixed_sizes",
        description="Dynamic multi-tier layout with mixed aspect ratios and sizes",
        image_path=str(p12.resolve()),
        width=1200,
        height=1800,
        reading_direction="ltr",
        ground_truth=gt12,
    ))

    return fixtures
