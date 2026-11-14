"""Generate master anchors for Environment and Secondary Characters in Nine Heavens Eclipse.

Anchors generated:
1. abyssal_quarry_anchor.png (The locked environment vista)
2. lingxiao_enforcer_anchor.png (The locked imperial soldier armor & helmet)
3. commander_meng_anchor.png (The locked lead enforcer officer)
4. li_ming_anchor.png (The locked elderly quarry slave)
"""
from pathlib import Path
from engine.comfyui.art import ArtEngine

def main():
    art = ArtEngine()
    env_dir = Path("output/series_1000/environment_anchors")
    char_dir = Path("output/series_1000/character_anchors")
    env_dir.mkdir(parents=True, exist_ok=True)
    char_dir.mkdir(parents=True, exist_ok=True)

    anchors = [
        {
            "path": env_dir / "abyssal_quarry_anchor.png",
            "prompt": (
                "Cinematic manhua environment key visual, wide panoramic vista of the Abyssal Basalt Quarry. "
                "Massive vertical hexagonal black basalt cliff walls with sharp angular rock fractures, "
                "luminescent violet crystal ore veins embedded in the wet rock emitting soft purple glow. "
                "Terraced quarry ledges of rain-slicked dark obsidian flagstones and crushed black gravel. "
                "Cold driving torrential rain, heavy rolling fog, dark stormy twilight with a faint purple eclipse halo in the sky. "
                "Flickering warm amber torchlight from rusted iron braziers on stone ledges. "
                "Atmospheric matte painting, dramatic depth, hyper-detailed, masterpiece, 8k, no characters, no people."
            ),
            "neg": "people, human, face, hands, body, character, modern buildings, bright sunny day, blurry, low quality",
            "seed": 88001,
            "prefix": "env_quarry",
        },
        {
            "path": char_dir / "lingxiao_enforcer_anchor.png",
            "prompt": (
                "Character design turnaround key visual, Lingxiao Iron Enforcer soldier standing in dark rain. "
                "Clad in uniform matte-black spiked segmented iron plate armor, sharp angular iron pauldrons. "
                "Full-face iron barbute helmet completely concealing the face, with a single narrow glowing crimson horizontal visor slit. "
                "Wielding a heavy double-edged serrated black steel polearm halberd with both gauntleted hands. "
                "Heavy black iron combat boots planted on wet dark stone. Raindrops splashing off the black iron plate. "
                "Intricate digital ink lineart, high contrast chiaroscuro, cinematic manhua art, masterpiece, 8k key visual."
            ),
            "neg": "shiny silver armor, gold armor, open face, human skin, bare face, blurry, low quality, distorted limbs",
            "seed": 88002,
            "prefix": "char_enforcer",
        },
        {
            "path": char_dir / "commander_meng_anchor.png",
            "prompt": (
                "Character design key visual, Commander Meng, brutal imperial enforcer officer. "
                "Towering muscular man in his late 30s with fierce ruthless scowl, jagged battle scar across his lower jaw. "
                "Wearing heavy black-and-crimson spiked plate armor with a silver dragon motif embossed on the right pauldron. "
                "Black hair tied back in a warrior topknot, rain dripping down his face. "
                "Resting one hand on the hilt of a massive serrated executioner broadsword sheathed at his hip. "
                "Cinematic manhua art, high contrast ink shadows, volumetric rain lighting, masterpiece, 8k."
            ),
            "neg": "blonde hair, delicate features, clean face, modern clothes, blurry, low quality, deformed hands",
            "seed": 88003,
            "prefix": "char_commander",
        },
        {
            "path": char_dir / "li_ming_anchor.png",
            "prompt": (
                "Character design key visual, Li Ming, elderly quarry slave. "
                "Weathered Asian man in his 60s with hollow gaunt cheeks, tired deep-set dark eyes, scraggly gray beard stubble. "
                "Wearing a frayed dark brown burlap mining vest over tattered linen rags, dust-stained skin, rope belt around waist. "
                "Holding a sputtering iron torch in trembling weathered hands, warm amber glow illuminating his fearful expression. "
                "Cinematic manhua illustration, emotive storytelling, high contrast chiaroscuro, masterpiece, 8k."
            ),
            "neg": "young, muscular, armor, clean clothes, smooth skin, modern, blurry, low quality",
            "seed": 88004,
            "prefix": "char_liming",
        },
    ]

    for item in anchors:
        out_p = item["path"]
        if out_p.exists():
            print(f"Anchor already exists: {out_p.name} ({out_p.stat().st_size} bytes)")
            continue
        print(f"Generating anchor: {out_p.name}...")
        img = art.generate(
            prompt=item["prompt"],
            negative_prompt=item["neg"],
            width=1344,
            height=768,
            seed=item["seed"],
            prefix=item["prefix"],
        )
        with open(out_p, "wb") as f:
            f.write(img.png)
        print(f"✓ Generated and saved: {out_p.name} ({len(img.png)} bytes)")

if __name__ == "__main__":
    main()
