# PanelFlow Studio — Story Analysis Pipeline

## 1. Pipeline Overview

The Story Analysis Pipeline transforms human-approved panels, reading order, and OCR transcripts (`OCR_APPROVED`) into a structured **Narrative IR** (`STORY_ANALYZED` / `STORY_APPROVED`).

```
[OCR_APPROVED Source Data]
         │
         ▼
[Level 1: Visual Perception & Geometry]
- Extract panel crops & balloon coordinates
- Identify visual bounding boxes of characters
         │
         ▼
[Level 2: Character Discovery & Resolution]
- Track recurring identities, faces, and outfits
- Map dialogue name mentions to characters
         │
         ▼
[Level 3: Dialogue & Speaker Attribution]
- Rule 1: Narration / Caption boxes -> NARRATOR
- Rule 2: Sound Effects -> SFX
- Rule 3: Solitary Character -> 100% confidence
- Rule 4: Balloon Tail Vector tracing -> Targeted Character bbox
- Rule 5: Spatial Left-to-Right positioning
- Rule 6: Sequential dialogue alternation
- Fallback: Vision LLM / Multi-character prompt
         │
         ▼
[Level 4: Narrative Event Extraction]
- Categorize physical actions (ENTER, MOVE, ATTACK, DISCOVER, REACTION)
- Associate actor, target, location, and supporting panel evidence
         │
         ▼
[Level 5: Scene Segmentation & Dramatic Beats]
- Identify scene cuts (LOCATION_CHANGE, TIME_CHANGE, NARRATIVE_SHIFT)
- Segment scenes into dramatic beats with dramatic functions
- Tag advisory intensity, music intent, and SFX cues
         │
         ▼
[Level 6: Automated Continuity Audit]
- Detect missing actors, invalid speaker IDs, duplicate names
- Flag critical errors that block approval
         │
         ▼
[Level 7: Persistence & Downstream Invalidation]
- Write narrative.json and database records
- Advance project stage to STORY_ANALYZED
- Invalidate downstream SCRIPT tier in Dependency Graph
```

---

## 2. Deterministic Balloon Geometry Heuristics

To ensure high performance and eliminate unnecessary LLM inference costs, PanelFlow Studio runs deterministic balloon geometry heuristics prior to calling an LLM:

1. **Narration / Caption Box Rule**: Any text region labeled `NARRATION` or `CAPTION` is attributed to `NARRATOR` (confidence = 0.99).
2. **Onomatopoeia Rule**: Any text region labeled `SFX` is attributed to `SFX` (confidence = 0.98).
3. **Solitary Character Rule**: If exactly one character is present in the panel, all non-caption speech balloons are attributed to that character (confidence = 0.95).
4. **Balloon Tail Vector Rule**: The OpenCV contour analyzer detects the pointed vertex of the speech balloon. The vector pointing from the balloon centroid through the tail apex is cast downward. If the vector targets a specific character bounding box, attribution confidence is set to 0.92.
5. **Spatial Left/Right Positioning**: When two characters are present and no prior speaker exists, balloons on the left half of the panel ($x < 0.5$) are attributed to the leftmost character; balloons on the right half ($x \ge 0.5$) are attributed to the rightmost character.
6. **Conversational Alternation**: In back-and-forth dialogue across consecutive panels or regions, speakers alternate between the two active characters (confidence = 0.82).

Only when spatial and contextual rules leave ambiguous candidates does the engine invoke the LLM with the versioned prompt `speaker_resolution_v1.md`.

---

## 3. Strict Preconditions & Approval Gates

- **Input Precondition**: The project must strictly be in `OCR_APPROVED` stage. Attempting to analyze an unapproved project returns HTTP 400.
- **Approval Gate**: Advancing to `STORY_APPROVED` (`POST /api/projects/{id}/story/confirm`) is blocked if any unresolved `ERROR`-severity continuity warnings remain.
