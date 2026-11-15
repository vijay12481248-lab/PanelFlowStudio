# Video Plan Kit: any chatbot interviews the owner, then writes a plan PanelFlow can run

Date 2026-11-15. Status: kit written and verified against the code; the importer is NOT built yet. Supersedes the first "brief" idea (a ChronoFlow-only JSON) written earlier the same day.

## Intent
The owner does not want to walk through every screen. They hand ONE file to any assistant (ChatGPT, Gemini, Claude, or a coding agent such as Claude Code, Codex, Antigravity). The assistant **interviews the owner** (which workflow, how long a clip their GPU makes, how scenes connect, cast, places, direction), then returns one JSON **plan** that fits PanelFlow's real workflows. The owner imports it; PanelFlow draws the pictures, shows them for review, then makes the videos. The kit also tells the assistant HOW to guide the plan so continuity, scene flow and direction survive the video model.

## Deliverables (all in `docs/video-plan-kit/`)
- `PANELFLOW_VIDEO_PLAN_KIT.md`: the one file to hand over (role, 3-round interview, system facts with evidence tags, 20 hard writing rules, the plan format with a complete worked example, self-check, delivery rules, the Short/Reel variant, and the checker script).
- `check_plan.py`: the same standalone checker (stdlib only) for the owner or an agent.
- `example_plan.json`: the worked example.

## What the research found (and what it changed)
1. **The existing production pipeline already is "plan -> pictures -> clips -> master".** `tools/produce_video.py` (stages `plan | frames | clips | stabilize | qa | master`, resumable) turns a brief into an `OriginalStory` via the Director (the local 9B model, a noisy writer), draws a checked start and end picture per take (`engine/original/storyboard.py`), animates between them with FL2VA (`engine/original/h3_modes.py`) and masters with narration and music. So the plan format is the `OriginalStory` shape, written by a stronger model; the stage split gives the "pictures, review, then videos" stop for free.
2. **Clip length is the owner's choice** (`production.clip_seconds`, maps to the pipeline's `--max-take`). Official H3 range 4-15 s; measured on this PC: 15 s = 6.3 min and 15.7 of 16.3 GB VRAM; shorter clips follow the plan better and longer ones invent (docs/H3_CLIP_EVAL.md, `minimax-h3-video-production/references/prompting.md`). The kit tells the assistant to ask, show these numbers, recommend 5 s, and use `beats` for 8 s and longer.
3. **Continuity** has three real mechanisms, offered as `production.join`: `matched_pictures` (the storyboard rule: a take in the same place with the same cast starts from the previous take's end picture, the same file; the tested default), `seamless_chain` (Herrgott latent chain, `engine/original/chain.py`, 16:9 only, ~4.5 s per clip, one place, not wired into the app yet) and `clip_tail` (start from the last video frame; drifts, `ChronoFlow sliding window`).
4. **The rules that matter are measured failures**, now hard rules in the kit: never name what must not appear (H3 draws negated words), describe each character once, closed cast, a walk must be drawn as start and end pictures on different sides with a direction, start and end pictures share the world, characters never carried or stacked, no readable text, fixed camera unless one of three slow moves, narration words from `int(max(1, s - 0.8) * 2.8)`.
5. **A quirk found while verifying:** the Director's movement detector reads the noun "head" ("tilts its head") as someone heading somewhere and silently inserts a direction. The kit forbids "head/heads" in pictures and motion; the importer must not blindly call `fix_direction`.
6. The shipped Shorts pipeline takes a `REELS` dict (`tools/reels/specs.py`); the kit's Short variant has exactly its keys.

## Plan -> existing code (verified with a scratch converter, not committed)
| Plan field | Existing structure |
|---|---|
| `title, logline, genre` | `Premise(title, genre, logline, tone = genre tone, setting)` |
| `cast[]`, `places[]`, `rules[]` | `Character`, `Location` (look = comma-separated tags), `Bible.rules` |
| `scenes[]` | `Scene(id, location_id = place, summary, mood, score = music, title)` |
| `takes[]` | `Panel(shot = framing, action = start picture, motion, end_state = end picture, dialogue = [Line("narrator", narration)], key_visuals = [shows], atmosphere, camera, seconds, shots = [{at, framing, camera, action, characters}])`; a `previous_end` take takes the previous end picture as its start |
| `production.clip_seconds` | `--max-take` |
| `target: "film"` | `produce_video.py` stages `frames`, review, `clips`, `stabilize`, `qa`, `master` |
| `target: "cards"` | ChronoFlow cards (`first_last` per take, plain motion as the card prompt) |
| `target: "short"` | one `REELS` entry |

**Proof of fit (2026-11-15):** the example plan built a real `OriginalStory` (4 panels, 2 scenes, 2 characters) and every take passed the Director's own storyboard validator (`director.check_take`) with 0 problems; a deliberately broken copy produced the four expected problems (narration length, readable-text word, end picture too short, `shows` too short). The standalone `check_plan.py` agrees on both and, in addition, found the "head" quirk. The Short example's keys equal a shipped `REELS` entry.

## Not built (next steps, in order)
1. A converter + validator in `engine/` (plan JSON -> `OriginalStory`, reusing `director.check_take` for film; `check_plan.py` stays the portable twin), with problems listed in plain words and a "copy for the assistant" button.
2. `produce_video.py --plan file.json` (skip the Director) and a review stop after the `frames` stage in the app; ChronoFlow "Import plan" for `cards` (the Pictures bar and Render all ideas from the earlier brief design carry over); `seamless_chain` wiring.
3. A real session with a chatbot using the kit, then fix the kit from what it gets wrong.

## Not verified
- The kit has not been given to a real chatbot yet (only its example and script were checked).
- No video clip from any workflow was rendered today (the machine's page file blocks the H3 model load; see the start-modes spec).
- The reference-PC timings are the owner's PC only; the kit tells the assistant to ask for theirs.
