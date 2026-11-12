"""Generate Panel 12 matching Commander Meng in Panel 13.

Ensures 100% character continuity between Panel 12 and Panel 13:
- Screen-Left: Chen Ye lunging toward screen-right.
- Screen-Right: Commander Meng (matching Panel 7 and Panel 13: towering muscular officer, warrior topknot, scarred jaw, heavy black-and-crimson spiked armor with silver dragon pauldron).
- Action: Chen Ye's ink-black spiral void fist driving directly into Commander Meng's chestplate, crumpling the iron with violet shockwaves and sparks!
"""
from pathlib import Path
import time
from engine.comfyui.art import ArtEngine

def main():
    art = ArtEngine()
    chen_anchor = Path("output/series_1000/character_anchors/chen_ye_anchor.png")
    meng_anchor = Path("output/series_1000/character_anchors/commander_meng_anchor.png")
    out_dir = Path("output/series_1000/episode_0001_perfect_continuity")
    out_path = out_dir / "panel_012_refined.png"

    prompt = (
        "Masterpiece cinematic manhua action keyframe, dynamic side profile strike impact. "
        "On SCREEN-LEFT: Protagonist Chen Ye [CHARACTER: young martial artist, pitch-black hair with stark snow-white streaks on left, "
        "piercing glowing amethyst-purple eyes, jagged battle scar over left brow, tattered dark gray linen tunic, broken iron cuff on wrist], "
        "lunging powerfully forward toward the right, driving an ink-black spiral void fist directly into the opponent's chestplate. "
        "On SCREEN-RIGHT: Commander Meng [CHARACTER: towering muscular imperial enforcer officer, black hair tied in a warrior topknot, "
        "snarling scarred jaw, heavy black-and-crimson spiked plate armor with embossed silver dragon pauldron on shoulder], "
        "facing left, taking the massive impact as his heavy black-and-crimson breastplate crumples inward under the void strike. "
        "Violent kinetic shockwave ripples, ink-splash void energy vortex, bright violet electric sparks bursting between fist and armor, "
        "splashing raindrops frozen in high-speed impact. "
        "Background: Abyssal Basalt Quarry, massive towering vertical black hexagonal basalt cliff walls with glowing luminescent violet crystal ore veins, "
        "rain-slicked dark obsidian ground reflecting purple light, dark stormy twilight, torrential rain. "
        "High contrast chiaroscuro, volumetric rain lighting, epic webtoon key visual, 8k resolution, crisp linework."
    )

    negative_prompt = (
        "helmet on commander, barbute helm, full face mask on commander, covered face on commander, "
        "chen ye on right side, commander on left side, punching towards left, silver armor, gold armor, "
        "blurry, low quality, distorted anatomy, extra arms, deformed hands, text artifacts"
    )

    print("Submitting Panel 12 (Commander Meng strike) to ComfyUI...")
    t0 = time.time()
    img = art.generate(
        prompt=prompt,
        negative_prompt=negative_prompt,
        width=1344,
        height=768,
        seed=104050,
        prefix="cont_p012_meng",
        reference_images=[chen_anchor, meng_anchor],
    )
    with open(out_path, "wb") as f:
        f.write(img.png)
    print(f"✓ Successfully generated and saved Panel 12 matching Commander Meng in {time.time() - t0:.1f}s: {out_path}")

if __name__ == "__main__":
    main()
