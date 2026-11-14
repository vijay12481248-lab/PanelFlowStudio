"""Tales Talk channel banner: ArtEngine picture with empty centre + the title lettered on top.

YouTube banner = 2560x1440; every device shows the centre 1235x338 safe area, desktop shows 2560x423.
Usage: python tools/generate_tales_talk_banner.py [seed]   (ComfyUI must be running)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw, ImageFont

from engine.comfyui import ComfyUIClient, ComfyWorkflowRegistry
from engine.comfyui.art import ArtEngine

OUT = Path("output/shorts/wheel_short/branding")
SEED = int(sys.argv[1]) if len(sys.argv) > 1 else 4242

PROMPT = (
    "A very wide prehistoric comedy panorama on a warm savanna, everything arranged in one horizontal band across the middle of the picture, "
    "plain empty sky above and plain empty grass below. On the far left, four clumsy cavemen with oversized round heads and thin stick limbs "
    "tumble downhill chasing runaway wooden wheels; this group fills only the left fifth of the picture. On the far right, a tiny proud white chicken "
    "stands on a stone like a king while three cavemen kneel before it; this group fills only the right fifth of the picture. "
    "The whole middle sixty percent of the picture is flat empty open savanna and sky with nothing in it at all. "
    "Naive hand-drawn folk-art children's storybook illustration, rough black pencil outlines, colored pencil texture, "
    "warm ochre, dusty brown, olive green and faded beige palette, aged paper texture."
)
NEGATIVE = (
    "photorealistic, 3d render, cgi, glossy digital painting, anime, modern vector graphics, neon glow, smooth gradients, "
    "plastic, sharp geometric lines, volumetric lighting, bloom, text, words, letters, logo, watermark, characters in the middle"
)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    engine = ArtEngine(ComfyUIClient(), ComfyWorkflowRegistry(ComfyUIClient()))
    art = engine.generate(prompt=PROMPT, negative_prompt=NEGATIVE, width=1344, height=768, seed=SEED, prefix="branding/tales_talk_banner")
    raw = OUT / f"tales_talk_banner_art_{SEED}.png"
    raw.write_bytes(art.png)

    img = Image.open(raw).convert("RGB").resize((2560, 1440), Image.LANCZOS)
    d = ImageDraw.Draw(img)
    cx, cy = 1280, 720
    title = ImageFont.truetype("C:/Windows/Fonts/Inkfree.ttf", 230)
    tag = ImageFont.truetype("C:/Windows/Fonts/Inkfree.ttf", 74)
    ink, paper = (38, 24, 14), (255, 244, 214)
    d.text((cx, cy - 40), "Tales Talk", font=title, fill=ink, anchor="mm", stroke_width=10, stroke_fill=paper)
    d.text((cx, cy + 120), "Humanity's dumbest great ideas", font=tag, fill=ink, anchor="mm", stroke_width=6, stroke_fill=paper)
    final = OUT / f"tales_talk_banner_{SEED}.png"
    img.save(final)
    print(final)


if __name__ == "__main__":
    main()
