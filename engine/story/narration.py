"""
Story-Aware Narration Generator for PanelFlow Studio.

Constructs structured intermediate story representations and drafts contextually
accurate motion-comic narration using a Two-Tier Hierarchical Analysis:
1. Page-Level Macro Analysis: Full-page layout, reading flow, overarching environmental atmosphere,
   character roster identification (proper names instead of generic descriptors), and margin speech bubbles.
2. Panel-Level Micro Analysis: Close-up visual framing, fine facial expressions, and immediate action beats.
3. Narrative Synthesis Pass: Harmonizes macro page context and micro panel observations into
   human-grade, emotionally vibrant, professional motion-comic narration.
"""
from typing import List, Dict, Any, Optional
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


class StructuredStoryBeat(BaseModel):
    """
    Intermediate story representation grounding narration in source manga panels.
    Distinguishes observed evidence from inferred context.
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
    proposed_narration_text: str = ""
    recommended_emotion: str = "Neutral"
    recommended_speed: float = 1.0


class NarrationDraftPlan(BaseModel):
    project_id: str
    chapter_number: int = 1
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


def build_hierarchical_story_prompt(
    scenes_data: List[Dict[str, Any]],
    pages_data: Optional[List[Dict[str, Any]]] = None,
    characters_data: Optional[List[Dict[str, Any]]] = None,
    page_macro_analyses: Optional[Dict[str, str]] = None,
) -> str:
    """
    Constructs an advanced two-tier prompt combining page-level macro context,
    character rosters, and panel micro-actions into vivid, human-grade narration.
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
    Drafts and structures narration segments for PanelFlow Studio using
    Two-Tier Hierarchical Page & Panel Analysis.
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
    ) -> NarrationDraftPlan:
        beats: List[StructuredStoryBeat] = []
        page_macro_analyses: Dict[str, str] = {}

        # 1. Resolve Provider and Model via Centralized Resolution Hierarchy
        llm_succeeded = False
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

                # 2. Tier 1: Page-Level Macro Analysis (Full Page Context & Margin Text)
                pages_root = workspace_path / "pages" if workspace_path else None
                pages_list = pages_data or []

                if workspace_path and supports_vision and pages_root and pages_root.exists():
                    # Identify all unique pages referenced in scenes
                    referenced_page_keys = set()
                    for sc in scenes_data:
                        pk = sc.get("page_id") or str(sc.get("page_sequence", 1))
                        referenced_page_keys.add(str(pk))

                    roster_summary = format_character_roster(characters_data)

                    for pg in pages_list:
                        pg_id_str = str(pg.get("id"))
                        pg_seq_str = str(pg.get("sequence"))
                        if pg_id_str not in referenced_page_keys and pg_seq_str not in referenced_page_keys:
                            continue

                        pg_filename = pg.get("filename")
                        if not pg_filename:
                            continue

                        try:
                            resolved_page = resolve_contained_path(pages_root, pg_filename, must_be_file=True)
                        except (FileNotFoundError, ValueError, OSError):
                            continue

                        if resolved_page and resolved_page.is_file():
                            try:
                                pg_ocr_text = " ".join(pg.get("ocr_lines", []))
                                pg_prompt = (
                                    f"Analyze this complete manga page (Page {pg.get('sequence', 1)}) containing {pg.get('panels_count', 'multiple')} panels.\n"
                                    f"Known Characters: {roster_summary}\n"
                                    f"Observed Dialogue on this Page: \"{pg_ocr_text[:300]}\"\n\n"
                                    "Provide a concise, 2-3 sentence macro narrative summary:\n"
                                    "1. WHO is present? Name characters from the roster or dialog (avoid generic labels like 'white-haired man').\n"
                                    "2. What is the overall setting, lighting, and dramatic mood?\n"
                                    "3. What major narrative transition, conflict, or revelation takes place across the page?"
                                )
                                page_summary = await prov.analyze_vision(
                                    image=resolved_page,
                                    prompt=pg_prompt,
                                    model=vision_model,
                                )
                                if page_summary and page_summary.strip():
                                    clean_summary = page_summary.strip()
                                    page_macro_analyses[pg_id_str] = clean_summary
                                    page_macro_analyses[pg_seq_str] = clean_summary
                            except Exception as page_err:
                                logger.debug(f"Page vision analysis skipped for {pg_filename}: {page_err}")

                # If vision was unavailable or images missing, synthesize text-based macro summaries
                for pg in pages_list:
                    pg_id_str = str(pg.get("id"))
                    pg_seq_str = str(pg.get("sequence"))
                    if pg_id_str not in page_macro_analyses:
                        ocr_lines = pg.get("ocr_lines", [])
                        summary = f"Page {pg.get('sequence', 1)} contains {pg.get('panels_count', 1)} panels. "
                        if ocr_lines:
                            summary += f"Spoken dialog involves: {' '.join(ocr_lines[:2])}"
                        else:
                            summary += "Pivotal visual progression beat."
                        page_macro_analyses[pg_id_str] = summary
                        page_macro_analyses[pg_seq_str] = summary

                # 3. Tier 2: Panel-Level Micro Analysis (Close-Up Expressions & Micro Actions)
                if workspace_path and supports_vision:
                    panels_root = workspace_path / "panels"
                    for sc in scenes_data:
                        panel_file_to_analyze = None
                        for cf in sc.get("crop_filenames", []):
                            if not isinstance(cf, str) or not cf.strip():
                                continue
                            try:
                                cand = resolve_contained_path(panels_root, cf, must_be_file=True)
                                panel_file_to_analyze = cand
                                break
                            except (FileNotFoundError, ValueError, OSError):
                                continue

                        if not panel_file_to_analyze and panels_root.exists():
                            seq = sc.get("sequence", 1)
                            for cand in [
                                panels_root / f"panel_{seq:04d}.jpg",
                                panels_root / f"panel_{seq:04d}.png",
                                panels_root / f"panel_{seq}.jpg",
                            ]:
                                try:
                                    resolved_cand = resolve_contained_path(panels_root, cand.name, must_be_file=True)
                                    panel_file_to_analyze = resolved_cand
                                    break
                                except (FileNotFoundError, ValueError, OSError):
                                    continue

                        if panel_file_to_analyze:
                            try:
                                vis_summary = await prov.analyze_vision(
                                    image=panel_file_to_analyze,
                                    prompt="Describe in 1 concise, vivid sentence the character's exact facial expression, emotional state, and immediate physical action in this panel.",
                                    model=vision_model,
                                )
                                existing_visual = str(sc.get("visual_description", "")).strip()
                                is_placeholder = (
                                    not existing_visual
                                    or existing_visual.lower() in {"no visual description", "no visual", "visual unavailable"}
                                    or bool(re.match(r"^(?:panel|scene|shot)\s*#?\d*\s*(?:visual composition|visual framing) ", existing_visual, re.IGNORECASE))
                                )
                                if vis_summary and is_placeholder:
                                    sc["visual_description"] = vis_summary.strip()
                            except Exception as img_err:
                                logger.debug(f"Panel vision analysis skipped: {img_err}")

                # 4. Tier 3: Narrative Synthesis Pass (Comparing Page Macro & Panel Micro)
                prompt = build_hierarchical_story_prompt(
                    scenes_data=scenes_data,
                    pages_data=pages_data,
                    characters_data=characters_data,
                    page_macro_analyses=page_macro_analyses,
                )

                raw_text = await prov.generate_text(
                    prompt=prompt,
                    system_prompt="You are an expert cinematic manga narrator and voice director crafting professional audio recap narration.",
                    model=model_to_use,
                )
                raw_text = raw_text.strip()

                # Parse JSON array from response
                start_idx = raw_text.find("[")
                end_idx = raw_text.rfind("]")
                if start_idx != -1 and end_idx != -1:
                    parsed = json.loads(raw_text[start_idx:end_idx + 1])
                    for item in parsed:
                        sc_match = next((s for s in scenes_data if s.get("id") == item.get("scene_id") or s.get("sequence") == item.get("sequence")), None)
                        p_seq = sc_match.get("page_sequence", 1) if sc_match else 1
                        p_key = str(sc_match.get("page_id") or p_seq) if sc_match else str(p_seq)

                        char_fallback = None
                        if characters_data:
                            char_fallback = characters_data[0].get("canonical_name") or characters_data[0].get("name")

                        char_from_scene = sc_match.get("speaker") or (sc_match.get("characters", [None])[0] if sc_match and sc_match.get("characters") else None)
                        raw_char_name = item.get("character_name")
                        if not raw_char_name or raw_char_name.strip().lower() in ("the narrator", "narrator"):
                            resolved_char_name = char_from_scene or char_fallback or "The Narrator"
                        else:
                            resolved_char_name = raw_char_name

                        beat = StructuredStoryBeat(
                            scene_id=item.get("scene_id", sc_match.get("id") if sc_match else f"sc_{item.get('sequence', 1)}"),
                            panel_ids=sc_match.get("panel_ids", []) if sc_match else [],
                            sequence=item.get("sequence", 1),
                            narration_intent=item.get("narration_intent", "EXPOSITION"),
                            speaker=item.get("speaker", "The Narrator"),
                            speaker_type="NARRATOR" if "narrator" in item.get("speaker", "").lower() else "CHARACTER",
                            character_name=resolved_char_name,
                            observed_ocr_dialogue=sc_match.get("ocr_text", "") if sc_match else "",
                            observed_visual_evidence=sc_match.get("visual_description", "") if sc_match else "",
                            page_context_summary=page_macro_analyses.get(p_key),
                            page_sequence=p_seq,
                            inferred_emotional_context=item.get("recommended_emotion", "Neutral"),
                            inferred_subtext=item.get("subtext", "Narrative progression"),
                            continuity_references=[f"Scene {item.get('sequence', 1)} context"],
                            proposed_narration_text=item.get("proposed_narration_text", "").strip(),
                            recommended_emotion=item.get("recommended_emotion", "Neutral"),
                            recommended_speed=item.get("recommended_speed", 1.0),
                        )
                        beats.append(beat)
                    llm_succeeded = len(beats) > 0
        except Exception as e:
            logger.warning(f"Hierarchical LLM narration draft failed: {e}. Falling back to contextual analysis.")

        # High-Fidelity Fallback with Character Names and Page Context
        if not llm_succeeded or len(beats) == 0:
            allow_mock = os.environ.get("PANELFLOW_ALLOW_MOCK_LLM", "").lower() in ("1", "true", "yes")
            if not allow_mock:
                raise RuntimeError(
                    "Narration generation produced no validated LLM beats. Configure a healthy local/cloud provider "
                    "or explicitly enable PANELFLOW_ALLOW_MOCK_LLM for tests."
                )

            # Resolve primary character name from roster
            primary_char_name = None
            if characters_data:
                for c in characters_data:
                    if c.get("role") in ("PROTAGONIST", "MAIN", "PRIMARY"):
                        primary_char_name = c.get("canonical_name") or c.get("name") or c.get("display_name")
                        break
                if not primary_char_name and len(characters_data) > 0:
                    primary_char_name = characters_data[0].get("canonical_name") or characters_data[0].get("name")

            beats = []
            for idx, sc in enumerate(scenes_data):
                ocr = sc.get("ocr_text", "").strip()
                vis = sc.get("visual_description", "").strip()
                speaker = sc.get("speaker") or (primary_char_name if idx % 2 == 1 else "The Narrator")
                is_dialogue = bool(ocr and len(ocr) > 3)
                p_seq = sc.get("page_sequence", 1)
                p_key = str(sc.get("page_id") or p_seq)
                macro_note = page_macro_analyses.get(p_key, f"Page {p_seq} narrative beat")

                if is_dialogue:
                    intent = "DIALOGUE"
                    if primary_char_name:
                        text = f'"{ocr}" {primary_char_name} declares.'
                    else:
                        text = ocr
                    emotion = sc.get("emotion", "Determined" if "!" in ocr else "Neutral")
                else:
                    intent = "EXPOSITION"
                    emotion = "Mysterious" if idx % 2 == 0 else "Suspenseful"
                    clean_vis = re.sub(r"^(?:Scene|Panel|Shot)\s*#?\d+\s*[-:—–.]\s*", "", vis, flags=re.IGNORECASE).strip()
                    char_lead = f"{primary_char_name} " if primary_char_name else "The figure "
                    if clean_vis and not re.match(r"^(?:Scene|Panel|Visual\s+framing|No\s+visual)", clean_vis, flags=re.IGNORECASE):
                        text = f"{char_lead}stands poised as {clean_vis.lower()}."
                    else:
                        text = f"{char_lead}surveys the tense atmosphere, every movement laden with quiet anticipation."

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
                    page_context_summary=macro_note,
                    page_sequence=p_seq,
                    inferred_emotional_context=emotion,
                    inferred_subtext=f"Continuity beat {idx + 1}",
                    continuity_references=[f"Scene {idx} -> Scene {idx + 1}"],
                    proposed_narration_text=text,
                    recommended_emotion=emotion,
                    recommended_speed=1.0,
                )
                beats.append(beat)

        return NarrationDraftPlan(project_id=project_id, beats=beats)


story_narration_service = StoryNarrationService()
