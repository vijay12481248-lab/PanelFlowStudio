import sys, os, shutil
sys.path.insert(0, '.')
from pathlib import Path
from PIL import Image, ImageDraw
import numpy as np

from engine.database.session import SessionLocal
from engine.database.models import PanelRecord

PROJECT_ID = '67e096cc-2e4f-4f40-9bb9-b6f99c297a9e'
ws = Path(r"C:\Users\Vijaya sekhar\AppData\Local\PanelFlow Studio\projects\67e096cc-2e4f-4f40-9bb9-b6f99c297a9e")
panels_dir = ws / "panels"
backup_dir = ws / "panels_backup"

backup_dir.mkdir(exist_ok=True)
print(f"Backing up panels to {backup_dir}...")
for f in panels_dir.glob("*.jpg"):
    dest = backup_dir / f.name
    if not dest.exists():
        shutil.copy2(f, dest)

db = SessionLocal()

# 1. Seq 01
p1 = db.query(PanelRecord).filter(PanelRecord.project_id == PROJECT_ID, PanelRecord.sequence == 1).first()
im1 = Image.open(backup_dir / p1.crop_filename)
# crop top 1760
im1_clean = im1.crop((0, 0, 1920, 1760))
im1_clean.save(panels_dir / p1.crop_filename, quality=95)
p1.width, p1.height = im1_clean.size
print(f"Seq 01 cleaned: new size {im1_clean.size}")

# 2. Seq 05
p5 = db.query(PanelRecord).filter(PanelRecord.project_id == PROJECT_ID, PanelRecord.sequence == 5).first()
im5 = Image.open(backup_dir / p5.crop_filename)
# crop top 300 to remove ad banner
im5_crop = im5.crop((0, 300, 1920, 12106))
# fill margin watermark at y=7345-300=7045
draw5 = ImageDraw.Draw(im5_crop)
draw5.rectangle([0, 7045, 605, 7110], fill=(252, 252, 252))
im5_crop.save(panels_dir / p5.crop_filename, quality=95)
p5.width, p5.height = im5_crop.size
print(f"Seq 05 cleaned: new size {im5_crop.size}")

# 3. Seq 06
p6 = db.query(PanelRecord).filter(PanelRecord.project_id == PROJECT_ID, PanelRecord.sequence == 6).first()
im6 = Image.open(backup_dir / p6.crop_filename)
im6_clean = im6.copy()
draw6 = ImageDraw.Draw(im6_clean)
draw6.rectangle([1300, 5830, 1920, 6000], fill=(229, 230, 230))
im6_clean.save(panels_dir / p6.crop_filename, quality=95)
p6.width, p6.height = im6_clean.size
print(f"Seq 06 cleaned: new size {im6_clean.size}")

# 4. Seq 09
p9 = db.query(PanelRecord).filter(PanelRecord.project_id == PROJECT_ID, PanelRecord.sequence == 9).first()
im9 = Image.open(backup_dir / p9.crop_filename)
im9_clean = im9.crop((0, 180, 1920, 3940))
im9_clean.save(panels_dir / p9.crop_filename, quality=95)
p9.width, p9.height = im9_clean.size
print(f"Seq 09 cleaned: new size {im9_clean.size}")

# 5. Seq 15
p15 = db.query(PanelRecord).filter(PanelRecord.project_id == PROJECT_ID, PanelRecord.sequence == 15).first()
im15 = Image.open(backup_dir / p15.crop_filename)
im15_clean = im15.crop((0, 0, 1867, 3400))
im15_clean.save(panels_dir / p15.crop_filename, quality=95)
p15.width, p15.height = im15_clean.size
print(f"Seq 15 cleaned: new size {im15_clean.size}")

# 6. Seq 18
p18 = db.query(PanelRecord).filter(PanelRecord.project_id == PROJECT_ID, PanelRecord.sequence == 18).first()
im18 = Image.open(backup_dir / p18.crop_filename)
im18_clean = im18.copy()
draw18 = ImageDraw.Draw(im18_clean)
draw18.rectangle([1230, 750, 1847, 900], fill=(250, 250, 249))
im18_clean.save(panels_dir / p18.crop_filename, quality=95)
p18.width, p18.height = im18_clean.size
print(f"Seq 18 cleaned: new size {im18_clean.size}")

# 7. Seq 26
p26 = db.query(PanelRecord).filter(PanelRecord.project_id == PROJECT_ID, PanelRecord.sequence == 26).first()
im26 = Image.open(backup_dir / p26.crop_filename)
im26_clean = im26.crop((0, 0, 1763, 2585))
im26_clean.save(panels_dir / p26.crop_filename, quality=95)
p26.width, p26.height = im26_clean.size
print(f"Seq 26 cleaned: new size {im26_clean.size}")

# 8. Seq 29
p29 = db.query(PanelRecord).filter(PanelRecord.project_id == PROJECT_ID, PanelRecord.sequence == 29).first()
im29 = Image.open(backup_dir / p29.crop_filename)
im29_clean = im29.copy()
draw29 = ImageDraw.Draw(im29_clean)
draw29.rectangle([1000, 3460, 1615, 3620], fill=(254, 254, 254))
im29_clean.save(panels_dir / p29.crop_filename, quality=95)
p29.width, p29.height = im29_clean.size
print(f"Seq 29 cleaned: new size {im29_clean.size}")

# 9. Seq 39
p39 = db.query(PanelRecord).filter(PanelRecord.project_id == PROJECT_ID, PanelRecord.sequence == 39).first()
im39 = Image.open(backup_dir / p39.crop_filename)
partA = im39.crop((0, 0, 1920, 895))
partB = im39.crop((0, 1215, 1920, 4413))
gutter_h = 20
total_h = partA.height + gutter_h + partB.height
im39_clean = Image.new('RGB', (1920, total_h), color=(255, 255, 255))
im39_clean.paste(partA, (0, 0))
im39_clean.paste(partB, (0, partA.height + gutter_h))
im39_clean.save(panels_dir / p39.crop_filename, quality=95)
p39.width, p39.height = im39_clean.size
print(f"Seq 39 cleaned: new size {im39_clean.size}")

db.commit()
db.close()
print("All target panels successfully cleaned and database dimensions updated!")
