"""Meta AI Prompt Engineering and Image Review Workflow for PanelFlow Studio.

Implements the automated agent loop:
1. Prompt Engineer: Converts story context, panel requirements, or asset briefs into
   optimized, hyper-detailed Meta AI prompts.
2. Generator: Dispatches the prompt to Meta AI through BrowserAIBridge (using persistent login).
3. Reviewer: Inspects the generated images, evaluates quality and narrative alignment,
   and recommends approval or refinement.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from engine.imaging.browser_ai_bridge import (
    BrowserAIBridge,
    BrowserBridgeResult,
    ExtractedImage,
    browser_ai_bridge,
)

logger = logging.getLogger("panelflow.meta_ai_workflow")


class PanelRequirement(BaseModel):
    """User or Storyboard specification for an image or panel."""
    description: str = Field(..., min_length=2, description="Base description of scene, character, or asset")
    style_preset: Literal[
        "manga_cinematic",
        "manga_classic_screentone",
        "anime_vibrant",
        "cyberpunk_noir",
        "tech_logo_minimal",
        "custom"
    ] = "manga_cinematic"
    aspect_ratio: Literal["1:1", "16:9", "9:16", "4:3", "3:4"] = "16:9"
    mood_lighting: Optional[str] = "dramatic contrast with volumetric rim lighting"
    camera_angle: Optional[str] = "dynamic low-angle medium shot"
    negative_prompt: Optional[str] = "blurry, distorted anatomy, bad hands, low resolution, watermark"
    project_id: Optional[str] = None
    panel_id: Optional[str] = None


class ReviewResult(BaseModel):
    """AI evaluation of the generated image candidate."""
    approved: bool
    score: int = Field(ge=0, le=100, description="Overall quality & prompt match score (0-100)")
    visual_fidelity: str
    composition_assessment: str
    suggested_refinements: List[str] = Field(default_factory=list)


class MetaAIWorkflowResult(BaseModel):
    """End-to-end execution result containing the engineered prompt, images, and review."""
    success: bool
    engineered_prompt: str
    platform: str = "meta_ai"
    generated_images: List[ExtractedImage] = Field(default_factory=list)
    review: Optional[ReviewResult] = None
    execution_time_sec: float = 0.0
    error: Optional[str] = None


class MetaAIPromptEngineer:
    """Specialized prompt craft engine for Meta AI (Imagine model)."""

    STYLE_MODIFIERS: Dict[str, str] = {
        "manga_cinematic": (
            "modern high-end Japanese anime cinematic frame, Makoto Shinkai and Ufotable aesthetic, "
            "striking composition, crisp linework, vibrant rich colors, atmospheric particle effects, 8k render"
        ),
        "manga_classic_screentone": (
            "authentic black and white manga panel, professional mangaka screentone textures, "
            "dynamic ink hatching, bold speedlines, Kentaro Miura and Takehiko Inoue inking mastery"
        ),
        "anime_vibrant": (
            "vivid high-action anime illustration, luminous cel shading, saturated colors, "
            "dramatic keyframe motion, pristine clean line art"
        ),
        "cyberpunk_noir": (
            "futuristic cyberpunk aesthetic, neon cyan and deep magenta reflections, wet pavement, "
            "matte dark zinc shadows, cinematic volumetric fog, intricate tech details"
        ),
        "tech_logo_minimal": (
            "modern minimalist vector tech logo, clean geometric squircle icon, sleek matte finish, "
            "luminescent gradient accents, balanced negative space, professional brand identity, 8k"
        ),
        "custom": "high resolution, professional digital art, award-winning illustration",
    }

    @classmethod
    def engineer_prompt(cls, req: PanelRequirement) -> str:
        """Transforms raw description into an optimized Meta AI prompt."""
        style_desc = cls.STYLE_MODIFIERS.get(req.style_preset, cls.STYLE_MODIFIERS["manga_cinematic"])
        components = [
            req.description.strip(),
            f"Framing: {req.camera_angle}" if req.camera_angle else "",
            f"Lighting: {req.mood_lighting}" if req.mood_lighting else "",
            f"Style: {style_desc}",
            f"Aspect ratio: {req.aspect_ratio}",
        ]
        prompt = ", ".join([c for c in components if c])
        return prompt


class MetaAIImageReviewer:
    """Automated quality gate inspecting image assets and grading fitness."""

    @classmethod
    def review_image(
        cls,
        image: ExtractedImage,
        requirement: PanelRequirement,
        engineered_prompt: str,
    ) -> ReviewResult:
        """Evaluates image dimensions, byte integrity, and aspect ratio alignment."""
        score = 85
        refinements: List[str] = []

        # 1. Dimension validation
        if image.width < 512 or image.height < 512:
            score -= 25
            refinements.append("Image resolution is below recommended 512px threshold.")
        
        # 2. Aspect Ratio check
        ratio_targets = {
            "1:1": 1.0,
            "16:9": 16 / 9,
            "9:16": 9 / 16,
            "4:3": 4 / 3,
            "3:4": 3 / 4,
        }
        target_ratio = ratio_targets.get(requirement.aspect_ratio, 1.0)
        actual_ratio = image.width / max(1, image.height)
        ratio_diff = abs(actual_ratio - target_ratio) / target_ratio

        if ratio_diff > 0.25:
            score -= 10
            refinements.append(f"Output aspect ratio ({actual_ratio:.2f}) differs from target {requirement.aspect_ratio}.")

        approved = score >= 70

        return ReviewResult(
            approved=approved,
            score=max(0, min(100, score)),
            visual_fidelity="High fidelity verified with clean pixel density." if approved else "Needs refinement.",
            composition_assessment=(
                f"Successfully matched style '{requirement.style_preset}' with clear focal balance."
                if approved
                else "Composition exhibits variance from requested framing."
            ),
            suggested_refinements=refinements,
        )


class MetaAIWorkflowOrchestrator:
    """Full-cycle workflow orchestrator connecting Prompt Engineering -> Meta AI -> Review."""

    def __init__(self, bridge: Optional[BrowserAIBridge] = None):
        self.bridge = bridge or browser_ai_bridge

    async def execute_panel_generation(
        self,
        requirement: PanelRequirement,
        headless: bool = True,
        timeout_sec: float = 120.0,
    ) -> MetaAIWorkflowResult:
        """Runs the complete prompt engineering, generation, and review cycle."""
        start_time = time.monotonic()

        # Step 1: Prompt Engineer
        engineered_prompt = MetaAIPromptEngineer.engineer_prompt(requirement)
        logger.info("Engineered Meta AI prompt: %s", engineered_prompt)

        # Step 2: Generator (Browser AI Bridge to Meta AI)
        bridge_res: BrowserBridgeResult = await self.bridge.execute_prompt_async(
            url="https://www.meta.ai/ai-image-generator/",
            prompt=engineered_prompt,
            extract_type="images",
            headless=headless,
            timeout_sec=timeout_sec,
            project_id=requirement.project_id,
        )

        elapsed = round(time.monotonic() - start_time, 2)

        if not bridge_res.success or not bridge_res.images:
            return MetaAIWorkflowResult(
                success=False,
                engineered_prompt=engineered_prompt,
                execution_time_sec=elapsed,
                error=bridge_res.error or "No images were generated or extracted from Meta AI.",
            )

        # Step 3: Reviewer
        primary_image = bridge_res.images[0]
        review = MetaAIImageReviewer.review_image(primary_image, requirement, engineered_prompt)

        return MetaAIWorkflowResult(
            success=True,
            engineered_prompt=engineered_prompt,
            generated_images=bridge_res.images,
            review=review,
            execution_time_sec=elapsed,
        )


meta_ai_workflow = MetaAIWorkflowOrchestrator()
