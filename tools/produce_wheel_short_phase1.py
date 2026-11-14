"""Production Script for Short #1: The Dumbest Man Who Changed History.
Phase 1: Synthesizes all 7 voiceover segments via Kokoro TTS and generates Scene 1 (Master Anchor) via Qwen Image 2.1 Turbo.
"""
import os
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import soundfile as sf
from engine.narration.runtime.audio import KokoroTts
from engine.comfyui import ComfyUIClient, ComfyWorkflowRegistry
from engine.comfyui.art import ArtEngine

PROJECT_DIR = Path("output/shorts/wheel_short")
PROJECT_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_DIR = PROJECT_DIR / "audio"
PANELS_DIR = PROJECT_DIR / "panels"
AUDIO_DIR.mkdir(exist_ok=True)
PANELS_DIR.mkdir(exist_ok=True)

NARRATIONS = [
    (1, "Thousands of years ago, one idiot had an idea that changed the world!"),
    (2, "He discovered that putting a round thing under a heavy thing... makes the heavy thing move!"),
    (3, "Suddenly, he became the smartest man in the entire tribe!"),
    (4, "But he forgot ONE tiny detail... brakes!"),
    (5, "He destroyed the village... his house... and probably his marriage!"),
    (6, "But the old man saw something different. He saw the future!"),
    (7, "And that's how humanity got the wheel... and the inventor got absolutely NOTHING!"),
]

SCENE_1_PROMPT = (
    "A primitive prehistoric caveman standing in the middle of a golden-yellow savanna, "
    "holding a large perfectly round wooden wheel above his head, looking extremely proud and excited. "
    "Several other primitive tribe members in simple ragged brown clothing are standing behind him, laughing and pointing fingers at him. "
    "Oversized round heads, thin stick-like limbs, funny expressive faces. "
    "Wide vertical 9:16 composition, hand-drawn naive folk-art children's storybook illustration, "
    "rough black pencil outlines, imperfect colored-pencil strokes, warm ochre and dusty brown palette, watercolor paper texture."
)

UNIVERSAL_NEGATIVE = (
    "photorealistic, 3d render, cgi, glossy digital painting, anime, modern vector graphics, neon glow, smooth gradients, "
    "highly detailed anatomy, plastic, polished cartoon aesthetics, sharp geometric lines, volumetric lighting, bloom, text, speech bubbles"
)

def step1_audio():
    print("--- STEP 1: Synthesizing Kokoro TTS Narration (7 scenes) ---")
    tts = KokoroTts()
    manifest = []
    for num, text in NARRATIONS:
        out_wav = AUDIO_DIR / f"scene_{num}.wav"
        print(f"Synthesizing Scene {num}: '{text[:40]}...'")
        samples = tts.synth(text, voice="am_adam", rate=1.12)
        sf.write(out_wav, samples, 24000)
        dur = len(samples) / 24000
        print(f"  -> {out_wav.name} ({dur:.2f}s)")
        manifest.append({"scene": num, "text": text, "audio": str(out_wav), "duration": dur})
    return manifest

def step2_scene1_master():
    print("\n--- STEP 2: Generating Scene 1 Master Anchor Image via Qwen Image 2.1 (768x1344) ---")
    client = ComfyUIClient()
    reg = ComfyWorkflowRegistry(client)
    engine = ArtEngine(client, reg)

    out_png = PANELS_DIR / "scene_1.png"
    print("Submitting prompt to ComfyUI (Qwen Image 2.1 Turbo)...")
    t0 = time.monotonic()
    art = engine.generate(
        prompt=SCENE_1_PROMPT,
        negative_prompt=UNIVERSAL_NEGATIVE,
        width=768,
        height=1344,
        seed=101,
        prefix="shorts/wheel_p1"
    )
    elapsed = time.monotonic() - t0
    out_png.write_bytes(art.png)
    print(f"  -> Generated {out_png.name} ({art.width}x{art.height}, {len(art.png)} bytes) in {elapsed:.1f}s")
    return str(out_png)

def main():
    manifest = step1_audio()
    scene1_path = step2_scene1_master()

    summary_file = PROJECT_DIR / "manifest.json"
    data = {
        "title": "The Dumbest Man Who Changed History",
        "genre": "Comedy / Unexpected twist",
        "aspect_ratio": "9:16",
        "resolution": [768, 1344],
        "scenes": manifest,
        "master_anchor_image": scene1_path
    }
    summary_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"\nPhase 1 Complete! Manifest saved to {summary_file}")

if __name__ == "__main__":
    main()
