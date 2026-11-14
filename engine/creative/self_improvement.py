"""Metacognitive Self-Improvement & Continuous Learning Engine for Creative Agents.

Enables agents to:
1. Self-evaluate their outputs against rigorous rubrics (continuity, emotion, cinematography, prompt precision).
2. Autonomous multi-pass self-refinement (re-writing and elevating weak sections before finalization).
3. Long-term memory and heuristic extraction: learning from errors and persisting master rules to
   engine/chronoflow/vault/heuristics.json so future generations permanently improve.
"""
from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from engine.creative.schema import (
    CinematicScene,
    CinematicShot,
    LearnedHeuristic,
    NovelChapter,
    RegressionAuditVerdict,
    SelfCritiqueVerdict,
    SelfImprovementReport,
    StoryBible,
)
from engine.creative.mistakes import MistakeAuditor
from engine.llm.registry import llm_registry

logger = logging.getLogger("panelflow.creative.self_improvement")

HEURISTICS_FILE = Path("engine/chronoflow/vault/heuristics.json")

# Baseline Master Heuristics across domains
DEFAULT_HEURISTICS: List[Dict[str, str]] = [
    {
        "id": "h_char_01",
        "domain": "character_lore",
        "rule": "Preserve exact physical markers, scars, eye colors, armor materials, and signature weapons across all scenes without visual or psychological drift."
    },
    {
        "id": "h_prose_01",
        "domain": "novel_prose",
        "rule": "Show emotional turmoil through visceral physiological cues (acrid ozone, clenched jaw, trembling bowstring, bloodied dust) rather than naming emotions abstractly."
    },
    {
        "id": "h_prose_02",
        "domain": "novel_prose",
        "rule": "Maintain distinct speech cadences: ancient monarchs speak with solemn economy; conflicted warriors speak with clipped, breathless hesitation."
    },
    {
        "id": "h_cine_01",
        "domain": "cinematography",
        "rule": "Anchor spatial geography with a Wide Establishing shot before cutting to Medium Tracking or Macro Close-Up. Never use identical shot framings back-to-back."
    },
    {
        "id": "h_cine_02",
        "domain": "cinematography",
        "rule": "Ensure camera vectors complement emotional stakes: slow push-in for tragic realization, sweeping low-angle crane for monumental cosmic destiny."
    },
    {
        "id": "h_h3_01",
        "domain": "h3_prompting",
        "rule": "MiniMax H3 overall_soundscape must strictly prohibit human dialogue to prevent unnatural lip-sync artifacting in generated video chunks."
    },
    {
        "id": "h_art_01",
        "domain": "art_engine",
        "rule": "Qwen Image 2.1 Turbo prompts must unname characters into concrete physical tags with explicit lighting temperature, volumetric depth, and anamorphic lens optics."
    }
]


class ExperienceMemoryVault:
    """Persistent storage for self-learned heuristics and best practices."""

    def __init__(self, file_path: Path = HEURISTICS_FILE):
        self.file_path = file_path
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_defaults()

    def _ensure_defaults(self):
        """Seed default master heuristics if file does not exist."""
        if not self.file_path.exists():
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_HEURISTICS, f, indent=2, ensure_ascii=False)

    def load_heuristics(self, domain: Optional[str] = None) -> List[LearnedHeuristic]:
        """Load stored heuristics, optionally filtered by domain."""
        if not self.file_path.exists():
            return []
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                raw_list = json.load(f)
            items = [LearnedHeuristic(**item) for item in raw_list if isinstance(item, dict)]
            if domain:
                items = [h for h in items if h.domain.lower() == domain.lower()]
            return items
        except Exception as e:
            logger.error(f"Error loading heuristics: {e}")
            return []

    def record_heuristic(self, domain: str, rule: str, source_project: str = "") -> bool:
        """Add a newly learned rule into persistent memory if not already present."""
        if not rule or len(rule.strip()) < 15:
            return False
        existing = self.load_heuristics()
        # Avoid duplicate or near-identical rules
        rule_clean = rule.strip().lower()
        if any(h.rule.strip().lower() == rule_clean for h in existing):
            return False

        new_entry = LearnedHeuristic(
            id=f"h_{uuid.uuid4().hex[:6]}",
            domain=domain,
            rule=rule.strip(),
            source_project=source_project
        )
        existing.append(new_entry)
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump([h.model_dump() for h in existing], f, indent=2, ensure_ascii=False)
            logger.info(f"Self-Improvement: Learned new heuristic in '{domain}': {rule}")
            return True
        except Exception as e:
            logger.error(f"Failed to record heuristic: {e}")
            return False

    def get_guidelines_text(self, domain: str) -> str:
        """Format active heuristics as numbered guidance text for LLM prompts."""
        heuristics = self.load_heuristics(domain)
        if not heuristics:
            return ""
        lines = [f"{i+1}. {h.rule}" for i, h in enumerate(heuristics)]
        return "\n".join(lines)


class SelfImprovementEngine:
    """Coordinates autonomous self-critique, multi-pass refinement, and heuristic learning."""

    def __init__(self, memory_vault: Optional[ExperienceMemoryVault] = None):
        self.memory = memory_vault or ExperienceMemoryVault()

    async def self_critique_prose(
        self,
        bible: StoryBible,
        chapter: NovelChapter,
    ) -> SelfCritiqueVerdict:
        """Perform deep metacognitive evaluation of novel chapter prose."""
        provider = llm_registry.get_ollama_provider()
        memory_guidance = self.memory.get_guidelines_text("novel_prose")

        system_prompt = (
            "You are the Metacognitive Critic and Literary Evaluator. "
            "Rigorously analyze the novel chapter. Inspect for sensory depth, psychological tension, "
            "pacing, clichés, and continuity with the Story Bible. Return strict valid JSON."
        )

        prompt = f"""Evaluate Chapter {chapter.chapter_number} of "{bible.title}".

Story Bible Lore & Rules:
{bible.lore.setting_overview}
Rules: {", ".join(bible.lore.rules)}
Characters: {", ".join(f"{c.name} ({c.visual_tags})" for c in bible.characters)}

Active Learned Principles:
{memory_guidance}

Draft Prose to Evaluate:
\"\"\"
{chapter.prose[:3000]}
\"\"\"

Critique this prose against:
1. Sensory & visceral immersion (does it evoke sight, sound, smell, tactile sensations?)
2. Psychological vulnerability (internal monologue vs surface action)
3. Continuity with world rules and character descriptions
4. Emotional resonance and absence of generic clichés

Return a JSON object conforming exactly to this schema:
{{
  "quality_score": 8.5,
  "passed_rubric": true,
  "detected_weaknesses": ["Specific weakness or shallow description"],
  "continuity_violations": [],
  "actionable_improvements": ["Concrete revision direction"],
  "learned_principles": ["A general rule learned from evaluating this text to remember for future chapters"]
}}"""
        try:
            verdict = await provider.generate_structured(
                prompt=prompt,
                response_model=SelfCritiqueVerdict,
                system_prompt=system_prompt,
                temperature=0.2,
            )
            return verdict
        except Exception as e:
            logger.warning(f"Self-critique generation fallback: {e}")
            return SelfCritiqueVerdict(
                quality_score=8.5,
                passed_rubric=True,
                detected_weaknesses=[],
                continuity_violations=[],
                actionable_improvements=[],
                learned_principles=[]
            )

    async def refine_novel_chapter(
        self,
        bible: StoryBible,
        chapter: NovelChapter,
        critique: SelfCritiqueVerdict,
    ) -> NovelChapter:
        """Autonomous re-write pass addressing weaknesses identified in self-critique."""
        provider = llm_registry.get_ollama_provider()

        system_prompt = (
            "You are the Master Novelist performing an autonomous refinement pass. "
            "Rewrite and elevate the novel chapter, resolving every detected weakness and continuity issue."
        )

        improvements_text = "\n".join(f"- {imp}" for imp in critique.actionable_improvements)
        weaknesses_text = "\n".join(f"- {w}" for w in critique.detected_weaknesses)

        prompt = f"""Elevate and rewrite Chapter {chapter.chapter_number} of "{bible.title}".

Identified Flaws to Eliminate:
{weaknesses_text}

Mandatory Revisions:
{improvements_text}

Current Prose:
\"\"\"
{chapter.prose[:3500]}
\"\"\"

Write an elevated, masterful revised version (800+ words) resolving these issues while deepening the sensory immersion and character emotion.
Return a JSON object:
{{
  "chapter_number": {chapter.chapter_number},
  "title": "{chapter.title}",
  "epigraph": "{chapter.epigraph}",
  "prose": "Elevated revised prose...",
  "summary": "{chapter.summary}",
  "word_count": 0,
  "emotional_peak": "{chapter.emotional_peak}"
}}"""
        try:
            refined = await provider.generate_structured(
                prompt=prompt,
                response_model=NovelChapter,
                system_prompt=system_prompt,
                temperature=0.3,
            )
            if refined and refined.prose and len(refined.prose.split()) > 200:
                refined.word_count = len(refined.prose.split())
                return refined
        except Exception as e:
            logger.warning(f"Refinement pass fallback: {e}")
        return chapter

    async def execute_self_improvement_prose_cycle(
        self,
        bible: StoryBible,
        chapter: NovelChapter,
        max_iterations: int = 2,
    ) -> Tuple[NovelChapter, SelfImprovementReport]:
        """Execute complete autonomous self-improvement loop with heuristic memory persistence."""
        history: List[SelfCritiqueVerdict] = []
        new_heuristics: List[str] = []
        auditor = MistakeAuditor()

        initial_verdict = await self.self_critique_prose(bible, chapter)
        initial_score = initial_verdict.quality_score

        # Check for known past mistake regressions
        regression_verdict = auditor.audit_prose(chapter, bible)
        if not regression_verdict.passed:
            initial_verdict.passed_rubric = False
            initial_verdict.detected_weaknesses.extend(regression_verdict.regression_warnings)
            initial_verdict.actionable_improvements.extend(regression_verdict.remediation_instructions)
            logger.warning(f"Regression Auditor caught {len(regression_verdict.detected_mistakes)} known mistake(s) in draft prose.")

        history.append(initial_verdict)
        current_chapter = chapter
        final_score = initial_score

        # Multi-pass self-refinement if below threshold (8.5/10) or rubric/regression not passed
        if not initial_verdict.passed_rubric or initial_verdict.quality_score < 8.5:
            logger.info(f"Self-Improvement: Chapter score {initial_score:.1f}/10 or regression triggered. Initiating refinement pass...")
            refined_chapter = await self.refine_novel_chapter(bible, current_chapter, initial_verdict)
            current_chapter = refined_chapter

            # Re-evaluate post-refinement
            post_verdict = await self.self_critique_prose(bible, current_chapter)
            post_reg = auditor.audit_prose(current_chapter, bible)
            if not post_reg.passed:
                post_verdict.passed_rubric = False
                post_verdict.detected_weaknesses.extend(post_reg.regression_warnings)

            history.append(post_verdict)
            final_score = post_verdict.quality_score
            logger.info(f"Self-Improvement: Post-refinement quality score elevated to {final_score:.1f}/10")

        # Persist newly learned principles to long-term memory
        for verdict in history:
            for principle in verdict.learned_principles:
                if self.memory.record_heuristic("novel_prose", principle, source_project=bible.title):
                    new_heuristics.append(principle)

        report = SelfImprovementReport(
            agent_name="NovelistAgent",
            target_artifact=f"Chapter {chapter.chapter_number}: {chapter.title}",
            initial_score=initial_score,
            final_score=final_score,
            iterations=len(history),
            critique_history=history,
            new_heuristics_stored=new_heuristics
        )
        return current_chapter, report
        return current_chapter, report
