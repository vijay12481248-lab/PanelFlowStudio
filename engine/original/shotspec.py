"""Shot specification and the image-prompt composer: the system, not a person, writes the detailed prompt.

A shot director (LLM, see beats.py) turns one narrated moment into a structured spec: who is on screen and where, each
character's pose, expression and action, the setting details, lighting and mood, and what must be visible. This module turns that
spec into an SDXL/booru-style prompt deterministically, using a vocabulary that maps plain words (pose, expression, action) to
tags the image model understands, and weights what the narration needs. The same code serves every story and genre.
"""
from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

from engine.original.genres import GENRES
from engine.original.models import Character, OriginalStory
from engine.original.rigging import RiggingSpec

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
CAMERA = {"wide": "wide shot, full body, scenery", "full": "full body shot, head to toe, visible feet",
          "full_body": "full body shot, head to toe, visible feet", "medium": "cowboy shot",
          "close": "close-up, portrait, face focus", "extreme_close": "extreme close-up, detail focus",
          "over_shoulder": "from behind, over the shoulder"}
ANGLE = {"eye_level": "", "low": "from below", "high": "from above", "dutch": ""}  # dutch angles distort this model's anatomy: dropped
LIGHT = {"warm": "warm lighting, golden light", "moon": "moonlight, soft blue light", "glow": "soft glow, bioluminescent", "dark": "dim lighting, shadows",
         "sunset": "sunset, orange sky", "sunrise": "sunrise, soft morning light", "fog": "fog, mist", "candle": "candlelight", "rain": "rain, wet",
         "night": "night, dark sky", "bright": "bright daylight"}
QUALITY = "safe, masterpiece, high score, great score, absurdres"
NEGATIVE = ("lowres, bad anatomy, bad hands, text, error, missing finger, extra digits, fewer digits, cropped, worst quality, "
            "low quality, low score, bad score, average score, signature, watermark, username, blurry, nsfw, nude, "
            "suggestive, revealing clothes, speech bubble, floating objects, disconnected hands")
EYES_CLOSED_NEGATIVE = ", open eyes, looking at viewer"
LOOK_AT_VIEWER_NEGATIVE = ", looking at viewer"  # for from-behind / looking-away shots
WEIGHTED = {"closed eyes", "sleeping, closed eyes", "crying, tears", "yawning", "from behind", "facing away", "lying down", "curled up, lying on side"}

# Standard 1-Megapixel resolution buckets optimized for SDXL, Flux, and Qwen
SHOT_DIMENSIONS: dict[str, tuple[int, int]] = {
    "wide": (1344, 768),
    "extreme_wide": (1344, 768),
    "landscape": (1344, 768),
    "over_shoulder": (1152, 896),
    "medium": (1024, 1024),
    "cowboy": (1024, 1024),
    "close": (1024, 1024),
    "extreme_close": (1024, 1024),
    "full": (832, 1216),
    "full_body": (832, 1216),
    "character_sheet": (832, 1216),
    "sheet": (832, 1216),
    "portrait": (832, 1216),
    "turnaround": (1536, 768),
    "turnaround_sheet": (1536, 768),
    "rigging": (832, 1216),
    "rigging_view": (832, 1216),
}

# Standard 0.25-Megapixel resolution buckets for rapid preview pass (all multiples of 16)
SHOT_DIMENSIONS_PREVIEW: dict[str, tuple[int, int]] = {
    "wide": (672, 384),
    "extreme_wide": (672, 384),
    "landscape": (672, 384),
    "over_shoulder": (576, 448),
    "medium": (512, 512),
    "cowboy": (512, 512),
    "close": (512, 512),
    "extreme_close": (512, 512),
    "full": (416, 608),
    "full_body": (416, 608),
    "character_sheet": (416, 608),
    "sheet": (416, 608),
    "portrait": (416, 608),
    "turnaround": (768, 384),
    "turnaround_sheet": (768, 384),
    "rigging": (416, 608),
    "rigging_view": (416, 608),
}


def resolve_dimensions(
    shot: str | None,
    num_characters: int = 1,
    default: tuple[int, int] = (1344, 768),
    preview: bool = False,
) -> tuple[int, int]:
    """Resolve standard 1-MP (or 0.25-MP when preview=True) (width, height) bucket for a given shot type and character count.
    Two or more characters side-by-side need landscape widescreen (1344x768 / 672x384) to prevent occlusion.
    Single full-body shots use portrait (832x1216 / 416x608) to prevent cutting off head or feet.
    Single close-up or medium shots use square (1024x1024 / 512x512) for centered framing.
    Turnaround sheets use ultra-wide landscape (1536x768 / 768x384) regardless of character count.
    """
    table = SHOT_DIMENSIONS_PREVIEW if preview else SHOT_DIMENSIONS
    def_dims = (
        (round(default[0] / 32) * 16, round(default[1] / 32) * 16)
        if preview
        else default
    )

    if shot:
        normalized = shot.strip().lower().replace("-", "_").replace(" ", "_")
        if normalized in ("turnaround", "turnaround_sheet"):
            return table["turnaround"]
    if num_characters >= 2:
        return table["wide"]
    if not shot:
        return def_dims
    normalized = shot.strip().lower().replace("-", "_").replace(" ", "_")
    return table.get(normalized, def_dims)


INTERACTION_BINDING_TAGS: dict[str, list[str]] = {
    "holding": ["firmly gripped in hands", "fingers wrapped around object", "physical contact visible", "zero gap"],
    "holds": ["firmly gripped in hands", "fingers wrapped around object", "physical contact visible", "zero gap"],
    "gripping": ["firmly gripped in hands", "fingers tightly wrapped around object", "physical contact visible"],
    "grips": ["firmly gripped in hands", "fingers tightly wrapped around object", "physical contact visible"],
    "carrying": ["holding securely against body", "physical contact visible", "hands supporting object"],
    "carries": ["holding securely against body", "physical contact visible", "hands supporting object"],
    "wielding": ["firmly gripped in hand", "fingers wrapped around handle", "physical contact visible"],
    "wields": ["firmly gripped in hand", "fingers wrapped around handle", "physical contact visible"],
    "reading": ["holding book in hands", "hands gripping pages", "physical contact visible"],
    "reads": ["holding book in hands", "hands gripping pages", "physical contact visible"],
    "reaching": ["extended hand", "fingers reaching toward target"],
    "reaches": ["extended hand", "fingers reaching toward target"],
    "touching": ["hand resting directly on surface", "physical contact visible", "zero gap"],
    "touches": ["hand resting directly on surface", "physical contact visible", "zero gap"],
    "grabbing": ["fingers grasping object", "firm grip", "physical contact visible"],
    "grabs": ["fingers grasping object", "firm grip", "physical contact visible"],
    "hugging": ["arms wrapped tightly around", "physical contact visible", "embracing"],
    "hug": ["arms wrapped tightly around", "physical contact visible", "embracing"],
    "drinking": ["holding cup to lips", "physical contact visible", "hand gripping cup"],
    "drinks": ["holding cup to lips", "physical contact visible", "hand gripping cup"],
    "eating": ["holding food in hand", "physical contact visible"],
    "eats": ["holding food in hand", "physical contact visible"],
}

INTERACTION_BINDING_NATURAL: dict[str, str] = {
    "holding": "hands firmly gripping the object with fingers visibly curled around it, maintaining unbroken physical contact",
    "holds": "hands firmly gripping the object with fingers visibly curled around it, maintaining unbroken physical contact",
    "gripping": "hands tightly gripping the object with fingers wrapped firmly around it, establishing solid physical contact",
    "grips": "hands tightly gripping the object with fingers wrapped firmly around it, establishing solid physical contact",
    "carrying": "arms securely supporting and carrying the object against the body with visible physical contact",
    "carries": "arms securely supporting and carrying the object against the body with visible physical contact",
    "wielding": "hand firmly gripping the handle with fingers wrapped tightly around it, showing true physical connection",
    "wields": "hand firmly gripping the handle with fingers wrapped tightly around it, showing true physical connection",
    "reading": "hands holding the book with visible finger contact on the cover or pages",
    "reads": "hands holding the book with visible finger contact on the cover or pages",
    "reaching": "hand extending forward toward the target with fingers opened in direction of reach",
    "reaches": "hand extending forward toward the target with fingers opened in direction of reach",
    "touching": "hand and fingers resting directly against the surface with no air gap between them",
    "touches": "hand and fingers resting directly against the surface with no air gap between them",
    "grabbing": "hand firmly grasping the object with fingers closed around it",
    "grabs": "hand firmly grasping the object with fingers closed around it",
    "hugging": "arms wrapped securely around with direct body and arm contact",
    "hug": "arms wrapped securely around with direct body and arm contact",
    "drinking": "hands holding the vessel securely against the lips with visible physical contact",
    "drinks": "hands holding the vessel securely against the lips with visible physical contact",
    "eating": "hand holding the food close to the mouth with clear physical contact",
    "eats": "hand holding the food close to the mouth with clear physical contact",
}

MARGIN_TAGS: dict[str, list[str]] = {
    "full": ["full body", "head to toe", "feet on ground", "visible feet", "wide margins", "subject completely in frame"],
    "full_body": ["full body", "head to toe", "feet on ground", "visible feet", "wide margins", "subject completely in frame"],
    "character_sheet": ["full body", "standing", "head to toe", "feet on ground", "visible feet", "wide margins", "subject completely in frame"],
    "close": ["centered face focus", "face and shoulders in frame"],
    "extreme_close": ["macro detail focus", "face focus"],
}

MARGIN_NATURAL: dict[str, str] = {
    "full": "Full body shot from head to toe with visible feet resting on the ground, generous margins around the subject, completely in frame with no cropping.",
    "full_body": "Full body shot from head to toe with visible feet resting on the ground, generous margins around the subject, completely in frame with no cropping.",
    "character_sheet": "Full length standing character reference from head to toe with clear empty margins around the subject, completely in frame.",
    "medium": "Medium shot from the waist up with generous headroom above the hair, subject completely in frame with no top cropping.",
    "close": "Centered framing focusing on the face and shoulders, with generous headroom above the hair, completely in frame.",
    "extreme_close": "Macro framing focusing closely on facial details.",
}


def compile_interaction_bindings_tags(actions: list[str]) -> list[str]:
    """Extract kinematic contact binding tags for any detected physical interaction."""
    bindings: list[str] = []
    text = " ".join(actions).lower()
    words = set(re.findall(r"\b\w+\b", text))
    for verb, tags in INTERACTION_BINDING_TAGS.items():
        if verb in words:
            for t in tags:
                if t not in bindings:
                    bindings.append(t)
    return bindings


def compile_interaction_bindings_natural(actions: list[str]) -> list[str]:
    """Extract natural-language kinematic contact directives for any detected physical interaction."""
    bindings: list[str] = []
    text = " ".join(actions).lower()
    words = set(re.findall(r"\b\w+\b", text))
    for verb, phrase in INTERACTION_BINDING_NATURAL.items():
        if verb in words and phrase not in bindings:
            bindings.append(phrase)
    return bindings


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
    pose_image: str | Path | None = None
    depth_image: str | Path | None = None
    control_pose: str | Path | None = None
    control_depth: str | Path | None = None
    pose_weight: float | None = 0.75
    depth_weight: float | None = 0.6

    # Rigging & Turnaround reference specifications (Phase 5 M1)
    rigging: RiggingSpec | None = None
    is_rigging: bool = False
    rigging_pose: str = "a_pose"
    turnaround_views: list[str] = Field(
        default_factory=lambda: ["front", "three_quarter", "side", "back"]
    )
    orthographic: bool = True
    limb_separation: bool = True

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


def compile_controlnet_conditioning(spec: ShotSpec, dims: tuple[int, int]) -> dict:
    """Compile pose and depth conditioning descriptors and paths for ControlNet from ShotSpec."""
    pose_img = str(spec.pose_image) if spec.pose_image is not None else None
    depth_img = str(spec.depth_image) if spec.depth_image is not None else None

    # Resolve control_pose from explicit field or character pose tags
    ctrl_pose = str(spec.control_pose) if spec.control_pose is not None else None
    if not ctrl_pose and not pose_img:
        for c in spec.characters:
            low = f"{c.pose} {c.action}".lower()
            for k, tag in POSES.items():
                if k in low:
                    ctrl_pose = tag
                    break
            if ctrl_pose:
                break

    # Resolve control_depth from explicit field or camera shot framing
    ctrl_depth = str(spec.control_depth) if spec.control_depth is not None else None
    if not ctrl_depth and not depth_img:
        if spec.shot in ("close", "extreme_close"):
            ctrl_depth = "depth_foreground_portrait"
        elif spec.shot in ("wide", "full", "full_body"):
            ctrl_depth = "depth_wide_landscape"
        elif spec.shot == "medium":
            ctrl_depth = "depth_midground"

    return {
        "pose_image": pose_img,
        "depth_image": depth_img,
        "pose_weight": spec.pose_weight if spec.pose_weight is not None else 0.75,
        "depth_weight": spec.depth_weight if spec.depth_weight is not None else 0.6,
        "control_pose": ctrl_pose,
        "control_depth": ctrl_depth,
        "camera": spec.camera,
        "shot": spec.shot,
        "dims": dims,
        "width": dims[0],
        "height": dims[1],
        "has_conditioning": bool(pose_img or depth_img or spec.control_pose or spec.control_depth),
    }


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


WORD_BUDGET = 110  # extended to accommodate explicit kinematic contact binding and margin tags


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
    # Kinematic interaction binding tokens (prevent floating objects and disconnected grip)
    action_texts = [c.action for c in shown if c.action] + [c.pose for c in shown if c.pose] + spec.key_visuals
    interaction_tags = compile_interaction_bindings_tags(action_texts)
    if interaction_tags:
        groups.append(interaction_tags)
    groups.append([f"({e}:1.4)" for e in emphasis if e not in spec.key_visuals])
    groups.append([f"({k}:1.3)" if k in emphasis else k for k in spec.key_visuals])
    groups.append(_tokens(spec.setting) + _tokens(loc.look, 5 if loc else 0))
    groups.append(light_tags(spec.lighting + " " + spec.mood) + _tokens(spec.lighting) + _tokens(spec.mood))
    margin_tags = MARGIN_TAGS.get(spec.shot, [])
    groups.append([CAMERA.get(spec.shot, ""), ANGLE.get(spec.camera, "")] + margin_tags)
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


NATURAL_PERSON = {
    ("child", "male"): "a little boy", ("child", "female"): "a little girl", ("child", "neutral"): "a child",
    ("teen", "male"): "a teenage boy", ("teen", "female"): "a teenage girl", ("teen", "neutral"): "a teenager",
    ("adult", "male"): "an adult man", ("adult", "female"): "an adult woman", ("adult", "neutral"): "an adult",
    ("elder", "male"): "an old man with a wrinkled face", ("elder", "female"): "an old woman with a wrinkled face",
    ("elder", "neutral"): "an elderly person",
}
FRAMING = {"wide": "Wide shot showing the whole scene and the surroundings.", "full": "Full-body shot showing the character from head to toe.",
           "full_body": "Full-body shot showing the character from head to toe.", "medium": "Medium shot from the waist up.",
           "close": "Close-up of the face and shoulders.", "extreme_close": "Extreme close-up on the face and eyes.",
           "over_shoulder": "Over-the-shoulder shot from behind the character."}
NATURAL_SUFFIX = "No text, no captions, no speech bubbles, no watermark. A single clean illustration with consistent character design."


def describe_character(ch: Character) -> str:
    """One reusable sentence fragment for a character: the same words in every picture keep the design consistent."""
    who = NATURAL_PERSON.get((ch.age_group, ch.gender), "a person") if ch.species == "human" else f"a {ch.species}"
    return f"{who} with {ch.look}"


NAME_TITLES = {"dr", "mr", "mrs", "ms", "miss", "sir", "lady", "lord", "professor", "prof", "captain", "doctor"}


def unname(text: str, characters: list[Character]) -> str:
    """An image model reads a character's NAME as a thing ("Biscuit" drew cookies): refer to each character by what they are."""
    for c in characters:
        noun = "the " + (re.sub(r"^(an?|the)\s+", "", NATURAL_PERSON.get((c.age_group, c.gender), "person").split(" with ")[0])
                         if c.species == "human" else c.species)
        for name in sorted({t for t in re.findall(r"[A-Za-z]{3,}", c.name) if t.lower() not in NAME_TITLES}, key=len, reverse=True):
            # LLM-written claims lowercase the name as a noun ("the biscuit nudges the glass"): an article in front gives it away
            text = re.sub(rf"\b(?:the|an?)\s+{re.escape(name)}\b", lambda m, n=noun: n.capitalize() if m.group(0)[0].isupper() else n, text, flags=re.I)
            text = re.sub(rf"\b{re.escape(name)}\b", lambda m, n=noun: n.capitalize() if m.start() == 0 or text[max(0, m.start() - 2):m.start()] in (". ", "! ", "? ") else n,
                          text)
    return text


def compose_natural(story: OriginalStory, spec: ShotSpec, location_id: str, emphasis: list[str] | None = None,
                    simplify: bool = False, target: str = "natural") -> tuple[str, str]:
    """The same ShotSpec as a paragraph of plain English, for models that follow sentences instead of tags. (positive, negative='')"""
    from engine.original.prompt import PromptCompiler
    compiled = PromptCompiler.compile_image_prompt(
        story=story,
        spec=spec,
        location_id=location_id,
        target=target,
        emphasis=emphasis,
        simplify=simplify,
    )
    return compiled.positive, compiled.negative


def pose_sensitive(spec: ShotSpec) -> bool:
    """Shots whose pose or expression the character portrait would override (it looks at the viewer, eyes open)."""
    text = " ".join([c.pose + " " + c.expression + " " + c.action for c in spec.characters] + spec.key_visuals).lower()
    return any(w in text for w in ("closed", "asleep", "sleeping", "from behind", "facing away", "turned away", "looking up", "looking down",
                                   "looking back", "curled", "lying", "hiding", "peeking"))


CAMERA_MOTIONS = {
    "push_in": "Slow cinematic camera push in towards the subject",
    "pull_out": "Smooth slow camera pull back revealing the surroundings",
    "pan_right": "Gentle camera pan from left to right across the scene",
    "pan_left": "Gentle camera pan from right to left across the scene",
    "tilt_up": "Slow camera tilt upwards",
    "orbit": "Slow subtle camera orbit around the focal point",
    "static": "Static camera framing, subtle ambient motion",
}


def compose_motion_prompt(
    spec: ShotSpec | None = None,
    camera_direction: str = "push_in",
    custom_prompt: str = "",
    action_hint: str = "",
    intensity: str = "balanced",
    fx_tags: str = "",
) -> tuple[str, str]:
    """Return (positive_prompt, negative_prompt) tailored for MiniMax Fast H3 Image-to-Video."""
    from engine.original.prompt import PromptCompiler
    compiled = PromptCompiler.compile_video_prompt(
        spec=spec,
        camera_direction=camera_direction,
        custom_prompt=custom_prompt,
        action_hint=action_hint,
        intensity=intensity,
        fx_tags=fx_tags,
    )
    return compiled.positive, compiled.negative
