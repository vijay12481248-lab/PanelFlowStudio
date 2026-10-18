"""Tests for panel split, merge, reordering, and reading order operations."""

import pytest
from pathlib import Path
from PIL import Image

from engine.database.models import ProjectRecord, PageRecord, PanelRecord
from engine.projects.service import ProjectService
from engine.imaging.panels.base import PanelBox, PanelType, PanelStatus, ReadingDirection
from engine.imaging.panels.detector import ContourPanelDetector

@pytest.fixture
def test_db_session(tmp_path: Path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from engine.database.models import Base
    
    db_file = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_panel_split_horizontal_and_vertical(test_db_session, tmp_path: Path):
    service = ProjectService()
    
    # Setup test project and page
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "panels").mkdir()
    (ws / "source").mkdir()
    
    # Create fake page
    img = Image.new("RGB", (1000, 1000), (255, 255, 255))
    img.save(ws / "source" / "p1.jpg")
    
    proj = ProjectRecord(
        id="proj-1",
        title="Split Test",
        source_type="LOCAL_FOLDER",
        source_url=str(ws),
        workspace_path=str(ws),
        rights_status="PUBLIC_DOMAIN",
        current_stage="NORMALIZED",
    )
    test_db_session.add(proj)
    
    page = PageRecord(
        id="page-1",
        project_id="proj-1",
        sequence=1,
        filename="p1.jpg",
        width=1000,
        height=1000,
        sha256="fake",
        status="READY",
    )
    test_db_session.add(page)
    test_db_session.commit()
    
    # Add a panel
    panel = service.add_panel(test_db_session, "proj-1", "page-1", x=100, y=100, width=800, height=600)
    assert panel.width == 800
    assert panel.height == 600
    
    # 1. Test Horizontal Split (splits top and bottom)
    parts_h = service.split_panel(test_db_session, "proj-1", panel.id, split_type="horizontal", ratio=0.5)
    assert len(parts_h) == 2
    top, bottom = parts_h[0], parts_h[1]
    assert top.x == 100
    assert top.y == 100
    assert top.width == 800
    assert top.height == 300
    assert top.manually_modified is True
    
    assert bottom.x == 100
    assert bottom.y == 400
    assert bottom.width == 800
    assert bottom.height == 300
    assert bottom.manually_modified is True
    
    # 2. Test Vertical Split on the top panel (splits left and right)
    parts_v = service.split_panel(test_db_session, "proj-1", top.id, split_type="vertical", ratio=0.25)
    # Returns all panels on page: the 2 new vertical halves + bottom panel
    assert len(parts_v) == 3
    left = [p for p in parts_v if p.x == 100 and p.y == 100][0]
    assert left.width == 200
    assert left.height == 300
    
    right = [p for p in parts_v if p.x == 300 and p.y == 100][0]
    assert right.width == 600
    assert right.height == 300

def test_panel_merge(test_db_session, tmp_path: Path):
    service = ProjectService()
    ws = tmp_path / "workspace_merge"
    ws.mkdir()
    (ws / "panels").mkdir()
    (ws / "source").mkdir()
    
    img = Image.new("RGB", (1000, 1000), (255, 255, 255))
    img.save(ws / "source" / "m.jpg")
    
    proj = ProjectRecord(
        id="proj-merge",
        title="Merge Test",
        source_type="LOCAL_FOLDER",
        source_url=str(ws),
        workspace_path=str(ws),
        rights_status="PUBLIC_DOMAIN",
        current_stage="NORMALIZED",
    )
    test_db_session.add(proj)
    page = PageRecord(
        id="page-m",
        project_id="proj-merge",
        sequence=1,
        filename="m.jpg",
        width=1000,
        height=1000,
        sha256="fake",
        status="READY",
    )
    test_db_session.add(page)
    test_db_session.commit()
    
    p1 = service.add_panel(test_db_session, "proj-merge", "page-m", x=50, y=50, width=400, height=300)
    p2 = service.add_panel(test_db_session, "proj-merge", "page-m", x=500, y=50, width=400, height=300)
    
    all_panels = service.list_panels(test_db_session, "proj-merge")
    assert len(all_panels) == 2
    
    # Merge p1 and p2 into a single bounding box
    merged = service.merge_panels(test_db_session, "proj-merge", [p1.id, p2.id])
    assert merged.x == 50
    assert merged.y == 50
    assert merged.width == 850  # from x=50 to x=900
    assert merged.height == 300
    assert merged.manually_modified is True
    assert merged.panel_type == "STANDARD"
    
    remaining = service.list_panels(test_db_session, "proj-merge")
    assert len(remaining) == 1
    assert remaining[0].id == merged.id

def test_reading_order_sorting():
    detector = ContourPanelDetector()
    
    # 4 panels:
    # Row 1: Top-Left (50, 50), Top-Right (550, 50)
    # Row 2: Bottom-Left (50, 550), Bottom-Right (550, 550)
    boxes = [
        (550, 50, 400, 400, 0.9, "STANDARD"),   # Top-Right
        (50, 550, 400, 400, 0.9, "STANDARD"),   # Bottom-Left
        (50, 50, 400, 400, 0.9, "STANDARD"),    # Top-Left
        (550, 550, 400, 400, 0.9, "STANDARD"),  # Bottom-Right
    ]
    
    # 1. LTR Order (Left to right, top to bottom)
    ltr = detector._sort_reading_order(boxes, page_h=1000, reading_direction="ltr")
    assert [(b[0], b[1]) for b in ltr] == [
        (50, 50),    # Top-Left
        (550, 50),   # Top-Right
        (50, 550),   # Bottom-Left
        (550, 550),  # Bottom-Right
    ]
    
    # 2. RTL Order (Right to left, top to bottom)
    rtl = detector._sort_reading_order(boxes, page_h=1000, reading_direction="rtl")
    assert [(b[0], b[1]) for b in rtl] == [
        (550, 50),   # Top-Right
        (50, 50),    # Top-Left
        (550, 550),  # Bottom-Right
        (50, 550),   # Bottom-Left
    ]
    
    # 3. Vertical Order (Top to bottom)
    vert = detector._sort_reading_order(boxes, page_h=1000, reading_direction="vertical")
    assert [(b[0], b[1]) for b in vert] == [
        (50, 50),
        (550, 50),
        (50, 550),
        (550, 550),
    ]

def test_delete_panel(test_db_session, tmp_path: Path):
    from engine.database.models import TextRegionRecord, OCRRecord
    service = ProjectService()
    ws = tmp_path / "workspace_delete"
    ws.mkdir()
    (ws / "panels").mkdir()
    (ws / "source").mkdir()

    img = Image.new("RGB", (1000, 1000), (255, 255, 255))
    img.save(ws / "source" / "p1.jpg")

    proj = ProjectRecord(
        id="proj-del",
        title="Delete Test",
        source_type="LOCAL_FOLDER",
        source_url=str(ws),
        workspace_path=str(ws),
        rights_status="PUBLIC_DOMAIN",
        current_stage="NORMALIZED",
    )
    test_db_session.add(proj)

    page = PageRecord(
        id="page-del",
        project_id="proj-del",
        sequence=1,
        filename="p1.jpg",
        width=1000,
        height=1000,
        sha256="fake_sha",
        status="READY",
    )
    test_db_session.add(page)
    test_db_session.commit()

    p1 = service.add_panel(test_db_session, "proj-del", "page-del", x=10, y=10, width=200, height=200)
    p2 = service.add_panel(test_db_session, "proj-del", "page-del", x=10, y=250, width=200, height=200)
    assert p1.sequence == 1
    assert p2.sequence == 2

    # Add text region to p1
    tr = TextRegionRecord(
        id="tr-1",
        project_id="proj-del",
        page_id="page-del",
        panel_id=p1.id,
        x=20, y=20, width=50, height=30,
        raw_text="Hello",
        corrected_text="Hello",
    )
    test_db_session.add(tr)
    test_db_session.commit()

    # Delete p1
    service.delete_panel(test_db_session, "proj-del", p1.id)

    # p1 should be deleted, p2 resequenced to 1
    remaining = test_db_session.query(PanelRecord).filter(PanelRecord.project_id == "proj-del").all()
    assert len(remaining) == 1
    assert remaining[0].id == p2.id
    assert remaining[0].sequence == 1

    # Text region should also be cleaned up
    tr_check = test_db_session.query(TextRegionRecord).filter(TextRegionRecord.id == "tr-1").first()
    assert tr_check is None

