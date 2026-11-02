"""Data contracts for original stories: premise -> bible -> scenes -> panels."""
from pydantic import BaseModel, Field


class Premise(BaseModel):
    title: str
    genre: str
    logline: str
    tone: str
    setting: str


class Character(BaseModel):
    id: str  # short slug, e.g. "mira"
    name: str
    role: str  # protagonist | companion | antagonist | mentor | other
    age_group: str  # child | teen | adult | elder
    look: str  # comma-separated visual tags reused verbatim in every art prompt
    personality: str


class Location(BaseModel):
    id: str
    name: str
    look: str  # comma-separated visual tags


class Bible(BaseModel):
    premise: Premise
    characters: list[Character]
    locations: list[Location]
    rules: list[str] = Field(default_factory=list)  # facts that must never be contradicted


class Line(BaseModel):
    speaker_id: str
    text: str


class Panel(BaseModel):
    id: str
    scene_id: str
    shot: str  # wide | medium | close | extreme_close | over_shoulder
    angle: str  # eye_level | low | high | dutch
    location_id: str
    character_ids: list[str]
    action: str  # concrete visual description for the art model
    dialogue: list[Line] = Field(default_factory=list)
    caption: str = ""  # narration box
    sfx: list[str] = Field(default_factory=list)


class Scene(BaseModel):
    id: str
    location_id: str
    character_ids: list[str]
    summary: str
    mood: str


class OriginalStory(BaseModel):
    bible: Bible
    scenes: list[Scene]
    panels: list[Panel]
    warnings: list[str] = Field(default_factory=list)
