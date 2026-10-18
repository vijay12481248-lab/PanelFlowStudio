import pytest

from engine.story.script.editor import edit_segments
from engine.story.models import ScriptSegment, ProvenanceReference


def segments():
    return [ScriptSegment(segment_id=f"s{i}", scene_id="scene", sequence=i,
                          text=f"Sentence {i}. Another sentence.",
                          source_evidence=ProvenanceReference(panel_ids=[f"p{i}"])) for i in (1, 2)]


def test_split_merge_reorder_preserves_provenance_and_retimes():
    items = edit_segments(segments(), "s1", "split")
    assert len(items) == 3
    assert items[0].source_evidence.panel_ids == ["p1"]
    merged = edit_segments(items, "s1", "merge_next")
    assert len(merged) == 2
    moved = edit_segments(merged, "s1", "move_down")
    assert moved[0].segment_id == "s2"
    assert moved[1].estimated_start == moved[0].estimated_end
    assert all(s.manual_override for s in moved)


def test_cannot_remove_last_segment():
    with pytest.raises(ValueError, match="last"):
        edit_segments(segments()[:1], "s1", "remove")
