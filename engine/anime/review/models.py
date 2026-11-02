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
