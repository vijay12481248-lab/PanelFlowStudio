"""YouTube packaging and ComfyUI thumbnail research generator for PanelFlow Studio."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from engine.database.models import CharacterRecord, ProjectRecord, RenderJobRecord, SceneRecord
from engine.security.paths import resolve_contained_path

logger = logging.getLogger("panelflow.story.packaging")


class YouTubeThumbnailResearch(BaseModel):
    aspect_ratio: str = Field(default="16:9", description="16:9, 9:16, or 1:1")
    recommended_width: int = Field(default=1280, ge=256, le=2048)
    recommended_height: int = Field(default=720, ge=256, le=2048)
    prompt: str = Field(..., description="Prompt for ComfyUI thumbnail generation")
    negative_prompt: str = Field(..., description="Negative prompt for ComfyUI")
    workflow_id: str = Field(default="manga_image_generation")
    seed: int = Field(default=20261023)
    text_hooks: List[str] = Field(default_factory=list)
    composition_guidance: str = Field(default="")


class YouTubeChapter(BaseModel):
    timestamp: str = Field(..., description="00:00 format")
    seconds: float = Field(..., ge=0.0)
    title: str = Field(..., min_length=1)


class YouTubePackagingData(BaseModel):
    project_id: str
    titles: List[str]
    selected_title: str
    description: str
    tags: List[str]
    tags_string: str
    hashtags: List[str]
    hashtags_string: str
    chapters: List[YouTubeChapter]
    thumbnail: YouTubeThumbnailResearch
    generated_at: str
    source_profile: str


def _clean_tag(text: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"\s+", " ", cleaned)


def _format_timestamp(seconds: float) -> str:
    total_sec = max(0, int(seconds))
    mins = total_sec // 60
    secs = total_sec % 60
    return f"{mins:02d}:{secs:02d}"


def _infer_aspect_ratio_and_dims(profile_name: str | None) -> tuple[str, int, int]:
    profile_lower = (profile_name or "").lower()
    if "vertical" in profile_lower or "shorts" in profile_lower or "9:16" in profile_lower:
        return "9:16", 720, 1280
    elif "square" in profile_lower or "1:1" in profile_lower:
        return "1:1", 1024, 1024
    else:
        # Standard 16:9 Landscape YouTube thumbnail (multiples of 8)
        return "16:9", 1280, 720


def generate_heuristic_packaging(
    project: ProjectRecord,
    profile_name: str | None = None,
    focus_character: str | None = None,
    style_tone: str = "dramatic",
    custom_hook: str | None = None,
) -> YouTubePackagingData:
    """Generate high-CTR, SEO-optimized YouTube packaging deterministically from project data."""
    title = project.title.strip() or "Untitled Manga Project"
    clean_title = re.sub(r"[^\w\s]", "", title).strip()

    # Discover characters
    characters: List[CharacterRecord] = list(project.characters or [])
    focus_char_name = focus_character
    focus_char_desc = ""
    if not focus_char_name and characters:
        first_char = characters[0]
        focus_char_name = getattr(first_char, "display_name", None) or getattr(first_char, "canonical_name", None) or getattr(first_char, "name", "The Protagonist")
        traits = getattr(first_char, "visual_traits", []) or []
        traits_str = ", ".join(traits) if isinstance(traits, list) else str(traits)
        focus_char_desc = getattr(first_char, "description", "") or traits_str
    elif focus_char_name:
        match = next((
            c for c in characters
            if (getattr(c, "display_name", "") or getattr(c, "canonical_name", "") or getattr(c, "name", "")).lower() == focus_char_name.lower()
        ), None)
        if match:
            traits = getattr(match, "visual_traits", []) or []
            traits_str = ", ".join(traits) if isinstance(traits, list) else str(traits)
            focus_char_desc = getattr(match, "description", "") or traits_str

    if not focus_char_name:
        focus_char_name = "The Protagonist"
        focus_char_desc = "young adult warrior with intense glowing eyes, expressive facial emotion, flowing hair and dramatic attire"

    # Discover scenes and calculate chapters
    scenes: List[SceneRecord] = list(project.scenes or [])
    scenes.sort(key=lambda s: getattr(s, "sequence", 0))

    chapters: List[YouTubeChapter] = []
    current_time = 0.0
    for idx, sc in enumerate(scenes):
        sc_title = sc.title or f"Scene {idx + 1}"
        duration = float(getattr(sc, "duration_sec", 4.0) or 4.0)
        chapters.append(YouTubeChapter(
            timestamp=_format_timestamp(current_time),
            seconds=current_time,
            title=sc_title,
        ))
        current_time += duration

    if not chapters:
        chapters = [
            YouTubeChapter(timestamp="00:00", seconds=0.0, title="Prologue"),
            YouTubeChapter(timestamp="00:15", seconds=15.0, title="The Turning Point"),
            YouTubeChapter(timestamp="00:30", seconds=30.0, title="The Climax"),
        ]

    aspect_ratio, rec_w, rec_h = _infer_aspect_ratio_and_dims(profile_name)
    is_shorts = aspect_ratio == "9:16"

    # Craft CTR Titles
    hook_prefix = f"[{custom_hook.strip()}] " if custom_hook and custom_hook.strip() else ""
    if is_shorts:
        titles = [
            f"{hook_prefix}This Scene Left Everyone SPEECHLESS! 😱🔥 #{clean_title.replace(' ', '')} #Shorts",
            f"{hook_prefix}When {focus_char_name} Finally Unleashes Their Power... ⚡ #Anime #Shorts",
            f"{hook_prefix}The Secret No One Saw Coming! [{clean_title}] #Shorts",
            f"{hook_prefix}Nobody Believed Them Until THIS Happened! 💀 #MotionComic #Shorts",
        ]
    else:
        titles = [
            f"{hook_prefix}He Awakened The Forbidden Power... And Everyone Regretted It! | {title} [Motion Comic]",
            f"{hook_prefix}When {focus_char_name} Broke The Ancient Rule... No One Could Stop Them! [Full Episode]",
            f"{hook_prefix}The Secret Kept For A Thousand Years Revealed! | {title} Motion Comic",
            f"{hook_prefix}They Thought {focus_char_name} Was Weak... Until The Mask Came Off!",
        ]

    selected_title = titles[0]

    # Craft Description
    synopsis = (
        (project.source_metadata.get("synopsis") if isinstance(project.source_metadata, dict) else None)
        or (project.settings.get("synopsis") if isinstance(project.settings, dict) else None)
        or f"An epic manga motion comic experience bringing '{title}' to life with voice acting, sound effects, and dynamic cinematic animation."
    )

    chapters_text = "\n".join(f"{ch.timestamp} - {ch.title}" for ch in chapters)
    clean_tag_slug = clean_title.replace(" ", "")

    description = f"""{selected_title}

{synopsis}

📌 CHAPTER TIMESTAMPS:
{chapters_text}

✨ SUPPORT THE SERIES:
👍 Like the video if you enjoyed this motion comic!
💬 Comment below with your favorite scene or theory!
🔔 SUBSCRIBE & turn on notifications so you never miss the next episode!

🎨 CREDITS & PRODUCTION:
• Motion Comic Production: PanelFlow Studio
• Original Work: {title}
• Audio & Visual Engineering: PanelFlow Production Engine

#{clean_tag_slug} #MotionComic #Anime #Manga #Webtoon #AnimeAnimation #FullEpisode #MangaDub
""".strip()

    # Craft Tags
    base_tags = [
        _clean_tag(title),
        "motion comic",
        "manga animation",
        "webtoon dub",
        "anime comic",
        "manga recap",
        "full episode",
        "comic dub",
        "anime",
        "manga",
        "webtoon",
        "manhwa",
        "panelflow",
        _clean_tag(focus_char_name),
        "animated manga",
        "voice acting",
        "motion manga",
    ]
    if is_shorts:
        base_tags.extend(["shorts", "anime shorts", "manga shorts", "youtube shorts"])
    else:
        base_tags.extend(["cinematic motion comic", "manga dub full", "action anime"])

    seen_tags = set()
    tags = []
    for t in base_tags:
        if t and t not in seen_tags and len(t) <= 40:
            seen_tags.add(t)
            tags.append(t)

    tags_string = ", ".join(tags)

    # Hashtags
    hashtags = [
        f"#{clean_tag_slug}",
        "#MotionComic",
        "#Anime",
        "#Manga",
        "#Webtoon",
        "#MangaAnimation",
        "#AnimeDub",
    ]
    if is_shorts:
        hashtags.insert(1, "#Shorts")
    hashtags_string = " ".join(hashtags)

    # ComfyUI Thumbnail Prompt Engineering
    desc_part = focus_char_desc if focus_char_desc else "striking anime protagonist with intense expressive eyes and flowing hair"
    prompt = (
        f"masterpiece anime YouTube thumbnail key art, {focus_char_name}, {desc_part}, "
        f"dynamic 3/4 angle, intense dramatic facial expression, piercing glowing eyes, "
        f"bold vibrant anime colors, cinematic rim lighting, volumetric energy glow, "
        f"sharp cel-shaded linework, clean separation from atmospheric background, "
        f"depth of field, rule of thirds, highly clickable YouTube thumbnail composition, "
        f"trending on ArtStation and Pixiv, 8k resolution, ultra detailed"
    )

    negative_prompt = (
        "text, watermark, logo, title, username, subtitles, borders, frame, "
        "blurry, low quality, bad anatomy, extra limbs, deformed hands, extra fingers, "
        "fused fingers, distorted eyes, amateur illustration, muted flat colors, "
        "cluttered noisy background, duplicate character, bad proportions"
    )

    text_hooks = [
        "HE AWAKENED?!",
        "THE TRUTH REVEALED!",
        "DON'T LOOK BACK!",
        "TOO LATE TO RUN!",
    ]

    composition_guidance = (
        "Position the main subject off-center along the left or right third. "
        "Maintain high contrast between character edges and the background. "
        "Leave the top-left or bottom-left zone clear for optional bold high-CTR hook text. "
        "Ensure the right bottom corner (timestamp area in YouTube UI) contains no critical focal elements."
    )

    thumbnail_research = YouTubeThumbnailResearch(
        aspect_ratio=aspect_ratio,
        recommended_width=rec_w,
        recommended_height=rec_h,
        prompt=prompt,
        negative_prompt=negative_prompt,
        workflow_id="manga_image_generation",
        seed=20261023,
        text_hooks=text_hooks,
        composition_guidance=composition_guidance,
    )

    now_iso = datetime.now(timezone.utc).isoformat()
    return YouTubePackagingData(
        project_id=str(project.id),
        titles=titles,
        selected_title=selected_title,
        description=description,
        tags=tags,
        tags_string=tags_string,
        hashtags=hashtags,
        hashtags_string=hashtags_string,
        chapters=chapters,
        thumbnail=thumbnail_research,
        generated_at=now_iso,
        source_profile=profile_name or "standard_1080p",
    )


async def generate_youtube_packaging(
    db: Session,
    project_id: str,
    profile_name: str | None = None,
    focus_character: str | None = None,
    style_tone: str = "dramatic",
    custom_hook: str | None = None,
) -> YouTubePackagingData:
    """Generate YouTube packaging with LLM research if configured, falling back smoothly to heuristics."""
    project = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    if not project:
        raise ValueError("Project not found")

    # If profile_name is not provided, check the most recent completed render job
    if not profile_name:
        latest_render = (
            db.query(RenderJobRecord)
            .filter(RenderJobRecord.project_id == project_id)
            .order_by(RenderJobRecord.created_at.desc())
            .first()
        )
        if latest_render and latest_render.output_profile:
            profile_name = latest_render.output_profile

    # Start with robust heuristic baseline
    packaging = generate_heuristic_packaging(
        project=project,
        profile_name=profile_name,
        focus_character=focus_character,
        style_tone=style_tone,
        custom_hook=custom_hook,
    )

    # Attempt LLM enhancement if active provider exists
    try:
        from engine.llm.registry import LLMRegistry
        registry = LLMRegistry()
        provider = await registry.get_active_provider()

        system_prompt = (
            "You are an expert YouTube anime/manga video packaging director and thumbnail strategist. "
            "You craft high-CTR titles, engaging descriptions with chapter timestamps, SEO tags, "
            "and professional ComfyUI / Stable Diffusion anime art prompts for motion comic videos."
        )

        user_prompt = f"""Generate YouTube release packaging for this motion comic video:
Project Title: {project.title}
Target Aspect Ratio: {packaging.thumbnail.aspect_ratio} ({packaging.thumbnail.recommended_width}x{packaging.thumbnail.recommended_height})
Focus Character: {focus_character or 'Main Character'}
Tone: {style_tone}
Custom Hook: {custom_hook or 'None'}
Scenes: {len(packaging.chapters)} chapters total

Respond in strictly valid JSON matching this schema:
{{
  "titles": ["Title 1 (High CTR)", "Title 2 (Curiosity)", "Title 3 (Dramatic)", "Title 4 (Action)"],
  "description": "Engaging description with hook, synopsis, chapter timestamps, and CTA",
  "tags": ["tag1", "tag2", "tag3"],
  "text_hooks": ["SHORT HOOK 1", "SHORT HOOK 2", "SHORT HOOK 3"],
  "thumbnail_prompt": "masterpiece anime YouTube thumbnail key art, ... (detailed prompt)",
  "thumbnail_negative_prompt": "text, watermark, ... (detailed negative prompt)"
}}
"""
        raw_text = await provider.generate_text(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=1500,
        )

        # Parse JSON from model
        cleaned_json = raw_text.strip()
        if "```json" in cleaned_json:
            cleaned_json = cleaned_json.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in cleaned_json:
            cleaned_json = cleaned_json.split("```", 1)[1].split("```", 1)[0].strip()

        data = json.loads(cleaned_json)
        if isinstance(data, dict):
            if isinstance(data.get("titles"), list) and data["titles"]:
                packaging.titles = [str(t) for t in data["titles"] if t]
                packaging.selected_title = packaging.titles[0]
            if isinstance(data.get("description"), str) and len(data["description"]) > 20:
                packaging.description = data["description"]
            if isinstance(data.get("tags"), list) and data["tags"]:
                packaging.tags = [str(t) for t in data["tags"] if t]
                packaging.tags_string = ", ".join(packaging.tags)
            if isinstance(data.get("text_hooks"), list) and data["text_hooks"]:
                packaging.thumbnail.text_hooks = [str(h) for h in data["text_hooks"] if h]
            if isinstance(data.get("thumbnail_prompt"), str) and len(data["thumbnail_prompt"]) > 20:
                packaging.thumbnail.prompt = data["thumbnail_prompt"]
            if isinstance(data.get("thumbnail_negative_prompt"), str) and len(data["thumbnail_negative_prompt"]) > 10:
                packaging.thumbnail.negative_prompt = data["thumbnail_negative_prompt"]
            logger.info("Successfully enhanced YouTube packaging with active LLM provider")
    except Exception as exc:
        logger.info("LLM packaging enhancement skipped/fallback to heuristic: %s", exc)

    # Persist cached packaging into project workspace
    try:
        workspace = Path(str(project.workspace_path))
        gen_dir = resolve_contained_path(workspace, Path("generated"))
        gen_dir.mkdir(parents=True, exist_ok=True)
        target = resolve_contained_path(workspace, Path("generated") / "youtube_packaging.json")
        target.write_text(packaging.model_dump_json(indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("Could not persist youtube_packaging.json to workspace: %s", exc)

    return packaging
