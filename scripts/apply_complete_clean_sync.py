import sys, os, json
sys.path.insert(0, '.')
from pathlib import Path
from sqlalchemy.orm.attributes import flag_modified

from engine.database.session import SessionLocal
from engine.database.models import ProjectRecord, PanelRecord
from engine.render.compiler import timeline_compiler

PROJECT_ID = '67e096cc-2e4f-4f40-9bb9-b6f99c297a9e'
ws = Path(r"C:\Users\Vijaya sekhar\AppData\Local\PanelFlow Studio\projects\67e096cc-2e4f-4f40-9bb9-b6f99c297a9e")

db = SessionLocal()
panels = db.query(PanelRecord).filter(PanelRecord.project_id == PROJECT_ID).all()
seq_to_id = {p.sequence: p.id for p in panels}

print(f"Loaded {len(seq_to_id)} panels for P1.")

def make_layer(seq: int, start_offset: float, duration: float, z: int = 1):
    pid = seq_to_id[seq]
    return {
        "source_panel_id": pid,
        "start_offset_sec": round(start_offset, 3),
        "duration_sec": round(duration, 3),
        "transform": {
            "x": 0.0,
            "y": 0.0,
            "scale": 1.0,
            "rotation": 0.0,
            "opacity": 1.0,
            "z_index": z,
        },
        "motion_preset": "none",
    }

# Scene 1: 0.000s - 71.700s (Seq 01 Cover OMITTED, Seq 12 Ad OMITTED)
# Total duration: 71.700s
scene_1_layers = [
    make_layer(2,  start_offset=0.000,  duration=8.480,  z=1),  # Clip 01: City establishing shot
    make_layer(3,  start_offset=8.480,  duration=1.650,  z=2),  # Clip 02: "I'M BACK..."
    make_layer(4,  start_offset=10.130, duration=1.370,  z=3),  # Clip 03a: Yifan looking
    make_layer(5,  start_offset=11.500, duration=1.850,  z=4),  # Clip 03b: Yifan rushing
    make_layer(6,  start_offset=13.350, duration=3.150,  z=5),  # Clip 04a: "Hurry up, dad and everyone..."
    make_layer(7,  start_offset=16.500, duration=3.310,  z=6),  # Clip 04b: "Qingwei only let me off..."
    make_layer(8,  start_offset=19.810, duration=3.690,  z=7),  # Clip 05a: "Of course we didn't know..."
    make_layer(9,  start_offset=23.500, duration=3.920,  z=8),  # Clip 05b: "Five days... search parties..."
    make_layer(10, start_offset=27.420, duration=7.080,  z=9),  # Clip 06a: "Anxiety is best... trick them"
    make_layer(11, start_offset=34.500, duration=8.020,  z=10), # Clip 06b: "Dad, Sir Gu is back!"
    make_layer(13, start_offset=42.520, duration=2.980,  z=11), # Clip 07a: "Yifu, you're finally back!"
    make_layer(14, start_offset=45.500, duration=3.020,  z=12), # Clip 07b: "Uncle, your hand..."
    make_layer(15, start_offset=48.520, duration=4.480,  z=13), # Clip 08a: "Is the map... Rest easy,"
    make_layer(16, start_offset=53.000, duration=4.870,  z=14), # Clip 08b: "Not a stone unchecked..."
    make_layer(17, start_offset=57.870, duration=7.490,  z=15), # Clip 09:  "Where are these 5 places?..."
    make_layer(18, start_offset=65.360, duration=6.340,  z=16), # Clip 10:  "How could I not look into it?..."
]

# Scene 2: 71.700s - 128.700s (Seq 19 Ad OMITTED, Seq 23 Ad OMITTED)
# Total duration: 57.000s
scene_2_layers = [
    make_layer(20, start_offset=0.000,  duration=18.440, z=1),  # Clips 11 & 12: Treasury & Barracks tour
    make_layer(21, start_offset=18.440, duration=6.390,  z=2),  # Clip 13: Private quarters / wives
    make_layer(22, start_offset=24.830, duration=6.160,  z=3),  # Clip 14: "Rotten degenerate! So many partners!"
    make_layer(24, start_offset=30.990, duration=2.510,  z=4),  # Clip 15a: Deadpan stare reaction
    make_layer(25, start_offset=33.500, duration=5.560,  z=5),  # Clip 15b: ANGRY FACE "Scouting manor not harem!"
    make_layer(26, start_offset=39.060, duration=8.740,  z=6),  # Clip 16a: "No time for dual cultivation!"
    make_layer(27, start_offset=47.800, duration=9.200,  z=7),  # Clip 16b: "Not a genuine degenerate..."
]

# Scene 3: 128.700s - 175.000s
# Total duration: 46.300s
scene_3_layers = [
    make_layer(28, start_offset=0.000,  duration=7.320,  z=1),  # Clip 17: Back to Eastern Lands technique
    make_layer(29, start_offset=7.320,  duration=3.470,  z=2),  # Clip 18: "Right, right, back on topic!"
    make_layer(30, start_offset=10.790, duration=2.510,  z=3),  # Clip 19a: "Ahem, remaining two areas?"
    make_layer(31, start_offset=13.300, duration=3.420,  z=4),  # Clip 19b: "Feiyun's resting room under guard"
    make_layer(32, start_offset=16.720, duration=10.270, z=5),  # Clip 20: "Jade Falls paradise..."
    make_layer(33, start_offset=26.990, duration=4.990,  z=6),  # Clip 21: "SOARING SWORD!"
    make_layer(34, start_offset=31.980, duration=14.320, z=7),  # Clip 22: "WHAT?! The Soaring Sword is there?!"
]

# Scene 4: 175.000s - 242.600s
# Total duration: 67.600s
scene_4_layers = [
    make_layer(35, start_offset=0.000,  duration=7.390,  z=1),  # Clip 23: Clan elders listening
    make_layer(36, start_offset=7.390,  duration=4.690,  z=2),  # Clip 24: "Exemplary work once more, hahaha!"
    make_layer(37, start_offset=12.080, duration=3.800,  z=3),  # Clip 25: "Uncle, after Soaring Sword?"
    make_layer(38, start_offset=15.880, duration=6.190,  z=4),  # Clip 26: "Yes, you've done clan service..."
    make_layer(39, start_offset=22.070, duration=25.760, z=5),  # Clips 27 & 28: "Highest elders... couldn't defeat him"
    make_layer(40, start_offset=47.830, duration=4.560,  z=6),  # Clip 29: "Fighting tooth and nail..."
    make_layer(41, start_offset=52.390, duration=10.700, z=7),  # Clip 30: "Shangguan clan glory will continue!"
    make_layer(42, start_offset=63.090, duration=4.510,  z=8),  # Clip 31: "Strut around clan with pride?"
]

# Scene 5: 242.600s - 314.000s (Seq 47 Ad OMITTED, Seq 53 Divider OMITTED, Seq 54 Discord OMITTED)
# Total duration: 71.400s
scene_5_layers = [
    make_layer(43, start_offset=0.000,  duration=2.900,  z=1),  # Clip 32a: Guard rushing in "OOM..."
    make_layer(44, start_offset=2.900,  duration=3.600,  z=2),  # Clip 32b: Elders stunned reaction
    make_layer(45, start_offset=6.500,  duration=7.270,  z=3),  # Clip 33: "Not two sword kings, only Feiyun!"
    make_layer(46, start_offset=13.770, duration=3.440,  z=4),  # Clip 34: "What's going on?"
    make_layer(48, start_offset=17.210, duration=16.310, z=5),  # Clip 35: "Baili Jingwei taking me as alchemist..."
    make_layer(49, start_offset=33.520, duration=3.480,  z=6),  # Clip 36a: Reaction shot
    make_layer(50, start_offset=37.000, duration=7.500,  z=7),  # Clip 36b: "Providence indeed! Heaven is helping us!"
    make_layer(51, start_offset=44.500, duration=11.870, z=8),  # Clip 37: "Congratulations, Clan Head! We will succeed!"
    make_layer(52, start_offset=56.370, duration=15.030, z=9),  # Clips 38 & 39: "Thank you for helping me... Grand Finale"
]

proj = db.query(ProjectRecord).filter(ProjectRecord.id == PROJECT_ID).first()
settings = dict(proj.settings or {})
state = dict(settings.get('story_editor_state', {}))
scenes = state.get('scenes', [])

bg_config = {
    "enabled": True,
    "preset": "duplicate_blur",
    "source_mode": "follow_active_visual",
    "blur_sigma": 36.0,
    "brightness": -0.16,
    "saturation": 0.85,
    "edge_shadow": 0.65,
    "motion": "slow_zoom",
    "motion_amount": 0.03,
    "foreground_fit": "contain",
    "foreground_x": 0.5,
    "foreground_y": 0.5,
}

scene_configs = [
    (0, "scene_6986e125", 0.000,   71.700, scene_1_layers),
    (1, "scene_dacaa0e8", 71.700,  57.000, scene_2_layers),
    (2, "scene_5a482d5d", 128.700, 46.300, scene_3_layers),
    (3, "scene_1fe1ec58", 175.000, 67.600, scene_4_layers),
    (4, "scene_c9ddf40c", 242.600, 71.400, scene_5_layers),
]

for idx, scene_id, start_time, duration, layers in scene_configs:
    if idx < len(scenes):
        sc = scenes[idx]
        sc['id'] = scene_id
        sc['start_time_sec'] = start_time
        sc['duration_sec'] = duration
        sc['layers'] = layers
        sc['background_treatment'] = bg_config
    else:
        scenes.append({
            "id": scene_id,
            "name": f"Scene {idx+1}",
            "start_time_sec": start_time,
            "duration_sec": duration,
            "layers": layers,
            "background_treatment": bg_config
        })

state['scenes'] = scenes[:5]
state['total_duration_sec'] = 314.000
settings['story_editor_state'] = state
proj.settings = settings
flag_modified(proj, "settings")
db.commit()
print("Updated project.settings.story_editor_state with all 54 clean individual panels and speech-synced timing!")

# Total duration is 314.0s
state["bgm_tracks"] = [{
    "id": "bgm_default",
    "title": "Crystal Resonance Theme",
    "name": "Crystal Resonance Theme",
    "file_url": "/assets/demo/crystal_resonance_bgm.mp3",
    "audio_url": "/assets/demo/crystal_resonance_bgm.mp3",
    "volume": 0.28,
    "start_time_sec": 0.0,
    "duration_sec": 314.0,
    "loop": True,
    "ducking_enabled": True,
    "ducking_amount_db": -14.0,
}]

settings["story_editor_state"] = state
proj.settings = settings
flag_modified(proj, "settings")
db.commit()

# Also sync to project.json
proj_json_path = ws / "project.json"
if proj_json_path.exists():
    with open(proj_json_path, 'r', encoding='utf-8') as f:
        pj = json.load(f)
    pj['settings'] = settings
    with open(proj_json_path, 'w', encoding='utf-8') as f:
        json.dump(pj, f, indent=2)

print("Applied semantic speech-synchronized timeline!")

report = timeline_compiler.preflight_validate(state, PROJECT_ID, ws)
print("Timeline compiler preflight valid:", report.get("valid"))
print("Stats:", report.get("stats"))
if report.get("errors"):
    print("Errors:", report.get("errors"))

plan = timeline_compiler.compile(state=state, project_id=PROJECT_ID, workspace_path=ws)
print(f"Compiled RenderPlan: duration={plan.total_duration_sec:.2f}s, shots={len(plan.shots)}, audio_tracks={len(plan.audio_tracks)}")

print("\n--- Visual Shots Breakdown ---")
for s in plan.shots:
    p_rec = db.query(PanelRecord).filter_by(id=s.panel_id).first()
    seq_str = f"Seq {p_rec.sequence:02d} ({p_rec.width}x{p_rec.height})" if p_rec else "Unknown"
    print(f"Shot [{s.shot_id}] | {s.start_time_sec:6.2f}s - {s.end_time_sec:6.2f}s (dur={s.duration_sec:5.2f}s) | {seq_str}")

db.close()
