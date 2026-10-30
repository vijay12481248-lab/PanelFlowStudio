import asyncio
import json
from pathlib import Path

from engine.story.models import NarrativeDocument
from engine.story.visual import ChapterNarration, NarratorBeat, VisualStoryEngine

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "acceptance" / "story" / "narrative.json"


class _RecapProvider:
    provider_id = "fake_llm"

    async def generate_structured(self, prompt, response_model, **_):
        assert "one narration line for each story panel" in prompt
        return ChapterNarration(segments=[
            NarratorBeat(scene_id="scene_dec3fd6d", panel_ids=["p1_9be088"],
                         narration="The explorer descends into the silent ancient courtyard ruins."),
            NarratorBeat(scene_id="scene_eadfbd9b", panel_ids=["p3_9be088"],
                         narration="Quantum bananas negotiate tariffs with bewildered volcano merchants tonight."),
        ])


def test_ungrounded_recap_line_is_dropped_instead_of_failing_the_chapter():
    narrative = NarrativeDocument.model_validate(json.loads(FIXTURE.read_text(encoding="utf-8")))
    script = asyncio.run(VisualStoryEngine().narrate(narrative, _RecapProvider()))
    assert [s.source_evidence.panel_ids for s in script.segments] == [["p1_9be088"]]
    assert all(s.faithfulness_status == "SUPPORTED" for s in script.segments)
    assert script.estimated_duration == script.segments[0].estimated_duration
