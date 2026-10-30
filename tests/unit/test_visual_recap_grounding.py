import asyncio
import json
from pathlib import Path

from engine.story.models import NarrativeDocument
from engine.story.visual import ChapterNarration, NarratorBeat, VisualStoryEngine

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "acceptance" / "story" / "narrative.json"


def _narrative():
    return NarrativeDocument.model_validate(json.loads(FIXTURE.read_text(encoding="utf-8")))


class _RecapProvider:
    """First call: the recap. Later calls: the coverage pass for skipped panels."""
    provider_id = "fake_llm"

    def __init__(self, recap, coverage=()):
        self.recap, self.coverage, self.prompts = recap, list(coverage), []

    async def generate_structured(self, prompt, response_model, **_):
        self.prompts.append(prompt)
        beats = self.recap if len(self.prompts) == 1 else self.coverage
        return ChapterNarration(segments=[NarratorBeat(scene_id="", panel_ids=[p], narration=t) for p, t in beats])


def test_ungrounded_recap_line_is_dropped_instead_of_failing_the_chapter():
    provider = _RecapProvider([
        ("p1_9be088", "The explorer descends into the silent ancient courtyard ruins."),
        ("p3_9be088", "Quantum bananas negotiate tariffs with bewildered volcano merchants tonight."),
    ])
    script = asyncio.run(VisualStoryEngine().narrate(_narrative(), provider))
    assert "one narration line for each story panel" in provider.prompts[0]
    assert [s.source_evidence.panel_ids for s in script.segments] == [["p1_9be088"]]
    assert all(s.faithfulness_status == "SUPPORTED" for s in script.segments)
    assert script.estimated_duration == script.segments[0].estimated_duration


def test_skipped_panels_get_lines_from_a_coverage_pass_in_reading_order():
    provider = _RecapProvider(
        recap=[("p3_9be088", "A cloaked silhouette watches from the dark gallery above.")],
        coverage=[("p2_9be088", "Lyra warns that the resonance frequency is rising rapidly."),
                  ("p1_9be088", "The explorer enters the silent ancient outer courtyard."),
                  ("p3_9be088", "Duplicate for an already narrated panel is ignored.")],
    )
    script = asyncio.run(VisualStoryEngine().narrate(_narrative(), provider))
    assert len(provider.prompts) == 2
    assert "p1_9be088" in provider.prompts[1] and "p3_9be088 |" not in provider.prompts[1]
    assert [s.source_evidence.panel_ids[0] for s in script.segments] == ["p1_9be088", "p2_9be088", "p3_9be088"]
