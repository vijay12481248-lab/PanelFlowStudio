"""Image Auto-Correction Bridge and Revalidation Engine."""
from __future__ import annotations

import io
import logging
import random
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Tuple, Union
from PIL import Image

from engine.comfyui.art import (
    ART_WORKFLOW_ID,
    ArtEngine,
    ComfyImageGenerationError,
    _patch_workflow,
)
from engine.inspector.image_inspector import ImageInspector
from engine.inspector.mask_gen import DefectMaskGenerator
from engine.inspector.schema import DefectRecord, QualityDecision

logger = logging.getLogger("panelflow.inspector.repair")
INPAINT_WORKFLOW_ID = "anime_sdxl_inpaint"
SEED_STEP = 7919


@dataclass
class RepairResult:
    """Artifacts, file paths, and revalidation outcome for an auto-correction pass."""
    repaired_png: bytes
    revalidated_decision: QualityDecision
    attempts: int
    actions_taken: List[str]
    success: bool
    repaired_image_path: Optional[Path] = None
    original_image_path: Optional[Path] = None
    mask_png: Optional[bytes] = None
    strategy_used: str = "none"
    original_score: float = 0.0
    final_score: float = 0.0
    score_improvement: float = 0.0
    seconds: float = 0.0

    @property
    def decision(self) -> QualityDecision:
        """Alias for backward compatibility."""
        return self.revalidated_decision

    @property
    def resolved(self) -> bool:
        """Alias for backward compatibility."""
        return self.success


class ImageRepairEngine:
    """
    Automated visual repair engine.
    1. Localized inpainting: Synthesizes feathered masks and runs SDXL inpainting for localized defects.
    2. Global redraw fallback: Steps seed with active anatomy lessons when structural defects are present.
    3. Revalidation: Automatically re-inspects repaired candidates to confirm defect eradication.
    4. Non-destructive: Never overwrites original files; writes to versioned outputs.
    """

    def __init__(
        self,
        art_engine: Optional[ArtEngine] = None,
        inspector: Optional[ImageInspector] = None,
        mask_generator: Optional[DefectMaskGenerator] = None,
    ):
        self.art_engine = art_engine
        self.inspector = inspector or ImageInspector()
        self.mask_generator = mask_generator or DefectMaskGenerator()

    def _refine_inpaint_prompt(self, prompt: str, defects: List[DefectRecord]) -> str:
        """
        Injects context-aware positive anatomical reinforcement based on detected defects.
        SDXL inpainting performs significantly better with explicit positive descriptors.
        """
        base = prompt.strip() if prompt.strip() else "anatomically correct subject, clean render"
        additions: List[str] = []
        cats = {d.category for d in defects}

        if "extra_hands" in cats or any("hand" in (d.evidence or "").lower() for d in defects):
            additions.append("anatomically correct hands, detailed 5-fingered hands, natural finger pose")
        if "extra_limbs" in cats or any("limb" in (d.evidence or "").lower() or "arm" in (d.evidence or "").lower() or "leg" in (d.evidence or "").lower() for d in defects):
            additions.append("realistic anatomically correct limbs and joints, clean body structure")
        if "distorted_face" in cats or "extra_head" in cats or any("face" in (d.evidence or "").lower() for d in defects):
            additions.append("symmetrical detailed face, expressive eyes, masterwork portrait")
        if "stray_text" in cats or any("text" in (d.evidence or "").lower() for d in defects):
            additions.append("clean seamless background, no text")

        if additions:
            return f"{base}, {', '.join(additions)}"
        return base

    def repair_image(
        self,
        image_data: Union[bytes, str, Path],
        decision: Optional[QualityDecision] = None,
        prompt: str = "",
        negative_prompt: str = "distorted, deformed, extra limbs, bad anatomy, low quality, stray text",
        output_dir: Optional[Union[str, Path]] = None,
        seed: Optional[int] = None,
        max_attempts: int = 2,
        progress: Optional[Callable[[float, str], None]] = None,
    ) -> RepairResult:
        """
        Executes localized inpaint or seed-stepped redraw and revalidates output.
        """
        t0 = time.monotonic()
        orig_path: Optional[Path] = None

        if isinstance(image_data, (str, Path)):
            orig_path = Path(image_data).resolve()
            if not orig_path.is_file():
                raise FileNotFoundError(f"Source image file not found: {orig_path}")
            image_bytes = orig_path.read_bytes()
        else:
            image_bytes = image_data

        if seed is None:
            seed = random.randint(1, 2**31 - 1)

        with Image.open(io.BytesIO(image_bytes)) as pil_img:
            width, height = pil_img.size

        # If decision not provided, inspect source image first
        if decision is None:
            decision = self.inspector.inspect(image_bytes, prompt)

        original_score = decision.overall_score
        actions_taken: List[str] = []

        if decision.clean or not decision.defects:
            logger.info("Image is clean; no repairs required.")
            return RepairResult(
                repaired_png=image_bytes,
                revalidated_decision=decision,
                attempts=0,
                actions_taken=["none_clean"],
                success=True,
                repaired_image_path=orig_path,
                original_image_path=orig_path,
                strategy_used="none",
                original_score=original_score,
                final_score=original_score,
                score_improvement=0.0,
                seconds=round(time.monotonic() - t0, 2),
            )

        # Inpaintable defects: direct bbox or known tile quadrant fallback
        inpaintable_defects = [
            d for d in decision.defects
            if d.recommended_action == "inpaint"
            and (d.bbox is not None or (d.tile and d.tile in self.mask_generator.TILE_BBOXES))
        ]

        repaired_png = image_bytes
        reval_decision = decision
        strategy_used = "none"
        attempts_executed = 0
        mask_png: Optional[bytes] = None

        # Strategy 1: Localized Inpainting (if defects are localized and ArtEngine is available)
        if inpaintable_defects and self.art_engine is not None:
            if progress:
                progress(0.2, "Synthesizing feathered inpainting mask")
            mask_png, coverage = self.mask_generator.generate_mask_png_with_coverage(
                width, height, inpaintable_defects
            )

            # Mask coverage overflow guard: if > 45% of canvas is masked, escalate directly to redraw
            if coverage > 0.45:
                logger.warning(
                    "Inpaint mask coverage (%.1f%%) exceeds 45%% canvas threshold. Escaping directly to global redraw.",
                    coverage * 100.0,
                )
                actions_taken.append(f"inpaint_skipped_mask_overflow_{coverage:.2f}")
            else:
                refined_prompt = self._refine_inpaint_prompt(prompt, inpaintable_defects)
                denoise_schedule = [0.65, 0.78]

                for attempt in range(max_attempts):
                    attempts_executed += 1
                    strategy_used = "inpaint"
                    denoise = denoise_schedule[min(attempt, len(denoise_schedule) - 1)]
                    action_name = (
                        f"inpaint_pass_{attempt + 1}_{len(inpaintable_defects)}_defects_denoise_{denoise:.2f}"
                    )
                    actions_taken.append(action_name)

                    if progress:
                        progress(0.3 + 0.2 * attempt, f"Executing inpaint pass {attempt + 1} (denoise={denoise:.2f})")
                    try:
                        candidate_png = self._run_inpaint_pass(
                            source_image_bytes=image_bytes,
                            mask_png_bytes=mask_png,
                            prompt=refined_prompt,
                            negative_prompt=negative_prompt,
                            seed=seed + attempt * 101,
                            denoise=denoise,
                        )

                        # Revalidation pass
                        if progress:
                            progress(0.7, f"Revalidating repaired candidate {attempt + 1}")
                        candidate_decision = self.inspector.inspect(candidate_png, prompt)

                        if candidate_decision.status == "PASS" or candidate_decision.overall_score > original_score:
                            repaired_png = candidate_png
                            reval_decision = candidate_decision
                            break
                    except Exception as exc:
                        logger.warning("Inpaint pass failed: %s", exc)

        # Strategy 2: Global Seed-Stepped Redraw Fallback
        if (reval_decision.status != "PASS" and reval_decision.overall_score <= original_score) and self.art_engine is not None:
            if progress:
                progress(0.5, "Falling back to seed-stepped generation with prompt rules")

            for attempt in range(max_attempts):
                attempts_executed += 1
                strategy_used = "redraw"
                actions_taken.append(f"redraw_fallback_pass_{attempt + 1}")

                step_seed = seed + (attempt + 1) * SEED_STEP
                lesson_prompt = f"{prompt} Remember: Exactly two arms, two hands, and clean anatomical proportions."
                try:
                    art = self.art_engine.generate(
                        prompt=lesson_prompt,
                        negative_prompt=negative_prompt,
                        width=width,
                        height=height,
                        seed=step_seed,
                        workflow_id=ART_WORKFLOW_ID,
                    )
                    candidate_decision = self.inspector.inspect(art.png, prompt)
                    if candidate_decision.status == "PASS" or candidate_decision.overall_score > original_score:
                        repaired_png = art.png
                        reval_decision = candidate_decision
                        break
                except Exception as exc:
                    logger.warning("Redraw attempt failed: %s", exc)

        # File persistence (non-destructive)
        saved_file_path: Optional[Path] = None
        if orig_path is not None or output_dir is not None:
            dest_dir = Path(output_dir).resolve() if output_dir else (orig_path.parent / "repaired" if orig_path else Path("output/repaired"))
            dest_dir.mkdir(parents=True, exist_ok=True)
            stem = orig_path.stem if orig_path else "image"
            saved_file_path = dest_dir / f"{stem}_repaired_{uuid.uuid4().hex[:6]}.png"
            saved_file_path.write_bytes(repaired_png)
            logger.info("Saved repaired image to: %s", saved_file_path)

        score_improvement = round(reval_decision.overall_score - original_score, 1)
        success = (reval_decision.status == "PASS") or (score_improvement > 0.0)

        return RepairResult(
            repaired_png=repaired_png,
            revalidated_decision=reval_decision,
            attempts=attempts_executed,
            actions_taken=actions_taken,
            success=success,
            repaired_image_path=saved_file_path,
            original_image_path=orig_path,
            mask_png=mask_png,
            strategy_used=strategy_used,
            original_score=original_score,
            final_score=reval_decision.overall_score,
            score_improvement=score_improvement,
            seconds=round(time.monotonic() - t0, 2),
        )

    def _run_inpaint_pass(
        self,
        source_image_bytes: bytes,
        mask_png_bytes: bytes,
        prompt: str,
        negative_prompt: str,
        seed: int,
        denoise: float = 0.68,
    ) -> bytes:
        """Patches and dispatches the anime_sdxl_inpaint ComfyUI workflow."""
        if self.art_engine is None:
            raise RuntimeError("ArtEngine is not configured.")

        # Upload source and mask images to ComfyUI input folder
        ref_image_name = self.art_engine.client.upload_image_bytes(source_image_bytes)
        mask_image_name = self.art_engine.client.upload_image_bytes(mask_png_bytes)

        workflow, _ = self.art_engine.registry.load(INPAINT_WORKFLOW_ID)
        metadata = self.art_engine.registry.metadata(INPAINT_WORKFLOW_ID)

        patched = _patch_workflow(
            workflow=workflow,
            patch_slots=metadata["patch_slots"],
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=1024,
            height=1024,
            seed=seed,
            prefix="panelflow_repaired",
            reference_image=ref_image_name,
            mask_image=mask_image_name,
            denoise=denoise,
        )

        repaired_bytes, _, _ = self.art_engine.run(patched, timeout=120.0)
        return repaired_bytes
