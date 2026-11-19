"""Thumbnail (cover) for r16 'Who Keeps Eating My Lunch?': three picture variants, then the title drawn by PIL (the art models must not draw text).
  python tools/reels/thumb_lunch.py art       a, b = Z-Image Turbo (keeps the stickman style), c = HiDream
  python tools/reels/thumb_lunch.py compose   adds the title in Impact -> thumb_{a,b,c}.jpg   (1080x1920, subject + title inside the centre 3:4 band)
REEL_OUT_DIR as for make_reel.py. Needs ComfyUI on :8188."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "output" / os.environ.get("REEL_OUT_DIR", "intel_test") / os.environ.get("THUMB_SLUG", "r16_lunch_thief") / "thumb"
W, H = 1080, 1920
TITLE, COLOR, TITLE_Y = "LUNCH THIEF!", "#FFE600", 300
LOOK = ("funny hand-drawn cartoon doodle, simple stick-figure style, thick black marker outlines, ultra saturated flat colors, strong color contrast, "
         "vertical 9:16 composition, plain pale blue office background with a soft glow, empty space at the top and bottom, no text, no letters, no numbers, no words. ")
BOSS = ("Extreme close-up of a chubby completely bald stick-figure boss in a light green shirt and a dark green tie, his whole face bright red, steam shooting out of both ears, "
         "eyes huge and watering, tongue sticking out, holding half a sandwich with one giant glowing red chili pepper sticking out of it; "
         "in the lower corner a small smirking stick-figure guy with spiky black hair and a blue t-shirt watches him with his arms crossed.")
HERO = ("Extreme close-up of a smirking stick-figure guy with spiky black hair and a blue t-shirt grinning evilly and holding up a sandwich with one giant glowing red chili pepper "
        "sticking out of it, tiny flames around the chili, a small bald chubby boss in a green tie peeking hungrily from the lower corner.")
SPLIT = ("Split-screen divided by a white zigzag line, both halves vertically centered with empty space above and below. LEFT half pale blue: a smirking spiky-haired stick-figure guy in a blue t-shirt "
         "holding a sandwich with a huge glowing red chili. RIGHT half hot orange: a chubby bald stick-figure boss in a green tie with a bright red face and steam shooting from his ears, tongue out, eyes watering.")
SCENES = {"boss": LOOK + BOSS, "hero": LOOK + HERO, "split": LOOK + SPLIT}
if os.environ.get("THUMB_STYLE") == "anime":  # same idea in the r17 anime look (cel shaded, adult hero, one bald boss)
    ANIME = ("high quality modern anime key visual, cel shaded, clean line art, vibrant saturated colors, soft glow and rim light, big shiny eyes, vertical 9:16 composition, "
             "plain pale blue office background, empty space at the top and bottom, no text, no letters, no numbers, no words. ")
    SCENES = {"boss": ANIME + "Extreme close-up of a chubby completely bald anime middle-aged boss in a light green shirt and a dark green tie, his whole face bright red, steam shooting out of both ears, "
              "eyes huge and watering, tongue sticking out, holding half a sandwich with one giant glowing red chili pepper sticking out of it; in the lower corner a smirking tall adult anime man with spiky "
              "black hair and a blue t-shirt watches him with his arms crossed.",
              "hero": ANIME + "Extreme close-up of a smirking adult anime man with spiky black hair and a blue t-shirt grinning evilly and holding up a sandwich with one giant glowing red chili pepper sticking out of it, "
              "tiny flames around the chili, a small chubby bald boss in a green tie peeking hungrily from the lower corner."}
    SCENES["split"] = SCENES["hero"]
# tag -> (workflow, seed, scene). a-c were the first round (c = HiDream, not wanted); d-g are the Z-Image round.
VARIANTS = {"a": ("zimage_turbo", 41, "boss"), "b": ("zimage_turbo", 42, "boss"), "c": ("hidream_i1_fast", 43, "boss"),
            "d": ("zimage_turbo", 44, "boss"), "e": ("zimage_turbo", 45, "hero"), "f": ("zimage_turbo", 46, "hero"), "g": ("zimage_turbo", 47, "split")}
ONLY = os.environ.get("THUMB_TAGS", "defg")


def stage_art():
    from engine.comfyui import ComfyUIClient, ComfyWorkflowRegistry
    from engine.comfyui.art import ArtEngine
    client = ComfyUIClient()
    engine = ArtEngine(client, ComfyWorkflowRegistry(client))
    OUT.mkdir(parents=True, exist_ok=True)
    for tag, (wf, seed, scene) in VARIANTS.items():
        if tag not in ONLY:
            continue
        dest = OUT / f"art_{tag}.png"
        if dest.exists() and dest.stat().st_size:
            continue
        dest.write_bytes(engine.generate(SCENES[scene], width=768, height=1344, seed=seed, prefix=f"reels/r16_thumb_{tag}", workflow_id=wf).png)
        print("thumb art", tag, wf, flush=True)


def stage_compose():
    from PIL import Image, ImageDraw, ImageFont
    for tag in ONLY:
        src = OUT / f"art_{tag}.png"
        if not src.exists():
            continue
        im = Image.open(src).convert("RGB").resize((W, H), Image.LANCZOS)
        d = ImageDraw.Draw(im)
        size = 200
        while d.textlength(TITLE, font=ImageFont.truetype("C:/Windows/Fonts/impact.ttf", size)) > W - 140 and size > 90:
            size -= 6
        font = ImageFont.truetype("C:/Windows/Fonts/impact.ttf", size)
        x = (W - d.textlength(TITLE, font=font)) / 2
        d.text((x + 8, TITLE_Y + 10), TITLE, font=font, fill="#000000", stroke_width=22, stroke_fill="#000000")
        d.text((x, TITLE_Y), TITLE, font=font, fill=COLOR, stroke_width=22, stroke_fill="#000000")
        im.save(OUT / f"thumb_{tag}.jpg", quality=92)
        print("composed", tag)


if __name__ == "__main__":
    {"art": stage_art, "compose": stage_compose}[sys.argv[1] if len(sys.argv) > 1 else sys.exit(__doc__)]()
