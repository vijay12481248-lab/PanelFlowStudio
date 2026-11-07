---
name: minimax-h3-video-production
description: Produce, prompt, evaluate and regenerate MiniMax H3 video clips in PanelFlow (local ComfyUI H3 - film shots, animated beats, multi-clip stories). Use when writing an H3 motion prompt, choosing a generation mode, fixing zoom/drift/invented speech/identity problems, judging whether a clip is good, or planning a multi-shot video. Not for still images (ArtEngine) or the hosted MiniMax API.
---

# MiniMax H3 video production (PanelFlow, local)

A guide for agents. It does not generate anything itself: the tools below do. It complements the official `h3-prompt-writing` skill (exact field syntax) and does not copy it.

## Ground rules
1. **Evidence tiers.** Every claim in `references/` is tagged `[official]` (MiniMax docs), `[verified]` (seen in this tree or measured here) or `[hypothesis]`. Do not promote a hypothesis to a fact in a report.
2. **Never call a clip good or fixed from the prompt or from a VLM alone.** Run `engine.original.clip_eval.evaluate`, look at the contact sheet, then say what was and was not checked.
3. **One lever per retry.** Same frame + prompt + seed + workflow gives a bit-identical clip `[verified]`, so a retry that changes nothing is wasted GPU time, and a retry that changes two things teaches nothing.
4. **Generic fixes only.** The system writes prompts (shot director -> `film.motion_prompt`); never hand-write per-story text into code. Fix the rule, not the shot.
5. **Local-first, no silent fallbacks.** Do not use the hosted API (Context-IR, Regenerate-2K: paid, pricing not found). Downloads of models need the owner's approval with file, size and source first.
6. **GPU etiquette.** ComfyUI + Ollama use ~13-15 GB of 16 GB. Check `GET :8188/queue` is empty before generating; another job may be running. Never restart the engine mid-job.

## What is actually available (details: `references/local-capabilities.md`)
| Mode | Local status |
|---|---|
| I2VA (first frame + text) | **Works.** Workflows `fastvideo_h3_i2v`, `fastvideo_h3_film_free`, `fastvideo_h3_film_voice` (voice-anchored) |
| FL2VA / L2VA (last frame) | Node supports it, but **no registered workflow wires `last_frame`**: needs a new approved workflow |
| T2VA | Same node with no frames; no registered workflow, never run here |
| Ref2VA (images/video/audio references) | **No Ref2VA weights on disk.** `MiniMaxH3ReferenceToVideo` node exists; do not use ChronoFlow "reference" mode |

## Procedure
1. **Plan the shot** - one clip = one shot, one action, 3-5 s, a Qwen first frame that already shows the look. Write its state card (`references/multi-clip.md`).
2. **Pick the mode** from the table above (almost always I2VA).
3. **Write the prompt** with the official skeleton + the local rules (`references/prompting.md`). Camera sentence defaults to **Static Shot** (`references/camera-and-motion.md`).
4. **Sound**: decide anchored voice / native voice / quiet / SFX (`references/audio-and-dialogue.md`).
5. **Generate** through `film.make_clips` / `animate.animate_beats` (they use `ArtEngine.run` + the workflow registry). Do not add a second submit/poll loop.
6. **Evaluate** (`references/evaluation.md`): `python -m engine.original.clip_eval clip.mp4 [any]`, read the contact sheet, record flags with timestamps.
7. **Correct** only the top confirmed defect with one lever (`references/regeneration.md`), re-evaluate, keep the better clip, stop at 3 attempts, report what remains.
8. **Assemble** with `film_master` (`references/multi-clip.md`), check cuts and loudness, then ASR the final file.

## When to load which reference
| Situation | Load |
|---|---|
| What can this machine do / which mode / limits | `references/local-capabilities.md` |
| Writing or fixing a prompt | `references/prompting.md` (+ `examples/i2va-static.md`) |
| Zoom, pan, camera wording, "keep it still" | `references/camera-and-motion.md` |
| Character, outfit, lighting, style staying the same | `references/consistency.md` |
| Speech, lip sync, SFX, music, loudness | `references/audio-and-dialogue.md` |
| Judging a clip, reading a flag | `references/evaluation.md` (+ `examples/evaluation-examples.md`) |
| A clip failed; what to change | `references/regeneration.md`, `references/troubleshooting.md` |
| Many clips / a 5+ minute video | `references/multi-clip.md` |

## Not built yet (do not pretend they exist)
The `quiet` lever, a metric that shows scene-continuity gains (the evaluator missed `p005`'s), API/MCP/UI hook for the loop (command line only), identity/object checks (no face/CLIP/SAM3 measurement yet), FL2VA workflow, reference mode weights, ChronoFlow UI still shows constant fake scores from the deprecated `chronoflow/reviewer.py`.
