import json
import math
import subprocess
import time
from pathlib import Path
from PIL import Image, ImageFilter, ImageOps, ImageDraw, ImageFont

PROJECT_DIR = Path("output/Regressed_Assassin_Duke")
AUDIO_DIR = PROJECT_DIR / "audio"
RAW_DIR = PROJECT_DIR / "raw_chapters"
FRAMES_DIR = PROJECT_DIR / "render_frames"
FRAMES_DIR.mkdir(parents=True, exist_ok=True)

WIDTH = 1920
HEIGHT = 1080
FPS = 25

def select_panels_for_beats():
    with open(AUDIO_DIR / "timing_manifest.json", "r", encoding="utf-8") as f:
        manifest = json.load(f)
    
    beats = manifest["beats"]
    
    # Load all slices per chapter
    chapter_slices = {}
    for ch in range(1, 6):
        ch_dir = RAW_DIR / f"chapter_{ch}"
        slices = sorted(list(ch_dir.glob("*.webp")))
        chapter_slices[ch] = slices
        print(f"Chapter {ch}: {len(slices)} available slices")

    # Map beats to chapters
    # Beats 1-5: Ch 1 (207 slices)
    # Beats 6-10: Ch 2 (117 slices)
    # Beats 11-15: Ch 3 (101 slices)
    # Beats 16-20: Ch 4 (110 slices)
    # Beats 21-26: Ch 5 (111 slices)
    
    act_to_chapter = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 5}
    
    shots = []
    
    for beat in beats:
        b_id = beat["beat_id"]
        act = beat["act"]
        ch_num = act_to_chapter.get(act, 5)
        avail = chapter_slices[ch_num]
        
        # Calculate slice slice window based on beat index within act
        act_beats = [b for b in beats if b["act"] == act]
        beat_idx_in_act = act_beats.index(beat)
        n_act_beats = len(act_beats)
        
        # Slice range
        step = len(avail) / n_act_beats
        start_idx = int(beat_idx_in_act * step)
        end_idx = int((beat_idx_in_act + 1) * step)
        selected_slices = avail[start_idx:end_idx]
        
        if not selected_slices:
            selected_slices = [avail[min(start_idx, len(avail)-1)]]
            
        # Pick 3-5 key frames across this beat duration
        beat_dur = beat["duration_sec"]
        num_shots = min(len(selected_slices), max(3, int(beat_dur / 6.0)))
        step_shot = max(1, len(selected_slices) // num_shots)
        
        shot_slices = [selected_slices[i * step_shot] for i in range(num_shots) if i * step_shot < len(selected_slices)]
        if not shot_slices:
            shot_slices = [selected_slices[0]]
            
        shot_dur = beat_dur / len(shot_slices)
        cur_t = beat["start_sec"]
        
        for s_idx, sl_path in enumerate(shot_slices):
            shots.append({
                "beat_id": b_id,
                "title": beat["title"],
                "act": act,
                "start_time": cur_t,
                "duration": shot_dur,
                "image_path": str(sl_path)
            })
            cur_t += shot_dur
            
    print(f"Total video shots planned: {len(shots)} across {manifest['total_duration_formatted']}")
    with open(PROJECT_DIR / "shots_plan.json", "w", encoding="utf-8") as f:
        json.dump(shots, f, indent=2)
    return shots

if __name__ == "__main__":
    select_panels_for_beats()
