import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.database.session import SessionLocal
from engine.database.models import ProjectRecord

db = SessionLocal()
p = db.query(ProjectRecord).filter(ProjectRecord.id == 'a4e8115d-1e24-4a23-88b5-ecc72941bc8f').first()
scenes = p.settings.get('story_editor_state', {}).get('scenes', [])
for i, s in enumerate(scenes):
    for ly in s.get('layers', []):
        preset = ly.get('motion_preset')
        print(f"Scene {i+1} ({s.get('id')}): {preset}")
