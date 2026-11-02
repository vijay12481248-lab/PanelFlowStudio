"""Data contracts for the Anime Review workflow (docs/ANIME_REVIEW.md)."""
from pydantic import BaseModel, Field

from engine.acquisition.rights.models import RightsDeclaration


class IngestRecord(BaseModel):
    source_uri: str
    local_path: str
    sha256: str
    title: str
    duration_sec: float
    width: int
    height: int
    fps: float
    has_audio: bool
    rights: RightsDeclaration
    ingested_at: float


class Shot(BaseModel):
    idx: int
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


class Segment(BaseModel):
    start: float
    end: float
    text: str


class EpisodeAnalysis(BaseModel):
    duration_sec: float
    shots: list[Shot] = Field(default_factory=list)
    transcript: list[Segment] = Field(default_factory=list)
    transcript_source: str = "none"  # embedded_subs | asr | none
    language: str | None = None
    audio_path: str | None = None


class Beat(BaseModel):
    """One reviewable moment of the episode, located in source time."""
    id: str
    start: float
    end: float
    kind: str  # opening | highlight | emotional | funny | smooth | weak | ending
    label: str
    why: str


class Understanding(BaseModel):
    summary: str
    characters: list[str] = Field(default_factory=list)
    beats: list[Beat] = Field(default_factory=list)
    energy_peaks: list[float] = Field(default_factory=list)  # seconds of loudest moments (deterministic)


class Clip(BaseModel):
    id: str
    beat_id: str
    start: float
    end: float
    purpose: str

    @property
    def duration(self) -> float:
        return self.end - self.start


class ClipPlan(BaseModel):
    clips: list[Clip]
    total_sec: float
    budget_sec: float
    dropped_beats: list[str] = Field(default_factory=list)


class ScriptSegment(BaseModel):
    id: str
    clip_id: str  # the clip shown while this segment is spoken
    role: str  # hook | recap | highlight | smooth | funny | critique | verdict | cta
    text: str


class ReviewScript(BaseModel):
    title_hook: str
    rating: float  # 0-10
    segments: list[ScriptSegment]
    tone: str = ""


class TimelineEntry(BaseModel):
    segment_id: str
    clip_id: str
    audio_path: str
    audio_sec: float  # measured from the written wav, frame-aligned: this IS the segment's length on the timeline
    timeline_start: float
    src_start: float  # seconds in the source episode
    src_len: float  # source seconds consumed
    speed: float = 1.0  # <1 slows the clip to cover more audio
    hold_sec: float = 0.0  # freeze the last frame for this long after the clip runs out
    warnings: list[str] = Field(default_factory=list)


class Timeline(BaseModel):
    fps: float
    total_sec: float
    entries: list[TimelineEntry]
    voice: str
