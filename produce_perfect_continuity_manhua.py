"""Production script for True Manhua Episode with Strict Environment & Secondary Character Continuity.

Solves all 4 user-reported regressions:
1. Environment Continuity: Scene locked to Abyssal Basalt Quarry with persistent landmarks across all panels.
2. Side Character Consistency: Enforcers locked to uniform matte-black armor and crimson visor; Commander Meng locked to scarred plate armor.
3. Direction & Cinematography: Standard coverage (EWS -> MLS -> OTS -> MCU -> Action Clash -> Resolution) preserving 180-degree axis.
4. Human Storyteller Cadence: Continuous dramatic narration with emotional modulation and natural breath buffers (zero dead silence).
"""
import asyncio
import os
from pathlib import Path
import subprocess
import time
from typing import List

from engine.comfyui.art import ArtEngine
from engine.creative.continuity import (
    SceneContinuityDirector,
    CinematicShotSpec,
)

OUTPUT_DIR = Path("output/series_1000/episode_0001_perfect_continuity")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Define the 16-Shot Master Cinematic Sequence for Episode 1 Act 1
SHOT_SEQUENCE: List[CinematicShotSpec] = [
    CinematicShotSpec(
        shot_index=1,
        scene_name="Abyssal Basalt Quarry",
        shot_type="Extreme Wide Shot (EWS) Master Establishing",
        screen_axis="Panoramic landscape, looking down into basalt pit",
        subject_entity="environment",
        subject_action="wide panoramic view of the vast rain-slicked quarry pit, towering basalt walls, glowing violet crystal ore veins",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0005,1.10)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="Deep within the Abyssal Quarry, cold rain slicked the towering black basalt cliffs, and the metallic tang of ozone hung heavy in the air.",
        emotion_tone="mystery",
        tts_rate="-7%",
        tts_pitch="-3Hz",
    ),
    CinematicShotSpec(
        shot_index=2,
        scene_name="Abyssal Basalt Quarry",
        shot_type="Macro Insert Detail",
        screen_axis="Ground level macro looking down",
        subject_entity="prop",
        subject_action="macro close-up of heavy shattered iron chains and broken wrist cuffs lying discarded on rain-slick dark basalt gravel",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='1.10':d={frames}:x='iw/2-(iw/zoom/2)':y='if(lte(on,1),0,y+0.5)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="At the edge of the pit lay the remnants of the unyielding chains that had bound him for years, reduced to shattered scrap.",
        emotion_tone="tension",
        tts_rate="-5%",
        tts_pitch="-2Hz",
    ),
    CinematicShotSpec(
        shot_index=3,
        scene_name="Abyssal Basalt Quarry",
        shot_type="Full Shot (FS)",
        screen_axis="Protagonist on screen-left, facing screen-right",
        subject_entity="chen_ye",
        subject_action="standing motionless on a rain-slick basalt stone ledge, dark linen tunic fluttering against the mountain gale",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='1.08':d={frames}:x='if(lte(on,1),ih*0.1,x-0.4)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="Chen Ye stood at the threshold of the abyss, silent against the whistling mountain gale.",
        emotion_tone="tension",
        tts_rate="-6%",
        tts_pitch="-2Hz",
    ),
    CinematicShotSpec(
        shot_index=4,
        scene_name="Abyssal Basalt Quarry",
        shot_type="Medium Close-Up (MCU)",
        screen_axis="Protagonist facing three-quarters screen-right",
        subject_entity="chen_ye",
        subject_action="intense focus on his face, piercing amethyst-purple eyes flaring with inner fire, jagged scar over left brow, wet black hair with white streaks, hands lowered and completely out of frame",
        forbidden_props="hands in frame, fists raised, holding chains, chained fists, looking at camera",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0008,1.14)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="Beneath the jagged scar crossing his brow, his amethyst eyes flared with the silent fury of the void furnace.",
        emotion_tone="tension",
        tts_rate="-6%",
        tts_pitch="-2Hz",
    ),
    CinematicShotSpec(
        shot_index=5,
        scene_name="Abyssal Basalt Quarry",
        shot_type="Medium Long Shot (MLS)",
        screen_axis="Side character on screen-left, looking toward Chen Ye",
        subject_entity="li_ming",
        subject_action="emerging from the wet basalt stone terrace holding a flickering rusted torch, shouting a desperate warning through the rain",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0006,1.12)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="'You stand too close to the precipice, Chen!' rasped old Li Ming, torchlight wavering across his dust-stained face.",
        emotion_tone="confrontation",
        tts_rate="-4%",
        tts_pitch="-1Hz",
    ),
    CinematicShotSpec(
        shot_index=6,
        scene_name="Abyssal Basalt Quarry",
        shot_type="Medium Long Shot (MLS)",
        screen_axis="Antagonist squad descending from screen-right toward screen-left",
        subject_entity="lingxiao_enforcer",
        subject_action="squad of imperial guards in identical matte-black spiked iron plate armor and glowing crimson slit helmets marching down rain-slick stone steps with halberds",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='1.10':d={frames}:x='iw/2-(iw/zoom/2)':y='if(lte(on,1),0,y+0.6)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="Heavy iron boots struck like thunderclaps as the Overseer's enforcers marched down the terraces, their halberds gleaming in the dark.",
        emotion_tone="tension",
        tts_rate="-3%",
        tts_pitch="-1Hz",
    ),
    CinematicShotSpec(
        shot_index=7,
        scene_name="Abyssal Basalt Quarry",
        shot_type="Medium Close-Up (MCU)",
        screen_axis="Antagonist on screen-right, scowling toward screen-left",
        subject_entity="commander_meng",
        subject_action="brandishing a massive serrated executioner broadsword, snarling face with battle scar, black-and-crimson armor dripping with rain",
        weapon_in_hand="serrated steel executioner broadsword",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0010,1.16)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="'Slaves who shatter their chains earn only a swifter grave!' Commander Meng bellowed, unsheathing his serrated cleaver.",
        emotion_tone="confrontation",
        tts_rate="-1%",
        tts_pitch="+0Hz",
    ),
    CinematicShotSpec(
        shot_index=8,
        scene_name="Abyssal Basalt Quarry",
        shot_type="Over-The-Shoulder (OTS) Standoff",
        screen_axis="Camera behind Chen Ye on screen-left, looking at Commander Meng on screen-right",
        subject_entity="chen_ye",
        subject_action="framed from behind shoulder facing the armed enforcer line across the rain-slick basalt ground, dark violet lightning beginning to spark around his fingers",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0006,1.12)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="Chen Ye did not flinch; the void furnace within his core ignited, cold ozone crackling across his skin.",
        emotion_tone="tension",
        tts_rate="-5%",
        tts_pitch="-1Hz",
    ),
    CinematicShotSpec(
        shot_index=9,
        scene_name="Abyssal Basalt Quarry",
        shot_type="Dynamic Action Hero Shot (Low-Angle Dutch Tilt)",
        screen_axis="Protagonist low combat stance, ready to strike screen-right",
        subject_entity="chen_ye",
        subject_action="dropping into a low martial arts combat stance on wet black stone, translucent violet dragon aura coiling around his arms",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0012,1.20)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="With an explosive burst of violet essence, he bridged the distance in a fraction of a heartbeat.",
        emotion_tone="battle_explosive",
        tts_rate="+3%",
        tts_pitch="+1Hz",
    ),
    CinematicShotSpec(
        shot_index=10,
        scene_name="Abyssal Basalt Quarry",
        shot_type="Dynamic Action Clash (Low-Angle Hero Impact)",
        screen_axis="Chen Ye on screen-left blocking Commander Meng on screen-right",
        subject_entity="action_clash",
        opponent_entity="commander_meng",
        weapon_in_hand="serrated steel executioner broadsword",
        subject_action="Chen Ye's bare forearm blocking Commander Meng's massive serrated executioner blade, brilliant violet sparks and shockwaves blasting outward",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0018,1.25)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="Steel met flesh with a screeching clash! The heavy blade groaned against skin tempered by raw void essence.",
        emotion_tone="battle_explosive",
        tts_rate="+4%",
        tts_pitch="+2Hz",
    ),
    CinematicShotSpec(
        shot_index=11,
        scene_name="Abyssal Basalt Quarry",
        shot_type="High-Speed Macro Freeze-Frame",
        screen_axis="Center macro focus",
        subject_entity="prop",
        subject_action="macro freeze frame of the heavy serrated steel broadsword shattering into hundreds of jagged metal shards flying through rain and sparks",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0020,1.26)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="With a deafening crack, the enforcer's cleaver shattered like brittle glass, shards tearing through the rain!",
        emotion_tone="battle_explosive",
        tts_rate="+5%",
        tts_pitch="+2Hz",
        intentional_pause_after_seconds=0.35,  # Intentional dramatic suspense pause before punch
    ),
    CinematicShotSpec(
        shot_index=12,
        scene_name="Abyssal Basalt Quarry",
        shot_type="Cinematic Strike Impact",
        screen_axis="Protagonist striking from screen-left into screen-right",
        subject_entity="chen_ye",
        opponent_entity="commander_meng",
        damage_state="breastplate caving inward under void fist impact, violet vortex shockwave",
        forbidden_props="sword, blade, weapon in hand, holding weapon, helmet, barbute helm",
        subject_action="Chen Ye driving an ink-black spiral void fist into Commander Meng's heavy breastplate, shockwave concussing the wet air",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0015,1.22)':d={frames}:x='if(lte(on,1),0,x+0.8)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="Chen Ye unleashed an ink-black vortex, driving his fist forward and crumpling the heavy iron plate inward.",
        emotion_tone="battle_explosive",
        tts_rate="+2%",
        tts_pitch="+1Hz",
    ),
    CinematicShotSpec(
        shot_index=13,
        scene_name="Abyssal Basalt Quarry",
        shot_type="Wide Impact Aftermath",
        screen_axis="Lateral wide tracking shot",
        subject_entity="commander_meng",
        damage_state="caved inward breastplate, cracked iron plate, violet void smoke and purple sparks crackling across chest, grimacing in agony",
        forbidden_props="sword, broadsword, blade, weapon in hand, holding weapon, clean undamaged armor, smooth chestplate",
        subject_action="Commander Meng violently embedded in a massive fractured impact crater in the black basalt cliff wall, both hands empty, dust and stone shards settling in the rain",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='1.10':d={frames}:x='if(lte(on,1),0,x+0.8)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="The armored commander was hurled through the cavern, smashing violently against the basalt cliff face.",
        emotion_tone="triumph_awe",
        tts_rate="-3%",
        tts_pitch="-1Hz",
    ),
    CinematicShotSpec(
        shot_index=14,
        scene_name="Abyssal Basalt Quarry",
        shot_type="Medium Long Shot (MLS) Reaction",
        screen_axis="Guards on screen-right backing away in terror",
        subject_entity="lingxiao_enforcer",
        subject_action="surviving black-armored enforcer soldiers trembling, halberds shaking as they step backward on the rain-slick basalt terraces",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='1.08':d={frames}:x='iw/2-(iw/zoom/2)':y='if(lte(on,1),0,y+0.4)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="A terrified silence gripped the quarry as the remaining enforcers took a trembling step backward.",
        emotion_tone="tension",
        tts_rate="-5%",
        tts_pitch="-2Hz",
    ),
    CinematicShotSpec(
        shot_index=15,
        scene_name="Abyssal Basalt Quarry",
        shot_type="Low-Angle Cosmic Rupture",
        screen_axis="Vertical composition looking up from quarry floor",
        subject_entity="environment",
        subject_action="ancient obsidian altar on the basalt quarry floor splitting open, erupting a vertical celestial pillar of violet light into the dark storm clouds",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='1.12':d={frames}:x='iw/2-(iw/zoom/2)':y='if(lte(on,1),ih*0.1,y-0.7)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="From the heart of the pit, the fractured altar ruptured, releasing an ancient celestial seal that had slumbered for ten thousand years.",
        emotion_tone="triumph_awe",
        tts_rate="-6%",
        tts_pitch="-3Hz",
    ),
    CinematicShotSpec(
        shot_index=16,
        scene_name="Abyssal Basalt Quarry",
        shot_type="Master Hero Climax (Low-Angle Heroic)",
        screen_axis="Chen Ye centered, looking up toward the heavens",
        subject_entity="chen_ye",
        subject_action="Chen Ye standing tall inside the celestial violet beam of light looking up toward the shattered heavens, arms naturally at his sides with broken wrist cuffs and no chains, rain evaporating into steam around him, amethyst eyes glowing with boundless sovereign power",
        forbidden_props="fists raised, holding chains, chained hands, long chains, looking down, looking at camera",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0008,1.15)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="Standing in the pillar of radiant light, Chen Ye looked up at the shattered heavens, knowing his sovereign path had finally begun.",
        emotion_tone="triumph_awe",
        tts_rate="-7%",
        tts_pitch="-3Hz",
    ),
]


async def run_production():
    director = SceneContinuityDirector()
    art = ArtEngine()

    print("=== Commencing Production: Perfect Continuity True Manhua Master ===")
    t_start = time.time()

    # Step 1: Synthesize all speech audio segments with emotional cadence
    print("\n--- Step 1: Synthesizing Emotional Storyteller Narration ---")
    audio_data = await director.synthesize_continuous_storyteller_audio(SHOT_SEQUENCE, OUTPUT_DIR)
    for idx, (a_path, dur) in enumerate(audio_data, 1):
        print(f"Shot {idx:02d} Audio: {dur:.2f}s | {SHOT_SEQUENCE[idx-1].narration_line[:60]}...")

    # Step 2: Render All 16 Character & Environment-Locked Panels on ComfyUI
    print("\n--- Step 2: Rendering 16 Character- & Environment-Locked Panels (ComfyUI) ---")
    panel_images: List[Path] = []
    force_regenerate = os.getenv("FORCE_REGENERATE", "1") == "1"

    for idx, shot in enumerate(SHOT_SEQUENCE, 1):
        panel_path = OUTPUT_DIR / f"panel_{idx:03d}.png"
        if panel_path.exists() and not force_regenerate:
            print(f"Panel {idx:02d} already rendered: {panel_path.name}")
            panel_images.append(panel_path)
            continue

        prompt, neg_prompt, ref_images = director.compile_shot_prompt(shot)
        ref_names = [p.name for p in ref_images] if ref_images else ["None"]
        print(f"Rendering Panel {idx:02d} [{shot.subject_entity}] (refs={ref_names})...")
        t_img = time.time()
        art_img = art.generate(
            prompt=prompt,
            negative_prompt=neg_prompt,
            width=1344,
            height=768,
            seed=99000 + idx * 111,
            prefix=f"cont_p{idx:03d}",
            reference_images=ref_images,
        )
        with open(panel_path, "wb") as f:
            f.write(art_img.png)
        print(f"✓ Panel {idx:02d} rendered in {time.time() - t_img:.1f}s ({len(art_img.png)} bytes)")
        panel_images.append(panel_path)

    # Step 3: Render Individual Video Shots Matching Exact Audio Length (Zero Dead Silence)
    print("\n--- Step 3: Encoding 4K Kinematic Video Shots with Exact Audio Timing ---")
    shot_video_paths: List[Path] = []
    for idx, (img_path, (audio_path, audio_dur)) in enumerate(zip(panel_images, audio_data), 1):
        shot_spec = SHOT_SEQUENCE[idx - 1]
        shot_video_path = OUTPUT_DIR / f"shot_{idx:03d}.mp4"
        
        # Exact duration = audio_dur + natural breath buffer (zero artificial dead gaps!)
        exact_duration = round(audio_dur + shot_spec.intentional_pause_after_seconds, 2)
        total_frames = int(exact_duration * 30)
        vf_filter = shot_spec.camera_movement.replace("{frames}", str(total_frames))

        if not shot_video_path.exists() or force_regenerate:
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-i", str(img_path),
                "-i", str(audio_path),
                "-vf", vf_filter,
                "-c:v", "h264_nvenc",
                "-c:a", "aac", "-b:a", "192k",
                "-t", str(exact_duration),
                "-pix_fmt", "yuv420p",
                "-shortest",
                str(shot_video_path),
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"✓ Encoded Shot {idx:02d}: {exact_duration:.2f}s (Audio: {audio_dur:.2f}s, Pause: {shot_spec.intentional_pause_after_seconds:.2f}s)")
        shot_video_paths.append(shot_video_path)

    # Step 4: Concatenate All Shots into Seamless Master Episode Video
    print("\n--- Step 4: Concatenating Master Episode Video ---")
    master_video = OUTPUT_DIR / "episode_0001_perfect_continuity_master.mp4"
    concat_manifest = OUTPUT_DIR / "shots_manifest.txt"
    with open(concat_manifest, "w", encoding="utf-8") as f:
        for p in shot_video_paths:
            f.write(f"file '{p.resolve().as_posix()}'\n")

    cmd_concat = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_manifest.resolve().as_posix(),
        "-c", "copy",
        str(master_video),
    ]
    subprocess.run(cmd_concat, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    total_time = time.time() - t_start
    print(f"\n==================================================================")
    print(f"🎉 MASTER EPISODE READY: {master_video.name}")
    print(f"Size: {master_video.stat().st_size / (1024*1024):.2f} MB")
    print(f"Total Pipeline Runtime: {total_time:.1f} seconds")
    print(f"==================================================================")


if __name__ == "__main__":
    asyncio.run(run_production())
