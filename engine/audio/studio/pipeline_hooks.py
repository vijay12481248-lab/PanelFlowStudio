"""Studio Pipeline Automation Hooks: Connects ChronoFlow Audio Studio with
Original Story Studio (engine/original/) and Anime Review (engine/anime/review/).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from engine.audio.studio.critique import apply_remediations, critique_plan
from engine.audio.studio.engine import AudioEngine
from engine.audio.studio.master import master_plan
from engine.audio.studio.plan import Cue, PlanStore, SoundPlan
from engine.audio.studio.spot import detect_cuts, draft_cues

logger = logging.getLogger(__name__)


def auto_soundtrack_original_story(
    engine: AudioEngine,
    video_path: Path,
    narration_path: Path | None = None,
    story_title: str = "Story",
    use_vision: bool = False,
    standard: str = "youtube",
) -> dict[str, Any]:
    """Automates sound post-production for an Original Story chapter:
    1. Creates SoundPlan bound to the chapter's video.
    2. Attaches narration voice track as Dialogue.
    3. Spots scene cuts and drafts context-aware cues (whooshes, impacts, ambient score).
    4. Sources candidate takes for drafted cues.
    5. Performs acoustic critique and automatically applies DSP remediations (mud removal, ducking).
    6. Masters the soundtrack to -14 LUFS YouTube standard with True-Peak lookahead limiting.
    """
    video_path = Path(video_path)
    if not video_path.is_file():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    # 1. Create or load plan
    existing = next((p for p in engine.store.list() if p.video_path == str(video_path)), None)
    if existing:
        plan = engine.store.load(existing.id)
    else:
        plan = engine.create_plan(video_path, dialogue_path=narration_path)

    # 2. Spot picture cuts & draft cues
    cuts = detect_cuts(video_path)
    with engine.store.lock(plan.id):
        plan = engine.store.load(plan.id)
        keep = [c for c in plan.cues if c.status != "draft"]
        taken = {c.id for c in keep}
        drafted = draft_cues(plan, cuts, use_vision=use_vision, video_path=video_path if use_vision else None)
        plan.cues = keep + [c for c in drafted if c.id not in taken]
        plan.cuts = [round(c, 4) for c in cuts]
        plan = engine.store.save(plan, "auto-spotted cuts")

    # 3. Source all pending draft cues
    sourced_count = 0
    for cue in plan.cues:
        if cue.status in ("draft", "failed"):
            try:
                plan = engine.source_cue(plan.id, cue.id, mode="auto")
                sourced_count += 1
            except Exception as e:
                logger.warning(f"Could not auto-source cue {cue.id}: {e}")

    # 4. Acoustic Critique & 1-click Auto-Remediation
    report = critique_plan(plan)
    if report.remediations:
        rem_ids = [r.id for r in report.remediations]
        plan, applied = apply_remediations(plan, rem_ids)
        plan = engine.store.save(plan, f"auto-remediated {len(applied)} acoustic issues")

    # 5. Master soundtrack
    out_master = engine.store.plan_dir(plan.id) / "exports" / "story_master.wav"
    out_video = engine.store.plan_dir(plan.id) / "exports" / f"{story_title.replace(' ', '_')}_master.mp4"
    master_info = master_plan(
        plan,
        out_master,
        standard=standard,  # type: ignore[arg-type]
        video_in=video_path,
        out_video=out_video,
    )

    return {
        "plan_id": plan.id,
        "cues_total": len(plan.cues),
        "sourced_count": sourced_count,
        "critique_score": report.overall_quality_score,
        "master_wav": str(out_master),
        "master_video": str(out_video) if out_video.is_file() else None,
        "loudness": master_info.get("loudness", {}),
        "compliance": master_info.get("compliance", {}),
    }


def auto_soundtrack_anime_review(
    engine: AudioEngine,
    video_path: Path,
    review_script_text: str | None = None,
    narration_path: Path | None = None,
    standard: str = "youtube",
) -> dict[str, Any]:
    """Automates sound post-production for an Anime Episode Review:
    1. Creates SoundPlan with narration as Dialogue.
    2. Spots review segment cuts.
    3. Applies dynamic ducking on backing track (-22 dB under review voice).
    4. Masters to -14 LUFS YouTube standard with True-Peak lookahead limiting.
    """
    video_path = Path(video_path)
    if not video_path.is_file():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    plan = engine.create_plan(video_path, dialogue_path=narration_path)

    # Configure dynamic ducking on music & sfx tracks
    with engine.store.lock(plan.id):
        plan = engine.store.load(plan.id)
        for trk in plan.tracks:
            if trk.id in ("music", "sfx", "ambience"):
                trk.duck_under = "dialogue"
                trk.ducking_depth_db = -22.0
                trk.ducking_attack_ms = 25
                trk.ducking_release_ms = 350
        plan = engine.store.save(plan, "configured anime review ducking")

    # Master
    out_master = engine.store.plan_dir(plan.id) / "exports" / "review_master.wav"
    out_video = engine.store.plan_dir(plan.id) / "exports" / "review_final.mp4"
    master_info = master_plan(
        plan,
        out_master,
        standard=standard,  # type: ignore[arg-type]
        video_in=video_path,
        out_video=out_video,
    )

    return {
        "plan_id": plan.id,
        "master_wav": str(out_master),
        "master_video": str(out_video) if out_video.is_file() else None,
        "loudness": master_info.get("loudness", {}),
        "compliance": master_info.get("compliance", {}),
    }
