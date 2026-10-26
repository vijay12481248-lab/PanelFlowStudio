import os, sys, shutil, uuid
sys.path.insert(0, '.')
from pathlib import Path
from engine.database.session import SessionLocal
from engine.database.models import ProjectRecord, PageRecord, PanelRecord, TextRegionRecord
from engine.projects.service import project_service

p1_id = '67e096cc-2e4f-4f40-9bb9-b6f99c297a9e'
p2_id = '682ba959-24e8-41d8-9cda-637a350b75c2'

p1_ws = Path(r"C:\Users\Vijaya sekhar\AppData\Local\PanelFlow Studio\projects\67e096cc-2e4f-4f40-9bb9-b6f99c297a9e")
p2_ws = Path(r"C:\Users\Vijaya sekhar\AppData\Local\PanelFlow Studio\projects\682ba959-24e8-41d8-9cda-637a350b75c2")

db = SessionLocal()

# Build page mapping
p1_pages = {p.sequence: p.id for p in db.query(PageRecord).filter_by(project_id=p1_id).all()}
p2_pages = {p.id: p.sequence for p in db.query(PageRecord).filter_by(project_id=p2_id).all()}

print(f"Mapping {len(p2_pages)} pages from P2 to P1...")

# Copy panel files
p1_panels_dir = p1_ws / "panels"
p2_panels_dir = p2_ws / "panels"
p1_panels_dir.mkdir(parents=True, exist_ok=True)

# Delete existing text regions and panels in P1
db.query(TextRegionRecord).filter(TextRegionRecord.project_id == p1_id).delete(synchronize_session=False)
db.query(PanelRecord).filter(PanelRecord.project_id == p1_id).delete(synchronize_session=False)
db.commit()
print("Cleared old P1 panels and text regions.")

# Fetch P2 panels
p2_panels = db.query(PanelRecord).filter_by(project_id=p2_id).order_by(PanelRecord.sequence.asc()).all()
p2_to_p1_panel_id = {}

for p2_p in p2_panels:
    p2_page_seq = p2_pages[p2_p.page_id]
    p1_page_id = p1_pages[p2_page_seq]
    new_panel_id = str(uuid.uuid4())
    p2_to_p1_panel_id[p2_p.id] = new_panel_id
    
    crop_filename = f"panel_{new_panel_id}.jpg"
    
    new_p = PanelRecord(
        id=new_panel_id,
        project_id=p1_id,
        page_id=p1_page_id,
        sequence=p2_p.sequence,
        page_sequence=p2_p.page_sequence,
        x=p2_p.x,
        y=p2_p.y,
        width=p2_p.width,
        height=p2_p.height,
        normalized_x=p2_p.normalized_x,
        normalized_y=p2_p.normalized_y,
        normalized_width=p2_p.normalized_width,
        normalized_height=p2_p.normalized_height,
        polygon_json=p2_p.polygon_json,
        crop_filename=crop_filename,
        reading_direction=p2_p.reading_direction,
        detection_method=p2_p.detection_method,
        confidence=p2_p.confidence,
        panel_type=p2_p.panel_type,
        status=p2_p.status,
        manually_modified=False,
        created_at=p2_p.created_at,
        updated_at=p2_p.updated_at,
    )
    db.add(new_p)
    
    # Copy crop image
    src_file = p2_panels_dir / p2_p.crop_filename
    dst_file = p1_panels_dir / crop_filename
    if src_file.exists():
        shutil.copy2(src_file, dst_file)
    else:
        print(f"Warning: src crop {src_file} missing!")

db.commit()
print(f"Copied {len(p2_panels)} panels to P1.")

# Fetch P2 text regions
p2_texts = db.query(TextRegionRecord).filter_by(project_id=p2_id).all()
for t in p2_texts:
    p2_page_seq = p2_pages.get(t.page_id, 1)
    p1_page_id = p1_pages.get(p2_page_seq)
    new_panel_id = p2_to_p1_panel_id.get(t.panel_id)
    new_text_id = str(uuid.uuid4())
    
    col_dict = {col.name: getattr(t, col.name) for col in TextRegionRecord.__table__.columns}
    col_dict['id'] = new_text_id
    col_dict['project_id'] = p1_id
    col_dict['page_id'] = p1_page_id
    col_dict['panel_id'] = new_panel_id
    
    new_t = TextRegionRecord(**col_dict)
    db.add(new_t)

db.commit()
print(f"Copied {len(p2_texts)} text regions to P1.")

project_service._sync_panels_json(db, p1_id)
print("Synced panels.json for P1.")
db.close()
