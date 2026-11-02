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
