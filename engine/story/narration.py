"""
Story-Aware Narration Generator for PanelFlow Studio.

Constructs structured intermediate story representations and drafts contextually
accurate motion-comic narration using local LLM (Ollama) or structured visual-text analysis.
Distinguishes directly observed facts (OCR text, visual framing) from model inferences.
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import json
import logging
from engine.llm.registry import llm_registry

logger = logging.getLogger("panelflow.story.narration")


class StructuredStoryBeat(BaseModel):
    """
    Intermediate story representation grounding narration in source manga panels.
    Distinguishes observed evidence from inferred context.
    """
    scene_id: str
    panel_ids: List[str]
    sequence: int
    narration_intent: str = "EXPOSITION"  # EXPOSITION, DIALOGUE, INTERNAL_MONOLOGUE, TENSION_BUILD, ACTION_BEAT
    speaker: str = "Narrator"
    speaker_type: str = "NARRATOR"  # NARRATOR or CHARACTER
    observed_ocr_dialogue: str = ""
    observed_visual_evidence: str = ""
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


def build_story_prompt(scenes_data: List[Dict[str, Any]]) -> str:
    """
    Constructs a disciplined prompt for Ollama to draft faithful motion-comic narration.
    """
    prompt = (
        "You are the Lead Narrative Director for a cinematic manga motion comic.\n"
        "Your task is to draft narration and dialogue for each scene based strictly on the provided "
        "manga panels, observed OCR text, and visual framing.\n\n"
        "CRITICAL RULES:\n"
        "1. Do NOT invent unrelated plot twists, characters, or motives unsupported by the panels.\n"
        "2. Ground every line in either the observed OCR dialogue or the visible action.\n"
        "3. Maintain natural continuity between consecutive scenes.\n"
        "4. Output MUST be valid JSON adhering to the specified schema.\n\n"
        "SCENES DATA:\n"
    )
    for sc in scenes_data:
        prompt += (
            f"- Scene {sc.get('sequence', 1)} (ID: {sc.get('id')}):\n"
            f"  Visuals: {sc.get('visual_description', 'No visual description')}\n"
            f"  Observed OCR: \"{sc.get('ocr_text', '')}\"\n"
            f"  Characters present: {', '.join(sc.get('characters', ['Narrator']))}\n"
        )

    prompt += (
        "\nReturn a JSON array of objects with keys:\n"
        "[\n"
        "  {\n"
        "    \"scene_id\": \"string\",\n"
        "    \"sequence\": number,\n"
        "    \"speaker\": \"string\",\n"
        "    \"narration_intent\": \"EXPOSITION\" | \"DIALOGUE\" | \"TENSION_BUILD\" | \"ACTION_BEAT\",\n"
        "    \"proposed_narration_text\": \"concise, evocative narration text\",\n"
        "    \"recommended_emotion\": \"Neutral\" | \"Mysterious\" | \"Suspenseful\" | \"Fearful\" | \"Determined\" | \"Sad\" | \"Happy\" | \"Whispering\",\n"
        "    \"recommended_speed\": 1.0\n"
        "  }\n"
        "]\n"
        "Output ONLY the JSON array. Do not add markdown commentary outside the JSON."
    )
    return prompt


from pathlib import Path

class StoryNarrationService:
    """
    Drafts and structures narration segments for PanelFlow Studio.
    """

    async def generate_narration_draft(
        self,
        project_id: str,
        scenes_data: List[Dict[str, Any]],
        provider_id: Optional[str] = None,
        model_name: Optional[str] = None,
        workspace_path: Optional[Path] = None,
    ) -> NarrationDraftPlan:
        beats: List[StructuredStoryBeat] = []

        # Try generating via local LLM if available
        llm_succeeded = False
        try:
            prov = llm_registry.get_ollama_provider()
            if not await prov.health_check():
                prov = await llm_registry.get_active_provider(provider_id)

            if prov and await prov.health_check():
                model_to_use = model_name or getattr(prov, "narration_model", "qwen3.5:9b")

                # If workspace_path is provided, inspect real images to enhance scene visual framing
                if workspace_path and getattr(prov, "supports_vision", True):
                    panels_dir = workspace_path / "panels"
                    for sc in scenes_data:
                        if not sc.get("visual_description") or sc.get("visual_description") == "No visual description":
                            panel_ids = sc.get("panel_ids", [])
                            for pid in panel_ids:
                                candidates = list(panels_dir.glob(f"{pid}*")) if panels_dir.exists() else []
                                if candidates and candidates[0].is_file():
                                    try:
                                        vis_summary = await prov.analyze_vision(
                                            image=candidates[0],
                                            prompt="In one short sentence, describe the character action and mood in this manga panel.",
                                            model=model_to_use,
                                        )
                                        if vis_summary:
                                            sc["visual_description"] = vis_summary.strip()
                                        break
                                    except Exception as img_err:
                                        logger.debug(f"Vision pre-analysis skipped: {img_err}")

                prompt = build_story_prompt(scenes_data)
                raw_text = await prov.generate_text(
                    prompt=prompt,
                    system_prompt="You are an expert cinematic manga narrator and storytelling director.",
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
                        beat = StructuredStoryBeat(
                            scene_id=item.get("scene_id", sc_match.get("id") if sc_match else f"sc_{item.get('sequence', 1)}"),
                            panel_ids=sc_match.get("panel_ids", []) if sc_match else [],
                            sequence=item.get("sequence", 1),
                            narration_intent=item.get("narration_intent", "EXPOSITION"),
                            speaker=item.get("speaker", "The Narrator"),
                            speaker_type="NARRATOR" if "narrator" in item.get("speaker", "").lower() else "CHARACTER",
                            observed_ocr_dialogue=sc_match.get("ocr_text", "") if sc_match else "",
                            observed_visual_evidence=sc_match.get("visual_description", "") if sc_match else "",
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
            logger.warning(f"Local LLM draft failed: {e}. Falling back to deterministic contextual analysis.")

        # Deterministic fallback: construct grounded beats from source OCR and visual metadata
        if not llm_succeeded or len(beats) == 0:
            beats = []
            for idx, sc in enumerate(scenes_data):
                ocr = sc.get("ocr_text", "").strip()
                vis = sc.get("visual_description", "").strip()
                speaker = sc.get("speaker", "The Narrator")
                is_dialogue = bool(ocr and len(ocr) > 3)

                if is_dialogue:
                    intent = "DIALOGUE"
                    text = ocr
                    emotion = sc.get("emotion", "Determined" if "!" in ocr else "Neutral")
                else:
                    intent = "EXPOSITION"
                    emotion = "Mysterious" if idx % 2 == 0 else "Suspenseful"
                    text = f"Scene {sc.get('sequence', idx + 1)}: {vis or 'The scene unfolds with palpable quietude.'}"

                beat = StructuredStoryBeat(
                    scene_id=sc.get("id", f"scene_{idx + 1}"),
                    panel_ids=sc.get("panel_ids", [f"panel_{idx + 1}"]),
                    sequence=sc.get("sequence", idx + 1),
                    narration_intent=intent,
                    speaker=speaker,
                    speaker_type="CHARACTER" if is_dialogue else "NARRATOR",
                    observed_ocr_dialogue=ocr,
                    observed_visual_evidence=vis,
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
