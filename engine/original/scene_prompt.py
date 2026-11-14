"""ScenePlan -> the Qwen prompt (through the existing prompt compiler, no second grammar) and -> the checklist the picture is judged against."""
from __future__ import annotations

from engine.original.models import Bible, Character, Claim, Location, OriginalStory, Panel, Premise, Scene
from engine.original.prompt import PromptCompiler
from engine.original.scene_plan import ScenePlan
from engine.original.shotspec import NATURAL_PERSON, CharPose, ShotSpec

DEFAULT_GENRE = "anime_adventure"  # style anchors come from the genre; a scene has none of its own
# How to ask Qwen for a camera angle so that it actually does it. Measured: at the end of the prompt this sentence gave a low angle in 3 of 8 fights on the first
# attempt, the compiler's own "Shot from a low camera angle looking up." alone gave 0 of 8 (blind camera read). Only the low angle is measured.
CAMERA_FIX = {
    "low": "Camera placed near the ground looking steeply upward, the subjects tower over the viewer.",
    "high": "Camera high above looking steeply down at the subjects, the ground visible around them.",
    "eye_level": "Camera at the subjects' eye height with a perfectly level horizon.",
    "dutch": "Camera tilted so the horizon is clearly slanted.",
}
_LIGHT = {"front": "the front", "back": "behind the subjects", "left": "the left", "right": "the right", "top": "above", "below": "below"}
_CAMERA = {
    "eye_level": "the view is at eye level",
    "low": "the camera looks up at the scene from a low angle",
    "high": "the camera looks down on the scene from a high angle",
    "dutch": "the camera is tilted at a dutch angle",
}
_SIDE = {"left": "on the left of the picture", "center": "in the centre of the picture", "right": "on the right of the picture"}
_NUMBER = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve"}


def _tags(text: str, n: int = 3) -> str:
    return ", ".join([t.strip() for t in text.split(",") if t.strip()][:n])


def describe_actor(a) -> str:
    """How a viewer would describe the actor (never the name): used in the checklist."""
    noun = NATURAL_PERSON.get((a.age_group, a.gender), "a person") if a.species == "human" else f"a {a.species}"
    return f"{noun} with {_tags(a.description)}"


def plan_to_shotspec(plan: ScenePlan, genre: str = DEFAULT_GENRE) -> tuple[OriginalStory, ShotSpec, str]:
    """An ephemeral one-scene story (one Character per actor, one Location) so the existing compiler can be reused as it is.
    The compiler draws at most two characters; a plan with more is still checked for all of them."""
    chars = [Character(id=a.id, name=a.id, role="protagonist" if i == 0 else "antagonist" if i == 1 else "other", age_group=a.age_group,
                       look=a.description, personality="", species=a.species, gender=a.gender) for i, a in enumerate(plan.actors)]
    place = Location(id="place", name="the place", look=plan.setting or "simple background")
    bible = Bible(premise=Premise(title=plan.brief[:60], genre=genre, logline=plan.brief, tone=plan.mood or "neutral", setting=plan.setting),
                  characters=chars, locations=[place])
    story = OriginalStory(
        bible=bible,
        scenes=[Scene(id="s1", location_id="place", character_ids=[c.id for c in chars], summary=plan.brief, mood=plan.mood)],
        panels=[Panel(id="p1", scene_id="s1", shot=plan.camera.distance, angle=plan.camera.angle, location_id="place",
                      character_ids=[c.id for c in chars], action=plan.brief)],
    )
    by_id = {a.id: a for a in plan.actors}
    pos = lambda i: f"the figure {_SIDE[by_id[i].side].replace(' of the picture', '')}"  # positions, not names: two men are both "the adult man" to the compiler
    poses = []
    for a in plan.actors:
        hit = next((c for c in plan.contacts if c.source == a.id and c.target in by_id), None)
        action = ""
        if hit:
            action = f"directed at {pos(hit.target)}" + (f" with the {hit.body_part}" if hit.body_part else "") + (f", moving {hit.direction}" if hit.direction else "")
        poses.append(CharPose(id=a.id, side=a.side, pose=a.action_state, expression=a.expression, action=action))
    layers = " ".join(f"{k.capitalize()}: {v}." for k, v in plan.depth.items())
    light = ", ".join(x for x in (f"light from {_LIGHT[plan.light.direction]}", plan.light.quality, plan.light.color) if x)
    spec = ShotSpec(shot=plan.camera.distance, camera=plan.camera.angle, characters=poses, setting=layers, lighting=light, mood=plan.mood,
                    key_visuals=[f"the {c.body_part or 'action'} of {pos(c.source)} meets {pos(c.target)}" for c in plan.contacts if c.source in by_id and c.target in by_id])
    return story, spec, "place"


def compile_scene_prompt(plan: ScenePlan, *, emphasis: list[str] | None = None, lessons: str = "",
                         target: str = "qwen_image_21") -> tuple[str, str, tuple[int, int]]:
    """(positive, negative, (width, height)). `emphasis` is what the last attempt failed to show: stated first, like the refine loop does.
    `lessons` is guidance learned from past failures, written as positive statements and added to the END of the positive prompt: measured on this PC the
    Qwen Turbo workflow ignores the negative prompt completely (same seed, empty vs strong negative: pixel difference 0.0)."""
    story, spec, loc = plan_to_shotspec(plan)
    compiled = PromptCompiler.compile_image_prompt(story, spec, loc, target=target)
    camera = CAMERA_FIX[plan.camera.angle] if plan.camera.angle != "eye_level" and CAMERA_FIX[plan.camera.angle] not in lessons else ""
    rules = " ".join(x for x in (camera, lessons.strip()) if x)
    positive = f"{compiled.positive} Remember: {rules}" if rules else compiled.positive
    if emphasis:
        positive = f"Most important: {'; '.join(e.rstrip('. ') for e in emphasis)}. {positive}"
    return positive, compiled.negative, tuple(compiled.dimensions)


def plan_requirements(plan: ScenePlan) -> list[Claim]:
    """What a viewer must be able to SEE. Actor count, each actor's side and action state, contacts and camera angle are critical; framing,
    light and depth layers are not. Mood is a feeling, not a visible fact, so it is never a requirement."""
    who = {a.id: describe_actor(a) for a in plan.actors}
    n = len(plan.actors)
    count = "there are no people in the picture" if n == 0 else "exactly one figure is in the picture" if n == 1 else \
        f"exactly {_NUMBER.get(n, n)} figures are in the picture"
    out = [Claim(text=count, critical=True, kind="subject")]
    for a in plan.actors:
        out.append(Claim(text=f"{who[a.id]} is {_SIDE[a.side]}", critical=True, kind="placement"))
        out.append(Claim(text=f"{who[a.id]} is {a.action_state}", critical=True, kind="pose"))
    for c in plan.contacts:
        if c.source in who and c.target in who:
            text = f"{who[c.source]} reaches {who[c.target]}" + (f" with the {c.body_part}" if c.body_part else "") + (f", aimed {c.direction}" if c.direction else "")
            out.append(Claim(text=text, critical=True, kind="pose"))
    out.append(Claim(text=_CAMERA[plan.camera.angle], critical=True, kind="camera"))
    out.append(Claim(text=f"the framing is a {plan.camera.distance} shot", critical=False, kind="framing"))
    out.append(Claim(text=f"the main light comes from {_LIGHT[plan.light.direction]}", critical=False, kind="environment"))
    out += [Claim(text=f"the {layer} shows {what}", critical=False, kind="environment") for layer, what in plan.depth.items()]
    return out
