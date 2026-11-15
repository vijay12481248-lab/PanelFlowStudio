# Scene Director - design

Status: DRAFT for owner approval (2026-11-14). Nothing is built.

## Intent and why

The art models (Qwen Image 2.1 Turbo, MiniMax H3-Image) draw well but obey vague or under-specified instructions loosely. The owner gives abstract briefs
("hero fights villain", "this emotion", "concept art like this"). The result is only good if the *staging* is right: who stands where, what each body is doing,
camera, light, depth. Today nothing turns a vague brief into that staging, nothing checks the picture against it, and the learning code is not connected to the art path.

The Scene Director is one layer between the brief and the image model:

    brief -> (ask / propose) -> ScenePlan -> prompt (+ staging picture if needed) -> image -> check against the plan -> correct -> deliver

Success, in the owner's words: what the user imagined and what is delivered agree at least 90% of the time, delivered fast, mostly with code and the existing small local model.

## Goals

1. A vague brief becomes a complete, written `ScenePlan` (actors, screen positions, action state, contact and direction, camera, lighting, depth). If the user will not answer questions, the system decides.
2. The user is asked at most 3 short questions, each with a proposed default ("low angle, hero left striking down-right, villain right blocking, light from behind - go?").
3. Every plan item that a picture can show becomes a checkable requirement. The picture is checked before the user sees it; failures change the instructions and the picture is redrawn or repaired.
4. Fast path first (words only, Qwen). Escalate to a staging picture + two-picture transfer only when pose / camera / contact checks fail.
5. The system keeps lessons (model, scene type, plan item, failure, what fixed it) and uses them in later plans and prompts.
6. The 90% target is measurable: owner ratings on real outputs, kept with the plan that produced them.

## Non-goals

- No new image model, no second text-to-image workflow (AGENTS.md: `qwen_image_21` via `ArtEngine` only; H3-Image only as the owner's existing exception).
- No fine-tuning or training of models.
- No cloud fallback. Local-first.
- No per-story hand-written prompts. Playbooks are generic per scene type, not per story.
- Video (H3 clips) staging is out of scope for the first version; pictures first.

## Anti-goals (a failure even if it "works")

- Passing the system's own check while the owner still dislikes the picture (the 9B judge is noisy; measured against owner ratings, not only against itself).
- Learning noise: a lesson saved from one lucky or unlucky run.
- Slower than the owner will tolerate, because every picture gets the full 70 s review.
- Tuned to one chapter, character or genre.

## Constraints

- RTX 5060 Ti 16 GB: ComfyUI + Ollama together use ~13 GB; GPU jobs are held back when memory is not free.
- Reviewer measured earlier: one full review ~70 s (`qwen3.5:9b`). Qwen Turbo draw time and planner time on this machine are NOT measured yet.
- Two-picture transfer measured 40-90 s per edit; pose picture must be Picture 1, characters Picture 2 (memory: h3-pose-camera-transfer). Only tried with real art / a photo as the pose picture, never a code-drawn stick-figure picture.
- Qwen Turbo ignores instruction edits; only masked latent redraw repairs work.
- Owner rules: verify on real data, generic solutions only, say what was not verified.

## What exists (checked 2026-11-14)

| Need | Already there |
|---|---|
| Structured staging | `ShotSpec` / `CharPose` in `engine/original/shotspec.py` (side, pose, action, camera, lighting, mood) |
| Prompt writing | `engine/original/prompt.py` composer, `docs/PROMPT_PRACTITIONER_GUIDE.md` (defect taxonomy, per-model rules) |
| Check | `engine/original/review.py` (`evaluate_prompt_image`, claims with kinds pose/camera/framing/placement, boxes, `Review`/`ItemVerdict`) |
| Correct | `planner.plan_correction`, `refine.py` (redraw, masked Qwen repair, candidates kept), `art._refine_directed_panel`; opt-in, unproven on a real failure |
| Pose/camera transfer | `ArtEngine.edit` + `compose_transfer_prompt` (`engine/comfyui/edit_prompt.py`) |
| Lessons | `engine/creative/mistakes.py` (`MistakeLedger`, 26 entries), `self_improvement.py` (7 rules), `knowledge.py` (93 entries) |

Gaps: (a) nothing fills a `ShotSpec` from a vague brief or asks the user; (b) plan-to-requirement check is not wired for a plan that came from a brief; (c) nothing in `engine/original` or `engine/comfyui` imports `engine.creative`, so the ledger never reaches the art path; (d) no labelled baseline and no owner rating.

## Approaches considered

- **A. Words only.** Planner -> composer -> Qwen -> check -> corrector. Fastest, cheapest; weak where Qwen Turbo ignores exact poses / contact.
- **B. Always plan + staging picture.** Best pose/camera control; every image pays the transfer cost; staging pictures unproven.
- **C. A first, escalate to B only when pose/camera/contact fail (chosen by the owner).** Fast by default, uses built or measured parts, escalation gives control where words fail.

## Design

### 1. Plan model and playbooks
`ScenePlan` (pydantic, extends what `ShotSpec` already holds, builder decides extend vs wrap): scene_type, actors[] (id, screen position left/center/right + depth layer, action_state from a small enum per scene type, e.g. fight: striking / blocking / readying / struck / falling; expression), contacts[] (who -> whom, body part, direction), camera (angle, distance, lens feel), light (direction, quality, key colour), depth (foreground / midground / background contents), mood.
Playbooks are data files (one per scene type: fight, emotion/portrait, concept art first) holding: the questions worth asking, default answers, allowed action states, and staging rules (e.g. attacker and defender on opposite sides, strike direction toward the other actor). The planner (local 9B, validated and retried like `story._ask`) fills the plan from the brief + playbook; rules, not the model, compose anything the image model must be told.

### 2. Intake: propose and confirm
Brief in -> planner proposes a full plan in plain words with defaults -> user says "go" or corrects a few items. Mode `auto` skips the question and uses the proposal. Questions are limited to items the playbook marks as high-impact and the brief did not state.

### 3. Fast path
`ScenePlan` -> `ShotSpec` + emphasis -> existing composer -> `ArtEngine` (Qwen).

### 4. Check against the plan
Each plan item that a picture can show is turned into a requirement (existing `Claim`, kinds pose / placement / camera / framing / count). Deterministic checks first (figure count, left/right from boxes), the VLM only for what code cannot decide. A fast mode checks only the critical items (positions, action states, contact, camera) on a downscaled picture; the full review stays available. Items a picture cannot show are returned as unverifiable, never "fixed".

### 5. Correct and escalate
Failure on non-spatial items: existing planner + redraw / masked repair. Failure on pose, camera or contact (or two plateaued redraws): render a staging picture by code from the plan (figures at planned positions, planned camera framing), use it as Picture 1 with the character sheets as Picture 2 through the existing transfer path. Hard budget on attempts; the best candidate is delivered with its unmet items listed, not hidden.

### 6. Learning
After a run: record (model, scene_type, plan item, failure type, what fixed it, whether review and owner agreed). A lesson is promoted to a rule only after it recurs or a fix is confirmed on a second picture. Promoted lessons feed the playbook defaults and the composer's anti-patterns, per model (Qwen, H3-Image). Builder decides whether to reuse `MistakeLedger` or a thin new store; either way the art path must read it.

### 7. Owner rating and the 90% number
Each delivered picture carries a one-tap rating (good / not good) and an optional reason tag (emotion, pose, camera, identity, style, other). Stored with the plan and iterations. The headline metric is the share of first-delivered pictures the owner rated good; also tracked: reviewer-vs-owner agreement and seconds per delivered picture.

## Phases (each shippable alone)

- **P0 - Baseline.** 20-30 briefs across fight / emotion / concept art, run today's pipeline, owner rates them, record timings (plan, draw, check). Sets the real starting number and the speed budget. Needs the owner's ratings.
- **P1 - Planner + playbooks + intake + fast path.** Engine function, HTTP route, MCP tool; UI later.
- **P2 - Plan-derived check + correction on the scene path.** Fast check mode; refine loop turned on for scene runs.
- **P3 - Staging-picture escalation.** Starts with a spike: does a code-drawn staging picture transfer pose/camera well enough? If not, fall back to using the best failed candidate or a reference the user supplies.
- **P4 - Learning and rating.** Wire the ledger into planner and composer; rating capture; reviewer-vs-owner agreement report.

## Tests and verification

Unit tests for plan validation, playbook defaults, plan-to-requirement mapping, escalation rules, lesson promotion. Real runs for every phase: look at the pictures, record timings, compare to owner ratings. A phase is not "done" on tests alone.

## Left to the builder

File layout (suggest `engine/original/scene_plan.py`, `engine/original/playbooks/`), extend-vs-wrap `ShotSpec`, exact action-state enums, how the staging picture is drawn, fast-check thresholds, ledger store choice, rating UI placement.

## Unproven / risks

- Planner quality and speed on `qwen3.5:9b`.
- Whether a code-drawn staging picture works with the transfer path.
- Whether a 9B reviewer agrees with the owner often enough to gate delivery; this is why P0 and P4 measure it.
- 90% is a target, not a promise; P0 sets the honest starting point.
