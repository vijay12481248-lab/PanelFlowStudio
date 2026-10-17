# PanelFlow Studio — Story Grounding & Provenance Architecture

## 1. Overview
A core design requirement of PanelFlow Studio is **total provenance**. In traditional naive LLM workflows, an LLM generates a monologue or screenplay where it is impossible to determine which comic panel or line of text justified a given spoken sentence. This leads to untraceable hallucinations, incorrect speakers, and timeline drift.

In PanelFlow Studio, **every narrative claim in Layer B and every adapted spoken line in Layer C MUST reference supporting evidence from Layer A**.

---

## 2. Provenance Reference Model

The standard `ProvenanceReference` structure is embedded across all domain entities:

```json
{
  "panel_ids": ["panel_003"],
  "text_region_ids": ["tr_007", "tr_008"],
  "confidence": 0.94
}
```

### Traceability Hierarchy:
- **Utterances (Layer B)** $\longrightarrow$ `TextRegionRecord.id` (Layer A) + `PanelRecord.id` (Layer A)
- **Events (Layer B)** $\longrightarrow$ `PanelRecord.id` list (Layer A)
- **Story Beats (Layer B)** $\longrightarrow$ Event IDs + `PanelRecord.id` list (Layer A)
- **Scenes (Layer B)** $\longrightarrow$ `panel_start` and `panel_end` (Layer A)
- **Script Segments (Layer C)** $\longrightarrow$ `panel_ids` + `text_region_ids` (Layer A)

---

## 3. Bidirectional Navigation in the UI

The Desktop UI provides two-way interactive grounding:
1. **Script-to-Panel**: Clicking any line in `ScriptReviewScreen` highlights the referenced source comic panels and text bubbles in the visual panel strip.
2. **Panel-to-Script**: Selecting a panel in `StoryReviewScreen` filters and displays all events, beats, and script dialogue associated with that panel.

---

## 4. Cascading Invalidation via Dependency Graph

When source material (Layer A) is modified, downstream entities must be invalidated safely without destroying manual human overrides:

```
[PAGE] ──▶ [PANEL] ──▶ [TEXT REGION] ──▶ [OCR]
                                           │
                                           ▼
                                      [UTTERANCE]
                                           │
                                           ▼
                                      [CHARACTER]
                                           │
                                           ▼
                                        [EVENT]
                                           │
                                           ▼
                                        [BEAT]
                                           │
                                           ▼
                                       [SCENE]
                                           │
                                           ▼
                                    [NARRATIVE IR]
                                           │
                                           ▼
                                       [SCRIPT]
```

### Invalidation Invariants:
1. When a user modifies or approves a text region in Layer A, the corresponding utterance and speaker attribution in Layer B are marked stale.
2. Machine-generated entities downstream of the invalidation tier are marked for re-analysis.
3. Entities with `manual_override = true` are **never deleted or overwritten**; instead, they are preserved with a continuity warning if source references are deleted.
