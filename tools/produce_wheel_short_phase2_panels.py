"""Production Script for Short #1: The Dumbest Man Who Changed History.
Phase 2: Generates Scenes 2 to 7 illustrations using Qwen Image 2.1 Turbo with Scene 1 as the character reference anchor.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.comfyui import ComfyUIClient, ComfyWorkflowRegistry
from engine.comfyui.art import ArtEngine

PROJECT_DIR = Path("output/shorts/wheel_short")
PANELS_DIR = PROJECT_DIR / "panels"
SCENE_1_ANCHOR = PANELS_DIR / "scene_1.png"

UNIVERSAL_NEGATIVE = (
    "photorealistic, 3d render, cgi, glossy digital painting, anime, modern vector graphics, neon glow, smooth gradients, "
    "highly detailed anatomy, plastic, polished cartoon aesthetics, sharp geometric lines, volumetric lighting, bloom, text, speech bubbles"
)

SCENE_PROMPTS = [
    (2, (
        "The same prehistoric caveman kneeling on the golden savanna, placing a round wooden wheel underneath a huge rectangular stone. "
        "He looks extremely confident, while three primitive tribe members watch with confused expressions. "
        "Simple wooden sticks, stones and dry grass around them. Consistent character designs and clothing. "
        "Primitive hand-drawn folk-art storybook style, rough black outlines, flat ochre colors, colored-pencil texture, vertical 9:16 composition."
    )),
    (3, (
        "The prehistoric inventor proudly sitting on top of a simple wooden cart with four wooden wheels, holding his arms in the air like a victorious king. "
        "Two tribe members stare at him with shocked expressions. Golden grassland, distant purple hills, primitive trees. "
        "Same recurring characters, ragged brown clothing, naive hand-drawn folk-art illustration, rough pencil outlines, earthy colors, vertical 9:16."
    )),
    (4, (
        "The same wooden cart rolling uncontrollably down a steep golden-brown hill. "
        "The caveman inventor is sitting on top, eyes wide open, mouth screaming, arms waving wildly. "
        "Several tribe members run behind him in panic. Dust clouds and scattered stones. "
        "Funny exaggerated expressions, primitive hand-drawn children's folk-art illustration, consistent characters, vertical 9:16."
    )),
    (5, (
        "The wooden cart crashes into the middle of a primitive village. Wooden huts, scattered baskets and clay pots fly through the air. "
        "The inventor is thrown upward with a ridiculous shocked expression. Tribe members jump away in panic. "
        "Funny chaotic composition, warm golden savanna, rough hand-drawn folk-art illustration, colored pencil texture, vertical 9:16."
    )),
    (6, (
        "The prehistoric inventor sitting sadly in a pile of straw, covered in dust. "
        "An elderly bearded tribe member stands beside him, pointing at the broken wooden cart with an impressed expression. "
        "Other tribe members gather around, looking amazed. The old man holds up one of the wooden wheels. "
        "Hand-drawn primitive folk-art storybook style, warm ochre palette, vertical 9:16."
    )),
    (7, (
        "The entire prehistoric tribe happily riding in several primitive wooden carts across the golden savanna. "
        "The original inventor walks behind them carrying a large wooden sign showing a simple crossed-out coin symbol without any words, looking exhausted and angry. "
        "The elderly man proudly rides the biggest cart. Funny visual ending, naive primitive folk-art children's book illustration, warm earthy colors, rough pencil outlines, vertical 9:16."
    )),
]

def main():
    print("--- STEP 3: Generating Scenes 2-7 with Reference Image Conditioning ---")
    client = ComfyUIClient()
    reg = ComfyWorkflowRegistry(client)
    engine = ArtEngine(client, reg)

    for num, prompt in SCENE_PROMPTS:
        out_png = PANELS_DIR / f"scene_{num}.png"
        if out_png.exists() and out_png.stat().st_size > 0:
            print(f"Scene {num} already exists, skipping.")
            continue
        print(f"\nGenerating Scene {num} (referenced from scene_1.png)...")
        t0 = time.monotonic()
        art = engine.generate(
            prompt=prompt,
            negative_prompt=UNIVERSAL_NEGATIVE,
            width=768,
            height=1344,
            seed=100 + num,
            prefix=f"shorts/wheel_p{num}",
            reference_image=SCENE_1_ANCHOR,
        )
        elapsed = time.monotonic() - t0
        out_png.write_bytes(art.png)
        print(f"  -> Saved {out_png.name} ({len(art.png)} bytes) in {elapsed:.1f}s")

    print("\nAll 7 Scene Illustrations Complete!")

if __name__ == "__main__":
    main()
