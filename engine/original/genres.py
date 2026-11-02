"""Genre presets: tone, structure, length, art style and the content limits the validators enforce."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Genre:
    key: str
    tone: str
    structure: str
    scenes: int
    panels_per_scene: tuple[int, int]
    art_style: str  # tags appended to every art prompt (used in S2)
    forbidden: frozenset[str] = field(default_factory=frozenset)
    child_safe: bool = False
    caption_words: tuple[int, int] = (15, 35)  # the narrator box on every panel carries the story in the video


# Words no genre may use (sexual content, self-harm, slurs are never in generated stories).
ALWAYS_FORBIDDEN = frozenset({"sex", "sexual", "naked", "nude", "rape", "suicide", "porn"})
GORE = frozenset({"gore", "blood", "bloody", "corpse", "dismember", "decapitate", "mutilate", "entrails"})
SCARY = frozenset({"terror", "terrifying", "terrified", "nightmare", "nightmares", "panic", "scary", "threatening", "scream",
                   "screaming", "trapped", "sweat", "dangerous", "dangerously", "howling", "violently"})
KIDS = GORE | SCARY | frozenset({"kill", "killed", "murder", "die", "died", "dead", "death", "gun", "knife", "weapon", "stab", "hate"})

GENRES: dict[str, Genre] = {
    "bedtime": Genre(
        "bedtime", "gentle, warm, soothing, slightly magical; a calm ending that helps a child fall asleep",
        "a small worry, a kind helper, a gentle adventure, everything resolved softly, the character goes to sleep",
        7, (4, 5), "soft pastel colors, warm lighting, storybook anime style, cozy, gentle",
        ALWAYS_FORBIDDEN | KIDS, child_safe=True, caption_words=(25, 45)),
    "horror": Genre(
        "horror", "slow-building dread, atmospheric, quiet and unsettling; suggestion over gore",
        "an ordinary place, a small wrong detail, escalating unease, a reveal, an ending that leaves a chill",
        8, (4, 5), "dark moody lighting, muted desaturated colors, night, fog, cinematic horror anime style",
        ALWAYS_FORBIDDEN | GORE),
    "mystery": Genre(
        "mystery", "curious, tense, clever; clues are planted fairly",
        "a puzzling event, clues, a false lead, a revelation that recontextualises an earlier clue",
        8, (4, 5), "noir lighting, rich shadows, detective anime style",
        ALWAYS_FORBIDDEN | GORE),
    "fantasy": Genre(
        "fantasy", "adventurous, wondrous, emotional",
        "an ordinary world, a call to adventure, trials with an ally, a costly victory, a changed hero",
        8, (4, 5), "vivid colors, epic scenery, fantasy anime style, dramatic lighting",
        ALWAYS_FORBIDDEN | GORE),
}

SHOTS = {"wide", "medium", "close", "extreme_close", "over_shoulder"}
ANGLES = {"eye_level", "low", "high", "dutch"}
