from typing import List, Optional
from pydantic import BaseModel, Field

from engine.story.models import (
    CharacterRole,
    CharacterStatus,
    EventType,
    BoundaryReason,
    DramaticFunction,
    ImportanceLevel,
)


class DiscoveredCharacter(BaseModel):
    name: str = Field(..., description="Character name or descriptive label if name is unknown")
    canonical_name: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)
    description: str = Field(..., description="Physical visual description or role")
    role: CharacterRole = CharacterRole.SUPPORTING
    first_panel_id: Optional[str] = None
    status: CharacterStatus = CharacterStatus.LIKELY


class DiscoveredLocation(BaseModel):
    name: str
    description: str
    panel_ids: List[str] = Field(default_factory=list)


class CharacterDiscoveryResponse(BaseModel):
    characters: List[DiscoveredCharacter]
    locations: List[DiscoveredLocation]


class SpeakerAttributionItem(BaseModel):
    text_region_id: str
    speaker_name: str
    confidence: float = Field(0.85, ge=0.0, le=1.0)
    reason_code: str = Field(..., description="Short reason e.g. CONVERSATIONAL_CONTEXT, EXPLICIT_NAME, NARRATION_BOX, UNKNOWN")


class SpeakerResolutionResponse(BaseModel):
    attributions: List[SpeakerAttributionItem]


class ExtractedEventItem(BaseModel):
    event_type: EventType = EventType.OTHER
    actor_name: str
    target_name: Optional[str] = None
    object_name: Optional[str] = None
    panel_id: str
    description: str
    confidence: float = Field(0.9, ge=0.0, le=1.0)


class EventExtractionResponse(BaseModel):
    events: List[ExtractedEventItem]


class DiscoveredScene(BaseModel):
    title: str
    panel_start: str
    panel_end: str
    summary: str
    boundary_reason: BoundaryReason = BoundaryReason.NARRATIVE_SHIFT
    confidence: float = Field(0.9, ge=0.0, le=1.0)


class DiscoveredBeat(BaseModel):
    scene_index: int = Field(1, description="1-based index of the parent scene")
    panel_ids: List[str] = Field(default_factory=list)
    summary: str
    dramatic_function: DramaticFunction = DramaticFunction.SETUP
    importance: ImportanceLevel = ImportanceLevel.MEDIUM
    intensity: float = Field(0.5, ge=0.0, le=1.0)
    music_intent: str = "MYSTERIOUS"
    sfx_intent: str = "NONE"


class SceneSegmentationResponse(BaseModel):
    scenes: List[DiscoveredScene]
    beats: List[DiscoveredBeat]
