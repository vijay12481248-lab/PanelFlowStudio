from PIL import Image

from engine.imaging.panels import strip_detector as sd


def test_fuse_joins_pieces_of_a_tall_panel_seen_by_overlapping_windows():
    a = sd.StripBox("panel", [100, 1000, 800, 2840], 0.9, cut=True)   # window 0..3840 cuts it at the bottom
    b = sd.StripBox("panel", [105, 1920, 795, 3500], 0.8, cut=True)   # window 1920..5760 cuts it at the top
    other = sd.StripBox("panel", [100, 6000, 800, 600], 0.9)
    fused = sd.fuse([a, b, other])
    assert len(fused) == 2
    joined = min(fused, key=lambda f: f.box[1])
    assert joined.box[1] == 1000 and joined.box[1] + joined.box[3] == 5420


def test_fuse_keeps_touching_full_width_panels_apart():
    a = sd.StripBox("panel", [0, 1000, 1920, 2840], 0.9, cut=True)
    b = sd.StripBox("panel", [0, 3850, 1920, 1500], 0.9, cut=True)  # starts where a ends; different panel
    assert len(sd.fuse([a, b])) == 2


def test_truncated_box_dropped_when_neighbour_window_sees_it_whole():
    assert sd.visible_elsewhere([0, 2500, 1920, 1335], top=0, total=20000)      # bottom-cut, starts in next window
    assert not sd.visible_elsewhere([0, 500, 1920, 3335], top=0, total=20000)   # taller than a half window
    assert sd.visible_elsewhere([0, 1920, 1920, 1200], top=1920, total=20000)   # top-cut, ends in previous window


def test_page_panels_assigns_home_page_and_local_promos():
    pages = [sd.StripPage("p1", None, 0, 3000), sd.StripPage("p2", None, 3000, 3000)]
    result = sd.StripResult(pages=pages, panels=[sd.StripBox("panel", [0, 2500, 1920, 1000], 0.9)],
                            promos=[sd.StripBox("promo", [1400, 3300, 500, 140], 0.8)])
    [item] = sd.page_panels(result)
    assert item.page.page_id == "p1" and item.box == [0, 2500, 1920, 1000]
    assert item.promos == [[1400, 800, 500, 140]]


def test_crop_strip_stitches_across_pages(tmp_path):
    for name, colour in (("a", "red"), ("b", "blue")):
        Image.new("RGB", (100, 200), colour).save(tmp_path / f"{name}.png")
    pages = [sd.StripPage("a", tmp_path / "a.png", 0, 200), sd.StripPage("b", tmp_path / "b.png", 200, 200)]
    crop = sd.crop_strip(pages, [0, 150, 100, 100])
    assert crop.size == (100, 100)
    assert crop.getpixel((50, 10)) == (255, 0, 0) and crop.getpixel((50, 90)) == (0, 0, 255)


def test_gradient_shot_has_no_art_but_drawing_does():
    import numpy as np
    strip = np.repeat(np.linspace(0, 255, 400, dtype=np.uint8)[:, None, None], 200, axis=1).repeat(3, axis=2)
    assert not sd.has_art(strip, [0, 0, 200, 400], 1.0)
    strip[100:300, 50:150] = 0
    strip[150:250, 80:120] = 255
    assert sd.has_art(strip, [0, 0, 200, 400], 1.0)


def test_vertical_scroll_detection():
    assert sd.is_vertical_scroll([(1920, 3200), (1920, 3200), (1920, 459)])
    assert not sd.is_vertical_scroll([(1500, 2100), (1500, 2100)])
    assert not sd.is_vertical_scroll([(1920, 4000), (1800, 4000)])
