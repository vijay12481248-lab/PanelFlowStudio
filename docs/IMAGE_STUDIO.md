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

Every AI result is already a project asset, so Deliver needs no "save" step for those; a colour grade is saved when you ask (phase 2).

## Phase 2: Color (built)
The **Color** page is the manual grade. The maths is ChronoFlow's own `engine/chronoflow/static/nle/grade.js`, imported unchanged
(`image-studio/color/grade.ts` types it), so a still is graded exactly as it would be in the video: a serial stack of nodes, each
with Lift/Gamma/Gain/Offset wheels, contrast + pivot, saturation, hue, temp, tint, colour boost, shadows, highlights, luma/RGB curves,
hue/sat curves, a `.cube` LUT and an ASC CDL, all baked into **one 33^3 LUT**.

| Piece | What it does |
|---|---|
| **Nodes** | Add, delete, reset, switch each one off (the dot), undo/redo (Ctrl+Z / Ctrl+Shift+Z on this page; a slider drag is one undo step), and an eye to see the picture without the grade. |
| **Tabs** | Primaries (wheels, sliders, **Auto balance**), Curves (luma/R/G/B), Hue / Sat curves, LUT & Looks (import `.cube`, strength, seven looks that each add a node), Scopes (waveform, RGB parade, vectorscope, histogram of the graded picture). |
| **Live view** | `GradeCanvas` draws the picture through the LUT with WebGL2 (`gradeRender.ts`, the same shader as ChronoFlow's monitor, CPU fallback if there is no WebGL2) over the plain `<img>`. "Hold to Compare" and the eye show the picture as it is. |
| **Deliver** | "Bake the colour grade into the export" renders the full-size picture through the LUT (PNG/JPG/WebP). **Save graded picture as a new asset** sends the baked PNG to `POST /api/projects/{id}/assets/graded`; it becomes a `GRADED_IMAGE` asset (version "Grade") whose provenance holds the source asset and the whole node stack, and the stack is then cleared because it is in the pixels. |

Rules that fall out of the design: the grade is a non-destructive stack on the **view**; AI edits always run on the clean pixels of the
open version and the stack follows onto the new result; opening another picture starts with no grade. Imported LUTs live in this
browser (`imagestudio:luts:v1`, 16-bit tables, the same format as ChronoFlow's library). Not built from ChronoFlow's page: stills
gallery and "shot match", copy/paste of a whole grade, the before/after wipe.

Gotcha found while testing: WebGL rejects `UNPACK_FLIP_Y_WEBGL` for an `ImageBitmap` (INVALID_OPERATION), so every redraw after the
first silently failed; the picture is flipped in the shader instead.

## Next phases (the rail shows them, disabled)
3. **Cut** - crop (9:16, 16:9, 1:1), straighten, rotate, flip, resize (a baked-pixels step, like the grade).
4. **Fusion** - an effect stack (glow, vignette, grain, text).

## Checked
Type check, `npm run test:ui` (703), the Python tests for the new endpoint, a production `vite build`, and in a real browser against the
running Vite server with stubbed engine calls.
- Phase 1: all three AI modes, a real mouse stroke painting a mask, the pose flow (the request carries the artwork id, the uploaded
  picture as a data URL and the note), Versions growing and switching, the Deliver page and its provenance, story mode.
- Phase 2: the WebGL picture matches ChronoFlow's CPU maths at full resolution (mean difference 0.44 out of 255, max 1; with a LUT 0.47),
  orientation right, `getError()` 0 and redraws on every change; five slider moves undo as one step; all four scopes draw; a real `.cube`
  (swap red and blue) imports, applies (pixel (34, 56, 80) becomes (80, 56, 34)) and survives a reload; Auto balance and a look add nodes;
  a real mouse drag bends a curve; the baked PNG export matches the CPU grade (0.47); the save request carries the PNG, the source asset,
  the grade and the LUT id and the stack clears afterwards.

**Not checked:** a real engine round trip from this UI (the new endpoint is covered by unit tests), the JPG/WebP exports, very large
pictures on the CPU fallback, the Tauri window, other window sizes.
