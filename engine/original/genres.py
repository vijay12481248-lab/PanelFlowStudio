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
                   "screaming"})
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
    "anime_adventure": Genre(
        "anime_adventure", "adventurous, funny, thrilling and heartfelt",
        "a lively hook, a home in danger, a rival, a perilous race, a truce, a puzzle, a guardian fight, a costly choice, a changed home",
        10, (10, 14),
        "high-budget theatrical anime film, cinematic key frame, clean cel shading, crisp line art, rich painterly backgrounds, vivid colors, dramatic lighting",
        ALWAYS_FORBIDDEN | GORE, caption_words=(0, 0)),
    "mythology": Genre(
        "mythology", "epic, solemn, majestic, celestial, spiritual; cosmic scale and deep philosophical weight",
        "a sacred prologue, a divine gathering, the eternal composition, the tragic conflict, an immortal proclamation",
        8, (4, 5), "authentic Indian historical cinema, photorealistic film still, 35mm Arri Alexa cinematography, culturally authentic Indian heritage, photorealistic natural Indian skin texture, warm golden hour temple sunlight, brass diya oil lamp lighting, floating dust motes, sacred vibhuti bhasma, rudraksha beads, handwoven cotton dhoti, intricate gold zari brocade, cinematic depth of field, 8k resolution, documentary realism, devotional masterpiece",
        ALWAYS_FORBIDDEN | GORE, caption_words=(15, 45)),
    "vox": Genre(
        "vox", "fast-paced, witty, deadpan humorous, energetic, Vox-style visual documentary explainer",
        "a bizarre question or hilarious everyday phenomenon, comical evidence, escalating absurd theories, comical expert demonstration, hilarious scientific breakdown, unexpected twist conclusion",
        5, (4, 5), "Signature Vox 2D motion explainer style, modern flat vector graphic illustration, crisp bold dark outlines, solid vibrant color palette with bright canary yellow and deep navy accents, minimalist clean cel shading, high-end YouTube visual journalism aesthetic, consistent 2D vector animation look, zero photographic textures, zero 3D CGI",
        ALWAYS_FORBIDDEN | GORE, caption_words=(15, 30)),
}

SHOTS = {"wide", "medium", "close", "extreme_close", "over_shoulder", "full", "full_body"}
ANGLES = {"eye_level", "low", "high", "dutch"}
