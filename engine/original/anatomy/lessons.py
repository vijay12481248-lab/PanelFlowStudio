"""What an image model gets wrong about bodies, kept per model so the next prompt can say it positively.

Built on the same `MistakeLedger` as the Scene Director's lessons (pass a file under the app-data folder, never the repo's vault ledger). A failure is keyed by its kind
and the pose word (`<kind>|<pose or any>`), never by story words. klein and Qwen ignore negative prompts (cfg 1), so every rule is a positive sentence appended to the end
of the prompt. A failure is a rule after two sightings; the rules the owner-checked audit of 2026-11-16 established start active and say so in `example_good`.
"""
from __future__ import annotations

import re

from engine.creative.mistakes import MistakeLedger
from engine.creative.schema import MistakeSeverity
from engine.original.anatomy.review import AnatomyReport
from engine.original.anatomy.rules import pose_asks

RULES = {
    "extra_hands|any": "Exactly two arms and two hands per person, no extra arms or hands anywhere, and nothing but the legs in the lap.",
    "stray_text|any": "No letters, numbers or writing anywhere in the picture.",
    "duplicate_object|any": "Each held object is drawn exactly once, nothing doubled.",
    "merged_bodies|any": "Each person's body is clearly separate, and every arm and leg can be traced to its owner.",
    "pose_missing|cross_legged": "The person sits on the floor with both legs crossed in front of them.",
    "pose_missing|hands_on_knees": "Both hands rest on the person's own knees and nothing lies in their lap.",
    "pose_missing|kick": "One leg is raised high and fully extended in a kick.",
    "pose_missing|raised_leg": "One leg is raised high off the ground.",
    "pose_missing|two_hands": "Both hands grip the object together.",
}
# A rule that talks about held objects is only added when the prompt names one: the first wording ("exactly one sword") made klein draw a sword into calm sitting
# pictures (real end-to-end run, 2026-11-16).
ONLY_WHEN = {"duplicate_object|any": re.compile(r"\b(sword|blade|weapon|staff|spear|knife|dagger|axe|bow|katana)\b", re.I)}
SEED_MARK = "agent-labelled 2026-11-16 audit"
SEEDED = ("extra_hands|any", "duplicate_object|any")  # klein: four arms in cross-legged seeds 101 and 103; a ghost second blade in sword seeds 101 and 103
DEFAULT_MODEL = "hidream_i1_fast"


def domain(model: str) -> str:
    return f"anatomy:{model}"


def _key(kind: str, pose: str | None) -> str:
    return f"{kind}|{pose or 'any'}"


def record_report(ledger: MistakeLedger, model: str, report: AnatomyReport) -> int:
    """One sighting per confirmed defect key; suspected defects teach nothing (one noisy judge is not a lesson). Returns how many keys were written."""
    seen: set[str] = set()
    for d in report.confirmed:
        key = _key(d.kind, d.pose)
        if key in seen or key not in RULES:
            continue
        seen.add(key)
        ledger.record_or_escalate_mistake(domain=domain(model), flawed_pattern=key, prevention_rule=RULES[key], category=d.kind, severity=MistakeSeverity.HIGH)
    return len(seen)


def rules_for(ledger: MistakeLedger, model: str, prompt: str, min_recurrence: int = 2) -> str:
    """The active rules that fit this prompt, most frequent first: every general rule, and a pose rule only when the prompt asks for that pose. "" on any ledger problem."""
    try:
        asked = {k for k, _ in pose_asks(prompt)[0]}
        rows = [r for r in ledger.load_mistakes(domain(model)) if r.recurrence_count >= min_recurrence
                and (not r.flawed_pattern.startswith("pose_missing|") or r.flawed_pattern.split("|", 1)[1] in asked)
                and (r.flawed_pattern not in ONLY_WHEN or ONLY_WHEN[r.flawed_pattern].search(prompt or ""))]
        return " ".join(RULES.get(r.flawed_pattern, r.prevention_rule) for r in sorted(rows, key=lambda r: -r.recurrence_count))
    except Exception:
        return ""


def seed_known_rules(ledger: MistakeLedger, model: str = DEFAULT_MODEL) -> int:
    """Make the audited klein failures active from day one (recurrence 2). Idempotent; returns how many rules were added or raised."""
    changed = 0
    for key in SEEDED:
        existing = next((r for r in ledger.load_mistakes(domain(model)) if r.flawed_pattern == key), None)
        if existing is not None and existing.recurrence_count >= 2:
            continue
        rec = ledger.record_or_escalate_mistake(domain=domain(model), flawed_pattern=key, prevention_rule=RULES[key], example_good=SEED_MARK,
                                                category=key.split("|")[0], severity=MistakeSeverity.HIGH)
        if rec.recurrence_count < 2:
            ledger.record_or_escalate_mistake(domain=domain(model), flawed_pattern=key, prevention_rule=RULES[key], category=key.split("|")[0])
        changed += 1
    return changed
