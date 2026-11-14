# Image Studio (the image editor)

`apps/desktop/src/components/ImageEditorModal.tsx` is the entry (the same props and `ImageEditorTarget` as before); the layout
pieces live in `components/image-studio/`. It is an AI-first editor laid out like ChronoFlow's workspace: a **page rail along the
bottom** (AI, Cut, Fusion, Color, Deliver), a **tool rail** on the left, the **canvas with a Versions strip**, and an **inspector**
on the right that belongs to the open page.

```
+--------------------------------------------------------------------------+
| Image Studio  1344 x 768  EDITED  frozen_duel.png      [Compare][save][x] |
+----+-----------------------------------------------+---------------------+
| T  |                                               | [Edit|Pose|Inpaint] |
| O  |                  canvas                       |   inspector of the  |
| O  |                                               |   open page         |
| L  +-----------------------------------------------+                     |
| S  | Versions: [Original][v1 Pose][v2 Edit]        | Seed  progress      |
+----+-----------------------------------------------+---------------------+
|                  AI    Cut    Fusion    Color    Deliver                  |
+--------------------------------------------------------------------------+
```

## Phase 1 (built)
| Piece | What it does |
|---|---|
| **AI page** | One segmented switch: **Edit** (instruction, no mask; `minimax_h3_image_edit`), **Pose & camera** (a picture from disk gives the poses, camera angle and framing; optional "who plays whom"; see `docs/H3_IMAGE_EDIT.md`), **Inpaint** (mask + prompt; `qwen_image_21_inpaint`). One seed and one progress area for all three. Story panels can only be inpainted. |
| **Tool rail** | Brush, eraser, undo, redo, clear, show/hide mask (only while Inpaint is open, B / E open it), zoom and fit. The mask canvas only takes strokes in Inpaint. |
| **Versions strip** | The original and every result of this session; click one to open it (and edit from it). "Hold to Compare" shows the version before the open one. |
| **Deliver page** | Export PNG, JPG or WebP (a PNG that is already PNG is saved byte for byte; JPG/WebP at 92%), and the generation record (workflow, mode, prompt, caption, seed, pose picture) with a SHA-256 copy. |

Every AI result is already a project asset, so Deliver needs no "save" step yet.

## Next phases (the rail already shows them, disabled)
2. **Color** - the manual grade, reusing `engine/chronoflow/static/nle/grade.js` (pure maths, bakes a node stack into one 33^3 LUT) so a still looks as it would in the video: wheels, curves, LUTs, scopes.
3. **Cut** - crop (9:16, 16:9, 1:1), straighten, rotate, flip, resize.
4. **Fusion** - an effect stack (glow, vignette, grain, text).

Design decisions for those: manual edits stay a non-destructive stack on the view; AI always runs on the clean pixels of the open
version and the stack follows onto the new result; Deliver bakes the stack. Saving a baked picture as a new asset needs one small
endpoint (the pose upload, `save_pose_reference`, is the pattern); it is not built because phase 1 has no manual edits.

## Checked
Type check, `npm run test:ui` (695), and in a real browser against the running Vite server with stubbed engine calls: all three AI
modes, a real mouse stroke painting a mask, the pose flow (the request carries the artwork id, the uploaded picture as a data URL and
the note), Versions growing and switching (header and EDITED badge follow), the Deliver page and its provenance, story mode (Edit and
Pose locked). **Not checked:** a real engine round trip from this UI (the engine paths were verified separately in
`docs/H3_IMAGE_EDIT.md`), the PNG/JPG/WebP export download, other window sizes, the Tauri window.
