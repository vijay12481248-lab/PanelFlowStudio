"""FastAPI router for Creative Multi-Agent Novel & Storyboard Studio."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from engine.creative.orchestrator import CreativeOrchestrator
from engine.creative.schema import CreativeProject, StorySeed
from engine.creative.vault import CreativeVault
from engine.comfyui.art import ArtEngine

logger = logging.getLogger("panelflow.api.creative")
router = APIRouter(prefix="/api/creative", tags=["creative"])
vault = CreativeVault()
orchestrator = CreativeOrchestrator(vault)


class AnchorGenRequest(BaseModel):
    project_id: str
    character_id: Optional[str] = None
    shot_index: Optional[int] = None
    prompt_override: Optional[str] = None


@router.post("/synthesize", response_model=Dict[str, Any])
async def synthesize_story(seed: StorySeed):
    """Trigger the autonomous multi-agent creation pipeline from an abstract prompt."""
    try:
        project = await orchestrator.synthesize_story(seed)
        return {
            "status": "success",
            "project_id": project.project_id,
            "title": project.title,
            "chapters_count": len(project.chapters),
            "scenes_count": len(project.scenes),
            "shots_count": sum(len(s.shots) for s in project.scenes),
            "parent_path": project.parent_path,
            "project": project.model_dump(),
        }
    except Exception as e:
        logger.exception(f"Synthesis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects", response_model=List[Dict[str, Any]])
def list_creative_projects():
    """List all saved creative projects."""
    return vault.list_projects()


@router.get("/project/{project_id}", response_model=Dict[str, Any])
def get_creative_project(project_id: str):
    """Retrieve full project details by project id."""
    project = vault.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return project.model_dump()


@router.post("/generate_anchor", response_model=Dict[str, Any])
async def generate_anchor_art(req: AnchorGenRequest):
    """Generate a keyframe anchor image using ArtEngine (Qwen Image 2.1 Turbo)."""
    project = vault.get_project(req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{req.project_id}' not found")

    prompt = req.prompt_override or ""
    char = None
    if req.character_id:
        char = next((c for c in project.bible.characters if c.id == req.character_id), None)
        if char and not prompt:
            prompt = (
                f"Masterpiece cinematic portrait, {char.name}, {char.visual_tags}. "
                f"{char.facial_features}. {project.seed.visual_style.value} style, 8k resolution, dramatic lighting."
            )

    if not prompt and req.shot_index:
        for sc in project.scenes:
            for sh in sc.shots:
                if sh.shot_index == req.shot_index:
                    prompt = sh.art_prompt or sh.prompt
                    break

    if not prompt:
        raise HTTPException(status_code=400, detail="Unable to resolve prompt for anchor generation")

    logger.info(f"Generating anchor image via ArtEngine: {prompt[:80]}...")
    try:
        # Invoke central ArtEngine (single approved workflow: qwen_image_21)
        art_image = await asyncio.to_thread(
            ArtEngine().generate,
            prompt=prompt,
            width=1024,
            height=1024,
        )
        image_name = art_image.filename

        if char and image_name:
            char.anchor_image = image_name
            # Re-sync character in vault
            vault.sync_characters_from_bible(project.bible.characters)

        if req.shot_index and image_name:
            for sc in project.scenes:
                for sh in sc.shots:
                    if sh.shot_index == req.shot_index:
                        sh.first_frame = image_name
                        break

        # Re-save project and update screenplay
        vault.save_project(project)
        return {
            "status": "success",
            "image": image_name,
            "prompt": prompt,
            "project_id": project.project_id,
        }
    except Exception as e:
        logger.exception(f"ArtEngine anchor generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/export_storyboard", response_model=Dict[str, Any])
def export_storyboard_blueprint(project_id: str):
    """Re-export storyboard blueprint directly into the ChronoFlow vault."""
    project = vault.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    screenplay_path = vault.export_to_screenplay(project)
    return {
        "status": "success",
        "screenplay_path": str(screenplay_path),
        "title": project.title,
    }
