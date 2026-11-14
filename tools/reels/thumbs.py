"""Thumbnails / Reel covers for the ten reels (1080x1920, subject + title inside the centre 3:4 band so the Instagram grid crop keeps them).

  python tools/reels/thumbs.py art [slug-prefix ...]       two Qwen Image variants per reel (seeds A/B) -> output/reels/<slug>/thumb/art_{a,b}.png
  python tools/reels/thumbs.py compose [slug-prefix ...]   adds the title (Impact, outlined) -> thumb_{a,b}.jpg

Rules baked into the prompts (from the thumbnail research): ONE huge expressive face, one clear idea, saturated high-contrast colours,
clean background, empty bands top and bottom for the title, and a curiosity gap in the 1-4 word title. The model draws NO text; PIL does.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from specs import NEGATIVE, REELS  # noqa: E402

OUT = ROOT / "output" / "reels"
W, H = 1080, 1920
LOOK = ("funny hand-drawn cartoon doodle, simple stick-figure style characters with giant round heads, huge dot eyes and extremely exaggerated "
        "facial expression, very thick black marker outlines, ultra saturated flat colors, strong color contrast, bold simple shapes, "
        "vertical 9:16 composition, main subject large and centered in the middle of the frame, plain uncluttered background with a soft glow, "
        "empty space at the top and bottom, no text, no letters, no numbers, no words")

# slug -> (title, title colour, scene prompt). Titles stay <= 4 words and create a question the video answers.
THUMBS = {
    "r01_one_percent": ("1% LEFT!!", "#FFE600",
        "extreme close-up of a stick-figure guy in a red t-shirt with messy black hair screaming in terror, eyes huge, sweat drops flying, "
        "holding a smartphone toward the viewer whose screen shows one tiny glowing red battery icon, background split hot red and yellow with a warning glow"),
    "r02_ac_war": ("THE AC WAR", "#FFFFFF",
        "a stick-figure husband with a thick black mustache and a stick-figure wife with a hair bun and no mustache glaring at each other nose to nose, "
        "each aiming a remote control like a pistol, a lightning bolt between their eyes, left half of the background icy blue with icicles, right half hot orange with flames"),
    "r03_study_plan": ("PLAN vs REALITY", "#FFE600",
        "split-screen divided by a vertical white lightning bolt, both halves vertically centered with empty space above and below; "
        "LEFT half bright orange: a stick-figure student with big round glasses and a green hoodie wearing a towel cape posing heroically with a fist raised on a stack of books; "
        "RIGHT half dark blue: the same student asleep face-down drooling on an open book with a phone showing a cat"),
    "r04_five_minutes": ("JUST 5 MINUTES", "#00E5FF",
        "extreme close-up of a stick-figure guy's face in bed with huge bloodshot red eyes and dark circles, his face lit electric blue by a phone, "
        "a bright sunrise exploding behind him through the window and an alarm clock jumping, dark navy background"),
    "r05_mom_radar": ("MOM RADAR", "#FFE600",
        "a huge stick-figure mom with a hair bun in a green kurta with giant glowing green eyes and a radar antenna on her head sending green scanning rings, "
        "towering over a tiny scared kid in a yellow t-shirt who is hiding a bag of chips behind his back, warm cream kitchen background"),
    "r06_exam_brain": ("BRAIN LEFT?!", "#FFFFFF",
        "on the left a stick-figure student in a yellow t-shirt with a blank shocked face and an empty head, on the right a big cute pink cartoon brain character "
        "almost as tall as the student, with tiny arms and legs, walking away carrying a small brown suitcase and waving goodbye, both large and fully visible, bright lime green background"),
    "r07_snooze_mafia": ("ALARM #6", "#FFE600",
        "a stick-figure guy in blue striped pajamas sprinting with a toothbrush in his mouth and flying toast, panicked wide eyes, "
        "a giant ringing alarm clock with angry eyes chasing him, motion speed lines, bold orange and blue background"),
    "r08_wifi_down": ("WI-FI DOWN!", "#FFE600",
        "a stick-figure family of four in a row, dad with a mustache and glasses, mom with a hair bun, a teenage girl and a small boy, all holding dead black phones "
        "with their mouths open in a horrified scream, a smoking broken router glowing red in front of them, deep purple background"),
    "r09_group_project": ("4 PEOPLE. 1 WORKER.", "#FFFFFF",
        "a very tired stick-figure student with glasses and a purple shirt buried under a mountain of papers and five coffee cups with spiral eyes, "
        "behind him three smug stick-figure classmates in sunglasses relaxing and giving thumbs up, bright yellow background"),
    "r10_dad_love": ("DAD NEVER SAID...", "#FFFFFF",
        "extreme close-up of a stern stick-figure dad with a thick mustache and a flat cap, arms crossed, one single glistening tear secretly rolling down his cheek, "
        "a tiny stick-figure son in a blue jacket looking up at him, warm golden sunset glow background"),
}


# slug -> (variant chosen after looking at both, title top y). Titles go where the picture is empty (never over a face).
FINAL = {"r01_one_percent": ("b", 1330), "r02_ac_war": ("b", 300), "r03_study_plan": ("a", 240), "r04_five_minutes": ("b", 1330),
         "r05_mom_radar": ("b", 300), "r06_exam_brain": ("b", 1240), "r07_snooze_mafia": ("b", 300), "r08_wifi_down": ("a", 300),
         "r09_group_project": ("a", 1300), "r10_dad_love": ("b", 1500)}


ONE_LINE = {"r10_dad_love"}


def pick(slugs):
    chosen = [s for s in THUMBS if not slugs or any(s.startswith(p) for p in slugs)]
    if not chosen:
        sys.exit(f"no thumbnail matches {slugs}")
    return chosen


def stage_art(slugs):
    from engine.comfyui import ComfyUIClient, ComfyWorkflowRegistry
    from engine.comfyui.art import ArtEngine
    client = ComfyUIClient()
    engine = ArtEngine(client, ComfyWorkflowRegistry(client))
    for slug in slugs:
        n = [r["slug"] for r in REELS].index(slug)
        for k, tag in enumerate("ab"):
            out = OUT / slug / "thumb" / f"art_{tag}.png"
            if out.exists() and out.stat().st_size:
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            art = engine.generate(prompt=f"{LOOK}. Scene: {THUMBS[slug][2]}.", negative_prompt=NEGATIVE, width=768, height=1344,
                                  seed=7000 + 10 * n + k, prefix=f"reels/{slug}_thumb_{tag}")
            out.write_bytes(art.png)
            print(f"thumb art {slug} {tag}")


def stage_compose(slugs):
    from PIL import Image, ImageDraw, ImageFont
    font_path = "C:/Windows/Fonts/impact.ttf"
    for slug in slugs:
        title, color, _ = THUMBS[slug]
        for tag in "ab":
            src = OUT / slug / "thumb" / f"art_{tag}.png"
            if not src.exists():
                continue
            im = Image.open(src).convert("RGB").resize((W, H), Image.LANCZOS)
            d = ImageDraw.Draw(im)
            words = title.split()
            lines = [title] if (len(title) <= 11 or slug in ONE_LINE) else [" ".join(words[:len(words) // 2 or 1]), " ".join(words[len(words) // 2 or 1:])]
            size = 200
            while True:  # shrink until the widest line fits the 3:4-safe width
                font = ImageFont.truetype(font_path, size)
                if max(d.textlength(t, font=font) for t in lines) <= W - 140 or size < 90:
                    break
                size -= 6
            y = FINAL[slug][1]  # inside the centre 3:4 band (y 240-1680) so the Instagram grid keeps it
            for t in lines:
                x = (W - d.textlength(t, font=font)) / 2
                d.text((x + 8, y + 10), t, font=font, fill="#000000", stroke_width=22, stroke_fill="#000000")  # drop shadow
                d.text((x, y), t, font=font, fill=color, stroke_width=22, stroke_fill="#000000")
                y += int(size * 1.08)
            dest = OUT / slug / "thumb" / f"thumb_{tag}.jpg"
            im.save(dest, quality=92)
            print("composed", dest)


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("art", "compose"):
        sys.exit(__doc__)
    {"art": stage_art, "compose": stage_compose}[sys.argv[1]](pick(sys.argv[2:]))
