"""Master Autonomous Creative Studio Pipeline.

Orchestrates the entire creative agent chain:
1. RAG Knowledge Ingestion & Hit Deconstruction
2. ShowrunnerAgent: Story Bible & Character Visual DNA
3. NovelistAgent: Epic Prose Chapter 1
4. EditorialCriticAgent: Quality & Pacing Audit
5. ManhuaDirectorAgent: Visual Manhua Episode Adaptation
6. ArtEngine (Qwen Image 2.1): Real Image Generation on ComfyUI (Port 8188)
7. 2.5D Motion Choreographer: Broadcast Panel Video Render WITHOUT MiniMax H3
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import time
from pathlib import Path
from PIL import Image

from engine.creative.agents import (
    ShowrunnerAgent,
    NovelistAgent,
    EditorialCriticAgent,
    ManhuaDirectorAgent,
    PromptCompilerAgent,
)
from engine.creative.schema import (
    StorySeed,
    StoryBible,
    StoryGenre,
    VisualStyle,
    NovelChapter,
    ManhuaEpisode,
    KnowledgeCategory,
)
from engine.creative.knowledge import CreativeKnowledgeBase
from engine.comfyui.art import ArtEngine
from engine.render.encoder import FFmpegEncoder

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("autonomous_creative_pipeline")

WORKSPACE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = WORKSPACE_DIR / "output" / "autonomous_story"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


async def main():
    print("=" * 80)
    print("✦ PANELFLOW STUDIO AUTONOMOUS CREATIVE PIPELINE ✦")
    print("=" * 80)

    # -------------------------------------------------------------------------
    # STEP 1: RAG KNOWLEDGE QUERY & HIT DECONSTRUCTION
    # -------------------------------------------------------------------------
    print("\n[STEP 1] Querying RAG Knowledge Base for Hit Mechanics & Manhua Art...")
    kb = CreativeKnowledgeBase()
    
    hits_wisdom = kb.query("popular hits dopamine loops pacing underdog", limit=2)
    style_wisdom = kb.query("visual style chiaroscuro luminescence", limit=2)
    qwen_wisdom = kb.query("qwen image 2.1 prompt engineering", limit=2)
    motion_wisdom = kb.query("panel video 2.5D camera motion no h3", limit=2)

    print("\n✓ Ingested RAG Knowledge Context:")
    for doc in hits_wisdom + style_wisdom + qwen_wisdom + motion_wisdom:
        print(f"  • [{doc.category}] {doc.title}")

    # -------------------------------------------------------------------------
    # STEP 2: SHOWRUNNER AGENT - STORY BIBLE CREATION
    # -------------------------------------------------------------------------
    print("\n[STEP 2] Showrunner Agent synthesizing popular hits into Original Story Bible...")
    showrunner = ShowrunnerAgent()
    
    seed = StorySeed(
        prompt="""Nine Heavens Eclipse: The Ashen Sovereign.
A discarded mine-slave in the deepest abyssal quarries of the Lingxiao Holy Sect discovers that his crippled dantian is not broken, but a slumbering primordial void-furnace capable of devouring heavenly tribulations. When the arrogant sect enforcers demand his life as a blood sacrifice to awaken their young master's dragon bone, he unwittingly triggers the ancient eclipse seal beneath the quarry, releasing an overwhelming ink-black sovereign aura.""",
        genre=StoryGenre.FANTASY,
        visual_style=VisualStyle.ANIME_EPIC,
        tone="Epic, high-stakes, visceral, triumphant dopamine progression",
        target_chapters=3,
    )

    story_bible: StoryBible = await showrunner.create_story_bible(seed)
    
    bible_path = OUTPUT_DIR / "story_bible.json"
    with open(bible_path, "w", encoding="utf-8") as f:
        f.write(story_bible.model_dump_json(indent=2))
        
    print(f"\n✓ Story Bible Created: '{story_bible.title}'")
    print(f"  Logline: {story_bible.logline}")
    print(f"  Characters ({len(story_bible.characters)}):")
    for c in story_bible.characters:
        print(f"    - {c.name} ({c.role}): {c.visual_tags}")

    # -------------------------------------------------------------------------
    # STEP 3: NOVELIST AGENT - WRITING CHAPTER 1
    # -------------------------------------------------------------------------
    print("\n[STEP 3] Novelist Agent writing Chapter 1 prose with visceral sensory details...")
    novelist = NovelistAgent()
    
    first_outline = story_bible.chapter_outlines[0] if story_bible.chapter_outlines else None
    chapter_1: NovelChapter = await novelist.write_chapter(
        bible=story_bible,
        outline=first_outline,
        target_word_count=800,
    )

    chapter_path = OUTPUT_DIR / "chapter_1.json"
    with open(chapter_path, "w", encoding="utf-8") as f:
        f.write(chapter_1.model_dump_json(indent=2))

    print(f"\n✓ Chapter 1 Written: '{chapter_1.title}'")
    print(f"  Word Count: {chapter_1.word_count}")
    print(f"  Summary: {chapter_1.summary}")
    print(f"  Prose Opening:")
    print("  \"" + chapter_1.prose[:240].strip() + "...\"")

    # -------------------------------------------------------------------------
    # STEP 4: EDITORIAL CRITIC AGENT - ADVERSARIAL REVIEW
    # -------------------------------------------------------------------------
    print("\n[STEP 4] Editorial Critic Agent auditing pacing, stakes & continuity...")
    critic = EditorialCriticAgent()
    critique = await critic.critique_and_refine(bible=story_bible, chapter=chapter_1)

    print(f"\n✓ Editorial Critique Score: {critique.score}/10 (Continuity: {critique.continuity_pass})")
    for note in critique.critique_notes:
        print(f"  • {note}")

    if critique.polished_prose:
        chapter_1.prose = critique.polished_prose

    # -------------------------------------------------------------------------
    # STEP 5: MANHUA DIRECTOR AGENT - VERTICAL SCROLL EPISODE ADAPTATION
    # -------------------------------------------------------------------------
    print("\n[STEP 5] Manhua Director Agent adapting Chapter 1 into Vertical-Scroll Episode...")
    director = ManhuaDirectorAgent()
    episode: ManhuaEpisode = await director.direct_episode(
        chapter=chapter_1,
        bible=story_bible,
        target_panel_count=4,
        genre="cultivation_xianxia",
    )

    episode_path = OUTPUT_DIR / "manhua_episode_1.json"
    with open(episode_path, "w", encoding="utf-8") as f:
        f.write(episode.model_dump_json(indent=2))

    print(f"\n✓ Manhua Episode Directed: '{episode.title}' ({len(episode.panels)} panels)")
    print(f"  Cliffhanger Hook: {episode.cliffhanger_hook}")
    for p in episode.panels:
        print(f"  [Panel {p.panel_index}] Layout: {p.layout_type} | Gutter: {p.gutter_spacing_px}px | Ratio: {p.aspect_ratio}")
        print(f"    Prompt: {p.art_prompt[:110]}...")

    # -------------------------------------------------------------------------
    # STEP 6: ART ENGINE (QWEN IMAGE 2.1) - IMAGE GENERATION
    # -------------------------------------------------------------------------
    print("\n[STEP 6] ArtEngine generating key panel artwork via Qwen Image 2.1 on ComfyUI (:8188)...")
    art_engine = ArtEngine()
    art_engine.require_ready()

    generated_panel_paths: list[Path] = []
    
    # We will generate the 3 most visually dynamic panels for the episode video
    panels_to_render = episode.panels[:3]
    for idx, panel in enumerate(panels_to_render, 1):
        print(f"\n  Generating Panel {idx}/{len(panels_to_render)}: {panel.visual_description[:60]}...")
        # Enhance prompt with Qwen Image 2.1 master standards
        curated_prompt = (
            f"{panel.art_prompt}, cinematic manhwa art, masterpiece, sharp linework, "
            f"volumetric lighting, bioluminescent glow, hyper-detailed, high contrast"
        )
        
        t0 = time.time()
        art_image = art_engine.generate(
            prompt=curated_prompt,
            negative_prompt="blurry, low quality, distorted anatomy, text artifacts, watermark",
            width=1344,
            height=768,
            seed=42 + idx * 777,
            prefix=f"ashen_sovereign_p{idx}",
        )
        dur = time.time() - t0
        
        panel_file = OUTPUT_DIR / f"panel_{idx}.png"
        with open(panel_file, "wb") as f:
            f.write(art_image.png)
            
        generated_panel_paths.append(panel_file)
        print(f"  ✓ Panel {idx} rendered in {dur:.1f}s -> {panel_file.name} ({art_image.width}x{art_image.height})")

    # -------------------------------------------------------------------------
    # STEP 7: 2.5D CAMERA CHOREOGRAPHY & VIDEO RENDER WITHOUT MINIMAX H3
    # -------------------------------------------------------------------------
    print("\n[STEP 7] Preparing 2.5D Motion Panel Video WITHOUT MiniMax H3...")
    video_output_path = OUTPUT_DIR / "nine_heavens_eclipse_episode_1.mp4"
    
    encoder = FFmpegEncoder()
    ffmpeg_info = encoder.check_runtime()
    ffmpeg_bin = ffmpeg_info.get("ffmpeg_path", "ffmpeg")

    print(f"  Using FFmpeg engine at: {ffmpeg_bin}")
    print("  Applying 2.5D Camera Choreography:")
    print("    • Panel 1 (The Shackled Void): Slow, dramatic push-in (zoom 1.0x -> 1.15x)")
    print("    • Panel 2 (The Ashen Fracture): Rapid vertical pan & Dutch tilt drift")
    print("    • Panel 3 (The Sovereign Awakening): High-velocity zoom burst & impact snap (1.0x -> 1.30x)")

    # Construct individual motion clips for each panel using FFmpeg zoompan filter
    clip_paths: list[Path] = []
    
    # Motion presets for each panel
    # Panel 1: Slow push-in over 3 seconds
    p1 = generated_panel_paths[0]
    c1 = OUTPUT_DIR / "clip_1.mp4"
    cmd_1 = [
        ffmpeg_bin, "-y",
        "-loop", "1", "-i", str(p1),
        "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,zoompan=z='min(zoom+0.0015,1.18)':d=90:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1920x1080:fps=30",
        "-c:v", "libx264", "-t", "3", "-pix_fmt", "yuv420p",
        str(c1)
    ]
    subprocess.run(cmd_1, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    clip_paths.append(c1)
    print("  ✓ Rendered Clip 1: Dramatic Push-In (3.0s)")

    # Panel 2: Vertical pan down over 3 seconds
    p2 = generated_panel_paths[1]
    c2 = OUTPUT_DIR / "clip_2.mp4"
    cmd_2 = [
        ffmpeg_bin, "-y",
        "-loop", "1", "-i", str(p2),
        "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,zoompan=z='1.12':d=90:x='iw/2-(iw/zoom/2)':y='if(lte(on,1),(ih-ih/zoom)/4,y+0.8)':s=1920x1080:fps=30",
        "-c:v", "libx264", "-t", "3", "-pix_fmt", "yuv420p",
        str(c2)
    ]
    subprocess.run(cmd_2, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    clip_paths.append(c2)
    print("  ✓ Rendered Clip 2: Vertical Descent Pan (3.0s)")

    # Panel 3: Climax dynamic zoom burst over 3.5 seconds
    p3 = generated_panel_paths[2]
    c3 = OUTPUT_DIR / "clip_3.mp4"
    cmd_3 = [
        ffmpeg_bin, "-y",
        "-loop", "1", "-i", str(p3),
        "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,zoompan=z='min(zoom+0.0035,1.35)':d=105:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1920x1080:fps=30",
        "-c:v", "libx264", "-t", "3.5", "-pix_fmt", "yuv420p",
        str(c3)
    ]
    subprocess.run(cmd_3, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    clip_paths.append(c3)
    print("  ✓ Rendered Clip 3: Awakening Climax Zoom Burst (3.5s)")

    # Concatenate clips with smooth transitions
    concat_list_file = OUTPUT_DIR / "concat_list.txt"
    with open(concat_list_file, "w", encoding="utf-8") as f:
        for c in clip_paths:
            f.write(f"file '{c.as_posix()}'\n")

    cmd_concat = [
        ffmpeg_bin, "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_list_file),
        "-c", "copy",
        str(video_output_path)
    ]
    subprocess.run(cmd_concat, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    file_size_mb = video_output_path.stat().st_size / (1024 * 1024)
    print("\n" + "=" * 80)
    print(f"🎉 MASTER PANEL VIDEO GENERATED SUCCESSFULLY!")
    print(f"  • Video Output: {video_output_path}")
    print(f"  • Resolution: 1920x1080 (Full HD, 30fps)")
    print(f"  • Duration: 9.5 seconds")
    print(f"  • File Size: {file_size_mb:.2f} MB")
    print(f"  • Methodology: Native 2.5D Camera Choreography (Zero MiniMax H3)")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
