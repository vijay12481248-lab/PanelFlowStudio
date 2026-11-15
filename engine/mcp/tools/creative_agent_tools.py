"""PanelFlow Studio MCP Tools — Creative Multi-Agent Pipeline & Knowledge RAG.

Exposes the full suite of creative agents, hybrid knowledge RAG, manhua structural
deconstruction analyzer, dynamic agent forge, and skill builder via standard MCP.
External agents (Coordinator, Antigravity Swarm, Claude Code, Cursor) interact with
PanelFlow Studio through these agents.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from engine.mcp.registry import registry
from engine.creative.schema import (
    ChapterOutline,
    CharacterProfile,
    CinematicScene,
    CinematicShot,
    DynamicAgentSpec,
    DynamicSkillSpec,
    KnowledgeCategory,
    KnowledgeEntry,
    ManhuaDeconstructionReport,
    ManhuaEpisode,
    NovelChapter,
    StoryBible,
    StoryGenre,
    StorySeed,
    VisualStyle,
)
from engine.creative.agents import (
    ShowrunnerAgent,
    NovelistAgent,
    EditorialCriticAgent,
    CinematographerAgent,
    PromptCompilerAgent,
    ManhuaDirectorAgent,
)
from engine.creative.knowledge import CreativeKnowledgeBase
from engine.creative.manhua_analyzer import ManhuaStructuralAnalyzer
from engine.creative.agent_forge import AgentForge, SkillBuilder
from engine.creative.mistakes import MistakeAuditor, MistakeLedger

logger = logging.getLogger("panelflow.mcp.creative_tools")


# ============================================================================
# 1. SHOWRUNNER AGENT
# ============================================================================

@registry.tool(
    name="panelflow_creative_showrunner_create_bible",
    description=(
        "Showrunner Agent: Takes an abstract story seed (e.g. Mahabharata epic, sci-fi, "
        "cultivation xianxia) and elaborates it into a comprehensive Story Bible with "
        "world lore, immutable rules, rich character profiles with visual tags, and chapter outlines."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "Story seed or narrative premise"},
            "genre": {
                "type": "string",
                "description": "Genre (cultivation, fantasy, sci_fi, horror, historical_epic, action_shonen)",
                "default": "cultivation",
            },
            "visual_style": {
                "type": "string",
                "description": "Visual aesthetic (cinematic_photoreal, anime_cel_shaded, dark_fantasy_oil, manhua_ink_wash)",
                "default": "cinematic_photoreal",
            },
            "tone": {"type": "string", "description": "Emotional tone (e.g. 'Epic, Mythological, High Stakes')", "default": "Epic, High Stakes"},
            "target_chapters": {"type": "integer", "description": "Number of chapters to outline (default: 3)", "default": 3},
        },
        "required": ["prompt"],
    },
    domain="creative_agent",
)
async def panelflow_creative_showrunner_create_bible(
    prompt: str,
    genre: str = "cultivation",
    visual_style: str = "cinematic_photoreal",
    tone: str = "Epic, High Stakes",
    target_chapters: int = 3,
) -> Dict[str, Any]:
    # Map genre and visual style enums safely
    try:
        genre_enum = StoryGenre(genre)
    except Exception:
        genre_enum = StoryGenre.CULTIVATION
    try:
        style_enum = VisualStyle(visual_style)
    except Exception:
        style_enum = VisualStyle.CINEMATIC_PHOTOREAL

    seed = StorySeed(
        prompt=prompt,
        genre=genre_enum,
        visual_style=style_enum,
        tone=tone,
        target_chapters=target_chapters,
    )
    agent = ShowrunnerAgent()
    bible = await agent.create_story_bible(seed)
    return bible.model_dump()


# ============================================================================
# 2. NOVELIST AGENT
# ============================================================================

@registry.tool(
    name="panelflow_creative_novelist_write_chapter",
    description=(
        "Novelist Agent: Writes a full literary novel chapter with deep prose, "
        "sensory atmosphere, character inner conflict, and snappy dialogue based on the Story Bible."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "bible_data": {"type": "object", "description": "StoryBible dictionary containing title, characters, and lore"},
            "chapter_number": {"type": "integer", "description": "Chapter number to write (default: 1)", "default": 1},
            "target_word_count": {"type": "integer", "description": "Target word count (default: 1200)", "default": 1200},
        },
        "required": ["bible_data"],
    },
    domain="creative_agent",
)
async def panelflow_creative_novelist_write_chapter(
    bible_data: Dict[str, Any],
    chapter_number: int = 1,
    target_word_count: int = 1200,
) -> Dict[str, Any]:
    bible = StoryBible(**bible_data)
    agent = NovelistAgent()
    outline = None
    if bible.chapter_outlines:
        for o in bible.chapter_outlines:
            if o.chapter_number == chapter_number:
                outline = o
                break
    chapter = await agent.write_chapter(bible, outline=outline, target_word_count=target_word_count)
    return chapter.model_dump()


# ============================================================================
# 3. EDITORIAL CRITIC AGENT
# ============================================================================

@registry.tool(
    name="panelflow_creative_critic_refine_chapter",
    description=(
        "Editorial Critic Agent: Reviews written prose for continuity, emotional pacing, "
        "and sensory immersion, refining the prose and returning a structured audit critique."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "chapter_data": {"type": "object", "description": "NovelChapter dictionary"},
            "bible_data": {"type": "object", "description": "StoryBible dictionary (optional)"},
        },
        "required": ["chapter_data"],
    },
    domain="creative_agent",
)
async def panelflow_creative_critic_refine_chapter(
    chapter_data: Dict[str, Any],
    bible_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    chapter = NovelChapter(**chapter_data)
    bible = StoryBible(**bible_data) if bible_data else None
    agent = EditorialCriticAgent()
    critique, refined = await agent.critique_and_refine(chapter, bible=bible)
    return {
        "critique": critique.model_dump(),
        "refined_chapter": refined.model_dump(),
    }


# ============================================================================
# 4. CINEMATOGRAPHER AGENT
# ============================================================================

@registry.tool(
    name="panelflow_creative_cinematographer_create_storyboard",
    description=(
        "Cinematographer Agent: Translates literary prose into sequential cinematic scenes "
        "and shots with precise camera moves, lighting, environmental details, and soundscapes."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "chapter_data": {"type": "object", "description": "NovelChapter dictionary"},
            "bible_data": {"type": "object", "description": "StoryBible dictionary"},
            "num_scenes": {"type": "integer", "description": "Number of scenes (default: 3)", "default": 3},
            "shots_per_scene": {"type": "integer", "description": "Shots per scene (default: 3)", "default": 3},
        },
        "required": ["chapter_data", "bible_data"],
    },
    domain="creative_agent",
)
async def panelflow_creative_cinematographer_create_storyboard(
    chapter_data: Dict[str, Any],
    bible_data: Dict[str, Any],
    num_scenes: int = 3,
    shots_per_scene: int = 3,
) -> Dict[str, Any]:
    chapter = NovelChapter(**chapter_data)
    bible = StoryBible(**bible_data)
    agent = CinematographerAgent()
    scenes = await agent.deconstruct_chapter_to_scenes(
        bible=bible,
        chapter=chapter,
        num_scenes=num_scenes,
        shots_per_scene=shots_per_scene,
    )
    return {"scenes": [s.model_dump() for s in scenes]}


# ============================================================================
# 5. PROMPT COMPILER AGENT
# ============================================================================

@registry.tool(
    name="panelflow_creative_compiler_build_tool_prompts",
    description=(
        "Prompt Compiler Agent: Compiles cinematic shots into Qwen Image 2.1 Turbo (ArtEngine) "
        "text-to-image prompts and MiniMax Fast H3 Turbo strict 6-heading prompt chains."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "scenes_data": {
                "type": "array",
                "items": {"type": "object"},
                "description": "List of CinematicScene dictionaries",
            },
            "protagonist_data": {
                "type": "object",
                "description": "CharacterProfile dictionary (optional)",
            },
        },
        "required": ["scenes_data"],
    },
    domain="creative_agent",
)
async def panelflow_creative_compiler_build_tool_prompts(
    scenes_data: List[Dict[str, Any]],
    protagonist_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    sanitized_scenes = []
    for idx, s in enumerate(scenes_data, start=1):
        s_copy = dict(s)
        if "id" not in s_copy or not s_copy["id"]:
            s_copy["id"] = f"scene_{s_copy.get('scene_index', idx)}"
        sanitized_scenes.append(CinematicScene(**s_copy))
    protagonist = CharacterProfile(**protagonist_data) if protagonist_data else None
    agent = PromptCompilerAgent()
    agent.process_scenes(sanitized_scenes, protagonist=protagonist)
    return {"scenes": [s.model_dump() for s in sanitized_scenes]}


# ============================================================================
# 6. MANHUA DIRECTOR AGENT
# ============================================================================

@registry.tool(
    name="panelflow_creative_manhua_direct_episode",
    description=(
        "Manhua Director Agent: Directs a full continuous vertical-scroll graphic episode "
        "(webtoon/manhua) with variable gutter heights, dynamic layouts (wide reveal, action diagonals, "
        "borderless insets), dialogue balloons, kinetic SFX onomatopoeia, and Qwen Image 2.1 art prompts."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Episode title"},
            "summary": {"type": "string", "description": "Dramatic summary or premise of the episode"},
            "chapter_prose": {"type": "string", "description": "Full literary prose text (optional)", "default": ""},
            "target_panel_count": {"type": "integer", "description": "Target number of panels (default: 6)", "default": 6},
            "genre": {"type": "string", "description": "Genre (default: cultivation_xianxia)", "default": "cultivation_xianxia"},
            "bible_data": {"type": "object", "description": "StoryBible dictionary (optional)"},
        },
        "required": ["title", "summary"],
    },
    domain="creative_agent",
)
async def panelflow_creative_manhua_direct_episode(
    title: str,
    summary: str,
    chapter_prose: str = "",
    target_panel_count: int = 6,
    genre: str = "cultivation_xianxia",
    bible_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    agent = ManhuaDirectorAgent()
    bible = StoryBible(**bible_data) if bible_data else None

    if chapter_prose.strip():
        chapter = NovelChapter(
            chapter_number=1,
            title=title,
            summary=summary,
            prose=chapter_prose,
            word_count=len(chapter_prose.split()),
        )
        episode = await agent.direct_episode(
            chapter=chapter,
            bible=bible,
            target_panel_count=target_panel_count,
            genre=genre,
        )
    else:
        episode = await agent.direct_from_prompt(
            title=title,
            summary=summary,
            target_panel_count=target_panel_count,
            genre=genre,
        )
    return episode.model_dump()


# ============================================================================
# 7. KNOWLEDGE BASE RAG TOOLS
# ============================================================================

@registry.tool(
    name="panelflow_creative_knowledge_query",
    description=(
        "Hybrid RAG Knowledge Retrieval: Searches the persistent creative knowledge base "
        "for vertical-scroll grammar, cultivation tropes, panel pacing, gutter timing, and artistic wisdom."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query_text": {"type": "string", "description": "Search query terms (e.g. 'vertical scroll gutter rhythm', 'cultivation aura')"},
            "category": {
                "type": "string",
                "description": "Category filter: panel_composition, cultivation_xianxia, dialogue_and_sfx, action_choreography, cliffhangers, general",
            },
            "limit": {"type": "integer", "description": "Max entries to return (default: 5)", "default": 5},
        },
        "required": ["query_text"],
    },
    domain="creative_agent",
)
async def panelflow_creative_knowledge_query(
    query_text: str,
    category: Optional[str] = None,
    limit: int = 5,
) -> Dict[str, Any]:
    kb = CreativeKnowledgeBase()
    entries = kb.query(query_text=query_text, category=category, limit=limit)
    return {
        "count": len(entries),
        "entries": [e.model_dump() for e in entries],
    }


@registry.tool(
    name="panelflow_creative_knowledge_add",
    description="Add a new atomic rule, trope, or structural technique to the persistent Creative Knowledge Base.",
    input_schema={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Knowledge entry title"},
            "content": {"type": "string", "description": "Detailed explanation, rule, or guideline"},
            "category": {
                "type": "string",
                "description": "Category (panel_composition, cultivation_xianxia, dialogue_and_sfx, action_choreography, cliffhangers, general)",
                "default": "general",
            },
            "tags": {"type": "array", "items": {"type": "string"}, "description": "Semantic search tags", "default": []},
            "source": {"type": "string", "description": "Source attribution", "default": "agent_discovery"},
            "confidence_score": {"type": "number", "description": "Confidence score 0.0 to 1.0", "default": 0.9},
        },
        "required": ["title", "content"],
    },
    domain="creative_agent",
)
async def panelflow_creative_knowledge_add(
    title: str,
    content: str,
    category: str = "general",
    tags: Optional[List[str]] = None,
    source: str = "agent_discovery",
    confidence_score: float = 0.9,
) -> Dict[str, Any]:
    kb = CreativeKnowledgeBase()
    import uuid
    from datetime import datetime

    try:
        cat_enum = KnowledgeCategory(category)
    except Exception:
        cat_enum = KnowledgeCategory.GENERAL

    entry = KnowledgeEntry(
        entry_id=f"kb_{uuid.uuid4().hex[:10]}",
        category=cat_enum,
        title=title,
        content=content,
        tags=tags or [],
        source=source,
        confidence_score=confidence_score,
        created_at=datetime.now().isoformat(),
    )
    saved = kb.add_entry(entry)
    return saved.model_dump()


# ============================================================================
# 8. MANHUA STRUCTURAL ANALYZER
# ============================================================================

@registry.tool(
    name="panelflow_creative_analyze_manhua",
    description=(
        "Clean-Room Manhua Structural Analyzer: Analyzes chapter layout geometry, "
        "gutter timing, dialogue density, and pacing rhythms from manifest data or public feeds. "
        "Strict clean-room rule: extracts structural grammar and heuristics without saving pirated scans."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "source_title": {"type": "string", "description": "Name of the manga / manhua / webtoon"},
            "chapter_identifier": {"type": "string", "description": "Chapter or episode identifier (e.g. 'Ch. 101')"},
            "panels_manifest": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Optional clean-room structural panel list with aspect_ratio, gutter_spacing_px, dialogue_count, action_type",
            },
            "url": {"type": "string", "description": "Web URL or feed endpoint (clean-room analysis only)", "default": ""},
            "auto_ingest_knowledge": {"type": "boolean", "description": "Automatically save extracted lessons into Knowledge Base", "default": True},
        },
        "required": ["source_title", "chapter_identifier"],
    },
    domain="creative_agent",
)
async def panelflow_creative_analyze_manhua(
    source_title: str,
    chapter_identifier: str,
    panels_manifest: Optional[List[Dict[str, Any]]] = None,
    url: str = "",
    auto_ingest_knowledge: bool = True,
) -> Dict[str, Any]:
    analyzer = ManhuaStructuralAnalyzer()
    if panels_manifest:
        report = analyzer.analyze_manifest(
            source_title=source_title,
            chapter_identifier=chapter_identifier,
            panels=panels_manifest,
            auto_ingest=auto_ingest_knowledge,
        )
    else:
        report = analyzer.analyze_url(
            url=url or f"https://clean-room.panelflow.local/manhua/{source_title}",
            source_title=source_title,
            chapter_identifier=chapter_identifier,
            auto_ingest=auto_ingest_knowledge,
        )
    return report.model_dump()


# ============================================================================
# 9. AGENT FORGE & SKILL SYNTHESIZER
# ============================================================================

@registry.tool(
    name="panelflow_creative_forge_agent",
    description=(
        "Agent Forge: Synthesizes a new specialized agent from scratch when a role is missing "
        "(e.g. SFXLettererAgent, CultivationLoreMaster, ActionChoreographer). Automatically "
        "persists the agent spec and injects relevant domain anti-patterns."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "role_name": {"type": "string", "description": "Unique role name (e.g. 'SFXLettererAgent')"},
            "domain": {"type": "string", "description": "Domain area (e.g. 'lettering', 'xianxia_worldbuilding')"},
            "description": {"type": "string", "description": "Purpose and operational goals of the agent"},
            "system_prompt": {"type": "string", "description": "Full system prompt defining the agent's behavior"},
            "anti_patterns": {"type": "array", "items": {"type": "string"}, "description": "Anti-patterns to enforce", "default": []},
        },
        "required": ["role_name", "domain", "description", "system_prompt"],
    },
    domain="creative_agent",
)
async def panelflow_creative_forge_agent(
    role_name: str,
    domain: str,
    description: str,
    system_prompt: str,
    anti_patterns: Optional[List[str]] = None,
) -> Dict[str, Any]:
    forge = AgentForge()
    spec = forge.forge_agent(
        role_name=role_name,
        domain=domain,
        description=description,
        system_prompt=system_prompt,
        anti_patterns=anti_patterns,
    )
    return {
        "status": "forged_and_registered",
        "agent": spec.model_dump(),
    }


@registry.tool(
    name="panelflow_creative_synthesize_skill",
    description=(
        "Skill Synthesizer: Synthesizes a new standardized Antigravity SKILL.md package "
        "with heuristics, anti-patterns, and bad/good examples, registering it into the Knowledge Base."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "skill_name": {"type": "string", "description": "Name of the skill (e.g. 'manhua-vertical-rhythm')"},
            "domain": {"type": "string", "description": "Domain category"},
            "description": {"type": "string", "description": "High-level description of what the skill teaches"},
            "heuristics": {"type": "array", "items": {"type": "string"}, "description": "List of core rules/heuristics"},
            "anti_patterns": {"type": "array", "items": {"type": "string"}, "description": "List of mistakes to avoid"},
            "examples_bad": {"type": "array", "items": {"type": "string"}, "description": "Bad examples", "default": []},
            "examples_good": {"type": "array", "items": {"type": "string"}, "description": "Good examples", "default": []},
        },
        "required": ["skill_name", "domain", "description", "heuristics", "anti_patterns"],
    },
    domain="creative_agent",
)
async def panelflow_creative_synthesize_skill(
    skill_name: str,
    domain: str,
    description: str,
    heuristics: List[str],
    anti_patterns: List[str],
    examples_bad: Optional[List[str]] = None,
    examples_good: Optional[List[str]] = None,
) -> Dict[str, Any]:
    builder = SkillBuilder()
    skill_dir, spec = builder.synthesize_skill(
        skill_name=skill_name,
        domain=domain,
        description=description,
        heuristics=heuristics,
        anti_patterns=anti_patterns,
        examples_bad=examples_bad,
        examples_good=examples_good,
    )
    return {
        "status": "synthesized_and_indexed",
        "skill_dir": str(skill_dir),
        "skill": spec.model_dump(),
    }


@registry.tool(
    name="panelflow_creative_list_dynamic_agents",
    description="List all dynamically forged agents stored in the persistent agents registry.",
    input_schema={
        "type": "object",
        "properties": {},
    },
    domain="creative_agent",
)
async def panelflow_creative_list_dynamic_agents() -> Dict[str, Any]:
    forge = AgentForge()
    agents = forge.list_forged_agents()
    return {
        "count": len(agents),
        "agents": [a.model_dump() for a in agents],
    }


# ============================================================================
# 10. SELF-IMPROVEMENT & MISTAKE AUDITOR
# ============================================================================

@registry.tool(
    name="panelflow_creative_self_improve_audit",
    description="Audits generated creative output against active anti-patterns, recording violations to prevent repeating mistakes.",
    input_schema={
        "type": "object",
        "properties": {
            "agent_name": {"type": "string", "description": "Agent name (e.g. 'ManhuaDirectorAgent', 'NovelistAgent')"},
            "domain": {"type": "string", "description": "Domain area (narrative, cinematography, manhua_direction, art_prompts)"},
            "content_to_audit": {"type": "string", "description": "Text, prompt, or JSON content to audit for mistakes"},
            "record_if_failed": {"type": "boolean", "description": "Whether to automatically log violations in MistakeLedger", "default": True},
        },
        "required": ["agent_name", "domain", "content_to_audit"],
    },
    domain="creative_agent",
)
async def panelflow_creative_self_improve_audit(
    agent_name: str,
    domain: str,
    content_to_audit: str,
    record_if_failed: bool = True,
) -> Dict[str, Any]:
    auditor = MistakeAuditor()
    passed, violations = auditor.audit_output(agent_name=agent_name, domain=domain, content=content_to_audit)
    return {
        "agent_name": agent_name,
        "domain": domain,
        "passed": passed,
        "violations_found": len(violations),
        "violations": violations,
    }


# ============================================================================
# 11. DELETION & LIFECYCLE MANAGEMENT (FULL CRUD)
# ============================================================================

@registry.tool(
    name="panelflow_creative_knowledge_delete",
    description="Delete or prune an obsolete or incorrect entry from the Creative Knowledge Base.",
    input_schema={
        "type": "object",
        "properties": {
            "entry_id": {"type": "string", "description": "Unique ID of the knowledge entry to delete"},
        },
        "required": ["entry_id"],
    },
    domain="creative_agent",
)
async def panelflow_creative_knowledge_delete(entry_id: str) -> Dict[str, Any]:
    kb = CreativeKnowledgeBase()
    success = kb.delete_entry(entry_id)
    return {"status": "deleted" if success else "not_found", "entry_id": entry_id}


@registry.tool(
    name="panelflow_creative_forge_delete_agent",
    description="Decommission and delete a dynamic agent specification from the persistent registry.",
    input_schema={
        "type": "object",
        "properties": {
            "role_name": {"type": "string", "description": "Role name of the agent to decommission"},
        },
        "required": ["role_name"],
    },
    domain="creative_agent",
)
async def panelflow_creative_forge_delete_agent(role_name: str) -> Dict[str, Any]:
    forge = AgentForge()
    success = forge.delete_agent(role_name)
    return {"status": "deleted" if success else "not_found", "role_name": role_name}


@registry.tool(
    name="panelflow_creative_skill_delete",
    description="Delete/deprecate a synthesized skill package and remove it from the Knowledge Base.",
    input_schema={
        "type": "object",
        "properties": {
            "skill_name": {"type": "string", "description": "Name of the skill to delete"},
        },
        "required": ["skill_name"],
    },
    domain="creative_agent",
)
async def panelflow_creative_skill_delete(skill_name: str) -> Dict[str, Any]:
    builder = SkillBuilder()
    success = builder.delete_skill(skill_name)
    return {"status": "deleted" if success else "not_found", "skill_name": skill_name}


@registry.tool(
    name="panelflow_creative_mistake_delete",
    description="Remove/retire a mistake pattern from the ledger (e.g. permanently resolved or obsolete).",
    input_schema={
        "type": "object",
        "properties": {
            "mistake_id": {"type": "string", "description": "ID of the mistake pattern to remove"},
        },
        "required": ["mistake_id"],
    },
    domain="creative_agent",
)
async def panelflow_creative_mistake_delete(mistake_id: str) -> Dict[str, Any]:
    ledger = MistakeLedger()
    success = ledger.delete_mistake(mistake_id)
    return {"status": "deleted" if success else "not_found", "mistake_id": mistake_id}


# ============================================================================
# 12. FREE LLM API & CLOUD PROVIDER CONFIGURATION
# ============================================================================

@registry.tool(
    name="panelflow_configure_freellmapi",
    description=(
        "Configure Free LLM API (OpenRouter free models, FreeLLMAPI, Groq, etc.) as the active provider "
        "for PanelFlow Studio and all creative agents. When configured, agents relay prompts to this API key."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "api_key": {"type": "string", "description": "The API key for Free LLM API / OpenRouter"},
            "endpoint_url": {
                "type": "string",
                "description": "API Base URL (default: 'https://openrouter.ai/api/v1')",
                "default": "https://openrouter.ai/api/v1",
            },
            "model_name": {
                "type": "string",
                "description": "Model identifier (default: 'meta-llama/llama-3.3-70b-instruct:free')",
                "default": "meta-llama/llama-3.3-70b-instruct:free",
            },
            "provider_type": {
                "type": "string",
                "description": "Provider type (freellmapi, openrouter, groq, custom)",
                "default": "freellmapi",
            },
            "set_as_global_default": {
                "type": "boolean",
                "description": "Whether to switch all creative agents and background flows to this provider by default",
                "default": True,
            },
        },
        "required": ["api_key"],
    },
    domain="creative_agent",
)
async def panelflow_configure_freellmapi(
    api_key: str,
    endpoint_url: str = "https://openrouter.ai/api/v1",
    model_name: str = "meta-llama/llama-3.3-70b-instruct:free",
    provider_type: str = "freellmapi",
    set_as_global_default: bool = True,
) -> Dict[str, Any]:
    from engine.llm.registry import llm_registry
    provider = llm_registry.configure_cloud_provider(
        endpoint_url=endpoint_url,
        api_key=api_key,
        model_name=model_name,
        provider_type=provider_type,
        is_active=True,
    )
    if set_as_global_default:
        llm_registry.update_global_settings(
            global_default_provider="cloud_llm",
            global_default_model=model_name,
        )
    is_healthy = await provider.health_check()
    masked = (api_key[:4] + "••••" + api_key[-4:]) if len(api_key) >= 12 else "••••"
    return {
        "status": "configured",
        "provider": provider.display_name,
        "endpoint_url": endpoint_url,
        "model_name": model_name,
        "masked_api_key": masked,
        "is_healthy": is_healthy,
        "is_global_default": set_as_global_default,
    }


@registry.tool(
    name="panelflow_get_llm_status",
    description="Get current status of active LLM providers (Ollama local vs. Free LLM API / Cloud).",
    input_schema={
        "type": "object",
        "properties": {},
    },
    domain="creative_agent",
)
async def panelflow_get_llm_status() -> Dict[str, Any]:
    from engine.llm.registry import llm_registry
    cloud_cfg = llm_registry.get_cloud_config()
    global_cfg = llm_registry.get_global_settings()
    active_provider, active_model = await llm_registry.resolve_provider_and_model(flow_id="creative_agents")
    is_healthy = await active_provider.health_check()
    return {
        "active_provider_id": active_provider.provider_id,
        "active_display_name": active_provider.display_name,
        "active_model": active_model,
        "is_healthy": is_healthy,
        "cloud_config": {
            "endpoint_url": cloud_cfg.get("endpoint_url"),
            "model_name": cloud_cfg.get("model_name"),
            "has_api_key": bool(cloud_cfg.get("api_key")),
            "is_active": cloud_cfg.get("is_active"),
        },
        "global_default_provider": global_cfg.get("global_default_provider"),
    }


@registry.tool(
    name="panelflow_reset_to_local_llm",
    description="Switches the active provider back to local Ollama (qwen3.5:9b).",
    input_schema={
        "type": "object",
        "properties": {},
    },
    domain="creative_agent",
)
async def panelflow_reset_to_local_llm() -> Dict[str, Any]:
    from engine.llm.registry import llm_registry
    llm_registry.update_global_settings(
        global_default_provider="ollama",
        global_default_model="qwen3.5:9b",
    )
    provider = llm_registry.get_ollama_provider()
    return {
        "status": "switched_to_local",
        "active_provider": provider.display_name,
        "model": provider.narration_model,
    }



