"""Generate a Mahabharata story episode and render panels using PanelFlow Studio's single art workflow (Qwen Image 2.1)."""
import json
import os
import sys
import time
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, ".")

# Set up ComfyUI environment
os.environ["PANELFLOW_COMFYUI_WORKFLOW_DIR"] = r"E:\VIJAY SEKAR\ComfyUI\workflow"

from engine.original.models import (
    Bible, Character, Location, Premise, OriginalStory, Panel, Scene
)
from engine.original.shotspec import ShotSpec, CharPose, compose_natural
from engine.original.art import ComfyRunner, sheet_prompt, seed_for

WS_DIR = Path("output/Original_Stories/mahabharata_kurukshetra")
PANELS_DIR = WS_DIR / "panels"
SHEETS_DIR = WS_DIR / "sheets"
PANELS_DIR.mkdir(parents=True, exist_ok=True)
SHEETS_DIR.mkdir(parents=True, exist_ok=True)

# 1. Define Bible
premise = Premise(
    title="The Chariot at Kurukshetra",
    genre="fantasy",
    logline="On the sacred plains of Kurukshetra, Prince Arjuna is overcome with despair before the great war, until Krishna imparts timeless wisdom.",
    tone="epic, solemn, majestic, spiritual",
    setting="The ancient battlefield of Kurukshetra between two colossal armies"
)

arjuna = Character(
    id="arjuna",
    name="Arjuna",
    role="protagonist",
    age_group="adult",
    species="human",
    gender="male",
    look="athletic warrior, black hair in warrior topknot, piercing intense eyes, golden plate armor, ornate silver diadem, holding divine longbow Gandiva",
    personality="noble, compassionate, peerless master archer"
)

krishna = Character(
    id="krishna",
    name="Krishna",
    role="mentor",
    age_group="adult",
    species="human",
    gender="male",
    look="serene divine countenance, dark sapphire skin, lotus eyes, peacock feather in ornate golden crown, draped in flowing golden-yellow silk, holding reins",
    personality="tranquil, all-knowing, compassionate guide"
)

loc = Location(
    id="kurukshetra",
    name="Kurukshetra Battlefield",
    look="vast sunlit plain, twin massive armies in distant ranks, fluttering silk battle standards, ancient golden war chariot with four white horses"
)

bible = Bible(
    premise=premise,
    characters=[arjuna, krishna],
    locations=[loc],
    rules=[
        "The chariot of Arjuna and Krishna stands in the neutral middle ground between the Pandava and Kaurava armies",
        "Krishna acts as charioteer and spiritual mentor, not an armed combatant",
        "Arjuna's bow Gandiva is his sacred weapon"
    ]
)

# 2. Define Story Panels & Directed Shots
shots_data = [
    {
        "panel_id": "panel_01",
        "caption": "Between the silent ranks of two colossal armies, the golden chariot of Arjuna halts in the sacred dust of Kurukshetra.",
        "spec": ShotSpec(
            shot="wide",
            camera="eye_level",
            characters=[
                CharPose(id="arjuna", side="left", pose="standing behind the charioteer", expression="solemn awe", action="looking across the vast field"),
                CharPose(id="krishna", side="right", pose="seated holding the reins", expression="calm majestic composure", action="guiding the four white horses")
            ],
            setting="ancient golden war chariot halted between two massive silent armies in the morning light",
            lighting="golden sunrise, atmospheric mist and dust",
            mood="epic and solemn",
            key_visuals=["golden chariot", "four white horses", "vast armies in distance", "fluttering battle standards"]
        )
    },
    {
        "panel_id": "panel_02",
        "caption": "Overcome by the sight of beloved kinsmen and elders, grief shakes Arjuna as his divine bow Gandiva slips from trembling hands.",
        "spec": ShotSpec(
            shot="medium",
            camera="eye_level",
            characters=[
                CharPose(id="arjuna", side="center", pose="kneeling on one knee on chariot floor", expression="anguished face, tears in eyes", action="lowering head in sorrow with hands open as bow rests on floor")
            ],
            setting="deck of the golden chariot, divine longbow Gandiva resting on the chariot floor",
            lighting="dramatic shadows, soft morning light",
            mood="deep sorrow and moral conflict",
            key_visuals=["divine longbow on chariot floor", "anguished expression", "tears", "kneeling warrior in golden armor"]
        )
    },
    {
        "panel_id": "panel_03",
        "caption": "Lord Krishna turns with an unshakeable, tranquil smile, his lotus eyes glowing with timeless wisdom to dispel the shadow of despair.",
        "spec": ShotSpec(
            shot="close",
            camera="eye_level",
            characters=[
                CharPose(id="krishna", side="center", pose="turning head slightly with gentle grace", expression="serene tranquil smile, radiant compassionate eyes", action="reassuring gesture with one hand")
            ],
            setting="charioteer seat with soft glow around his figure",
            lighting="celestial soft golden glow, warm highlights",
            mood="divine peace and transcendent clarity",
            key_visuals=["peacock feather in crown", "serene tranquil smile", "golden pitambara silk", "radiant lotus eyes"]
        )
    },
    {
        "panel_id": "panel_04",
        "caption": "Empowered by eternal truth, Arjuna rises with burning resolve, raising the mighty Gandiva toward the morning heavens.",
        "spec": ShotSpec(
            shot="medium",
            camera="low",
            characters=[
                CharPose(id="arjuna", side="center", pose="standing upright with powerful warrior stance", expression="fierce resolute determination, confident eyes", action="firmly raising divine bow Gandiva")
            ],
            setting="standing tall on chariot deck against the rising sun and soaring eagles",
            lighting="brilliant golden sunburst directly behind him, heroic rim lighting",
            mood="unyielding resolve and spiritual victory",
            key_visuals=["raising divine bow Gandiva", "resolute warrior gaze", "golden sunrise backlight", "heroic warrior posture"]
        )
    }
]

panels = []
for item in shots_data:
    p = Panel(
        id=item["panel_id"],
        scene_id="sc01",
        shot=item["spec"].shot,
        angle=item["spec"].camera,
        location_id="kurukshetra",
        character_ids=[c.id for c in item["spec"].characters],
        action="; ".join(f"{c.pose} {c.action}" for c in item["spec"].characters),
        caption=item["caption"],
        key_visuals=item["spec"].key_visuals,
        director=item["spec"].model_dump()
    )
    panels.append(p)

story = OriginalStory(
    bible=bible,
    scenes=[Scene(id="sc01", location_id="kurukshetra", character_ids=["arjuna", "krishna"], summary="Arjuna and Krishna on the battlefield of Kurukshetra", mood="epic")],
    panels=panels
)

# Save story.json
(WS_DIR / "story.json").write_text(story.model_dump_json(indent=2), encoding="utf-8")
print(f"Saved story.json to {WS_DIR / 'story.json'}")

# 3. Generate Character Sheets & Panels with ComfyRunner
runner = ComfyRunner()
print(f"Initialized ComfyRunner (Engine: {runner.engine}, Style: {runner.style})")

art_manifest = {}

# Character Portraits
print("\n=== Generating Character Portraits ===")
for char in [arjuna, krishna]:
    sheet_path = SHEETS_DIR / f"{char.id}.png"
    if sheet_path.exists():
        print(f"Character sheet {char.id} already exists, skipping.")
        continue
    prompt = sheet_prompt(char, story, style_kind=runner.style)
    print(f"Generating sheet for {char.name}...")
    seed = seed_for(story, f"sheet_{char.id}")
    t0 = time.time()
    png_bytes = runner.generate(
        pos=prompt,
        neg="",
        seed=seed,
        width=1344,
        height=768,
        prefix=f"sheet_{char.id}"
    )
    sheet_path.write_bytes(png_bytes)
    print(f"  Saved {sheet_path.name} in {time.time()-t0:.1f}s ({len(png_bytes)/1024:.1f} KB)")

# Story Panels
print("\n=== Generating Story Panels with Natural Prompts (Qwen Image 2.1) ===")
for item in shots_data:
    pid = item["panel_id"]
    spec = item["spec"]
    out_img = PANELS_DIR / f"{pid}.png"
    
    # Prompt composed using system's compose_natural
    prompt, neg = compose_natural(story, spec, "kurukshetra")
    print(f"\n--- {pid} ({spec.shot}, {spec.camera}) ---")
    print(f"Narration: {item['caption']}")
    print(f"Composed Prompt: {prompt[:160]}...")
    
    seed = seed_for(story, pid)

    t0 = time.time()
    png_bytes = runner.generate(
        pos=prompt,
        neg=neg,
        seed=seed,
        width=1344,
        height=768,
        prefix=f"panel_{pid}",
    )
    out_img.write_bytes(png_bytes)
    dur = time.time() - t0
    print(f"  [DONE] Rendered {out_img.name} in {dur:.1f}s ({len(png_bytes)/(1024*1024):.2f} MB)")
    
    art_manifest[pid] = {
        "panel_id": pid,
        "caption": item["caption"],
        "prompt": prompt,
        "seed": seed,
        "duration_sec": round(dur, 2),
        "file_path": str(out_img)
    }

(WS_DIR / "art_manifest.json").write_text(json.dumps(art_manifest, indent=2), encoding="utf-8")

# 4. Create HTML Gallery for easy user inspection
html_rows = []
for item in shots_data:
    pid = item["panel_id"]
    img_rel = f"panels/{pid}.png"
    html_rows.append(f"""
    <div class="card">
        <img src="{img_rel}" alt="{pid}" />
        <div class="info">
            <span class="badge">{pid.upper()} - {item['spec'].shot.upper()} SHOT</span>
            <p class="caption">"{item['caption']}"</p>
            <div class="keys"><b>Key Visuals:</b> {', '.join(item['spec'].key_visuals)}</div>
        </div>
    </div>
    """)

html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>The Chariot at Kurukshetra - PanelFlow Studio</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, sans-serif; background: #0e0e12; color: #e5e5eb; margin: 0; padding: 24px; }}
        h1 {{ color: #ffd700; margin-bottom: 4px; }}
        .subtitle {{ color: #9a9ab0; margin-bottom: 24px; font-size: 14px; }}
        .gallery {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(560px, 1fr)); gap: 24px; }}
        .card {{ background: #181820; border: 1px solid #282835; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 16px rgba(0,0,0,0.4); }}
        .card img {{ width: 100%; aspect-ratio: 16/9; object-fit: cover; display: block; }}
        .info {{ padding: 16px; }}
        .badge {{ background: #ffd700; color: #111; font-weight: bold; font-size: 11px; padding: 3px 8px; border-radius: 4px; display: inline-block; margin-bottom: 8px; }}
        .caption {{ font-size: 15px; line-height: 1.5; color: #ffffff; font-style: italic; margin: 8px 0; }}
        .keys {{ font-size: 12px; color: #a0a0c0; margin-top: 6px; }}
    </style>
</head>
<body>
    <h1>The Chariot at Kurukshetra</h1>
    <div class="subtitle">Generated with PanelFlow Studio Qwen Image 2.1 engine (1344x768 16:9)</div>
    <div class="gallery">
        {''.join(html_rows)}
    </div>
</body>
</html>"""

report_file = WS_DIR / "gallery.html"
report_file.write_text(html_content, encoding="utf-8")
print(f"\n[SUCCESS] Story and images successfully generated! HTML report: {report_file}")
