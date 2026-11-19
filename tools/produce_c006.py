"""Production script for C006 Empty Seat stickman short video.

Uses Z-Image Turbo (ArtEngine) for still frame generation and ChronoFlow MiniMax H3 Turbo
for video clip generation, followed by audio generation and FFmpeg timeline assembly.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.comfyui.art import ArtEngine
from engine.chronoflow.pipeline import ChronoFlowPipeline, COMFY_INPUT_DIR
from engine.original.animate import release_ollama

OUT_DIR = ROOT / "output" / "c006_empty_seat"
IMG_DIR = OUT_DIR / "images"
CLIP_DIR = OUT_DIR / "clips"
SEG_DIR = OUT_DIR / "seg"
AUDIO_DIR = OUT_DIR / "audio"
FINAL_DIR = OUT_DIR / "final"

for d in (IMG_DIR, CLIP_DIR, SEG_DIR, AUDIO_DIR, FINAL_DIR):
    d.mkdir(parents=True, exist_ok=True)

SHOTS = [
    {
        "id": "s1",
        "dur": 3.0,
        "seed_img": 1001,
        "seed_clip": 2001,
        "img_prompt": (
            "Single still frame, vertical 9:16. A stickman character named Pip with round white head, black monoline limbs, wearing a teal scarf. "
            "A place card sits on the table opposite him. Minimalist warm off-white coffee shop or cafe environment, tight close-up shot. "
            "Crisp flat 2D line art, clean silhouette, curiosity readable in pose, soft consistent lighting, simple clean composition."
        ),
        "video_prompt": (
            "A stick-figure guy in a teal scarf with round white head and black monoline limbs. "
            "A place card sits opposite him on the table. He sits still, looking with curiosity at the place card. "
            "The camera does a slight slow push-in. Only the action of this moment moves; "
            "everything else stays exactly as drawn in the same flat hand-drawn doodle cartoon style, no new objects appear."
        ),
    },
    {
        "id": "s2",
        "dur": 6.0,
        "seed_img": 1002,
        "seed_clip": 2002,
        "img_prompt": (
            "Single still frame, vertical 9:16. Stickman Pip with round white head, black monoline limbs, teal scarf. "
            "Medium shot in minimalist warm cafe. Pip sits at the small cafe table saving the empty chair opposite him, "
            "looking eagerly toward the entrance with anticipation. Clean silhouette, crisp flat 2D line art, soft warm lighting."
        ),
        "video_prompt": (
            "A stick-figure guy named Pip in a teal scarf with round white head and black monoline limbs. "
            "Medium shot. Pip sits at the cafe table looking eagerly towards the entrance, waiting for someone to arrive. "
            "Clear anticipation in movement, slight shifting pose. The camera is a static medium shot. Only the action of this moment moves; "
            "everything else stays exactly as drawn in the same flat hand-drawn doodle cartoon style, no new objects appear."
        ),
    },
    {
        "id": "s3",
        "dur": 7.0,
        "seed_img": 1003,
        "seed_clip": 2003,
        "img_prompt": (
            "Single still frame, vertical 9:16. Stickman Pip with round white head, black monoline limbs, teal scarf. "
            "Wide shot in minimalist warm cafe. A physical complication: the place card wobbles and someone almost takes the empty chair, "
            "Pip lunges forward with hands outstretched to protect the seat, comic tension, expressive nervous pose. "
            "Clean silhouette, crisp flat 2D line art, soft warm lighting."
        ),
        "video_prompt": (
            "A stick-figure guy named Pip in a teal scarf with round white head and black monoline limbs. "
            "Wide shot. Pip reacts to keep the empty seat safe, extending his arms defensively to protect the empty chair. "
            "Comic tension and urgent movement. The camera is a static shot. Only the action of this moment moves; "
            "everything else stays exactly as drawn in the same flat hand-drawn doodle cartoon style, no new objects appear."
        ),
    },
    {
        "id": "s4",
        "dur": 7.0,
        "seed_img": 1004,
        "seed_clip": 2004,
        "img_prompt": (
            "Single still frame, vertical 9:16. Stickman Pip with round white head, black monoline limbs, teal scarf. "
            "Over-the-shoulder shot in minimalist warm cafe looking across the empty table. "
            "Pip looks at the empty chair and place card, realizing time has passed and no one has arrived, surprise and bittersweet realization. "
            "Clean silhouette, crisp flat 2D line art, soft warm lighting."
        ),
        "video_prompt": (
            "A stick-figure guy named Pip in a teal scarf with round white head and black monoline limbs. "
            "Over-the-shoulder shot. Pip sits at the table, slowly lowers his head and looks at the empty chair, "
            "realizing the wait was in vain. Soft melancholic movement, quiet surprise. The camera is a static shot. "
            "Only the action of this moment moves; everything else stays exactly as drawn in the same flat hand-drawn doodle cartoon style, no new objects appear."
        ),
    },
    {
        "id": "s5",
        "dur": 11.0,
        "seed_img": 1005,
        "seed_clip": 2005,
        "img_prompt": (
            "Single still frame, vertical 9:16. Minimalist warm cafe. A stranger stickman with round white head, black monoline limbs "
            "and a warm yellow scarf gently sits down in the empty seat across from Pip. Pip is startled then warmly surprised. "
            "Two stickman characters at the table. Clean silhouette, crisp flat 2D line art, soft warm lighting."
        ),
        "video_prompt": (
            "Two stick-figure characters in a minimalist cafe: Pip in a teal scarf, and a friendly stranger stickman in a yellow scarf. "
            "The stranger sits down in the empty chair across the table, offering a friendly nod. Pip reacts with warm surprise and relief. "
            "The camera does a restrained slow push-in. Only the action of this moment moves; "
            "everything else stays exactly as drawn in the same flat hand-drawn doodle cartoon style, no new objects appear."
        ),
    },
    {
        "id": "s6",
        "dur": 6.0,
        "seed_img": 1016,
        "seed_clip": 2006,
        "img_prompt": (
            "Single still frame, vertical 9:16. Two simple 2D stick-figure characters with round white heads and black monoline limbs "
            "sitting opposite each other at a small round cafe table: one stickman on the left wearing a teal scarf, "
            "and one stickman on the right wearing a yellow scarf. They sit together peacefully with gentle curved smiles on their white round faces. "
            "Minimalist warm off-white cafe background. Crisp flat 2D line art, clean silhouette, contentment readable in pose, soft consistent lighting."
        ),
        "video_prompt": (
            "Two stick-figure characters: Pip in a teal scarf and the friendly stranger in a yellow scarf sitting across from each other at the cafe table. "
            "They sit peacefully together, gentle smiling and quiet companionship. Visual callback to opening composition. "
            "The camera is a static close-up shot. Only the action of this moment moves; "
            "everything else stays exactly as drawn in the same flat hand-drawn doodle cartoon style, no new objects appear."
        ),
    },
]

NEGATIVE = "extra limbs, duplicated characters, inconsistent clothes, changed head/body proportions, malformed hands, random text, logos, watermark, unwanted objects, style drift, 3d render, photo"
LORA4 = "minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors"
CLIP_W, CLIP_H = 480, 832


def generate_clips():
    pipe = ChronoFlowPipeline()
    print("=== STAGE 2: CHRONOFLOW VIDEO GENERATION ===")
    for shot in SHOTS:
        clip_file = CLIP_DIR / f"{shot['id']}.mp4"
        if clip_file.exists() and clip_file.stat().st_size > 0:
            print(f"Clip {shot['id']} already exists ({clip_file.stat().st_size} bytes), skipping.")
            continue

        panel = IMG_DIR / f"{shot['id']}.png"
        if not panel.exists():
            print(f"Error: image {panel} missing!")
            sys.exit(1)

        input_name = f"c006_{shot['id']}.png"
        shutil.copy2(panel, COMFY_INPUT_DIR / input_name)

        print(f"\n--- Rendering ChronoFlow Clip {shot['id']} ---")
        print(f"Prompt: {shot['video_prompt'][:90]}...")
        t0 = time.time()
        graph = pipe.build_h3_prompt(
            prompt=shot["video_prompt"],
            width=CLIP_W,
            height=CLIP_H,
            length=124,
            steps=4,
            lora_name=LORA4,
            workflow_mode="sliding_window",
            first_frame_filename=input_name,
            seed=shot["seed_clip"],
            fast_h3=False,
        )

        res = asyncio.run(pipe.execute_prompt(graph))
        elapsed = time.time() - t0
        shutil.copy2(res, clip_file)
        print(f"Clip {shot['id']}.mp4 generated in {elapsed:.1f}s ({clip_file.stat().st_size} bytes)")


if __name__ == "__main__":
    generate_clips()
