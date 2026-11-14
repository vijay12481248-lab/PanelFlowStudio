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

## Phase 3: Cut (built)
The **Cut** page is geometry: crop, straighten, quarter turns, flips and resize. The maths is pure and tested
(`image-studio/cut/geometry.ts`); `render.ts` draws it on a 2D canvas and also runs the **one pipeline Deliver uses: the colour grade
first (full size), then the cut** (`renderEdited`).

| Piece | What it does |
|---|---|
| **Crop** | The picture is shown as oriented and straightened, with a frame and eight handles (rule-of-thirds lines, the outside dimmed). Drag inside to move, a handle to resize. Aspects: Free, Original, 1:1, 4:5, 3:4, 4:3, 16:9, 9:16; any aspect but Free stays locked while you drag (the opposite corner is the anchor). |
| **Straighten** | -45 to +45 degrees. The crop is shrunk to stay inside the rotated content with a 1 px margin, so no empty corner and no half-empty edge pixel ever reaches an export. |
| **Turn / flip** | Quarter turns left and right, flip horizontally and vertically; the crop turns and mirrors with the picture. |
| **Output size** | Long edge: Keep, 2048, 1536, 1080, 720, 512, or any value from 16 to 16384; the readout shows the result ("512 x 288 px from 1100 x 629"). |
| **Undo** | Ctrl+Z / Ctrl+Shift+Z on this page, plus buttons and Reset; a drag is one step (the grade's history code, now generic). |

Like the grade, the cut is a **view-level state, applied when you export or save**. The AI and Inpaint pages keep showing the whole
picture, so masks line up with what the model sees; the header shows a `CUT 512 x 288` chip while one is set. Deliver bakes the grade
and the cut together; "Save edited picture as a new asset" sends the rendered PNG plus the grade and/or the cut to
`POST /api/projects/{id}/assets/graded` (one of the two is required). The asset is `GRADED_IMAGE` when a grade is in it and `CUT_IMAGE`
for a cut alone, with the source asset and the exact settings as provenance (versions are labelled "Grade" and "Cut"); both stacks are
cleared afterwards because they are in the pixels. Opening another picture starts with no cut.

## Phase 4: Fusion (built)
The **Fusion** page is an effect stack applied last, to the finished picture (after the grade and the cut), so a vignette centres on the
final frame and text is placed in it. Glow, vignette, blur and text are ChronoFlow's own renderers (`fusion-graph.js`, `processNode`,
imported unchanged by `image-studio/fusion/fusionGraph.ts`), so they look as they do on the video Fusion page; **film grain is the
studio's own** (`effects.ts`, `grainPixels`) because ChronoFlow's ignores its size setting.

| Piece | What it does |
|---|---|
| **Effects** | Glow (size, intensity), Vignette (radius, softness, opacity, colour), Film grain (amount, size, a fixed pattern you can re-roll), Blur (radius), Text (text, size, colour, outline, glow, alignment, background box, line spacing). Add any number, in any order; each has a switch, move up/down and delete, and a "(no effect)" note when it would change nothing. |
| **Text placement** | While a text effect is selected, click or drag on the picture to place it. |
| **Live view** | `FusionStage` renders the whole pipeline (grade, cut, effects) at screen size. Header chip `FX n` while effects are set. Undo/redo (Ctrl+Z on this page, a drag is one step). |
| **Deliver** | Bakes grade, then cut, then effects (`renderEdited`) into PNG/JPG/WebP, or saves it as an asset. The endpoint now also takes `fusion`; the asset is named after the first thing in it (`GRADED_IMAGE`, then `CUT_IMAGE`, then `FUSION_IMAGE`) and keeps all three records as provenance. |

**Size independence.** Pixel sizes are written for a frame 720 pixels high (like ChronoFlow) and scaled by the picture's real height
(`refScale`, `scaledNode`), so a still looks the same at any resolution. Limits: ChronoFlow's blur and glow clamp at 80 and 60 px, so
on pictures taller than about 3,500 px the slider maxima give a relatively weaker effect. Grain is seeded, so the preview and the
export are the same picture. Not built from ChronoFlow's Fusion page: the node graph itself, masks, chroma key, camera shake, transform.

All four pages of the rail are now open; the page-rail test asserts none is locked.

## Checked
Type check, `npm run test:ui` (724), the Python tests for the endpoint (65 related), a production `vite build`, and in a real browser
against the running Vite server with stubbed engine calls.
- Phase 1: all three AI modes, a real mouse stroke painting a mask, the pose flow (the request carries the artwork id, the uploaded
  picture as a data URL and the note), Versions growing and switching, the Deliver page and its provenance, story mode.
- Phase 2: the WebGL picture matches ChronoFlow's CPU maths at full resolution (mean difference 0.44 out of 255, max 1; with a LUT 0.47),
  orientation right, `getError()` 0 and redraws on every change; five slider moves undo as one step; all four scopes draw; a real `.cube`
  imports, applies and survives a reload; Auto balance and a look add nodes; a real mouse drag bends a curve; the baked PNG export
  matches the CPU grade (0.47); the save request carries the PNG, the source asset, the grade and the LUT id.
- Phase 3: 9:16 gives exactly 0.5625; a real mouse drag moves the frame and a corner drag shrinks it keeping the ratio with the opposite
  corner fixed; the exported PNG of a turned picture is pixel-identical (mean 0, max 0) to an independent 90-degree rotation, and of a
  flipped-both-ways picture likewise; a straightened 8-degree auto-crop matches an independently computed bilinear rotation to 0.28 of
  255; at 8, -23 and 40 degrees the export has zero transparent or half-transparent pixels.
- Phase 4: a vignette darkens the corner to 0.30 to 0.33 of the original (opacity 0.7) and leaves the centre untouched; a real mouse
  click places the text where it was clicked; with vignette, text, glow and grain the live preview and the exported PNG are
  **pixel-identical** (mean 0, max 0) and a second export is identical to the first; text covers the same share of the frame at 1100
  and 2200 px (width 0.126 against 0.126, height 0.048 against 0.049); reorder, undo and redo behave; grade + cut + effects save in
  one request (PNG, grade, cut, the effect types) and all three stacks clear afterwards.

**Not checked:** a real engine round trip from this UI (the endpoint is covered by unit tests), the JPG/WebP exports, very large
pictures on the CPU fallback, pictures taller than about 3,500 px with strong blur or glow, the Tauri window, other window sizes,
touch input on the crop handles and the text placement.
