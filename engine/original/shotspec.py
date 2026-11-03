"""Shot specification and the image-prompt composer: the system, not a person, writes the detailed prompt.

A shot director (LLM, see beats.py) turns one narrated moment into a structured spec: who is on screen and where, each
character's pose, expression and action, the setting details, lighting and mood, and what must be visible. This module turns that
spec into an SDXL/booru-style prompt deterministically, using a vocabulary that maps plain words (pose, expression, action) to
tags the image model understands, and weights what the narration needs. The same code serves every story and genre.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from engine.original.genres import GENRES
from engine.original.models import Character, OriginalStory

# plain-English fragment -> image-model tags. Longest fragments are matched first; unmatched words still go in as plain text.
EXPRESSIONS = {
    "eyes closed": "closed eyes", "closes his eyes": "closed eyes", "closed eyes": "closed eyes", "asleep": "sleeping, closed eyes",
    "sleeping": "sleeping, closed eyes", "slumber": "sleeping, closed eyes", "peaceful": "serene, gentle smile", "gentle smile": "gentle smile",
    "smile": "smile", "smiling": "smile", "grin": "grin", "laugh": "laughing, open mouth", "giggl": "laughing, open mouth",
    "surprised": "surprised, wide eyes, open mouth", "startled": "surprised, wide eyes", "amazed": "wide eyes, sparkling eyes",
    "scared": "scared, wide eyes, trembling", "afraid": "scared, wide eyes", "worried": "worried, furrowed brow", "anxious": "worried, nervous",
    "sad": "sad, downcast eyes", "cry": "crying, tears", "tears": "tears", "angry": "angry, furrowed brow", "determined": "determined, serious",
    "curious": "curious, head tilt", "thoughtful": "thoughtful, looking away", "sleepy": "sleepy, half-closed eyes", "yawn": "yawning",
    "relieved": "relieved, soft smile", "hopeful": "hopeful, looking up", "excited": "excited, sparkling eyes, open mouth",
    "calm": "calm, relaxed", "whisper": "whispering, hand near mouth", "blush": "blush", "wink": "wink",
}
POSES = {
    "lying": "lying down", "curled up": "curled up, lying on side", "sitting": "sitting", "kneeling": "kneeling", "crouch": "crouching",
    "standing": "standing", "walking": "walking", "running": "running, motion blur", "jumping": "jumping", "reaching": "reaching out",
    "hugging": "hug", "holding": "holding", "carrying": "carrying", "pointing": "pointing", "waving": "waving", "leaning": "leaning",
    "looking up": "looking up", "looking down": "looking down", "looking back": "looking back", "from behind": "from behind",
    "facing away": "facing away", "turned away": "from behind", "peeking": "peeking", "floating": "floating", "flying": "flying",
    "dancing": "dancing", "resting": "resting, relaxed", "huddled": "huddling together", "side by side": "side by side",
}
CAMERA = {"wide": "wide shot, full body, scenery", "medium": "cowboy shot", "close": "close-up, portrait, face focus",
          "extreme_close": "extreme close-up, detail focus", "over_shoulder": "from behind, over the shoulder"}
ANGLE = {"eye_level": "", "low": "from below", "high": "from above", "dutch": ""}  # dutch angles distort this model's anatomy: dropped
LIGHT = {"warm": "warm lighting, golden light", "moon": "moonlight, soft blue light", "glow": "soft glow, bioluminescent", "dark": "dim lighting, shadows",
         "sunset": "sunset, orange sky", "sunrise": "sunrise, soft morning light", "fog": "fog, mist", "candle": "candlelight", "rain": "rain, wet",
         "night": "night, dark sky", "bright": "bright daylight"}
QUALITY = "safe, masterpiece, high score, great score, absurdres"
NEGATIVE = ("lowres, bad anatomy, bad hands, text, error, missing finger, extra digits, fewer digits, cropped, worst quality, "
            "low quality, low score, bad score, average score, signature, watermark, username, blurry, nsfw, nude, "
            "suggestive, revealing clothes, speech bubble")
EYES_CLOSED_NEGATIVE = ", open eyes, looking at viewer"
LOOK_AT_VIEWER_NEGATIVE = ", looking at viewer"  # for from-behind / looking-away shots
WEIGHTED = {"closed eyes", "sleeping, closed eyes", "crying, tears", "yawning", "from behind", "facing away", "lying down", "curled up, lying on side"}


PERSON = {  # (age group, gender) -> the words an anime model needs to draw the right kind of person
    ("child", "male"): "little boy, child", ("child", "female"): "little girl, child", ("child", "neutral"): "child",
    ("teen", "male"): "teenage boy", ("teen", "female"): "teenage girl", ("teen", "neutral"): "teenager",
    ("adult", "male"): "adult man, male focus", ("adult", "female"): "adult woman", ("adult", "neutral"): "adult",
    ("elder", "male"): "old man, elderly man, wrinkles, male focus", ("elder", "female"): "old woman, elderly woman, wrinkles",
    ("elder", "neutral"): "elderly person, wrinkles",
}


def person_tags(c: Character) -> str:
    """Kind-of-person tags for humans; creatures and objects get their own look tags only."""
    return PERSON.get((c.age_group, c.gender), "") if c.species == "human" else c.species


class CharPose(BaseModel):
    id: str
    side: str = "center"  # left | center | right (screen position; the first listed character is drawn left in two-character shots)
    pose: str = ""
    expression: str = ""
    action: str = ""


class ShotSpec(BaseModel):
    shot: str
    camera: str = "eye_level"
    characters: list[CharPose] = Field(default_factory=list)
    setting: str = ""  # specifics beyond the location's own look: objects, time of day, weather
    lighting: str = ""
    mood: str = ""
    key_visuals: list[str] = Field(default_factory=list)

    def required_text(self, chars: dict[str, Character]) -> str:
        """Plain-language list of what the picture must show, for the judge."""
        lines = []
        for c in self.characters:
            ch = chars.get(c.id)
            who = f"{ch.name} ({ch.look.split(',')[0]})" if ch else c.id
            lines.append(f"{who}: {', '.join(x for x in (c.pose, c.expression, c.action) if x)}")
        if self.setting:
            lines.append(f"Setting: {self.setting}")
        lines += [f"Must be visible: {k}" for k in self.key_visuals]
        return "\n".join(lines)


def tags_for(text: str, vocab: dict[str, str]) -> list[str]:
    """Vocabulary tags for every known fragment in `text` (longest first, no duplicates)."""
    low, found = text.lower(), []
    for frag in sorted(vocab, key=len, reverse=True):
        if frag in low and vocab[frag] not in found:
            found.append(vocab[frag])
    return found


def light_tags(text: str) -> list[str]:
    low = text.lower()
    return [v for k, v in LIGHT.items() if k in low]


WORD_BUDGET = 90  # the image model's text encoder reads about 77 tokens with full attention; later words fade, so priority order matters


def _tokens(text: str, limit: int | None = None) -> list[str]:
    out = [t.strip() for t in text.split(",") if t.strip()]
    return out[:limit] if limit else out


def compose(story: OriginalStory, spec: ShotSpec, location_id: str, emphasis: list[str] | None = None,
            fallback_action: str = "") -> tuple[str, str]:
    """(positive, negative) prompt for one shot, most important first and kept inside a word budget.

    Order: who is drawn and what they do (pose, expression, action), what must be visible, the specifics of the place, light and
    mood, the camera, then the style tags. If the budget runs out the least important detail (late place/light words) is cut,
    never the subject. `emphasis` are phrases a previous attempt failed to show: they get extra weight and a place near the front.
    """
    genre = GENRES[story.bible.premise.genre]
    chars = {c.id: c for c in story.bible.characters}
    loc = next((x for x in story.bible.locations if x.id == location_id), None)
    shown = [c for c in spec.characters if c.id in chars][:2]
    if len(shown) == 2:
        shown.sort(key=lambda c: {"left": 0, "center": 1, "right": 2}.get(c.side, 1))  # the masked two-reference workflow draws #1 left
    emphasis = emphasis or []
    groups: list[list[str]] = [[{0: "no humans", 1: "solo", 2: "2others"}.get(len(shown), "multiple others")]]
    for c in shown:
        ch = chars[c.id]
        detail = list(dict.fromkeys(tags_for(c.expression, EXPRESSIONS) + tags_for(c.pose, POSES) + tags_for(c.action, POSES)
                                    + tags_for(c.action, EXPRESSIONS)))
        groups.append(_tokens(person_tags(ch)) + _tokens(ch.look, 6) + detail + [x for x in (c.pose, c.action) if x])
    groups.append([f"({e}:1.4)" for e in emphasis if e not in spec.key_visuals])
    groups.append([f"({k}:1.3)" if k in emphasis else k for k in spec.key_visuals])
    groups.append(_tokens(spec.setting) + _tokens(loc.look, 5 if loc else 0))
    groups.append(light_tags(spec.lighting + " " + spec.mood) + _tokens(spec.lighting) + _tokens(spec.mood))
    groups.append([CAMERA.get(spec.shot, ""), ANGLE.get(spec.camera, "")])
    tokens: list[str] = []
    words = 0
    for group in groups:
        for t in group:
            t = t.strip()
            if not t:
                continue
            w = f"({t}:1.3)" if t in WEIGHTED and not t.startswith("(") else t
            n = len(t.split())
            if w in tokens or words + n > WORD_BUDGET:
                continue
            tokens.append(w)
            words += n
    tokens += [t for t in _tokens(genre.art_style) + _tokens(QUALITY) if t not in tokens]  # style and quality tags are never cut
    neg = NEGATIVE
    if any("closed eyes" in t for t in tokens):
        neg += EYES_CLOSED_NEGATIVE
    elif any(t.strip("()").split(":")[0] in ("from behind", "facing away") for t in tokens):
        neg += LOOK_AT_VIEWER_NEGATIVE
    return ", ".join(tokens), neg


def pose_sensitive(spec: ShotSpec) -> bool:
    """Shots whose pose or expression the character portrait would override (it looks at the viewer, eyes open)."""
    text = " ".join([c.pose + " " + c.expression + " " + c.action for c in spec.characters] + spec.key_visuals).lower()
    return any(w in text for w in ("closed", "asleep", "sleeping", "from behind", "facing away", "turned away", "looking up", "looking down",
                                   "looking back", "curled", "lying", "hiding", "peeking"))
