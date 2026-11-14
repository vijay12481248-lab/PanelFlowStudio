"""Generate the refined, production-perfect version of Panel 12.

Fixes:
1. 180° Spatial Axis: Chen Ye is on SCREEN-LEFT, punching toward SCREEN-RIGHT.
2. Opponent Uniformity: Lingxiao Enforcer is on SCREEN-RIGHT, wearing FULL-FACE HELMET with horizontal glowing crimson visor slit.
3. Impact Kinetic Geometry: Dynamic profile impact, fist driving directly into chestplate with void spiral vortex.
4. Dual Reference Conditioning: Conditions on both chen_ye_anchor.png and lingxiao_enforcer_anchor.png!
"""
from pathlib import Path
import time
from engine.comfyui.art import ArtEngine

def main():
    art = ArtEngine()
    chen_anchor = Path("output/series_1000/character_anchors/chen_ye_anchor.png")
    enforcer_anchor = Path("output/series_1000/character_anchors/lingxiao_enforcer_anchor.png")
    out_dir = Path("output/series_1000/episode_0001_perfect_continuity")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "panel_012_refined.png"

    prompt = (
        "Masterpiece cinematic manhua action keyframe, dynamic side profile strike impact. "
        "On SCREEN-LEFT: Protagonist Chen Ye [CHARACTER: young martial artist, pitch-black hair with stark snow-white streaks on left, "
        "piercing glowing amethyst-purple eyes, jagged battle scar over left brow, tattered dark gray linen tunic, broken iron cuff on wrist], "
        "lunging powerfully forward toward the right, driving an ink-black spiral void fist directly into the opponent's chestplate. "
        "On SCREEN-RIGHT: Lingxiao Iron Enforcer [CHARACTER: imperial soldier clad in uniform matte-black spiked segmented iron plate armor, "
        "full-face iron barbute helmet completely covering the head with a single horizontal glowing crimson slit visor, heavy spiked pauldrons], "
        "facing left, his heavy black chestplate crumpling inward under the violent impact. "
        "Violent kinetic shockwave ripples, ink-splash void energy vortex, bright violet electric sparks bursting between fist and armor, "
        "splashing raindrops frozen in high-speed impact. "
        "Background: Abyssal Basalt Quarry, massive towering vertical black hexagonal basalt cliff walls with glowing luminescent violet crystal ore veins, "
        "rain-slicked dark obsidian ground reflecting purple light, dark stormy twilight, torrential rain. "
        "High contrast chiaroscuro, volumetric rain lighting, epic webtoon key visual, 8k resolution, crisp linework."
    )

    negative_prompt = (
        "bare head on soldier, human hair on soldier, open face on soldier, unmasked soldier, skin face on soldier, "
        "soldier on left side, chen ye on right side, punching towards left, silver armor, gold armor, colorful armor, "
        "blurry, low quality, distorted anatomy, extra arms, deformed hands, text artifacts"
    )

    print("Submitting refined Panel 12 generation to ComfyUI with dual reference anchors...")
    t0 = time.time()
    img = art.generate(
        prompt=prompt,
        negative_prompt=negative_prompt,
        width=1344,
        height=768,
        seed=102030,
        prefix="cont_p012_refined",
        reference_images=[chen_anchor, enforcer_anchor],
    )
    with open(out_path, "wb") as f:
        f.write(img.png)
    print(f"✓ Successfully generated and saved refined Panel 12 in {time.time() - t0:.1f}s: {out_path} ({len(img.png)} bytes)")

if __name__ == "__main__":
    main()
