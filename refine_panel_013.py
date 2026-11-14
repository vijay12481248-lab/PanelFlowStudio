"""Generate Panel 013: Flawless Aftermath Continuity.

Ensures 100% character and cause-and-effect continuity with Panel 011 and Panel 012:
- Subject: Commander Meng (matching commander_meng_anchor.png and panel_012_refined.png).
- Physical State: Violently slammed backward into the towering black basalt cliff wall,
  embedded in a massive fractured stone impact crater with cracks radiating through the rock.
- Chestplate: Heavily dented, fractured, crumpled inward from Chen Ye's void fist strike,
  with faint wisps of dark purple void smoke and residual violet sparks crackling on the damaged iron.
- Hands / Weapon: ABSOLUTELY NO SWORD! Both hands empty, clutching his damaged chest or slumped down.
  His broadsword shattered in Panel 011 and remains destroyed.
- Armor: Spiked black plate armor with crimson inner trim, high flared collar,
  silver dragon embossed on his left pauldron (viewer's right) with sharp top spikes,
  spiked pauldron on right shoulder.
- Environment: Abyssal Basalt Quarry, hexagonal black basalt cliffs with glowing vertical violet crystal veins,
  rain-slick dark obsidian ground, flickering amber braziers, torrential rain, purple eclipse moon in twilight sky.
"""
from pathlib import Path
import time
from engine.comfyui.art import ArtEngine

def main():
    art = ArtEngine()
    meng_anchor = Path("output/series_1000/character_anchors/commander_meng_anchor.png")
    out_dir = Path("output/series_1000/episode_0001_perfect_continuity")
    out_path = out_dir / "panel_013_refined.png"

    prompt = (
        "Masterpiece cinematic manhua aftermath keyframe, wide impact composition. "
        "Commander Meng [CHARACTER: towering muscular imperial enforcer officer, black hair tied in a loosened warrior topknot, "
        "grimacing in pain with clenched teeth, dark stubble, jagged diagonal battle scar across left cheek, "
        "heavy black-and-crimson spiked plate armor with high flared red-lined collar, "
        "curved black pauldron with embossed silver coiled dragon and sharp top spikes on his left shoulder, "
        "segmented spiked pauldron on right shoulder] violently embedded into a massive fractured impact crater "
        "in the vertical black hexagonal basalt cliff wall. "
        "His heavy black iron chestplate is visibly caved inward, cracked and dented from the devastating void strike, "
        "with faint wisps of dark violet smoke and lingering purple sparks crackling across the fractured metal breastplate. "
        "His hands are empty, no weapon, slumped against the shattered rock. "
        "Massive spiderweb rock fractures radiating outward, basalt stone rubble and flying dust settling in the torrential rain. "
        "Background: Abyssal Basalt Quarry, towering vertical hexagonal basalt cliffs with glowing luminescent violet crystal ore veins, "
        "rain-slicked dark obsidian ground, warm flickering amber brazier torches in the background, dark stormy twilight with glowing purple eclipse moon halo. "
        "High-contrast ink chiaroscuro, volumetric rain haze, dramatic webtoon illustration, 8k key visual, sharp detailed linework."
    )

    negative_prompt = (
        "sword, broadsword, blade, cleaver, weapon in hand, holding sword, holding weapon, weapon handle, "
        "standing upright, clean undamaged armor, smooth chestplate, smiling, peaceful, helmet, barbute helm, "
        "covered face, modern clothes, colorful, blurry, low quality, distorted anatomy, extra limbs, text artifacts"
    )

    print("Submitting Panel 013 (Aftermath Crater) to ComfyUI with Commander Meng reference anchor...")
    t0 = time.time()
    img = art.generate(
        prompt=prompt,
        negative_prompt=negative_prompt,
        width=1344,
        height=768,
        seed=104013,
        prefix="cont_p013_aftermath",
        reference_images=[meng_anchor],
    )
    with open(out_path, "wb") as f:
        f.write(img.png)
    print(f"✓ Successfully generated Panel 013 in {time.time() - t0:.1f}s: {out_path} ({len(img.png)} bytes)")

if __name__ == "__main__":
    main()
