from enum import Enum
from typing import Set, Dict, List
import logging

logger = logging.getLogger("panelflow.story.dependency")


def mark_media_stale(db, project_id, include_audio=True, include_scripts=False):
    """Persist invalidation so approvals cannot survive engine restarts."""
    from engine.database.models import AudioTimelineRecord, VisualTimelineRecord, RenderJobRecord, VideoScriptRecord
    if include_scripts:
        db.query(VideoScriptRecord).filter(VideoScriptRecord.project_id == project_id).update({"status": "STALE"}, synchronize_session="fetch")
    if include_audio:
        db.query(AudioTimelineRecord).filter(AudioTimelineRecord.project_id == project_id).update({"status": "STALE"}, synchronize_session="fetch")
    db.query(VisualTimelineRecord).filter(VisualTimelineRecord.project_id == project_id).update({"status": "STALE"}, synchronize_session="fetch")
    db.query(RenderJobRecord).filter(RenderJobRecord.project_id == project_id, RenderJobRecord.status == "COMPLETE").update({"status": "STALE"}, synchronize_session="fetch")

class PipelineEntityTier(str, Enum):
    PAGE = "PAGE"
    PANEL = "PANEL"
    TEXT_REGION = "TEXT_REGION"
    OCR = "OCR"
    UTTERANCE = "UTTERANCE"
    SPEAKER = "SPEAKER"
    CHARACTER = "CHARACTER"
    EVENT = "EVENT"
    BEAT = "BEAT"
    SCENE = "SCENE"
    NARRATIVE_IR = "NARRATIVE_IR"
    SCRIPT = "SCRIPT"


class DependencyGraph:
    """
    Lightweight in-memory and persistent dependency tracking.
    When upstream entities (e.g. OCR text, panel order, speaker assignment) are modified,
    calculates affected downstream tiers and marks them STALE.
    """

    # Downstream cascade graph
    DOWNSTREAM_CASCADE = {
        PipelineEntityTier.PAGE: {PipelineEntityTier.PANEL, PipelineEntityTier.NARRATIVE_IR, PipelineEntityTier.SCRIPT},
        PipelineEntityTier.PANEL: {PipelineEntityTier.TEXT_REGION, PipelineEntityTier.EVENT, PipelineEntityTier.BEAT, PipelineEntityTier.SCENE, PipelineEntityTier.NARRATIVE_IR, PipelineEntityTier.SCRIPT},
        PipelineEntityTier.TEXT_REGION: {PipelineEntityTier.OCR, PipelineEntityTier.UTTERANCE, PipelineEntityTier.SPEAKER, PipelineEntityTier.NARRATIVE_IR, PipelineEntityTier.SCRIPT},
        PipelineEntityTier.OCR: {PipelineEntityTier.UTTERANCE, PipelineEntityTier.EVENT, PipelineEntityTier.NARRATIVE_IR, PipelineEntityTier.SCRIPT},
        PipelineEntityTier.UTTERANCE: {PipelineEntityTier.EVENT, PipelineEntityTier.BEAT, PipelineEntityTier.NARRATIVE_IR, PipelineEntityTier.SCRIPT},
        PipelineEntityTier.SPEAKER: {PipelineEntityTier.UTTERANCE, PipelineEntityTier.EVENT, PipelineEntityTier.SCRIPT},
        PipelineEntityTier.CHARACTER: {PipelineEntityTier.SPEAKER, PipelineEntityTier.UTTERANCE, PipelineEntityTier.EVENT, PipelineEntityTier.SCRIPT},
        PipelineEntityTier.EVENT: {PipelineEntityTier.BEAT, PipelineEntityTier.SCENE, PipelineEntityTier.NARRATIVE_IR, PipelineEntityTier.SCRIPT},
        PipelineEntityTier.BEAT: {PipelineEntityTier.SCENE, PipelineEntityTier.SCRIPT},
        PipelineEntityTier.SCENE: {PipelineEntityTier.NARRATIVE_IR, PipelineEntityTier.SCRIPT},
        PipelineEntityTier.NARRATIVE_IR: {PipelineEntityTier.SCRIPT},
        PipelineEntityTier.SCRIPT: set(),
    }

    def __init__(self):
        # project_id -> set of stale tiers
        self._stale_tiers_by_project: Dict[str, Set[PipelineEntityTier]] = {}

    def invalidate(self, project_id: str, modified_tier: PipelineEntityTier) -> Set[PipelineEntityTier]:
        """
        Marks modified_tier and all downstream dependencies as STALE for the given project.
        Returns the set of invalidated downstream tiers.
        """
        invalidated: Set[PipelineEntityTier] = {modified_tier}
        to_process = [modified_tier]

        while to_process:
            curr = to_process.pop(0)
            children = self.DOWNSTREAM_CASCADE.get(curr, set())
            for child in children:
                if child not in invalidated:
                    invalidated.add(child)
                    to_process.append(child)

        if project_id not in self._stale_tiers_by_project:
            self._stale_tiers_by_project[project_id] = set()

        self._stale_tiers_by_project[project_id].update(invalidated)
        logger.info(f"Invalidated downstream tiers for project {project_id}: {[t.value for t in invalidated]}")
        return invalidated

    def clear(self, project_id: str, tier: PipelineEntityTier) -> None:
        """Clears stale status when a tier is regenerated or confirmed."""
        if project_id in self._stale_tiers_by_project:
            self._stale_tiers_by_project[project_id].discard(tier)

    def is_stale(self, project_id: str, tier: PipelineEntityTier) -> bool:
        """Returns True if the specified tier is currently out of date."""
        return tier in self._stale_tiers_by_project.get(project_id, set())

    def get_stale_tiers(self, project_id: str) -> List[str]:
        return [t.value for t in self._stale_tiers_by_project.get(project_id, set())]


dependency_graph = DependencyGraph()
