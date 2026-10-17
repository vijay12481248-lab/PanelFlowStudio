# Reading Order Engine Specification

## 1. Overview
Reading order determines the narrative sequence in which panels are presented to the reader, processed by downstream OCR dialogue extractors, and keyframed in motion comic engines. Reading direction is never hardcoded globally; it is configured at the project level and can be overridden on individual pages or adjusted manually panel-by-panel.

---

## 2. Supported Reading Directions

| Mode | Direction Name | Typical Comic Medium | Traversal Logic |
| :--- | :--- | :--- | :--- |
| `ltr` | Left-to-Right | Western Comics, Graphic Novels | Top to bottom, left to right within each row cluster |
| `rtl` | Right-to-Left | Japanese Manga, Manhua (traditional) | Top to bottom, right to left within each row cluster |
| `vertical`| Vertical Scroll | Korean Webtoons, Mobile Comics | Strictly top to bottom (`y` ascending) |
| `auto` | Automatic Inference | Multi-origin archives | Inferred from aspect ratio and language metadata |
| `custom` | Manual Custom | Experimental / complex layouts | Strictly respects manual timeline sequence |

---

## 3. Algorithmic Row Clustering & Sorting

Because comic panels rarely align along pixel-perfect horizontal lines, a simple coordinate sort on `(y, x)` fails on staggered or dynamic layouts. PanelFlow Studio employs an **Adaptive Row Clustering Algorithm**:

```
      Row 1 (Y ≈ 150):   ┌──────────────┐     ┌──────────────┐
                         │   Panel 1    │     │   Panel 2    │
                         └──────────────┘     └──────────────┘
                                                 (Δy <= row_tol)
      Row 2 (Y ≈ 800):   ┌───────────────────────────────────┐
                         │              Panel 3              │
                         └───────────────────────────────────┘
```

1. **Vertical Tolerance Window**:
   - `row_tol = page_height * 0.08` (configurable via `row_threshold_ratio`).
2. **Cluster Grouping**:
   - Panels are pre-sorted by `y`.
   - Sequential panels whose vertical deviation from the current cluster's running mean is within `row_tol` are grouped into the same row.
3. **In-Row Ordering**:
   - For `ltr`: Sorted by `x` ascending (`left -> right`).
   - For `rtl`: Sorted by `x` descending (`right -> left`).
   - For `vertical`: Row clustering is bypassed; all panels are sorted strictly by `y` ascending, then `x` ascending.

---

## 4. Sequence Hierarchies

Each panel maintains two distinct sequence indices:
- `sequence_page`: 1-indexed order of the panel relative to other panels on the same page.
- `sequence_global`: 1-indexed contiguous order across all pages in the entire book/chapter.

When a panel is added, deleted, split, or merged, `_resequence_project_panels` immediately recalculates both `sequence_page` and `sequence_global` monotonically without gaps.

---

## 5. Manual Override Workflow

Downstream stages (OCR and motion cameras) always prioritize manual ordering over automated estimates:
1. **Interactive Timeline Bar**:
   - The desktop Panel Review UI displays a horizontal sequence timeline (`P-1 -> P-2 -> P-3`).
   - Users can drag and drop badges or select a panel and adjust its sequence number in the inspector.
2. **REST API**:
   - `POST /api/projects/{project_id}/panel-order`
   - `POST /api/projects/{project_id}/panels/reorder`
   - Body: `{"panel_ids": ["uuid-3", "uuid-1", "uuid-2"]}`
   - When received, the engine updates `sequence_page` and `sequence_global`, marks `manually_modified = True`, and syncs `panels.json`.
