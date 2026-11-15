# ChronoFlow Studio - UX and layout redesign (2026-11-15)

Owner's request: the video studio looks arranged "randomly" - Color / Deliver / Fusion do not sync with the UI, AI features sit
under the video wherever they landed, recently generated videos vanish (fixed, then gone again), and there is no import from the
file system or from the places videos are stored. Research first, then arrange everything properly.

## What was measured (real app, 1440x900)
- **Two navigations fight.** `switchTab()` rewrites the bottom rail (Video Studio -> Edit, Image Studio -> Color, Storyboard -> Cut), so the
  rail highlights the wrong page; Color/Deliver show "Edit" highlighted. Cut and Fairlight have nothing behind them (Cut = a hidden old
  chunk list, Fairlight = a copy of Edit). Fusion rendered the Deliver panel in my run.
- **Layout is height-by-guess.** `.davinci-top-row` is `56vh` and each page overrides it (48vh / 58vh), the timeline is whatever is left, the
  Color panel falls below the fold. The player shrinks to a thumbnail on Color/Deliver.
- **AI actions are scattered:** "Prompt" + "New Shot Controls" (same button twice, header), "Load Scene" + "Import Scene" (twice),
  "Magic Brush" (monitor bar + frame bar), "Image Studio", "Auto-Gen Prompt", "Regen Frame", the AI Director (Storyboard tab only).
- **Hard-coded title** "MATT GOSS PROMO v2" on every job; the studio opens on a test job.
- **Why videos "disappear":** (1) `vault/jobs.json` is tracked in git *and* written by the unit tests (41 of 64 jobs were test leftovers
  pointing at `test_chunk_1.mp4`), so test runs and `git checkout` rewrite or bury the real jobs; (2) the studio only scans `output/chronoflow`
  - the real videos live in `output/Original_Stories` (1276 mp4), `series_*`, `reels`, `shorts`, `youtube_uploads`; (3) the only import path
  needs storyboard shots (`import_scene_to_studio`); the "Browse Disk" button just opens that scene importer.

## Research (summary)
- DaVinci Resolve: pages run left to right in workflow order along the bottom (Media, Cut, Edit, Fusion, Color, Fairlight, Deliver), all share
  one timeline; beginners are told Edit + Color + Deliver is enough for a short video. Media = import and organise, Edit = main hub.
- Premiere / Resolve import: import lands in the selected bin, folders map to bins, show a preview, search before importing; moving source
  files outside the app breaks clips (so import must not depend on the original path staying put).
- Empty states should teach and give one obvious action (Descript, VEED, iMovie patterns); never leave a blank pane.

## Decisions (my calls, owner can overrule)
1. **One source of truth for navigation.** `CFPage` holds the current page; the rail, the layout (`data-page`) and the modules (Color/Fusion/Deliver
   open/close) all derive from it. The rail is shown only on the Video Studio tab. Pages: **Media, Edit, Fusion, Color, Deliver**. Cut and Fairlight are
   removed because nothing is behind them (re-add when real).
2. **Fixed workspace, no page scroll.** Wrapper is `100vh - header - rail`. Row 1 (flex) = left panel | monitor | right panel; row 2 = timeline (260 px)
   or, on Color/Fusion, the page's own panel with a slim timeline strip. The monitor never goes below ~45 % of the width.
   Left/right panels per page: Edit = Media pool | **AI Tools**; Fusion = Media pool | node inspector; Color = Stills | Scopes;
   Deliver = Render settings | Render queue.
3. **AI Tools panel (Edit, right column)** groups every AI action with a one-line "what it is for": New shot, Shot prompt (auto-write, correct,
   regenerate), Change this frame (Magic Brush), Plan a storyboard (AI Director), Send frame to Image Studio. Header keeps only one primary button,
   "+ New video".
4. **Media page = library.** Left: sources (Recent, each output folder, saved locations). Centre: searchable grid with hover preview, multi-select.
   Footer: "Add N to project". Plus "Import files..." and "Add folder..." (native OS dialogs, real paths, no upload).
5. **Import = hard-link into the studio output folder** (copy when on another drive) as `imp_<id>_chunk_<n>.<ext>` of a new job, so the existing
   player, thumbnails and `resolve_media()` work unchanged and the file keeps working if the original moves.
6. **Jobs vault leaves git and tests.** `PANELFLOW_CHRONOFLOW_VAULT` env override, tests use a temp vault, `jobs.json` untracked + ignored. The 41 test
   leftovers are removed after a backup. The studio opens on the newest *real* job, and the job picker is a labelled list, not raw ids.
7. Not doing: drag-and-drop from Explorer (browsers give no real paths; needs upload), a mixer for audio, rewriting the 11k-line page.

## Done means
Every page shows a full-size monitor, the rail always matches the page, imported/recent videos appear and survive a restart and a test run, checked in the
real app at 1440x900 and a narrower window.
