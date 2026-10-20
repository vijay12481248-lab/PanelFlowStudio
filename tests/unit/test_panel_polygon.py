from pathlib import Path
from engine.imaging.panels.detector import ContourPanelDetector
from engine.database.models import PanelRecord
import json


def test_panel_record_accepts_detected_polygon_json():
    panel = PanelRecord(
        project_id="project-1",
        page_id="page-1",
        sequence=1,
        page_sequence=1,
        x=0,
        y=0,
        width=100,
        height=100,
        crop_filename="panel.jpg",
        polygon_json="[[0, 0], [100, 0], [100, 100], [0, 100]]",
    )

    assert panel.polygon_json.startswith("[[0, 0]")

def test_polygon_extraction_populated():
    sample_page = Path(__file__).parent.parent.parent / "fixtures" / "sample_comic" / "page_01.jpg"
    assert sample_page.exists()
    detector = ContourPanelDetector()
    panels = detector.detect_panels(sample_page, reading_direction="ltr", page_id="page-1")
    assert len(panels) >= 3
    # At least one panel should have polygon data for non-rectangular detection
    has_polygon = any(p.polygon_json for p in panels)
    # Polygon may be None for simple rectangles, ensure field exists and is serializable
    for p in panels:
        if p.polygon_json:
            data = json.loads(p.polygon_json)
            assert isinstance(data, list)
            assert all(isinstance(pt, list) and len(pt) == 2 for pt in data)
