"""Optional chapter music and sparse semantic SFX; speech never depends on them."""
import hashlib
import json
import re
from pathlib import Path


def plan_chapter_audio(workspace, settings, segments, timeline):
    workspace = Path(workspace)
    directory = workspace / "audio"
    directory.mkdir(parents=True, exist_ok=True)
    arc = list(dict.fromkeys(s.music_intent for s in segments if s.music_intent and s.music_intent != "NONE"))
    warnings = []
    selected = settings.get("chapter_music_path")
    music_path = str(Path(selected).resolve()) if selected and Path(selected).is_file() else None
    if selected and music_path is None:
        warnings.append("Selected music file is missing; narration-only export is available.")
    if not music_path and settings.get("auto_music"):
        try:
            from engine.audio.synthesis import local_adapter
            # Initialize the installed adapter import path and offline policy.
            local_adapter(settings.get("tts_provider", "chatterbox_turbo"))
            from lumina_audio_director.adapters.ace_step_adapter import ACEStepAdapter
            from lumina_audio_director.core.brief import AudioBrief, AudioType, MusicalParameters
            summary = " ".join(s.text for s in segments)[:3000]
            key = hashlib.sha256(json.dumps([summary, arc, timeline["total_duration_sec"]]).encode()).hexdigest()[:20]
            target = directory / f"chapter_music_{key}.wav"
            if not target.exists():
                brief = AudioBrief(
                    scene=summary, location="Source manga chapter", story_position="complete chapter",
                    audio_type=AudioType.MUSIC, purpose="narration underscore", emotion_primary=" → ".join(arc) or "calm",
                    emotion_secondary="restrained", intensity=0.35,
                    world_identity="User-supplied manga chapter", character_focus="chapter ensemble",
                    narrative_function="Quiet instrumental supporting the original narrator",
                    duration_seconds=min(180, timeline["total_duration_sec"]), loop_required=True,
                    musical_params=MusicalParameters(leitmotif_references=[]),
                )
                result = ACEStepAdapter().generate(brief, output_path=target)
                if not result.success:
                    raise ValueError(result.error_message)
            music_path = str(target)
        except Exception as exc:
            warnings.append(f"Optional music generation failed: {exc}. Narration-only export is available.")

    sfx = []
    if settings.get("auto_sfx"):
        library = Path(settings.get("sfx_library_path") or workspace / "audio" / "sfx")
        intervals = {iv["script_segment_id"]: iv for iv in timeline["intervals"]}
        last_cue = -10.0
        for segment in segments:
            cue = re.sub(r"[^a-z0-9]+", "_", (segment.sfx_intent or "NONE").lower()).strip("_")
            interval = intervals.get(segment.id)
            if cue in ("none", "", "silence") or interval is None:
                continue
            start = interval["start_time"] + (interval["end_time"] - interval["start_time"]) * 0.35
            if start - last_cue < 4.0:
                continue
            candidates = [library / f"{cue}{extension}" for extension in (".wav", ".flac", ".ogg")]
            asset = next((p for p in candidates if p.is_file()), None)
            if asset:
                sfx.append({"scene_id": segment.scene_id, "type": cue, "time": round(start, 3),
                            "path": str(asset.resolve()), "gain_db": -12.0})
                last_cue = start
            else:
                warnings.append(f"No local SFX asset for {cue}; cue omitted.")
    plan = {"music": {"path": music_path, "emotional_arc": arc, "gain_db": -16.0}, "sfx": sfx, "warnings": warnings}
    (directory / "chapter_audio_plan.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    return plan
