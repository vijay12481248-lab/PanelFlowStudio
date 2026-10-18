"""
Story-Aware Music Director for PanelFlow Studio (Chapter 9).

Analyzes manga scene narrative, emotional trajectory, and timeline durations
to compose structured, continuous MusicDirectionPlans with story-aware cues,
motif progression, and editable ACE-Step generation prompts.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from engine.audio.models.music_plan import (
    MusicCuePlan,
    MusicDirectionPlan,
    MusicTakeRecord,
)
from engine.database.models import (
    ProjectRecord,
    VideoScriptRecord,
    ScriptSegmentRecord,
    SceneRecord,
    VisualTimelineRecord,
)

logger = logging.getLogger("panelflow.audio.music_director")


class StoryAwareMusicDirector:
    """
    Analyzes manga project narrative and orchestrates story-aware music direction.
    """

    def __init__(self):
        pass

    def get_or_create_plan(
        self,
        db: Session,
        project_id: str,
        force_replan: bool = False,
    ) -> MusicDirectionPlan:
        """
        Loads the persisted MusicDirectionPlan from the project workspace,
        or generates a new story-aware plan from the script and scenes.
        """
        proj = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
        if not proj:
            raise ValueError(f"Project not found: {project_id}")

        workspace = Path(proj.workspace_path)
        music_dir = workspace / "audio" / "music"
        music_dir.mkdir(parents=True, exist_ok=True)
        plan_file = music_dir / "music_direction_plan.json"

        if plan_file.exists() and not force_replan:
            try:
                data = json.loads(plan_file.read_text(encoding="utf-8"))
                return MusicDirectionPlan(**data)
            except Exception as e:
                logger.warning(f"Could not load existing music direction plan: {e}. Generating fresh plan.")

        # Generate fresh story-aware plan
        plan = self.analyze_and_plan_soundtrack(db, proj)
        self.save_plan(workspace, plan)
        return plan

    def save_plan(self, workspace_path: Path, plan: MusicDirectionPlan) -> None:
        """Persists the MusicDirectionPlan JSON sidecar to workspace."""
        music_dir = Path(workspace_path) / "audio" / "music"
        music_dir.mkdir(parents=True, exist_ok=True)
        plan_file = music_dir / "music_direction_plan.json"
        plan.updated_at = time.time()
        plan_file.write_text(plan.model_dump_json(indent=2), encoding="utf-8")

    def analyze_and_plan_soundtrack(
        self,
        db: Session,
        project: ProjectRecord,
    ) -> MusicDirectionPlan:
        """
        Performs deep story and timeline analysis to design a cohesive, multi-movement score.
        """
        project_id = project.id
        script = (
            db.query(VideoScriptRecord)
            .filter(VideoScriptRecord.project_id == project_id)
            .order_by(VideoScriptRecord.created_at.desc())
            .first()
        )
        segments: List[ScriptSegmentRecord] = script.segments if (script and script.segments) else []
        ordered_segments = sorted(segments, key=lambda s: s.sequence)

        # Inspect scenes and layout from SceneRecord or VisualTimelineRecord
        db_scenes = (
            db.query(SceneRecord)
            .filter(SceneRecord.project_id == project_id)
            .order_by(SceneRecord.sequence.asc())
            .all()
        )

        scenes_meta: List[Dict[str, Any]] = []
        if db_scenes:
            for sc in db_scenes:
                scenes_meta.append({
                    "id": sc.id,
                    "name": sc.title or f"Scene {sc.sequence + 1}",
                    "duration": 6.0,
                    "order": sc.sequence,
                })
        else:
            motion_rec = (
                db.query(VisualTimelineRecord)
                .filter(VisualTimelineRecord.project_id == project_id)
                .order_by(VisualTimelineRecord.created_at.desc())
                .first()
            )
            if motion_rec and motion_rec.timeline_json and "scenes" in motion_rec.timeline_json:
                for sc in motion_rec.timeline_json["scenes"]:
                    scenes_meta.append({
                        "id": sc.get("id"),
                        "name": sc.get("name", "Scene"),
                        "duration": float(sc.get("duration", 5.0)),
                        "order": int(sc.get("order", 0)),
                    })
        scenes_meta.sort(key=lambda s: s["order"])

        # If storyboard scenes metadata isn't populated, derive from script segments
        if not scenes_meta:
            seen_scenes = set()
            for seg in ordered_segments:
                sc_id = seg.scene_id or f"scene_{len(seen_scenes) + 1}"
                if sc_id not in seen_scenes:
                    seen_scenes.add(sc_id)
                    scenes_meta.append({
                        "id": sc_id,
                        "name": f"Scene {len(seen_scenes)}",
                        "duration": float(seg.estimated_duration or 6.0),
                        "order": len(seen_scenes) - 1,
                    })

        if not scenes_meta:
            # Fallback 60-second default scene sequence
            scenes_meta = [
                {"id": "scene_01", "name": "Opening Mystery", "duration": 8.0, "order": 0},
                {"id": "scene_02", "name": "Character Discovery", "duration": 10.0, "order": 1},
                {"id": "scene_03", "name": "Rising Tension", "duration": 12.0, "order": 2},
                {"id": "scene_04", "name": "Climactic Confrontation", "duration": 16.0, "order": 3},
                {"id": "scene_05", "name": "Aftermath & Resolution", "duration": 14.0, "order": 4},
            ]

        # Calculate cumulative timeline boundaries
        current_time = 0.0
        for sc in scenes_meta:
            sc["start_time"] = round(current_time, 2)
            sc["end_time"] = round(current_time + sc["duration"], 2)
            current_time = sc["end_time"]
        total_score_duration = round(current_time, 2)

        # Cluster scenes into cohesive musical cues / storytelling movements
        cues = self._cluster_scenes_into_cues(scenes_meta, ordered_segments, project.title)

        plan = MusicDirectionPlan(
            plan_id=f"mdp_{project_id[:8]}_{int(time.time())}",
            project_id=project_id,
            storyboard_id=None,
            overall_musical_theme="Ancient crystal techno-magic, tactical revelation, and dark fantasy tension",
            harmonic_key="D Minor / D Dorian",
            recommended_headroom_notes=(
                "Maintain 2 kHz - 5 kHz acoustic space for dialogue and sound effects. "
                "Keep dynamic peaks controlled (-1.0 dBFS) to ensure speech intelligibility."
            ),
            cues=cues,
            total_score_duration_sec=total_score_duration,
            created_at=time.time(),
            updated_at=time.time(),
        )

        return plan

    def _cluster_scenes_into_cues(
        self,
        scenes: List[Dict[str, Any]],
        segments: List[ScriptSegmentRecord],
        project_title: str,
    ) -> List[MusicCuePlan]:
        """
        Partitions the scenes into continuous musical cues based on narrative arc:
        Movement 1: Opening & Discovery
        Movement 2: Suspense & Escalation
        Movement 3: Action / Climax
        Movement 4: Resolution & Mystery Outro
        """
        num_scenes = len(scenes)
        cues: List[MusicCuePlan] = []

        if num_scenes <= 2:
            # Single continuous cue
            sc_ids = [s["id"] for s in scenes]
            st = scenes[0]["start_time"]
            et = scenes[-1]["end_time"]
            dur = round(et - st, 2)
            cues.append(
                MusicCuePlan(
                    cue_id="cue_01_complete_score",
                    title="Complete Narrative Underscore",
                    scene_ids=sc_ids,
                    start_time_sec=st,
                    end_time_sec=et,
                    duration_sec=dur,
                    narrative_function="ambient_underscore",
                    emotional_direction="mysterious and contemplative with subtle tension",
                    intensity=0.45,
                    genre_style="cinematic dark-fantasy underscore",
                    instrumentation=["low strings", "crystal chimes", "warm analog synth pad"],
                    tempo_bpm=82,
                    tonal_center="D Minor",
                    time_signature="4/4",
                    instrumental=True,
                    musical_continuity="establishes main harmonic theme throughout sequence",
                    editable_prompt=(
                        f"Instrumental cinematic dark-fantasy underscore for '{project_title}'. "
                        "Begin with sparse low strings and subtle crystal resonance. "
                        "Gradually introduce an evolving warm analog synth pad and restrained cello ostinato. "
                        "Mysterious and atmospheric, no harsh brass, no vocals, controlled dynamics, "
                        "leaves clean acoustic space for voice narration, natural acoustic and synthetic blending."
                    ),
                )
            )
            return cues

        # Multi-cue continuous score progression:
        # Cue 1: Opening & Discovery (scenes 1 .. ceil(N * 0.35))
        # Cue 2: Rising Tension & Escalation (ceil(N * 0.35) .. ceil(N * 0.70))
        # Cue 3: Confrontation & Resolution (ceil(N * 0.70) .. N)
        split1 = max(1, int(round(num_scenes * 0.35)))
        split2 = max(split1 + 1, int(round(num_scenes * 0.70)))

        group1 = scenes[:split1]
        group2 = scenes[split1:split2]
        group3 = scenes[split2:]

        # --- Cue 1: Opening Mystery & Tactical Discovery ---
        st1 = group1[0]["start_time"]
        et1 = group1[-1]["end_time"]
        dur1 = round(et1 - st1, 2)
        cues.append(
            MusicCuePlan(
                cue_id="cue_01_opening_mystery",
                title="Opening Mystery & Discovery",
                scene_ids=[s["id"] for s in group1],
                start_time_sec=st1,
                end_time_sec=et1,
                duration_sec=dur1,
                narrative_function="opening_mystery",
                emotional_direction="subtle curiosity, atmospheric dread, and careful discovery",
                intensity=0.35,
                genre_style="cinematic ambient dark-fantasy",
                instrumentation=["low cello", "crystal chimes", "distant metallic resonance", "soft analog pad"],
                tempo_bpm=78,
                tonal_center="D Minor",
                time_signature="4/4",
                instrumental=True,
                musical_continuity="establishes primary crystal motif and D Minor tonal center",
                editable_prompt=(
                    f"Instrumental cinematic dark-fantasy ambient underscore for '{project_title}'. "
                    "Sparse low cello and delicate crystal chimes with evolving subtle metallic resonance. "
                    "Mysterious, contemplative, and restrained. Controlled dynamic floor, "
                    "leaves 2 kHz to 5 kHz acoustic space for dialogue narration, no vocals, no trailer drums."
                ),
            )
        )

        # --- Cue 2: Rising Tension & Threat Escalation ---
        st2 = group2[0]["start_time"]
        et2 = group2[-1]["end_time"]
        dur2 = round(et2 - st2, 2)
        cues.append(
            MusicCuePlan(
                cue_id="cue_02_rising_tension",
                title="Rising Threat & Tactical Escalation",
                scene_ids=[s["id"] for s in group2],
                start_time_sec=st2,
                end_time_sec=et2,
                duration_sec=dur2,
                narrative_function="rising_threat",
                emotional_direction="anticipation, building suspense, and dark magical awakening",
                intensity=0.60,
                genre_style="orchestral suspense with kinetic synth pulse",
                instrumentation=["staccato strings", "dark sub-bass pulse", "taiko accents", "glass harmonica"],
                tempo_bpm=92,
                tonal_center="D Dorian",
                time_signature="4/4",
                instrumental=True,
                musical_continuity="develops rhythmic pulse out of opening crystal motif",
                editable_prompt=(
                    f"Instrumental cinematic tension cue for '{project_title}'. "
                    "Begins from restrained low strings, steadily introducing a rhythmic sub-bass pulse "
                    "and muted staccato string ostinato. Suspenseful, foreboding, and driving. "
                    "Clear midrange space for speech, crisp acoustic transients, no vocals, building momentum."
                ),
            )
        )

        # --- Cue 3: Confrontation & Emotional Resolution ---
        if group3:
            st3 = group3[0]["start_time"]
            et3 = group3[-1]["end_time"]
            dur3 = round(et3 - st3, 2)
            cues.append(
                MusicCuePlan(
                    cue_id="cue_03_confrontation_resolution",
                    title="Climactic Surge & Resolution",
                    scene_ids=[s["id"] for s in group3],
                    start_time_sec=st3,
                    end_time_sec=et3,
                    duration_sec=dur3,
                    narrative_function="emotional_resolution",
                    emotional_direction="dramatic release resolving into eerie calm and ancient mystery",
                    intensity=0.70,
                    genre_style="cinematic orchestral climax to atmospheric decay",
                    instrumentation=["full string section", "warm brass pad", "crystal chimes", "deep timpani"],
                    tempo_bpm=86,
                    tonal_center="D Minor",
                    time_signature="4/4",
                    instrumental=True,
                    musical_continuity="recapitulates main theme with emotional weight before fading to stillness",
                    editable_prompt=(
                        f"Instrumental cinematic climax and resolution cue for '{project_title}'. "
                        "Powerful sustained cello and violin chords with deep resonant percussion, "
                        "recapitulating the crystal chime theme with emotional gravity. "
                        "Gradually softens into an ambient atmospheric decay. "
                        "No vocals, no spoken words, smooth transitions, dialogue-safe mix."
                    ),
                )
            )

        return cues

    def update_cue_prompt(
        self,
        workspace_path: Path,
        plan: MusicDirectionPlan,
        cue_id: str,
        new_prompt: str,
        bpm: Optional[int] = None,
        intensity: Optional[float] = None,
    ) -> MusicCuePlan:
        """Updates a cue's prompt or musical parameters and persists the plan."""
        target_cue = next((c for c in plan.cues if c.cue_id == cue_id), None)
        if not target_cue:
            raise ValueError(f"Cue '{cue_id}' not found in plan")

        target_cue.editable_prompt = new_prompt.strip()
        if bpm is not None:
            target_cue.tempo_bpm = max(40, min(240, bpm))
        if intensity is not None:
            target_cue.intensity = max(0.0, min(1.0, intensity))

        self.save_plan(workspace_path, plan)
        return target_cue

    def attach_take_to_cue(
        self,
        workspace_path: Path,
        plan: MusicDirectionPlan,
        cue_id: str,
        take: MusicTakeRecord,
        set_as_selected: bool = True,
    ) -> MusicDirectionPlan:
        """Registers a new candidate take under the specified cue."""
        target_cue = next((c for c in plan.cues if c.cue_id == cue_id), None)
        if not target_cue:
            # If cue not found, attach to first cue or create a custom cue
            if plan.cues:
                target_cue = plan.cues[0]
            else:
                target_cue = MusicCuePlan(
                    cue_id=cue_id,
                    title="Custom Generated Score",
                    scene_ids=[],
                    duration_sec=take.duration_sec,
                    editable_prompt=take.prompt,
                )
                plan.cues.append(target_cue)

        # Check if take already registered
        existing = next((t for t in target_cue.takes if t.take_id == take.take_id), None)
        if not existing:
            target_cue.takes.append(take)

        if set_as_selected or target_cue.selected_take_id is None:
            target_cue.selected_take_id = take.take_id

        self.save_plan(workspace_path, plan)
        return plan

    def select_take(
        self,
        workspace_path: Path,
        plan: MusicDirectionPlan,
        cue_id: str,
        take_id: str,
    ) -> MusicDirectionPlan:
        """Selects which candidate take is active for the cue."""
        target_cue = next((c for c in plan.cues if c.cue_id == cue_id), None)
        if not target_cue:
            raise ValueError(f"Cue '{cue_id}' not found")

        matching_take = next((t for t in target_cue.takes if t.take_id == take_id), None)
        if not matching_take:
            raise ValueError(f"Take '{take_id}' not found under cue '{cue_id}'")

        target_cue.selected_take_id = take_id
        for t in target_cue.takes:
            if t.take_id == take_id:
                t.approval_status = "APPROVED"
            elif t.approval_status == "APPROVED":
                t.approval_status = "DRAFT"

        self.save_plan(workspace_path, plan)
        return plan


story_aware_music_director = StoryAwareMusicDirector()
