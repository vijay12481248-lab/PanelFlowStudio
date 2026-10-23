"""
Deterministic Timeline Compiler for PanelFlow Production Renderer.
Compiles Video-First Story Editor Schema v2 state directly into frame-accurate RenderPlan.
Preserves scene durations, independent layer timing, transforms, keyframes, motion presets,
camera movement, transitions, narration audio, background music, sound effects, and ducking.
"""
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import json
import math
import hashlib
import urllib.parse
from PIL import Image

from engine.render.models.render_plan import RenderPlan, RenderShotPlan, RenderAudioTrack
from engine.render.models.profiles import RenderProfile
from engine.render.models.enums import MusicDurationPolicy, ScalePolicy, BackgroundFillPolicy
from engine.motion.models.camera import CameraState, NormalizedRect
from engine.motion.models.enums import EasingFunction, MotionType
from engine.motion.models.transitions import TransitionInstruction
from engine.motion.models.cues import CaptionCue
from engine.render.clock import RenderFrameClock
from engine.render.models.background import BackgroundSettings


class TimelineCompiler:
    """
    Deterministic compiler converting StoryEditorState (Schema v2) into a validated RenderPlan.
    """

    def __init__(self):
        pass

    @staticmethod
    def _compile_background(scene, state, layers, workspace_path, project_id):
        raw = scene.get("background")
        if raw is None:
            raw = state.get("background_default")
        if raw is None:
            return None, None
        settings = BackgroundSettings.model_validate(raw)
        if not settings.enabled or settings.preset == "none":
            return settings, None
        if settings.source_mode == "pinned_layer":
            pinned = next((layer for layer in layers if layer["id"] == settings.source_layer_id), None)
            if not pinned or not pinned.get("disk_image_path"):
                raise ValueError("Background pinned layer is missing. Select an existing visual layer or follow the current visual.")
        custom_path = None
        if settings.preset == "custom_image" or settings.source_mode == "custom_image":
            raw_url = settings.custom_image_url or ""
            # Explicit backgrounds must never invoke the legacy page fallback resolver.
            for layer in layers:
                if raw_url and raw_url in (layer.get("image_url"), layer.get("disk_image_path")):
                    custom_path = layer.get("disk_image_path")
                    break
            parsed = urllib.parse.urlparse(raw_url)
            prefix = f"/api/projects/{urllib.parse.quote(str(project_id), safe='')}/backgrounds/"
            decoded = urllib.parse.unquote(parsed.path)
            if custom_path is None and decoded.startswith(prefix):
                filename = decoded[len(prefix):]
                if filename.endswith("/file"):
                    filename = filename[:-len("/file")]
                if filename and Path(filename).name == filename and "/" not in filename and "\\" not in filename:
                    root = (workspace_path / "backgrounds").resolve()
                    candidate = (root / filename).resolve()
                    if candidate.parent == root and candidate.is_file():
                        custom_path = str(candidate)
            if not custom_path or not Path(custom_path).is_file():
                raise ValueError("Background custom image is missing or unavailable. Upload it again or select a known visual layer.")
            try:
                with Image.open(custom_path) as image:
                    image.verify()
            except Exception as exc:
                raise ValueError("Background custom image could not be decoded. Upload a valid PNG, JPEG or WebP image.") from exc
        return settings, custom_path

    def _resolve_image_path(self, raw_url_or_id: str, panel_id: Optional[str], page_id: Optional[str], workspace_path: Path, strict: bool = False) -> Tuple[Optional[str], bool]:
        """
        Locates the physical image file on disk matching a panel or page reference.
        Returns (file_path, is_already_cropped).
        """
        # 1. Direct path check
        if raw_url_or_id:
            p = Path(raw_url_or_id)
            if p.exists() and p.is_file():
                is_crop = "panel" in p.name.lower() or "panels" in str(p).lower()
                return str(p.resolve()), is_crop

        # 2. Check panels.json in workspace/panels/
        panel_dir = workspace_path / "panels"
        if panel_dir.exists():
            panels_json_p = panel_dir / "panels.json"
            if panels_json_p.exists():
                try:
                    p_data = json.loads(panels_json_p.read_text(encoding="utf-8"))
                    for p_item in p_data.get("panels", []):
                        if (
                            p_item.get("id") == panel_id
                            or str(p_item.get("sequence")) == str(panel_id)
                            or f"panel_{p_item.get('sequence')}" == str(panel_id)
                            or (raw_url_or_id and p_item.get("id") in raw_url_or_id)
                        ):
                            crop_ref = p_item.get("crop_reference", "")
                            if crop_ref:
                                cand = workspace_path / crop_ref
                                if cand.exists():
                                    return str(cand.resolve()), True
                                cand2 = panel_dir / Path(crop_ref).name
                                if cand2.exists():
                                    return str(cand2.resolve()), True
                except Exception:
                    pass

            # Direct match by name or uuid in panels directory
            if panel_id:
                for ext in [".jpg", ".png", ".webp", ".jpeg"]:
                    candidate = panel_dir / f"{panel_id}{ext}"
                    if candidate.exists():
                        return str(candidate.resolve()), True
                    candidate = panel_dir / f"panel_{panel_id}{ext}"
                    if candidate.exists():
                        return str(candidate.resolve()), True
                for p in list(panel_dir.glob("*.jpg")) + list(panel_dir.glob("*.png")):
                    if panel_id in p.name:
                        return str(p.resolve()), True

        # 3. Check page images in workspace/pages/, workspace/source/, workspace/normalized/
        for sub in ["pages", "source", "normalized"]:
            dir_p = workspace_path / sub
            if dir_p.exists():
                if page_id:
                    for ext in [".jpg", ".png", ".webp", ".jpeg"]:
                        candidate = dir_p / f"{page_id}{ext}"
                        if candidate.exists():
                            return str(candidate.resolve()), False
                # Check for any page files
                page_files = sorted(list(dir_p.glob("*.jpg")) + list(dir_p.glob("*.png")))
                if page_files and not strict:
                    return str(page_files[0].resolve()), False

        # 4. Check workspace root
        if not strict:
            for p in workspace_path.glob("*.jpg"):
                return str(p.resolve()), False

        return None, False

    def _resolve_audio_path(self, raw_url: str, workspace_path: Path) -> Optional[str]:
        """
        Locates the physical audio file on disk matching an audio URL or reference.
        """
        if not raw_url:
            return None

        # 1. Check if raw_url is a backend streaming URL with ?path=...
        if "path=" in raw_url:
            parsed = urllib.parse.urlparse(raw_url)
            query = urllib.parse.parse_qs(parsed.query)
            if "path" in query and query["path"]:
                decoded_path = urllib.parse.unquote(query["path"][0])
                p = Path(decoded_path)
                if p.exists() and p.is_file():
                    return str(p.resolve())

        # 2. Direct absolute or relative path
        p = Path(raw_url)
        if p.exists() and p.is_file():
            return str(p.resolve())

        # 3. If path is relative to desktop public assets (e.g. /assets/demo/crystal_resonance_bgm.mp3)
        clean_rel = raw_url.lstrip("/\\")
        project_root = Path(__file__).resolve().parent.parent.parent
        desktop_asset = project_root / "apps" / "desktop" / "public" / clean_rel
        if desktop_asset.exists() and desktop_asset.is_file():
            return str(desktop_asset.resolve())

        # 4. Check workspace/audio/
        audio_dir = workspace_path / "audio"
        if audio_dir.exists():
            candidate = audio_dir / Path(clean_rel).name
            if candidate.exists() and candidate.is_file():
                return str(candidate.resolve())
            candidate_dialogue = audio_dir / "dialogue" / Path(clean_rel).name
            if candidate_dialogue.exists() and candidate_dialogue.is_file():
                return str(candidate_dialogue.resolve())
            candidate_music = audio_dir / "music" / Path(clean_rel).name
            if candidate_music.exists() and candidate_music.is_file():
                return str(candidate_music.resolve())
            for sub_p in audio_dir.rglob(Path(clean_rel).name):
                if sub_p.is_file():
                    return str(sub_p.resolve())

        return None

    @staticmethod
    def _resolve_scene_timing(scenes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Match editor intervals: explicit gaps survive; missing/stale starts follow the previous end."""
        result = []
        end = 0.0
        for scene in scenes:
            raw_start = scene.get("start_time_sec")
            start = max(end, float(raw_start)) if isinstance(raw_start, (int, float)) and math.isfinite(raw_start) else end
            duration = float(scene.get("duration_sec", 4.0))
            result.append({**scene, "start_time_sec": start, "duration_sec": duration})
            end = start + duration
        return result

    @staticmethod
    def _resolve_narration_timing(scenes: List[Dict[str, Any]], clips: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        starts = {scene.get("id"): scene["start_time_sec"] for scene in scenes}
        result = []
        for clip in clips:
            parent = clip.get("scene_id")
            offset = clip.get("scene_offset_sec")
            if clip.get("linked_to_scene") is not False and parent in starts and isinstance(offset, (int, float)) and math.isfinite(offset):
                clip = {**clip, "start_time_sec": round(starts[parent] + offset, 2)}
            result.append(clip)
        return result

    def preflight_validate(
        self,
        state: Dict[str, Any],
        project_id: str,
        workspace_path: Path,
    ) -> Dict[str, Any]:
        """
        Performs comprehensive pre-flight verification before rendering.
        Reports warnings (outdated audio, missing optional cues) and blockers (missing scenes, missing media).
        """
        issues: List[str] = []
        if state.get("panel_review_sync", {}).get("removed_layers_count", 0):
            issues.append("Source panels were deleted or replaced. Review the affected video layers before exporting.")
        warnings: List[str] = []
        scenes = self._resolve_scene_timing(state.get("scenes", []))
        if not scenes:
            issues.append("Project timeline has no scenes to render.")

        # 1. Validate scenes and layers
        total_layers = 0
        missing_images = 0
        for sc in scenes:
            layers = sc.get("layers", [])
            total_layers += len(layers)
            background_raw = sc.get("background") if sc.get("background") is not None else state.get("background_default")
            background_active = bool(background_raw and background_raw.get("enabled", True) and background_raw.get("preset") != "none")
            resolved_layers = []
            for ly in layers:
                img_path, _ = self._resolve_image_path(
                    ly.get("image_url", ""),
                    ly.get("source_panel_id"),
                    ly.get("source_page_id"),
                    workspace_path,
                    strict=background_active,
                )
                resolved_layers.append({**ly, "disk_image_path": img_path or ""})
                if not img_path:
                    missing_images += 1
                    warnings.append(f"Visual asset for layer '{ly.get('id', 'unnamed')}' in Scene '{sc.get('title', sc.get('id'))}' could not be resolved.")
            try:
                self._compile_background(sc, state, resolved_layers, workspace_path, project_id)
            except ValueError as exc:
                issues.append(f"Background in scene '{sc.get('title', sc.get('id'))}': {exc}")

        # 2. Validate Narration clips
        narration_clips = self._resolve_narration_timing(scenes, state.get("narration_clips", []))
        approved_narration = 0
        outdated_narration = 0
        missing_narration = 0

        for clip in narration_clips:
            status = clip.get("status", "UNQUEUED")
            rev_status = clip.get("review_status", "DRAFT")
            audio_url = clip.get("audio_url")
            resolved_audio = self._resolve_audio_path(audio_url, workspace_path) if audio_url else None

            if status == "OUTDATED":
                outdated_narration += 1
                warnings.append(f"Narration clip '{clip.get('speaker', 'Narrator')}' at {clip.get('start_time_sec', 0):.1f}s is flagged OUTDATED because script text was revised.")
            elif not resolved_audio:
                missing_narration += 1
                warnings.append(f"Narration clip '{clip.get('speaker', 'Narrator')}' has no synthesized audio file.")
            elif rev_status == "APPROVED" or status in ("READY", "PROCESSING"):
                approved_narration += 1

        # 3. Validate BGM and SFX
        bgm_tracks = state.get("bgm_tracks", [])
        resolved_bgm_count = 0
        for bgm in bgm_tracks:
            p = self._resolve_audio_path(bgm.get("file_url", ""), workspace_path)
            if p:
                resolved_bgm_count += 1
            else:
                warnings.append(f"BGM asset '{bgm.get('title', 'BGM')}' not found on disk.")

        sfx_cues = state.get("sfx_cues", [])
        resolved_sfx_count = 0
        for sfx in sfx_cues:
            p = self._resolve_audio_path(sfx.get("file_url", ""), workspace_path)
            if p:
                resolved_sfx_count += 1

        # Calculate planned duration
        planned_duration = max((sc["start_time_sec"] + sc["duration_sec"] for sc in scenes), default=0.0)

        return {
            "valid": len(issues) == 0,
            "blockers": issues,
            "warnings": warnings,
            "stats": {
                "scenes_count": len(scenes),
                "layers_count": total_layers,
                "narration_clips_total": len(narration_clips),
                "narration_approved": approved_narration,
                "narration_outdated": outdated_narration,
                "narration_missing": missing_narration,
                "bgm_tracks_count": resolved_bgm_count,
                "sfx_cues_count": resolved_sfx_count,
                "planned_duration_sec": round(planned_duration, 2),
                "total_frames_30fps": int(round(planned_duration * 30.0)),
            },
        }

    def compile(
        self,
        state: Dict[str, Any],
        project_id: str,
        workspace_path: Path,
        profile: Optional[RenderProfile] = None,
        subtitle_enabled: bool = False,
        bgm_volume_db: float = -10.0,
        dialogue_gain_db: float = 0.0,
    ) -> RenderPlan:
        """
        Compiles the state dictionary into an inspectable, deterministic RenderPlan.
        """
        prof = profile or RenderProfile.standard_1080p()
        if state.get("panel_review_sync", {}).get("removed_layers_count", 0):
            raise ValueError("Source panels were deleted or replaced. Review the affected video layers before exporting.")
        fps = prof.fps
        clock = RenderFrameClock(fps=fps)

        scenes = self._resolve_scene_timing(state.get("scenes", []))
        if not scenes:
            raise ValueError("Cannot compile timeline: no scenes found in timeline state.")

        # 1. Compute deterministic scene frame intervals
        running_time = 0.0
        shot_plans: List[RenderShotPlan] = []
        speech_intervals: List[Tuple[float, float, float]] = []

        # Gather narration intervals first for ducking & captions
        narration_clips = self._resolve_narration_timing(scenes, state.get("narration_clips", []))
        audio_tracks: List[RenderAudioTrack] = []

        for clip in narration_clips:
            clip_start = float(clip.get("start_time_sec", 0.0))
            clip_dur = float(clip.get("duration_sec", 0.0))
            clip_end = clip_start + clip_dur
            audio_url = clip.get("audio_url")
            resolved_p = self._resolve_audio_path(audio_url, workspace_path) if audio_url else None

            if resolved_p and clip_dur > 0:
                audio_tracks.append(
                    RenderAudioTrack(
                        track_type="dialogue",
                        file_path=resolved_p,
                        start_time=clip_start,
                        end_time=clip_end,
                        gain_db=dialogue_gain_db,
                    )
                )
                # Speech interval with ducking amount
                speech_intervals.append((clip_start, clip_end, -12.0))

        # 2. Compile Shot Plans
        for idx, sc in enumerate(scenes):
            sc_id = sc.get("id", f"scene_{idx + 1}")
            duration = float(sc.get("duration_sec", 4.0))
            start_time = float(sc.get("start_time_sec", running_time))
            end_time = start_time + duration
            running_time = end_time

            s_frame = clock.time_to_frame(start_time)
            e_frame = clock.time_to_frame(end_time)
            n_frames = max(1, e_frame - s_frame)

            # Compile visual layers
            compiled_layers: List[Dict[str, Any]] = []
            layers = sc.get("layers", [])
            raw_background = sc.get("background") if sc.get("background") is not None else state.get("background_default")
            validated_background = BackgroundSettings.model_validate(raw_background) if raw_background is not None else None
            background_active = bool(validated_background and validated_background.enabled and validated_background.preset != "none")

            for ly in layers:
                img_path, already_cropped = self._resolve_image_path(
                    ly.get("image_url", ""),
                    ly.get("source_panel_id"),
                    ly.get("source_page_id"),
                    workspace_path,
                    strict=background_active,
                )

                # Ensure crop has default
                raw_crop = ly.get("crop") or {"x": 0, "y": 0, "width": 100, "height": 100}
                raw_tf = ly.get("transform") or {"x": 0, "y": 0, "scale": 1.0, "rotation": 0, "opacity": 1.0, "z_index": 0}

                layer_data = {
                    "id": ly.get("id", f"layer_{len(compiled_layers) + 1}"),
                    "name": ly.get("name", "Visual Layer"),
                    "image_url": ly.get("image_url", ""),
                    "disk_image_path": img_path or "",
                    "already_cropped": bool(already_cropped),
                    "crop": raw_crop,
                    "transform": {
                        "x": float(raw_tf.get("x", 0.0)),
                        "y": float(raw_tf.get("y", 0.0)),
                        "scale": float(raw_tf.get("scale", 1.0)),
                        "rotation": float(raw_tf.get("rotation", 0.0)),
                        "opacity": float(raw_tf.get("opacity", 1.0)),
                        "z_index": int(raw_tf.get("z_index", 0)),
                    },
                    "start_offset_sec": float(ly.get("start_offset_sec", 0.0)),
                    "duration_sec": float(ly.get("duration_sec", duration)),
                    "motion_preset": ly.get("motion_preset") or "none",
                    "motion_direction": ly.get("motion_direction", "right"),
                    "motion_intensity": float(ly.get("motion_intensity", 1.0)),
                    "motion_easing": ly.get("motion_easing", "ease_in_out"),
                    "animation": ly.get("animation") or ly.get("animation_config") or {},
                    "visible": ly.get("visible", True) is not False,
                }
                compiled_layers.append(layer_data)

            background, background_image_path = self._compile_background(sc, state, compiled_layers, workspace_path, project_id)
            if background and background.enabled and background.preset != "none":
                tracks = state.get("track_states") or {}
                for layer_index, layer in enumerate(compiled_layers):
                    key, alias = ("Visuals", "visuals") if layer_index == 0 else ("Layer 2", "layer2")
                    track = tracks.get(key, tracks.get(alias, {}))
                    layer["visible"] = layer["visible"] and track.get("visible", True) is not False

            # Compile Camera Motion
            cam_data = sc.get("camera_motion") or sc.get("camera") or {
                "preset": "static",
                "zoom_start": 1.0,
                "zoom_end": 1.0,
                "pan_x_start": 0.0,
                "pan_x_end": 0.0,
                "pan_y_start": 0.0,
                "pan_y_end": 0.0,
                "easing": "ease_in_out",
                "duration_sec": duration,
            }

            # Compile Transition In
            trans_data = {
                "type": sc.get("transition_in", "none"),
                "duration_sec": float(sc.get("transition_duration_sec", 0.5)),
            }

            # Generate Subtitle Cues if enabled
            captions: List[CaptionCue] = []
            if subtitle_enabled:
                for clip in narration_clips:
                    c_start = float(clip.get("start_time_sec", 0.0))
                    c_end = c_start + float(clip.get("duration_sec", 0.0))
                    # Check overlap with this shot
                    if max(start_time, c_start) < min(end_time, c_end):
                        text = clip.get("text", "").strip()
                        if text:
                            captions.append(
                                CaptionCue(
                                    cue_id=f"cap_{clip.get('id', idx)}",
                                    start_time=c_start,
                                    end_time=c_end,
                                    text=text,
                                    speaker=clip.get("speaker"),
                                )
                            )

            primary_asset = compiled_layers[0]["disk_image_path"] if compiled_layers else ""

            shot_plans.append(
                RenderShotPlan(
                    shot_id=f"shot_{sc_id}",
                    scene_id=sc_id,
                    sequence_global=idx + 1,
                    source_asset_path=primary_asset,
                    start_frame=s_frame,
                    end_frame=e_frame,
                    total_frames=n_frames,
                    start_time=start_time,
                    end_time=end_time,
                    duration=duration,
                    scene_layers=compiled_layers,
                    background=background,
                    background_image_path=background_image_path,
                    camera_config=cam_data,
                    transition_config=trans_data,
                    captions=captions,
                )
            )

        total_duration = running_time
        total_frames = clock.time_to_frame(total_duration)

        # 3. Background Music Tracks
        bgm_tracks = state.get("bgm_tracks", [])
        for bgm in bgm_tracks:
            bgm_url = bgm.get("file_url")
            resolved_p = self._resolve_audio_path(bgm_url, workspace_path) if bgm_url else None
            if resolved_p:
                vol = float(bgm.get("volume", 0.6))
                gain_db = bgm_volume_db if bgm_volume_db != -10.0 else (20.0 * math.log10(max(0.01, vol)))
                duck_enabled = bgm.get("ducking_enabled", True)
                duck_amt = float(bgm.get("ducking_amount_db", -12.0))
                active_ducking = [(s, e, duck_amt) for s, e, _ in speech_intervals] if duck_enabled else []

                s_time = float(bgm.get("start_time_sec", 0.0))
                d_time = float(bgm.get("duration_sec", 0.0))
                e_time = min(total_duration, s_time + d_time) if d_time > 0 else total_duration

                audio_tracks.append(
                    RenderAudioTrack(
                        track_type="music",
                        file_path=resolved_p,
                        start_time=s_time,
                        end_time=e_time,
                        gain_db=gain_db,
                        ducking_intervals=active_ducking,
                    )
                )

        # 4. Sound Effects Tracks
        sfx_cues = state.get("sfx_cues", [])
        for sfx in sfx_cues:
            sfx_url = sfx.get("file_url")
            resolved_p = self._resolve_audio_path(sfx_url, workspace_path) if sfx_url else None
            if resolved_p:
                vol = float(sfx.get("volume", 0.8))
                gain = 20.0 * math.log10(max(0.01, vol))
                s_time = float(sfx.get("start_time_sec", 0.0))
                s_dur = float(sfx.get("duration_sec", 2.0))
                audio_tracks.append(
                    RenderAudioTrack(
                        track_type="sfx",
                        file_path=resolved_p,
                        start_time=s_time,
                        end_time=min(total_duration, s_time + s_dur),
                        gain_db=gain,
                    )
                )

        # 5. Deterministic Hash
        hash_payload = {
            "project_id": project_id,
            "duration": round(total_duration, 4),
            "total_frames": total_frames,
            "shots": [{"id": s.shot_id, "start_frame": s.start_frame, "end_frame": s.end_frame,
                       **({"background": s.background.model_dump(), "background_image_path": s.background_image_path}
                          if s.background is not None else {})} for s in shot_plans],
            "audio": [{"path": a.file_path, "start": a.start_time, "end": a.end_time} for a in audio_tracks],
            "profile": prof.model_dump(),
        }
        plan_hash = hashlib.sha256(json.dumps(hash_payload, sort_keys=True).encode()).hexdigest()

        return RenderPlan(
            project_id=project_id,
            total_duration_sec=total_duration,
            total_frames=total_frames,
            profile=prof,
            shots=shot_plans,
            audio_tracks=audio_tracks,
            music_policy=MusicDurationPolicy.LOOP,
            subtitle_enabled=subtitle_enabled,
            hash=plan_hash,
            metadata={
                "aspect_ratio": state.get("aspect_ratio", "16:9"),
                "compiled_from_story_editor": True,
                "scenes_count": len(shot_plans),
            },
        )


timeline_compiler = TimelineCompiler()
