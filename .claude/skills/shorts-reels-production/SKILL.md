---
name: shorts-reels-production
description: Make vertical YouTube Shorts / Instagram Reels (9:16, 20-32 s, funny or emotional stick-figure doodle animation) end to end in PanelFlow - concept, narration, music, pictures, MiniMax H3 animation, captions, thumbnail, title/description/tags. Use when asked for Shorts, Reels, viral clips, a batch of short videos, a thumbnail or cover for one, or its upload copy. Not for 5+ minute videos (see docs/ORIGINAL_STORY_STUDIO.md) or anime reviews (docs/ANIME_REVIEW.md).
---

# Shorts / Reels production (PanelFlow, local)

A guide for agents plus the runnable pipeline in `tools/reels/`. The system writes nothing per reel by hand except the **spec** (concept, narration lines, one picture prompt and one motion sentence per scene); every model call, timing, caption and mix is code. Proven on 2026-11-14: 10 reels, 50 scenes, one night.

## Ground rules (the owner's, from AGENTS.md)
1. **Verify on real data.** Look at the contact sheets and frames, run the checks below, then say what was and was not checked. Never grade from tests or from a VLM alone.
2. **Generic fixes only.** If a picture or clip is wrong, fix the rule or the spec text, not a one-off hack in code.
3. **Originals only.** Concepts are written fresh from everyday situations. Never download, scrape or copy another creator's video, script, characters or audio. State plainly that no source video was used.
4. **Local-first, no silent fallback.** Qwen3-TTS missing -> stop, do not switch to Kokoro. ComfyUI down -> start it or stop.
5. **Publishing.** Upload PRIVATE first; public or scheduled needs the owner's explicit go-ahead; "made for kids" is the owner's declaration. Tick the AI/synthetic-content disclosure on YouTube and Instagram.
6. **Downloads of models/files need the owner's approval** with exact file, size and source.
7. **Licences are unresolved - say so.** Qwen-Image-2.1 is under the Qwen Research License (research/evaluation only; see the Qwen audit in memory). H3-Image, H3 video, ACE-Step and the voice-reference recordings were NOT checked for commercial use. Tell the owner before they monetise.
8. Never restart the engine or ComfyUI mid-job. Commit only your own files (`git status` shows others' work).

## The models (all local)
| Job | Model | Notes |
|---|---|---|
| Voice | Qwen3-TTS voice clone, `D:\Tools\Qwen3-TTS` | references in `%LOCALAPPDATA%\PanelFlow Studio\voice_references` (`marcus_male`, `aria_female`); ~50 lines in ~4 min |
| Music | ACE-Step 1.5 (`engine/audio/providers/ace_step.py`) | 32 s instrumental bed in ~6 s; daemon auto-starts on :8001 and is stopped after the stage |
| Pictures | **MiniMax-H3-Image** = workflow `minimax_h3_image_edit` with no picture bound (text to image), 768x1344, 17-32 s each | default since 2026-11-14 at the owner's request; `REEL_IMG_WORKFLOW=qwen_image_21` gives Qwen (8-25 s). Called only through `ArtEngine.generate(workflow_id=...)`; never add a second submit/poll loop |
| Animation | MiniMax FastH3 image-to-video, workflow `fastvideo_h3_i2v`, 480x832, 5 s | ~86 s per clip; one action per clip, Static Shot (load `minimax-h3-video-production` for prompt rules) |
| Assemble | ffmpeg (libx264 + libass) | 1080x1920, 30 fps, Impact captions, loudnorm to about -16 LUFS |

## Run it
```
cd "E:\VIJAY SEKAR\PanelFlow Studio"
# ComfyUI must be up on :8188 (see AGENTS.md); set PANELFLOW_COMFYUI_WORKFLOW_DIR=E:\VIJAY SEKAR\ComfyUI\workflow
.venv\Scripts\python.exe tools/reels/make_reel.py status
.venv\Scripts\python.exe tools/reels/make_reel.py tts      [slug-prefix ...]
.venv\Scripts\python.exe tools/reels/make_reel.py music    [slug-prefix ...]
.venv\Scripts\python.exe tools/reels/make_reel.py art      [slug-prefix ...]
.venv\Scripts\python.exe tools/reels/make_reel.py clips    [slug-prefix ...]
.venv\Scripts\python.exe tools/reels/make_reel.py assemble [slug-prefix ...]
.venv\Scripts\python.exe tools/reels/thumbs.py art|compose [slug-prefix ...]
.venv\Scripts\python.exe tools/reels/publish.py
```
- **One model family on the GPU at a time:** tts -> music -> art -> clips. Assemble is CPU only and can run while clips render.
- Every stage is resumable and skips existing files. To redo one item delete its file (panel, clip, wav) and rerun the stage.
- Env: `REEL_OUT_DIR` (default `reels`; use another name so a new run never overwrites finished reels), `REEL_IMG_WORKFLOW`, `REEL_SEED_BUMP` (re-roll clips with a new seed).
- Long stages: run in the background and read the log; do not poll in a tight loop. Run with `python -u` or the log stays empty.

## Make a new reel (procedure)
1. **Concept**: pick a relatable situation and write it with the formula in `references/concept-formula.md` (hook -> 3 escalating beats -> twist or emotional payoff -> comment bait; 5 scenes, narration lines of 8-14 words).
2. **Spec**: add a dict to `REELS` in `tools/reels/specs.py` (slug `rNN_name`, title, hook, voice, music prompt, bpm, palette, `chars`, tags, five scenes with `img`, `act`, `line`). Put scenes that change location in `NO_REF` so the scene-1 picture does not drag the old room along. Add a `THUMBS` entry and `COPY` entry (`thumbs.py`, `publish.py`).
3. **Voice, music, pictures** (stages above). **Look at a contact sheet of the stills before any clip**: wrong face, wrong room, missing prop, text in the picture. Redraw cheap stills first (a clip costs ~86 s).
4. **Clips**, then assemble. Fix at most the top defect per retry with one lever (new seed via `REEL_SEED_BUMP`, or reword `act`/`img`), keep the better clip, stop at 3 tries and report what remains.
5. **Check the finished file** (all three, on the real mp4): `ffprobe` size 1080x1920 and duration 20-32 s; `ffmpeg -i f.mp4 -af ebur128=peak=true -f null -` gives about -16 LUFS and true peak under -1 dBFS; Whisper word-error rate through `engine.narration.runtime.audio.WhisperStt` (pass samples, not a path; extract with `ffmpeg -vn -ac 1 -ar 16000`). Also view a frame strip (`ffmpeg -vf "fps=1/2.6,scale=216:384,tile=6x2"`) for captions on the face, frozen frames and invented objects.
6. **Thumbnail and publish copy**: `references/thumbnails-and-publishing.md`.
7. Copy finals into `output/reels/_READY_TO_UPLOAD/` (it is a copy: say so) and write the index.

## Report honestly
State: files and where they are; what was checked (size, loudness, WER, frames); what was NOT (the voices were not listened to, the jokes are untested on an audience, no click-through or retention measured, nothing uploaded); the licence caveat; known defects.

## References (load when needed)
| Need | File |
|---|---|
| Hook, formula, research summary, the ten shipped concepts | `references/concept-formula.md` |
| Thumbnails, covers, safe zones, title/description/tags, platform facts | `references/thumbnails-and-publishing.md` |
| Everything that went wrong and the fix | `references/gotchas.md` |
| H3 clip prompts, drift, regeneration | `.claude/skills/minimax-h3-video-production/` |
