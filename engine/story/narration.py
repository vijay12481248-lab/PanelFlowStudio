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
                    panels_root = panels_dir
                    vision_model = getattr(prov, "vision_model", "qwen3.5:9b")
                    for sc in scenes_data:
                        panel_file_to_analyze = None
                        # Try crop_filenames first, but never allow paths outside panels/.
                        for cf in sc.get("crop_filenames", []):
                            if not isinstance(cf, str) or not cf.strip():
                                continue
                            try:
                                cand = resolve_contained_path(panels_root, cf, must_be_file=True)
                            except (FileNotFoundError, ValueError, OSError):
                                logger.warning("Skipping panel path outside workspace: %s", cf)
                                continue
                            panel_file_to_analyze = cand
                            break
                        # Try sequence matching panel_0001.jpg
                        if not panel_file_to_analyze and panels_dir.exists():
                            seq = sc.get("sequence", 1)
                            for cand in [
                                panels_dir / f"panel_{seq:04d}.jpg",
                                panels_dir / f"panel_{seq:04d}.png",
                                panels_dir / f"panel_{seq}.jpg",
                            ]:
                                try:
                                    resolved_cand = resolve_contained_path(
                                        panels_root,
                                        cand.name,
                                        must_be_file=True,
                                    )
                                except (FileNotFoundError, ValueError, OSError):
                                    continue
                                panel_file_to_analyze = resolved_cand
                                break
                        # Try panel_ids matching
                        if not panel_file_to_analyze and panels_dir.exists():
                            for pid in sc.get("panel_ids", []):
                                if not isinstance(pid, str) or not pid or any(sep in pid for sep in ("/", "\\")):
                                    continue
                                candidates = list(panels_dir.glob(f"*{pid}*"))
                                for candidate in candidates:
                                    try:
                                        resolved_candidate = resolve_contained_path(
                                            panels_root,
                                            candidate.name,
                                            must_be_file=True,
                                        )
                                    except (FileNotFoundError, ValueError, OSError):
                                        continue
                                    if resolved_candidate.is_file():
                                        panel_file_to_analyze = resolved_candidate
                                        break
                                if panel_file_to_analyze:
                                    break

                        if panel_file_to_analyze:
                            try:
                                vis_summary = await prov.analyze_vision(
                                    image=panel_file_to_analyze,
                                    prompt="Describe in 1-2 concise, vivid sentences what characters, emotions, actions, and atmosphere are visible in this manga panel.",
                                    model=vision_model,
                                )
                                existing_visual = str(sc.get("visual_description", "")).strip()
                                is_placeholder = (
                                    not existing_visual
                                    or existing_visual.lower() in {"no visual description", "no visual", "visual unavailable"}
                                    or bool(re.match(r"^(?:panel|scene|shot)\s*#?\d*\s*(?:visual composition|visual framing)", existing_visual, re.IGNORECASE))
                                )
                                if vis_summary and is_placeholder:
                                    sc["visual_description"] = vis_summary.strip()
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

        # Deterministic fallback is test-only. Production narration must fail closed
        # instead of presenting generic text as source-grounded storytelling.
        if not llm_succeeded or len(beats) == 0:
            allow_mock = os.environ.get("PANELFLOW_ALLOW_MOCK_LLM", "").lower() in ("1", "true", "yes")
            if not allow_mock:
                raise RuntimeError("Narration generation produced no validated LLM beats. Configure a healthy real provider or explicitly enable PANELFLOW_ALLOW_MOCK_LLM for tests.")
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
                    clean_vis = re.sub(r"^(?:Scene|Panel|Shot)\s*#?\d+\s*[-:—–.]\s*", "", vis, flags=re.IGNORECASE).strip()
                    if clean_vis and not re.match(r"^(?:Scene|Panel|Visual\s+framing|No\s+visual)", clean_vis, flags=re.IGNORECASE):
                        text = clean_vis
                    else:
                        text = "The scene unfolds with palpable quietude, the atmosphere taut with quiet anticipation."

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
