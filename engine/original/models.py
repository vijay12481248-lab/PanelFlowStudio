"""Data contracts for original stories: premise -> bible -> scenes -> panels."""
from pydantic import BaseModel, Field, model_validator


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
    species: str = "human"  # "human" or what they are: "fox cub", "clockwork assistant" (a human tag must never be put on a creature)
    gender: str = "neutral"  # male | female | neutral (humans only)


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
    key_visuals: list[str] = Field(default_factory=list)  # what the narration needs visible; checked on the image
    director: dict = Field(default_factory=dict)  # the ShotSpec the shot director wrote (see shotspec.py); empty for plain panels
    motion: str = ""  # what moves during this shot, for the video model (film.py); one action, never a loop
    seconds: float = 0.0  # take length for the video model (a long take: up to H3's 15 s limit); 0 = derived from the voice / shot size as before
    shots: list[dict] = Field(default_factory=list)  # shots INSIDE one take, [{"at": s, "framing": "wide|medium|close", "camera": "", "action": "...", "characters": ["id"]}]; empty = one shot (motion)
    atmosphere: str = ""  # the sky and light of this shot (both pictures): the Writer plans it per take so a story with a change in the weather or the mood is SEEN to change
    end_state: str = ""  # storyboard mode: what the LAST picture of the shot shows (who is where, doing what); the first picture is `action`
    camera: str = ""  # an explicit camera move for the video model ("a slow, steady push-in"); empty = Static Shot, the default (measured: a push-in sentence in every shot zoomed 38% on average)


class Scene(BaseModel):
    id: str
    location_id: str
    character_ids: list[str]
    summary: str
    mood: str
    score: str = ""  # music direction for this scene's cue (film.py / score.py); empty = derived from the mood
    bpm: int = 0
    key: str = ""
    title: str = ""  # the YouTube chapter label; empty = the first words of `summary`


class OriginalStory(BaseModel):
    bible: Bible
    scenes: list[Scene]
    panels: list[Panel]
    warnings: list[str] = Field(default_factory=list)
    # packaging the author chose (all optional): hook (first description line), cta, tags, thumb_text (1-3 words), thumb_panel (panel id)
    meta: dict = Field(default_factory=dict)


class Claim(BaseModel):
    text: str
    critical: bool = True
    category: str = "narration"  # narration | anatomy | spatial_contact
    defect_type: str = ""  # polycephaly | extra_limbs | missing_limbs | distorted_digits | limb_topology | unanchored_object | disconnected_interaction
    interaction_target: str = ""
    kind: str = ""  # prompt requirements only: subject | attribute | object | placement | clothing | pose | environment | camera | framing | style


class ItemVerdict(BaseModel):
    item: str
    critical: bool
    verdict: str  # shown | partial | missing
    confidence: float
    vision: str  # yes | partly | no
    description_says: bool
    evidence: str = ""
    category: str = "narration"  # narration | anatomy | spatial_contact
    defect_type: str = ""  # polycephaly | extra_limbs | missing_limbs | distorted_digits | limb_topology | unanchored_object | disconnected_interaction
    passed: bool = True
    bbox: list[int | float] | None = None  # normalised 0..1 [x1, y1, x2, y2]; only ever set from a model-reported, validated box
    bbox_source: str = ""  # "vlm" | "" (a region the reviewer did not locate is never invented)
    status: str = ""  # correct | missing | incorrect | uncertain | not_verifiable (derived from verdict when the reviewer did not set it)
    severity: str = ""  # critical | minor, only for items that did not pass
    repairable_locally: bool = False  # a located, existing-but-wrong thing: a masked edit can fix it without redrawing the picture

    def model_post_init(self, __context) -> None:
        if self.verdict != "shown" or not self.passed:
            self.passed = False
        if not self.passed and self.category in ("anatomy", "spatial_contact"):
            self.verdict = "missing"
        if not self.status:
            self.status = {"shown": "correct", "partial": "uncertain"}.get(self.verdict, "missing")


class Review(BaseModel):
    items: list[ItemVerdict]
    score: float
    confidence: float
    decision: str  # accept | accept_low | regenerate
    reasons: list[str] = Field(default_factory=list)
    description: str = ""
    anatomy_passed: bool = True
    spatial_contact_passed: bool = True
    defects: list[str] = Field(default_factory=list)
    unverifiable: list[str] = Field(default_factory=list)  # requirements a picture cannot show (sound, ideas): for a human, never "fixed"

    @property
    def missing_critical(self) -> list[str]:
        return [i.item for i in self.items if i.critical and i.verdict != "shown" and i.category == "narration"]

    @property
    def all_missing_critical(self) -> list[str]:
        return [i.item for i in self.items if i.critical and i.verdict != "shown"]

    @property
    def anatomical_failures(self) -> list[ItemVerdict]:
        return [i for i in self.items if i.category == "anatomy" and (not i.passed or i.verdict != "shown")]

    @property
    def spatial_contact_failures(self) -> list[ItemVerdict]:
        return [i for i in self.items if i.category == "spatial_contact" and (not i.passed or i.verdict != "shown")]

    @property
    def spatial_failures(self) -> list[ItemVerdict]:
        return self.spatial_contact_failures

    @model_validator(mode="after")
    def _enforce_quality_gates(self) -> Review:
        af = self.anatomical_failures
        sf = self.spatial_contact_failures

        ANATOMY_DEFECT_TYPES = {"polycephaly", "extra_limbs", "missing_limbs", "distorted_digits", "limb_topology"}
        SPATIAL_DEFECT_TYPES = {"unanchored_object", "disconnected_interaction"}

        has_anatomy_defect = bool(af) or not self.anatomy_passed or any(d in ANATOMY_DEFECT_TYPES for d in self.defects)
        has_spatial_defect = bool(sf) or not self.spatial_contact_passed or any(d in SPATIAL_DEFECT_TYPES for d in self.defects)

        if has_anatomy_defect:
            self.anatomy_passed = False
            self.decision = "regenerate"
        if has_spatial_defect:
            self.spatial_contact_passed = False
            self.decision = "regenerate"

        new_defects = [i.defect_type or i.item for i in af + sf if (i.defect_type or i.item)]
        merged_defects = list(dict.fromkeys(self.defects + new_defects))
        self.defects = merged_defects

        if self.defects or not self.anatomy_passed or not self.spatial_contact_passed:
            self.decision = "regenerate"
        return self

