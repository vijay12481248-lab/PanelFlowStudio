import sys, os, json
sys.path.insert(0, '.')
from pathlib import Path
from engine.database.session import SessionLocal
from engine.database.models import ProjectRecord, PanelRecord
from engine.render.compiler import timeline_compiler

PROJECT_ID = '67e096cc-2e4f-4f40-9bb9-b6f99c297a9e'
ws = Path(r"C:\Users\Vijaya sekhar\AppData\Local\PanelFlow Studio\projects\67e096cc-2e4f-4f40-9bb9-b6f99c297a9e")

OMITTED_PANEL_IDS = {
    '65890491-dd5e-43dc-84ab-5e91cb36fccf',  # Seq 12 (READ banner)
    '4ad19529-e4d4-4d49-bc8b-9e2edf7d1340',  # Seq 20 (FASTER RELEASE banner)
    'c78ba66d-69b0-4fa7-9a29-246986405e08',  # Seq 37 (READ banner)
    '9ec39c91-0f40-4a05-b808-20fd9028d802',  # Seq 42 (Discord recruitment card)
}

db = SessionLocal()
proj = db.query(ProjectRecord).filter(ProjectRecord.id == PROJECT_ID).first()
settings = dict(proj.settings or {})
state = dict(settings.get('story_editor_state', {}))

scenes = state.get('scenes', [])
print(f"Loaded {len(scenes)} scenes from story_editor_state.")

for s_idx, scene in enumerate(scenes):
    s_id = scene.get('id')
    scene_dur = float(scene.get('duration_sec', 0.0))
    orig_layers = scene.get('layers', [])
    
    # Filter out omitted panels
    kept_layers = [l for l in orig_layers if l.get('source_panel_id') not in OMITTED_PANEL_IDS]
    omitted_in_scene = len(orig_layers) - len(kept_layers)
    
    N = len(kept_layers)
    if N > 0:
        base_dur = round(scene_dur / N, 3)
        for i, l in enumerate(kept_layers):
            start = round(i * base_dur, 3)
            l['start_offset_sec'] = start
            if i < N - 1:
                l['duration_sec'] = base_dur
            else:
                l['duration_sec'] = round(scene_dur - start, 3)
                
    scene['layers'] = kept_layers
    print(f"Scene {s_idx+1} [{s_id}]: {len(orig_layers)} -> {len(kept_layers)} layers (omitted {omitted_in_scene}), layer_dur ~{scene_dur/max(N,1):.2f}s")

from sqlalchemy.orm.attributes import flag_modified

state['scenes'] = scenes
state['bgm_tracks'] = [{
    'id': 'bgm_default',
    'title': 'Crystal Resonance Theme',
    'name': 'Crystal Resonance Theme',
    'file_url': '/assets/demo/crystal_resonance_bgm.mp3',
    'audio_url': '/assets/demo/crystal_resonance_bgm.mp3',
    'volume': 0.30,
    'start_time_sec': 0.0,
    'duration_sec': 324.3,
    'loop': True,
    'ducking_enabled': True,
    'ducking_amount_db': -14.0,
}]
settings['story_editor_state'] = state
proj.settings = settings
flag_modified(proj, "settings")
db.commit()
print("Saved updated story_editor_state with non-story panels omitted and layers rebalanced.")

# Also update project.json if exists
proj_json_path = ws / "project.json"
if proj_json_path.exists():
    try:
        with open(proj_json_path, 'r', encoding='utf-8') as f:
            pdata = json.load(f)
        pdata['settings'] = settings
        with open(proj_json_path, 'w', encoding='utf-8') as f:
            json.dump(pdata, f, indent=2)
        print("Updated project.json successfully.")
    except Exception as e:
        print("Note: could not update project.json:", e)

# Preflight validation
report = timeline_compiler.preflight_validate(state, PROJECT_ID, ws)
print(f"\nTimeline compiler preflight valid: {report.get('valid')}")
print(f"Stats: total_duration={report.get('stats', {}).get('total_duration')}s, scenes={report.get('stats', {}).get('scene_count')}, narration_clips={report.get('stats', {}).get('narration_count')}")
if report.get('errors'):
    print(f"Preflight errors: {report.get('errors')}")
if report.get('warnings'):
    print(f"Preflight warnings: {report.get('warnings')}")

db.close()
