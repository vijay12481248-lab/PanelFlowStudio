"""Test Visceral Emotion and Somatic Trauma Prompting for Qwen Image 2.1.

Proves the effectiveness of the Somatic Emotion Guider:
- Meng: Visceral agony, mouth wide open spitting blood and saliva, eyes wide in shock,
  veins bulging on neck/temple, head whipped back by kinetic whiplash, spine arched backwards,
  iron breastplate collapsing inward.
- Chen Ye: Lethal wrath, teeth bared, veins bulging, purple flame radiating from eyes,
  extreme kinetic follow-through.
- Atmosphere: Concussive kinetic shockwave rings shearing raindrops, frozen blood droplets in mid-air.
"""
from pathlib import Path
import time
from engine.comfyui.art import ArtEngine

def main():
    art = ArtEngine()
    chen_anchor = Path("output/series_1000/character_anchors/chen_ye_anchor.png")
    meng_anchor = Path("output/series_1000/character_anchors/commander_meng_anchor.png")
    out_dir = Path("output/series_1000/emotional_tests")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "panel_012_visceral_agony.png"

    prompt = (
        "Masterpiece cinematic manhua high-octane battle keyframe, extreme kinetic impact and visceral somatic agony. "
        "On SCREEN-LEFT: Protagonist Chen Ye [CHARACTER: young martial artist, pitch-black hair with stark snow-white streak on left, "
        "piercing glowing amethyst-purple eyes burning with blazing purple aura flame, jagged brow scar, tattered dark gray tunic, broken wrist cuff]. "
        "Lunging with explosive lethal velocity, face contorted in fierce warrior wrath with bared teeth and straining neck tendons, "
        "driving an ink-black spiral void vortex fist violently forward. "
        "On SCREEN-RIGHT: Commander Meng [CHARACTER: towering muscular imperial officer, loosened dark warrior topknot with wild whipping strands, "
        "jagged jaw scar, heavy black-and-crimson spiked plate armor with embossed silver dragon pauldron on left shoulder]. "
        "Reeling in excruciating visceral pain and traumatic kinetic shock: his mouth is stretched wide in a breathless gasp of pure agony, "
        "teeth bared with crimson blood spittle and saliva spraying violently from his lips into the rain, "
        "eyes wide in agonizing shock with bulging veins on his neck and forehead, head violently snapped backward by the kinetic whiplash, "
        "spine arched backwards as his heavy black iron breastplate caves inward under the crushing void impact. "
        "Violent concussive air distortion rings shattering raindrops, radial ink-black shockwave bursting with blinding violet lightning sparks, "
        "frozen droplets of blood mist suspended in mid-air. "
        "Background: Abyssal Basalt Quarry, vertical black hexagonal basalt cliff walls with glowing luminescent violet crystal ore veins, "
        "rain-slicked dark obsidian ground reflecting purple light, dark stormy twilight, torrential rain. "
        "High-contrast ink chiaroscuro, extreme dramatic intensity, dynamic action manhua illustration, 8k key visual, hyper-expressive emotions."
    )

    negative_prompt = (
        "calm face, peaceful expression, handsome model pose, gentle expression, closed mouth, polite frown, "
        "stoic, emotionless, stiff posture, relaxed body, smiling, friendly, "
        "helmet on commander, barbute helm, full face mask, generic soldier, "
        "chen ye on right, commander on left, punching left, silver armor, gold armor, "
        "blurry, low quality, distorted anatomy, extra limbs, bad hands, text artifacts"
    )

    print("Submitting Visceral Emotion Test (Panel 12 Extreme Pain) to ComfyUI...")
    t0 = time.time()
    img = art.generate(
        prompt=prompt,
        negative_prompt=negative_prompt,
        width=1344,
        height=768,
        seed=104088,
        prefix="visceral_p012_agony",
        reference_images=[chen_anchor, meng_anchor],
    )
    with open(out_path, "wb") as f:
        f.write(img.png)
    print(f"✓ Visceral Emotion Panel generated in {time.time() - t0:.1f}s: {out_path} ({len(img.png)} bytes)")

if __name__ == "__main__":
    main()
