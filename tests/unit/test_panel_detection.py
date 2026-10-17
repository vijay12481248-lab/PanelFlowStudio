from pathlib import Path
from engine.imaging.panels.detector import ContourPanelDetector

def test_panel_detection_on_sample_comic(tmp_path: Path):
    sample_page = Path(__file__).parent.parent.parent / "fixtures" / "sample_comic" / "page_01.jpg"
    assert sample_page.exists(), f"Sample comic page not found at {sample_page}"

    detector = ContourPanelDetector()

    # 1. Test LTR Detection
    panels_ltr = detector.detect_panels(sample_page, reading_direction="ltr", page_id="page-1")
    assert len(panels_ltr) >= 3, f"Expected at least 3 panels, got {len(panels_ltr)}"

    # Panel 1 in LTR should be top-left (x < 600, y < 800)
    p1 = panels_ltr[0]
    assert p1.x < 500
    assert p1.y < 500

    # Panel 2 in LTR should be top-right (x > 500, y < 800)
    p2 = panels_ltr[1]
    assert p2.x > 500
    assert p2.y < 500

    # Panel 3 should be bottom (y > 700)
    p3 = panels_ltr[2]
    assert p3.y > 700

    # 2. Test RTL Detection (Manga reading order: top-right first, then top-left)
    panels_rtl = detector.detect_panels(sample_page, reading_direction="rtl", page_id="page-1")
    assert len(panels_rtl) >= 3

    # In RTL, panel 1 should be top-right
    p1_rtl = panels_rtl[0]
    assert p1_rtl.x > 500
    assert p1_rtl.y < 500

    # In RTL, panel 2 should be top-left
    p2_rtl = panels_rtl[1]
    assert p2_rtl.x < 500
    assert p2_rtl.y < 500

    # 3. Test Crop Extraction
    crop_dest = tmp_path / "panel_crop_01.jpg"
    crop_res = detector.extract_crop(sample_page, p1, crop_dest)
    assert crop_dest.exists()
    assert crop_res["width"] > 0
    assert crop_res["height"] > 0
    assert crop_res["byte_size"] > 0
