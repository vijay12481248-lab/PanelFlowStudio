"""Batch production suite for all stickman shorts/reels:
C006 (Empty Seat)
C012 (The Quiet Backup)
C020 (A Smile on Loan)
C021 (The Elevator Button Again)
C024 (The Tiny Trophy Again)
C030 (The Giant Spider Again)
C035 (The Paper Boat Promise Again)
C036 (Last Bus Again)
C042 (One More Scroll After Hours)

Usage:
  python tools/produce_reels_suite.py <slug>
  e.g.: python tools/produce_reels_suite.py c020
        python tools/produce_reels_suite.py all
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import cv2
import edge_tts
import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.comfyui.art import ArtEngine
from engine.chronoflow.pipeline import ChronoFlowPipeline, COMFY_INPUT_DIR

SR = 48000
W, H = 1080, 1920
NEGATIVE = "extra limbs, duplicated characters, inconsistent clothes, changed head/body proportions, malformed hands, random text, logos, watermark, unwanted objects, style drift, 3d render, photo, realistic people, realistic anatomy"
LORA4 = "minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors"
CLIP_W, CLIP_H = 480, 832

REEL_REGISTRY = {
    "c020": {
        "slug": "c020_smile_on_loan",
        "title": "C020 A Smile on Loan",
        "shots": [
            {
                "id": "s1", "dur": 3.0, "camera": "push_in", "scale_start": 1.0, "scale_end": 1.15,
                "line": "Monday morning. The entire subway platform wears a heavy frown.",
                "img": "Single still frame, vertical 9:16. Minimalist subway platform. Grumpy stickman commuter in a dark coat and hat frowns deeply among waiting passengers. Pip in teal scarf watches. Tight close-up, push-in. Crisp flat 2D line art, clean silhouette.",
                "act": "The grumpy commuter sighs heavily, shoulders dropping. The camera does a slight slow push-in. Flat 2D doodle style, no text."
            },
            {
                "id": "s2", "dur": 6.0, "camera": "medium_drift", "scale_start": 1.0, "scale_end": 1.07,
                "line": "A gust of wind blows the commuter's hat across the train platform.",
                "img": "Single still frame, vertical 9:16. Medium shot. The commuter's hat flies off in the wind, landing near Pip's feet. The commuter gasps. Crisp flat 2D line art, clean silhouette.",
                "act": "The hat skitters across the platform floor. Pip steps forward to stop it with his foot. Medium shot. Flat 2D doodle style, no text."
            },
            {
                "id": "s3", "dur": 7.0, "camera": "reaction_punch", "scale_start": 1.0, "scale_end": 1.18,
                "line": "Pip scoops up the hat, hands it back, and offers a bright, warm smile.",
                "img": "Single still frame, vertical 9:16. Wide shot. Pip in teal scarf bends down, picks up the hat, and holds it out with a radiant smile toward the grump. Crisp flat 2D line art, clean silhouette.",
                "act": "Pip offers the hat back with both hands and smiles warmly. The grumpy commuter blinks in surprise. Flat 2D doodle style, no text."
            },
            {
                "id": "s4", "dur": 7.0, "camera": "over_shoulder_push", "scale_start": 1.04, "scale_end": 1.14,
                "line": "The commuter takes the hat. His stern frown slowly melts into a gentle grin.",
                "img": "Single still frame, vertical 9:16. Over-shoulder view. The commuter puts his hat back on, smiling softly, surprised by the kindness. Crisp flat 2D line art, clean silhouette.",
                "act": "The commuter puts the hat on and a small smile forms on his face. Over-shoulder shot. Flat 2D doodle style, no text."
            },
            {
                "id": "s5", "dur": 11.0, "camera": "restrained_push", "scale_start": 1.0, "scale_end": 1.12,
                "line": "He turns and smiles at a tired student beside him. Like magic, the smile ripples down the line.",
                "img": "Single still frame, vertical 9:16. The commuter smiles at a tired passenger, who in turn smiles at another commuter, a chain reaction of smiles. Crisp flat 2D line art, clean silhouette.",
                "act": "The commuter nods warmly to the next passenger, who smiles back. A chain of smiles spreads down the platform. Restrained push-in. Flat 2D doodle style, no text."
            },
            {
                "id": "s6", "dur": 6.0, "camera": "static_close", "scale_start": 1.06, "scale_end": 1.06,
                "line": "A single smile costs nothing, but it can change someone's entire day.",
                "img": "Single still frame, vertical 9:16. Static close-up. Pip and the happy commuter exchange a friendly wave as the train doors open, bright happy atmosphere. Crisp flat 2D line art, clean silhouette.",
                "act": "Pip and the commuter wave goodbye to each other with warm smiles. Static close-up shot. Flat 2D doodle style, no text."
            },
        ]
    },
    "c021": {
        "slug": "c021_elevator_button",
        "title": "C021 The Elevator Button Again",
        "shots": [
            {
                "id": "s1", "dur": 3.0, "camera": "push_in", "scale_start": 1.0, "scale_end": 1.15,
                "line": "In the crowded office lobby, one man has appointed himself Master of the Elevator.",
                "img": "Single still frame, vertical 9:16. Lobby. A proud stickman stands guard firmly right next to the glowing elevator call button. Tight close-up. Crisp flat 2D line art, clean silhouette.",
                "act": "The guard stickman stands tall and taps the button with exaggerated pride. Push-in. Flat 2D doodle style, no text."
            },
            {
                "id": "s2", "dur": 6.0, "camera": "medium_drift", "scale_start": 1.0, "scale_end": 1.07,
                "line": "Whenever anyone approaches, he proudly presses the button for them.",
                "img": "Single still frame, vertical 9:16. Medium shot. Pip in teal scarf approaches, and the man dramatically extends his finger to press the button first with a salute. Crisp flat 2D line art.",
                "act": "The man dramatically lunges his finger forward to press the button before Pip can reach it. Medium shot. Flat 2D doodle style, no text."
            },
            {
                "id": "s3", "dur": 7.0, "camera": "reaction_punch", "scale_start": 1.0, "scale_end": 1.18,
                "line": "Ten minutes pass. The crowd grows huge, all staring at the stubborn metal doors.",
                "img": "Single still frame, vertical 9:16. Wide shot. A giant line of stick-figure commuters waits behind the button guy, tapping their feet and checking wristwatches. Crisp flat 2D line art.",
                "act": "Commuters tap their feet and check their watches impatiently. The man nervously presses the button five more times fast. Flat 2D doodle style, no text."
            },
            {
                "id": "s4", "dur": 7.0, "camera": "over_shoulder_push", "scale_start": 1.04, "scale_end": 1.14,
                "line": "Pip glances over his shoulder and notices a small detail on the opposite wall.",
                "img": "Single still frame, vertical 9:16. Over-shoulder view. Pip turns around and notices an elevator door open on the other side of the corridor. Crisp flat 2D line art, clean silhouette.",
                "act": "Pip turns his head and points behind the crowd with a puzzled look. Over-shoulder shot. Flat 2D doodle style, no text."
            },
            {
                "id": "s5", "dur": 11.0, "camera": "restrained_push", "scale_start": 1.0, "scale_end": 1.12,
                "line": "Ding! The real elevator had arrived behind them all along.",
                "img": "Single still frame, vertical 9:16. The crowd turns around to see the open, empty elevator car behind them. The button guy slowly looks back in shock. Crisp flat 2D line art.",
                "act": "The crowd turns around and happily walks into the real elevator behind them. The button guy stands frozen in disbelief. Flat 2D doodle style, no text."
            },
            {
                "id": "s6", "dur": 6.0, "camera": "static_close", "scale_start": 1.06, "scale_end": 1.06,
                "line": "Sometimes we are so focused on waiting, we miss the open door right behind us.",
                "img": "Single still frame, vertical 9:16. Static close-up. Pip smiles from inside the open elevator, holding the door open for the embarrassed button guy. Crisp flat 2D line art.",
                "act": "Pip waves for the button guy to join him inside the elevator with a kind chuckle. Static close-up. Flat 2D doodle style, no text."
            },
        ]
    },
    "c030": {
        "slug": "c030_giant_spider",
        "title": "C030 The Giant Spider Again",
        "shots": [
            {
                "id": "s1", "dur": 3.0, "camera": "push_in", "scale_start": 1.0, "scale_end": 1.15,
                "line": "Late at night, a terrifying creature crawls across the bedroom wall.",
                "img": "Single still frame, vertical 9:16. Dim bedroom. A gigantic dark many-legged spider silhouette casts a huge shadow across the wall. Pip gasps in terror. Tight close-up. Crisp flat 2D line art.",
                "act": "The giant shadow wiggles its creepy legs on the wall. Pip trembles with wide eyes. Push-in. Flat 2D doodle style, no text."
            },
            {
                "id": "s2", "dur": 6.0, "camera": "medium_drift", "scale_start": 1.0, "scale_end": 1.07,
                "line": "Pip grabs a broom, heart pounding, preparing for the battle of his life.",
                "img": "Single still frame, vertical 9:16. Medium shot. Pip in teal scarf nervously grips a long broom like a spear, tiptoeing forward with shaking knees. Crisp flat 2D line art.",
                "act": "Pip tiptoes forward holding the broom out defensively, knees trembling. Medium shot. Flat 2D doodle style, no text."
            },
            {
                "id": "s3", "dur": 7.0, "camera": "reaction_punch", "scale_start": 1.0, "scale_end": 1.18,
                "line": "The beast suddenly lunges! Pip screams and swings wildly into thin air.",
                "img": "Single still frame, vertical 9:16. Wide shot. Pip jumps back screaming comically, swinging the broom at the shadow, panic comic tension. Crisp flat 2D line art.",
                "act": "Pip jumps in panic, waving the broom wildly while the shadow sways back and forth. Flat 2D doodle style, no text."
            },
            {
                "id": "s4", "dur": 7.0, "camera": "over_shoulder_push", "scale_start": 1.04, "scale_end": 1.14,
                "line": "He stops, panting. Then looks up toward the ceiling light.",
                "img": "Single still frame, vertical 9:16. Over-shoulder view. Pip lowers the broom and gazes up toward the ceiling fan light fixture. Crisp flat 2D line art.",
                "act": "Pip lowers the broom slowly and tilts his head upward with growing curiosity. Over-shoulder shot. Flat 2D doodle style, no text."
            },
            {
                "id": "s5", "dur": 11.0, "camera": "restrained_push", "scale_start": 1.0, "scale_end": 1.12,
                "line": "It isn't a monster at all. Just a lone black sock gently spinning on the ceiling fan.",
                "img": "Single still frame, vertical 9:16. An ordinary striped sock caught on a slowly rotating ceiling fan blade, casting the funny shadow right in front of the lamp. Crisp flat 2D line art.",
                "act": "The ceiling fan turns slowly, swinging the harmless sock. Restrained push-in. Flat 2D doodle style, no text."
            },
            {
                "id": "s6", "dur": 6.0, "camera": "static_close", "scale_start": 1.06, "scale_end": 1.06,
                "line": "Most monsters in life are just shadows of harmless little things.",
                "img": "Single still frame, vertical 9:16. Static close-up. Pip holds the sock in his hand, chuckling with relief, smiling warmly at the camera. Crisp flat 2D line art.",
                "act": "Pip shakes his head with a warm chuckle and tosses the sock into a laundry hamper. Static close-up. Flat 2D doodle style, no text."
            },
        ]
    },
    "c035": {
        "slug": "c035_paper_boat",
        "title": "C035 The Paper Boat Promise Again",
        "shots": [
            {
                "id": "s1", "dur": 3.0, "camera": "push_in", "scale_start": 1.0, "scale_end": 1.15,
                "line": "All day at school, Pip carefully protects a tiny folded paper boat.",
                "img": "Single still frame, vertical 9:16. Pip in teal scarf gently holds a crisp white paper boat in cupped hands, smiling warmly. Tight close-up. Crisp flat 2D line art.",
                "act": "Pip gently examines the paper boat in his hands with a smile. Push-in. Flat 2D doodle style, no text."
            },
            {
                "id": "s2", "dur": 6.0, "camera": "medium_drift", "scale_start": 1.0, "scale_end": 1.07,
                "line": "He promised his best friend they would launch it together after the bell.",
                "img": "Single still frame, vertical 9:16. Medium shot. Pip walks out of the school gates clutching the boat safely to his chest, looking for his friend. Crisp flat 2D line art.",
                "act": "Pip walks forward eagerly looking left and right for his friend. Medium shot. Flat 2D doodle style, no text."
            },
            {
                "id": "s3", "dur": 7.0, "camera": "reaction_punch", "scale_start": 1.0, "scale_end": 1.18,
                "line": "A sudden rain shower starts, and water drops threaten to soak the fragile boat.",
                "img": "Single still frame, vertical 9:16. Wide shot. Rain starts falling. Pip desperately covers the paper boat with his teal scarf to shield it from drops. Comic tension. Crisp flat 2D line art.",
                "act": "Pip shields the boat under his scarf, dodging rain drops with comic urgency. Flat 2D doodle style, no text."
            },
            {
                "id": "s4", "dur": 7.0, "camera": "over_shoulder_push", "scale_start": 1.04, "scale_end": 1.14,
                "line": "Through the rain, a familiar yellow umbrella rushes toward him.",
                "img": "Single still frame, vertical 9:16. Over-shoulder view. Pip looks up as his friend in a yellow raincoat runs up holding an umbrella over them both. Crisp flat 2D line art.",
                "act": "The friend runs up and shelters Pip with the umbrella. Over-shoulder shot. Flat 2D doodle style, no text."
            },
            {
                "id": "s5", "dur": 11.0, "camera": "restrained_push", "scale_start": 1.0, "scale_end": 1.12,
                "line": "Together, they place the dry little boat onto a sparkling rainwater puddle.",
                "img": "Single still frame, vertical 9:16. The two friends kneel together by a sparkling rainwater puddle, setting the little boat into the water. Warm joy. Crisp flat 2D line art.",
                "act": "Both friends gently launch the paper boat, watching it float smoothly across the puddle. Restrained push-in. Flat 2D doodle style, no text."
            },
            {
                "id": "s6", "dur": 6.0, "camera": "static_close", "scale_start": 1.06, "scale_end": 1.06,
                "line": "A promise kept is a boat that can never sink.",
                "img": "Single still frame, vertical 9:16. Static close-up. The two friends stand under the shared umbrella, smiling as the paper boat sails peacefully across the puddle. Crisp flat 2D line art.",
                "act": "The two friends smile happily together, watching the boat sail. Static close-up. Flat 2D doodle style, no text."
            },
        ]
    },
    "c036": {
        "slug": "c036_last_bus",
        "title": "C036 Last Bus Again",
        "shots": [
            {
                "id": "s1", "dur": 3.0, "camera": "push_in", "scale_start": 1.0, "scale_end": 1.15,
                "line": "The last bus of the night pulls up, and the doors are already hissing shut.",
                "img": "Single still frame, vertical 9:16. Night city street. The taillights of a night bus glow as doors start closing. Tight close-up. Crisp flat 2D line art.",
                "act": "The bus doors begin to close slowly. Camera does a slight push-in. Flat 2D doodle style, no text."
            },
            {
                "id": "s2", "dur": 6.0, "camera": "medium_drift", "scale_start": 1.0, "scale_end": 1.07,
                "line": "Pip sprints at full speed down the sidewalk, determined not to be stranded.",
                "img": "Single still frame, vertical 9:16. Medium shot. Pip in teal scarf running at full speed with wind blowing his scarf back, eyes locked on the bus. Crisp flat 2D line art.",
                "act": "Pip sprints dynamically across the sidewalk, pumping his arms. Medium shot. Flat 2D doodle style, no text."
            },
            {
                "id": "s3", "dur": 7.0, "camera": "reaction_punch", "scale_start": 1.0, "scale_end": 1.18,
                "line": "Just meters away, an elderly passenger drops their grocery bag, spilling apples everywhere.",
                "img": "Single still frame, vertical 9:16. Wide shot. An elderly stickman stumbles and drops a grocery bag, fruit rolling across the pavement. Comic tension. Crisp flat 2D line art.",
                "act": "The elderly stickman drops the bag in dismay. Pip skids to an abrupt halt. Flat 2D doodle style, no text."
            },
            {
                "id": "s4", "dur": 7.0, "camera": "over_shoulder_push", "scale_start": 1.04, "scale_end": 1.14,
                "line": "Pip looks at the closing bus doors. Then turns right back to help.",
                "img": "Single still frame, vertical 9:16. Over-shoulder view. Pip turns away from the bus and immediately kneels down to gather the fallen groceries. Crisp flat 2D line art.",
                "act": "Pip quickly gathers the groceries and hands the bag back with a reassuring nod. Over-shoulder shot. Flat 2D doodle style, no text."
            },
            {
                "id": "s5", "dur": 11.0, "camera": "restrained_push", "scale_start": 1.0, "scale_end": 1.12,
                "line": "Honk! The bus driver saw it all, holding the doors wide open with a thumbs up.",
                "img": "Single still frame, vertical 9:16. The bus driver waves warmly from the open doors, welcoming both Pip and the passenger aboard. Warm surprise. Crisp flat 2D line art.",
                "act": "The bus driver gives a big thumbs up as Pip and the passenger step aboard together. Restrained push-in. Flat 2D doodle style, no text."
            },
            {
                "id": "s6", "dur": 6.0, "camera": "static_close", "scale_start": 1.06, "scale_end": 1.06,
                "line": "Doing the right thing is never the detour that makes you late.",
                "img": "Single still frame, vertical 9:16. Static close-up. Pip and the passenger sit comfortably side by side by the bus window, smiling as the city lights roll past. Crisp flat 2D line art.",
                "act": "Pip and the passenger sit smiling by the window as the bus drives into the night. Static close-up. Flat 2D doodle style, no text."
            },
        ]
    },
    "c042": {
        "slug": "c042_one_more_scroll",
        "title": "C042 One More Scroll After Hours",
        "shots": [
            {
                "id": "s1", "dur": 3.0, "camera": "push_in", "scale_start": 1.0, "scale_end": 1.15,
                "line": "It's midnight. Pip promises himself just one quick minute of scrolling.",
                "img": "Single still frame, vertical 9:16. Dim bedroom. Pip lies on the couch, face lit by the glowing smartphone screen. Tight close-up. Crisp flat 2D line art.",
                "act": "Pip swipes up gently on his phone with a sleepy smile. Push-in. Flat 2D doodle style, no text."
            },
            {
                "id": "s2", "dur": 6.0, "camera": "medium_drift", "scale_start": 1.0, "scale_end": 1.07,
                "line": "He tries to put the phone down, but every notification pulls him back like a magnet.",
                "img": "Single still frame, vertical 9:16. Medium shot. Pip tries to reach for the bedside table, but his hand clings to the phone, comedic struggle. Crisp flat 2D line art.",
                "act": "Pip strains to stretch his arm away, but his eyes stay locked on the screen. Medium shot. Flat 2D doodle style, no text."
            },
            {
                "id": "s3", "dur": 7.0, "camera": "reaction_punch", "scale_start": 1.0, "scale_end": 1.18,
                "line": "Suddenly the charging cable feels like an unbreakable rope tying him to the screen.",
                "img": "Single still frame, vertical 9:16. Wide shot. Pip tangled in comic charging cable ropes on the couch, battling imaginary notification bubbles. Comic tension. Crisp flat 2D line art.",
                "act": "Pip flails comically on the couch trying to break free from the screen hypnosis. Flat 2D doodle style, no text."
            },
            {
                "id": "s4", "dur": 7.0, "camera": "over_shoulder_push", "scale_start": 1.04, "scale_end": 1.14,
                "line": "He glances at the clock. It's two AM, and he's watching a video of bread falling over.",
                "img": "Single still frame, vertical 9:16. Over-shoulder view. Pip stares blankly at a video of a slice of bread flopping over, exhausted and bewildered. Crisp flat 2D line art.",
                "act": "Pip blinks slowly in disbelief at the ridiculous video on screen. Over-shoulder shot. Flat 2D doodle style, no text."
            },
            {
                "id": "s5", "dur": 11.0, "camera": "restrained_push", "scale_start": 1.0, "scale_end": 1.12,
                "line": "He finally slaps the phone face down, yanks the plug, and takes a giant breath of freedom.",
                "img": "Single still frame, vertical 9:16. Pip proudly flips the phone screen-down onto the table and raises both arms in heroic victory. Warm relief. Crisp flat 2D line art.",
                "act": "Pip firmly places the phone face down and exhales with huge triumph. Restrained push-in. Flat 2D doodle style, no text."
            },
            {
                "id": "s6", "dur": 6.0, "camera": "static_close", "scale_start": 1.06, "scale_end": 1.06,
                "line": "Put down the screen tonight. The real world is waiting for you tomorrow.",
                "img": "Single still frame, vertical 9:16. Static close-up. Pip tucked peacefully under a cozy blanket in bed, eyes closed, smiling as moonlight shines through the window. Crisp flat 2D line art.",
                "act": "Pip snuggles into his pillow, drifting off to sleep with a peaceful smile. Static close-up. Flat 2D doodle style, no text."
            },
        ]
    }
}

async def generate_narration_edge(audio_dir: Path, shots: list[dict]):
    voice = "en-US-ChristopherNeural"
    for s in shots:
        mp3 = audio_dir / f"{s['id']}_voice.mp3"
        if not mp3.exists():
            c = edge_tts.Communicate(s["line"], voice, rate="-4%", pitch="+1Hz")
            await c.save(str(mp3))
        wav = audio_dir / f"{s['id']}_voice.wav"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(mp3), "-ar", str(SR), "-ac", "2", str(wav)], check=True)

def apply_camera_motion_reel(src: Path, dst: Path, dur: float, s_start: float, s_end: float):
    cap = cv2.VideoCapture(str(src))
    total_frames = int(dur * 30.0)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    tmp = dst.with_suffix(".tmp.mp4")
    out = cv2.VideoWriter(str(tmp), fourcc, 30.0, (W, H))

    frames = []
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frames.append(frame)
    cap.release()

    n_in = len(frames)
    for i in range(total_frames):
        prog = i / max(1, total_frames - 1)
        scale = s_start + (s_end - s_start) * prog
        src_idx = min(n_in - 1, int(prog * n_in))
        base = frames[src_idx]
        up = cv2.resize(base, (W, H), interpolation=cv2.INTER_LANCZOS4)
        if abs(scale - 1.0) > 0.001:
            cw, ch = int(W / scale), int(H / scale)
            x1 = (W - cw) // 2
            y1 = (H - ch) // 2
            crop = up[y1:y1 + ch, x1:x1 + cw]
            final_f = cv2.resize(crop, (W, H), interpolation=cv2.INTER_LINEAR)
        else:
            final_f = up
        out.write(final_f)
    out.release()

    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(tmp), "-c:v", "libx264", "-crf", "16", "-preset", "fast", "-pix_fmt", "yuv420p", str(dst)], check=True)
    if tmp.exists():
        tmp.unlink()

def build_soundscape_reel(audio_dir: Path, shots: list[dict], total_dur: float = 40.0) -> np.ndarray:
    n_samples = int(total_dur * SR)
    audio = np.zeros((n_samples, 2), dtype=np.float32)
    rng = np.random.default_rng(77)

    # Room ambience
    noise = rng.standard_normal(n_samples).astype(np.float32)
    sos_amb = butter(2, [80, 850], "band", fs=SR, output="sos")
    audio += sosfilt(sos_amb, noise)[:, None] * 0.016

    # Soft melodic progression
    chords = [
        (0.5, 3.5, [261.63, 329.63, 392.00], 0.05),
        (4.0, 3.5, [196.00, 246.94, 293.66], 0.05),
        (7.5, 3.5, [220.00, 261.63, 329.63], 0.06),
        (11.0, 4.0, [174.61, 220.00, 261.63], 0.06),
        (15.0, 4.0, [196.00, 246.94, 293.66], 0.06),
        (19.0, 3.5, [220.00, 261.63, 329.63], 0.06),
        (22.5, 5.0, [261.63, 329.63, 392.00, 523.25], 0.09),  # Bloom
        (27.5, 4.0, [196.00, 246.94, 293.66], 0.08),
        (31.5, 4.0, [220.00, 261.63, 329.63], 0.07),
        (35.5, 4.5, [261.63, 329.63, 392.00], 0.07),
    ]
    for start_t, dur, freqs, vol in chords:
        i0 = int(start_t * SR)
        i1 = min(n_samples, i0 + int(dur * SR))
        ct = np.arange(i1 - i0) / SR
        env = np.sin(np.pi * np.clip(ct / dur, 0, 1) ** 0.5) * np.exp(-ct / (dur * 0.7))
        for f in freqs:
            tone = np.sin(2 * np.pi * f * ct) + 0.25 * np.sin(4 * np.pi * f * ct)
            audio[i0:i1] += (tone * env * vol)[:, None].astype(np.float32)

    # Foley accents
    def add_chime(at_s: float, vol: float = 0.16):
        i0 = int(at_s * SR)
        i1 = min(n_samples, i0 + int(2.0 * SR))
        tt = np.arange(i1 - i0) / SR
        for pf in [1046.5, 1318.5, 1567.98]:
            ch = np.sin(2 * np.pi * pf * tt) * np.exp(-tt * 2.3) * (vol / 3)
            audio[i0:i1] += ch[:, None]

    add_chime(23.2, vol=0.18)
    add_chime(34.8, vol=0.14)

    # Narrative voice mix
    t_cursor = 0.0
    for s in shots:
        wav_p = audio_dir / f"{s['id']}_voice.wav"
        if wav_p.exists():
            vdata, vsr = sf.read(str(wav_p), dtype="float32")
            if vdata.ndim == 1:
                vdata = np.stack([vdata, vdata], axis=1)
            i0 = int((t_cursor + 0.25) * SR)
            i1 = min(n_samples, i0 + vdata.shape[0])
            audio[i0:i1] += vdata[:i1 - i0] * 0.95
        t_cursor += s["dur"]

    fade_len = int(1.5 * SR)
    fade_c = np.linspace(1.0, 0.0, fade_len, dtype=np.float32)
    audio[-fade_len:] *= fade_c[:, None]

    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio * (10 ** (-1.0 / 20) / peak)
    return audio

def build_subtitles_file(ass_p: Path, shots: list[dict]):
    def ass_time(t: float) -> str:
        cs = round(t * 100)
        return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"

    head = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 0\n\n"
        "[V4+ Styles]\n"
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n"
        "Style: Default,Impact,74,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,1,0,1,6,2,2,60,60,340,1\n"
        "Style: Hook,Impact,86,&H0000E5FF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,1,0,1,7,3,2,60,60,340,1\n\n"
        "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
    )
    lines = []
    t_cursor = 0.0
    for i, s in enumerate(shots):
        st = t_cursor + 0.25
        et = t_cursor + s["dur"] - 0.2
        style = "Hook" if i == 0 else "Default"
        text = s["line"].upper()
        lines.append(f"Dialogue: 0,{ass_time(st)},{ass_time(et)},{style},,0,0,0,,{text}")
        t_cursor += s["dur"]
    ass_p.write_text(head + "\n".join(lines) + "\n", encoding="utf-8")

def produce_single_reel(key: str):
    spec = REEL_REGISTRY[key]
    out_dir = ROOT / "output" / "reels_production" / spec["slug"]
    img_dir = out_dir / "images"
    clip_dir = out_dir / "clips"
    seg_dir = out_dir / "seg"
    audio_dir = out_dir / "audio"
    final_dir = out_dir / "final"

    for d in (img_dir, clip_dir, seg_dir, audio_dir, final_dir):
        d.mkdir(parents=True, exist_ok=True)

    print(f"\n=======================================================")
    print(f"PRODUCING REEL: {spec['title']}")
    print(f"=======================================================")

    engine = ArtEngine()
    pipe = ChronoFlowPipeline()

    # 1. Images
    for s in spec["shots"]:
        img_p = img_dir / f"{s['id']}.png"
        if not img_p.exists():
            print(f"Generating image {s['id']}...")
            seed = int(time.time() * 1000) % 100000
            art = engine.generate(s["img"], NEGATIVE, 768, 1344, seed, f"{spec['slug']}_{s['id']}", workflow_id="zimage_turbo")
            img_p.write_bytes(art.png)

    # 2. Clips
    for s in spec["shots"]:
        clip_p = clip_dir / f"{s['id']}.mp4"
        if not clip_p.exists():
            img_p = img_dir / f"{s['id']}.png"
            inp_name = f"{spec['slug']}_{s['id']}.png"
            shutil.copy2(img_p, COMFY_INPUT_DIR / inp_name)
            print(f"Rendering clip {s['id']}...")
            t0 = time.time()
            g = pipe.build_h3_prompt(s["act"], CLIP_W, CLIP_H, 124, 4, LORA4, "sliding_window", inp_name, seed=int(time.time() * 1000) % 100000, fast_h3=False)
            res = asyncio.run(pipe.execute_prompt(g))
            shutil.copy2(res, clip_p)
            print(f"Clip {s['id']} done in {time.time()-t0:.1f}s")

    # 3. Narration
    asyncio.run(generate_narration_edge(audio_dir, spec["shots"]))

    # 4. Camera & Segments
    seg_files = []
    for s in spec["shots"]:
        src = clip_dir / f"{s['id']}.mp4"
        dst = seg_dir / f"{s['id']}.mp4"
        apply_camera_motion_reel(src, dst, s["dur"], s["scale_start"], s["scale_end"])
        seg_files.append(f"file '{dst.as_posix()}'")

    seg_list = out_dir / "seg.txt"
    seg_list.write_text("\n".join(seg_files), encoding="utf-8")

    # 5. Audio Bed
    audio_path = audio_dir / "master_audio.wav"
    audio_arr = build_soundscape_reel(audio_dir, spec["shots"], 40.0)
    sf.write(str(audio_path), audio_arr, SR)

    # 6. Subtitles
    ass_path = out_dir / "subtitles.ass"
    build_subtitles_file(ass_path, spec["shots"])

    # 7. Concat & Final Mux
    concat_video = out_dir / "concat.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(seg_list), "-c", "copy", str(concat_video)], check=True)

    final_video = final_dir / f"{spec['slug']}_final_40s.mp4"
    ass_escaped = str(ass_path).replace("\\", "/").replace(":", "\\:")
    cmd_mux = [
        "ffmpeg", "-y", "-v", "error",
        "-i", str(concat_video),
        "-i", str(audio_path),
        "-vf", f"subtitles='{ass_escaped}'",
        "-c:v", "libx264", "-crf", "17", "-preset", "fast",
        "-c:a", "aac", "-b:a", "192k",
        "-t", "40.000",
        "-movflags", "+faststart",
        str(final_video)
    ]
    subprocess.run(cmd_mux, check=True)
    print(f"\nCOMPLETED: {final_video} ({final_video.stat().st_size / (1024*1024):.2f} MB)")
    return final_video

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "c020"
    if target == "all":
        for k in REEL_REGISTRY:
            produce_single_reel(k)
    elif target in REEL_REGISTRY:
        produce_single_reel(target)
    else:
        print(f"Unknown reel key: {target}. Choices: {list(REEL_REGISTRY.keys())}")
