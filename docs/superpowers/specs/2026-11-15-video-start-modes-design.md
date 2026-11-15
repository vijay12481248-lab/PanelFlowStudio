# ChronoFlow "New Video": choose how to start, plan segments, review each one

Date 2026-11-15. Status: awaiting owner approval. Scope: ChronoFlow studio UI (`engine/chronoflow/static/index.html`) and `engine/api/routers/chronoflow.py`.

## Intent
Today "Start New Video Production" opens one popup (one prompt, one duration) and fires an automatic sliding-window run. The owner wants a **manual, guided** way to make videos: first say *how the video starts* (text, first frame, first+last frame, last frame, reference images, or an existing video), then how long it is, then fill in a plan of segments, then render and approve one segment at a time. A 5 minute video is ~58 segments of 5.17 s, so the plan has to be a real grid, not a popup.

## Goals
- Step 1: pick a start mode. Step 2: pick a length, which becomes N segments. Step 3: a segment plan where each segment shows only what its mode needs: a video prompt plus frame slots.
- A frame slot can be filled by **upload**, **Vault**, or **generate from a text image prompt, preview, accept** (so the user can start with no pictures).
- Render one segment, **approve or redo**, then the next segment starts from the approved clip's real tail frame.
- Prompts: the user writes them, or one click drafts all N from a story idea with the local LLM and the user edits.
- Reuse what exists; no second storyboard editor and no second text-to-image path.

## Non-goals
- No change to Original Stories, `engine/original/chain.py`, or anime review.
- No "render everything" run. The owner chose per-segment review. (A button that renders only the next segment is fine.)
- No audio or voice-over work, no upload to YouTube.
- The `POST /generate` batch route stays for agents (MCP) and the old reference path (up to 9 refs); the UI just stops calling it.

## Anti-goals (would be a failure even if it works)
- Plans that only work for one story or genre (AGENTS.md: generic only).
- Silent fallback to a different mode (for example a missing last frame turning into text-only without telling the user).
- Reporting a mode as working without watching a real clip from it.

## Approaches considered
- **A. Everything inside the popup.** Smallest change. 58 segments with image slots and previews do not fit in a 580 px popup. Rejected.
- **B. Short wizard, then the existing Storyboard grid.** The popup asks mode, length and story idea, then creates a storyboard pre-filled with N cards and opens it. The grid, `render_shot`, link-video, move/delete and the vault save already exist. **Chosen by the owner.**
- **C. New full-page Production Planner.** Cleanest layout, but a second segment editor beside the storyboard. Rejected.

Decided with the owner (2026-11-15): per-segment prompts with AI draft help; review each segment before the next; the new modes run through the registered `engine/original/h3_modes.py` workflows.

## Flow
```
[New Video] -> Wizard (popup)
   1 Start mode   Text only | First frame | First + last | Last frame only | Reference images | From a video
   2 Length       presets 15s / 30s / 1 min / 5 min / custom -> "5 min = 58 segments x 5.17 s"
                  Format 16:9 or 9:16, speed (4-step / 8-step) tucked under "More"
   3 Story idea   optional; checkbox "Draft all prompts with AI"
 -> creates a storyboard of N cards, opens the Storyboard tab at card 1

Card (per segment)         mode chip | prompt | slots for this mode | state
  Text            no slot
  First           [First frame]
  First + last    [First frame] [Last frame]
  Last            [Last frame]
  Reference       [Ref 1] [Ref 2]
  Slot actions    Upload | Vault | Generate (image prompt -> preview -> Accept)

Card state: empty -> ready -> rendering -> review (Approve | Redo | Edit prompt) -> approved
```
Rules:
- The wizard mode is the **default mode of every card**. A card can change its own mode (the owner can mix modes in one video).
- **Continuity:** a card whose first frame is empty and whose mode takes one inherits the **tail frame of the previous approved card** (that is what sliding window does today). Text-only video therefore means segment 1 is text-only and later segments continue from tail frames; the card's mode chip shows this plainly ("First frame: from Shot 1 tail").
- A card that depends on the previous card cannot render until that card is approved. A card with its own user-supplied frames can render any time.
- First + last: the last frame of card N is offered as the first frame of card N+1 (keyframe chain), editable.
- "From a video": the user picks a clip from the media library; its tail frame becomes card 1's first frame (`pipeline.extract_tail_frame`). This sixth mode is my addition to the owner's list ("if he has the video, similar workflow").

## Engine routing
`POST /storyboard/render_shot` gets a `start_mode` per scene and dispatches:

| Card mode | Route |
|-----------|-------|
| First, From a video, inherited tail frame | existing `pipeline.build_h3_prompt` (unchanged) |
| Text | `h3_modes.make_clip("t2va")` |
| First + last | `h3_modes.make_clip("fl2va")` |
| Last | `h3_modes.make_clip("l2va")` |
| Reference | `h3_modes.make_clip("ref2va")` (`fastvideo_h3_omniref`) |

`make_clip` is synchronous (`ArtEngine.run` polls ComfyUI), so the endpoint runs it in a worker thread. The card's `duration` is honored (snapped to the 17k+5 frame grid with `h3_modes.clip_seconds`); today `render_shot` ignores it and renders 124 frames.

Prompt wrapping: for the `h3_modes` routes the card stores a plain action description and the engine wraps it with the matching builder (`t2va_prompt`, `fl2va_prompt`, `l2va_prompt`, `ref2va_prompt`). A card whose prompt already uses the official headings is sent as written (my call, the builder may refine).

## Data (additions to a storyboard scene)
`start_mode`, `first_prompt`, `last_prompt` (image prompts for the slot's Generate action), `first_frame`, `last_frame`, `ref_images` (already exist), `state`, `approved` (bool), `inherits_tail` (bool). Saved through the existing `saveCurrentStoryboard` / `/screenplay/save`, so a plan survives a restart and can be reopened.

## Backend additions
1. Wizard -> `POST /storyboard/plan` creates N empty cards (mode, durations, folder) and returns the screenplay. Plain code, no LLM.
2. `POST /storyboard/draft_prompts` (story idea, N, mode) -> N plain action prompts from the local LLM (Ollama `qwen3.5:9b`), each continuing the last. Server checks count == N and non-empty; on failure it says so (no silent mock). `/ai_director/plan` is a canned template, not an LLM, so it is not reused; `/autogen_prompt` is job-bound, so it is not reused either.
3. `render_shot` dispatch above, plus tail-frame extraction and saving the tail to the ComfyUI input folder for the next card.
4. Frame slot Generate: the existing `POST /generate_image` (the one `ArtEngine` path); Upload: existing `/upload_image`.

## UI additions
- Replace `#promptModal` contents with the 3-step wizard; the header button becomes "New Video". Resolution and speed move under "More".
- Beat editor / cards (`renderStoryboardGrid`, `openBeatEditor`): mode chip, the slots above with thumbnails, state badge, Approve / Redo. The card already shows the first frame; last frame and refs have no UI today.
- `renderSingleStoryboardShot`: send `start_mode` and duration, stop the blocking `alert`, route the result to the review state.

## Constraints and known limits (tell the owner)
- **Text-only and reference clips render at 960x544 (0.5 MP)**, not 1344x768 (`T2VA_SIZE`). First+last derives its size from the pictures. Mixed modes in one video therefore mix sizes; the stitch step must scale or the UI must warn. Decision for the builder: warn on the card and scale to the video's format when stitching.
- `ref2va` takes **2** reference pictures (identity + place). The old ChronoFlow path took up to 9; the new Reference mode is limited to 2.
- 58 sequential renders is a long GPU session; the review-each-segment rule makes the user the pacing, and ComfyUI+Ollama hold ~13 GB VRAM (the job manager holds back when memory is not free).
- The 9B local model is a noisy drafter: drafts are suggestions, the user edits.

## Verification (owner's rule: verify on real data)
- Unit tests: segment count from length, mode -> route table, slot requirements per mode (missing frame is an error, never a silent mode change), render_shot dispatch with `make_clip` faked, draft_prompts count check.
- Real runs, watched by me before claiming done: one clip each of text, first+last, last-only and reference, plus a 3-segment first-frame chain through the approve gate. Report what was not verified.
- Desktop UI is not a Tauri window path here (the studio is static HTML on :8765); check in the in-app browser.

## Left to the builder
Exact visual design of the wizard and slot widgets (follow the existing `btn-tool`, `shot-beat-card` styles), the draft prompt template text, stitching/scaling of mixed sizes, how "From a video" opens the media library, naming of new scene fields.

## My calls to check
1. Sixth mode "From a video".
2. Reference mode limited to 2 pictures.
3. Wizard mode = default per card, mixable per card.
4. Plain action text on cards for the `h3_modes` routes, wrapped by the engine.
5. 960x544 clips for text and reference, warn + scale at stitch.

## Measured (2026-11-15)
Checked against an isolated engine (port 8766, temp app-data) with the real local models and the real ComfyUI.

**Worked, seen on screen**
- Wizard, three steps; a 5 min plan shows "5 min = 58 segments x 5.17 s"; 30 s 9:16 makes 6 cards at 768x1344.
- AI draft (Ollama `qwen3.5:9b`, 6 batches for 58 shots): 58 unique prompts, about 22 words each, the story carried forward; some repetition near the end ("descends the staircase" twice), so drafts are suggestions to edit.
- A saved plan reloads with every card field intact (this needed a fix: the screenplay loader used to drop unknown fields; test `test_screenplay_round_trip_keeps_wizard_card_fields`).
- Card slot "Generate": a real Qwen picture from the shot prompt (a red fox in snow), previewed and accepted; Vault picker listed real pictures; Render is disabled with a readable reason until the card has its prompt and frames.
- Review gate: Shot 2 locked until Shot 1 is approved; Redo marks chained followers "Redo needed".
- Server guard rails with real inputs: a missing frame file and a chained card without a previous tail frame both return 400 naming the problem; nothing renders.

**NOT verified**
- **No clip was rendered in any mode** (text, first+last, last-only, reference, 3-card first-frame chain). Every attempt failed inside ComfyUI at the video model loader with Windows "The paging file is too small for this operation to complete (os error 1455)". The unchanged first-frame path failed the same way, so this is the machine's commit limit, not the new code: the two H3 models need about 38 GB (20.6 GB video model + ~15 GB text encoder) against ~34 GB free commit (page file system-managed, ~40 GB allocated). A larger page file, a restart, or closing memory-heavy programs is needed; then run the clips again and add what was seen here (identity drift, zoom, invented speech, render time, VRAM).
- 9:16 clips at 544x960; the sizes the engine asks `make_clip` for are untested on real output.
- Upload button (opens a file dialog) and the "Clip..." picker for "From a video".
- Mixed sizes at Deliver: read, not run. `pipeline.py` (timeline export) scales every clip to the program size with letterboxing, so a 960x544 clip in a 1344x768 program should be accepted; the old `stitch_chunks` concat needs same-size clips but the wizard flow does not use it.
