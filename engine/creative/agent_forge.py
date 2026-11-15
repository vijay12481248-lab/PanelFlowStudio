"""Dynamic Agent Forge & Autonomous Skill Synthesizer.

Enables the creative agent swarm to synthesize, validate, persist, and execute
new specialized subagents and reusable skills (SKILL.md) on the fly whenever
a domain gap (e.g. Manhua Layout, SFX Lettering, Cultivation Lore) is identified.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from engine.creative.knowledge import CreativeKnowledgeBase
from engine.creative.mistakes import MistakeLedger
from engine.creative.schema import (
    DynamicAgentSpec,
    DynamicSkillSpec,
    KnowledgeCategory,
    KnowledgeEntry,
)

logger = logging.getLogger("panelflow.creative.agent_forge")

VAULT_DIR = Path(__file__).resolve().parents[1] / "chronoflow" / "vault"
AGENTS_FILE = VAULT_DIR / "dynamic_agents.json"
SKILLS_DIR = Path(__file__).resolve().parent / "skills"


class AgentForge:
    """Autonomous factory and registry for forging new specialized creative agents."""

    def __init__(
        self,
        agents_file: Optional[Path] = None,
        mistake_ledger: Optional[MistakeLedger] = None
    ):
        self.agents_file = agents_file or AGENTS_FILE
        self.ledger = mistake_ledger or MistakeLedger()
        self.agents_file.parent.mkdir(parents=True, exist_ok=True)
        self._runtime_agents: Dict[str, DynamicAgentSpec] = {}
        self._load_all()

    def forge_agent(
        self,
        role_name: str,
        domain: str,
        description: str,
        system_prompt: str,
        required_capabilities: Optional[List[str]] = None,
        anti_patterns_to_enforce: Optional[List[str]] = None,
        anti_patterns: Optional[List[str]] = None,
        created_by: str = "AgentForge"
    ) -> DynamicAgentSpec:
        """Synthesize, validate, and persist a new specialized agent."""
        clean_role = re.sub(r"[^a-zA-Z0-9_ ]+", "", role_name).strip()
        if not clean_role:
            raise ValueError("Role name cannot be empty")
        if not system_prompt.strip():
            raise ValueError("System prompt cannot be empty")

        # Inject known anti-patterns for the specified domain
        domain_anti_patterns = list(anti_patterns or anti_patterns_to_enforce or [])
        known_anti_patterns = self.ledger.load_mistakes(domain)
        for m in known_anti_patterns:
            if m.flawed_pattern not in domain_anti_patterns:
                domain_anti_patterns.append(f"[{m.mistake_id}] {m.flawed_pattern}: {m.prevention_rule}")

        spec = DynamicAgentSpec(
            role_name=clean_role,
            domain=domain.strip().lower(),
            description=description.strip(),
            system_prompt=system_prompt.strip(),
            required_capabilities=required_capabilities or ["reasoning", "knowledge_retrieval"],
            anti_patterns_to_enforce=domain_anti_patterns,
            created_by=created_by,
            created_at=datetime.now().isoformat()
        )

        self._runtime_agents[clean_role.lower()] = spec
        self._save_all()
        logger.info("Successfully forged new creative agent: %s (%s)", spec.role_name, spec.domain)
        return spec

    def get_agent(self, role_name: str) -> Optional[DynamicAgentSpec]:
        return self._runtime_agents.get(role_name.strip().lower())

    def list_agents(self, domain: Optional[str] = None) -> List[DynamicAgentSpec]:
        all_specs = list(self._runtime_agents.values())
        if domain:
            return [s for s in all_specs if s.domain.lower() == domain.strip().lower()]
        return all_specs

    def list_forged_agents(self, domain: Optional[str] = None) -> List[DynamicAgentSpec]:
        return self.list_agents(domain=domain)

    def delete_agent(self, role_name: str) -> bool:
        """Decommission and remove a dynamic agent specification."""
        key = role_name.strip().lower()
        if key in self._runtime_agents:
            del self._runtime_agents[key]
            self._save_all()
            logger.info("Successfully deleted dynamic agent: %s", role_name)
            return True
        return False

    def _load_all(self):
        if not self.agents_file.exists():
            # Seed foundational specialized subagents
            self._seed_default_agents()
            return
        try:
            with open(self.agents_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data:
                    spec = DynamicAgentSpec(**item)
                    self._runtime_agents[spec.role_name.lower()] = spec
        except Exception as e:
            logger.error("Failed to load dynamic agents from disk: %s", e)
            self._seed_default_agents()

    def _save_all(self):
        try:
            data = [spec.model_dump() for spec in self._runtime_agents.values()]
            temp = self.agents_file.with_suffix(".tmp")
            with open(temp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            temp.replace(self.agents_file)
        except Exception as e:
            logger.error("Failed to persist dynamic agents to disk: %s", e)

    def _seed_default_agents(self):
        """Seed foundational specialized agents for Manhua, Lettering, and Cultivation."""
        seeds = [
            (
                "ManhuaPanelLayoutAgent",
                "manhua_layout",
                "Specialist in vertical webtoon canvas slicing, gutter timing, and diagonal kinetic panels.",
                (
                    "You are a master Webtoon & Manhua Layout Director. Your role is to convert prose and story beats "
                    "into continuous vertical-scroll panels. You calculate optimal gutter heights (temporal delay), "
                    "determine camera angle compositions (heroic low angle vs Dutch tilt action cuts), and ensure "
                    "kinetic speed lines guide the reader's eye downward naturally."
                )
            ),
            (
                "SFXLettererAgent",
                "dialogue_and_sfx",
                "Integrates dynamic stylized onomatopoeia and speech bubbles directly into the visual composition.",
                (
                    "You are an elite Comic & Graphic Novel SFX Letterer. You formulate integrated onomatopoeia "
                    "('BOOM', 'SWOOSH', 'KRA-KATH') and speech balloon geometry that reflects emotional volume and Qi resonance. "
                    "You ensure text is never cluttered (max 25 words per action panel) and sound effects slice dynamically behind characters."
                )
            ),
            (
                "CultivationLoreAgent",
                "cultivation_xianxia",
                "Ensures authentic Xianxia/Cultivation terminology, dantian energy auras, realm hierarchies, and martial arts.",
                (
                    "You are a scholar of Xianxia and Cultivation narrative traditions. You ensure character techniques, "
                    "spiritual root affinities, tribulation lightning, pill formulas, and sect politics adhere to grand mythological standards."
                )
            )
        ]
        for name, domain, desc, prompt in seeds:
            try:
                self.forge_agent(name, domain, desc, prompt, created_by="SystemSeed")
            except Exception:
                pass


class SkillBuilder:
    """Synthesizes reusable, executable markdown skill packages for agents."""

    def __init__(
        self,
        skills_dir: Optional[Path] = None,
        skills_base_dir: Optional[Path] = None,
        knowledge_base: Optional[CreativeKnowledgeBase] = None,
        kb: Optional[CreativeKnowledgeBase] = None,
    ):
        self.skills_dir = skills_dir or skills_base_dir or SKILLS_DIR
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.kb = kb or knowledge_base or CreativeKnowledgeBase()

    def synthesize_skill(
        self,
        skill_name: str,
        domain: str,
        description: str,
        instructions_markdown: Optional[str] = None,
        heuristics: Optional[List[str]] = None,
        anti_patterns: Optional[List[str]] = None,
        examples_bad: Optional[List[str]] = None,
        examples_good: Optional[List[str]] = None
    ) -> Tuple[Path, DynamicSkillSpec]:
        """Create and persist a standardized SKILL.md package and ingest into Knowledge Base."""
        slug = re.sub(r"[^a-z0-9_-]+", "-", skill_name.strip().lower()).strip("-")
        skill_folder = self.skills_dir / slug
        skill_folder.mkdir(parents=True, exist_ok=True)
        skill_md_path = skill_folder / "SKILL.md"

        instructions = (instructions_markdown or f"Standard operating procedures and guidelines for {skill_name} in domain '{domain}'.").strip()
        heur_list = heuristics or []
        anti_list = anti_patterns or []
        ex_bad = examples_bad or []
        ex_good = examples_good or []

        # Format standardized Antigravity SKILL.md
        lines = [
            "---",
            f"name: {slug}",
            f"description: {description.strip()}",
            f"domain: {domain.strip().lower()}",
            "---",
            "",
            f"# {skill_name.strip()}",
            "",
            f"> {description.strip()}",
            "",
            "## Core Directorial Instructions",
            instructions,
            "",
            "## Directorial Heuristics & Best Practices"
        ]
        for h in heur_list:
            lines.append(f"- ✓ {h}")
        if not heur_list:
            lines.append("- ✓ Follow vertical visual flow and preserve character continuity.")

        lines.append("\n## Anti-Patterns & Pitfalls to Avoid")
        for a in anti_list:
            lines.append(f"- ❌ {a}")
        if not anti_list:
            lines.append("- ❌ Avoid overcrowded text balloons in action panels.")

        if ex_bad or ex_good:
            lines.append("\n## Reference Examples")
            for b in ex_bad:
                lines.append(f"❌ **AVOID**: \"{b}\"")
            for g in ex_good:
                lines.append(f"✓ **APPLY**: \"{g}\"")

        skill_content = "\n".join(lines)
        with open(skill_md_path, "w", encoding="utf-8") as f:
            f.write(skill_content)

        spec = DynamicSkillSpec(
            skill_name=slug,
            domain=domain.strip().lower(),
            description=description.strip(),
            instructions_markdown=instructions,
            heuristics=heur_list,
            anti_patterns=anti_list,
            examples_bad=ex_bad,
            examples_good=ex_good,
            created_at=datetime.now().isoformat()
        )

        # Ingest skill into Knowledge Base for instant agent retrieval
        kb_entry = KnowledgeEntry(
            entry_id=f"kb_skill_{slug}",
            category=KnowledgeCategory.PANEL_COMPOSITION,
            title=f"Skill: {skill_name.strip()}",
            content=f"Description: {description}\n\nInstructions:\n{instructions_markdown}\n\nHeuristics:\n" + "\n".join(heur_list),
            tags=["skill", slug, domain.strip().lower()],
            source=f"SkillBuilder: {slug}",
            confidence_score=0.98
        )
        self.kb.add_entry(kb_entry)

        logger.info("Successfully synthesized and persisted skill [%s] at %s", slug, skill_md_path)
        return skill_folder, spec

    def delete_skill(self, skill_name: str) -> bool:
        """Delete a synthesized skill package and remove it from Knowledge Base."""
        import shutil
        slug = re.sub(r"[^a-z0-9_-]+", "-", skill_name.strip().lower()).strip("-")
        skill_folder = self.skills_dir / slug
        deleted = False
        if skill_folder.exists():
            shutil.rmtree(skill_folder, ignore_errors=True)
            deleted = True
        self.kb.delete_entry(f"kb_skill_{slug}")
        logger.info("Deleted skill [%s] (folder removed: %s)", slug, deleted)
        return deleted

    def list_skills(self) -> List[Dict[str, str]]:
        skills = []
        for p in self.skills_dir.glob("*/SKILL.md"):
            try:
                text = p.read_text(encoding="utf-8")
                name_match = re.search(r"^name:\s*(.+)$", text, re.MULTILINE)
                desc_match = re.search(r"^description:\s*(.+)$", text, re.MULTILINE)
                skills.append({
                    "skill_name": name_match.group(1).strip() if name_match else p.parent.name,
                    "description": desc_match.group(1).strip() if desc_match else "",
                    "path": str(p)
                })
            except Exception:
                pass
        return sorted(skills, key=lambda x: x["skill_name"])

    def load_skill_instructions(self, skill_name: str) -> Optional[str]:
        slug = re.sub(r"[^a-z0-9_-]+", "-", skill_name.strip().lower()).strip("-")
        target = self.skills_dir / slug / "SKILL.md"
        if target.exists():
            return target.read_text(encoding="utf-8")
        return None
