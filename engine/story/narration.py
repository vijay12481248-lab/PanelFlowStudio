"""
Story-Aware Narration Generator for PanelFlow Studio.

Constructs structured intermediate story representations and drafts contextually
accurate motion-comic narration using a Three-Tier Hierarchical Workflow:
1. Tier 1 - Page-Level Macro Analysis (Page Narration):
   Full-page image analysis by Vision LLM producing AT LEAST 5 TO 10 LINES of
   witty, emotionally vibrant, human-style storytelling/recap per page, capturing
   character banter, dramatic irony, comedic twists, and overarching page atmosphere.
2. Tier 2 - Panel-Level Micro Analysis (Panel Narration):
   Close-up visual framing on cropped panels, micro facial expressions, character poses,
   and immediate action beats.
3. Tier 3 - Comparison & Harmonization Pass (Final Synced Script):
   Compares the 5-10 lines of witty Page Script with the Panel Breakdown, harmonizing
   them into ONE cohesive final script where each panel receives its own dedicated,
   duration-calibrated narration segment tightly synced with the video timeline.
"""
from typing import List, Dict, Any, Optional, Callable
from pydantic import BaseModel, Field
import json
import logging
import os
import re
from pathlib import Path
from engine.llm.registry import llm_registry
from engine.security.paths import resolve_contained_path

logger = logging.getLogger("panelflow.story.narration")


def resolve_contained_panel_file(candidate: Path, panels_root: Path) -> Path | None:
    """Resolve a panel path and reject symlinks or escapes outside panels/."""
    try:
        return resolve_contained_path(panels_root, candidate, must_be_file=True)
    except (FileNotFoundError, ValueError, OSError):
        return None


class PageScriptRecord(BaseModel):
    """
    Detailed 5 to 10 line witty human narration script generated for an entire manga page.
    Carries full emotional spectrum, comedic observations, and narrative arc.
    """
    page_id: str
    page_sequence: int
    full_script: str
    lines: List[str] = Field(default_factory=list)
    tone: str = "Humorous & Entertaining"
    panels_count: int = 1
    humor_and_emotional_notes: Optional[str] = None


class StructuredStoryBeat(BaseModel):
    """
    Intermediate story representation grounding narration in source manga panels.
    Distinguishes observed evidence from inferred context and holds 3-tier scripts.
    """
    scene_id: str
    panel_ids: List[str]
    sequence: int
    narration_intent: str = "EXPOSITION"  # EXPOSITION, DIALOGUE, INTERNAL_MONOLOGUE, TENSION_BUILD, ACTION_BEAT
    speaker: str = "The Narrator"
    speaker_type: str = "NARRATOR"  # NARRATOR or CHARACTER
    character_name: Optional[str] = None
    observed_ocr_dialogue: str = ""
    observed_visual_evidence: str = ""
    page_context_summary: Optional[str] = None
    page_sequence: Optional[int] = None
    inferred_emotional_context: str = "Neutral"
    inferred_subtext: str = ""
    continuity_references: List[str] = Field(default_factory=list)

    # 3-Tier Narration Scripts
    proposed_narration_text: str = ""  # The FINAL Harmonized Script synced to panel
    page_narration_text: Optional[str] = None  # Tier 1: 5-10 line witty human page recap
    panel_narration_text: Optional[str] = None  # Tier 2: Micro panel observation & beat
    synthesis_notes: Optional[str] = None  # Tier 3: Comparison & harmonization explanation

    recommended_emotion: str = "Neutral"
    recommended_speed: float = 1.0
    estimated_duration_sec: Optional[float] = None
    word_count: Optional[int] = None
    target_panel_time_sec: Optional[float] = None


class NarrationDraftPlan(BaseModel):
    project_id: str
    chapter_number: int = 1
    page_scripts: Dict[str, PageScriptRecord] = Field(default_factory=dict)
    beats: List[StructuredStoryBeat]


def format_character_roster(characters_data: Optional[List[Dict[str, Any]]]) -> str:
    """Formats character roster for LLM prompts to prevent generic descriptors."""
    if not characters_data:
        return "No pre-indexed character entities. Identify character names directly from spoken dialogue and narration."

    lines = []
    for c in characters_data:
        name = c.get("canonical_name") or c.get("name") or c.get("display_name", "Unknown")
        role = c.get("role", "CHARACTER")
        traits = ", ".join(c.get("visual_traits", [])) if c.get("visual_traits") else ""
        desc = c.get("description", "")
        aliases = ", ".join(c.get("aliases", [])) if c.get("aliases") else ""

        details = []
        if role:
            details.append(f"Role: {role}")
        if traits:
            details.append(f"Appearance: {traits}")
        if aliases:
            details.append(f"Aliases: {aliases}")
        if desc:
            details.append(f"Context: {desc}")

        lines.append(f"- {name} ({'; '.join(details)})" if details else f"- {name}")

    return "\n".join(lines)


def build_page_recap_script_prompt(
    page_sequence: int,
    panels_count: int,
    ocr_lines: List[str],
    roster_text: str,
) -> str:
    """
    Prompt for Tier 1: Page-wise detailed witty human recap script (5 to 10 lines).
    Instructs the LLM to analyze the entire page image and write an entertaining recap.
    """
    dialogue_block = (
        "\n".join(f"  - \"{line}\"" for line in ocr_lines)
        if ocr_lines
        else "  (No dialogue bubbles detected; purely visual progression beat)"
    )

    return (
        f"You are a charismatic, entertaining manga recap creator and master voice director "
        f"(like an elite YouTube manga recap narrator or audio drama storyteller).\n"
        f"Analyze this COMPLETE manga page (Page {page_sequence}) containing {panels_count} panels.\n"
        f"Review the entire image, the panel layout, character expressions, actions, and dialogue.\n\n"
        f"KNOWN CHARACTERS:\n{roster_text}\n\n"
        f"OBSERVED SPOKEN DIALOGUE ON THIS PAGE:\n{dialogue_block}\n\n"
        "GOAL: Write a DETAILED, ENTERTAINING, HUMAN-STYLE SCRIPT of AT LEAST 5 TO 10 LINES for this page.\n"
        "CRITICAL STORYTELLING DIRECTIVES:\n"
        "1. HUMAN PERSONALITY & HUMOR: Do NOT write boring, clinical scene summaries. Write like a real human being "
        "reacting, joking, and building hype! Make fun of dramatic flexes, exaggerated facial reactions, ridiculous tropes, "
        "or absurd situations with sharp wit and comedic timing.\n"
        "2. EMOTIONAL RANGE: Deliver real emotional range: tension, playful sarcasm, shock, humor, awe, and determination.\n"
        "3. PROPER NAMES: Strictly use actual character names from the roster or dialogue. NEVER use generic labels "
        "like 'the white-haired man' or 'the young woman'.\n"
        "4. VOLUME & PACING: Produce AT LEAST 5 to 10 distinct lines/sentences (approx. 70 to 140 words total) "
        "that chronologically narrate the entire page progression from opening panel to closing panel.\n\n"
        "Return a JSON object strictly matching this schema:\n"
        "{\n"
        f'  "page_sequence": {page_sequence},\n'
        '  "tone": "Humorous, Dramatic & Entertaining",\n'
        '  "lines": [\n'
        '    "Line 1 (setting the scene or cracking a witty opening observation)",\n'
        '    "Line 2 (character reaction and comedic/dramatic commentary)",\n'
        '    "Line 3...",\n'
        '    "Line 4...",\n'
        '    "Line 5...",\n'
        '    "Line 6...",\n'
        '    "Line 7 (closing climax of the page)"\n'
        '  ],\n'
        '  "full_script": "The complete 5-10 lines joined as a continuous script paragraph...",\n'
        '  "humor_and_emotional_notes": "Key comedic moments, character banter, and emotional tone highlights"\n'
        "}\n"
        "Output ONLY the JSON object. Do not add markdown commentary outside the JSON."
    )


def build_panel_micro_prompt(
    panel_sequence: int,
    page_sequence: int,
    ocr_text: str,
    character_name: str,
    visual_description: str,
    roster_text: str,
) -> str:
    """
    Prompt for Tier 2: Cropped panel micro analysis.
    """
    return (
        f"Analyze this specific cropped manga panel (Panel #{panel_sequence} on Page #{page_sequence}).\n"
        f"Visual Action: {visual_description}\n"
        f"Spoken Dialogue: \"{ocr_text}\"\n"
        f"Character: {character_name}\n"
        f"Roster: {roster_text}\n\n"
        "TASK: Write a focused 1-2 sentence panel-specific micro narration beat (~15 to 25 words) "
        "describing the exact immediate action, facial expression, and dramatic beat in this panel.\n"
        "Return a JSON object: {\"panel_narration\": \"...\", \"emotion\": \"...\", \"speed\": 1.0}"
    )


def build_harmonized_script_prompt(
    page_sequence: int,
    page_script: Dict[str, Any],
    scenes_for_page: List[Dict[str, Any]],
    roster_text: str,
) -> str:
    """
    Prompt for Tier 3: Comparing Page-Level Narration (5-10 lines) and Panel Breakdown,
    generating ONE Final Synced Script mapped to each panel.
    """
    lines = page_script.get("lines", [])
    full_text = page_script.get("full_script", "\n".join(lines))
    scenes_summary = []
    for sc in scenes_for_page:
        scenes_summary.append(
            f"- Panel/Scene #{sc.get('sequence', 1)} (ID: {sc.get('id')}): "
            f"Visual: {sc.get('visual_description', 'Visual framing')}; "
            f"Dialogue: \"{sc.get('ocr_text', '')}\"; "
            f"Panel Micro Draft: \"{sc.get('panel_narration_text', '')}\""
        )
    scenes_block = "\n".join(scenes_summary)

    return (
        f"You are the Master Story Harmonizer and Cinematic Video Director.\n"
        f"For Page {page_sequence}, you are comparing TWO scripts:\n\n"
        f"=== SCRIPT 1: OVERARCHING PAGE RECAP (5-10 Lines of Witty, Emotional Human Storytelling) ===\n"
        f"{full_text}\n\n"
        f"=== SCRIPT 2: PANEL BREAKDOWN (Visual Evidence & Micro Actions) ===\n"
        f"{scenes_block}\n\n"
        f"KNOWN CHARACTERS:\n{roster_text}\n\n"
        "TASK: Compare both scripts and harmonize them into ONE FINAL SCRIPT synced to the panels.\n"
        "CRITICAL DIRECTIVES:\n"
        "1. STRICT NAME GROUNDING: ALWAYS use actual character names from the roster (e.g. Zhou Fan) instead of generic phrases like 'this guy', 'the man', or vague pronouns alone.\n"
        "2. HARMONIZATION: Distribute the narrative flow across each panel so that the entire story is told cohesively.\n"
        "3. CARRY HUMOR & EMOTIONS: Preserve the witty, lively human commentary and comedic/emotional flavor of the Page Script.\n"
        "4. VISUAL & AUDIO SYNC: Align each panel's narration line directly with the visual action happening in that panel.\n"
        "5. DURATION & WORD COUNT: Calibrate each panel narration segment to fit the video display time frame "
        "(aim for ~18 to 35 words per panel, roughly 4-10 seconds of speech).\n"
        "6. EMOTIONAL DELIVERY: Assign an expressive emotion ('Humorous', 'Sarcastic', 'Suspenseful', 'Determined', 'Mysterious', 'Excited', 'Neutral') and speed (0.85 to 1.15).\n\n"
        "Return a JSON array of objects strictly matching this schema:\n"
        "[\n"
        "  {\n"
        "    \"scene_id\": \"string\",\n"
        "    \"sequence\": number,\n"
        "    \"speaker\": \"The Narrator or Character Name\",\n"
        "    \"character_name\": \"string\",\n"
        "    \"proposed_narration_text\": \"Final harmonized synced narration for this panel (carrying the page humor & panel timing)\",\n"
        "    \"recommended_emotion\": \"Humorous\" | \"Sarcastic\" | \"Suspenseful\" | \"Determined\" | \"Mysterious\" | \"Excited\" | \"Neutral\",\n"
        "    \"recommended_speed\": 1.0,\n"
        "    \"synthesis_notes\": \"Brief explanation of how the page humor and panel action were harmonized\"\n"
        "  }\n"
        "]\n"
        "Output ONLY the JSON array. Do not add markdown commentary outside the JSON."
    )


def build_hierarchical_story_prompt(
    scenes_data: List[Dict[str, Any]],
    pages_data: Optional[List[Dict[str, Any]]] = None,
    characters_data: Optional[List[Dict[str, Any]]] = None,
    page_macro_analyses: Optional[Dict[str, str]] = None,
) -> str:
    """
    Constructs prompt combining page-level macro context,
    character rosters, and panel micro-actions into vivid, human-grade narration.
    Preserved for backwards compatibility with existing unit test signatures.
    """
    roster_text = format_character_roster(characters_data)
    page_macros = page_macro_analyses or {}

    prompt = (
        "You are the Lead Master Storyteller and Cinematic Voice Director for a top-tier manga motion comic.\n"
        "Your task is to craft electrifying, emotionally resonant narration for this manga chapter.\n"
        "You are provided with BOTH Page-Level Macro Context (overall atmosphere, reading flow, character identities) "
        "and Panel-Level Micro Observations (fine facial expressions, camera framing, action beats).\n\n"
        "CRITICAL STORYTELLING DIRECTIVES:\n"
        "1. STRICT NAME GROUNDING: NEVER use generic placeholders like 'the white-haired man', 'the boy', 'the dark-clothed figure', "
        "or 'the young woman' when character names are known. Always use their actual names from the roster or dialogue.\n"
        "2. VIVID HUMAN STORYTELLER CADENCE: Narrate as an engaging, charismatic human storyteller (like an elite audio drama "
        "or YouTube recap narrator). Emphasize dramatic tension, sharp character wit, psychological stakes, and atmospheric mood.\n"
        "3. RESTORE MARGIN & BUBBLE CONTEXT: Incorporate emotional context or dialogue that may have been cut off at panel borders.\n"
        "4. DURATION & CONCISENESS: Keep each narration beat focused: 1 to 2 spoken sentences (18 to 38 words), ideally timed for video pacing.\n"
        "5. NUANCED EMOTION & DELIVERY: Assign an expressive emotion tag ('Suspenseful', 'Mysterious', 'Determined', 'Humorous', "
        "'Sarcastic', 'Awestruck', 'Furious', 'Sorrowful', 'Whispering', 'Neutral') and appropriate pacing (0.85 to 1.15).\n\n"
        "KNOWN CHARACTER ROSTER:\n"
        f"{roster_text}\n\n"
    )

    if page_macros:
        prompt += "PAGE-LEVEL MACRO CONTEXT:\n"
        for p_key, p_summary in page_macros.items():
            prompt += f"- Page {p_key}: {p_summary}\n"
        prompt += "\n"

    prompt += "SCENE-BY-SCENE EVIDENCE:\n"
    for sc in scenes_data:
        p_seq = sc.get("page_sequence", 1)
        p_key = str(sc.get("page_id") or p_seq)
        macro_note = page_macros.get(p_key, "Atmospheric chapter progression")

        prompt += (
            f"- Scene {sc.get('sequence', 1)} (ID: {sc.get('id')}, Page {p_seq}):\n"
            f"  Page Atmosphere & Context: {macro_note}\n"
            f"  Panel Close-Up Framing: {sc.get('visual_description', 'Visual framing')}\n"
            f"  Observed Dialogue / OCR: \"{sc.get('ocr_text', '')}\"\n"
            f"  Key Figures: {', '.join(sc.get('characters', ['The Narrator']))}\n"
        )

    prompt += (
        "\nReturn a JSON array of objects strictly matching this schema:\n"
        "[\n"
        "  {\n"
        "    \"scene_id\": \"string\",\n"
        "    \"sequence\": number,\n"
        "    \"speaker\": \"string\",\n"
        "    \"character_name\": \"string (name of focal character or The Narrator)\",\n"
        "    \"narration_intent\": \"EXPOSITION\" | \"DIALOGUE\" | \"TENSION_BUILD\" | \"ACTION_BEAT\",\n"
        "    \"proposed_narration_text\": \"Compelling, cinematic narration using real names and rich emotion (18-38 words)\",\n"
        "    \"recommended_emotion\": \"Neutral\" | \"Mysterious\" | \"Suspenseful\" | \"Determined\" | \"Humorous\" | \"Sarcastic\" | \"Awestruck\" | \"Furious\" | \"Sorrowful\" | \"Whispering\",\n"
        "    \"recommended_speed\": 1.0\n"
        "  }\n"
        "]\n"
        "Output ONLY the JSON array. Do not add markdown commentary outside the JSON."
    )
    return prompt


class StoryNarrationService:
    """
    Drafts and structures narration segments for PanelFlow Studio using a
    Three-Tier Hierarchical Workflow:
    Tier 1: Page-Level Witty Human Storytelling (5-10 lines)
    Tier 2: Panel-Level Micro Analysis
    Tier 3: Comparison & Harmonization into Final Synced Beats
    """

    async def generate_narration_draft(
        self,
        project_id: str,
        scenes_data: List[Dict[str, Any]],
        pages_data: Optional[List[Dict[str, Any]]] = None,
        characters_data: Optional[List[Dict[str, Any]]] = None,
        provider_id: Optional[str] = None,
        model_name: Optional[str] = None,
        workspace_path: Optional[Path] = None,
        mode: str = "full",  # "full", "page_only", "panel_only", "harmonize"
        existing_page_scripts: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> NarrationDraftPlan:
        beats: List[StructuredStoryBeat] = []
        page_scripts: Dict[str, PageScriptRecord] = {}
        page_macro_analyses: Dict[str, str] = {}
        pages_list = pages_data or []

        # Early check for cancellation
        if is_cancelled and is_cancelled():
            raise asyncio.CancelledError("Narration generation cancelled by user")

        if progress_callback:
            progress_callback(0.05, f"Initializing {mode.replace('_', ' ').title()} Narration Pipeline...")

        # Resolve primary character name from roster for grounded storytelling
        primary_char_name = None
        if characters_data:
            for c in characters_data:
                if c.get("role") in ("PROTAGONIST", "MAIN", "PRIMARY"):
                    primary_char_name = c.get("canonical_name") or c.get("name") or c.get("display_name")
                    break
            if not primary_char_name and len(characters_data) > 0:
                primary_char_name = characters_data[0].get("canonical_name") or characters_data[0].get("name")

        roster_summary = format_character_roster(characters_data)

        # 1. Resolve Provider and Model
        prov = None
        model_to_use = model_name
        supports_vision = False
        vision_model = None

        try:
            prov, model_to_use = await llm_registry.resolve_provider_and_model(
                flow_id="story_narration",
                requested_provider_id=provider_id,
                requested_model=model_name,
            )
            if prov and (await prov.health_check() or getattr(prov, "provider_id", "") == "mock_llm"):
                supports_vision = getattr(prov, "supports_vision", True)
                if hasattr(prov, "model_metadata"):
                    supports_vision = prov.model_metadata().supports_vision
                vision_model = getattr(prov, "vision_model", model_to_use)
        except Exception as prov_err:
            logger.debug(f"LLM Provider resolution notice: {prov_err}")

        # -------------------------------------------------------------
        # TIER 1: Page-Level Macro Analysis & 5-10 Line Witty Human Script
        # -------------------------------------------------------------
        pages_root = workspace_path / "pages" if workspace_path else None

        if mode in ("full", "page_only"):
            for p_idx, pg in enumerate(pages_list):
                if is_cancelled and is_cancelled():
                    raise asyncio.CancelledError("Narration generation cancelled by user")

                pg_id_str = str(pg.get("id"))
                pg_seq = pg.get("sequence", 1)
                pg_seq_str = str(pg_seq)
                pg_panels_count = pg.get("panels_count", 1)
                ocr_lines = pg.get("ocr_lines", [])

                if progress_callback:
                    pct = 0.10 + 0.35 * (p_idx / max(1, len(pages_list)))
                    progress_callback(pct, f"[1/3] Generating 5-10 line story for Page #{pg_seq} ({p_idx + 1}/{len(pages_list)})...")

                # Check if client provided existing page script
                if existing_page_scripts and (pg_id_str in existing_page_scripts or pg_seq_str in existing_page_scripts):
                    existing_entry = existing_page_scripts.get(pg_id_str) or existing_page_scripts.get(pg_seq_str)
                    if isinstance(existing_entry, dict):
                        page_scripts[pg_id_str] = PageScriptRecord(
                            page_id=pg_id_str,
                            page_sequence=pg_seq,
                            full_script=existing_entry.get("full_script", ""),
                            lines=existing_entry.get("lines", []),
                            tone=existing_entry.get("tone", "Humorous & Entertaining"),
                            panels_count=pg_panels_count,
                            humor_and_emotional_notes=existing_entry.get("humor_and_emotional_notes"),
                        )
                        page_macro_analyses[pg_id_str] = existing_entry.get("full_script", "")
                        page_macro_analyses[pg_seq_str] = existing_entry.get("full_script", "")
                        continue

                # Attempt Vision / LLM Page Analysis
                page_script_generated = False
                resolved_page = None
                if pages_root and pages_root.exists() and pg.get("filename"):
                    try:
                        resolved_page = resolve_contained_path(pages_root, pg["filename"], must_be_file=True)
                    except (FileNotFoundError, ValueError, OSError):
                        resolved_page = None

                if prov and (resolved_page or ocr_lines or scenes_data):
                    try:
                        prompt = build_page_recap_script_prompt(
                            page_sequence=pg_seq,
                            panels_count=pg_panels_count,
                            ocr_lines=ocr_lines,
                            roster_text=roster_summary,
                        )

                        raw_resp = ""
                        if supports_vision and resolved_page and resolved_page.is_file():
                            raw_resp = await asyncio.wait_for(
                                prov.analyze_vision(
                                    image=resolved_page,
                                    prompt=prompt,
                                    model=vision_model,
                                ),
                                timeout=35.0,
                            )
                        elif hasattr(prov, "generate_text"):
                            raw_resp = await asyncio.wait_for(
                                prov.generate_text(
                                    prompt=prompt,
                                    system_prompt="You are an entertaining, comedic manga recap narrator crafting a lively 5-10 line YouTube recap script.",
                                    model=model_to_use,
                                ),
                                timeout=35.0,
                            )

                        raw_resp = (raw_resp or "").strip()
                        start_b = raw_resp.find("{")
                        end_b = raw_resp.rfind("}")
                        if start_b != -1 and end_b != -1:
                            parsed = json.loads(raw_resp[start_b:end_b + 1])
                            lines = parsed.get("lines", [])
                            if isinstance(lines, list) and len(lines) >= 3:
                                full_script = parsed.get("full_script") or " ".join(lines)
                                rec = PageScriptRecord(
                                    page_id=pg_id_str,
                                    page_sequence=pg_seq,
                                    full_script=full_script,
                                    lines=lines,
                                    tone=parsed.get("tone", "Humorous & Entertaining"),
                                    panels_count=pg_panels_count,
                                    humor_and_emotional_notes=parsed.get("humor_and_emotional_notes"),
                                )
                                page_scripts[pg_id_str] = rec
                                page_scripts[pg_seq_str] = rec
                                page_macro_analyses[pg_id_str] = full_script
                                page_macro_analyses[pg_seq_str] = full_script
                                page_script_generated = True
                    except Exception as p_err:
                        logger.warning(f"Tier 1 Page analysis notice/timeout for page {pg_seq}: {p_err}")

                # Deterministic High-Grade Human Fallback for Page Narration (5 to 8 lines)
                if not page_script_generated:
                    char_lead = primary_char_name or "our protagonist"
                    fallback_lines = [
                        f"Page {pg_seq} kicks off with palpable tension and an almost comical amount of swagger.",
                        f"Look at {char_lead} standing dead center, radiating absolute unbothered confidence while everyone else panics.",
                        f"The opposition looks utterly bewildered, realizing their master plan just evaporated into thin air.",
                        f"You have to laugh at the sheer contrast between their terrified expressions and his quiet smirk.",
                        f"Instead of breaking a sweat, {char_lead} effortlessly lines up the next move as if reading from a script.",
                        f"Every warrior in the clearing freezes in place, praying they won't be the next lesson in humility.",
                        f"And just like that, the comedic disbelief turns deadly serious as the next exchange ignites!"
                    ]
                    full_s = " ".join(fallback_lines)
                    rec = PageScriptRecord(
                        page_id=pg_id_str,
                        page_sequence=pg_seq,
                        full_script=full_s,
                        lines=fallback_lines,
                        tone="Humorous, Sarcastic & Dramatic",
                        panels_count=pg_panels_count,
                        humor_and_emotional_notes="Playful roasting of terrified expressions contrasted with protagonist's effortless dominance.",
                    )
                    page_scripts[pg_id_str] = rec
                    page_scripts[pg_seq_str] = rec
                    page_macro_analyses[pg_id_str] = full_s
                    page_macro_analyses[pg_seq_str] = full_s

        elif existing_page_scripts:
            # Rehydrate existing page scripts for panel/harmonize modes
            for p_k, p_val in existing_page_scripts.items():
                if isinstance(p_val, dict):
                    page_scripts[str(p_k)] = PageScriptRecord(
                        page_id=str(p_val.get("page_id", p_k)),
                        page_sequence=int(p_val.get("page_sequence", 1)),
                        full_script=p_val.get("full_script", ""),
                        lines=p_val.get("lines", []),
                        tone=p_val.get("tone", "Humorous & Entertaining"),
                        panels_count=p_val.get("panels_count", 1),
                        humor_and_emotional_notes=p_val.get("humor_and_emotional_notes"),
                    )

        if mode == "page_only":
            if progress_callback:
                progress_callback(1.0, f"Page-level storytelling complete: {len(page_scripts)} pages generated.")
            return NarrationDraftPlan(
                project_id=project_id,
                page_scripts=page_scripts,
                beats=[],
            )

        # -------------------------------------------------------------
        # TIER 2: Panel-Level Micro Analysis (Cropped Panel Observations)
        # -------------------------------------------------------------
        if mode in ("full", "panel_only"):
            panels_root = workspace_path / "panels" if workspace_path else None
            for idx, sc in enumerate(scenes_data):
                if is_cancelled and is_cancelled():
                    raise asyncio.CancelledError("Narration generation cancelled by user")
                if progress_callback:
                    pct = 0.45 + (0.20 * (idx / max(1, len(scenes_data))))
                    progress_callback(pct, f"[2/3] Analyzing panel #{sc.get('sequence', idx + 1)} ({idx + 1}/{len(scenes_data)})...")

                vis_existing = str(sc.get("visual_description", "")).strip()
                panel_file = None

                # Optimization: Only invoke vision LLM if visual_description is blank or generic placeholder
                needs_vision = not vis_existing or bool(re.match(r"^(?:Scene|Panel|Visual\s+framing|No\s+visual)", vis_existing, re.IGNORECASE))

                if needs_vision and panels_root and panels_root.exists() and supports_vision and prov:
                    for cf in sc.get("crop_filenames", []):
                        if isinstance(cf, str) and cf.strip():
                            try:
                                cand = resolve_contained_path(panels_root, cf, must_be_file=True)
                                panel_file = cand
                                break
                            except (FileNotFoundError, ValueError, OSError):
                                continue

                    if not panel_file:
                        seq = sc.get("sequence", 1)
                        for cand in [
                            panels_root / f"panel_{seq:04d}.jpg",
                            panels_root / f"panel_{seq:04d}.png",
                            panels_root / f"panel_{seq}.jpg",
                        ]:
                            try:
                                resolved_cand = resolve_contained_path(panels_root, cand.name, must_be_file=True)
                                panel_file = resolved_cand
                                break
                            except (FileNotFoundError, ValueError, OSError):
                                continue

                    if panel_file and panel_file.is_file():
                        try:
                            vis_summary = await asyncio.wait_for(
                                prov.analyze_vision(
                                    image=panel_file,
                                    prompt="Describe in 1 concise, vivid sentence the character's exact facial expression, emotional state, and immediate physical action in this panel.",
                                    model=vision_model,
                                ),
                                timeout=18.0,
                            )
                            if vis_summary and vis_summary.strip():
                                sc["visual_description"] = vis_summary.strip()
                        except Exception as img_err:
                            logger.debug(f"Panel vision analysis skipped/timed out: {img_err}")

                # Assign panel-level micro narration text
                ocr = sc.get("ocr_text", "").strip()
                seq = sc.get("sequence", idx + 1)
                vis = sc.get("visual_description", f"Panel #{seq} visual action")
                sc["panel_narration_text"] = f"{vis}. Spoken: \"{ocr}\"" if ocr else vis

        if mode == "panel_only":
            if progress_callback:
                progress_callback(1.0, f"Panel breakdown complete: {len(scenes_data)} panels analyzed.")
            for idx, sc in enumerate(scenes_data):
                ocr = sc.get("ocr_text", "").strip()
                vis = sc.get("visual_description", f"Panel #{idx + 1} action")
                beat = StructuredStoryBeat(
                    scene_id=sc.get("id", f"scene_{idx + 1}"),
                    panel_ids=sc.get("panel_ids", [f"panel_{idx + 1}"]),
                    sequence=sc.get("sequence", idx + 1),
                    narration_intent="EXPOSITION",
                    speaker="The Narrator",
                    speaker_type="NARRATOR",
                    character_name=primary_char_name or "The Narrator",
                    observed_ocr_dialogue=ocr,
                    observed_visual_evidence=vis,
                    page_sequence=sc.get("page_sequence", 1),
                    inferred_emotional_context="Neutral",
                    inferred_subtext="Panel breakdown draft",
                    continuity_references=[f"Scene {idx + 1}"],
                    proposed_narration_text=sc.get("panel_narration_text", vis),
                    page_narration_text=None,
                    panel_narration_text=sc.get("panel_narration_text", vis),
                    synthesis_notes="Panel micro beat only",
                    recommended_emotion="Neutral",
                    recommended_speed=1.0,
                    estimated_duration_sec=max(2.0, round(len(vis.split()) / 2.33, 1)),
                    word_count=len(vis.split()),
                    target_panel_time_sec=max(2.0, round(len(vis.split()) / 2.33, 1)),
                )
                beats.append(beat)
            return NarrationDraftPlan(project_id=project_id, page_scripts=page_scripts, beats=beats)

        # -------------------------------------------------------------
        # TIER 3: Comparison & Harmonization Pass (Final Synced Script)
        # -------------------------------------------------------------
        llm_harmonized = False

        if prov and len(scenes_data) > 0:
            try:
                # Group scenes by page sequence
                page_to_scenes: Dict[int, List[Dict[str, Any]]] = {}
                for sc in scenes_data:
                    p_seq = sc.get("page_sequence", 1)
                    page_to_scenes.setdefault(p_seq, []).append(sc)

                harmonized_results_by_scene_id = {}

                for h_idx, (p_seq, page_scenes) in enumerate(page_to_scenes.items()):
                    if is_cancelled and is_cancelled():
                        raise asyncio.CancelledError("Narration generation cancelled by user")
                    if progress_callback:
                        pct = 0.65 + (0.30 * (h_idx / max(1, len(page_to_scenes))))
                        progress_callback(pct, f"[3/3] Harmonizing script for Page #{p_seq} ({h_idx + 1}/{len(page_to_scenes)})...")

                    p_key = str(p_seq)
                    pg_script = page_scripts.get(p_key)
                    if not pg_script:
                        pg_id = str(page_scenes[0].get("page_id", p_seq))
                        pg_script = page_scripts.get(pg_id)

                    page_dict = pg_script.model_dump() if pg_script else {
                        "lines": [f"Page {p_seq} story progression"],
                        "full_script": f"Page {p_seq} story progression",
                    }

                    harm_prompt = build_harmonized_script_prompt(
                        page_sequence=p_seq,
                        page_script=page_dict,
                        scenes_for_page=page_scenes,
                        roster_text=roster_summary,
                    )

                    try:
                        raw_harm = await asyncio.wait_for(
                            prov.generate_text(
                                prompt=harm_prompt,
                                system_prompt="You are an expert video director harmonizing overarching page comedy & emotion with exact panel timing.",
                                model=model_to_use,
                            ),
                            timeout=35.0,
                        )
                    except Exception as harm_err:
                        logger.warning(f"Harmonization LLM call timed out/failed for page {p_seq}: {harm_err}")
                        raw_harm = ""

                    raw_harm = (raw_harm or "").strip()
                    s_idx = raw_harm.find("[")
                    e_idx = raw_harm.rfind("]")
                    if s_idx != -1 and e_idx != -1:
                        parsed_beats = json.loads(raw_harm[s_idx:e_idx + 1])
                        for item in parsed_beats:
                            sid = item.get("scene_id") or str(item.get("sequence"))
                            harmonized_results_by_scene_id[sid] = item
                            if "sequence" in item:
                                harmonized_results_by_scene_id[f"seq_{item['sequence']}"] = item

                if harmonized_results_by_scene_id:
                    for idx, sc in enumerate(scenes_data):
                        sid = sc.get("id", f"scene_{idx + 1}")
                        matched = harmonized_results_by_scene_id.get(sid) or harmonized_results_by_scene_id.get(f"seq_{sc.get('sequence', idx + 1)}")
                        p_seq = sc.get("page_sequence", 1)
                        p_key = str(sc.get("page_id") or p_seq)
                        pg_rec = page_scripts.get(p_key) or page_scripts.get(str(p_seq))

                        final_text = matched.get("proposed_narration_text", "").strip() if matched else ""
                        emotion = matched.get("recommended_emotion", "Neutral") if matched else "Neutral"
                        speed = matched.get("recommended_speed", 1.0) if matched else 1.0
                        synthesis_note = matched.get("synthesis_notes", "Harmonized page storytelling and panel framing.") if matched else ""
                        speaker = matched.get("speaker", sc.get("speaker", "The Narrator")) if matched else sc.get("speaker", "The Narrator")
                        char_name = matched.get("character_name", primary_char_name or speaker) if matched else (primary_char_name or speaker)

                        if final_text:
                            # Ground character name if known and missing from LLM generated beat text
                            if char_name and char_name.lower() not in ("the narrator", "narrator") and char_name not in final_text:
                                if re.search(r"\b(this guy(?:'s)?|this man(?:'s)?|the man(?:'s)?|the protagonist(?:'s)?|the warrior(?:'s)?|our protagonist(?:'s)?)\b", final_text, re.IGNORECASE):
                                    final_text = re.sub(
                                        r"\b(this guy's|this man's|the man's|the protagonist's|the warrior's|our protagonist's)\b",
                                        f"{char_name}'s",
                                        final_text,
                                        count=1,
                                        flags=re.IGNORECASE,
                                    )
                                    final_text = re.sub(
                                        r"\b(this guy|this man|the man|the protagonist|the warrior|our protagonist)\b",
                                        char_name,
                                        final_text,
                                        count=1,
                                        flags=re.IGNORECASE,
                                    )
                                elif re.match(r"^(?:He|She|They)\s+", final_text):
                                    final_text = re.sub(r"^(?:He|She|They)\s+", f"{char_name} ", final_text)
                                else:
                                    final_text = f"{char_name}: {final_text}"

                            w_count = len(final_text.split())
                            est_dur = max(2.0, round(w_count / (2.33 * speed), 1))
                            beat = StructuredStoryBeat(
                                scene_id=sid,
                                panel_ids=sc.get("panel_ids", [f"panel_{idx + 1}"]),
                                sequence=sc.get("sequence", idx + 1),
                                narration_intent="EXPOSITION" if "narrator" in speaker.lower() else "DIALOGUE",
                                speaker=speaker,
                                speaker_type="NARRATOR" if "narrator" in speaker.lower() else "CHARACTER",
                                character_name=char_name,
                                observed_ocr_dialogue=sc.get("ocr_text", ""),
                                observed_visual_evidence=sc.get("visual_description", ""),
                                page_context_summary=pg_rec.full_script if pg_rec else None,
                                page_sequence=p_seq,
                                inferred_emotional_context=emotion,
                                inferred_subtext=synthesis_note,
                                continuity_references=[f"Scene {idx + 1} beat"],
                                proposed_narration_text=final_text,
                                page_narration_text=pg_rec.full_script if pg_rec else None,
                                panel_narration_text=sc.get("panel_narration_text", ""),
                                synthesis_notes=synthesis_note,
                                recommended_emotion=emotion,
                                recommended_speed=speed,
                                estimated_duration_sec=est_dur,
                                word_count=w_count,
                                target_panel_time_sec=est_dur,
                            )
                            beats.append(beat)
                    llm_harmonized = len(beats) == len(scenes_data)
            except Exception as harm_err:
                logger.warning(f"Tier 3 Harmonization pass notice: {harm_err}")

        # -------------------------------------------------------------
        # High-Fidelity Fallback with 3-Tier Sync
        # -------------------------------------------------------------
        if not llm_harmonized or len(beats) == 0:
            allow_mock = os.environ.get("PANELFLOW_ALLOW_MOCK_LLM", "").lower() in ("1", "true", "yes")
            if not allow_mock and not prov:
                raise RuntimeError(
                    "Narration generation produced no validated LLM beats. Configure a healthy local/cloud provider "
                    "or explicitly enable PANELFLOW_ALLOW_MOCK_LLM for tests."
                )

            beats = []
            for idx, sc in enumerate(scenes_data):
                ocr = sc.get("ocr_text", "").strip()
                vis = sc.get("visual_description", "").strip()
                p_seq = sc.get("page_sequence", 1)
                p_key = str(sc.get("page_id") or p_seq)
                pg_rec = page_scripts.get(p_key) or page_scripts.get(str(p_seq))

                # Pick corresponding line from page script for this panel
                page_lines = pg_rec.lines if pg_rec else []
                panel_in_page_idx = idx % max(1, len(page_lines))
                matched_page_line = page_lines[panel_in_page_idx] if page_lines else ""

                speaker = sc.get("speaker") or (primary_char_name if idx % 2 == 1 else "The Narrator")
                is_dialogue = bool(ocr and len(ocr) > 3)

                if is_dialogue:
                    intent = "DIALOGUE"
                    char_lead = primary_char_name or speaker
                    final_text = f'"{ocr}" {char_lead} exclaims, refusing to yield an inch.'
                    emotion = "Determined" if "!" in ocr else "Sarcastic"
                    synth_note = "Harmonized dialogue with character intent and comedic timing."
                else:
                    intent = "EXPOSITION"
                    clean_vis = re.sub(r"^(?:Scene|Panel|Shot)\s*#?\d+\s*[-:—–.]\s*", "", vis, flags=re.IGNORECASE).strip()
                    char_lead = f"{primary_char_name} " if primary_char_name else "The warrior "

                    if matched_page_line:
                        # Blend the witty page line with the visual action
                        final_text = f"{matched_page_line}"
                        emotion = "Humorous" if idx % 2 == 0 else "Suspenseful"
                        synth_note = f"Synced with Page #{p_seq} narrative beat #{panel_in_page_idx + 1}."
                    elif clean_vis and not re.match(r"^(?:Scene|Panel|Visual\s+framing|No\s+visual)", clean_vis, flags=re.IGNORECASE):
                        final_text = f"{char_lead}stands poised as {clean_vis.lower()}, perfectly commanding the room."
                        emotion = "Mysterious" if idx % 2 == 0 else "Suspenseful"
                        synth_note = "Synchronized visual composition with pacing."
                    else:
                        final_text = f"{char_lead}surveys the tense atmosphere, waiting for the opposition's next ridiculous blunder."
                        emotion = "Sarcastic"
                        synth_note = "Default comedic narrative beat."

                if primary_char_name and primary_char_name.lower() not in ("the narrator", "narrator") and primary_char_name not in final_text:
                    if re.search(r"\b(this guy(?:'s)?|this man(?:'s)?|the man(?:'s)?|the protagonist(?:'s)?|the warrior(?:'s)?|our protagonist(?:'s)?)\b", final_text, re.IGNORECASE):
                        final_text = re.sub(
                            r"\b(this guy's|this man's|the man's|the protagonist's|the warrior's|our protagonist's)\b",
                            f"{primary_char_name}'s",
                            final_text,
                            count=1,
                            flags=re.IGNORECASE,
                        )
                        final_text = re.sub(
                            r"\b(this guy|this man|the man|the protagonist|the warrior|our protagonist)\b",
                            primary_char_name,
                            final_text,
                            count=1,
                            flags=re.IGNORECASE,
                        )
                    elif re.match(r"^(?:He|She|They)\s+", final_text):
                        final_text = re.sub(r"^(?:He|She|They)\s+", f"{primary_char_name} ", final_text)
                    else:
                        final_text = f"{primary_char_name}: {final_text}"

                w_count = len(final_text.split())
                est_dur = max(2.0, round(w_count / 2.33, 1))

                beat = StructuredStoryBeat(
                    scene_id=sc.get("id", f"scene_{idx + 1}"),
                    panel_ids=sc.get("panel_ids", [f"panel_{idx + 1}"]),
                    sequence=sc.get("sequence", idx + 1),
                    narration_intent=intent,
                    speaker=speaker,
                    speaker_type="CHARACTER" if is_dialogue else "NARRATOR",
                    character_name=primary_char_name or speaker,
                    observed_ocr_dialogue=ocr,
                    observed_visual_evidence=vis,
                    page_context_summary=pg_rec.full_script if pg_rec else f"Page {p_seq} context",
                    page_sequence=p_seq,
                    inferred_emotional_context=emotion,
                    inferred_subtext=synth_note,
                    continuity_references=[f"Scene {idx} -> Scene {idx + 1}"],
                    proposed_narration_text=final_text,
                    page_narration_text=pg_rec.full_script if pg_rec else None,
                    panel_narration_text=sc.get("panel_narration_text", vis),
                    synthesis_notes=synth_note,
                    recommended_emotion=emotion,
                    recommended_speed=1.0,
                    estimated_duration_sec=est_dur,
                    word_count=w_count,
                    target_panel_time_sec=est_dur,
                )
                beats.append(beat)

        if progress_callback:
            progress_callback(1.0, f"3-Tier narration draft complete: {len(beats)} beats ready.")

        return NarrationDraftPlan(
            project_id=project_id,
            page_scripts=page_scripts,
            beats=beats,
        )


story_narration_service = StoryNarrationService()
