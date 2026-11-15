"""True Unique-Panel Manhua Video Production Engine (V2 - Corrected).

Fixes applied:
1. Dynamic Subject Conditioning:
   - Only conditions on chen_ye_anchor.png when Chen Ye is the explicit subject.
   - For environments, props, and antagonists, generates the actual subject with zero character leakage.
   - Poses for Chen Ye vary dynamically across every scene (martial stance, blocking blade, punch, standing tall).
2. Semantic Synchronization: Every image visually illustrates the exact narration event.
3. Natural Human-like Narrator: Resonant storytelling cadence (rate=-6%, pitch=-2Hz).
4. Silky-Smooth Camera Dynamics: 4K pre-scaled smooth float kinematics eliminate sub-pixel zoompan jitter completely.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Dict, Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import edge_tts
from engine.comfyui.art import ArtEngine
from engine.render.encoder import FFmpegEncoder

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("true_manhua_producer_v2")

EPISODE_1_UNIQUE_PANELS = [
    {
        "panel_index": 1,
        "title": "The Deep Quarry Abyss",
        "category": "environment",
        "subject": "none",
        "prompt": "wide establishing panoramic vista of a colossal deep basalt quarry, wet black stone cliffs glistening in cold rain, atmospheric mountain fog, dramatic violet eclipse halo in the stormy sky, cold blue and violet lighting, cinematic anime background art, 8k resolution, masterpiece, no people",
        "negative_prompt": "people, human, man, woman, face, hands, body, character, text, blurry, low quality",
        "narration": "Deep within the Abyssal Quarry, rain slicked the jagged basalt walls, and the metallic tang of cold ozone hung heavy in the air.",
        "motion": "smooth_descent"
    },
    {
        "panel_index": 2,
        "title": "The Shattered Shackles",
        "category": "prop_macro",
        "subject": "none",
        "prompt": "macro ground shot of shattered heavy iron chains and broken iron slave shackles lying in dark mud and wet gravel, faint violet smoke wafting from broken metal links, rain puddles reflecting violet sky, cinematic photorealistic digital ink, 8k",
        "negative_prompt": "people, face, hands, full body, standing person, blurry, text",
        "narration": "At the edge of the pit lay the remnants of the unyielding chains that had bound him for years, now reduced to scrap.",
        "motion": "slow_push"
    },
    {
        "panel_index": 3,
        "title": "The Lone Sovereign Stands",
        "category": "protagonist",
        "subject": "chen_ye",
        "prompt": "heroic wide shot from behind of Chen Ye standing at the edge of a precipice, arms at his sides, dark gray linen tunic fluttering in the howling wind, broken iron cuffs around wrists, looking out over the boundless cloudy abyss, cold mist swirling, masterpiece manhwa",
        "negative_prompt": "chained hands, hands held up, face front, blurry, low quality",
        "narration": "Chen Ye stood at the threshold of the abyss, his posture motionless against the whistling mountain gale.",
        "motion": "slow_push"
    },
    {
        "panel_index": 4,
        "title": "Gaze of the Ashen Sovereign",
        "category": "protagonist_macro",
        "subject": "chen_ye",
        "prompt": "extreme macro close-up portrait of Chen Ye face, sharp angular features, piercing glowing amethyst-purple eyes, jagged battle scar crossing left eyebrow, wet hair with white streaks falling across forehead, rain droplets on pale skin, determined expression, no hands, cinematic depth of field",
        "negative_prompt": "hands, body, chains, multiple people, blurry, distorted eyes",
        "narration": "Beneath the jagged scar crossing his brow, his amethyst eyes flared with the silent fury of the void furnace.",
        "motion": "slow_push"
    },
    {
        "panel_index": 5,
        "title": "The Floating Sky Palaces",
        "category": "environment",
        "subject": "none",
        "prompt": "low-angle looking up from dark cavern at magnificent floating celestial palaces drifting on airborne stone islands high above clouds, glowing lanterns, golden spires, dark storm clouds, epic cultivation fantasy architecture, 8k scale",
        "negative_prompt": "people, character, face, hands, body, blurry",
        "narration": "High above, the celestial sky palaces drifted like silent tyrants, unaware of the rebellion stirring in the mud below.",
        "motion": "smooth_pan_up"
    },
    {
        "panel_index": 6,
        "title": "Shadows in the Shaft",
        "category": "secondary_characters",
        "subject": "slaves",
        "prompt": "mine shaft tunnel entrance in dark cavern, group of ragged weary rebel slaves holding flickering amber torches creeping out from the shadows, frightened desperate expressions, dusty ragged clothes, high contrast warm lantern chiaroscuro",
        "negative_prompt": "Chen Ye, glowing purple eyes, white hair streaks, solo hero, blurry",
        "narration": "Footsteps echoed against damp stone as cloaked figures crept from the mine shafts, desperate and cornered.",
        "motion": "smooth_lateral"
    },
    {
        "panel_index": 7,
        "title": "Li Ming's Warning",
        "category": "secondary_character",
        "subject": "li_ming",
        "prompt": "medium shot of Li Ming, a middle-aged weathered Asian rebel warrior with dirt-streaked face and desperate eyes, holding a sputtering wooden torch, reaching out a pleading hand in warning, dark cave background, warm amber lighting on skin",
        "negative_prompt": "young boy, purple eyes, white hair, Chen Ye, armor, clean skin, blurry",
        "narration": "'You stand too close to the edge, Chen!' rasped Li Ming, torchlight wavering across his dust-stained face.",
        "motion": "slow_push"
    },
    {
        "panel_index": 8,
        "title": "Sparks of the Void",
        "category": "protagonist_action",
        "subject": "chen_ye",
        "prompt": "macro close-up of a powerful clenched fist, glowing violet lightning and ink-black void flame swirling around knuckles, broken iron cuff on wrist, dark stone background, intense energy crackling, dynamic lighting, 8k",
        "negative_prompt": "full body, face, head, multiple hands, chains binding hands together, blurry",
        "narration": "'The edge is where the void meets the world,' Chen replied coldly. 'If you cannot see it, you will fall.'",
        "motion": "slow_push"
    },
    {
        "panel_index": 9,
        "title": "The Reversing Altar",
        "category": "environment",
        "subject": "none",
        "prompt": "massive ancient black obsidian ritual altar standing on stone dais in cave, glowing blood-red runes and glyphs pulsing in reverse, ominous crimson light illuminating basalt pillars, dark occult fantasy ritual, intricate geometry, no people",
        "negative_prompt": "people, character, face, hands, body, blurry",
        "narration": "Deep in the quarry's heart, the ancient altar hummed ominously, its runes reversing into crimson death.",
        "motion": "slow_push"
    },
    {
        "panel_index": 10,
        "title": "Descent of the Enforcers",
        "category": "antagonists",
        "subject": "guards",
        "prompt": "squad of heavy armored imperial enforcers marching down carved stone stairs, intimidating spiked black iron armor, glowing red visor slits, carrying massive jagged executioner swords, cold metallic reflections, dark stone quarry",
        "negative_prompt": "Chen Ye, linen tunic, unarmed, friendly, blurry",
        "narration": "The Overseer's enforcers marched down the terraces, their heavy iron boots striking like thunderclaps.",
        "motion": "smooth_descent"
    },
    {
        "panel_index": 11,
        "title": "The Cruel Command",
        "category": "antagonist",
        "subject": "commander",
        "prompt": "close-up of brutal scarred overseer commander wearing ornate dark spiked helmet, face twisted in savage bloodthirsty grin, shouting fiercely, raising a massive jagged iron broadsword, dynamic Dutch tilt, harsh crimson rim lighting",
        "negative_prompt": "young hero, purple eyes, gentle, Chen Ye, blurry",
        "narration": "'Slaves who break their chains earn only a swifter grave!' the lead enforcer bellowed.",
        "motion": "slow_push"
    },
    {
        "panel_index": 12,
        "title": "Ignition of the Void Core",
        "category": "protagonist_action",
        "subject": "chen_ye",
        "prompt": "dynamic medium combat stance: Chen Ye dropping low in martial arts tiger stance, arms angled ready to strike, translucent violet dragon phantom aura swirling around his body, glowing amethyst eyes, cracked stone ground, cinematic manhwa action",
        "negative_prompt": "hands chained up, standing still, relaxed, blurry",
        "narration": "Chen Ye did not flinch; the void furnace within his dantian ignited, ravenous for battle.",
        "motion": "slow_push"
    },
    {
        "panel_index": 13,
        "title": "The Sonic Dash",
        "category": "action_speed",
        "subject": "chen_ye",
        "prompt": "explosive high-speed dash, diagonal dynamic action lines, blurred violet afterimages of charging martial artist, sonic shockwave rings kicking up water and mud, high speed motion blur, cinematic webtoon fight cut",
        "negative_prompt": "static standing, portrait, slow, blurry face",
        "narration": "With an explosive burst, he bridged the distance in a fraction of a heartbeat, a phantom of violet wrath.",
        "motion": "smooth_lateral"
    },
    {
        "panel_index": 14,
        "title": "Iron Meets Void",
        "category": "combat_clash",
        "subject": "clash",
        "prompt": "intense combat impact clash: young martial artist bare forearm blocking a massive descending iron broadsword, radiant explosion of yellow sparks and violet shockwaves at point of contact, two figures locked in furious struggle, high contrast chiaroscuro",
        "negative_prompt": "hands chained, solo portrait, calm, blurry",
        "narration": "Steel met flesh, but the blade groaned against skin tempered by raw void essence, sparks illuminating the darkness.",
        "motion": "slow_push"
    },
    {
        "panel_index": 15,
        "title": "Shattering Steel",
        "category": "prop_action_macro",
        "subject": "none",
        "prompt": "macro dynamic freeze-frame of a heavy iron executioner blade shattering into dozens of sharp jagged flying metal shards, radiant violet shockwave fracturing through the steel, sparks and water droplets suspended in mid-air, 8k detail",
        "negative_prompt": "person, face, full body, standing human, blurry",
        "narration": "With a deafening crack, the enforcer's cleaver shattered like brittle glass, shards tearing through the rain.",
        "motion": "slow_push"
    },
    {
        "panel_index": 16,
        "title": "The Sovereign's Strike",
        "category": "combat_impact",
        "subject": "strike",
        "prompt": "devastating punch impact: Chen Ye driving a fierce extended fist into heavy iron breastplate armor, spiraling black ink vortex and violet flame exploding from point of contact, metal armor buckling inward, shockwave blast",
        "negative_prompt": "hands chained together, calm, missing punch, blurry",
        "narration": "Chen Ye drove his fist forward, unleashing an ink-black vortex that crumpled the heavy armor inward.",
        "motion": "slow_push"
    },
    {
        "panel_index": 17,
        "title": "Impact into the Pillar",
        "category": "action_aftermath",
        "subject": "commander",
        "prompt": "wide action scene of armored commander flying through air and crashing violently into massive ancient stone pillar, stone shattering into boulders, huge dust and smoke explosion, kinetic destruction",
        "negative_prompt": "Chen Ye close up, portrait, peaceful, blurry",
        "narration": "The armored giant was launched through the cavern, smashing into the stone pillar with a sickening crunch.",
        "motion": "smooth_lateral"
    },
    {
        "panel_index": 18,
        "title": "Terror of the Enforcers",
        "category": "reaction",
        "subject": "guards",
        "prompt": "group of heavy armored guards stumbling backward in terrified shock, trembling gauntlets dropping weapons onto stone floor, wide eyes behind cracked visors, dark shadowy cave, atmospheric fear",
        "negative_prompt": "Chen Ye, hero winning, smiling, blurry",
        "narration": "A terrified silence gripped the quarry as the remaining guards took a trembling step backward.",
        "motion": "smooth_descent"
    },
    {
        "panel_index": 19,
        "title": "The Seal Ruptures",
        "category": "supernatural_event",
        "subject": "none",
        "prompt": "ancient stone altar splitting wide open down center, colossal blinding geyser of radiant gold and purple divine light blasting straight into storm clouds, dark cavern illuminated in celestial luminescence, divine rays, no people",
        "negative_prompt": "people, human, face, hands, body, blurry",
        "narration": "The fractured altar ruptured, releasing an ancient celestial seal that had slept for ten thousand years.",
        "motion": "smooth_pan_up"
    },
    {
        "panel_index": 20,
        "title": "Coronation of the Ashen Sovereign",
        "category": "heroic_climax",
        "subject": "chen_ye",
        "prompt": "monumental climax splash art: Chen Ye standing tall in the center of the radiant cosmic light beam, dark hair with white streaks billowing freely, glowing amethyst eyes gazing upward toward the heavens, arms relaxed at his sides with broken iron cuffs, regal sovereign aura, masterpiece cover art",
        "negative_prompt": "hands chained up, looking down, beaten, sad, blurry",
        "narration": "Standing in the pillar of light, Chen Ye gazed up at the shattered heavens, knowing his sovereign path had just begun.",
        "motion": "slow_push"
    },
]


async def produce_true_manhua_episode(
    output_dir: Path = Path("output/series_1000/episode_0001_true_manhua"),
    voice: str = "en-US-ChristopherNeural",
) -> Path:
    """Produces a true, non-repeating 20-panel manhua video with zero repetition and butter-smooth motion."""
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    
    art_engine = ArtEngine()
    encoder = FFmpegEncoder()
    ffmpeg_bin = encoder.ffmpeg_path or "ffmpeg"
    
    anchor_path = Path("output/series_1000/character_anchors/chen_ye_anchor.png").resolve()
    
    logger.info("================================================================================")
    logger.info(f"🎨 PRODUCING TRUE MANHUA EPISODE (V2): 20 DIVERSE & UNIQUE STORY PANELS")
    logger.info("================================================================================")
    
    # 1. Generate every unique image with strict dynamic conditioning
    generated_images: List[Path] = []
    for p in EPISODE_1_UNIQUE_PANELS:
        idx = p["panel_index"]
        img_path = output_dir / f"panel_{idx:03d}.png"
        
        # Only pass anchor when Chen Ye is the subject
        is_chen_ye = p["subject"] in ["chen_ye", "clash", "strike"]
        ref_arg = anchor_path if (is_chen_ye and anchor_path.exists()) else None
        
        if is_chen_ye:
            full_prompt = (
                f"[CHARACTER: Chen Ye (Protagonist): young martial artist, pitch-black hair with stark snow-white streaks, "
                f"piercing glowing amethyst-purple eyes, jagged battle scar across left eyebrow, pale skin with light coal dust, "
                f"tattered dark gray linen tunic, broken cuffs on wrists] "
                f"{p['prompt']}, cinematic manhwa art, masterpiece, high contrast ink chiaroscuro, 8k key visual"
            )
        else:
            full_prompt = f"{p['prompt']}, cinematic manhwa art, masterpiece, high contrast ink chiaroscuro, 8k key visual"
            
        logger.info(f"Generating Panel {idx:02d}/20 [{p['category'].upper()}]: '{p['title']}' (Anchor: {'YES' if ref_arg else 'NO'})...")
        t0 = time.time()
        art = art_engine.generate(
            prompt=full_prompt,
            negative_prompt=p.get("negative_prompt", "blurry, low quality, distorted anatomy, text artifacts"),
            width=1344,
            height=768,
            seed=2001 + idx * 79,
            prefix=f"v2_p{idx:03d}",
            reference_image=ref_arg,
        )
        with open(img_path, "wb") as f:
            f.write(art.png)
        logger.info(f"✓ Panel {idx:02d} rendered in {time.time() - t0:.1f}s ({img_path.stat().st_size / 1024:.1f} KB)")
        generated_images.append(img_path)

    # 2. Synthesize expressive human-like narration and render rock-solid smooth 1080p shots
    shot_clips: List[Path] = []
    logger.info("🎬 Rendering Synced Smooth Motion Shots for each Unique Panel...")
    
    # 4K pre-scaled smooth zoom/pan definitions (eliminates integer truncation shake completely)
    smooth_motion_filters = {
        "slow_push": "scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0006,1.10)':d={d}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        "smooth_descent": "scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='1.08':d={d}:x='iw/2-(iw/zoom/2)':y='if(lte(on,1),0,y+0.8)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        "smooth_pan_up": "scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='1.08':d={d}:x='iw/2-(iw/zoom/2)':y='if(lte(on,1),ih*0.07,y-0.8)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        "smooth_lateral": "scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='1.08':d={d}:x='if(lte(on,1),0,x+1.0)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
    }
    
    for idx, p in enumerate(EPISODE_1_UNIQUE_PANELS, 1):
        img = generated_images[idx - 1]
        shot_clip = output_dir / f"shot_{idx:03d}.mp4"
        audio_clip = output_dir / f"audio_{idx:03d}.mp3"
        
        # A. Synthesize expressive narrator audio (slower rate -6% & pitch -2Hz for gravitas)
        comm = edge_tts.Communicate(text=p["narration"], voice=voice, rate="-6%", pitch="-2Hz")
        await comm.save(str(audio_clip))
            
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(audio_clip)],
            capture_output=True, text=True, check=True
        )
        audio_dur = float(probe.stdout.strip())
        panel_duration = max(6.0, round(audio_dur + 0.8, 1))
        frames_count = int(panel_duration * 30)
        
        # B. Render smooth motion shot with hardware acceleration
        motion_key = p.get("motion", "slow_push")
        filter_template = smooth_motion_filters.get(motion_key, smooth_motion_filters["slow_push"])
        vf_filter = filter_template.replace("{d}", str(frames_count))
        
        cmd = [
            ffmpeg_bin, "-y",
            "-loop", "1", "-i", str(img),
            "-i", str(audio_clip),
            "-vf", vf_filter,
            "-c:v", "h264_nvenc" if encoder.check_runtime().get("h264_hardware_nvenc") else "libx264",
            "-c:a", "aac", "-b:a", "192k",
            "-af", f"apad=whole_dur={panel_duration}",
            "-t", str(panel_duration),
            "-pix_fmt", "yuv420p",
            str(shot_clip)
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logger.info(f"✓ Shot {idx:02d}/20 rendered ({panel_duration:.1f}s, unique subject: {p['title']})")
        shot_clips.append(shot_clip)

    # 3. Concatenate all 20 unique shots into final master video
    concat_manifest = output_dir / "shots_manifest.txt"
    with open(concat_manifest, "w", encoding="utf-8") as f:
        for s in shot_clips:
            f.write(f"file '{s.resolve().as_posix()}'\n")

    master_video = output_dir / "episode_0001_true_manhua_master_v2.mp4"
    cmd_concat = [
        ffmpeg_bin, "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_manifest.as_posix(),
        "-c", "copy",
        str(master_video)
    ]
    subprocess.run(cmd_concat, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    probe_res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration,size", "-of", "json", str(master_video)],
        capture_output=True, text=True, check=True
    )
    data = json.loads(probe_res.stdout)
    final_dur = float(data["format"]["duration"])
    final_size_mb = float(data["format"]["size"]) / (1024 * 1024)
    
    logger.info("================================================================================")
    logger.info(f"🎉 TRUE MANHUA VIDEO V2 COMPLETED: {master_video}")
    logger.info(f"Duration: {final_dur:.2f}s ({final_dur/60:.2f} mins) | Size: {final_size_mb:.2f} MB | 20 UNIQUE PANELS")
    logger.info("================================================================================")
    return master_video


if __name__ == "__main__":
    asyncio.run(produce_true_manhua_episode())
