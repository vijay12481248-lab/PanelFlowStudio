"""
Panel Reading Order Engine.
Implements:
- LTR (Western): Row banding top-to-bottom, left-to-right within rows.
- RTL (Manga): Row banding top-to-bottom, right-to-left within rows.
- VERTICAL (Webtoon): Continuous vertical sequence top-to-bottom.
- CUSTOM: User-specified manual sequence preservation.
- Assigns sequence_page and sequence_global.
"""

from typing import Sequence, TypeVar
import numpy as np
from engine.imaging.panels.base import PanelBox, ReadingDirection, PanelType

T = TypeVar("T")


def sort_panel_boxes(
    boxes: list[PanelBox],
    reading_direction: str = "ltr",
    page_height: int = 1800,
    row_threshold_ratio: float = 0.08,
) -> list[PanelBox]:
    """Sorts PanelBox objects by reading direction, handling row banding and inset panels."""
    if len(boxes) <= 1:
        return list(boxes)

    direction = reading_direction.lower()

    # If CUSTOM, preserve existing sequence
    if direction in (ReadingDirection.CUSTOM.value, "custom"):
        return sorted(boxes, key=lambda b: (b.page_sequence, b.sequence))

    # If VERTICAL (webtoon), strictly top to bottom
    if direction in (ReadingDirection.VERTICAL.value, "vertical"):
        sorted_boxes = sorted(boxes, key=lambda b: (b.y, b.x))
        for idx, b in enumerate(sorted_boxes, start=1):
            b.page_sequence = idx
            b.sequence = idx
        return sorted_boxes

    # Separate inset panels from primary layout panels
    primary_boxes: list[PanelBox] = []
    inset_boxes: list[PanelBox] = []

    for b in boxes:
        if b.panel_type == PanelType.INSET.value:
            inset_boxes.append(b)
        else:
            primary_boxes.append(b)

    if not primary_boxes:
        primary_boxes = list(boxes)
        inset_boxes = []

    # Sort primary panels into row bands
    row_tol = page_height * row_threshold_ratio
    sorted_by_y = sorted(primary_boxes, key=lambda b: b.y)

    rows: list[list[PanelBox]] = []
    curr_row: list[PanelBox] = [sorted_by_y[0]]

    for b in sorted_by_y[1:]:
        curr_y = b.y
        row_avg_y = sum(item.y for item in curr_row) / len(curr_row)

        if abs(curr_y - row_avg_y) <= row_tol:
            curr_row.append(b)
        else:
            rows.append(curr_row)
            curr_row = [b]

    if curr_row:
        rows.append(curr_row)

    # Sort within rows based on direction
    ordered_primary: list[PanelBox] = []
    is_rtl = direction in (ReadingDirection.RTL.value, "rtl")

    for row in rows:
        sorted_row = sorted(row, key=lambda b: b.x, reverse=is_rtl)
        ordered_primary.extend(sorted_row)

    # Insert inset panels immediately following their enclosing parent panel
    final_ordered: list[PanelBox] = []
    remaining_insets = list(inset_boxes)

    for p in ordered_primary:
        final_ordered.append(p)
        # Find any insets inside this panel
        px1, py1, px2, py2 = p.x, p.y, p.x + p.width, p.y + p.height
        matched_insets = []
        for inset in remaining_insets:
            ix1, iy1, ix2, iy2 = inset.x, inset.y, inset.x + inset.width, inset.y + inset.height
            # If inset center is inside parent
            cx = inset.x + inset.width / 2.0
            cy = inset.y + inset.height / 2.0
            if px1 <= cx <= px2 and py1 <= cy <= py2:
                matched_insets.append(inset)

        for mi in matched_insets:
            remaining_insets.remove(mi)
            final_ordered.append(mi)

    # Append any unparented insets at the end
    final_ordered.extend(remaining_insets)

    # Assign page sequence numbers
    for idx, b in enumerate(final_ordered, start=1):
        b.page_sequence = idx
        b.sequence = idx

    return final_ordered


def resequence_project_panels(panels_by_page: dict[str, list[PanelBox]]) -> list[PanelBox]:
    """
    Assigns sequential page_sequence (1..N on page) and sequence (1..M globally)
    across all pages in project reading order.
    """
    global_seq = 1
    all_panels: list[PanelBox] = []

    for page_id, page_panels in panels_by_page.items():
        for page_seq, p in enumerate(page_panels, start=1):
            p.page_sequence = page_seq
            p.sequence = global_seq
            all_panels.append(p)
            global_seq += 1

    return all_panels
