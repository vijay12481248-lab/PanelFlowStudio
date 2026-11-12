"""Persistent Mistake Ledger, Anti-Pattern Memory, and Regression Auditor.

Guarantees agents learn from their errors and permanently prevent regressions
by cataloging failure patterns, injecting negative constraints into prompts,
and auditing outputs before final acceptance.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.creative.schema import (
    CinematicScene,
    CinematicShot,
    MistakeRecord,
    MistakeSeverity,
    NovelChapter,
    RegressionAuditVerdict,
    StoryBible,
)

logger = logging.getLogger("panelflow.creative.mistakes")

MISTAKES_FILE = Path("engine/chronoflow/vault/mistakes_ledger.json")

# Master Base Anti-Patterns (Pre-seeded from historical failure modes)
DEFAULT_MISTAKES: List[Dict[str, Any]] = [
    {
        "mistake_id": "err_h3_soundscape_speech",
        "domain": "h3_prompting",
        "category": "tool_syntax",
        "flawed_pattern": "Including human speech, dialogue, or spoken battle cries inside MiniMax H3's overall_soundscape.",
        "prevention_rule": "The overall_soundscape must contain exclusively diegetic foley and environment audio (wind, boot crunch, armor rattle, conch blares). It MUST strictly state: 'Strict rule: absolutely no human speech or dialogue.' Human dialogue causes grotesque video mouth-morphing artifacts.",
        "example_bad": "overall_soundscape: War conch blares, soldiers shouting 'Charge!', distant screams.",
        "example_good": "overall_soundscape: War conch blares, heavy boot thuds on gravel, cold wind howl through bronze armor. Strict rule: absolutely no human speech or dialogue.",
        "recurrence_count": 1,
        "severity": "critical"
    },
    {
        "mistake_id": "err_prose_flat_emotion",
        "domain": "novel_prose",
        "category": "sensory_immersion",
        "flawed_pattern": "Using abstract emotional labels ('felt sad', 'was terrified', 'became furious') instead of physical somatic sensations.",
        "prevention_rule": "Never state the emotion as an adjective; evoke the emotion through autonomic body responses (cold sweat, trembling grip on bow, hollow ache in throat, breath catching).",
        "example_bad": "Arjuna was deeply saddened as he looked at Bhishma.",
        "example_good": "A hot, suffocating knot tightened in Arjuna's throat as his fingers slipped against the taut silk of the Gandiva.",
        "recurrence_count": 1,
        "severity": "high"
    },
    {
        "mistake_id": "err_char_visual_drift",
        "domain": "character_lore",
        "category": "continuity",
        "flawed_pattern": "Changing established character appearance, eye color, scars, or armor materials across scenes.",
        "prevention_rule": "Every character's established visual tags must be preserved verbatim in all subsequent descriptions and prompts without hallucinating changes.",
        "example_bad": "Scene 1: Bhishma in weathered golden breastplate. Scene 2: Bhishma in black iron tunic.",
        "example_good": "All scenes: Bhishma in weathered golden breastplate with sun crest, white beard with gold ash.",
        "recurrence_count": 1,
        "severity": "critical"
    },
    {
        "mistake_id": "err_cine_camera_monotony",
        "domain": "cinematography",
        "category": "camera_optics",
        "flawed_pattern": "Using the same camera movement or framing vector in 2 or more consecutive shots (e.g. push-in after push-in).",
        "prevention_rule": "Always alternate shot types and camera vectors: Wide Establishing ➔ Medium Tracking ➔ Macro Close-Up; push-in ➔ lateral track ➔ low-angle tilt.",
        "example_bad": "Shot 1: Slow push-in. Shot 2: Steadicam push-in. Shot 3: Slow push-in.",
        "example_good": "Shot 1: Wide panoramic low-angle crane. Shot 2: Ground-level lateral tracking shot. Shot 3: Macro close-up static push-in.",
        "recurrence_count": 1,
        "severity": "high"
    },
    {
        "mistake_id": "err_art_character_naming",
        "domain": "art_engine",
        "category": "tool_syntax",
        "flawed_pattern": "Using proper names directly in text-to-image prompts without visual descriptor tags.",
        "prevention_rule": "In Qwen Image 2.1 prompts, unname the character into visual tags: 'venerable silver-haired warrior in weathered golden breastplate', not bare proper names that the art model cannot interpret.",
        "example_bad": "Masterpiece photo of Arjuna in Kurukshetra.",
        "example_good": "Masterpiece photo, youthful muscular dark-skinned warrior with crimson archer sash, silver-embossed armguards, taut celestial bow.",
        "recurrence_count": 1,
        "severity": "high"
    }
]


class MistakeLedger:
    """Persistent storage and query engine for cataloged failure patterns."""

    def __init__(self, file_path: Path = MISTAKES_FILE):
        self.file_path = file_path
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_defaults()

    def _ensure_defaults(self):
        """Seed default anti-patterns if ledger file does not exist."""
        if not self.file_path.exists():
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_MISTAKES, f, indent=2, ensure_ascii=False)

    def load_mistakes(self, domain: Optional[str] = None) -> List[MistakeRecord]:
        """Load cataloged mistakes, optionally filtered by domain."""
        if not self.file_path.exists():
            return []
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                raw_list = json.load(f)
            records = [MistakeRecord(**r) for r in raw_list if isinstance(r, dict)]
            if domain:
                records = [r for r in records if r.domain.lower() == domain.lower()]
            return records
        except Exception as e:
            logger.error(f"Error loading mistakes ledger: {e}")
            return []

    def get_anti_patterns_prompt(self, domain: str) -> str:
        """Format domain anti-patterns as strict negative constraints for agent prompts."""
        mistakes = self.load_mistakes(domain)
        if not mistakes:
            return ""

        lines = [
            "### CRITICAL ANTI-PATTERNS & MISTAKES YOU MUST NEVER REPEAT:",
            "Past iterations failed because of these specific mistakes. Violating any of these will trigger immediate rejection:"
        ]
        for m in mistakes:
            lines.append(f"\n❌ [Mistake ID: {m.mistake_id}] (Severity: {m.severity.value.upper()}, Recurred: {m.recurrence_count}x)")
            lines.append(f"• FLAW TO AVOID: {m.flawed_pattern}")
            lines.append(f"• MANDATORY RULE: {m.prevention_rule}")
            if m.example_bad:
                lines.append(f"  - BAD: \"{m.example_bad}\"")
            if m.example_good:
                lines.append(f"  - GOOD: \"{m.example_good}\"")

        return "\n".join(lines)

    def record_or_escalate_mistake(
        self,
        domain: str,
        flawed_pattern: str,
        prevention_rule: str,
        example_bad: str = "",
        example_good: str = "",
        category: str = "general",
        severity: MistakeSeverity = MistakeSeverity.HIGH
    ) -> MistakeRecord:
        """Add a newly discovered mistake or increment recurrence if already known."""
        records = self.load_mistakes()

        # Check for near-duplicate match
        clean_pattern = flawed_pattern.strip().lower()
        for r in records:
            if r.domain.lower() == domain.lower() and (clean_pattern in r.flawed_pattern.lower() or r.flawed_pattern.lower() in clean_pattern):
                r.recurrence_count += 1
                r.last_detected = datetime.now().isoformat()
                if r.recurrence_count >= 3:
                    r.severity = MistakeSeverity.CRITICAL
                self._save_all(records)
                logger.warning(f"Mistake [{r.mistake_id}] recurred (Count: {r.recurrence_count}). Escalated.")
                return r

        # New mistake
        slug = re.sub(r"[^a-z0-9]+", "_", domain.lower() + "_" + category.lower()).strip("_")
        new_record = MistakeRecord(
            mistake_id=f"err_{slug}_{uuid.uuid4().hex[:4]}",
            domain=domain,
            category=category,
            flawed_pattern=flawed_pattern.strip(),
            prevention_rule=prevention_rule.strip(),
            example_bad=example_bad.strip(),
            example_good=example_good.strip(),
            recurrence_count=1,
            severity=severity
        )
        records.append(new_record)
        self._save_all(records)
        logger.info(f"Learned and cataloged new mistake pattern: [{new_record.mistake_id}] in {domain}")
        return new_record

    def record_mistake(
        self,
        domain: str,
        flawed_pattern: str,
        prevention_rule: str,
        example_bad: str = "",
        example_good: str = "",
        category: str = "general",
        severity: MistakeSeverity = MistakeSeverity.HIGH,
    ) -> MistakeRecord:
        """Alias for record_or_escalate_mistake."""
        return self.record_or_escalate_mistake(
            domain=domain,
            flawed_pattern=flawed_pattern,
            prevention_rule=prevention_rule,
            example_bad=example_bad,
            example_good=example_good,
            category=category,
            severity=severity,
        )

    def increment_recurrence(self, mistake_id: str) -> Optional[MistakeRecord]:
        """Increment recurrence counter for a specific caught mistake."""
        records = self.load_mistakes()
        for r in records:
            if r.mistake_id == mistake_id:
                r.recurrence_count += 1
                r.last_detected = datetime.now().isoformat()
                if r.recurrence_count >= 3:
                    r.severity = MistakeSeverity.CRITICAL
                self._save_all(records)
                return r
        return None

    def delete_mistake(self, mistake_id: str) -> bool:
        """Remove a mistake pattern from the ledger (e.g. permanently resolved/deprecated)."""
        records = self.load_mistakes()
        initial_len = len(records)
        records = [r for r in records if r.mistake_id != mistake_id]
        if len(records) < initial_len:
            self._save_all(records)
            logger.info("Deleted mistake pattern [%s] from ledger.", mistake_id)
            return True
        return False

    def _save_all(self, records: List[MistakeRecord]):
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump([r.model_dump() for r in records], f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to persist mistake ledger: {e}")


class MistakeAuditor:
    """Post-execution regression scanner and mistake linter."""

    def __init__(self, ledger: Optional[MistakeLedger] = None):
        self.ledger = ledger or MistakeLedger()

    def audit_prose(self, chapter: NovelChapter, bible: StoryBible) -> RegressionAuditVerdict:
        """Scan drafted novel chapter for known prose anti-patterns."""
        detected = []
        warnings = []
        remediations = []

        prose = chapter.prose.lower()

        # Check 1: Flat emotional declarations
        flat_triggers = ["felt sad", "felt angry", "felt terrified", "was happy", "was scared", "felt afraid", "got very mad"]
        for trig in flat_triggers:
            if trig in prose:
                record = self.ledger.increment_recurrence("err_prose_flat_emotion")
                if not record:
                    record = self.ledger.record_or_escalate_mistake(
                        domain="novel_prose",
                        flawed_pattern="Used flat emotional verb declaration",
                        prevention_rule="Replace emotional labels with somatic visceral cues",
                        severity=MistakeSeverity.HIGH
                    )
                detected.append(record)
                warnings.append(f"Detected flat emotional phrase '{trig}'. Show somatic physical sensations instead of naming the emotion.")
                remediations.append(f"Rewrite passages containing '{trig}' to depict racing pulse, hollow throat, clenched knuckles, or dry breath.")
                break

        # Check 2: Lore/character name check
        if bible.characters:
            # Check full name or significant individual name tokens (e.g. "Bhishma" in "Bhishma Pitamaha")
            found_any = False
            for c in bible.characters:
                c_name = c.name.lower().strip()
                if c_name and c_name in prose:
                    found_any = True
                    break
                name_tokens = [tok for tok in re.split(r"\s+", c_name) if len(tok) >= 3]
                if any(tok in prose for tok in name_tokens):
                    found_any = True
                    break
            if not found_any:
                warnings.append("None of the Story Bible's established characters were mentioned in the chapter prose.")
                remediations.append("Ensure the protagonist and key figures from the Story Bible are actively present.")

        passed = len(detected) == 0 and len(warnings) == 0
        return RegressionAuditVerdict(
            passed=passed,
            detected_mistakes=detected,
            regression_warnings=warnings,
            remediation_instructions=remediations
        )

    def audit_cinematography(self, scenes: List[CinematicScene]) -> RegressionAuditVerdict:
        """Audit scene and shot lists for camera monotony and framing variety."""
        detected = []
        warnings = []
        remediations = []

        all_shots: List[CinematicShot] = [shot for sc in scenes for shot in sc.shots]
        if len(all_shots) >= 3:
            # Check 1: Consecutive identical shot types
            for i in range(len(all_shots) - 2):
                t1, t2, t3 = all_shots[i].shot_type.lower(), all_shots[i+1].shot_type.lower(), all_shots[i+2].shot_type.lower()
                if t1 == t2 == t3:
                    rec = self.ledger.increment_recurrence("err_cine_camera_monotony")
                    if rec:
                        detected.append(rec)
                    warnings.append(f"Shots #{all_shots[i].shot_index}, #{all_shots[i+1].shot_index}, #{all_shots[i+2].shot_index} share identical framing '{t1}'.")
                    remediations.append("Vary shot framings: establish with Wide, follow with Medium Tracking, focus on Macro Close-Up.")
                    break

            # Check 2: Repetitive camera vectors
            moves = [s.camera_movement.lower() for s in all_shots]
            push_in_count = sum(1 for m in moves if "push-in" in m or "push in" in m)
            if push_in_count >= len(all_shots) * 0.75 and len(all_shots) >= 4:
                warnings.append(f"Over 75% of shots ({push_in_count}/{len(all_shots)}) use push-in camera moves.")
                remediations.append("Introduce orbital cranes, lateral tracking glides, and low-angle tilts for dynamic cinematics.")

        passed = len(detected) == 0 and len(warnings) == 0
        return RegressionAuditVerdict(
            passed=passed,
            detected_mistakes=detected,
            regression_warnings=warnings,
            remediation_instructions=remediations
        )

    def audit_h3_prompt(self, shot: CinematicShot) -> RegressionAuditVerdict:
        """Strictly verify MiniMax H3 6-heading prompt formatting and soundscape rules."""
        detected = []
        warnings = []
        remediations = []

        prompt = shot.prompt

        # Check 1: Spoken dialogue in soundscape
        sound_match = re.search(r"overall_soundscape:\s*(.*?)(?=\n\n|\Z)", prompt, re.DOTALL)
        if sound_match:
            sound_text = sound_match.group(1).lower()
            # Check for quotation marks or dialogue indicators in soundscape
            if '"' in sound_text or "'" in sound_text or "shouting '" in sound_text or "whispers '" in sound_text or "says" in sound_text:
                rec = self.ledger.increment_recurrence("err_h3_soundscape_speech")
                if rec:
                    detected.append(rec)
                warnings.append(f"Shot #{shot.shot_index} overall_soundscape contains quoted speech or spoken dialogue.")
                remediations.append("Strip all speech from overall_soundscape and enforce: 'Strict rule: absolutely no human speech or dialogue.'")

            # Check that strict rule is present
            if "no human speech" not in sound_text:
                warnings.append(f"Shot #{shot.shot_index} soundscape is missing the mandatory rule: 'Strict rule: absolutely no human speech or dialogue.'")
                remediations.append("Append 'Strict rule: absolutely no human speech or dialogue.' to the soundscape section.")

        # Check 2: Required 6 headings
        required_headings = [
            "subject_definitions:",
            "summary:",
            "retention_analysis:",
            "detailed_description:",
            "overall_soundscape:",
            "non_diegetic_music:"
        ]
        missing = [h for h in required_headings if h not in prompt]
        if missing:
            warnings.append(f"Shot #{shot.shot_index} prompt is missing required headings: {', '.join(missing)}")
            remediations.append("Ensure all 6 MiniMax H3 prompt headings are explicitly present.")

        passed = len(detected) == 0 and len(warnings) == 0
        return RegressionAuditVerdict(
            passed=passed,
            detected_mistakes=detected,
            regression_warnings=warnings,
            remediation_instructions=remediations
        )

    def audit_output(
        self,
        agent_name: str,
        domain: str,
        content: str,
    ) -> tuple[bool, List[str]]:
        """Audit arbitrary creative content against known domain anti-patterns."""
        mistakes = self.ledger.load_mistakes(domain=domain)
        violations: List[str] = []
        clean_content = content.lower()

        # Check domain-specific anti-pattern trigger phrases
        for m in mistakes:
            # Check bad examples
            if m.example_bad:
                bad_phrase = m.example_bad.lower().strip()
                # Check significant substring (>= 5 chars)
                words = [w for w in re.split(r"[^\w]+", bad_phrase) if len(w) >= 4]
                if words and any(w in clean_content for w in words):
                    # Flag potential violation
                    pass

        # Check explicit prohibited phrases
        if domain in ("narrative", "novel_prose"):
            flat_triggers = [
                "felt very sad", "felt sad", "felt angry", "felt terrified",
                "was happy", "was scared", "became furious", "got very mad"
            ]
            for t in flat_triggers:
                if t in clean_content:
                    violations.append(f"Detected flat emotion '{t}'. Use somatic physical cues instead of naming emotion.")
                    self.ledger.increment_recurrence("err_prose_flat_emotion")

        if domain in ("h3_prompting", "cinematography"):
            if "shouted:" in clean_content or "screamed:" in clean_content:
                violations.append("Dialogue in soundscape: Enforce 'Strict rule: absolutely no human speech or dialogue.'")
                self.ledger.increment_recurrence("err_h3_soundscape_speech")

        passed = len(violations) == 0
        return passed, violations

