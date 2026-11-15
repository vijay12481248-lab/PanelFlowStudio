# ChronoFlow Color page

The **Color** button on the page rail (Media, Cut, Edit, Fusion, **Color**, Fairlight, Deliver) opens a Resolve-style grading workspace on the
same timeline as Edit. Grades live on the clips (`clip.grade`), are saved with the timeline (browser storage, per job), are undoable with
Ctrl+Z, and are rendered by "Bake Master Cut" (Deliver).

## Layout
- **Left, Stills**: "Grab still" keeps the current frame with its grade (Ctrl+Alt+G). Click a still to make it the reference; "Apply grade" copies its grade
  to the clip at the playhead; "Compare with still" shows it on the right of the viewer's split.
- **Centre, monitor**: the normal program monitor, graded live. Split slider (or drag the blue line): left = graded, right = original or the still.
  "Original" shows the ungraded picture on the whole monitor.
- **Right, Scopes**: waveform, RGB parade, vectorscope (with skin-tone line), histogram, of the graded frame.
- **Bottom**: nodes (left) and tools. The clip being graded is the clip under the playhead; ‹ › step between clips.

## Tools
| Tab | What it does |
|---|---|
| Primaries | Lift / Gamma / Gain / Offset wheels with master sliders, contrast + pivot, saturation, hue, temp, tint, colour boost, shadows, highlights. Double-click any label or wheel to reset it. |
| Curves | Luma, red, green, blue curves (monotone spline, click to add, drag, double-click or right-click a point to remove it). |
| Hue / Sat curves | Hue vs Hue, Hue vs Sat, Hue vs Lum, Lum vs Sat. The first click lays down flat anchors. Greys are left alone. |
| LUTs & Looks | Import a `.cube` (3D or 1D, any size; resampled to 33) with a strength slider; seven looks that each add a node. |
| Auto & Match | **Auto balance** (gray-world on the mid tones + black/white points, written as an ASC CDL node "Auto Balance", first). **Shot match** (match mean and spread per channel to the chosen still, CDL node "Shot Match", last). |

Nodes are serial (node 1 then 2 ...). Each can be bypassed (the dot), reset, deleted. Copy / Paste / Apply to all / Reset clip act on a whole clip grade.

## How it stays accurate (one maths, three users)
`static/nle/grade.js` (pure, unit-tested in `tests/js/chronoflow_grade.test.js`) bakes a clip's node stack into **one 33³ 3D LUT**.
- the monitor draws each video through that LUT with WebGL2 (`color.js`, a canvas laid over each deck's `<video>`; ungraded clips cost nothing);
- the scopes apply it on the CPU to a 192×108 copy of the frame;
- the export sends it as `.cube` text (`luts` + a `lut` id per clip, identical grades share one) and `pipeline.render_timeline_edl` runs FFmpeg
  `lut3d` (tetrahedral) per clip, inside an explicit BT.709 RGB round trip because ChronoFlow clips carry no colour tags.

Measured on real clips (768×1344 and 1080p, `vox_cat_physics_master.mp4` and a ChronoFlow job): FFmpeg's `lut3d` is within 0.6/255 of the JS table;
the whole export (4:2:0 + x264) is within 1 to 2.5 of 255 mean absolute error of the preview maths, with larger differences only at saturated edges (chroma subsampling).

## Limits (by design, today)
- No masks: no qualifier, power windows or tracking (they need per-pixel masks, which `lut3d` cannot do). Colour only; no blur, sharpen or noise reduction (Fusion's job).
- Grades apply to V1 video clips, not to V2 still overlays.
- Mid-detail, HDR wheels, log wheels, colour-managed workflows and the CIE scope are not built. Values are display-referred Rec.709.
- Stills and imported LUTs live in browser storage (about 24 stills; LUTs are stored as 16-bit tables), not in the engine vault.
- Each unique grade adds about 1 MB to the export request.
