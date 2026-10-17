"""Generates 10 synthetic manga/comic/webtoon fixtures with ground truth annotations.

All fixtures are procedurally generated with Pillow; no copyrighted assets are used.
"""

import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "synthetic"

def save_fixture(name: str, img: Image.Image, reading_direction: str, panels: list[dict]):
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    img_path = FIXTURES_DIR / f"{name}.png"
    json_path = FIXTURES_DIR / f"{name}.json"

    img.save(img_path, "PNG")

    # Add normalized coordinates to ground truth
    w, h = img.size
    enriched_panels = []
    for idx, p in enumerate(panels, start=1):
        enriched_panels.append({
            "id": p.get("id", f"p{idx}"),
            "sequence": idx,
            "x": p["x"],
            "y": p["y"],
            "width": p["width"],
            "height": p["height"],
            "normalized_x": round(p["x"] / float(w), 4),
            "normalized_y": round(p["y"] / float(h), 4),
            "normalized_width": round(p["width"] / float(w), 4),
            "normalized_height": round(p["height"] / float(h), 4),
            "panel_type": p.get("panel_type", "STANDARD"),
        })

    gt_data = {
        "layout_name": name,
        "width": w,
        "height": h,
        "reading_direction": reading_direction,
        "panels": enriched_panels,
    }

    json_path.write_text(json.dumps(gt_data, indent=2))
    print(f"Generated fixture: {name} ({w}x{h}, {len(panels)} panels)")

def create_01_simple_2x2_grid():
    w, h = 1200, 1600
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # 4 equal panels with 40px gutters
    p_w, p_h = 520, 680
    panels = [
        {"x": 60, "y": 60, "width": p_w, "height": p_h, "id": "p1"},
        {"x": 620, "y": 60, "width": p_w, "height": p_h, "id": "p2"},
        {"x": 60, "y": 780, "width": p_w, "height": p_h, "id": "p3"},
        {"x": 620, "y": 780, "width": p_w, "height": p_h, "id": "p4"},
    ]

    for idx, p in enumerate(panels, start=1):
        draw.rectangle([p["x"], p["y"], p["x"] + p["width"], p["y"] + p["height"]], fill=(240, 240, 245), outline=(20, 20, 20), width=4)
        draw.text((p["x"] + 20, p["y"] + 20), f"Panel {idx}", fill=(50, 50, 50))

    save_fixture("01_simple_2x2_grid", img, "ltr", panels)

def create_02_manga_rtl():
    w, h = 1200, 1800
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Manga RTL reading: top-right -> top-left -> bottom-right -> bottom-left
    panels = [
        {"x": 620, "y": 50, "width": 530, "height": 780, "id": "p1"},
        {"x": 50, "y": 50, "width": 530, "height": 780, "id": "p2"},
        {"x": 620, "y": 870, "width": 530, "height": 870, "id": "p3"},
        {"x": 50, "y": 870, "width": 530, "height": 870, "id": "p4"},
    ]

    for idx, p in enumerate(panels, start=1):
        draw.rectangle([p["x"], p["y"], p["x"] + p["width"], p["y"] + p["height"]], fill=(245, 245, 245), outline=(0, 0, 0), width=5)
        draw.text((p["x"] + 30, p["y"] + 30), f"Manga Panel #{idx} (RTL)", fill=(0, 0, 0))

    save_fixture("02_manga_rtl", img, "rtl", panels)

def create_03_irregular_panels():
    w, h = 1200, 1600
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # 3 irregular panels: top wide, middle left, middle right
    panels = [
        {"x": 50, "y": 50, "width": 1100, "height": 450, "id": "p1"},
        {"x": 50, "y": 540, "width": 450, "height": 1000, "id": "p2"},
        {"x": 540, "y": 540, "width": 610, "height": 1000, "id": "p3"},
    ]

    for idx, p in enumerate(panels, start=1):
        draw.rectangle([p["x"], p["y"], p["x"] + p["width"], p["y"] + p["height"]], fill=(235, 240, 245), outline=(15, 15, 15), width=4)
        draw.text((p["x"] + 25, p["y"] + 25), f"Irregular {idx}", fill=(30, 30, 30))

    save_fixture("03_irregular_panels", img, "ltr", panels)

def create_04_splash_panel():
    w, h = 1200, 1600
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Full splash page with margins
    panels = [
        {"x": 40, "y": 40, "width": 1120, "height": 1520, "panel_type": "SPLASH", "id": "p1"},
    ]
    p = panels[0]
    draw.rectangle([p["x"], p["y"], p["x"] + p["width"], p["y"] + p["height"]], fill=(220, 225, 235), outline=(0, 0, 0), width=6)
    draw.text((w // 2 - 100, h // 2), "DRAMATIC SPLASH PAGE", fill=(10, 10, 10))

    save_fixture("04_splash_panel", img, "ltr", panels)

def create_05_nested_inset():
    w, h = 1200, 1600
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Big primary panel with inset sub-panel
    panels = [
        {"x": 50, "y": 50, "width": 1100, "height": 1500, "panel_type": "STANDARD", "id": "p1"},
        {"x": 650, "y": 950, "width": 450, "height": 550, "panel_type": "INSET", "id": "p2"},
    ]
    # Draw primary
    p1 = panels[0]
    draw.rectangle([p1["x"], p1["y"], p1["x"] + p1["width"], p1["y"] + p1["height"]], fill=(230, 235, 240), outline=(20, 20, 20), width=5)
    # Draw inset
    p2 = panels[1]
    draw.rectangle([p2["x"], p2["y"], p2["x"] + p2["width"], p2["y"] + p2["height"]], fill=(255, 255, 255), outline=(180, 20, 20), width=6)
    draw.text((p2["x"] + 20, p2["y"] + 20), "INSET PANEL", fill=(180, 20, 20))

    save_fixture("05_nested_inset", img, "ltr", panels)

def create_06_borderless_panel():
    w, h = 1200, 1600
    # White background acting as gutters
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # 3 borderless panels with filled distinct colored areas
    panels = [
        {"x": 60, "y": 60, "width": 1080, "height": 450, "panel_type": "BORDERLESS", "id": "p1"},
        {"x": 60, "y": 550, "width": 520, "height": 990, "panel_type": "BORDERLESS", "id": "p2"},
        {"x": 620, "y": 550, "width": 520, "height": 990, "panel_type": "BORDERLESS", "id": "p3"},
    ]

    colors = [(200, 215, 230), (220, 205, 215), (210, 225, 210)]
    for idx, (p, col) in enumerate(zip(panels, colors), start=1):
        # No outline! Borderless!
        draw.rectangle([p["x"], p["y"], p["x"] + p["width"], p["y"] + p["height"]], fill=col)
        draw.text((p["x"] + 30, p["y"] + 30), f"Borderless Panel #{idx}", fill=(40, 40, 40))

    save_fixture("06_borderless_panel", img, "ltr", panels)

def create_07_webtoon_tall():
    # Long vertical strip
    w, h = 1000, 4800
    img = Image.new("RGB", (w, h), (250, 250, 250))
    draw = ImageDraw.Draw(img)

    # 4 vertically stacked panels separated by large webtoon gutters
    panels = [
        {"x": 80, "y": 150, "width": 840, "height": 950, "panel_type": "WEBTOON_SEGMENT", "id": "p1"},
        {"x": 80, "y": 1300, "width": 840, "height": 950, "panel_type": "WEBTOON_SEGMENT", "id": "p2"},
        {"x": 80, "y": 2450, "width": 840, "height": 950, "panel_type": "WEBTOON_SEGMENT", "id": "p3"},
        {"x": 80, "y": 3600, "width": 840, "height": 950, "panel_type": "WEBTOON_SEGMENT", "id": "p4"},
    ]

    for idx, p in enumerate(panels, start=1):
        draw.rectangle([p["x"], p["y"], p["x"] + p["width"], p["y"] + p["height"]], fill=(230, 235, 245), outline=(30, 30, 30), width=4)
        draw.text((p["x"] + 40, p["y"] + 40), f"Webtoon Episode Beat #{idx}", fill=(30, 30, 30))

    save_fixture("07_webtoon_tall", img, "vertical", panels)

def create_08_grayscale_manga():
    w, h = 1200, 1800
    img = Image.new("L", (w, h), 255)
    draw = ImageDraw.Draw(img)

    # Grayscale 3-panel manga RTL layout
    panels = [
        {"x": 620, "y": 60, "width": 520, "height": 600, "id": "p1"},
        {"x": 60, "y": 60, "width": 520, "height": 600, "id": "p2"},
        {"x": 60, "y": 700, "width": 1080, "height": 1020, "id": "p3"},
    ]

    for idx, p in enumerate(panels, start=1):
        draw.rectangle([p["x"], p["y"], p["x"] + p["width"], p["y"] + p["height"]], fill=210, outline=0, width=5)
        draw.text((p["x"] + 30, p["y"] + 30), f"Manga Screen {idx} (Grayscale)", fill=0)

    save_fixture("08_grayscale_manga", img, "rtl", panels)

def create_09_colored_comic():
    w, h = 1200, 1600
    # Colored gutter (dark navy)
    img = Image.new("RGB", (w, h), (15, 23, 42))
    draw = ImageDraw.Draw(img)

    panels = [
        {"x": 50, "y": 50, "width": 530, "height": 700, "id": "p1"},
        {"x": 620, "y": 50, "width": 530, "height": 700, "id": "p2"},
        {"x": 50, "y": 790, "width": 1100, "height": 750, "id": "p3"},
    ]

    border_colors = [(244, 63, 94), (59, 130, 246), (16, 185, 129)]
    fill_colors = [(30, 27, 46), (23, 37, 84), (6, 78, 59)]
    for idx, (p, b_col, f_col) in enumerate(zip(panels, border_colors, fill_colors), start=1):
        draw.rectangle([p["x"], p["y"], p["x"] + p["width"], p["y"] + p["height"]], fill=f_col, outline=b_col, width=5)
        draw.text((p["x"] + 30, p["y"] + 30), f"Colored Comic Panel {idx}", fill=(240, 240, 240))

    save_fixture("09_colored_comic", img, "ltr", panels)

def create_10_ambiguous_layout():
    w, h = 1200, 1600
    # Ambiguous layout / subtle border or single page composition testing fallback
    img = Image.new("RGB", (w, h), (245, 245, 248))
    draw = ImageDraw.Draw(img)

    # Single full-bleed page art with faint gradient-like elements
    panels = [
        {"x": 0, "y": 0, "width": w, "height": h, "panel_type": "FULL_PAGE", "id": "p1"},
    ]
    draw.text((w // 2 - 120, h // 2), "Ambiguous / Full-Bleed Artwork", fill=(100, 100, 100))

    save_fixture("10_ambiguous_layout", img, "ltr", panels)

def generate_all():
    print(f"Generating 10 synthetic fixtures into {FIXTURES_DIR.resolve()}...")
    create_01_simple_2x2_grid()
    create_02_manga_rtl()
    create_03_irregular_panels()
    create_04_splash_panel()
    create_05_nested_inset()
    create_06_borderless_panel()
    create_07_webtoon_tall()
    create_08_grayscale_manga()
    create_09_colored_comic()
    create_10_ambiguous_layout()
    print("All 10 synthetic fixtures generated successfully.")

if __name__ == "__main__":
    generate_all()
