"""Creative Studio Agents implemented with google.antigravity and local LLM runtime.

Specialized Agents:
1. ShowrunnerAgent: Deconstructs abstract seed into Story Bible, World Lore, Characters, and Roadmaps.
2. NovelistAgent: Crafts deep, emotionally resonant novel prose and dialogue.
3. EditorialCriticAgent: Audits continuity, emotional resonance, and refines prose.
4. CinematographerAgent: Translates prose into visual scenes and cinematic shots.
5. PromptCompilerAgent: Compiles prompts for Qwen Image 2.1 (ArtEngine) and MiniMax H3.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional, Type, TypeVar
from pydantic import BaseModel

import google.antigravity as ag
from engine.creative.schema import (
    ChapterBeat,
    ChapterOutline,
    CharacterProfile,
    CinematicScene,
    CinematicShot,
    EditorialCritique,
    KnowledgeCategory,
    ManhuaEpisode,
    ManhuaPanel,
    NovelChapter,
    PanelLayoutType,
    StoryBible,
    StorySeed,
    WorldLore,
)
from engine.creative.knowledge import CreativeKnowledgeBase
from engine.creative.mistakes import MistakeLedger
from engine.llm.registry import llm_registry

logger = logging.getLogger("panelflow.creative.agents")

T = TypeVar("T", bound=BaseModel)

OLLAMA_BASE_URL = "http://127.0.0.1:11434/v1"
LOCAL_MODEL = "qwen3.5:9b"


def _clean_json_response(raw_text: str) -> str:
    """Extract valid JSON object from LLM response containing markdown or prose wrappers."""
    raw = raw_text.strip()
    # Strip markdown code blocks ```json ... ```
    if "```json" in raw:
        match = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
        if match:
            return match.group(1).strip()
    if "```" in raw:
        match = re.search(r"```\s*(.*?)\s*```", raw, re.DOTALL)
        if match:
            return match.group(1).strip()
    # Find outer curly braces
    first_brace = raw.find("{")
    last_brace = raw.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return raw[first_brace : last_brace + 1]
    return raw


async def _execute_agent_prompt(
    system_instructions: str,
    prompt: str,
    response_model: Optional[Type[T]] = None,
    max_retries: int = 2,
) -> Any:
    """Execute an agent prompt using google.antigravity with the active provider (Free LLM API or local Ollama)."""
    # 1. Resolve active provider and model
    try:
        provider, model_name = await llm_registry.resolve_provider_and_model(flow_id="creative_agents")
    except Exception as resolve_err:
        logger.warning(f"Could not resolve active provider ({resolve_err}), defaulting to local Ollama...")
        provider = llm_registry.get_ollama_provider()
        model_name = LOCAL_MODEL

    endpoint = getattr(provider, "endpoint_url", OLLAMA_BASE_URL)
    if not endpoint.endswith("/v1"):
        endpoint = f"{endpoint.rstrip('/')}/v1"
    active_model = model_name or getattr(provider, "model_name", LOCAL_MODEL)
    api_key = getattr(provider, "api_key", "")
    is_cloud = bool(api_key and api_key != "local-no-key")

    logger.info(f"Invoking creative agent with model '{active_model}' via '{endpoint}' (cloud_provider={is_cloud})")

    # 2. If configured with Free LLM API / Cloud, execute directly with retry
    if is_cloud:
        for attempt in range(max_retries + 1):
            try:
                if response_model is not None:
                    return await provider.generate_structured(
                        prompt=f"{system_instructions}\n\nTask:\n{prompt}",
                        response_model=response_model,
                        system_prompt=system_instructions,
                        temperature=0.3,
                    )
                else:
                    return await provider.generate_text(
                        prompt=prompt,
                        system_prompt=system_instructions,
                        temperature=0.5,
                    )
            except Exception as cloud_err:
                logger.warning(f"FreeLLMAPI attempt {attempt + 1}/{max_retries + 1} error: {cloud_err}")
                if attempt < max_retries:
                    await asyncio.sleep(1.0)
                else:
                    raise cloud_err

    # 3. Antigravity Agent session (for local Ollama)
    try:
        caps = ag.types.CapabilitiesConfig(
            file_reads=False,
            file_writes=False,
            command_execution=False,
            subagents=False,
            mcp=False,
        )
        cfg = ag.LocalOpenAIAgentConfig(
            model=active_model,
            base_url=endpoint,
            system_instructions=system_instructions,
            capabilities=caps,
        )
        async with ag.Agent(cfg) as agent:
            response = await asyncio.wait_for(agent.chat(prompt), timeout=60.0)
            output_text = await response.text()
            if output_text and output_text.strip():
                if response_model is not None:
                    cleaned_json = _clean_json_response(output_text)
                    try:
                        data = json.loads(cleaned_json)
                        return response_model(**data)
                    except Exception as parse_err:
                        logger.warning(f"Antigravity output JSON parse failed ({parse_err}), repairing with active provider...")
                else:
                    return output_text
    except Exception as agent_err:
        logger.warning(f"Antigravity Agent session error ({agent_err}), routing to active provider ({provider.display_name})...")

    # 4. Final Fallback for local Ollama
    if response_model is not None:
        return await provider.generate_structured(
            prompt=f"{system_instructions}\n\nTask:\n{prompt}",
            response_model=response_model,
            system_prompt=system_instructions,
            temperature=0.3,
        )
    else:
        return await provider.generate_text(
            prompt=prompt,
            system_prompt=system_instructions,
            temperature=0.5,
        )


class ShowrunnerAgent:
    """Master Narrative Showrunner & Worldbuilder."""

    SYSTEM_INSTRUCTIONS = """You are the Master Narrative Showrunner and Worldbuilder for PanelFlow Studio.
Your mission is to take an abstract story seed (whether a mythological epic like the Mahabharata, hard sci-fi, dark fantasy, or original drama) and elaborate it into a foundational Story Bible.
You define:
1. A captivating, profound title and high-stakes logline.
2. Thematic core and emotional arc across the narrative.
3. World Lore: setting, historical/mythological era, factions, and immutable rules that must never be broken.
4. Rich Character Profiles: distinct visual tags, psychological depths, signature items/weapons, facial micro-expressions, and speech cadence.
5. Chapter Outlines: dramatic premises, emotional shifts, and beat-by-beat breakdowns.

Always return strict, valid JSON matching the StoryBible schema."""

    async def create_story_bible(self, seed: StorySeed) -> StoryBible:
        anti_patterns = MistakeLedger().get_anti_patterns_prompt("character_lore")
        prompt = f"""Deconstruct this story seed into a master Story Bible:

Seed Prompt: "{seed.prompt}"
Genre: {seed.genre.value}
Visual Aesthetic: {seed.visual_style.value}
Emotional Tone: {seed.tone}
Target Chapters: {seed.target_chapters}

{anti_patterns}

Respond with a JSON object conforming exactly to this schema:
{{
  "title": "String title",
  "logline": "Two-sentence logline outlining the central conflict and stakes",
  "thematic_core": "Core philosophical and emotional themes",
  "emotional_arc": "Overall emotional progression",
  "lore": {{
    "world_name": "Name of world or historical realm",
    "era_or_timeline": "Time period or mythological epoch",
    "setting_overview": "Vivid description of the environment and atmosphere",
    "rules": ["Rule 1", "Rule 2", "Rule 3"],
    "key_factions": ["Faction 1", "Faction 2"]
  }},
  "characters": [
    {{
      "id": "short_slug_name",
      "name": "Full Name",
      "role": "Protagonist / Antagonist / Mentor / Companion",
      "visual_tags": "strict comma-separated visual tags (clothing, armor, hair, distinctive mark)",
      "personality": "Psychological depth and temperament",
      "signature_item": "Iconic item or weapon",
      "facial_features": "Facial expressions, age markers, gaze",
      "emotional_arc": "Character emotional trajectory",
      "tag": "<Picture 1>"
    }}
  ],
  "chapter_outlines": [
    {{
      "chapter_number": 1,
      "title": "Chapter Title",
      "epigraph": "Short evocative quote or poetic epigraph",
      "dramatic_premise": "Core dilemma of the chapter",
      "beats": [
        {{
          "beat_index": 1,
          "title": "Beat Title",
          "narrative_summary": "What happens",
          "emotional_shift": "Emotional transition in this beat",
          "characters_present": ["character_id"]
        }}
      ]
    }}
  ]
}}"""
        result = await _execute_agent_prompt(
            system_instructions=self.SYSTEM_INSTRUCTIONS,
            prompt=prompt,
            response_model=StoryBible,
        )
        return result


class NovelistAgent:
    """Master Epic Novelist & Literary Prose Author."""

    SYSTEM_INSTRUCTIONS = """You are a Master Epic Novelist.
You write immersive, emotionally profound novel prose.
You weave:
- Visceral sensory details (smell of ozone, cold iron, dust, sweat, incense).
- Deep internal monologue, psychological complexity, and personal vulnerability.
- High-stakes dramatic dialogue reflecting each character's distinct voice.
- Pacing that balances tension, atmospheric stillness, and explosive revelations.

Do not write brief summaries; write authentic, complete book chapter prose."""

    async def write_chapter(
        self,
        bible: StoryBible,
        chapter_outline: Optional[ChapterOutline] = None,
        outline: Optional[ChapterOutline] = None,
        target_word_count: int = 1000,
    ) -> NovelChapter:
        effective_outline = chapter_outline or outline or (bible.chapter_outlines[0] if bible.chapter_outlines else None)
        if not effective_outline:
            effective_outline = ChapterOutline(
                chapter_number=1,
                title="Chapter 1: The Threshold",
                epigraph="",
                dramatic_premise=bible.logline,
                beats=[],
            )
        char_context = "\n".join(
            f"- {c.name} ({c.role}): {c.visual_tags}. Personality: {c.personality}. Facial markers: {c.facial_features}"
            for c in bible.characters
        )
        beats_context = "\n".join(
            f"Beat {b.beat_index}: {b.title} - {b.narrative_summary} (Emotional Shift: {b.emotional_shift})"
            for b in effective_outline.beats
        ) if effective_outline.beats else "Establish setting, introduce conflict, and climax on sudden confrontation."
        anti_patterns = MistakeLedger().get_anti_patterns_prompt("novel_prose")

        prompt = f"""Write the full literary prose for Chapter {effective_outline.chapter_number} of "{bible.title}".

Epigraph: "{effective_outline.epigraph}"
Dramatic Premise: {effective_outline.dramatic_premise}

World Lore & Rules:
{bible.lore.setting_overview}
Rules: {", ".join(bible.lore.rules)}

Characters Involved:
{char_context}

Beats to cover in this chapter:
{beats_context}

{anti_patterns}

Write complete, rich narrative prose (around {target_word_count} words). Include sensory atmosphere, dialogue, and emotional nuance.

Return a JSON object conforming to this schema:
{{
  "chapter_number": {effective_outline.chapter_number},
  "title": "{effective_outline.title}",
  "epigraph": "{effective_outline.epigraph}",
  "prose": "Full chapter prose text here...",
  "summary": "Concise summary of chapter events",
  "word_count": 0,
  "emotional_peak": "The climactic emotional moment of this chapter"
}}"""
        res = await _execute_agent_prompt(
            system_instructions=self.SYSTEM_INSTRUCTIONS,
            prompt=prompt,
            response_model=NovelChapter,
        )
        if res.prose:
            res.word_count = len(res.prose.split())
        return res


class EditorialCriticAgent:
    """Senior Literary Editor & Continuity Auditor."""

    SYSTEM_INSTRUCTIONS = """You are the Senior Literary Editor and Continuity Overseer.
Your role is to rigorously evaluate draft novel chapters:
1. Verify continuity with the Story Bible (character looks, items, lore rules, injuries).
2. Rate emotional resonance and pacing (1 to 10).
3. Check dialogue authenticity and character voices.
4. Polish and refine any awkward phrasing or continuity breaks."""

    async def critique_and_refine(self, bible: StoryBible, chapter: NovelChapter) -> EditorialCritique:
        prompt = f"""Review and audit this draft novel chapter:

Title: {bible.title}
Chapter {chapter.chapter_number}: {chapter.title}

World Rules: {", ".join(bible.lore.rules)}
Characters: {", ".join(c.name for c in bible.characters)}

Draft Prose:
\"\"\"
{chapter.prose[:3000]}
\"\"\"

Audit the chapter for continuity, tone, and literary impact.
Return a JSON object:
{{
  "score": 9,
  "continuity_pass": true,
  "critique_notes": [
    "Note on pacing or emotional delivery",
    "Note on sensory immersion"
  ],
  "polished_prose": "Polished text if minor improvements were made, or omit if already great"
}}"""
        return await _execute_agent_prompt(
            system_instructions=self.SYSTEM_INSTRUCTIONS,
            prompt=prompt,
            response_model=EditorialCritique,
        )


class CinematographerAgent:
    """Master Director of Photography & Visual Scene Director."""

    SYSTEM_INSTRUCTIONS = """You are the Master Cinematographer and Director of Photography for PanelFlow Studio.
Your mission is to translate literary novel chapters into sequential cinematic scenes and shots.
Each shot must specify:
- Shot Type (Wide Establishing, Medium Tracking, Macro Close-Up, Low-Angle Hero, Overhead Bird's Eye, Dutch Angle).
- Camera Movement (slow deliberate push-in, orbital crane, lateral tracking, steadicam glide).
- Subject Action & Micro-Expressions (furrowed brow, trembling jaw, determined gaze, unnaming visual descriptors).
- Environmental Details (atmospheric haze, floating embers, dust particles, textured architecture).
- Lighting & Atmosphere (volumetric beams, high-contrast chiaroscuro, warm rim light, bioluminescent glow).
- Soundscape (diegetic foley: wind howl, boot footsteps on stone, armor rattle, strictly NO human speech).
- Non-diegetic Music (haunting strings, deep sub-bass drone, rising crescendo)."""

    async def deconstruct_chapter_to_scenes(
        self,
        bible: StoryBible,
        chapter: NovelChapter,
        num_scenes: int = 3,
        shots_per_scene: int = 3,
    ) -> List[CinematicScene]:
        anti_patterns = MistakeLedger().get_anti_patterns_prompt("cinematography")
        prompt = f"""Translate Chapter {chapter.chapter_number} of "{bible.title}" into {num_scenes} cinematic scenes, each containing {shots_per_scene} precise visual shots.

Chapter Summary: {chapter.summary}
Chapter Prose Sample:
\"\"\"
{chapter.prose[:2000]}
\"\"\"

Characters & Visual Tags:
{", ".join(f"{c.name}: {c.visual_tags}" for c in bible.characters)}

{anti_patterns}

Break down the chapter into {num_scenes} sequential scenes. Each scene has a name, description, and {shots_per_scene} shots.
Return a JSON object with this structure:
{{
  "scenes": [
    {{
      "scene_index": 1,
      "id": "scene_1",
      "name": "Scene 1: Descriptive Title",
      "description": "Narrative overview of this scene's events",
      "shots": [
        {{
          "shot_index": 1,
          "scene_index": 1,
          "title": "Shot 1: The Threshold",
          "shot_type": "Wide Establishing",
          "duration": 5.2,
          "workflow": "reference",
          "camera_movement": "Slow sweeping low-angle crane tracking forward across the terrain.",
          "subject_description": "Detailed subject pose, costume silhouette, and subtle micro-expression (furrowed brow, steely resolve).",
          "environmental_details": "Towering stone monolithic arches, dense low-hanging mist, scattered ancient debris.",
          "lighting_and_atmosphere": "Dramatic chiaroscuro with piercing golden sun rays cutting through cold azure shadows.",
          "soundscape": "Heavy wind howling through stone crevices, distant raven caw, armor plate clinks. Strict rule: absolutely no human speech or dialogue.",
          "non_diegetic_music": "Low resonant cello drone building solemn tension."
        }}
      ]
    }}
  ]
}}"""
        class _ScenesContainer(BaseModel):
            scenes: List[CinematicScene]

        result = await _execute_agent_prompt(
            system_instructions=self.SYSTEM_INSTRUCTIONS,
            prompt=prompt,
            response_model=_ScenesContainer,
        )
        return result.scenes if result and result.scenes else []


class PromptCompilerAgent:
    """Compiles shots into Qwen Image 2.1 (ArtEngine) and MiniMax H3 6-Heading Prompt Chains."""

    def compile_h3_prompt(self, shot: CinematicShot, protagonist: Optional[CharacterProfile] = None) -> str:
        """Compile MiniMax Fast H3 Turbo strict 6-heading prompt chain."""
        subject_header = "subject_definitions:\n"
        if protagonist:
            subject_header += f"{protagonist.name}: {protagonist.visual_tags}. Facial expression: {shot.subject_description}\n"
        else:
            subject_header += f"Subject: {shot.subject_description}\n"

        summary_header = f"summary:\nCinematic sequence: {shot.title}. {shot.subject_description[:120]}...\n"
        retention_header = "retention_analysis:\nSubject anatomy, clothing textures, environment architecture, and atmospheric lighting are strictly preserved.\n"

        detailed_desc = (
            f"detailed_description:\n"
            f"camera_movement: {shot.camera_movement} "
            f"subject_description: {shot.subject_description} "
            f"environmental_details: {shot.environmental_details} "
            f"lighting_and_atmosphere: {shot.lighting_and_atmosphere} "
            f"overall_soundscape: {shot.soundscape} "
            f"non_diegetic_music: {shot.non_diegetic_music}"
        )

        sound_clean = shot.soundscape.strip()
        sound_clean = sound_clean.replace('"', "").replace("'", "")
        if "no human speech" not in sound_clean.lower():
            sound_clean += " Strict rule: absolutely no human speech or dialogue."
        overall_sound = f"overall_soundscape:\n{sound_clean}"
        music_header = f"non_diegetic_music:\n{shot.non_diegetic_music}"

        return f"{subject_header}\n{summary_header}\n{retention_header}\n{detailed_desc}\n\n{overall_sound}\n\n{music_header}"

    def compile_qwen_art_prompt(self, shot: CinematicShot, protagonist: Optional[CharacterProfile] = None) -> str:
        """Compile Qwen Image 2.1 Turbo (ArtEngine) text-to-image prompt."""
        char_tags = protagonist.visual_tags if protagonist else ""
        return (
            f"Masterpiece cinematic film still, {shot.shot_type.lower()}, {shot.lighting_and_atmosphere}. "
            f"{char_tags}. {shot.subject_description}. "
            f"Environment: {shot.environmental_details}. "
            f"8k resolution, photorealistic, intricate textures, volumetric depth, anamorphic lens flare."
        )

    def process_scenes(self, scenes: List[CinematicScene], protagonist: Optional[CharacterProfile] = None) -> None:
        """Enrich all shots in all scenes with compiled H3 and Qwen prompts and sequential indices."""
        global_shot_idx = 1
        for s_idx, scene in enumerate(scenes, start=1):
            scene.scene_index = s_idx
            scene.shot_indices = []
            for shot in scene.shots:
                shot.shot_index = global_shot_idx
                shot.scene_index = s_idx
                shot.workflow = "reference" if global_shot_idx == 1 else "sliding_window"
                shot.prompt = self.compile_h3_prompt(shot, protagonist)
                shot.art_prompt = self.compile_qwen_art_prompt(shot, protagonist)
                scene.shot_indices.append(global_shot_idx)
                global_shot_idx += 1


class ManhuaDirectorAgent:
    """Master Manhua & Webtoon Director specializing in vertical-scroll storytelling.

    Transforms novel chapters or abstract story beats into continuous vertical-scroll
    episodes with variable gutter heights, dynamic layouts (wide reveal, action diagonals,
    borderless insets), dialogue balloons, visual sound effects (SFX onomatopoeia),
    and Qwen Image 2.1 art prompts.

    Integrates self-improvement by querying CreativeKnowledgeBase for layout and genre
    grammar, and enforces anti-patterns from MistakeLedger.
    """

    SYSTEM_INSTRUCTIONS = """You are the Master Manhua and Webtoon Director for PanelFlow Studio.
Your mission is to adapt literary chapters into continuous vertical-scroll graphic episodes (webtoons/manhua).
For every panel, you must direct:
1. Layout Type:
   - vertical_scroll_full (100% width dramatic impact, splash panel)
   - vertical_split_stack (two stacked panels showing cause and effect)
   - horizontal_split (side-by-side contrasting characters or reactions)
   - diagonal_action (dynamic angled slashes for fast martial arts strikes)
   - gutter_transition (extended vertical gap for dramatic pause/silence)
   - borderless_inset (character floating over background)
2. Gutter Spacing: Variable vertical pixel height representing temporal pause.
   - 40-60px: Fast, rapid-fire martial exchange or urgent dialogue
   - 80-120px: Standard narrative flow
   - 180-260px: Extended silence, realization of catastrophe, or suspenseful reveal
3. Visual Description & Composition: Clear focal hierarchy, camera angle (low-angle heroic, high-angle vulnerability, Dutch tilt), and dynamic lighting.
4. Art Prompt: Formatted for Qwen Image 2.1 Turbo (photorealistic/masterpiece digital ink, unnamed visual tags, atmospheric lighting).
5. Dialogue Balloons: Keep concise (under 20 words per balloon). Never clutter action panels.
6. SFX Onomatopoeia: Cultivation/action kinetic sound effects (e.g., 'BOOM', 'SWOOSH', 'CRACKLE', 'HUM').
7. Cliffhanger: End every episode with an irresistible narrative hook (arrival of an ancient powerhouse, weapon unsheathed, sudden betrayal).

Always output strict, valid JSON matching the ManhuaEpisode schema."""

    def __init__(self, kb: Optional[CreativeKnowledgeBase] = None):
        self.kb = kb or CreativeKnowledgeBase()

    async def direct_episode(
        self,
        chapter: NovelChapter,
        bible: Optional[StoryBible] = None,
        target_panel_count: int = 6,
        genre: str = "cultivation_xianxia",
    ) -> ManhuaEpisode:
        """Direct a complete vertical-scroll episode from a chapter."""
        # 1. Query Knowledge Base for structural wisdom & genre rules
        layout_wisdom = self.kb.query(
            "vertical scroll gutter rhythm panel composition",
            category=KnowledgeCategory.PANEL_COMPOSITION,
            limit=2,
        )
        genre_wisdom = self.kb.query(
            genre,
            category=KnowledgeCategory.CULTIVATION_XIANXIA,
            limit=2,
        )
        all_wisdom = layout_wisdom + genre_wisdom
        knowledge_context = "\n".join(f"- {e.title}: {e.content[:160]}..." for e in all_wisdom) if all_wisdom else "Follow standard vertical-scroll webtoon pacing."

        # 2. Fetch active anti-patterns from MistakeLedger
        anti_patterns = MistakeLedger().get_anti_patterns_prompt("manhua_direction")

        # 3. Formulate Prompt
        protagonist_name = bible.protagonist_name if bible and hasattr(bible, "protagonist_name") else (bible.characters[0].name if bible and bible.characters else "Hero")
        characters_desc = ", ".join(f"{c.name}: {c.visual_tags}" for c in bible.characters) if bible and bible.characters else protagonist_name

        prompt = f"""Adapt Chapter {chapter.chapter_number}: "{chapter.title}" into a vertical-scroll Manhua Episode with {target_panel_count} panels.

Chapter Summary:
{chapter.summary}

Prose Excerpt:
\"\"\"
{chapter.prose[:1800]}
\"\"\"

Characters & Visual Tags:
{characters_desc}

Knowledge Base Guidelines:
{knowledge_context}

{anti_patterns}

Output a complete JSON object adhering to the ManhuaEpisode schema:
- episode_number: {chapter.chapter_number}
- title: Episode title
- reading_flow: "vertical_scroll"
- summary: Dramatic overview
- cliffhanger_hook: High-stakes closing beat
- panels: Exactly {target_panel_count} sequential panels with variable gutters (40px to 240px), dynamic layouts, concise dialogue balloons, kinetic SFX onomatopoeia, and Qwen Image 2.1 art prompts.
- estimated_scroll_length_px: Total vertical scroll height
- theme_palette: Array of hex colors"""

        try:
            result = await _execute_agent_prompt(
                system_instructions=self.SYSTEM_INSTRUCTIONS,
                prompt=prompt,
                response_model=ManhuaEpisode,
            )
            if result and isinstance(result, ManhuaEpisode) and len(result.panels) > 0:
                return result
        except Exception as exc:
            logger.warning(f"ManhuaDirectorAgent LLM execution failed ({exc}), using deterministic fallback...")

        return self._create_fallback_episode(
            title=f"Episode {chapter.chapter_number}: {chapter.title}",
            summary=chapter.summary,
            target_panel_count=target_panel_count,
            protagonist_name=protagonist_name,
        )

    async def direct_from_prompt(
        self,
        title: str,
        summary: str,
        target_panel_count: int = 6,
        genre: str = "cultivation_xianxia",
    ) -> ManhuaEpisode:
        """Direct a vertical-scroll episode directly from a high-level summary or premise."""
        mock_chapter = NovelChapter(
            chapter_number=1,
            title=title,
            summary=summary,
            prose=summary,
            word_count=len(summary.split()),
        )
        return await self.direct_episode(mock_chapter, target_panel_count=target_panel_count, genre=genre)

    def _create_fallback_episode(
        self,
        title: str,
        summary: str,
        target_panel_count: int = 6,
        protagonist_name: str = "Hero",
    ) -> ManhuaEpisode:
        """Create a production-grade vertical-scroll episode using clean-room structural rules."""
        panels = [
            ManhuaPanel(
                panel_index=1,
                layout_type=PanelLayoutType.VERTICAL_SCROLL_FULL,
                aspect_ratio="9:16",
                gutter_spacing_px=100,
                visual_description=f"Wide establishing vista of an ancient misty abyss under blood-red twilight. {protagonist_name} stands silhouetted on a jagged stone precipice.",
                art_prompt=f"Masterpiece cinematic webtoon splash art, wide angle, dramatic crimson dusk lighting, volumetric mountain fog. Lone martial artist in weathered charcoal robes standing on jagged stone cliff overlooking boundless abyss. Intricate digital ink lineart, vibrant cel-shaded color palette.",
                dialogue_balloons=[{"character": "Narrator", "text": "Beyond the Heavenly Boundary, only silence reigns.", "style": "narration"}],
                sfx_onomatopoeia=[{"text": "WHOOSH", "meaning": "cold alpine gale", "color": "cyan"}],
                camera_angle="low-angle heroic",
                lighting_color="blood-red and deep navy",
            ),
            ManhuaPanel(
                panel_index=2,
                layout_type=PanelLayoutType.VERTICAL_SPLIT_STACK,
                aspect_ratio="16:9",
                gutter_spacing_px=60,
                visual_description=f"Close-up on {protagonist_name}'s steely eyes narrowing as celestial runes ignite across the obsidian blade in hand.",
                art_prompt=f"Dynamic manhua frame, macro close-up of sharp eyes reflecting brilliant azure lightning runes, dark disheveled hair, determined gaze, hyper-detailed linework, glowing runic reflections, cinematic depth of field.",
                dialogue_balloons=[{"character": protagonist_name, "text": "They think ten thousand li is enough to escape.", "style": "whisper"}],
                sfx_onomatopoeia=[{"text": "BZZT", "meaning": "runic resonance", "color": "electric-blue"}],
                camera_angle="macro close-up",
                lighting_color="azure lightning glow",
            ),
            ManhuaPanel(
                panel_index=3,
                layout_type=PanelLayoutType.DIAGONAL_ACTION,
                aspect_ratio="16:9",
                gutter_spacing_px=40,
                visual_description="Explosive kinetic leap, body carving an arc across the air as sonic boom shockwaves shatter the stone ledge.",
                art_prompt="High-speed dynamic action manhua cut, diagonal speedlines, explosive sonic shockwave expanding from shattered cliff edge, aerial martial combat stance, flying dust debris, motion blur accent.",
                dialogue_balloons=[],
                sfx_onomatopoeia=[{"text": "BOOM!", "meaning": "kinetic detonation", "color": "crimson"}],
                camera_angle="Dutch tilt dynamic",
                lighting_color="explosive orange flash",
            ),
            ManhuaPanel(
                panel_index=4,
                layout_type=PanelLayoutType.BORDERLESS_INSET,
                aspect_ratio="1:1",
                gutter_spacing_px=80,
                visual_description="The enemy elder turning in sudden horror, pupils contracted as spiritual pressure crushes the surrounding bamboo forest.",
                art_prompt="Manhua dramatic reaction frame, terrified aged patriarch in ornate imperial gold robes recoiling in horror, flying bamboo splinters, high contrast shadow across face.",
                dialogue_balloons=[{"character": "Elder Yan", "text": "Impossible! That spiritual domain...", "style": "panicked"}],
                sfx_onomatopoeia=[{"text": "GASP", "meaning": "breath stolen", "color": "white"}],
                camera_angle="high-angle vulnerability",
                lighting_color="cold eerie moonlight",
            ),
            ManhuaPanel(
                panel_index=5,
                layout_type=PanelLayoutType.GUTTER_TRANSITION,
                aspect_ratio="16:9",
                gutter_spacing_px=240,
                visual_description="Complete silence falls. A single obsidian feather floats down into a pool of rainwater reflecting the eclipsed moon.",
                art_prompt="Poetic contemplation panel, solitary dark feather settling onto dark ripple water surface reflecting shattered blood moon, stark negative space, moody chiaroscuro.",
                dialogue_balloons=[],
                sfx_onomatopoeia=[{"text": "DRIP...", "meaning": "ominous stillness", "color": "slate-gray"}],
                camera_angle="overhead macro",
                lighting_color="monochromatic silver and slate",
            ),
            ManhuaPanel(
                panel_index=6,
                layout_type=PanelLayoutType.VERTICAL_SCROLL_FULL,
                aspect_ratio="9:16",
                gutter_spacing_px=120,
                visual_description=f"Massive final cliffhanger reveal: A colossal nine-headed primordial dragon phantom materializes behind {protagonist_name}, its eyes burning like golden suns.",
                art_prompt=f"Monumental manhua climax splash art, massive vertical scroll composition. Colossal draconic spirit phantom looming into the stratosphere with burning golden eyes, {protagonist_name} holding blade upright in foreground. Intricate smoke tendrils, thunderous golden aura, apocalyptic scale.",
                dialogue_balloons=[{"character": protagonist_name, "text": "Nine Heavens Sovereignty... Awaken.", "style": "commanding"}],
                sfx_onomatopoeia=[{"text": "ROOOAAAAR!!", "meaning": "heaven-splitting roar", "color": "radiant gold"}],
                camera_angle="extreme low-angle grand reveal",
                lighting_color="celestial gold against abyssal black",
            ),
        ]
        selected_panels = panels[:target_panel_count] if target_panel_count <= len(panels) else panels
        total_scroll = sum(p.gutter_spacing_px + 1200 for p in selected_panels)
        return ManhuaEpisode(
            episode_number=1,
            title=title,
            reading_flow="vertical_scroll",
            summary=summary,
            cliffhanger_hook="The primordial dragon spirit awakens, shattering the sky and reversing the heavenly dao.",
            panels=selected_panels,
            estimated_scroll_length_px=total_scroll,
            theme_palette=["#0f172a", "#38bdf8", "#f59e0b", "#e11d48"],
        )

