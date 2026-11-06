"""Image reviewer: does this picture show what the narration says? Evidence, confidence and a decision - accept or redraw.

Why it exists: the first checker described the picture and asked one model whether "everything required" was visible. It
accepted a picture whose narration was "Elena turns her head upward, her eyes locking onto the single silver bell hanging high on
the wall" although the bell was a speck on her head and she looked sideways, because (a) the director's key-visual list had lost the
bell, and (b) the judge marked nearly everything missing and the loop kept the best of three anyway.

The reviewer therefore works from the NARRATION itself, independently of the shot director, and uses two separate witnesses:

1. claims   : an LLM lists the visible facts the narration asserts (who, what they do, where they look, objects with colour and
               position, count of people), each marked critical or not.
2. witness A: the vision model answers one numbered question per requirement with yes / partly / no and the visible evidence.
3. witness B: the same vision model writes a free description of the picture, and a text-only model says whether that description
               states each requirement.
4. verdict  : per requirement - both witnesses agree -> shown/missing with high confidence; they disagree -> partial with low confidence.
5. decision : accept (no critical miss, score >= 0.75, confidence >= 0.6), accept_low (no critical miss, score >= 0.6: kept but
               flagged), otherwise regenerate. After the last attempt a picture that still fails is never silently accepted: it is
               marked needs_review and listed in the report.
"""
from __future__ import annotations

import html
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter
from pydantic import BaseModel, Field

from engine.original.shotspec import ShotSpec
from engine.original.models import Character, Claim, ItemVerdict, Review

ACCEPT_SCORE, ACCEPT_CONFIDENCE, LOW_SCORE = 0.75, 0.6, 0.6
VERDICT_SCORE = {"shown": 1.0, "partial": 0.5, "missing": 0.0}
RANK = {"accept": 2, "accept_low": 1, "regenerate": 0}


class AuditVerdictList(list):
    """List of ItemVerdict with convenience properties for audit validation gates."""

    @property
    def passed(self) -> bool:
        return all(getattr(v, "passed", True) and getattr(v, "verdict", "shown") == "shown" for v in self)

    @property
    def failures(self) -> list[ItemVerdict]:
        return [v for v in self if not getattr(v, "passed", True) or getattr(v, "verdict", "shown") != "shown"]

    @property
    def critical_failures(self) -> list[ItemVerdict]:
        return [v for v in self if getattr(v, "critical", False) and (not getattr(v, "passed", True) or getattr(v, "verdict", "shown") != "shown")]

    @property
    def decision(self) -> str:
        return "accept" if self.passed else "regenerate"

    @property
    def defects(self) -> list[str]:
        return [getattr(v, "defect_type", "") or v.item for v in self.failures]


class _Claims(BaseModel):
    claims: list[Claim] = Field(description="the visible facts the narration asserts, at most 6")


class _QA(BaseModel):
    n: int
    answer: str = Field(description="yes, partly or no")
    evidence: str = Field(default="", description="what is visible that supports the answer, at most 12 words")


class _VQA(BaseModel):
    answers: list[_QA]


class _DescJudge(BaseModel):
    stated: list[bool] = Field(description="for each numbered requirement, whether the description states it, in order")



STOP = {"the", "and", "that", "with", "from", "into", "this", "there", "their", "they", "them", "her", "his", "she", "for", "are", "was",
        "has", "have", "who", "what", "which", "while", "over", "onto", "than", "then", "its", "any", "all", "one", "single", "very"}
NEGATIVE_CLAIM = ("no visible", "not visible", "not visibly", "there is no", "is not ", "are not ", "cannot be seen")


def _content(text: str) -> set[str]:
    return {w.strip(".,;:!?'\"()").lower().rstrip("s") for w in text.split() if len(w) > 3 and w.lower() not in STOP}


def clean_claims(claims: list[Claim], narration: str) -> list[Claim]:
    """A claim must be a positive, visible statement that comes from THIS narration: no negations, no proper nouns (the cast is
    checked separately), and at least one content word the narration actually uses. A small model otherwise parrots the cast list."""
    said = _content(narration)
    seen, out = set(), []
    for c in claims:
        t = " ".join(c.text.split())
        words = t.split()
        proper = any(w[:1].isupper() and k > 0 for k, w in enumerate(words))
        if not t or t.lower() in seen or proper or any(n in t.lower() for n in NEGATIVE_CLAIM) or not (_content(t) & said):
            continue
        seen.add(t.lower())
        out.append(Claim(text=t[:140], critical=c.critical, category=getattr(c, "category", "narration"),
                         defect_type=getattr(c, "defect_type", ""), interaction_target=getattr(c, "interaction_target", "")))
    return out[:6]


async def extract_claims(provider, narration: str) -> list[Claim]:
    prompt = ("Narration that will be read aloud over a picture:\n\"" + narration + "\"\n\n"
              "List the facts in it that can be SEEN in a single picture: which people or creatures, what each is doing, which way they "
              "look, objects with their colour and position, the place. Use only what the narration says. Skip ideas, feelings, names of "
              "places or people, and anything not visible. Mark a claim critical if the picture is wrong without it (a named object, an "
              "action, a gaze direction). Write each claim as a short positive statement, e.g. 'a silver bell hangs high on the wall'.")
    out = await provider.generate_structured(prompt, _Claims, system_prompt="You extract visual requirements precisely.", temperature=0.0,
                                             max_tokens=500, num_ctx=8192)
    return clean_claims(out.claims, narration)


def requirements(claims: list[Claim], spec: ShotSpec | None, chars: dict[str, Character]) -> list[tuple[str, bool]]:
    """Narration claims first (critical as judged), then what the shot director added: who is visible, how many, the place."""
    reqs: list[tuple[str, bool]] = [(c.text, c.critical) for c in claims]
    if spec is not None:
        n = len(spec.characters)
        reqs.append(("there are no people in the picture" if n == 0 else f"exactly {n} {'person or creature is' if n == 1 else 'people or creatures are'} visible", True))
        for c in spec.characters:
            ch = chars.get(c.id)
            if ch:
                reqs.append((f"{ch.look.split(',')[0].strip()} {('(' + ch.species + ')') if ch.species != 'human' else 'character'} is visible", False))
        if spec.setting:
            reqs.append((spec.setting.split(".")[0].split(":")[-1].strip()[:90], False))
    out, seen = [], set()
    for t, crit in reqs:
        key = " ".join(sorted(set(t.lower().split())))
        if t and key not in seen:
            seen.add(key)
            out.append((t, crit))
    return out[:10]


async def _vqa(provider, image: Path, reqs: list[tuple[str, bool]]) -> list[_QA]:
    if not reqs:
        return []
    qs = "\n".join(f"{i + 1}. Is this true of the picture: {t}?" for i, (t, _) in enumerate(reqs))
    prompt = ("Look carefully at this illustration and answer each question with yes, partly or no. 'yes' only if it is clearly visible; "
              "'partly' if it is there but small, hidden or different; 'no' if it is absent or contradicted. Give the visible evidence.\n" + qs)
    raw = await provider.analyze_vision(image, prompt, format_schema=_VQA.model_json_schema(), max_tokens=900, temperature=0.0)
    try:
        if isinstance(raw, dict):
            by_n = {a["n"]: _QA(**a) for a in raw.get("answers", [])}
        elif isinstance(raw, _VQA):
            by_n = {a.n: a for a in raw.answers}
        else:
            by_n = {a.n: a for a in _VQA.model_validate_json(raw).answers}
    except Exception:
        by_n = {}
    return [by_n.get(i + 1, _QA(n=i + 1, answer="partly", evidence="no answer")) for i in range(len(reqs))]


async def _describe(provider, image: Path) -> str:
    try:
        res = await provider.analyze_vision(
            image, "Describe this illustration literally for someone who cannot see it: each character (kind, hair, clothes), body pose, "
            "face, where they look, what they hold or do, objects and where they are, the place and the light. Do not guess. At most 110 words.",
            max_tokens=1100, temperature=0.0)
        return str(res).strip()
    except Exception:
        return ""


async def _description_states(provider, description: str, reqs: list[tuple[str, bool]]) -> list[bool]:
    if not reqs:
        return []
    if not hasattr(provider, "generate_structured"):
        return [True] * len(reqs)
    lst = "\n".join(f"{i + 1}. {t}" for i, (t, _) in enumerate(reqs))
    prompt = (f"DESCRIPTION OF A PICTURE:\n{description}\n\nREQUIREMENTS:\n{lst}\n\nFor each numbered requirement say whether the description "
              "states it or clearly implies it (different wording counts). Answer with one true/false per requirement, in order.")
    try:
        out = await provider.generate_structured(prompt, _DescJudge, system_prompt="You are a strict, literal reader.", temperature=0.0,
                                                 max_tokens=300, num_ctx=8192)
        if isinstance(out, dict):
            flags = list(out.get("stated", []))[:len(reqs)]
        else:
            flags = list(out.stated)[:len(reqs)]
    except Exception:
        flags = []
    return flags + [False] * (len(reqs) - len(flags))


ANATOMY_CHECKS: list[tuple[str, str]] = [
    ("single head per person or creature with no polycephaly, duplicate heads, or fused faces", "polycephaly"),
    ("correct number of limbs with no extra arms, extra legs, duplicate limbs, or mutated appendages", "extra_limbs"),
    ("complete body structure with no missing limbs, severed arms, or amputated body parts (accounting for frame cropping)", "missing_limbs"),
    ("for any human characters visible, natural hands and feet with anatomically correct digits and no extra or fused fingers", "distorted_digits"),
    ("valid limb topology and joint connections with natural bending angles and plausible skeletal structure", "limb_topology"),
]

DEFECT_KEYWORDS = {
    "polycephaly": (
        "two heads", "extra head", "multiple heads", "duplicate head", "polycephaly",
        "second head", "fused head", "fused heads", "two faces", "too many heads",
        "multiple faces", "duplicate face", "double head", "conjoined head",
    ),
    "extra_limbs": (
        "extra arm", "extra leg", "three arms", "three legs", "four arms", "extra limb",
        "third arm", "third leg", "additional limb", "multiple arms", "duplicate arm",
        "duplicate leg", "extra hands", "third hand", "too many limbs", "too many arms",
        "too many legs", "too many hands", "five limbs", "supernumerary",
    ),
    "missing_limbs": (
        "missing arm", "missing leg", "amputated", "severed arm", "severed leg",
        "no arm", "no leg", "missing limb", "truncated limb", "detached limb",
        "severed hand", "severed limb",
    ),
    "distorted_digits": (
        "six fingers", "seven fingers", "fused fingers", "distorted hand", "deformed hand",
        "extra finger", "missing finger", "malformed hand", "distorted digits", "twisted fingers",
        "webbed fingers", "extra thumb", "clawed hand", "mangled fingers", "mutated hand",
        "too many fingers", "deformed fingers", "distorted fingers", "malformed fingers",
        "mutated fingers", "fused digits", "extra digits", "missing digits", "duplicate fingers",
        "six-fingered", "polydactyly", "syndactyly",
    ),
    "limb_topology": (
        "bent backwards", "impossible joint", "broken joint", "twisted limb", "unnatural angle",
        "dislocated", "inverted joint", "broken bone", "anatomically impossible", "reversed joint",
        "twisted backwards", "bent the wrong way",
    ),
    "unanchored_object": (
        "floating object", "unanchored", "floating in air", "floating in the air", "hovering in air",
        "hovering in the air", "suspended in air", "suspended in the air", "floating cup",
        "floating book", "floating sword", "floating lamp", "floating tray", "levitating",
        "hovering object", "floating in mid-air", "floating mid-air", "hovering in mid-air",
        "hovering mid-air", "suspended in mid-air", "suspended mid-air", "floating in midair",
        "floating midair", "hovering in midair", "hovering midair", "suspended in midair",
        "suspended midair", "levitating object", "unsupported floating",
    ),
    "disconnected_interaction": (
        "disconnected", "not touching", "hovering near hand", "not held", "no contact",
        "floating near", "detached", "floating next to", "not grasped", "not being held",
        "floating away from hand", "hovering above hand", "separated from hand",
        "gap between hand", "detached from grip",
    ),
}

NEGATION_PREFIX_PATTERN = re.compile(
    r'\b(no|not|without|zero|neither|none|never|free\s+of|lack(?:s|ing)?|absence\s+of|devoid\s+of)\b(?:\s+\w+){0,3}\s*$',
    re.IGNORECASE
)

BENIGN_ANATOMY_EXPLANATION_PATTERN = re.compile(
    r'\b('
    r'(?:in|inside)\s+(?:[^\s,;.\!?]+\s+){0,3}pockets?|'
    r'hands?\s+(?:are\s+)?(?:in|inside)\s+(?:[^\s,;.\!?]+\s+){0,3}pockets?|'
    r'behind\s+(?:the|his|her|their)?\s*back|'
    r'out\s+of\s+frame|'
    r'outside\s+(?:the\s+)?frame|'
    r'not\s+in\s+frame|'
    r'cropped(?:\s+out)?|'
    r'cropping|'
    r'cut\s+off\s+by\s+frame|'
    r'portrait(?:\s+shot)?|'
    r'close-?up(?:\s+shot)?|'
    r'bust\s+shot|'
    r'waist\s+up|'
    r'hidden(?:\s+from\s+view)?|'
    r'concealed|'
    r'obscured|'
    r'covered\s+by|'
    r'in\s+sleeves?|'
    r'under\s+(?:the\s+)?table|'
    r'behind\s+(?:the\s+)?desk|'
    r'facing\s+away|'
    r'from\s+behind|'
    r'turned\s+away|'
    r'back\s+turned|'
    r'back\s+of\s+(?:the\s+|his\s+|her\s+)?head|'
    r'no\s+(?:people|person|characters?|humans?|figures?|creatures?)|'
    r'empty\s+(?:scene|room|landscape)|'
    r'landscape\s+only|'
    r'scenery\s+only|'
    r'nobody\s+(?:is\s+)?visible'
    r')\b',
    re.IGNORECASE,
)

BENIGN_SPATIAL_EXPLANATION_PATTERN = re.compile(
    r'\b('
    r'no\s+(?:objects?|props?|furniture|items?)|'
    r'empty\s+(?:scene|room|landscape|meadow|plain)|'
    r'outdoor\s+landscape|'
    r'scenery\s+only|'
    r'landscape\s+only|'
    r'nothing\s+floating|'
    r'reaching(?:\s+for)?|'
    r'not\s+yet\s+touching|'
    r'approaching|'
    r'resting\s+on\s+(?:the\s+)?(?:table|shelf|ground|floor|surface)|'
    r'on\s+the\s+(?:table|shelf|ground|floor)|'
    r'not\s+(?:yet\s+)?picked\s+up'
    r')\b',
    re.IGNORECASE,
)


def _has_defect_keyword(text: str, defect_type: str) -> bool:
    """Return True if text asserts a defect, ignoring negated mentions like 'no extra limbs'."""
    keywords = DEFECT_KEYWORDS.get(defect_type, ())
    if not keywords or not text:
        return False
    t = text.lower()
    for kw in keywords:
        for m in re.finditer(r'\b' + re.escape(kw) + r'\b', t):
            prefix = t[:m.start()]
            clause = re.split(r'[,;.\!?\n]', prefix)[-1]
            if not NEGATION_PREFIX_PATTERN.search(clause):
                return True
    return False


INTERACTION_VERBS = {
    "hold", "holds", "holding", "held",
    "grasp", "grasps", "grasping", "grasped",
    "grip", "grips", "gripping", "gripped",
    "carry", "carries", "carrying", "carried",
    "wield", "wields", "wielding", "wielded",
    "touch", "touches", "touching", "touched",
    "clutch", "clutches", "clutching", "clutched",
    "lift", "lifts", "lifting", "lifted",
    "pull", "pulls", "pulling", "pulled",
    "push", "pushes", "pushing", "pushed",
    "catch", "catches", "catching", "caught",
    "grab", "grabs", "grabbing", "grabbed",
    "take", "takes", "taking", "took",
    "reach", "reaches", "reaching", "reached",
    "brandish", "brandishes", "brandishing", "brandished",
    "hoist", "hoists", "hoisting", "hoisted",
    "pick", "picks", "picking", "picked",
    "clasp", "clasps", "clasping", "clasped",
    "snatch", "snatches", "snatching", "snatched",
    "seize", "seizes", "seizing", "seized",
}

NON_PROP_OBJECTS = {
    # Body parts / self-touches
    "hand", "hands", "arm", "arms", "finger", "fingers", "fist", "fists",
    "head", "face", "back", "chest", "shoulder", "shoulders", "chin", "cheek",
    "cheeks", "mouth", "lip", "lips", "neck", "throat", "hair", "waist", "hip",
    "hips", "knee", "knees", "leg", "legs", "foot", "feet", "heart", "belly",
    "stomach", "forehead", "eyebrow", "eyebrows",
    # Architectural / environmental surfaces / heavy furniture
    "ground", "floor", "wall", "walls", "door", "doors", "ceiling", "table",
    "tables", "chair", "chairs", "desk", "desks", "bench", "counter", "bed",
    "window", "windows", "air", "sky",
    # Abstract / non-physical concepts / action idioms
    "breath", "eye", "eyes", "tear", "tears", "gaze", "sight", "voice",
    "silence", "peace", "attention", "focus", "still", "stillness", "pace",
    "step", "steps", "seat", "pose",
    # Adverbs / particles / directions
    "up", "down", "on", "out", "away", "off", "back", "fast", "tight",
    "tightly", "firmly", "gently", "softly", "carefully", "closely", "slowly",
    "quickly", "hard", "deeply", "around", "close",
    # Pronouns
    "someone", "anyone", "everyone", "nobody", "nothing", "something",
    "anything", "everything", "himself", "herself", "itself", "themselves",
    "myself", "yourself", "him", "them", "her", "me", "us", "it",
}

OBJECT_PRONOUNS = {
    "him", "them", "her", "me", "us", "it", "someone", "anyone", "everyone", "nobody", "something",
}

CONNECTING_PARTICLES = {
    "up", "out", "down", "away", "off", "back", "tight", "tightly", "firmly",
    "for", "at", "to", "onto", "on", "into", "from", "against", "towards", "toward",
    "hold", "of",
}

STOP_ADVERBS = {
    "firmly", "tightly", "gently", "softly", "carefully", "closely", "slowly",
    "quickly", "hard", "deeply", "tight", "still", "again", "now", "then", "close",
}

STOP_PREPOSITIONS = {
    "in", "on", "at", "with", "by", "to", "from", "into", "onto",
    "against", "over", "under", "and", "while", "as", "for", "of",
    "before", "after", "through", "or", "so", "but",
}

LEADING_DETERMINERS = {
    "a", "an", "the", "her", "his", "their", "its", "my", "your",
    "this", "that", "some", "one", "two", "both",
}

VERB_PATTERN = re.compile(
    r'\b(' + '|'.join(sorted(INTERACTION_VERBS, key=len, reverse=True)) + r')\b',
    re.IGNORECASE
)


def _extract_interaction_targets(
    claims: list[Claim] | None = None,
    spec: ShotSpec | None = None,
    caption: str = "",
) -> list[tuple[str, str]]:
    """Extract (verb, target_object) pairs mentioned in claims, director spec, or caption."""
    targets: list[tuple[str, str]] = []
    seen_objects = set()

    if claims:
        for c in claims:
            target = getattr(c, "interaction_target", "")
            if target and target.lower() not in seen_objects and target.lower() not in NON_PROP_OBJECTS:
                seen_objects.add(target.lower())
                targets.append(("interact", target))

    texts = []
    if caption:
        texts.append(caption)
    if claims:
        for c in claims:
            if not getattr(c, "interaction_target", ""):
                texts.append(c.text)
    if spec:
        for ch in spec.characters:
            if getattr(ch, "action", ""):
                texts.append(ch.action)

    for t in texts:
        for m in VERB_PATTERN.finditer(t):
            verb = m.group(1).lower()
            remainder = t[m.end():]
            first_clause = re.split(r'[,;.\!?\n]', remainder)[0]
            words = [w.strip() for w in first_clause.split() if w.strip()]
            while words and (words[0].lower() in CONNECTING_PARTICLES or words[0].lower() in LEADING_DETERMINERS):
                words.pop(0)
            if words and words[0].lower() in OBJECT_PRONOUNS:
                continue
            prop_words = []
            for w in words:
                clean_w = re.sub(r'[^a-zA-Z\-]', '', w).lower()
                if not clean_w or clean_w in STOP_PREPOSITIONS or clean_w in STOP_ADVERBS:
                    break
                prop_words.append(clean_w)
                if len(prop_words) == 4:
                    break
            if prop_words:
                candidate = " ".join(prop_words)
                last_word = prop_words[-1]
                if last_word not in NON_PROP_OBJECTS and candidate not in NON_PROP_OBJECTS:
                    if candidate.lower() not in seen_objects:
                        seen_objects.add(candidate.lower())
                        targets.append((verb, candidate))
    return targets


async def _audit_anatomy(
    provider,
    image: Path,
    spec: ShotSpec | None = None,
    description: str = "",
) -> AuditVerdictList:
    """Vision-based anatomical integrity audit via two-witness review pattern."""
    if spec is not None and len(spec.characters) == 0:
        return AuditVerdictList([])

    if not description:
        description = await _describe(provider, image)

    reqs = [(text, True) for text, _ in ANATOMY_CHECKS]
    qa = await _vqa(provider, image, reqs)

    desc_lower = description.lower()
    verdicts = []
    for (text, defect_type), a in zip(ANATOMY_CHECKS, qa):
        v = a.answer.strip().lower()
        v = "yes" if v.startswith("y") else "no" if v.startswith("n") else "partly"

        witness_a_explicit_defect = _has_defect_keyword(a.evidence, defect_type)
        witness_b_explicit_defect = _has_defect_keyword(description, defect_type)

        is_benign = bool(BENIGN_ANATOMY_EXPLANATION_PATTERN.search(a.evidence))

        witness_a_defect = witness_a_explicit_defect or (v in ("no", "partly") and not is_benign)
        witness_b_defect = witness_b_explicit_defect

        has_defect = witness_a_defect or witness_b_defect

        if not has_defect:
            verdict, conf = "shown", 0.9
            passed = True
            v_final = "yes"
            desc_agrees = True
        elif witness_a_defect and witness_b_defect:
            verdict, conf = "missing", 0.9
            passed = False
            v_final = "no"
            desc_agrees = False
        elif witness_a_defect:
            verdict, conf = "missing", 0.7
            passed = False
            v_final = v
            desc_agrees = False
        else:
            verdict, conf = "missing", 0.7
            passed = False
            v_final = "no"
            desc_agrees = False

        verdicts.append(ItemVerdict(
            item=text,
            critical=True,
            verdict=verdict,
            confidence=conf,
            vision=v_final,
            description_says=desc_agrees,
            evidence=a.evidence,
            category="anatomy",
            defect_type=defect_type,
            passed=passed,
        ))

    return AuditVerdictList(verdicts)


async def _audit_spatial_contact(
    provider,
    image: Path,
    claims: list[Claim] | None = None,
    spec: ShotSpec | None = None,
    description: str = "",
    caption: str = "",
) -> AuditVerdictList:
    """Vision-based spatial contact and grasp verification via two-witness pattern."""
    checks: list[tuple[str, str]] = [
        ("all objects, props, and furniture are physically supported or resting on surfaces with no unanchored floating objects", "unanchored_object")
    ]

    interactions = _extract_interaction_targets(claims, spec, caption)
    for verb, obj in interactions[:3]:
        checks.append((
            f"the {obj} is physically held or touched with continuous grasp contact and is not floating or disconnected",
            "disconnected_interaction"
        ))

    if not description:
        description = await _describe(provider, image)

    reqs = [(text, True) for text, _ in checks]
    qa = await _vqa(provider, image, reqs)

    desc_lower = description.lower()
    verdicts = []
    for (text, defect_type), a in zip(checks, qa):
        v = a.answer.strip().lower()
        v = "yes" if v.startswith("y") else "no" if v.startswith("n") else "partly"

        witness_a_explicit_defect = _has_defect_keyword(a.evidence, defect_type)
        witness_b_explicit_defect = _has_defect_keyword(description, defect_type)

        is_benign = bool(BENIGN_SPATIAL_EXPLANATION_PATTERN.search(a.evidence))

        witness_a_defect = witness_a_explicit_defect or (v in ("no", "partly") and not is_benign)
        witness_b_defect = witness_b_explicit_defect

        has_defect = witness_a_defect or witness_b_defect

        if not has_defect:
            verdict, conf = "shown", 0.9
            passed = True
            v_final = "yes"
            desc_agrees = True
        elif witness_a_defect and witness_b_defect:
            verdict, conf = "missing", 0.9
            passed = False
            v_final = "no"
            desc_agrees = False
        elif witness_a_defect:
            verdict, conf = "missing", 0.7
            passed = False
            v_final = v
            desc_agrees = False
        else:
            verdict, conf = "missing", 0.7
            passed = False
            v_final = "no"
            desc_agrees = False

        verdicts.append(ItemVerdict(
            item=text,
            critical=True,
            verdict=verdict,
            confidence=conf,
            vision=v_final,
            description_says=desc_agrees,
            evidence=a.evidence,
            category="spatial_contact",
            defect_type=defect_type,
            passed=passed,
        ))

    return AuditVerdictList(verdicts)


def combine(
    reqs: list[tuple[str, bool]] | list[Claim],
    qa: list[_QA],
    stated: list[bool],
    description: str = "",
    audit_items: list[ItemVerdict] | None = None,
) -> Review:
    """Pure decision logic: two witnesses per requirement -> verdict, confidence, score and accept/regenerate."""
    items: list[ItemVerdict] = []
    for req, a, said in zip(reqs, qa, stated):
        text = req.text if isinstance(req, Claim) else req[0]
        crit = req.critical if isinstance(req, Claim) else req[1]
        cat = getattr(req, "category", "narration")
        defect = getattr(req, "defect_type", "")
        v = a.answer.strip().lower()
        v = "yes" if v.startswith("y") else "no" if v.startswith("n") else "partly"
        if v == "yes" and said:
            verdict, conf = "shown", 0.9
        elif v == "no" and not said:
            verdict, conf = "missing", 0.9
        elif v == "yes":
            verdict, conf = "shown", 0.5  # only the vision answer says so: believed, but not twice
        elif v == "no":
            verdict, conf = "partial", 0.4  # the description mentions it, the question says no: unclear
        else:
            verdict, conf = "partial", 0.6
        passed = (verdict == "shown")
        items.append(ItemVerdict(item=text, critical=crit, verdict=verdict, confidence=conf, vision=v,
                                 description_says=said, evidence=a.evidence, category=cat, defect_type=defect, passed=passed))

    if audit_items:
        items.extend(audit_items)

    if not items:
        return Review(items=[], score=1.0, confidence=0.0, decision="accept_low", reasons=["nothing to check"], description=description)

    w = [2.0 if i.critical else 1.0 for i in items]
    score = sum(wi * VERDICT_SCORE[i.verdict] for wi, i in zip(w, items)) / sum(w)
    confidence = sum(wi * i.confidence for wi, i in zip(w, items)) / sum(w)

    crit_missing = [i.item for i in items if i.critical and i.verdict == "missing" and i.category == "narration"]
    crit_partial = [i.item for i in items if i.critical and i.verdict == "partial" and i.category == "narration"]
    reasons = [f"critical item not shown: {t}" for t in crit_missing] + [f"critical item unclear: {t}" for t in crit_partial]

    # Quality Gate Failures (Anatomy and Spatial Contact)
    anatomy_fails = [i for i in items if i.category == "anatomy" and (not getattr(i, "passed", True) or i.verdict != "shown")]
    spatial_fails = [i for i in items if i.category == "spatial_contact" and (not getattr(i, "passed", True) or i.verdict != "shown")]

    for af in anatomy_fails:
        reasons.append(f"critical anatomical failure [{af.defect_type or 'defect'}]: {af.item} ({af.evidence or af.verdict})")
    for sf in spatial_fails:
        reasons.append(f"critical spatial contact failure [{sf.defect_type or 'defect'}]: {sf.item} ({sf.evidence or sf.verdict})")

    anatomy_passed = len(anatomy_fails) == 0
    spatial_passed = len(spatial_fails) == 0
    defects = [i.defect_type or i.item for i in anatomy_fails + spatial_fails]

    if not anatomy_passed or not spatial_passed:
        decision = "regenerate"
    elif not crit_missing and not crit_partial and score >= ACCEPT_SCORE and confidence >= ACCEPT_CONFIDENCE:
        decision = "accept"
    elif not crit_missing and score >= LOW_SCORE:
        decision = "accept_low"
        reasons.append(f"score {score:.2f} / confidence {confidence:.2f} is below the accept bar")
    else:
        decision = "regenerate"

    return Review(
        items=items,
        score=round(score, 3),
        confidence=round(confidence, 3),
        decision=decision,
        reasons=reasons,
        description=description,
        anatomy_passed=anatomy_passed,
        spatial_contact_passed=spatial_passed,
        defects=defects,
    )


async def review_image(
    provider,
    image: Path,
    claims: list[Claim],
    spec: ShotSpec | None,
    chars: dict[str, Character],
    audit_gates: bool = True,
    caption: str = "",
) -> Review:
    reqs = requirements(claims, spec, chars)
    if not reqs and not audit_gates:
        return combine([], [], [], "")

    description = await _describe(provider, image)
    qa = await _vqa(provider, image, reqs) if reqs else []
    stated = await _description_states(provider, description, reqs) if reqs else []

    audit_items: list[ItemVerdict] = []
    if audit_gates:
        anatomy_items = await _audit_anatomy(provider, image, spec=spec, description=description)
        spatial_items = await _audit_spatial_contact(provider, image, claims=claims, spec=spec, description=description, caption=caption)
        audit_items.extend(anatomy_items)
        audit_items.extend(spatial_items)

    return combine(reqs, qa, stated, description, audit_items=audit_items)


def write_report(story_panels: list, ws: Path, records: list[dict]) -> Path:
    """review_report.html: each picture beside its narration, the decision and every requirement with both witnesses' answers."""
    by_id = {r["panel_id"]: r for r in records}
    rows = []
    for p in story_panels:
        r = by_id.get(p.id)
        if not r:
            continue
        rev = r.get("review") or {}
        status = r.get("status", "")
        items = "".join(
            f"<tr class='{html.escape(i['verdict'])}'><td>{'★ ' if i['critical'] else ''}{html.escape(i['item'])}</td><td>{html.escape(i['verdict'])}</td>"
            f"<td>{i['confidence']:.1f}</td><td>{html.escape(i['vision'])}: {html.escape(i.get('evidence', ''))}</td></tr>" for i in rev.get("items", []))
        rows.append(
            f"<section class='{html.escape(status)}'><img src='panels/{html.escape(p.id)}.png' width='480'><div><h3>{html.escape(p.id)} "
            f"<span class='b'>{html.escape(status)}</span> score {rev.get('score', '-')} confidence {rev.get('confidence', '-')} "
            f"attempts {r.get('attempts')}</h3><p>{html.escape(p.caption)}</p><table>{items}</table>"
            f"<p class='desc'>{html.escape(rev.get('description', ''))}</p></div></section>")
    css = ("body{font-family:sans-serif;max-width:1100px;margin:20px auto;background:#111;color:#eee}section{display:flex;gap:16px;margin:18px 0;"
           "padding:12px;border-radius:8px;background:#1b1b1f}h3{margin:0 0 6px}.b{padding:2px 8px;border-radius:10px;background:#444;font-size:12px}"
           "section.accept .b{background:#1c6b3a}section.accept_low .b{background:#8a6d12}section.needs_review .b{background:#8b2b2b}"
           "table{border-collapse:collapse;font-size:12px}td{border-bottom:1px solid #333;padding:3px 8px}tr.missing td{color:#f08080}"
           "tr.partial td{color:#e6c35c}.desc{font-size:12px;color:#aaa}")
    out = ws / "review_report.html"
    out.write_text(f"<!doctype html><meta charset='utf-8'><title>Picture review</title><style>{css}</style><h1>Picture review</h1>" + "".join(rows),
                   encoding="utf-8")
    return out


INPAINT_CORRECTION_PROMPTS: dict[str, tuple[str, str]] = {
    "distorted_digits": (
        "detailed anatomical hand, five fingers, correct digits, natural hand pose, well-defined fingers, perfect anatomy",
        "bad anatomy, extra digits, missing fingers, fused fingers, distorted hand, polydactyly, syndactyly, deformed digits, six fingers",
    ),
    "polycephaly": (
        "single head, symmetrical face, natural neck, serene anime face, perfect head proportions",
        "multiple heads, two faces, duplicate head, fused heads, conjoined head, deformed face, two heads",
    ),
    "extra_limbs": (
        "correct number of limbs, natural anatomical arms and legs, proper proportions, anatomically correct body",
        "extra limbs, extra arms, extra legs, mutated appendages, duplicate limbs, three arms, four arms",
    ),
    "missing_limbs": (
        "complete body structure, intact limbs, natural anatomy, fully rendered arms and legs",
        "missing limbs, amputated, severed limbs, truncated limbs, missing arms",
    ),
    "limb_topology": (
        "natural limb topology, natural bending angles, plausible skeletal joints, correct anatomy",
        "bent backwards, impossible joints, twisted limbs, broken bones, unnatural angles, inverted joints",
    ),
    "unanchored_object": (
        "grounded object resting firmly on surface, contact shadow, stable placement, realistic physics",
        "floating object, hovering in air, unanchored object, levitating, suspended in mid-air",
    ),
    "disconnected_interaction": (
        "firmly gripping object, fingers wrapped around handle, direct physical contact, continuous grasp, zero gap",
        "disconnected grip, hovering near hand, floating object, detached, gap between hand and object, not touching",
    ),
}

DEFECT_HEURISTIC_REGIONS: dict[str, tuple[float, float, float, float]] = {
    "polycephaly": (0.15, 0.05, 0.85, 0.45),
    "extra_limbs": (0.10, 0.25, 0.90, 0.90),
    "missing_limbs": (0.10, 0.25, 0.90, 0.90),
    "limb_topology": (0.15, 0.30, 0.85, 0.85),
    "unanchored_object": (0.20, 0.35, 0.80, 0.85),
    "disconnected_interaction": (0.15, 0.35, 0.85, 0.85),
}


def extract_defect_mask(
    image_size: tuple[int, int],
    verdicts: list[ItemVerdict] | Review,
    padding: int = 32,
    blur_radius: int = 12,
) -> Image.Image | None:
    """Extract a feathered binary defect mask (PIL L-mode, 255=defect, 0=background) from review findings.

    Returns None if no anatomical or spatial defects are present.
    """
    if isinstance(verdicts, Review):
        items = verdicts.items
    else:
        items = verdicts or []

    defects = [
        i for i in items
        if (not getattr(i, "passed", True) or getattr(i, "verdict", "shown") != "shown")
        and (getattr(i, "defect_type", "") or getattr(i, "category", "") in ("anatomy", "spatial_contact"))
    ]
    if not defects:
        return None

    w, h = image_size
    bboxes: list[tuple[int, int, int, int]] = []

    for d in defects:
        b = getattr(d, "bbox", None)
        if b and len(b) == 4:
            # Check if normalized coordinates in [0..1]
            if all(isinstance(v, (int, float)) and 0.0 <= v <= 1.0 for v in b):
                x1, y1 = int(b[0] * w), int(b[1] * h)
                x2, y2 = int(b[2] * w), int(b[3] * h)
            else:
                x1, y1, x2, y2 = int(b[0]), int(b[1]), int(b[2]), int(b[3])
            x1, x2 = max(0, min(x1, x2)), min(w, max(x1, x2))
            y1, y2 = max(0, min(y1, y2)), min(h, max(y1, y2))
            if x2 > x1 and y2 > y1:
                bboxes.append((x1, y1, x2, y2))
                continue

        # Coordinate-based heuristics based on defect type and evidence
        dtype = getattr(d, "defect_type", "")
        ev = (getattr(d, "evidence", "") or "").lower()

        if dtype == "distorted_digits":
            if "left" in ev:
                rel = (0.05, 0.40, 0.55, 0.85)
            elif "right" in ev:
                rel = (0.45, 0.40, 0.95, 0.85)
            else:
                rel = (0.20, 0.40, 0.80, 0.85)
        else:
            rel = DEFECT_HEURISTIC_REGIONS.get(dtype, (0.15, 0.20, 0.85, 0.80))

        x1 = max(0, int(rel[0] * w))
        y1 = max(0, int(rel[1] * h))
        x2 = min(w, int(rel[2] * w))
        y2 = min(h, int(rel[3] * h))
        if x2 > x1 and y2 > y1:
            bboxes.append((x1, y1, x2, y2))

    if not bboxes:
        return None

    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    for bx1, by1, bx2, by2 in bboxes:
        px1 = max(0, bx1 - padding)
        py1 = max(0, by1 - padding)
        px2 = min(w, bx2 + padding)
        py2 = min(h, by2 + padding)
        draw.rectangle([px1, py1, px2, py2], fill=255)

    if blur_radius > 0:
        mask = mask.filter(ImageFilter.GaussianBlur(radius=blur_radius))

    return mask


def build_inpaint_correction_prompt(
    verdicts: list[ItemVerdict] | Review,
    base_prompt: str = "",
) -> tuple[str, str]:
    """Build targeted, generic inpaint positive and negative correction prompts for identified defects.

    Strictly generic per AGENTS.md: contains no story-specific or character-specific strings.
    """
    if isinstance(verdicts, Review):
        items = verdicts.items
    else:
        items = verdicts or []

    failed_dtypes = [
        getattr(i, "defect_type", "")
        for i in items
        if (not getattr(i, "passed", True) or getattr(i, "verdict", "shown") != "shown")
        and getattr(i, "defect_type", "")
    ]

    if not failed_dtypes:
        failed_dtypes = ["distorted_digits"]

    pos_parts: list[str] = []
    neg_parts: list[str] = []

    for dt in failed_dtypes:
        if dt in INPAINT_CORRECTION_PROMPTS:
            p, n = INPAINT_CORRECTION_PROMPTS[dt]
            pos_parts.append(p)
            neg_parts.append(n)

    if not pos_parts:
        p, n = INPAINT_CORRECTION_PROMPTS["distorted_digits"]
        pos_parts.append(p)
        neg_parts.append(n)

    pos_combined = ", ".join(dict.fromkeys(pos_parts))
    neg_combined = ", ".join(dict.fromkeys(neg_parts))

    if base_prompt:
        positive_prompt = f"{pos_combined}, {base_prompt}".strip(", ")
    else:
        positive_prompt = pos_combined

    return positive_prompt, neg_combined


def splice_repaired_image(
    base_img: Image.Image,
    repaired_img: Image.Image,
    mask: Image.Image,
) -> Image.Image:
    """Splice the repaired image into the base image using the feathered mask.

    Pixels where mask is 0 remain identical to base_img; pixels where mask is 255 come from repaired_img.
    """
    if base_img.size != repaired_img.size:
        repaired_img = repaired_img.resize(base_img.size, Image.Resampling.LANCZOS)
    if mask.size != base_img.size:
        mask = mask.resize(base_img.size, Image.Resampling.LANCZOS)
    base_rgb = base_img.convert("RGB")
    repaired_rgb = repaired_img.convert("RGB")
    mask_l = mask.convert("L")
    return Image.composite(repaired_rgb, base_rgb, mask_l)
