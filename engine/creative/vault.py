"""Persistent Lore and Character Vault for the Creative Studio.

Manages persistent storage, character roster synchronization with ChronoFlow's
characters.json, and exports storyboard blueprints directly into the Studio vault.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.creative.schema import (
    CharacterProfile,
    CinematicScene,
    CinematicShot,
    CreativeProject,
    NovelChapter,
    StoryBible,
)

logger = logging.getLogger("panelflow.creative.vault")

CHRONOFLOW_VAULT_DIR = Path("engine/chronoflow/vault")
CHARACTERS_JSON_PATH = CHRONOFLOW_VAULT_DIR / "characters.json"
LORE_VAULT_DIR = CHRONOFLOW_VAULT_DIR / "lore"


class CreativeVault:
    """Manages reading, persisting, and synchronizing creative lore, characters, and storyboards."""

    def __init__(self, vault_dir: Path = CHRONOFLOW_VAULT_DIR):
        self.vault_dir = vault_dir
        self.lore_dir = vault_dir / "lore"
        self.characters_path = vault_dir / "characters.json"
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        self.lore_dir.mkdir(parents=True, exist_ok=True)

    def load_characters(self) -> List[Dict[str, Any]]:
        """Load character definitions from characters.json."""
        if not self.characters_path.exists():
            return []
        try:
            with open(self.characters_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load characters from {self.characters_path}: {e}")
            return []

    def sync_characters_from_bible(self, characters: List[CharacterProfile]) -> int:
        """Add new characters from a StoryBible into characters.json without duplicating existing ids."""
        existing = self.load_characters()
        existing_ids = {c.get("id") for c in existing if isinstance(c, dict)}
        added_count = 0

        next_tag_index = len(existing) + 1
        for char in characters:
            if char.id not in existing_ids:
                entry = {
                    "id": char.id,
                    "name": char.name,
                    "role": char.role,
                    "image": char.anchor_image or "",
                    "description": f"{char.name}. {char.visual_tags}. Personality: {char.personality}",
                    "tag": f"<Picture {next_tag_index}>",
                }
                existing.append(entry)
                existing_ids.add(char.id)
                next_tag_index += 1
                added_count += 1

        if added_count > 0:
            with open(self.characters_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
            logger.info(f"Synchronized {added_count} new character(s) into {self.characters_path}")
        return added_count

    def save_project(self, project: CreativeProject) -> Path:
        """Persist a full CreativeProject to disk."""
        proj_dir = self.lore_dir / project.project_id
        proj_dir.mkdir(parents=True, exist_ok=True)

        # 1. Save project metadata & Bible
        project_json_path = proj_dir / "project.json"
        with open(project_json_path, "w", encoding="utf-8") as f:
            json.dump(project.model_dump(), f, indent=2, ensure_ascii=False)

        # 2. Save Markdown chapters
        for ch in project.chapters:
            ch_filename = f"chapter_{ch.chapter_number:02d}.md"
            ch_path = proj_dir / ch_filename
            md_content = f"# Chapter {ch.chapter_number}: {ch.title}\n\n"
            if ch.epigraph:
                md_content += f"> *{ch.epigraph}*\n\n---\n\n"
            md_content += f"{ch.prose}\n"
            ch_path.write_text(md_content, encoding="utf-8")

        # 3. Export to ChronoFlow Screenplay JSON
        screenplay_path = self.export_to_screenplay(project)
        logger.info(f"Project '{project.title}' saved to {proj_dir} and screenplay at {screenplay_path}")
        return proj_dir

    def export_to_screenplay(self, project: CreativeProject) -> Path:
        """Export project scenes and shots to a ChronoFlow-compatible screenplay blueprint."""
        slug = re.sub(r"[^a-z0-9]+", "_", project.title.lower()).strip("_")
        screenplay_filename = f"screenplay_{slug}.json"
        screenplay_path = self.vault_dir / screenplay_filename

        # Determine protagonist
        protagonist_entry = None
        if project.bible.characters:
            main_char = project.bible.characters[0]
            protagonist_entry = {
                "id": main_char.id,
                "name": main_char.name,
                "role": main_char.role,
                "image": main_char.anchor_image or "",
                "description": main_char.visual_tags,
                "tag": main_char.tag,
            }

        # Build folder list
        folders = []
        all_shots_flat = []

        total_duration = 0.0
        first_frame_anchor = ""

        for sc in project.scenes:
            shot_indices = [shot.shot_index for shot in sc.shots]
            folder_dict = {
                "id": sc.id,
                "name": sc.name,
                "description": sc.description,
                "path": sc.path or (f"{project.parent_path}\\{sc.name}" if project.parent_path else ""),
                "shot_indices": shot_indices,
            }
            folders.append(folder_dict)

            for shot in sc.shots:
                total_duration += shot.duration
                if not first_frame_anchor and shot.first_frame:
                    first_frame_anchor = shot.first_frame

                shot_dict = {
                    "shot_index": shot.shot_index,
                    "title": shot.title,
                    "shot_type": shot.shot_type,
                    "duration": shot.duration,
                    "workflow": shot.workflow,
                    "first_frame": shot.first_frame or "",
                    "last_frame": shot.last_frame or "",
                    "ref_images": [],
                    "prompt": shot.prompt,
                    "rendered_video": shot.rendered_video,
                    "rendered_video_filename": shot.rendered_video_filename,
                    "folder_id": sc.id,
                }
                all_shots_flat.append(shot_dict)

        blueprint = {
            "title": project.title.upper(),
            "duration": round(total_duration, 2),
            "protagonist": protagonist_entry,
            "anchor_images": {
                "start": first_frame_anchor,
                "climax": "",
                "concept": "",
            },
            "parent_path": project.parent_path,
            "folders": folders,
            "scenes": all_shots_flat,
        }

        with open(screenplay_path, "w", encoding="utf-8") as f:
            json.dump(blueprint, f, indent=2, ensure_ascii=False)

        return screenplay_path

    def list_projects(self) -> List[Dict[str, Any]]:
        """List all saved creative projects."""
        projects = []
        if not self.lore_dir.exists():
            return projects

        for item in self.lore_dir.iterdir():
            if item.is_dir():
                proj_json = item / "project.json"
                if proj_json.exists():
                    try:
                        with open(proj_json, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            projects.append({
                                "project_id": data.get("project_id"),
                                "title": data.get("title"),
                                "genre": data.get("seed", {}).get("genre"),
                                "created_at": data.get("created_at"),
                                "chapters_count": len(data.get("chapters", [])),
                                "scenes_count": len(data.get("scenes", [])),
                                "parent_path": data.get("parent_path"),
                            })
                    except Exception as e:
                        logger.warning(f"Error reading {proj_json}: {e}")
        return projects

    def get_project(self, project_id: str) -> Optional[CreativeProject]:
        """Load a project by its id."""
        proj_json = self.lore_dir / project_id / "project.json"
        if not proj_json.exists():
            return None
        try:
            with open(proj_json, "r", encoding="utf-8") as f:
                data = json.load(f)
                return CreativeProject(**data)
        except Exception as e:
            logger.error(f"Failed to load project {project_id}: {e}")
            return None
