# Panel Model Specification & Future Stage Contracts

## 1. Overview
The canonical **Panel Model** in PanelFlow Studio establishes the persistent, immutable source of truth for extracted comic, manga, and webtoon panels. It connects page normalization with downstream automated analysis (OCR, speech bubble segmentation, character detection) and timeline rendering (motion graphics, 2.5D camera choreographies).

---

## 2. Canonical Panel Record Schema

Every panel extracted or drawn is persisted in SQLite (`panels` table) with UUID identifiers and serialized to `panels.json` in the project workspace.

### Database Entity (`PanelRecord`)
```sql
CREATE TABLE panels (
    id VARCHAR(36) PRIMARY KEY,
    project_id VARCHAR(36) NOT NULL,
    page_id VARCHAR(36) NOT NULL,
    sequence INTEGER NOT NULL,          -- sequence_global across entire book
    page_sequence INTEGER NOT NULL,     -- sequence within containing page
    x INTEGER NOT NULL,                 -- Original page coordinates (pixels)
    y INTEGER NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    normalized_x FLOAT NOT NULL,        -- Unit coordinate space [0.0, 1.0]
    normalized_y FLOAT NOT NULL,
    normalized_width FLOAT NOT NULL,
    normalized_height FLOAT NOT NULL,
    confidence FLOAT NOT NULL,          -- Detection confidence [0.0, 1.0]
    panel_type VARCHAR(32) NOT NULL,    -- STANDARD, SPLASH, INSET, BORDERLESS, etc.
    status VARCHAR(32) NOT NULL,        -- DETECTED, CONFIRMED, NEEDS_REVIEW, IGNORED
    detection_method VARCHAR(32),       -- AUTO, MANUAL, FALLBACK
    manually_modified BOOLEAN DEFAULT 0,
    crop_filename VARCHAR(255) NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);
```

### Dual Coordinate Spaces
1. **Source Coordinate Space (Absolute Pixels)**:
   - Integers `(x, y, width, height)` mapped directly to the unscaled source page.
   - Crop extraction utilizes source coordinates to preserve maximal line-art fidelity without interpolation artifacts.
2. **Normalized Coordinate Space (`0.0` to `1.0`)**:
   - Floating point values rounded to 4 decimal places.
   - `normalized_x = x / page_width`
   - `normalized_y = y / page_height`
   - `normalized_width = width / page_width`
   - `normalized_height = height / page_height`
   - Essential for resolution-independent viewport positioning, responsive UI canvas scaling, and motion camera keyframing.

---

## 3. Downstream Contract 1: Future OCR Engine

Downstream OCR engines (e.g. Manga-OCR, Tesseract, PaddleOCR, or Vision-LLM adapters) consume panels strictly via the canonical `PanelInput` contract.

### Contract Schema (`PanelInput`)
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "PanelInputContract",
  "type": "object",
  "required": [
    "panel_id",
    "project_id",
    "page_id",
    "sequence_global",
    "crop_path",
    "bounding_box",
    "reading_direction"
  ],
  "properties": {
    "panel_id": { "type": "string", "format": "uuid" },
    "project_id": { "type": "string", "format": "uuid" },
    "page_id": { "type": "string", "format": "uuid" },
    "sequence_global": { "type": "integer", "minimum": 1 },
    "sequence_page": { "type": "integer", "minimum": 1 },
    "reading_direction": { "type": "string", "enum": ["ltr", "rtl", "vertical"] },
    "crop_path": { "type": "string", "description": "Absolute filesystem path to lossless JPEG/PNG crop" },
    "aspect_ratio": { "type": "number", "minimum": 0.01 },
    "bounding_box": {
      "type": "object",
      "required": ["x", "y", "width", "height", "normalized"],
      "properties": {
        "x": { "type": "integer" },
        "y": { "type": "integer" },
        "width": { "type": "integer" },
        "height": { "type": "integer" },
        "normalized": {
          "type": "object",
          "properties": {
            "x": { "type": "number", "minimum": 0.0, "maximum": 1.0 },
            "y": { "type": "number", "minimum": 0.0, "maximum": 1.0 },
            "width": { "type": "number", "minimum": 0.0, "maximum": 1.0 },
            "height": { "type": "number", "minimum": 0.0, "maximum": 1.0 }
          }
        }
      }
    }
  }
}
```

### Quality & Resolution Guarantees
- **Crop Quality**: Crops are generated with lossless quality (JPEG 95 or PNG) from unscaled source pages.
- **Reading Order**: Panels are delivered in strict reading sequence (`sequence_global`). OCR output text streams inherit this order to ensure correct narrative continuity.
- **Separation**: Downstream OCR models process individual cropped panels independently, eliminating cross-panel speech bubble contamination.

---

## 4. Downstream Contract 2: Future Motion Planning Engine

Future motion planning and video generation modules (e.g. Godot 4 camera tracks, 2.5D parallax separation, or Remotion sequences) consume the panel sequence to generate dynamic camera keyframes.

### Motion Planning Contract Schema
```json
{
  "project_id": "904661aa-147e-4fef-90f5-b20c6285dee8",
  "timeline_sequence": [
    {
      "step_index": 1,
      "panel_id": "fb63b0fb-6aef-4810-842e-c163118614f1",
      "page_id": "61977a87-6916-456e-929c-751c58652a4d",
      "camera_frame": {
        "center_normalized": { "x": 0.255, "y": 0.231 },
        "zoom": 1.45,
        "viewport_aspect": "16:9",
        "bounds_normalized": { "x": 0.041, "y": 0.094, "width": 0.436, "height": 0.324 }
      },
      "pacing_hint": {
        "panel_type": "STANDARD",
        "has_dialogue": true,
        "suggested_hold_sec": 3.5
      }
    }
  ]
}
```

### Guarantees for Motion Planning
- **Continuous Normalized Trajectory**: Camera interpolators can glide smoothly across page coordinate space using `normalized` bounding box coordinates without needing to know physical DPI or display resolution.
- **Aspect Ratio Safe Margins**: Standard, Splash, and Webtoon segments specify explicit aspect ratios allowing automatic pillarboxing or cinematic zooms without cutting off dialogue.
- **Stable IDs**: All motion keyframes and timeline blocks link permanently to `panel_id`. If a user re-runs detection or reorders panels, timeline associations remain robust.
