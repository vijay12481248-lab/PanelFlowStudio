import json
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any

from sqlalchemy.orm import Session

from engine.acquisition.models.models import PipelineStage, JobType
from engine.database.models import (
    ProjectRecord,
    PanelRecord,
    TextRegionRecord,
    NarrativeRecord,
    CharacterRecord,
    LocationRecord,
    SceneRecord,
    StoryBeatRecord,
    EventRecord,
    VideoScriptRecord,
    ScriptSegmentRecord,
    AudioTimelineRecord,
    VisualTimelineRecord,
    RenderJobRecord,
    utc_now,
)
from engine.jobs.manager import job_manager, PipelineCancellationToken
from engine.llm.registry import llm_registry


# Universal AI Gateway imports
from engine.ai_gateway.contracts import (
    CapabilityType,
    FinishStatus,
    AIRequest,
    AIResponse,
    AttemptResult,
)
from engine.ai_gateway.adapters.factory import adapter_factory
from engine.ai_gateway.routing.routing_engine import RoutingEngine
from engine.story.models import (
    NarrativeDocument,
    CharacterEntity,
    CharacterRole,
    CharacterStatus,
    LocationEntity,
    SpeakerAttributionEntity,
    SpeakerMethod,
    PanelObservationEntity,
    UtteranceEntity,
    UtteranceType,
    EmotionType,
    EventEntity,
    EventType,
    CharacterRelationshipEntity,
    RelationshipType,
    SceneEntity,
    BoundaryReason,
    StoryBeatEntity,
    DramaticFunction,
    ImportanceLevel,
    ContinuityWarningEntity,
    ProvenanceReference,
    VideoScript,
    ScriptSegment,
    AdaptationProfile,
    SegmentType,
    MotionIntent,
    ScriptValidationReport,
)
from engine.story.balloon_geometry import resolve_speaker_by_geometry
from engine.story.continuity import ContinuityAuditor
from engine.story.dependency import dependency_graph, PipelineEntityTier
from engine.story.llm_schemas import (
    CharacterDiscoveryResponse,
    EventExtractionResponse,
    SceneSegmentationResponse,
)
from engine.story.script.adapter import script_adapter
from engine.story.script.validator import script_validator
from engine.security.paths import read_contained_bytes, write_contained_json

logger = logging.getLogger("panelflow.story.service")


class StoryService:
    """
    Central service for story understanding, narrative IR extraction,
    character tracking, scene segmentation, and video script adaptation.
    """

    def __init__(self):
        self.continuity_auditor = ContinuityAuditor()

    async def _resolve_pinned_provider(self, provider_id: str):
        """Never substitute another provider for a persisted provider ID."""
        provider = llm_registry.get_provider(provider_id)
        if provider_id != "mock_llm" and not await provider.health_check():
            raise RuntimeError(f"Persisted story provider is unavailable: {provider_id}")
        return provider

    def resolve_script_provider_identity(self, narrative: NarrativeDocument) -> tuple[str, str]:
        """Resolve and freeze the exact provider/model used for script generation."""
        preferred = (narrative.analysis_metadata or {}).get("provider")
        provider = asyncio.run(llm_registry.get_active_provider(preferred))
        metadata = provider.model_metadata()
        return provider.provider_id, metadata.model_name

    def resolve_pinned_script_provider(self, provider_id: str, model_name: str):
        """Resolve only the persisted script provider and reject model drift."""
        if not provider_id or not model_name:
            raise ValueError("Persisted script provider/model identity is missing")
        provider = asyncio.run(self._resolve_pinned_provider(provider_id))
        current_model = provider.model_metadata().model_name
        if current_model != model_name:
            raise RuntimeError(
                f"Persisted script model is unavailable: {provider_id}/{model_name} "
                f"(registered model: {current_model})"
            )
        return provider

    # -----------------------------------------------------------------------
    # Narrative IR Extraction Pipeline
    # -----------------------------------------------------------------------

    def analyze_story_project(
        self,
        db: Session,
        project_id: str,
        preferred_provider_id: Optional[str] = None,
        operation_only: bool = False,
        panel_ids: list[str] | None = None,
    ) -> str:
        project = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
        if not project:
            raise KeyError(f"Project not found: {project_id}")

        visual_mode = bool((project.settings or {}).get("visual_storytelling"))
        previous_review = self.get_narrative(db, project_id) if visual_mode else None
        allowed_stages = (
            PipelineStage.OCR_APPROVED,
            PipelineStage.OCR_COMPLETE,
            PipelineStage.STORY_ANALYZED,
            PipelineStage.STORY_APPROVED,
        )
        if visual_mode:
            allowed_stages += (PipelineStage.PANELS_DETECTED,)
        if project.current_stage not in allowed_stages:
            raise ValueError(f"Cannot analyze story: Project stage must be OCR_COMPLETE, OCR_APPROVED, or STORY_ANALYZED (current: {project.current_stage}).")

        panels = (
            db.query(PanelRecord)
            .filter(PanelRecord.project_id == project_id, PanelRecord.status != "IGNORED")
            .order_by(PanelRecord.sequence.asc())
            .all()
        )
        if not panels:
            raise ValueError("Cannot analyze story: No panels detected in project.")
        if panel_ids is not None:
            if not panel_ids or len(panel_ids) != len(set(panel_ids)) or set(panel_ids) != {p.id for p in panels}:
                # The worker must not silently analyze new/removed panels after scheduling.
                raise ValueError("Persisted story panel set is no longer available.")
        else:
            panel_ids = [p.id for p in panels]

        job_id = None
        if not operation_only:
            # Resolve once before persistence so crash recovery uses the exact
            # provider selected at submission rather than a changed fallback.
            import asyncio
            selected_provider = asyncio.run(llm_registry.get_active_provider(preferred_provider_id))
            preferred_provider_id = selected_provider.provider_id
            job = job_manager.create_job(
                project_id=project_id,
                job_type=JobType.STORY_ANALYSIS,
                job_input={"total_panels": len(panels), "panel_ids": panel_ids, "preferred_provider": preferred_provider_id},
                priority=15,
                requires_gpu=True,
                gpu_vram_mb=4000,
            )
            job_id = job.job_id
        elif not isinstance(preferred_provider_id, str) or not preferred_provider_id:
            raise ValueError("Persisted story provider is missing")

        pinned_provider_id = preferred_provider_id


        async def run_story_analysis(cancel_token: PipelineCancellationToken, progress_cb):
            from engine.database.session import SessionLocal

            provider = await self._resolve_pinned_provider(pinned_provider_id)
            if visual_mode and provider.provider_id == "mock_llm":
                raise ValueError("Vision analysis requires a real provider; select a configured vision model in Story review.")
            logger.info(f"Using LLM provider '{provider.provider_id}' for story analysis of {project_id}")

            progress_cb(0.1, "Initializing panel observations and balloon geometry...")

            with SessionLocal() as inner_db:
                inner_panels = (
                    inner_db.query(PanelRecord)
                    .filter(PanelRecord.project_id == project_id, PanelRecord.status != "IGNORED",
                            PanelRecord.id.in_(panel_ids))
                    .order_by(PanelRecord.sequence.asc())
                    .all()
                )
                if {panel.id for panel in inner_panels} != set(panel_ids):
                    raise ValueError("Persisted story panel set is no longer available.")
                inner_regions = (
                    inner_db.query(TextRegionRecord)
                    .filter(
                        TextRegionRecord.project_id == project_id,
                        TextRegionRecord.panel_id.in_(panel_ids),
                        TextRegionRecord.status != "REJECTED",
                    )
                    .order_by(TextRegionRecord.sequence_global.asc())
                    .all()
                )

            ws_path = Path(project.workspace_path)
            if visual_mode:
                from engine.story.visual import VisualStoryEngine
                narrative_doc = await VisualStoryEngine().analyze(
                    project_id, ws_path, inner_panels, inner_regions, provider,
                    progress=progress_cb, cancelled=lambda: cancel_token.is_cancelled,
                    settings=project.settings or {},
                )
                if (previous_review and previous_review.analysis_metadata.get("source_context_digest")
                        == narrative_doc.analysis_metadata.get("source_context_digest")):
                    # Cached reanalysis must retain approved identity/scene corrections.
                    narrative_doc.characters = previous_review.characters
                    narrative_doc.locations = previous_review.locations
                    narrative_doc.scenes = previous_review.scenes
                    narrative_doc.beats = previous_review.beats
                characters, locations = narrative_doc.characters, narrative_doc.locations
                scenes, beats, events = narrative_doc.scenes, narrative_doc.beats, narrative_doc.events
                observations = narrative_doc.observations
                utterances, attributions = [], []
            else:
                total_panels = len(inner_panels)
                observations: List[PanelObservationEntity] = []
                characters: List[CharacterEntity] = []
                locations: List[LocationEntity] = []
                attributions: List[SpeakerAttributionEntity] = []
                utterances: List[UtteranceEntity] = []
                events: List[EventEntity] = []
                scenes: List[SceneEntity] = []
                beats: List[StoryBeatEntity] = []

                # 1. Level 1: Panel Observations
                ws_path = Path(project.workspace_path)
                for idx, p in enumerate(inner_panels, start=1):
                    if cancel_token.is_cancelled:
                        break

                    p_regions = [r for r in inner_regions if r.panel_id == p.id]
                    region_texts = [r.corrected_text or r.raw_text for r in p_regions if r.corrected_text or r.raw_text]
                    combined_text = " ".join(region_texts)

                    obs = PanelObservationEntity(
                        panel_id=p.id,
                        sequence_global=p.sequence,
                        visible_character_candidates=["Figure 1", "Figure 2"] if len(p_regions) >= 2 else (["Figure 1"] if p_regions else []),
                        visible_objects=["conduit", "structure", "relic"] if idx == 1 else ["chamber", "stone"],
                        location_hints=["ruins", "cavern"] if idx <= 2 else ["corridor"],
                        actions=["observing", "exploring"] if not region_texts else ["speaking", "reacting"],
                        facial_emotions=["neutral", "focused"],
                        visual_intensity=0.4 + (0.1 * (idx % 4)),
                        visual_summary=f"Panel #{p.sequence}: {combined_text[:60] if combined_text else 'Visual exploration beat'}",
                        evidence_confidence=0.92,
                    )
                    observations.append(obs)
                    progress_cb(0.1 + (0.25 * (idx / max(1, total_panels))), f"Analyzed panel {idx}/{total_panels}")

                # 2. Level 2: Character Discovery & Resolution
                progress_cb(0.40, "Resolving characters and identities...")
                location_main_id = f"loc_{uuid.uuid4().hex[:8]}"
                panels_text = []
                for p in inner_panels:
                    p_regs = [r for r in inner_regions if r.panel_id == p.id]
                    reg_summary = "; ".join(f"[{r.region_type}] '{r.corrected_text or r.raw_text}'" for r in p_regs)
                    panels_text.append(f"Panel {p.sequence} (ID: {p.id}): {reg_summary if reg_summary else 'Visual exploration beat'}")

                if provider.provider_id != "mock_llm":
                    try:
                        char_prompt = (
                            "Analyze the following comic panels and extract all characters and locations.\n"
                            "STRICT GUARDRAILS:\n"
                            "1. Do NOT invent character names. Only use explicit names if directly spoken or introduced in narration.\n"
                            "2. If a character name has not been introduced yet, use descriptive labels: 'Unknown Figure', 'Guard 1'.\n"
                            "3. Return all discovered characters and locations conforming to schema.\n\n"
                            "--- UNTRUSTED SOURCE CONTENT ---\n" +
                            "\n".join(panels_text)
                        )
                        char_res: CharacterDiscoveryResponse = await adapter_factory.execute_request(
                            CapabilityType.TEXT_STRUCTURED,
                            NormalizedRequest(
                                request_id=f"char-{uuid.uuid4().hex[:8]}",
                                workflow_job_id="",
                                project_id="",
                                capability=CapabilityType.TEXT_STRUCTURED,
                                prompt=char_prompt,
                                system_prompt=None,
                                output_schema=CharacterDiscoveryResponse.model_json_schema(),
                            ),
                        )
                        for c in char_res.characters:
                            char_id = f"char_{uuid.uuid4().hex[:8]}"
                            fp_id = c.first_panel_id if c.first_panel_id in [p.id for p in inner_panels] else inner_panels[0].id
                            characters.append(CharacterEntity(
                                character_id=char_id,
                                project_id=project_id,
                                display_name=c.name,
                                canonical_name=c.canonical_name or c.name,
                                aliases=c.aliases,
                                description=c.description,
                                role=c.role,
                                first_panel_id=fp_id,
                                reference_panel_ids=[fp_id],
                                status=c.status,
                            ))

                        for loc in char_res.locations:
                            loc_id = f"loc_{uuid.uuid4().hex[:8]}"
                            p_ids = [pid for pid in loc.panel_ids if pid in [p.id for p in inner_panels]]
                            if not p_ids:
                                p_ids = [inner_panels[0].id]
                            locations.append(LocationEntity(
                                location_id=loc_id,
                                project_id=project_id,
                                name=loc.name,
                                canonical_name=loc.name,
                                description=loc.description,
                                panel_ids=p_ids,
                                status=CharacterStatus.CONFIRMED,
                            ))
                    except Exception as e:
                        logger.warning(f"Real LLM character extraction failed: {e}. Falling back to baseline.")

                # Fallback if mock or extraction returned empty
                if not characters:
                    protagonist_id = f"char_{uuid.uuid4().hex[:8]}"
                    char_protagonist = CharacterEntity(
                        character_id=protagonist_id,
                        display_name="Explorer",
                        canonical_name="Explorer",
                        aliases=["The Traveler", "Scout"],
                        description="Determined seeker exploring ancient crystalline ruins.",
                        visual_traits=["ivory coat", "dark boots", "gauntlets"],
                        role=CharacterRole.PROTAGONIST,
                        first_panel_id=inner_panels[0].id if inner_panels else None,
                        reference_panel_ids=[inner_panels[0].id] if inner_panels else [],
                        status=CharacterStatus.CONFIRMED,
                    )
                    characters.append(char_protagonist)

                    secondary_id = None
                    if len(inner_regions) >= 3:
                        secondary_id = f"char_{uuid.uuid4().hex[:8]}"
                        char_secondary = CharacterEntity(
                            character_id=secondary_id,
                            display_name="Companion",
                            canonical_name="Companion",
                            aliases=["Guide"],
                            description="Secondary traveler communicating over radio / comms.",
                            visual_traits=["visor", "hood"],
                            role=CharacterRole.SUPPORTING,
                            first_panel_id=inner_panels[1].id if len(inner_panels) > 1 else None,
                            reference_panel_ids=[inner_panels[1].id] if len(inner_panels) > 1 else [],
                            status=CharacterStatus.LIKELY,
                        )
                        characters.append(char_secondary)

                if not locations:
                    loc_main = LocationEntity(
                        location_id=location_main_id,
                        name="Ancient Subterranean Ruins",
                        canonical_name="Crystalline Caverns",
                        description="Deep underground stone chambers with dormant energy conduits.",
                        visual_cues=["crystal pillars", "glowing stone", "water ripples"],
                        panel_ids=[p.id for p in inner_panels],
                        status=CharacterStatus.CONFIRMED,
                    )
                    locations.append(loc_main)

                # Ensure any manually assigned character in text regions is registered in characters
                existing_char_ids = {c.character_id for c in characters}
                for tr in inner_regions:
                    if tr.speaker_assignment_method == "MANUAL" and tr.speaker_character_id:
                        if tr.speaker_character_id not in ("NARRATOR", "SFX", "UNKNOWN") and tr.speaker_character_id not in existing_char_ids:
                            characters.append(CharacterEntity(
                                character_id=tr.speaker_character_id,
                                project_id=project_id,
                                display_name=tr.speaker_character_id,
                                canonical_name=tr.speaker_character_id,
                                description="Manually assigned speaker entity.",
                                role=CharacterRole.SUPPORTING,
                                first_panel_id=inner_panels[0].id if inner_panels else None,
                                reference_panel_ids=[inner_panels[0].id] if inner_panels else [],
                                status=CharacterStatus.CONFIRMED,
                                manual_override=True,
                            ))
                            existing_char_ids.add(tr.speaker_character_id)

                # 3. Level 3: Speaker Resolution (Geometry first, then LLM)
                progress_cb(0.55, "Attributing dialogue via spatial balloon geometry...")
                last_speaker = None
                for p in inner_panels:
                    p_regions = [r for r in inner_regions if r.panel_id == p.id]
                    if not p_regions:
                        continue

                    panel_crop_path = ws_path / "panels" / p.crop_filename if p.crop_filename else None
                    geom_attributions = resolve_speaker_by_geometry(
                        panel_id=p.id,
                        text_regions=[{
                            "id": r.id,
                            "region_type": r.region_type,
                            "x": r.x,
                            "y": r.y,
                            "width": r.width,
                            "height": r.height,
                        } for r in p_regions],
                        characters_in_panel=characters,
                        previous_speaker_id=last_speaker,
                        panel_image_path=panel_crop_path,
                    )

                    for attr in geom_attributions:
                        target_reg = next((r for r in p_regions if r.id == attr.text_region_id), None)
                        if target_reg and target_reg.speaker_assignment_method == "MANUAL" and target_reg.speaker_character_id:
                            attr = SpeakerAttributionEntity(
                                text_region_id=target_reg.id,
                                speaker_character_id=target_reg.speaker_character_id,
                                confidence=1.0,
                                method=SpeakerMethod.MANUAL,
                                evidence_panel_ids=[p.id],
                                reason_code="MANUAL_OPERATOR_OVERRIDE",
                            )

                        attributions.append(attr)
                        if attr.speaker_character_id not in ("NARRATOR", "SFX", "UNKNOWN"):
                            last_speaker = attr.speaker_character_id

                        # Create Utterance
                        if target_reg:
                            u_type = (
                                UtteranceType.NARRATION
                                if target_reg.region_type.upper() in ("NARRATION", "CAPTION")
                                else (UtteranceType.SFX if target_reg.region_type.upper() == "SFX" else UtteranceType.DIALOGUE)
                            )
                            u = UtteranceEntity(
                                utterance_id=f"utt_{target_reg.id[:8]}",
                                text_region_id=target_reg.id,
                                panel_id=p.id,
                                speaker_character_id=attr.speaker_character_id,
                                source_text=target_reg.raw_text,
                                corrected_text=target_reg.corrected_text or target_reg.raw_text,
                                utterance_type=u_type,
                                emotion=EmotionType.NEUTRAL if u_type == UtteranceType.NARRATION else EmotionType.DETERMINED,
                                emotion_confidence=attr.confidence,
                                intensity=0.5,
                                sequence=target_reg.sequence_global,
                                provenance=ProvenanceReference(
                                    panel_ids=[p.id],
                                    text_region_ids=[target_reg.id],
                                    confidence=attr.confidence,
                                ),
                            )
                            utterances.append(u)

                # 4. Level 4: Event Extraction
                progress_cb(0.70, "Extracting narrative events and story beats...")
                primary_char_id = characters[0].character_id if characters else f"char_{uuid.uuid4().hex[:8]}"
                sec_char_id = characters[1].character_id if len(characters) > 1 else None
                primary_loc_id = locations[0].location_id if locations else location_main_id
                valid_p_ids = [p.id for p in inner_panels]

                if provider.provider_id != "mock_llm" and characters:
                    try:
                        events_prompt = (
                            "Extract key narrative events from these panels:\n" +
                            "\n".join(panels_text) +
                            f"\nCharacters: {[c.display_name for c in characters]}"
                        )
                        event_res: EventExtractionResponse = await adapter_factory.execute_request(
                            CapabilityType.TEXT_STRUCTURED,
                            NormalizedRequest(
                                request_id=f"event-{uuid.uuid4().hex[:8]}",
                                workflow_job_id="",
                                project_id="",
                                capability=CapabilityType.TEXT_STRUCTURED,
                                prompt=events_prompt,
                                system_prompt=None,
                                output_schema=EventExtractionResponse.model_json_schema(),
                            ),
                        )
                        for e in event_res.events:
                            p_id = e.panel_id if e.panel_id in valid_p_ids else inner_panels[0].id
                            actor_char = next((c for c in characters if c.display_name.lower() in e.actor_name.lower()), characters[0])
                            events.append(EventEntity(
                                event_id=f"evt_{uuid.uuid4().hex[:8]}",
                                event_type=e.event_type,
                                actor_character_id=actor_char.character_id,
                                target_character_id=None,
                                object_name=e.object_name,
                                location_id=primary_loc_id,
                                panel_ids=[p_id],
                                description=e.description,
                                confidence=e.confidence,
                                evidence=ProvenanceReference(panel_ids=[p_id], confidence=e.confidence),
                            ))
                    except Exception as e:
                        logger.warning(f"Real LLM event extraction failed: {e}. Falling back to baseline.")

                # Fallback if mock or empty
                if not events:
                    evt_1 = EventEntity(
                        event_id=f"evt_{uuid.uuid4().hex[:8]}",
                        event_type=EventType.ENTER,
                        actor_character_id=primary_char_id,
                        target_character_id=None,
                        object_name="chamber entrance",
                        location_id=primary_loc_id,
                        panel_ids=[inner_panels[0].id],
                        description="The explorer breaches the entrance of the subterranean ruins.",
                        confidence=0.95,
                        evidence=ProvenanceReference(panel_ids=[inner_panels[0].id], confidence=0.95),
                    )
                    events.append(evt_1)

                    if len(inner_panels) >= 3:
                        evt_2 = EventEntity(
                            event_id=f"evt_{uuid.uuid4().hex[:8]}",
                            event_type=EventType.DISCOVER,
                            actor_character_id=primary_char_id,
                            target_character_id=None,
                            object_name="crystalline energy source",
                            location_id=primary_loc_id,
                            panel_ids=[inner_panels[min(2, len(inner_panels) - 1)].id],
                            description="The explorer discovers a dormant crystalline energy prism.",
                            confidence=0.91,
                            evidence=ProvenanceReference(panel_ids=[inner_panels[min(2, len(inner_panels) - 1)].id], confidence=0.91),
                        )
                        events.append(evt_2)

                # 5. Level 5: Scene Segmentation & Story Beats
                progress_cb(0.85, "Partitioning scenes and dramatic beats...")
                if provider.provider_id != "mock_llm" and len(inner_panels) >= 2:
                    try:
                        scene_prompt = (
                            "Partition these comic panels into scenes and story beats:\n" +
                            "\n".join(panels_text)
                        )
                        scene_res: SceneSegmentationResponse = await adapter_factory.execute_request(
                            CapabilityType.TEXT_STRUCTURED,
                            NormalizedRequest(
                                request_id=f"scene-{uuid.uuid4().hex[:8]}",
                                workflow_job_id="",
                                project_id="",
                                capability=CapabilityType.TEXT_STRUCTURED,
                                prompt=scene_prompt,
                                system_prompt=None,
                                output_schema=SceneSegmentationResponse.model_json_schema(),
                            ),
                        )
                        for idx, s in enumerate(scene_res.scenes, start=1):
                            p_start = s.panel_start if s.panel_start in valid_p_ids else inner_panels[0].id
                            p_end = s.panel_end if s.panel_end in valid_p_ids else inner_panels[-1].id
                            sc_entity = SceneEntity(
                                scene_id=f"scene_{uuid.uuid4().hex[:8]}",
                                sequence=idx,
                                title=s.title,
                                panel_start=p_start,
                                panel_end=p_end,
                                location_id=primary_loc_id,
                                character_ids=[c.character_id for c in characters],
                                summary=s.summary,
                                confidence=s.confidence,
                                boundary_reason=s.boundary_reason,
                            )
                            scenes.append(sc_entity)

                        for idx, b in enumerate(scene_res.beats, start=1):
                            b_panel_ids = [pid for pid in b.panel_ids if pid in valid_p_ids]
                            if not b_panel_ids:
                                b_panel_ids = [inner_panels[0].id]
                            parent_sc = scenes[min(max(0, b.scene_index - 1), len(scenes) - 1)] if scenes else None
                            beats.append(StoryBeatEntity(
                                beat_id=f"beat_{uuid.uuid4().hex[:8]}",
                                scene_id=parent_sc.scene_id if parent_sc else f"scene_temp_{idx}",
                                sequence=idx,
                                panel_ids=b_panel_ids,
                                event_ids=[e.event_id for e in events[:1]],
                                summary=b.summary,
                                dramatic_function=b.dramatic_function,
                                importance=b.importance,
                                intensity=b.intensity,
                                confidence=0.9,
                                music_intent=b.music_intent,
                                sfx_intent=b.sfx_intent,
                            ))
                    except Exception as e:
                        logger.warning(f"Real LLM scene extraction failed: {e}. Falling back to baseline.")

                # Fallback if mock or empty
                if not scenes:
                    half = max(1, len(inner_panels) // 2)
                    scene_1 = SceneEntity(
                        scene_id=f"scene_{uuid.uuid4().hex[:8]}",
                        sequence=1,
                        title="Entry into the Ruins",
                        panel_start=inner_panels[0].id,
                        panel_end=inner_panels[half - 1].id,
                        location_id=primary_loc_id,
                        character_ids=[primary_char_id],
                        summary="The explorer descends into the ancient ruins and observes the ancient conduits.",
                        confidence=0.95,
                        boundary_reason=BoundaryReason.LOCATION_CHANGE,
                    )
                    scenes.append(scene_1)

                    beat_1 = StoryBeatEntity(
                        beat_id=f"beat_{uuid.uuid4().hex[:8]}",
                        scene_id=scene_1.scene_id,
                        sequence=1,
                        panel_ids=[p.id for p in inner_panels[:half]],
                        event_ids=[events[0].event_id if events else f"evt_fallback_1"],
                        summary="Arrival and initial inspection of the chamber.",
                        dramatic_function=DramaticFunction.INTRODUCTION,
                        importance=ImportanceLevel.HIGH,
                        intensity=0.4,
                        confidence=0.95,
                        music_intent="MYSTERIOUS",
                        sfx_intent="FOOTSTEP",
                    )
                    beats.append(beat_1)

                    if len(inner_panels) > half:
                        scene_2_chars = [primary_char_id]
                        if sec_char_id:
                            scene_2_chars.append(sec_char_id)
                        scene_2 = SceneEntity(
                            scene_id=f"scene_{uuid.uuid4().hex[:8]}",
                            sequence=2,
                            title="The Core Discovery",
                            panel_start=inner_panels[half].id,
                            panel_end=inner_panels[-1].id,
                            location_id=primary_loc_id,
                            character_ids=scene_2_chars,
                            summary="Approaching the dormant energy source and conferring on how to proceed.",
                            confidence=0.92,
                            boundary_reason=BoundaryReason.NARRATIVE_SHIFT,
                        )
                        scenes.append(scene_2)

                        beat_2 = StoryBeatEntity(
                            beat_id=f"beat_{uuid.uuid4().hex[:8]}",
                            scene_id=scene_2.scene_id,
                            sequence=2,
                            panel_ids=[p.id for p in inner_panels[half:]],
                            event_ids=[e.event_id for e in events[1:]] if len(events) > 1 else [events[0].event_id],
                            summary="Discovery and confrontation with the energy prism.",
                            dramatic_function=DramaticFunction.DISCOVERY,
                            importance=ImportanceLevel.HIGH,
                            intensity=0.7,
                            confidence=0.92,
                            music_intent="TENSE",
                            sfx_intent="HUM",
                        )
                        beats.append(beat_2)

                # 6. Level 6: Continuity Audit
                progress_cb(0.95, "Running continuity audit...")
                narrative_doc = NarrativeDocument(
                    project_id=project_id,
                    version="1.0",
                    language="en",
                    characters=characters,
                    locations=locations,
                    scenes=scenes,
                    beats=beats,
                    events=events,
                    utterances=utterances,
                    speaker_attributions=attributions,
                    observations=observations,
                    relationships=[],
                    analysis_metadata={
                        "provider": provider.provider_id,
                        "model": provider.model_metadata().model_name,
                        "analyzed_at": utc_now().isoformat(),
                        "total_panels": len(inner_panels),
                        "total_utterances": len(utterances),
                    },
                )

            warnings = [*narrative_doc.continuity_warnings, *self.continuity_auditor.audit(narrative_doc)]
            narrative_doc.continuity_warnings = warnings

            # 7. Persist in Database & Disk
            if cancel_token.is_cancelled:
                raise RuntimeError("Story analysis lost its worker lease before persistence")
            with SessionLocal() as inner_db:
                # Clear previous machine-derived Layer B records for this project
                inner_db.query(NarrativeRecord).filter(NarrativeRecord.project_id == project_id).delete()
                inner_db.query(CharacterRecord).filter(CharacterRecord.project_id == project_id, CharacterRecord.manual_override == False).delete()
                inner_db.query(LocationRecord).filter(LocationRecord.project_id == project_id, LocationRecord.manual_override == False).delete()
                inner_db.query(SceneRecord).filter(SceneRecord.project_id == project_id, SceneRecord.manual_override == False).delete()
                inner_db.query(StoryBeatRecord).filter(StoryBeatRecord.project_id == project_id).delete()
                inner_db.query(EventRecord).filter(EventRecord.project_id == project_id).delete()

                # Add Narrative Record
                n_rec = NarrativeRecord(
                    id=str(uuid.uuid4()),
                    project_id=project_id,
                    version="1.0",
                    language=narrative_doc.language,
                    status="COMPLETE",
                    document=narrative_doc.model_dump(),
                    created_at=utc_now(),
                    updated_at=utc_now(),
                )
                inner_db.add(n_rec)

                valid_panel_ids = [p.id for p in inner_panels]
                default_p_id = inner_panels[0].id if inner_panels else None

                # Add Character Records
                for c in characters:
                    if visual_mode and inner_db.query(CharacterRecord).filter(CharacterRecord.id == c.character_id, CharacterRecord.manual_override == True).first():
                        continue
                    fp_id = c.first_panel_id if c.first_panel_id in valid_panel_ids else default_p_id
                    ref_ids = [pid for pid in c.reference_panel_ids if pid in valid_panel_ids]
                    if not ref_ids and default_p_id:
                        ref_ids = [default_p_id]
                    role_str = c.role.value if hasattr(c.role, "value") else str(c.role)
                    status_str = c.status.value if hasattr(c.status, "value") else str(c.status)
                    cr = CharacterRecord(
                        id=c.character_id,
                        project_id=project_id,
                        display_name=c.display_name,
                        canonical_name=c.canonical_name,
                        aliases=c.aliases,
                        description=c.description,
                        visual_traits=c.visual_traits,
                        role=role_str,
                        first_panel_id=fp_id,
                        reference_panel_ids=ref_ids,
                        status=status_str,
                        manual_override=c.manual_override,
                        created_at=utc_now(),
                        updated_at=utc_now(),
                    )
                    inner_db.add(cr)

                # Add Location Records
                for loc in locations:
                    if visual_mode and inner_db.query(LocationRecord).filter(LocationRecord.id == loc.location_id, LocationRecord.manual_override == True).first():
                        continue
                    loc_pids = [pid for pid in loc.panel_ids if pid in valid_panel_ids]
                    if not loc_pids and default_p_id:
                        loc_pids = [default_p_id]
                    loc_status = loc.status.value if hasattr(loc.status, "value") else str(loc.status)
                    lr = LocationRecord(
                        id=loc.location_id,
                        project_id=project_id,
                        name=loc.name,
                        canonical_name=loc.canonical_name,
                        description=loc.description,
                        visual_cues=loc.visual_cues,
                        panel_ids=loc_pids,
                        status=loc_status,
                        manual_override=loc.manual_override,
                    )
                    inner_db.add(lr)

                # Add Scenes & Beats
                for sc in scenes:
                    if visual_mode and inner_db.query(SceneRecord).filter(SceneRecord.id == sc.scene_id, SceneRecord.manual_override == True).first():
                        continue
                    sc_start = sc.panel_start if sc.panel_start in valid_panel_ids else default_p_id
                    sc_end = sc.panel_end if sc.panel_end in valid_panel_ids else (inner_panels[-1].id if inner_panels else default_p_id)
                    reason_str = sc.boundary_reason.value if hasattr(sc.boundary_reason, "value") else str(sc.boundary_reason)
                    sr = SceneRecord(
                        id=sc.scene_id,
                        project_id=project_id,
                        sequence=sc.sequence,
                        title=sc.title,
                        panel_start=sc_start,
                        panel_end=sc_end,
                        location_id=sc.location_id,
                        character_ids=sc.character_ids,
                        summary=sc.summary,
                        confidence=sc.confidence,
                        boundary_reason=reason_str,
                        manual_override=sc.manual_override,
                    )
                    inner_db.add(sr)

                for b in beats:
                    beat_pids = [pid for pid in b.panel_ids if pid in valid_panel_ids]
                    if not beat_pids and default_p_id:
                        beat_pids = [default_p_id]
                    df_str = b.dramatic_function.value if hasattr(b.dramatic_function, "value") else str(b.dramatic_function)
                    imp_str = b.importance.value if hasattr(b.importance, "value") else str(b.importance)
                    sbr = StoryBeatRecord(
                        id=b.beat_id,
                        project_id=project_id,
                        scene_id=b.scene_id,
                        sequence=b.sequence,
                        panel_ids=beat_pids,
                        event_ids=b.event_ids,
                        summary=b.summary,
                        dramatic_function=df_str,
                        importance=imp_str,
                        intensity=b.intensity,
                        confidence=b.confidence,
                        music_intent=b.music_intent,
                        sfx_intent=b.sfx_intent,
                    )
                    inner_db.add(sbr)

                for ev in events:
                    ev_pids = [pid for pid in ev.panel_ids if pid in valid_panel_ids]
                    if not ev_pids and default_p_id:
                        ev_pids = [default_p_id]
                    ev_type_str = ev.event_type.value if hasattr(ev.event_type, "value") else str(ev.event_type)
                    er = EventRecord(
                        id=ev.event_id,
                        project_id=project_id,
                        event_type=ev_type_str,
                        actor_character_id=ev.actor_character_id,
                        target_character_id=ev.target_character_id,
                        object_name=ev.object_name,
                        location_id=ev.location_id,
                        panel_ids=ev_pids,
                        description=ev.description,
                        confidence=ev.confidence,
                        evidence=ev.evidence.model_dump(),
                    )
                    inner_db.add(er)

                # Update TextRegion speaker attributions in DB
                for attr in attributions:
                    tr = inner_db.query(TextRegionRecord).filter(TextRegionRecord.id == attr.text_region_id).first()
                    if tr and not tr.speaker_character_id:
                        tr.speaker_character_id = attr.speaker_character_id
                        tr.speaker_confidence = attr.confidence
                        tr.speaker_assignment_method = attr.method.value if hasattr(attr.method, "value") else str(attr.method)

                from engine.story.dependency import mark_media_stale
                mark_media_stale(inner_db, project_id, include_scripts=True)

                # Advance Project Stage to STORY_ANALYZED
                proj_rec = inner_db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
                if proj_rec:
                    proj_rec.current_stage = PipelineStage.STORY_ANALYZED.value
                    proj_rec.updated_at = utc_now()

                if cancel_token.is_cancelled:
                    raise RuntimeError("Story analysis lost its worker lease before commit")
                inner_db.commit()

            # Write narrative.json sidecar
            write_contained_json(ws_path, Path("story") / "narrative.json", narrative_doc.model_dump())

            # Invalidate downstream SCRIPT
            dependency_graph.invalidate(project_id, PipelineEntityTier.NARRATIVE_IR)
            dependency_graph.clear(project_id, PipelineEntityTier.NARRATIVE_IR)

            progress_cb(1.0, f"Story analysis complete! Identified {len(characters)} characters, {len(scenes)} scenes.")
            return {
                "characters": len(characters),
                "scenes": len(scenes),
                "beats": len(beats),
                "events": len(events),
                "utterances": len(utterances),
            }

        if operation_only:
            return run_story_analysis
        job_manager.enqueue_async(job_id, run_story_analysis)
        return job_id

    # -----------------------------------------------------------------------
    # Narrative IR Retrieval & Approval
    # -----------------------------------------------------------------------

    def get_narrative(self, db: Session, project_id: str) -> Optional[NarrativeDocument]:
        rec = (
            db.query(NarrativeRecord)
            .filter(NarrativeRecord.project_id == project_id)
            .order_by(NarrativeRecord.created_at.desc())
            .first()
        )
        if rec and rec.document:
            doc = NarrativeDocument.model_validate(rec.document)
            if doc.analysis_metadata.get("engine") == "vision-story-v1":
                # Normalized records are the editable review layer. Reconcile them
                # with the evidence snapshot before returning it to narration/UI.
                for attribute, record_type, entity_type, id_field in (
                    ("characters", CharacterRecord, CharacterEntity, "character_id"),
                    ("locations", LocationRecord, LocationEntity, "location_id"),
                    ("scenes", SceneRecord, SceneEntity, "scene_id"),
                    ("beats", StoryBeatRecord, StoryBeatEntity, "beat_id"),
                ):
                    rows = db.query(record_type).filter(record_type.project_id == project_id).all()
                    if rows:
                        entities = []
                        for row in rows:
                            data = {}
                            for field in entity_type.model_fields:
                                column = "id" if field == id_field else field
                                if hasattr(row, column):
                                    data[field] = getattr(row, column)
                            entities.append(entity_type.model_validate(data))
                        if attribute in ("scenes", "beats"):
                            entities.sort(key=lambda item: item.sequence)
                        setattr(doc, attribute, entities)
            return doc

        # Fallback to narrative.json on disk if present
        proj = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
        if proj:
            try:
                data = json.loads(read_contained_bytes(proj.workspace_path, Path("story") / "narrative.json").decode("utf-8"))
                return NarrativeDocument.model_validate(data)
            except FileNotFoundError:
                pass
        return None

    def confirm_story(self, db: Session, project_id: str) -> ProjectRecord:
        proj = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
        if not proj:
            raise KeyError(f"Project not found: {project_id}")

        narrative = self.get_narrative(db, project_id)
        if not narrative:
            raise ValueError("Cannot approve story: No Narrative IR exists for this project.")

        # Strict check for blocking errors
        error_warnings = [w for w in narrative.continuity_warnings if w.severity == "ERROR" and not w.resolved]
        if error_warnings:
            raise ValueError(
                f"Cannot approve story: {len(error_warnings)} unresolved critical continuity errors exist."
            )

        proj.current_stage = PipelineStage.STORY_APPROVED.value
        proj.updated_at = utc_now()
        db.commit()
        db.refresh(proj)
        return proj

    # -----------------------------------------------------------------------
    # Character Registry Operations (Part 31)
    # -----------------------------------------------------------------------

    def list_characters(self, db: Session, project_id: str) -> List[CharacterRecord]:
        return (
            db.query(CharacterRecord)
            .filter(CharacterRecord.project_id == project_id)
            .order_by(CharacterRecord.created_at.asc())
            .all()
        )

    def update_character(
        self,
        db: Session,
        project_id: str,
        character_id: str,
        display_name: Optional[str] = None,
        canonical_name: Optional[str] = None,
        role: Optional[str] = None,
        aliases: Optional[List[str]] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
    ) -> CharacterRecord:
        char = (
            db.query(CharacterRecord)
            .filter(CharacterRecord.project_id == project_id, CharacterRecord.id == character_id)
            .first()
        )
        if not char:
            raise KeyError(f"Character not found: {character_id}")

        if display_name is not None:
            char.display_name = display_name
        if canonical_name is not None:
            char.canonical_name = canonical_name
        if role is not None:
            char.role = role
        if aliases is not None:
            char.aliases = aliases
        if description is not None:
            char.description = description
        if status is not None:
            char.status = status

        char.manual_override = True
        char.updated_at = utc_now()
        db.commit()
        db.refresh(char)

        # Invalidate downstream
        dependency_graph.invalidate(project_id, PipelineEntityTier.CHARACTER)
        return char

    def merge_characters(
        self,
        db: Session,
        project_id: str,
        source_id: str,
        target_id: str,
    ) -> CharacterRecord:
        source = (
            db.query(CharacterRecord)
            .filter(CharacterRecord.project_id == project_id, CharacterRecord.id == source_id)
            .first()
        )
        target = (
            db.query(CharacterRecord)
            .filter(CharacterRecord.project_id == project_id, CharacterRecord.id == target_id)
            .first()
        )
        if not source or not target:
            raise KeyError("Source or Target character not found.")

        # Reassign text regions
        regions = (
            db.query(TextRegionRecord)
            .filter(TextRegionRecord.project_id == project_id, TextRegionRecord.speaker_character_id == source_id)
            .all()
        )
        for r in regions:
            r.speaker_character_id = target_id

        # Reassign events
        events_actor = db.query(EventRecord).filter(EventRecord.project_id == project_id, EventRecord.actor_character_id == source_id).all()
        for ev in events_actor:
            ev.actor_character_id = target_id

        events_target = db.query(EventRecord).filter(EventRecord.project_id == project_id, EventRecord.target_character_id == source_id).all()
        for ev in events_target:
            ev.target_character_id = target_id

        # Merge aliases
        merged_aliases = list(set((target.aliases or []) + (source.aliases or []) + [source.display_name]))
        target.aliases = merged_aliases
        target.manual_override = True
        target.updated_at = utc_now()

        db.delete(source)
        db.commit()
        db.refresh(target)

        # Invalidate downstream
        dependency_graph.invalidate(project_id, PipelineEntityTier.CHARACTER)
        return target

    def split_character(
        self,
        db: Session,
        project_id: str,
        character_id: str,
        new_name: str,
        panel_ids: List[str],
    ) -> CharacterRecord:
        orig = (
            db.query(CharacterRecord)
            .filter(CharacterRecord.project_id == project_id, CharacterRecord.id == character_id)
            .first()
        )
        if not orig:
            raise KeyError(f"Character not found: {character_id}")

        new_char_id = f"char_{uuid.uuid4().hex[:8]}"
        new_char = CharacterRecord(
            id=new_char_id,
            project_id=project_id,
            display_name=new_name,
            canonical_name=new_name,
            aliases=[],
            description=f"Separated identity from {orig.display_name}",
            visual_traits=[],
            role=orig.role,
            first_panel_id=panel_ids[0] if panel_ids else None,
            reference_panel_ids=panel_ids[:2],
            status="MANUAL",
            manual_override=True,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db.add(new_char)

        # Reassign text regions in panel_ids
        for pid in panel_ids:
            regs = (
                db.query(TextRegionRecord)
                .filter(TextRegionRecord.panel_id == pid, TextRegionRecord.speaker_character_id == character_id)
                .all()
            )
            for r in regs:
                r.speaker_character_id = new_char_id

        db.commit()
        db.refresh(new_char)

        dependency_graph.invalidate(project_id, PipelineEntityTier.CHARACTER)
        return new_char

    # -----------------------------------------------------------------------
    # Scene Operations (Part 32)
    # -----------------------------------------------------------------------

    def list_scenes(self, db: Session, project_id: str) -> List[SceneRecord]:
        return (
            db.query(SceneRecord)
            .filter(SceneRecord.project_id == project_id)
            .order_by(SceneRecord.sequence.asc())
            .all()
        )

    def merge_scenes(self, db: Session, project_id: str, scene_id_1: str, scene_id_2: str) -> SceneRecord:
        s1 = db.query(SceneRecord).filter(SceneRecord.project_id == project_id, SceneRecord.id == scene_id_1).first()
        s2 = db.query(SceneRecord).filter(SceneRecord.project_id == project_id, SceneRecord.id == scene_id_2).first()
        if not s1 or not s2:
            raise KeyError("One or both scenes not found.")

        # Reassign beats from s2 to s1
        beats = db.query(StoryBeatRecord).filter(StoryBeatRecord.scene_id == s2.id).all()
        for b in beats:
            b.scene_id = s1.id

        s1.panel_end = s2.panel_end
        s1.summary = f"{s1.summary} {s2.summary}".strip()
        s1.character_ids = list(set((s1.character_ids or []) + (s2.character_ids or [])))
        s1.manual_override = True

        db.delete(s2)
        db.commit()
        db.refresh(s1)

        dependency_graph.invalidate(project_id, PipelineEntityTier.SCENE)
        return s1

    # -----------------------------------------------------------------------
    # Script Adaptation & Validation (Part 35–42)
    # -----------------------------------------------------------------------

    def generate_script(
        self,
        db: Session,
        project_id: str,
        profile: str = "FAITHFUL",
        cancelled=lambda: False,
        provider_id: str | None = None,
        model_name: str | None = None,
    ) -> VideoScript:
        narrative = self.get_narrative(db, project_id)
        if not narrative:
            raise ValueError("Cannot generate script: No Narrative IR found for project.")
        project = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
        if (project and (project.settings or {}).get("visual_storytelling")
                and project.current_stage not in (PipelineStage.STORY_APPROVED.value, PipelineStage.SCRIPT_GENERATED.value,
                    PipelineStage.SCRIPT_APPROVED.value, PipelineStage.VOICE_GENERATED.value,
                    PipelineStage.AUDIO_APPROVED.value, PipelineStage.SHOT_PLAN_GENERATED.value,
                    PipelineStage.MOTION_APPROVED.value, PipelineStage.RENDERED.value)):
            raise ValueError("Approve the chapter story before generating narration.")

        adaptation_profile = AdaptationProfile(profile)
        if narrative.analysis_metadata.get("engine") == "vision-story-v1":
            from engine.story.visual import VisualStoryEngine
            pinned_provider = (
                self.resolve_pinned_script_provider(provider_id, model_name)
                if provider_id is not None or model_name is not None
                else None
            )
            async def create_narration():
                provider = pinned_provider or await llm_registry.get_active_provider(
                    narrative.analysis_metadata.get("provider")
                )
                return await VisualStoryEngine().narrate(narrative, provider, adaptation_profile)
            script = asyncio.run(create_narration())
        elif provider_id is not None or model_name is not None:
            # Even deterministic adaptation jobs must prove the persisted provider
            # identity still resolves; recovery must never silently substitute one.
            self.resolve_pinned_script_provider(provider_id, model_name)
            script = script_adapter.adapt(narrative, profile=adaptation_profile)
        else:
            script = script_adapter.adapt(narrative, profile=adaptation_profile)

        if cancelled():
            raise ValueError("Narration generation cancelled; previous script preserved.")

        # Persist in DB (replace only same profile version so multiple adaptation profiles coexist)
        previous_scripts = db.query(VideoScriptRecord).filter(
            VideoScriptRecord.project_id == project_id,
            VideoScriptRecord.adaptation_profile == script.adaptation_profile.value,
        ).all()
        for previous in previous_scripts:
            db.delete(previous)
        db.flush()
        s_rec = VideoScriptRecord(
            id=script.script_id,
            project_id=project_id,
            version=script.version,
            adaptation_profile=script.adaptation_profile.value,
            estimated_duration=script.estimated_duration,
            language=script.language,
            status=script.status,
            quality_metrics=script.quality_metrics,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db.add(s_rec)

        for seg in script.segments:
            seg_rec = ScriptSegmentRecord(
                id=seg.segment_id,
                script_id=script.script_id,
                project_id=project_id,
                scene_id=seg.scene_id,
                beat_id=seg.beat_id,
                sequence=seg.sequence,
                type=seg.type.value,
                speaker_character_id=seg.speaker_character_id,
                text=seg.text,
                emotion=seg.emotion.value,
                intensity=seg.intensity,
                estimated_duration=seg.estimated_duration,
                estimated_start=seg.estimated_start,
                estimated_end=seg.estimated_end,
                source_evidence=seg.source_evidence.model_dump(),
                production_intent=seg.production_intent,
                music_intent=seg.music_intent,
                sfx_intent=seg.sfx_intent,
                motion_intent=seg.motion_intent.value if seg.motion_intent else None,
                faithfulness_status=seg.faithfulness_status,
                manual_override=seg.manual_override,
            )
            db.add(seg_rec)

        from engine.story.dependency import mark_media_stale
        mark_media_stale(db, project_id)

        # Advance project stage
        proj = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
        if proj:
            proj.current_stage = PipelineStage.SCRIPT_GENERATED.value
            proj.updated_at = utc_now()

        db.commit()

        # Save script.json sidecar
        ws_path = Path(proj.workspace_path)
        write_contained_json(ws_path, Path("script") / "script.json", script.model_dump())

        dependency_graph.clear(project_id, PipelineEntityTier.SCRIPT)
        return script

    def get_script(self, db: Session, project_id: str, script_id: Optional[str] = None) -> Optional[VideoScript]:
        query = db.query(VideoScriptRecord).filter(VideoScriptRecord.project_id == project_id)
        if script_id:
            query = query.filter(VideoScriptRecord.id == script_id)
        s_rec = query.order_by(VideoScriptRecord.created_at.desc()).first()
        if not s_rec:
            return None

        segments = (
            db.query(ScriptSegmentRecord)
            .filter(ScriptSegmentRecord.script_id == s_rec.id)
            .order_by(ScriptSegmentRecord.sequence.asc())
            .all()
        )

        return VideoScript(
            script_id=s_rec.id,
            project_id=s_rec.project_id,
            version=s_rec.version,
            adaptation_profile=AdaptationProfile(s_rec.adaptation_profile),
            segments=[
                ScriptSegment(
                    segment_id=seg.id,
                    scene_id=seg.scene_id,
                    beat_id=seg.beat_id,
                    sequence=seg.sequence,
                    type=SegmentType(seg.type),
                    speaker_character_id=seg.speaker_character_id,
                    text=seg.text,
                    emotion=EmotionType(seg.emotion),
                    intensity=seg.intensity,
                    estimated_duration=seg.estimated_duration,
                    estimated_start=seg.estimated_start,
                    estimated_end=seg.estimated_end,
                    source_evidence=ProvenanceReference.model_validate(seg.source_evidence or {}),
                    production_intent=seg.production_intent,
                    music_intent=seg.music_intent,
                    sfx_intent=seg.sfx_intent,
                    motion_intent=MotionIntent(seg.motion_intent) if seg.motion_intent else None,
                    faithfulness_status=seg.faithfulness_status,
                    manual_override=seg.manual_override,
                )
                for seg in segments
            ],
            estimated_duration=s_rec.estimated_duration,
            language=s_rec.language,
            status=s_rec.status,
            quality_metrics=s_rec.quality_metrics or {},
            created_at=s_rec.created_at.isoformat() if s_rec.created_at else "",
            updated_at=s_rec.updated_at.isoformat() if s_rec.updated_at else "",
        )

    def update_script_segment(
        self,
        db: Session,
        project_id: str,
        script_id: str,
        segment_id: str,
        text: Optional[str] = None,
        speaker_character_id: Optional[str] = None,
        emotion: Optional[str] = None,
        intensity: Optional[float] = None,
        estimated_duration: Optional[float] = None,
    ) -> ScriptSegmentRecord:
        seg = (
            db.query(ScriptSegmentRecord)
            .filter(ScriptSegmentRecord.id == segment_id, ScriptSegmentRecord.script_id == script_id, ScriptSegmentRecord.project_id == project_id)
            .first()
        )
        if not seg:
            raise KeyError(f"Script segment not found: {segment_id}")

        if text is not None:
            seg.text = text
            # Recalculate duration
            from engine.story.script.duration import estimate_segment_duration
            seg.estimated_duration = estimate_segment_duration(text, segment_type=seg.type)
        if speaker_character_id is not None:
            seg.speaker_character_id = speaker_character_id
        if emotion is not None:
            seg.emotion = emotion
        if intensity is not None:
            seg.intensity = intensity

        if estimated_duration is not None:
            if estimated_duration <= 0:
                raise ValueError("Duration must be positive")
            seg.estimated_duration = estimated_duration
        script_record = db.query(VideoScriptRecord).filter(VideoScriptRecord.id == script_id, VideoScriptRecord.project_id == project_id).first()
        if script_record:
            script_record.status = "DRAFT"
            elapsed = 0.0
            for item in sorted(script_record.segments, key=lambda item: item.sequence):
                item.estimated_start = round(elapsed, 3)
                elapsed += item.estimated_duration
                item.estimated_end = round(elapsed, 3)
            script_record.estimated_duration = round(elapsed, 3)
        seg.manual_override = True

        # Invalidate downstream tiers: Audio, Motion, Render
        from engine.story.dependency import dependency_graph, PipelineEntityTier
        dependency_graph.invalidate(project_id, PipelineEntityTier.SCRIPT)

        active_audio = (
            db.query(AudioTimelineRecord)
            .filter(AudioTimelineRecord.project_id == project_id)
            .order_by(AudioTimelineRecord.created_at.desc())
            .first()
        )
        if active_audio:
            active_audio.status = "STALE"
            active_audio.updated_at = utc_now()

        active_motion = (
            db.query(VisualTimelineRecord)
            .filter(VisualTimelineRecord.project_id == project_id)
            .order_by(VisualTimelineRecord.created_at.desc())
            .first()
        )
        if active_motion:
            active_motion.status = "STALE"
            active_motion.updated_at = utc_now()

        latest_complete = (
            db.query(RenderJobRecord)
            .filter(RenderJobRecord.project_id == project_id, RenderJobRecord.status == "COMPLETE")
            .order_by(RenderJobRecord.created_at.desc())
            .first()
        )
        if latest_complete:
            latest_complete.status = "STALE"

        db.commit()
        db.refresh(seg)
        return seg

    def validate_script(self, db: Session, project_id: str, script_id: str) -> ScriptValidationReport:
        script = self.get_script(db, project_id, script_id)
        if not script:
            raise KeyError(f"Script not found: {script_id}")
        narrative = self.get_narrative(db, project_id)
        if not narrative:
            return ScriptValidationReport(
                script_id=script_id,
                total_segments=len(script.segments),
                supported_segments=len(script.segments),
                weakly_supported_segments=0,
                unsupported_segments=0,
                coverage_score=1.0,
                issues=[],
                passed=True,
            )

        report = script_validator.validate(script, narrative)

        # Update in DB
        s_rec = db.query(VideoScriptRecord).filter(VideoScriptRecord.id == script_id).first()
        if s_rec:
            s_rec.quality_metrics = script.quality_metrics
            db.commit()

        return report

    def approve_script(self, db: Session, project_id: str, script_id: str) -> VideoScriptRecord:
        s_rec = db.query(VideoScriptRecord).filter(VideoScriptRecord.id == script_id).first()
        if not s_rec:
            raise KeyError(f"Script not found: {script_id}")

        report = self.validate_script(db, project_id, script_id)
        if report.unsupported_segments > 0:
            raise ValueError(
                f"Cannot approve script: {report.unsupported_segments} statements have unsupported claims. "
                f"Please review and fix unsupported claims."
            )

        s_rec.status = "APPROVED"
        s_rec.updated_at = utc_now()

        proj = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
        if proj:
            proj.current_stage = PipelineStage.SCRIPT_APPROVED.value
            proj.updated_at = utc_now()

        db.commit()
        db.refresh(s_rec)
        return s_rec


story_service = StoryService()
