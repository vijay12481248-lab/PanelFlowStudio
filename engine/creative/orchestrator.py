"""Autonomous Multi-Agent Orchestrator for Novel & Storyboard Production.

Directs the collaboration between:
- ShowrunnerAgent (Story Bible, World Lore, Character Roster)
- NovelistAgent (Deep Narrative Prose & Dialogue)
- EditorialCriticAgent (Continuity & Emotional Polish)
- CinematographerAgent (Visual Scene & Shot Decomposition)
- PromptCompilerAgent (Qwen Image 2.1 & MiniMax H3 Compilations)
- CreativeVault (Persistence & ChronoFlow Vault Synchronization)
"""
from __future__ import annotations

import logging
import re
import uuid
from typing import Callable, Optional

from engine.creative.agents import (
    CinematographerAgent,
    EditorialCriticAgent,
    NovelistAgent,
    PromptCompilerAgent,
    ShowrunnerAgent,
)
from engine.creative.schema import (
    CreativeProject,
    NovelChapter,
    RegressionAuditVerdict,
    SelfImprovementReport,
    StorySeed,
)
from engine.creative.mistakes import MistakeAuditor, MistakeLedger
from engine.creative.self_improvement import ExperienceMemoryVault, SelfImprovementEngine
from engine.creative.vault import CreativeVault

logger = logging.getLogger("panelflow.creative.orchestrator")


class CreativeOrchestrator:
    """End-to-end multi-agent production coordinator."""

    def __init__(self, vault: Optional[CreativeVault] = None):
        self.vault = vault or CreativeVault()
        self.memory_vault = ExperienceMemoryVault(self.vault.vault_dir / "heuristics.json")
        self.mistake_ledger = MistakeLedger(self.vault.vault_dir / "mistakes_ledger.json")
        self.self_improver = SelfImprovementEngine(self.memory_vault)
        self.auditor = MistakeAuditor(self.mistake_ledger)
        self.showrunner = ShowrunnerAgent()
        self.novelist = NovelistAgent()
        self.critic = EditorialCriticAgent()
        self.cinematographer = CinematographerAgent()
        self.prompt_compiler = PromptCompilerAgent()

    async def synthesize_story(
        self,
        seed: StorySeed,
        progress_callback: Optional[Callable[[str, float], None]] = None,
    ) -> CreativeProject:
        """Execute full autonomous multi-agent creation cycle from an abstract seed."""
        def _report(msg: str, pct: float):
            logger.info(f"[{pct*100:.0f}%] {msg}")
            if progress_callback:
                progress_callback(msg, pct)

        _report("Phase 1/5: Showrunner Agent synthesizing Story Bible and character lore...", 0.1)
        bible = await self.showrunner.create_story_bible(seed)

        # Synchronize characters into ChronoFlow's characters.json immediately
        self.vault.sync_characters_from_bible(bible.characters)
        protagonist = bible.characters[0] if bible.characters else None

        _report(f"Phase 2/5: Novelist Agent crafting Chapter 1 of '{bible.title}'...", 0.3)
        chapters: list[NovelChapter] = []
        self_improvement_reports: list[SelfImprovementReport] = []

        for outline in bible.chapter_outlines[: seed.target_chapters]:
            chapter = await self.novelist.write_chapter(bible, outline)

            _report(f"Phase 3/5: Autonomous Self-Improvement Loop evaluating Chapter {chapter.chapter_number}...", 0.5)
            improved_chapter, report = await self.self_improver.execute_self_improvement_prose_cycle(
                bible, chapter
            )
            self_improvement_reports.append(report)
            chapters.append(improved_chapter)

        _report("Phase 4/5: Cinematographer Agent decomposing narrative into visual scene beats & shots...", 0.7)
        primary_chapter = chapters[0] if chapters else None
        if primary_chapter:
            scenes = await self.cinematographer.deconstruct_chapter_to_scenes(
                bible=bible,
                chapter=primary_chapter,
                num_scenes=3,
                shots_per_scene=3,
            )
        else:
            scenes = []

        _report("Phase 5/5: Compiling Qwen Image 2.1 art prompts & MiniMax H3 6-heading chains...", 0.85)
        self.prompt_compiler.process_scenes(scenes, protagonist)

        # Post-Execution Regression Auditing: Verify zero past mistakes were repeated
        regression_audits: list[RegressionAuditVerdict] = []
        if scenes:
            cine_verdict = self.auditor.audit_cinematography(scenes)
            regression_audits.append(cine_verdict)
            for sc in scenes:
                for sh in sc.shots:
                    prompt_verdict = self.auditor.audit_h3_prompt(sh)
                    if not prompt_verdict.passed:
                        regression_audits.append(prompt_verdict)

        # Package project
        project_slug = re.sub(r"[^a-z0-9]+", "_", bible.title.lower()).strip("_")
        project_id = f"{project_slug}_{uuid.uuid4().hex[:6]}"

        project = CreativeProject(
            project_id=project_id,
            title=bible.title,
            seed=seed,
            bible=bible,
            chapters=chapters,
            scenes=scenes,
            parent_path=seed.parent_folder or f"D:\\panelflow_studio\\{bible.title.replace(' ', '_')}",
            status="completed",
            self_improvement_reports=self_improvement_reports,
            regression_audits=regression_audits,
        )

        # Persist project and export ChronoFlow Screenplay JSON
        self.vault.save_project(project)
        _report(f"Creative production completed successfully: '{project.title}'", 1.0)
        return project
