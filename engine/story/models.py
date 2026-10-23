from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, Dict, Any, Literal
from pydantic import ConfigDict, StrictBool, StrictStr, model_validator
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Controlled Enums
# ---------------------------------------------------------------------------

class CharacterRole(str, Enum):
    UNKNOWN = "UNKNOWN"
    PROTAGONIST = "PROTAGONIST"
    ANTAGONIST = "ANTAGONIST"
    SUPPORTING = "SUPPORTING"
    MINOR = "MINOR"


class CharacterStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    LIKELY = "LIKELY"
    UNCERTAIN = "UNCERTAIN"
    MANUAL = "MANUAL"


class SpeakerMethod(str, Enum):
    MANUAL = "MANUAL"
    BALLOON_GEOMETRY = "BALLOON_GEOMETRY"
    VISION = "VISION"
    LLM = "LLM"
    COMBINED = "COMBINED"
    UNKNOWN = "UNKNOWN"


class UtteranceType(str, Enum):
    DIALOGUE = "DIALOGUE"
    THOUGHT = "THOUGHT"
    NARRATION = "NARRATION"
    SFX = "SFX"
    CAPTION = "CAPTION"


class EmotionType(str, Enum):
    NEUTRAL = "NEUTRAL"
    HAPPY = "HAPPY"
    SAD = "SAD"
    ANGRY = "ANGRY"
    AFRAID = "AFRAID"
    SURPRISED = "SURPRISED"
    DISGUSTED = "DISGUSTED"
    CONFUSED = "CONFUSED"
    DETERMINED = "DETERMINED"
    EXCITED = "EXCITED"
    CALM = "CALM"
    TENSE = "TENSE"
    GRIEVING = "GRIEVING"
    SARCASTIC = "SARCASTIC"
    UNKNOWN = "UNKNOWN"


class EventType(str, Enum):
    MOVE = "MOVE"
    ENTER = "ENTER"
    EXIT = "EXIT"
    SPEAK = "SPEAK"
    ATTACK = "ATTACK"
    DEFEND = "DEFEND"
    DISCOVER = "DISCOVER"
    REVEAL = "REVEAL"
    TRANSFORM = "TRANSFORM"
    GIVE = "GIVE"
    TAKE = "TAKE"
    OPEN = "OPEN"
    CLOSE = "CLOSE"
    FALL = "FALL"
    JUMP = "JUMP"
    RUN = "RUN"
    CHASE = "CHASE"
    REACTION = "REACTION"
    LOCATION_CHANGE = "LOCATION_CHANGE"
    TIME_CHANGE = "TIME_CHANGE"
    OTHER = "OTHER"


class RelationshipType(str, Enum):
    ALLY = "ALLY"
    ENEMY = "ENEMY"
    FAMILY = "FAMILY"
    FRIEND = "FRIEND"
    RIVAL = "RIVAL"
    COMMANDER = "COMMANDER"
    SUBORDINATE = "SUBORDINATE"
    UNKNOWN = "UNKNOWN"


class BoundaryReason(str, Enum):
    LOCATION_CHANGE = "LOCATION_CHANGE"
    TIME_CHANGE = "TIME_CHANGE"
    NARRATIVE_SHIFT = "NARRATIVE_SHIFT"
    CHAPTER_BOUNDARY = "CHAPTER_BOUNDARY"
    MANUAL = "MANUAL"
    UNKNOWN = "UNKNOWN"


class DramaticFunction(str, Enum):
    INTRODUCTION = "INTRODUCTION"
    SETUP = "SETUP"
    DISCOVERY = "DISCOVERY"
    CONFLICT = "CONFLICT"
    ESCALATION = "ESCALATION"
    REVELATION = "REVELATION"
    REVERSAL = "REVERSAL"
    CLIMAX = "CLIMAX"
    REACTION = "REACTION"
    RESOLUTION = "RESOLUTION"
    TRANSITION = "TRANSITION"
    UNKNOWN = "UNKNOWN"


class ImportanceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class AdaptationProfile(str, Enum):
    FAITHFUL = "FAITHFUL"
    CONDENSED = "CONDENSED"
    DRAMATIC_NARRATION = "DRAMATIC_NARRATION"
    ACCESSIBLE_RECAP = "ACCESSIBLE_RECAP"


class SegmentType(str, Enum):
    NARRATOR = "NARRATOR"
    CHARACTER_DIALOGUE = "CHARACTER_DIALOGUE"
    SFX_CUE = "SFX_CUE"
    PAUSE = "PAUSE"
    TRANSITION = "TRANSITION"


class MotionIntent(str, Enum):
    ESTABLISHING = "ESTABLISHING"
    CHARACTER_FOCUS = "CHARACTER_FOCUS"
    REACTION_CLOSEUP = "REACTION_CLOSEUP"
    SLOW_PUSH = "SLOW_PUSH"
    IMPACT = "IMPACT"
    REVEAL = "REVEAL"
    PAN = "PAN"
    STATIC = "STATIC"


class AnalysisStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    FAILED = "FAILED"
    STALE = "STALE"
    MANUALLY_CONFIRMED = "MANUALLY_CONFIRMED"


# ---------------------------------------------------------------------------
# Core Narrative Domain Models
# ---------------------------------------------------------------------------

class ProvenanceReference(BaseModel):
    panel_ids: List[str] = Field(default_factory=list)
    text_region_ids: List[str] = Field(default_factory=list)
    confidence: float = 1.0


class PanelObservationEntity(BaseModel):
    panel_id: str
    sequence_global: int
    visible_character_candidates: List[str] = Field(default_factory=list)
    visible_objects: List[str] = Field(default_factory=list)
    location_hints: List[str] = Field(default_factory=list)
    actions: List[str] = Field(default_factory=list)
    facial_emotions: List[str] = Field(default_factory=list)
    visual_intensity: float = 0.5
    visual_summary: str = ""
    evidence_confidence: float = 0.9


class CharacterEntity(BaseModel):
    character_id: str
    display_name: str
    canonical_name: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)
    description: str = ""
    visual_traits: List[str] = Field(default_factory=list)
    role: CharacterRole = CharacterRole.UNKNOWN
    first_panel_id: Optional[str] = None
    reference_panel_ids: List[str] = Field(default_factory=list)
    status: CharacterStatus = CharacterStatus.LIKELY
    manual_override: bool = False


class LocationEntity(BaseModel):
    location_id: str
    name: str
    canonical_name: Optional[str] = None
    description: str = ""
    visual_cues: List[str] = Field(default_factory=list)
    panel_ids: List[str] = Field(default_factory=list)
    status: CharacterStatus = CharacterStatus.LIKELY
    manual_override: bool = False


class SpeakerAttributionEntity(BaseModel):
    text_region_id: str
    speaker_character_id: str
    confidence: float = 0.8
    method: SpeakerMethod = SpeakerMethod.LLM
    evidence_panel_ids: List[str] = Field(default_factory=list)
    reason_code: str = "LLM_INFERENCE"


class UtteranceEntity(BaseModel):
    utterance_id: str
    text_region_id: str
    panel_id: str
    speaker_character_id: Optional[str] = None
    source_text: str = ""
    corrected_text: str = ""
    utterance_type: UtteranceType = UtteranceType.DIALOGUE
    emotion: EmotionType = EmotionType.NEUTRAL
    emotion_confidence: float = 0.8
    intensity: float = 0.5
    valence: float = 0.0   # [-1.0, 1.0]
    arousal: float = 0.5   # [0.0, 1.0]
    sequence: int = 1
    provenance: ProvenanceReference = Field(default_factory=ProvenanceReference)


class StateApproval(BaseModel):
    """A recorded creator decision, never inferred from model confidence.

    Frozen records must be replaced with a new decision rather than edited.
    This data contract is not an authentication boundary; API callers still
    need to authorize the creator before accepting an APPROVED decision.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")
    status: Literal["PENDING", "APPROVED", "REJECTED"] = "PENDING"
    approved_by: Optional[str] = None


class StateValue(BaseModel):
    """Absent knowledge is explicit; known None means no owner/location."""
    model_config = ConfigDict(extra="forbid")
    known: StrictBool = False
    value: StrictStr | StrictBool | None = None

    @model_validator(mode="after")
    def reject_unknown_value(self):
        if not self.known and self.value is not None:
            raise ValueError("An unknown state value cannot contain a fact")
        return self


class StateChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    domain: Literal["POSSESSION", "LOCATION", "KNOWLEDGE"]
    subject_id: str = Field(min_length=1)
    fact_id: Optional[str] = None
    before: StateValue
    after: StateValue
    evidence: ProvenanceReference = Field(default_factory=ProvenanceReference)
    approval: StateApproval = Field(default_factory=StateApproval)

    @model_validator(mode="after")
    def validate_domain_values(self):
        if self.domain == "KNOWLEDGE":
            if not self.fact_id or not self.fact_id.strip():
                raise ValueError("Knowledge changes require a fact_id")
            if any(v.known and type(v.value) is not bool for v in (self.before, self.after)):
                raise ValueError("Known knowledge values must be boolean")
        else:
            if self.fact_id is not None:
                raise ValueError("Only knowledge changes have a fact_id")
            if any(v.known and v.value is not None and type(v.value) is not str for v in (self.before, self.after)):
                raise ValueError("Possession and location values must be IDs or explicit None")
        return self


class WorldState(BaseModel):
    """Version 1 canonical facts. Missing keys mean unknown, never false/None.

    Possessions map object IDs to owner character IDs (None = unowned).
    Locations map character IDs to location IDs (None = explicitly nowhere).
    Knowledge maps character IDs and proposition IDs to established truth.
    """
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"] = "1.0"
    possessions: Dict[str, Optional[StrictStr]] = Field(default_factory=dict)
    locations: Dict[str, Optional[StrictStr]] = Field(default_factory=dict)
    knowledge: Dict[str, Dict[str, StrictBool]] = Field(default_factory=dict)
    evidence: ProvenanceReference = Field(default_factory=ProvenanceReference)
    approval: StateApproval = Field(default_factory=StateApproval)


class EventEntity(BaseModel):
    event_id: str
    event_type: EventType = EventType.OTHER
    actor_character_id: Optional[str] = None
    target_character_id: Optional[str] = None
    object_name: Optional[str] = None
    location_id: Optional[str] = None
    panel_ids: List[str] = Field(default_factory=list)
    description: str = ""
    confidence: float = 0.85
    evidence: ProvenanceReference = Field(default_factory=ProvenanceReference)
    state_changes: List[StateChange] = Field(default_factory=list)
    caused_by: List[str] = Field(default_factory=list)
    enables: List[str] = Field(default_factory=list)


class CharacterRelationshipEntity(BaseModel):
    character_a_id: str
    character_b_id: str
    relation_type: RelationshipType = RelationshipType.UNKNOWN
    description: str = ""
    evidence_panel_ids: List[str] = Field(default_factory=list)
    confidence: float = 0.8


class StoryBeatEntity(BaseModel):
    beat_id: str
    scene_id: str
    sequence: int
    panel_ids: List[str] = Field(default_factory=list)
    event_ids: List[str] = Field(default_factory=list)
    summary: str = ""
    dramatic_function: DramaticFunction = DramaticFunction.UNKNOWN
    importance: ImportanceLevel = ImportanceLevel.MEDIUM
    intensity: float = 0.5
    confidence: float = 0.85
    music_intent: Optional[str] = None
    sfx_intent: Optional[str] = None


class SceneEntity(BaseModel):
    scene_id: str
    sequence: int
    title: str = ""
    panel_start: str
    panel_end: str
    location_id: Optional[str] = None
    character_ids: List[str] = Field(default_factory=list)
    summary: str = ""
    confidence: float = 0.85
    boundary_reason: BoundaryReason = BoundaryReason.UNKNOWN
    manual_override: bool = False


class ContinuityWarningEntity(BaseModel):
    warning_id: str
    warning_type: str
    severity: str = "WARNING"  # ERROR, WARNING, INFO
    description: str
    affected_panel_ids: List[str] = Field(default_factory=list)
    affected_character_ids: List[str] = Field(default_factory=list)
    resolved: bool = False


class NarrativeDocument(BaseModel):
    project_id: str
    version: str = "1.0"
    language: str = "en"
    characters: List[CharacterEntity] = Field(default_factory=list)
    locations: List[LocationEntity] = Field(default_factory=list)
    scenes: List[SceneEntity] = Field(default_factory=list)
    beats: List[StoryBeatEntity] = Field(default_factory=list)
    events: List[EventEntity] = Field(default_factory=list)
    initial_world_state: WorldState = Field(default_factory=WorldState)
    utterances: List[UtteranceEntity] = Field(default_factory=list)
    speaker_attributions: List[SpeakerAttributionEntity] = Field(default_factory=list)
    observations: List[PanelObservationEntity] = Field(default_factory=list)
    relationships: List[CharacterRelationshipEntity] = Field(default_factory=list)
    continuity_warnings: List[ContinuityWarningEntity] = Field(default_factory=list)
    analysis_metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# Video Script Adaptation Models (Layer C)
# ---------------------------------------------------------------------------

class ScriptSegment(BaseModel):
    segment_id: str
    scene_id: str
    beat_id: Optional[str] = None
    sequence: int = 1
    type: SegmentType = SegmentType.CHARACTER_DIALOGUE
    speaker_character_id: Optional[str] = None
    text: str = ""
    emotion: EmotionType = EmotionType.NEUTRAL
    intensity: float = 0.5
    estimated_duration: float = 2.0  # seconds
    estimated_start: float = 0.0     # seconds
    estimated_end: float = 2.0       # seconds
    source_evidence: ProvenanceReference = Field(default_factory=ProvenanceReference)
    production_intent: str = ""
    music_intent: Optional[str] = None
    sfx_intent: Optional[str] = None
    motion_intent: Optional[MotionIntent] = None
    delivery_style: str = "CALM_NARRATION"  # CALM_NARRATION, SUSPENSE, WONDER, DANGER, CLIFFHANGER
    vocal_energy: str = "medium"
    target_pace: float = 1.30
    trailing_pause: float = 0.35
    evidence_summary: str = ""
    faithfulness_status: str = "SUPPORTED"  # SUPPORTED, WEAKLY_SUPPORTED, UNSUPPORTED
    manual_override: bool = False


class VideoScript(BaseModel):
    script_id: str
    project_id: str
    version: str = "1.0"
    adaptation_profile: AdaptationProfile = AdaptationProfile.FAITHFUL
    segments: List[ScriptSegment] = Field(default_factory=list)
    estimated_duration: float = 0.0
    language: str = "en"
    status: str = "DRAFT"  # DRAFT, VALIDATED, APPROVED
    quality_metrics: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def is_approved(self) -> bool:
        return self.status == "APPROVED"


class ScriptValidationReport(BaseModel):
    script_id: str
    total_segments: int
    supported_segments: int
    weakly_supported_segments: int
    unsupported_segments: int
    coverage_score: float  # e.g. 0.95
    issues: List[Dict[str, Any]] = Field(default_factory=list)
    passed: bool = True
