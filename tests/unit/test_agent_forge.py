"""Unit tests for PanelFlow Agent Forge and Skill Synthesizer."""

import json
import pytest
from pathlib import Path
from engine.creative.agent_forge import AgentForge, SkillBuilder
from engine.creative.knowledge import CreativeKnowledgeBase
from engine.creative.schema import DynamicAgentSpec, DynamicSkillSpec


@pytest.fixture
def temp_forge_env(tmp_path: Path):
    agents_file = tmp_path / "dynamic_agents.json"
    skills_dir = tmp_path / "skills"
    kb_file = tmp_path / "forge_kb.db"

    kb = CreativeKnowledgeBase(db_path=kb_file)
    forge = AgentForge(agents_file=agents_file)
    builder = SkillBuilder(skills_base_dir=skills_dir, kb=kb)
    return forge, builder, kb, agents_file, skills_dir


def test_forge_agent_synthesis_and_persistence(temp_forge_env):
    """Verify forging a new dynamic agent, anti-pattern attachment, and file persistence."""
    forge, _, _, agents_file, _ = temp_forge_env

    spec = forge.forge_agent(
        role_name="CultivationAuraColorist",
        domain="color_scripting",
        description="Directs color grading and celestial aura gradients for spiritual breakthroughs.",
        system_prompt="You are the master colorist for celestial energy auras in xianxia webtoons.",
        anti_patterns=["Avoid uniform flat neon colors with no core density"],
    )

    assert isinstance(spec, DynamicAgentSpec)
    assert spec.role_name == "CultivationAuraColorist"
    assert spec.domain == "color_scripting"
    assert any("Avoid uniform flat neon" in ap for ap in spec.anti_patterns_to_enforce)

    # Verify persistence on disk
    assert agents_file.exists()
    with open(agents_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert any(a["role_name"] == "CultivationAuraColorist" for a in data)

    # Verify retrieval
    retrieved = forge.get_agent("CultivationAuraColorist")
    assert retrieved is not None
    assert retrieved.role_name == "CultivationAuraColorist"

    # Verify listing
    all_agents = forge.list_agents()
    assert any(a.role_name == "CultivationAuraColorist" for a in all_agents)

    # Verify deletion (decommission)
    deleted = forge.delete_agent("CultivationAuraColorist")
    assert deleted is True
    assert forge.get_agent("CultivationAuraColorist") is None


def test_forge_agent_default_seeds(tmp_path: Path):
    """Verify default specialized subagents are seeded if file is missing."""
    seed_file = tmp_path / "seed_agents.json"
    forge = AgentForge(agents_file=seed_file)
    agents = forge.list_agents()
    assert len(agents) >= 3
    role_names = [a.role_name for a in agents]
    assert "ManhuaPanelLayoutAgent" in role_names
    assert "SFXLettererAgent" in role_names
    assert "CultivationLoreAgent" in role_names


def test_skill_builder_synthesis_and_kb_indexing(temp_forge_env):
    """Verify synthesizing a standardized SKILL.md package and indexing it into Knowledge Base."""
    _, builder, kb, _, skills_dir = temp_forge_env

    skill_path, spec = builder.synthesize_skill(
        skill_name="manhua-vertical-rhythm",
        domain="panel_composition",
        description="Guides dynamic vertical-scroll webtoon pacing and gutter timing.",
        heuristics=[
            "Use 40px gutters for rapid martial exchange.",
            "Use 220px gutters for shock reveals.",
        ],
        anti_patterns=[
            "Never use identical square boxes down an entire episode.",
        ],
        examples_bad=["Monotonous 1:1 grids with equal 80px gaps."],
        examples_good=["Dynamic 9:16 splash followed by 30px action slash and 200px cliffhanger gap."],
    )

    assert skill_path.exists()
    skill_md = skill_path / "SKILL.md"
    assert skill_md.exists()

    content = skill_md.read_text(encoding="utf-8")
    assert "name: manhua-vertical-rhythm" in content
    assert "Use 40px gutters" in content
    assert "Never use identical square boxes" in content

    # Verify indexing into Knowledge Base
    kb_entries = kb.query("manhua vertical rhythm", limit=5)
    assert len(kb_entries) > 0
    assert any("manhua-vertical-rhythm" in e.title for e in kb_entries)
