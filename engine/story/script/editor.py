"""Review operations on existing script segments; preserve source evidence."""
import re
import uuid

from engine.story.script.duration import estimate_segment_duration


def retime(segments):
    elapsed = 0.0
    for index, segment in enumerate(segments, 1):
        segment.sequence = index
        segment.estimated_start = round(elapsed, 3)
        elapsed += segment.estimated_duration
        segment.estimated_end = round(elapsed, 3)
    return segments


def edit_segments(segments, segment_id, action):
    items = [s.model_copy(deep=True) for s in sorted(segments, key=lambda s: s.sequence)]
    index = next((i for i, s in enumerate(items) if s.segment_id == segment_id), None)
    if index is None:
        raise KeyError("Script segment not found")
    segment = items[index]
    if action == "remove":
        if len(items) == 1:
            raise ValueError("Cannot remove the last script segment")
        items.pop(index)
    elif action in ("move_up", "move_down"):
        other = index + (-1 if action == "move_up" else 1)
        if not 0 <= other < len(items):
            raise ValueError("Already at the edge of the script")
        items[index], items[other] = items[other], items[index]
    elif action == "merge_next":
        if index + 1 >= len(items):
            raise ValueError("No following segment to merge")
        following = items.pop(index + 1)
        if following.scene_id != segment.scene_id:
            raise ValueError("Merge scenes in story review before merging their narration")
        segment.text = f"{segment.text.strip()} {following.text.strip()}".strip()
        segment.source_evidence.panel_ids = list(dict.fromkeys(segment.source_evidence.panel_ids + following.source_evidence.panel_ids))
        segment.source_evidence.text_region_ids = list(dict.fromkeys(segment.source_evidence.text_region_ids + following.source_evidence.text_region_ids))
        segment.estimated_duration = estimate_segment_duration(segment.text, segment_type=segment.type.value)
    elif action == "split":
        sentences = re.split(r"(?<=[.!?])\s+", segment.text.strip())
        if len(sentences) < 2:
            raise ValueError("Add a sentence boundary before splitting this segment")
        midpoint = max(1, len(sentences) // 2)
        second = segment.model_copy(deep=True)
        second.segment_id = f"seg_{uuid.uuid4().hex[:12]}"
        segment.text, second.text = " ".join(sentences[:midpoint]), " ".join(sentences[midpoint:])
        panels = segment.source_evidence.panel_ids
        if len(panels) >= 2:
            cut = max(1, len(panels) // 2)
            segment.source_evidence.panel_ids = panels[:cut]
            second.source_evidence.panel_ids = panels[cut:]
        for part in (segment, second):
            part.estimated_duration = estimate_segment_duration(part.text, segment_type=part.type.value)
        items.insert(index + 1, second)
    else:
        raise ValueError(f"Unknown script action: {action}")
    for item in items:
        item.manual_override = True
    return retime(items)
