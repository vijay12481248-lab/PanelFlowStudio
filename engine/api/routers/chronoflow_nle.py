"""ChronoFlow's Magic Brush and range editing (the "NLE" routes), served by the engine.

These lived only in the old standalone ChronoFlow server (port 7860). They are here now so ChronoFlow is one thing: the engine on
port 8765 serves the studio UI, this API and everything else.

- `upload_ref`  : keep a reference picture in ComfyUI's input folder (data URL, or a file already in the media folders)
- `frame/generate` : draw a new picture for the paused frame with the one PanelFlow art workflow (Qwen Image 2.1)
- `range/auto_prompt`, `range/generate`, `range/apply` : look at a stretch of the timeline, write a Fast H3 prompt, render a
  replacement clip from the frame at its start, and splice it into the master video.

Changes from the standalone version, all deliberate: file names from the client are reduced to a bare name (they were joined to
the input folder as they came); `upload_ref` no longer copies arbitrary paths or downloads URLs; `frame/generate` calls the real
`ArtEngine.generate` (the old code called a method that does not exist, so it always failed); a range with no anchor frame is
refused instead of silently using a sample picture; the unused `frame/inpaint` and `frame/apply` routes were not carried over
(the UI inpaints through `/api/chronoflow/inpaint_image`).
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import io
import logging
import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from PIL import Image
from pydantic import BaseModel, Field

from engine.api.routers import chronoflow as cf
from engine.chronoflow import media_tools
from engine.chronoflow.pipeline import COMFY_INPUT_DIR, STUDIO_OUTPUT_DIR

logger = logging.getLogger("panelflow.chronoflow.nle")

router = APIRouter(prefix="/api/chronoflow/nle", tags=["chronoflow"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
FRAME_SIZE = (1024, 576)
LORA_NAME = "minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors"


# ---------- small helpers (pure, tested) ----------
def safe_name(name: str | None, *, default_ext: str = ".png", allowed: tuple[str, ...] = IMAGE_EXTENSIONS) -> str:
    """A bare file name with an allowed extension: no folders, no `..`, a random name when there is none."""
    base = Path(str(name or "")).name.strip()
    if not base or base.startswith("."):
        base = f"ref_{uuid.uuid4().hex[:8]}{default_ext}"
    if not base.lower().endswith(allowed):
        base += default_ext
    return base


def decode_data_url(data: str, *, limit: int = MAX_UPLOAD_BYTES) -> bytes:
    """The bytes of a `data:image/...;base64,` URL (or bare base64). Raises ValueError if it is not a usable picture."""
    payload = data.split(",", 1)[1] if data.startswith("data:") and "," in data else data
    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("the picture is not valid base64") from exc
    if len(raw) > limit:
        raise ValueError(f"the picture is larger than {limit // (1024 * 1024)} MB")
    try:
        with Image.open(io.BytesIO(raw)) as picture:
            picture.verify()
    except Exception as exc:
        raise ValueError("the data is not a readable picture") from exc
    return raw


def strip_code_fence(text: str) -> str:
    """Remove a ``` fence the model may have wrapped its answer in."""
    clean = (text or "").strip()
    if clean.startswith("```"):
        lines = clean.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        clean = "\n".join(lines).strip()
    return clean


def frame_length_for(duration: float) -> int:
    """Fast H3 frame counts that match the clip lengths it was tuned for."""
    if duration <= 1.5:
        return 22
    if duration <= 2.5:
        return 56
    if duration <= 3.5:
        return 73
    return 124


def latest_master(job_id: str | None) -> Path | None:
    """The master video of a job, else the newest master in the studio output folder."""
    if job_id:
        candidate = STUDIO_OUTPUT_DIR / f"chronoflow_master_{Path(job_id).name}.mp4"
        if candidate.exists():
            return candidate
    masters = sorted(STUDIO_OUTPUT_DIR.glob("chronoflow_master_*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    return masters[0] if masters else None


def render_size(job: dict[str, Any], job_id: str | None) -> tuple[int, int]:
    """The size to render a replacement clip at: the job's own, else the master video it will be spliced into, else 1344 x 768.

    A clip of another shape cannot be joined to the master (ffmpeg's concat needs equal sizes), so matching the master matters.
    """
    if job.get("width") and job.get("height"):
        return int(job["width"]), int(job["height"])
    base = latest_master(job_id)
    if base:
        try:
            info = media_tools.probe(base)
            if info.get("width") and info.get("height"):
                return int(info["width"]), int(info["height"])
        except Exception as exc:
            logger.warning("Could not read the master video size: %s", exc)
    return 1344, 768


def _job(job_id: str | None) -> dict[str, Any]:
    return (cf.supervisor.get_job(job_id) if job_id else None) or {}


def _anchor(job_id: str | None, t: float, ref_image: str | None, job: dict[str, Any]) -> tuple[Path | None, str | None]:
    """The frame a range starts from: the picture the user chose, else the master video at `t`, else the job's first picture."""
    if ref_image:
        candidate = COMFY_INPUT_DIR / Path(ref_image).name
        if candidate.exists():
            return candidate, candidate.name
    base = latest_master(job_id)
    if base and base.exists():
        name = f"range_anchor_{uuid.uuid4().hex[:8]}.png"
        try:
            media_tools.extract_frame(base, t, COMFY_INPUT_DIR / name)
            return COMFY_INPUT_DIR / name, name
        except Exception as exc:
            logger.warning("Could not take a frame at %.1fs: %s", t, exc)
    initial = job.get("initial_image")
    if initial and (COMFY_INPUT_DIR / Path(initial).name).exists():
        return COMFY_INPUT_DIR / Path(initial).name, Path(initial).name
    return None, None


# ---------- requests ----------
class UploadRefRequest(BaseModel):
    image: str = Field(..., min_length=1, description="A data URL, or the name of a file already in the media folders")
    filename: str | None = None


class FrameGenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=8000)
    reference_image: str | None = None
    time: float = 0.0
    job_id: str | None = None


class RangeRequest(BaseModel):
    job_id: str | None = None
    t_start: float = 0.0
    t_end: float | None = None
    prompt: str = ""
    adjustments: str = ""
    current_prompt: str = ""
    reference_image: str | None = None

    def end(self) -> float:
        return self.t_end if self.t_end is not None else self.t_start + 2.5


class RangeApplyRequest(BaseModel):
    job_id: str | None = None
    clip_filename: str = Field(..., min_length=1)
    t_start: float = 0.0
    t_end: float = 0.0


# ---------- routes ----------
@router.post("/upload_ref")
async def upload_ref(req: UploadRefRequest) -> dict[str, Any]:
    """Keep a reference picture in ComfyUI's input folder so a clip or frame can be conditioned on it."""
    name = safe_name(req.filename)
    target = COMFY_INPUT_DIR / name
    COMFY_INPUT_DIR.mkdir(parents=True, exist_ok=True)
    if req.image.startswith("data:"):
        try:
            target.write_bytes(decode_data_url(req.image))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        source = media_tools.resolve_media(Path(req.image).name)
        if not source or not source.exists() or source.suffix.lower() not in IMAGE_EXTENSIONS:
            raise HTTPException(status_code=400, detail="No valid picture: send a data URL or the name of a picture already in the media folders")
        shutil.copy2(source, target)
    return {"success": True, "filename": name, "url": f"/inputs/{name}", "path": str(target)}


@router.post("/frame/generate")
async def frame_generate(req: FrameGenerateRequest) -> dict[str, Any]:
    """Draw a new picture for the paused frame with the one PanelFlow art workflow (Qwen Image 2.1)."""
    from engine.comfyui.art import ArtEngine, ComfyImageGenerationError

    references: list[bytes] = []
    if req.reference_image:
        ref = COMFY_INPUT_DIR / Path(req.reference_image).name
        if ref.exists():
            references.append(ref.read_bytes())
    width, height = FRAME_SIZE

    def run():
        return ArtEngine().generate(req.prompt, width=width, height=height, prefix="chronoflow_frame",
                                    reference_images=references or None, timeout=900.0)

    try:
        art = await asyncio.to_thread(run)
    except (ComfyImageGenerationError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    name = f"nle_frame_{uuid.uuid4().hex[:8]}.png"
    COMFY_INPUT_DIR.mkdir(parents=True, exist_ok=True)
    (COMFY_INPUT_DIR / name).write_bytes(art.png)
    return {"success": True, "id": name, "image_url": f"/inputs/{name}", "time": req.time}


_AUTO_PROMPT_SYSTEM = (
    "You are an elite cinematic film director and AI video prompt engineer for ChronoFlow Studio and MiniMax H3 / Qwen Image 2.1.\n"
    "You are analyzing timeline video range [{t0:.1f}s -> {t1:.1f}s] ({dur:.1f}s duration).\n\n"
    "TASK: Inspect the anchor frame at this exact timestamp, diagnose what is missing or flawed in the current action, "
    "and compose a refined, production-grade Fast H3 prompt executing the director's requested adjustments.\n\n"
    "CONTINUITY & KINEMATIC RULES:\n"
    "1. CHARACTER & VISUAL RETENTION: Strictly preserve the character's face, hair, costume, and the scene environment from the anchor frame.\n"
    "2. CHRONOLOGICAL SEQUENCING: Execute steps in exact logical temporal sequence (e.g. turning on the light FIRST to illuminate the scene, then reaching out and picking up the cup).\n"
    "3. NO ACTION REVERSAL OR TELEPORTATION: Natural physical movement progressing organically from the starting anchor posture.\n"
    "4. CAMERA KINEMATICS: Explicit camera movement (e.g., slow low-angle tracking, smooth subtle push-in, lens depth).\n"
    "5. OUTPUT SCHEMA: You MUST format your output conforming to the 6 headings:\n"
    "summary:\n[1-sentence concise shot logline]\n\n"
    "retention_analysis:\n[Preserved character identity, attire, lighting, setting]\n\n"
    "detailed_description:\n[Cinematic 35mm film shot. Precise camera kinematics, sequential character actions, physical contact with objects, "
    "secondary environmental dynamics, lighting transition]\n\n"
    "overall_soundscape:\n[Diegetic foley sound: click of switch, hum of light, ceramic clink]\n\n"
    "non_diegetic_music:\n[Cinematic score mood and instrumentation]"
)


async def _write_prompt(system: str, user: str, anchor: Path | None) -> str:
    """Ask the local vision model (or the text model when there is no anchor frame) to write the prompt."""
    from engine.llm.providers.ollama import OllamaProvider

    provider = OllamaProvider(vision_model="qwen3.5:9b")
    if anchor and anchor.exists():
        text = await provider.analyze_vision(image=anchor, prompt=user, system_prompt=system)
    else:
        text = await provider.generate_text(prompt=user, system_prompt=system)
    return strip_code_fence(text)


@router.post("/range/auto_prompt")
async def range_auto_prompt(req: RangeRequest) -> dict[str, Any]:
    """Look at the frame where a range starts and write a production-grade Fast H3 prompt for the director's adjustments."""
    t0, t1 = req.t_start, req.end()
    duration = max(0.5, t1 - t0)
    job = _job(req.job_id)
    anchor, anchor_name = _anchor(req.job_id, t0, req.reference_image, job)
    adjustments = (req.adjustments or req.prompt).strip()
    chunk_prompts = job.get("chunk_prompts", []) or []
    prior = "\n".join(f"Shot #{i + 1}: {p[:120]}..." for i, p in enumerate(chunk_prompts) if p)
    user = (
        f"Overall Story Context: {job.get('prompt', 'Cinematic photorealistic action shot')}\n"
        f"Timeline Interval: [{t0:.1f}s -> {t1:.1f}s] ({duration:.1f}s)\n"
        + (f"Prior Context:\n{prior}\n" if prior else "")
        + (f"Current Baseline Prompt:\n{req.current_prompt.strip()}\n" if req.current_prompt.strip() else "")
        + f"DIRECTOR'S ADJUSTMENTS & ISSUES TO FIX:\n{adjustments}\n\n"
        "Analyze the anchor frame, identify the delta, and generate the complete 6-heading prompt implementing these adjustments."
    )
    try:
        prompt = await _write_prompt(_AUTO_PROMPT_SYSTEM.format(t0=t0, t1=t1, dur=duration), user, anchor)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"The local model could not write the prompt: {exc}") from exc
    summary = next((ln.strip() for ln in prompt.split("\n") if ln.strip() and not ln.lower().startswith("summary:") and not ln.strip().endswith(":")), "")
    return {
        "success": True, "prompt": prompt, "summary": summary or "Prompt refined from range analysis.", "anchor_image": anchor_name,
        "anchor_url": f"/inputs/{anchor_name}" if anchor_name else None, "t_start": t0, "t_end": t1, "duration": duration,
    }


@router.post("/range/generate")
async def range_generate(req: RangeRequest) -> dict[str, Any]:
    """Render a replacement clip for [t_start, t_end] with Fast H3, starting from the frame at t_start."""
    t0, t1 = req.t_start, req.end()
    duration = max(0.5, t1 - t0)
    job = _job(req.job_id)
    anchor, anchor_name = _anchor(req.job_id, t0, req.reference_image, job)
    if not anchor_name:
        raise HTTPException(status_code=400, detail="There is no frame to start from: pick a reference picture, or open a job that has a master video")
    prompt = req.prompt.strip()
    if prompt and "detailed_description:" not in prompt.lower():
        # a short adjustment note: turn it into the full 6-heading prompt first (the director step), keeping the note if the model is away
        try:
            system = _AUTO_PROMPT_SYSTEM.format(t0=t0, t1=t1, dur=duration)
            user = f"Director Adjustments / Scene Issues: {prompt}\nTimeline Range: [{t0:.1f}s -> {t1:.1f}s] ({duration:.1f}s)\nStory Context: {job.get('prompt', 'Cinematic shot')}"
            refined = await _write_prompt(system, user, anchor)
            if len(refined) > 30:
                prompt = refined
        except Exception as exc:
            logger.info("Range prompt refinement skipped: %s", exc)
    if not prompt:
        raise HTTPException(status_code=400, detail="A prompt is required")
    width, height = render_size(job, req.job_id)
    graph = cf.pipeline.build_h3_prompt(
        prompt=prompt, width=width, height=height, length=frame_length_for(duration), steps=4,
        lora_name=LORA_NAME, workflow_mode="sliding_window", first_frame_filename=anchor_name,
    )
    try:
        chunk_output = await cf.pipeline.execute_prompt(graph)
    except Exception as exc:
        logger.exception("Range generation failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    name = f"range_chunk_{uuid.uuid4().hex[:8]}.mp4"
    shutil.copy2(chunk_output, STUDIO_OUTPUT_DIR / name)
    return {"success": True, "clip_url": f"/outputs/{name}", "clip_filename": name, "t_start": t0, "t_end": t1, "duration": duration,
            "anchor_image": anchor_name, "prompt": prompt}


@router.post("/range/apply")
async def range_apply(req: RangeApplyRequest) -> dict[str, Any]:
    """Splice a generated clip into the master video over [t_start, t_end]."""
    base = latest_master(req.job_id)
    if not base or not base.exists():
        raise HTTPException(status_code=404, detail="No base master video found to splice into")
    clip = media_tools.resolve_media(Path(req.clip_filename).name)
    if not clip or not clip.exists():
        clip = STUDIO_OUTPUT_DIR / Path(req.clip_filename).name
    if not clip.exists():
        raise HTTPException(status_code=404, detail=f"Replacement clip not found: {req.clip_filename}")
    out_name = f"chronoflow_spliced_{uuid.uuid4().hex[:8]}.mp4"
    out_path = STUDIO_OUTPUT_DIR / out_name
    try:
        await asyncio.to_thread(media_tools.splice_timeline_range, base, clip, req.t_start, req.t_end, out_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if req.job_id and out_path.exists():
        master = STUDIO_OUTPUT_DIR / f"chronoflow_master_{Path(req.job_id).name}.mp4"
        try:
            shutil.copy2(out_path, master)
            cf.supervisor.update_job(req.job_id, master_video=f"/outputs/{master.name}")
        except OSError as exc:
            logger.warning("Could not copy the spliced video over the master: %s", exc)
    return {"success": True, "spliced_url": f"/outputs/{out_name}", "spliced_filename": out_name, "t_start": req.t_start, "t_end": req.t_end}
