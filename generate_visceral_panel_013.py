"""Generate Panel 013: Visceral Aftermath Matching Panel 012's Severe Trauma.

Ensures 100% causal and emotional continuity:
- Commander Meng embedded in the massive impact crater in the black basalt cliff.
- Facial Trauma: Mouth dripping crimson blood down stubbled chin and scarred jaw,
  teeth stained with blood, eyes half-closed in traumatic concussive shock and daze,
  loosened warrior topknot with dark strands plastered against sweaty brow.
- Chest Trauma: Black iron breastplate heavily caved inward, cracked and shattered at center,
  dark violet void smoke and purple sparks rising from the impact wound.
- Hands: Both hands completely empty, limp or weakly clutching bruised ribs. NO WEAPON.
- Armor: Spiked black plate, embossed silver coiled dragon on left pauldron with sharp spikes,
  flared red collar.
- Environment: Fractured black basalt cliff crater with spiderweb cracks, glowing violet crystal veins,
  rain-slick dark obsidian ground, torrents of rain, dark twilight sky.
"""
from pathlib import Path
import time
from engine.comfyui.art import ArtEngine

def main():
    art = ArtEngine()
    meng_anchor = Path("output/series_1000/character_anchors/commander_meng_anchor.png")
    out_dir = Path("output/series_1000/episode_0001_perfect_continuity")
    out_path = out_dir / "panel_013.png"

    prompt = (
        "Masterpiece cinematic manhua visceral aftermath keyframe, wide impact composition. "
        "Commander Meng [CHARACTER: towering muscular imperial enforcer officer, loosened dark warrior topknot with disheveled strands, "
        "jagged diagonal battle scar across left cheek, dark stubble, heavy black-and-crimson spiked plate armor with high flared red-lined collar, "
        "curved black pauldron with embossed silver coiled dragon and sharp top spikes on his left shoulder, spiked right pauldron] "
        "violently embedded into a deep fractured impact crater in the black hexagonal basalt cliff wall. "
        "His heavy black iron breastplate is severely crushed and caved inward with spiderweb metal cracks, "
        "wisps of dark violet void smoke and dying purple electrical sparks smoldering across the shattered chestplate. "
        "A thick trickle of dark crimson blood runs from the corner of his lips down his chin and neck, "
        "his mouth parted in ragged wheezing breaths, eyes half-glazed in traumatic concussive shock and daze. "
        "Both hands are empty, limp and trembling with no weapon. "
        "Massive radial impact fissures shattering the basalt rock wall, stone debris and settling dust in the pouring rain. "
        "Background: Abyssal Basalt Quarry, towering vertical black basalt cliffs with glowing luminescent violet crystal ore veins, "
        "rain-slicked dark obsidian ground, flickering warm amber torch braziers, stormy twilight with purple eclipse moon halo. "
        "High-contrast ink chiaroscuro, volumetric rain haze, epic webtoon key visual, 8k resolution, raw somatic trauma."
    )

    negative_prompt = (
        "sword, broadsword, blade, cleaver, weapon in hand, holding weapon, weapon handle, "
        "clean undamaged armor, smooth chestplate, standing upright, peaceful, smiling, energetic, "
        "helmet on commander, barbute helm, full face mask, generic soldier, "
        "calm face, peaceful expression, handsome model pose, gentle expression, closed mouth, polite frown, "
        "stoic, emotionless, stiff posture, relaxed body, smiling, friendly, blank stare, "
        "blurry, low quality, distorted anatomy, extra limbs, deformed hands, text artifacts"
    )

    print("Submitting Visceral Panel 013 (Severe Trauma Aftermath) to ComfyUI...")
    t0 = time.time()
    img = art.generate(
        prompt=prompt,
        negative_prompt=negative_prompt,
        width=1344,
        height=768,
        seed=104099,
        prefix="visceral_p013_trauma",
        reference_images=[meng_anchor],
    )
    with open(out_path, "wb") as f:
        f.write(img.png)
    print(f"✓ Visceral Panel 013 generated in {time.time() - t0:.1f}s: {out_path} ({len(img.png)} bytes)")

if __name__ == "__main__":
    main()
