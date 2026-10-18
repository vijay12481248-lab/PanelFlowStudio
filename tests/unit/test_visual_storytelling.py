import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.story.visual import VisualStoryEngine
from engine.story.script.validator import script_validator
from engine.story.models import NarrativeDocument, PanelObservationEntity, VideoScript, ScriptSegment, SegmentType, ProvenanceReference


class VisionProvider:
    provider_id = "test_vision"

    def __init__(self):
        self.images = []
        self.prompts = []

    def model_metadata(self):
        return SimpleNamespace(model_name="fixture", supports_vision=True, model_dump=lambda: {"model": "fixture"})

    async def analyze_vision(self, image, prompt, **kwargs):
        self.images.append(image)
        self.prompts.append(prompt)
        return json.dumps({"visual_summary": "A guard watches the gate.", "actions": ["watching"],
                           "memory": {"current_location": "gate", "unresolved_questions": ["Who is arriving?"]}})

    async def generate_structured(self, prompt, response_model, **kwargs):
        self.chapter_prompt = prompt
        return response_model.model_validate({
            "chapter_summary": "A guard watches the gate.",
            "scenes": [{"scene_id": "s1", "sequence": 1, "title": "The gate", "panel_start": "p1", "panel_end": "p2", "summary": "A guard keeps watch."}],
            "beats": [{"beat_id": "b1", "scene_id": "s1", "sequence": 1, "panel_ids": ["p1", "p2"], "summary": "A guard keeps watch."}],
        })


def panels(tmp_path):
    (tmp_path / "panels").mkdir()
    for i in (1, 2):
        (tmp_path / "panels" / f"p{i}.png").write_bytes(f"image{i}".encode())
    return [SimpleNamespace(id=f"p{i}", sequence=i, crop_filename=f"p{i}.png") for i in (1, 2)]


def test_vision_receives_images_memory_and_resumes(tmp_path):
    provider = VisionProvider()
    items = panels(tmp_path)
    engine = VisualStoryEngine()
    doc = asyncio.run(engine.analyze("project", tmp_path, items, [], provider))
    assert provider.images == [tmp_path / "panels/p1.png", tmp_path / "panels/p2.png"]
    assert "Who is arriving?" in provider.prompts[1]
    assert "A guard watches the gate" in provider.chapter_prompt
    assert doc.analysis_metadata["chapter_summary"] == "A guard watches the gate."
    asyncio.run(engine.analyze("project", tmp_path, items, [], provider))
    assert len(provider.images) == 2
    (tmp_path / "panels/p1.png").write_bytes(b"edited")
    asyncio.run(engine.analyze("project", tmp_path, items, [], provider))
    assert len(provider.images) == 4  # changed context invalidates later panel


def test_no_mock_story_can_be_presented_as_visual_analysis(tmp_path):
    provider = VisionProvider()
    provider.provider_id = "mock_llm"
    with pytest.raises(ValueError, match="real vision"):
        asyncio.run(VisualStoryEngine().analyze("project", tmp_path, panels(tmp_path), [], provider))


def test_failed_panel_preserves_checkpoint_and_identifies_stage(tmp_path):
    provider = VisionProvider()
    items = panels(tmp_path)
    original = provider.analyze_vision

    async def failing(image, prompt, **kwargs):
        if image.name == "p2.png":
            raise RuntimeError("model timeout")
        return await original(image, prompt, **kwargs)

    provider.analyze_vision = failing
    with pytest.raises(ValueError, match="Vision analysis failed for panel p2"):
        asyncio.run(VisualStoryEngine().analyze("project", tmp_path, items, [], provider))
    assert list((tmp_path / "story/vision_cache").glob("*.json"))


def test_narration_can_be_grounded_in_visual_observations_without_ocr():
    narrative = NarrativeDocument(project_id="p", observations=[PanelObservationEntity(
        panel_id="panel", sequence_global=1, visual_summary="The guard opens the gate and watches the traveler.")])
    script = VideoScript(script_id="s", project_id="p", segments=[ScriptSegment(
        segment_id="seg", scene_id="sc", type=SegmentType.NARRATOR,
        text="The guard opens the gate and watches the traveler.",
        source_evidence=ProvenanceReference(panel_ids=["panel"]))])
    assert script_validator.validate(script, narrative).passed
    script.segments[0].source_evidence.panel_ids = ["invented_panel"]
    assert not script_validator.validate(script, narrative).passed
