# Motion Director Upstream Integration & Database Contract

## 1. Upstream Data Sources

The Motion Director consumes data exclusively from established PanelFlow upstream modules:

1. **Normalized Panels & OCR Review (Milestone 2 & 3)**:
   - Panel bounding boxes (`NormalizedRect`).
   - Character bounding boxes and speech balloon coordinates.
   - Text region reading order.

2. **Narrative Understanding & Script Adaptation (Milestone 4)**:
   - `NarrativeIR`: Scene boundaries (`SceneEntity`), character entities (`CharacterEntity`), story beats (`StoryBeatEntity`).
   - `VideoScript`: Approved script segments (`ScriptSegment`), speaker character attributions, emotion cues, motion intents (`MotionIntent`).

3. **Audio Director & Master Audio Timeline (Milestone 5)**:
   - `MasterAudioTimeline`: Authoritative speech intervals (`AudioInterval`), speech start/end seconds, pause durations.

---

## 2. API Routes & Desktop Invocation Flow

When integrated into the FastAPI backend (`engine/api/`):
- `POST /api/projects/{project_id}/motion/plan`: Generates or returns cached `VisualTimeline`.
- `POST /api/projects/{project_id}/motion/override`: Applies human director tweaks (`ShotOverride`).
- `POST /api/projects/{project_id}/motion/regenerate`: Selectively replans invalid or updated scenes.
- `GET /api/projects/{project_id}/motion/preview/{shot_id}`: Returns JPEG keyframe preview.

---

## 3. Database Persistence Contract

`VisualTimeline` artifacts are persisted under:
`projects/{project_id}/motion/timeline_{hash}.json`

Database models (`Project`) track:
- `current_motion_timeline_id`: Pointer to active visual timeline.
- `motion_plan_hash`: SHA-256 for cache validation.
- `motion_status`: `DRAFT`, `PLANNED`, `APPROVED`.
