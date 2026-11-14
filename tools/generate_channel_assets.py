"""Generate YouTube Channel Branding Assets: Avatar and Banner."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.comfyui import ComfyUIClient, ComfyWorkflowRegistry
from engine.comfyui.art import ArtEngine

BRAND_DIR = Path("output/shorts/wheel_short/branding")
BRAND_DIR.mkdir(parents=True, exist_ok=True)

AVATAR_PROMPT = (
    "A close-up portrait of a funny primitive caveman inventor, oversized round head, wild messy dark hair, "
    "funny wide expressive eyes with tiny pupils, goofy proud grin, thin stick-like neck. "
    "He holds a tiny perfectly round wooden wheel like a prized jewel. "
    "Naive hand-drawn folk-art children's book illustration style, rough black pencil and ink contours, "
    "colored pencil and crayon texture, flat muted earthy ochre and warm beige palette, textured aged watercolor paper background, "
    "circular balanced composition, iconic logo avatar."
)

BANNER_PROMPT = (
    "A wide panoramic prehistoric comedy scene on a warm golden-yellow savanna. "
    "On the left, clumsy primitive cavemen with oversized round heads and thin stick limbs are chasing runaway wooden wheels and rolling down hills. "
    "In the center, an empty clear space against the warm sky. "
    "On the right, a tiny innocent chicken proudly stands on a stone like a king while primitive tribe members kneel before it. "
    "Naive primitive folk-art children's storybook illustration style, rough black pencil outlines, "
    "colored pencil texture, warm ochre, dusty brown, olive green, and faded beige palette, wide panoramic landscape."
)

UNIVERSAL_NEGATIVE = (
    "photorealistic, 3d render, cgi, glossy digital painting, anime, modern vector graphics, neon glow, smooth gradients, "
    "highly detailed anatomy, plastic, polished cartoon aesthetics, sharp geometric lines, volumetric lighting, bloom, text, words, logo"
)

def main():
    client = ComfyUIClient()
    reg = ComfyWorkflowRegistry(client)
    engine = ArtEngine(client, reg)

    # 1. Avatar (1024x1024 Square)
    avatar_path = BRAND_DIR / "channel_avatar.png"
    print("Generating Channel Avatar (1024x1024)...")
    t0 = time.monotonic()
    art_avatar = engine.generate(
        prompt=AVATAR_PROMPT,
        negative_prompt=UNIVERSAL_NEGATIVE,
        width=1024,
        height=1024,
        seed=777,
        prefix="branding/avatar"
    )
    avatar_path.write_bytes(art_avatar.png)
    print(f"  -> Saved {avatar_path.name} in {time.monotonic()-t0:.1f}s ({len(art_avatar.png)} bytes)")

    # 2. Banner (1344x768 Landscape)
    banner_path = BRAND_DIR / "channel_banner.png"
    print("\nGenerating Channel Banner (1344x768)...")
    t1 = time.monotonic()
    art_banner = engine.generate(
        prompt=BANNER_PROMPT,
        negative_prompt=UNIVERSAL_NEGATIVE,
        width=1344,
        height=768,
        seed=888,
        prefix="branding/banner"
    )
    banner_path.write_bytes(art_banner.png)
    print(f"  -> Saved {banner_path.name} in {time.monotonic()-t1:.1f}s ({len(art_banner.png)} bytes)")

    print("\nChannel Branding Assets Generated Successfully!")

if __name__ == "__main__":
    main()
