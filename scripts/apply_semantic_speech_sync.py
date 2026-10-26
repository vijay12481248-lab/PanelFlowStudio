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

# Define the exact semantic speech-to-panel sync plan
# Scene 1: 0.00s - 71.70s (Seq 01 Cover OMITTED)
scene_1_layers = [
    make_layer(2, start_offset=0.000, duration=10.134, z=1),   # Clips 1 & 2 ("Yifu returns...", "I'm back, everyone!")
    make_layer(3, start_offset=10.134, duration=1.610, z=2),  # Clip 3 part 1 ("Hurry up!")
    make_layer(4, start_offset=11.744, duration=1.610, z=3),  # Clip 3 part 2 ("Dad getting impatient!")
    make_layer(5, start_offset=13.354, duration=14.066, z=4), # Clips 4 & 5 ("Five whole days...", "Clan in massive rush...")
    make_layer(6, start_offset=27.420, duration=30.450, z=5), # Clips 6, 7, 8 ("Anxiety is best...", "Rest easy...", "Detailed map...")
    make_layer(7, start_offset=57.870, duration=7.490, z=6),  # Clip 9 ("Where exactly are these 5 places?...")
    make_layer(8, start_offset=65.360, duration=6.340, z=7),  # Clip 10 ("How could I not look into it?...")
]

# Scene 2: 71.70s - 128.70s (Seq 12 Ad OMITTED)
scene_2_layers = [
    make_layer(9, start_offset=0.000, duration=18.440, z=1),   # Clips 11 & 12 (Treasury & Barracks map tour)
    make_layer(10, start_offset=18.440, duration=6.390, z=2),  # Clip 13 ("Private quarters, wives & partners...")
    make_layer(11, start_offset=24.830, duration=6.160, z=3),  # Clip 14 ("What a rotten degenerate!...")
    make_layer(13, start_offset=30.990, duration=1.810, z=4),  # Clip 15 part 1 (Deadpan reaction stare)
    make_layer(14, start_offset=32.800, duration=6.260, z=5),  # Clip 15 part 2 ("Scouting manor not harem!" - ANGRY FACE!)
    make_layer(15, start_offset=39.060, duration=8.740, z=6),  # Clip 16 part 1 ("Dual cultivation mission...")
    make_layer(16, start_offset=47.800, duration=9.200, z=7),  # Clip 16 part 2 ("Not a genuine horn dog...")
]

# Scene 3: 128.70s - 175.00s (Seq 20 Ad OMITTED)
scene_3_layers = [
    make_layer(17, start_offset=0.000, duration=7.320, z=1),   # Clip 17 (Eastern Lands ultimate technique)
    make_layer(18, start_offset=7.320, duration=3.470, z=2),   # Clip 18 ("Right, right, let's get back on topic!")
    make_layer(19, start_offset=10.790, duration=2.510, z=3),  # Clip 19 part 1 ("Ahem, what about remaining areas?")
    make_layer(21, start_offset=13.300, duration=3.420, z=4),  # Clip 19 part 2 ("Feiyun's resting room...")
    make_layer(22, start_offset=16.720, duration=10.270, z=5), # Clip 20 ("Jade Falls paradise...")
    make_layer(23, start_offset=26.990, duration=4.990, z=6),  # Clip 21 ("SOARING SWORD!")
    make_layer(24, start_offset=31.980, duration=14.320, z=7), # Clip 22 ("What?! The Soaring Sword is truly there?!")
]

# Scene 4: 175.00s - 242.60s
scene_4_layers = [
    make_layer(25, start_offset=0.000, duration=7.390, z=1),   # Clip 23 (Clan elders gathered)
    make_layer(26, start_offset=7.390, duration=4.690, z=2),   # Clip 24 ("Exemplary work once more, hahaha!")
    make_layer(27, start_offset=12.080, duration=3.800, z=3),  # Clip 25 ("Uncle, is clan after Soaring Sword?")
    make_layer(28, start_offset=15.880, duration=12.620, z=4), # Clip 26 ("Yes, you've done clan service...")
    make_layer(29, start_offset=28.500, duration=19.330, z=5), # Clips 27 & 28 ("Highest elders... couldn't defeat him...")
    make_layer(30, start_offset=47.830, duration=4.560, z=6),  # Clip 29 ("Fighting tooth and nail...")
    make_layer(31, start_offset=52.390, duration=10.700, z=7), # Clip 30 ("Shangguan clan glory will continue!")
    make_layer(32, start_offset=63.090, duration=4.510, z=8),  # Clip 31 ("Strut around clan with pride?")
]

# Scene 5: 242.60s - 316.00s (Seq 37 Ad & Seq 42 Discord OMITTED)
scene_5_layers = [
    make_layer(33, start_offset=0.000, duration=2.900, z=1),   # Clip 32 part 1 (Guard rushing in "OOM...")
    make_layer(34, start_offset=2.900, duration=3.600, z=2),   # Clip 32 part 2 (Elders intense reaction)
    make_layer(35, start_offset=6.500, duration=7.270, z=3),   # Clip 33 ("Not two Sword Kings, only Feiyun remains!")
    make_layer(36, start_offset=13.770, duration=3.440, z=4),  # Clip 34 ("What's going on?")
    make_layer(38, start_offset=17.210, duration=16.310, z=5), # Clip 35 ("Baili Jingwei taking me as alchemist...")
    make_layer(39, start_offset=33.520, duration=10.980, z=6), # Clip 36 ("Dragon Cleaving Sword King leaving...")
    make_layer(40, start_offset=44.500, duration=11.870, z=7), # Clip 37 ("Congratulations, Clan Head!...")
    make_layer(41, start_offset=56.370, duration=17.030, z=8), # Clips 38 & 39 ("Thank you for paving way... Grand finale")
]

# Update project.settings
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
    (0, "scene_6986e125", 0.000, 71.700, scene_1_layers),
    (1, "scene_dacaa0e8", 71.700, 57.000, scene_2_layers),
    (2, "scene_5a482d5d", 128.700, 46.300, scene_3_layers),
    (3, "scene_1fe1ec58", 175.000, 67.600, scene_4_layers),
    (4, "scene_c9ddf40c", 242.600, 73.400, scene_5_layers),
]

for idx, sid, start, dur, layers in scene_configs:
    sc = scenes[idx]
    sc["id"] = sid
    sc["start_time_sec"] = start
    sc["duration_sec"] = dur
    sc["layers"] = layers
    sc["background"] = bg_config.copy()
    sc["camera"] = {
        "preset": "custom",
        "zoom_start": 1.00,
        "zoom_end": 1.03,
        "pan_x_start": 0.0,
        "pan_x_end": 0.0,
        "pan_y_start": 0.0,
        "pan_y_end": 0.0,
        "easing": "ease_in_out",
        "duration_sec": dur,
    }
    sc["transition_in"] = "fade" if idx > 0 else "none"
    sc["transition_duration_sec"] = 0.40

state["scenes"] = scenes

# Also update narration clip scene assignments & start times so they match 100%
clips = state.get("narration_clips", [])
# Total duration is 316.0s
state["bgm_tracks"] = [{
    "id": "bgm_default",
    "title": "Crystal Resonance Theme",
    "name": "Crystal Resonance Theme",
    "file_url": "/assets/demo/crystal_resonance_bgm.mp3",
    "audio_url": "/assets/demo/crystal_resonance_bgm.mp3",
    "volume": 0.28,
    "start_time_sec": 0.0,
    "duration_sec": 316.0,
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

db.close()
