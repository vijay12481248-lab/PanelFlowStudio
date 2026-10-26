import sys, os
sys.path.insert(0, '.')
from PIL import Image
from engine.database.session import SessionLocal
from engine.database.models import PanelRecord, TextRegionRecord, ProjectRecord

PROJECT_ID = '67e096cc-2e4f-4f40-9bb9-b6f99c297a9e'
ws = r'C:\Users\Vijaya sekhar\AppData\Local\PanelFlow Studio\projects\67e096cc-2e4f-4f40-9bb9-b6f99c297a9e\panels'

db = SessionLocal()
proj = db.query(ProjectRecord).filter(ProjectRecord.id == PROJECT_ID).first()
state = (proj.settings or {}).get('story_editor_state', {})
scenes = state.get('scenes', [])
clips = state.get('narration_clips', [])

panels = db.query(PanelRecord).filter(PanelRecord.project_id == PROJECT_ID).order_by(PanelRecord.sequence.asc()).all()
panel_by_id = {p.id: p for p in panels}
panel_by_seq = {p.sequence: p for p in panels}

print(f"Total scenes: {len(scenes)}, Total clips: {len(clips)}, Total panels: {len(panels)}")

for sc_idx, sc in enumerate(scenes):
    sc_id = sc.get('id')
    sc_dur = sc.get('duration_sec')
    sc_start = sc.get('start_time_sec')
    sc_clips = [c for c in clips if c.get('scene_id') == sc_id]
    layers = sc.get('layers', [])
    print(f"\n==========================================")
    print(f"SCENE {sc_idx+1} [{sc_id}]: start={sc_start}s, dur={sc_dur}s, {len(layers)} layers, {len(sc_clips)} clips")
    print(f"==========================================")
    print("CLIPS:")
    for c_idx, c in enumerate(sc_clips):
        c_start = c.get('start_time_sec')
        c_dur = c.get('duration_sec')
        print(f"  [{c_idx+1}] {c.get('id')} ({c_start:.2f}s - {c_start+c_dur:.2f}s, dur={c_dur:.2f}s) {c.get('speaker')}: \"{c.get('text')[:60]}...\"")
    print("\nLAYERS:")
    for l_idx, l in enumerate(layers):
        pid = l.get('source_panel_id')
        p = panel_by_id.get(pid)
        t_regs = db.query(TextRegionRecord).filter(TextRegionRecord.panel_id == pid).all() if p else []
        txt = " // ".join([(t.corrected_text or t.raw_text or "").replace('\n', ' ') for t in t_regs if (t.corrected_text or t.raw_text)])
        print(f"  [L{l_idx+1}] Seq {p.sequence if p else '?'}: start_offset={l.get('start_offset_sec')}s, dur={l.get('duration_sec')}s | text: \"{txt[:60]}...\"")

db.close()
