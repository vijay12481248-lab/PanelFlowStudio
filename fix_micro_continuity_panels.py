"""Fix all remaining micro-continuity details across the 16-panel sequence.

Fixes:
1. Panel 004: True MCU focusing on scarred brow and glowing amethyst eyes, hands down (no anchor pose fists).
2. Panel 010: Chen Ye blocking COMMANDER MENG's executioner blade (Commander Meng on screen-right: warrior topknot, scarred jaw, dragon pauldron).
3. Panel 016: Majestic sovereign stance inside the celestial pillar of light looking up at the heavens, arms lowered (no anchor pose fists or chains).
"""
from pathlib import Path
import time
from engine.comfyui.art import ArtEngine

def main():
    art = ArtEngine()
    chen_anchor = Path("output/series_1000/character_anchors/chen_ye_anchor.png")
    meng_anchor = Path("output/series_1000/character_anchors/commander_meng_anchor.png")
    out_dir = Path("output/series_1000/episode_0001_perfect_continuity")

    # 1. Panel 004: True MCU on Eyes & Scar
    p004_prompt = (
        "Masterpiece cinematic manhua close-up portrait, Medium Close-Up (MCU). "
        "[CHARACTER: Chen Ye: young martial artist, pitch-black hair with stark snow-white streaks on left, "
        "piercing glowing amethyst-purple eyes, jagged battle scar crossing left eyebrow, pale skin with light coal dust, "
        "tattered dark gray linen tunic]. Intense steely gaze focused toward screen-right, dark rain dripping down face. "
        "Hands lowered and completely out of frame. "
        "Background: Abyssal Basalt Quarry, massive vertical black basalt cliff walls with glowing violet crystal ore veins, "
        "volumetric rain mist, high contrast ink chiaroscuro, 8k resolution, crisp linework."
    )
    p004_neg = "hands in frame, fists raised, holding chains, blurry, distorted anatomy, text artifacts"

    # 2. Panel 010: Clash with Commander Meng
    p010_prompt = (
        "Masterpiece cinematic manhua dynamic combat action clash, low-angle hero impact. "
        "On SCREEN-LEFT: Protagonist Chen Ye [CHARACTER: young martial artist, black hair with snow-white streaks, amethyst-purple eyes, "
        "tattered dark gray tunic], dynamic martial stance, his bare forearm raised to deflect a massive blow. "
        "On SCREEN-RIGHT: Commander Meng [CHARACTER: towering muscular imperial officer, black hair in warrior topknot, "
        "snarling scarred jaw, heavy black-and-crimson spiked plate armor with embossed silver dragon pauldron on shoulder], "
        "striking downward with a massive serrated executioner broadsword. "
        "Steel meeting flesh with blinding violet lightning sparks, kinetic ink-splash shockwave rings concussing the rain. "
        "Background: Abyssal Basalt Quarry, towering hexagonal basalt cliffs with glowing violet crystal ore veins, rain-slick stone."
    )
    p010_neg = "helmet on commander, barbute helm, full face mask, generic soldier, chen ye on right, commander on left, blurry, distorted limbs"

    # 3. Panel 016: Sovereign Ascendance Climax
    p016_prompt = (
        "Masterpiece cinematic manhua epic hero climax, low-angle heroic composition. "
        "Protagonist Chen Ye [CHARACTER: young martial artist, pitch-black hair with stark snow-white streaks, "
        "boundless glowing amethyst-purple eyes, jagged battle scar over left brow, tattered dark gray linen tunic, broken iron wrist cuffs with no chains]. "
        "Standing tall and resolute inside a massive vertical celestial pillar of radiant violet cosmic light on the quarry floor. "
        "Looking up with awe and sovereign determination toward the shattered heavens, arms naturally at his sides, "
        "rain evaporating into radiant violet mist around his body. "
        "Background: Abyssal Basalt Quarry, towering hexagonal basalt cliffs with glowing violet crystal ore veins, dark stormy twilight."
    )
    p016_neg = "fists raised at chest, holding chains, long chains, looking down, looking at camera, blurry, low quality, deformed anatomy"

    tasks = [
        ("panel_004.png", p004_prompt, p004_neg, [chen_anchor], 104004),
        ("panel_010.png", p010_prompt, p010_neg, [chen_anchor, meng_anchor], 104010),
        ("panel_016.png", p016_prompt, p016_neg, [chen_anchor], 104016),
    ]

    for fname, prompt, neg, refs, seed in tasks:
        p_path = out_dir / fname
        print(f"Generating micro-continuity fix for {fname}...")
        t0 = time.time()
        img = art.generate(
            prompt=prompt,
            negative_prompt=neg,
            width=1344,
            height=768,
            seed=seed,
            prefix=f"fix_{fname[:9]}",
            reference_images=refs,
        )
        with open(p_path, "wb") as f:
            f.write(img.png)
        print(f"✓ Generated {fname} in {time.time() - t0:.1f}s ({len(img.png)} bytes)")

if __name__ == "__main__":
    main()
