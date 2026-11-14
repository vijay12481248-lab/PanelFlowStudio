# Scene review page with two cooperating vision judges - design

Status: DRAFT for owner approval (2026-11-14). Nothing is built. Builds on `docs/SCENE_DIRECTOR.md` (the Scene Director already makes and checks pictures).

## Intent and why

The Scene Director produces pictures, but nobody can yet say how often they match what the owner imagined, and the system learns only from its own noisy judge. The owner wants:

1. Right after a picture is made, an eye-catching, hard-to-skip prompt to review it.
2. The analysis ("what is good, what went wrong, camera, confidence") written by vision models, not typed by the owner.
3. The owner only decides how much they liked it (a percentage), and either agrees with the AI's review or adds their own comments.
4. Everything stored in a database that other models can query, so the system gets smarter from real verdicts.
5. Two vision models that communicate to reach one result.

## Goals

- **Two judges, one result.** `qwen3.5:9b` (Ollama) and Qwen3-VL 8B (already on disk in ComfyUI, `TextGenerate` node) each judge the picture blind. Agreed items are accepted; each disagreement gets ONE structured cross-check (approach B below); what is still disputed is shown as low confidence for the owner to decide.
- **A review page in the desktop app** (a new screen): brief and plan, the picture, the AI review with the cross-check shown, and the owner's panel (liked %, agree with AI / my own comments, good and wrong tags, note).
- **A visible, persistent review request**: a banner and a count badge on every screen (and in the existing notification bell) until the picture is reviewed. Not a blocking pop-up.
- **A knowledge base in the existing SQLite database**: one row per picture with the plan, system attempts, both judges' answers, the cross-check, the final per-item verdicts and confidence, and the owner's feedback; JSON columns for the nested parts; full-text search over notes and briefs.
- **Use it**: an API and an MCP query tool (other models can ask "what fails most for fights?"); a report of how often each judge agrees with the owner; the Scene Director's lessons are fed from this table.

## Non-goals

- No vector database in v1 (see Approaches: storage). No free-form multi-round chat between the models. No computer-control agent: the "workflow" is an ordinary background job. No auto-publishing.
- No change to the picture-making path (planner, prompt, Qwen drawing) except where it reads lessons.

## Anti-goals (a failure even if it "works")

- The two models flattering each other: agreeing because the other said so, not because they looked.
- A second judge that makes every review much slower for no gain in accuracy.
- A review page the owner starts ignoring because it nags or takes too many clicks.
- Owner feedback that cannot be tied back to the exact plan, prompt, picture and judge answers that produced it.

## Constraints

- RTX 5060 Ti 16 GB: ComfyUI and Ollama together use ~13 GB while drawing; the two judges run one after the other, never together with a draw.
- `TextGenerate` with Qwen3-VL 8B works only when ComfyUI runs with `--disable-dynamic-vram` (measured; drawing still works, 6.0 s per 1344x768 picture). The app starts ComfyUI itself in `engine/system/setup.py:509`.
- Measured so far: Qwen3-VL 8B ~4 s per picture (30 s first load); on 3 known pictures it read the camera right 2 of 3, `qwen3.5:9b` 3 of 3. The yes/no check is too agreeable (a level-camera fight accepted as "low angle"); pictures must not be shrunk before judging.
- The desktop app has no OS notification plugin (no `notification` in `package.json`, `Cargo.toml` or `tauri.conf.json`); it does have `ErrorNotificationBell` in `AppShell`.
- Downloads and new dependencies need the owner's approval first (AGENTS.md).

## Approaches considered

Judge cooperation: **A** vote only (fast, no talking); **B** structured cross-check, one extra round only for disagreements, each model re-looks with a narrow question, the other's claim and a request for visible evidence (chosen by the owner); **C** free chat over several rounds (slow, models give in to each other, hard to log).
Storage: **relational SQLite** (chosen) vs a vector database. The data is structured (scene type, camera, failure kind, confidence, percent liked) and a few hundred to a few thousand rows; SQL plus FTS5 answers it, and a vector store would need an embedding model download and another service. Revisit with `sqlite-vec` when "find scenes similar to this one" is a real need and there are thousands of rows.

## Design

### 1. The cross-check judge
Input: picture + plan. Judge output (both models, same JSON shape): camera angle, number of people, each person's action, side of each person, plus a one-line reason and where in the picture the evidence is. Round 1 is blind to the other model. Items where the two differ go to round 2: each model gets the picture, only the disputed question, the other model's answer and evidence, and is asked to answer again and point to what it sees. Result per item: `agreed`, `resolved` (both converge), or `disputed` (low confidence, owner decides). A model that flips toward the other without giving new evidence is counted as a suspect flip (logged, shown, and measured). Confidence per item: agreed 0.9, resolved 0.7, disputed 0.3; the existing deterministic witnesses (figure count, side from the reported box) still apply on top.
Gate before it ships: on labelled pictures it must beat each judge alone and the plain vote on agreement with the labels; otherwise the simpler judge stays. Labels start with the agent's own reading of known pictures and grow from the owner's feedback.

### 2. Pipeline and notification
After a scene picture is delivered, a background job runs the two judges in turn (Ollama model, then ComfyUI Qwen3-VL), stores the analysis, and raises a "review waiting" event. The app shows a banner (colour, count) on every screen, a badge on the bell, and the item at the top of the review page; it stays until the owner submits or explicitly dismisses it. An OS toast needs a new Tauri plugin dependency: a call for the owner, not v1.

### 3. Storage
New tables in the app database (SQLAlchemy models plus a numbered `.sql` migration like `engine/database/migrations/`): `scene_runs` (project, brief, plan JSON, picture path, attempts and system review JSON, created), `scene_analyses` (run, judge name, round, raw answers JSON, per-item verdict and confidence, suspect flips), `scene_feedback` (run, liked 0-100, agrees_with_ai, good_tags, wrong_tags, note, created). FTS5 virtual table over brief and notes. The earlier ratings file (`scene_ratings.json`) and the lessons ledger are migrated or read from here.

### 4. The review page
One screen: top, brief and the plan in plain words (editable, then regenerate); middle, the picture and the AI review (per-item agreed / resolved / disputed with both models' wording, confidence, what the system missed); bottom, the owner's panel: liked slider, "I agree with the AI" or free comments, good and wrong tag chips (emotion, pose, camera, identity, style, other plus free text), submit. A queue of unreviewed pictures at the side.

### 5. Using the knowledge
`GET` and MCP query endpoints: failures by scene type / model / camera, owner liked % by style, judge-vs-owner agreement, disputed items that the owner resolved. The Scene Director reads promoted lessons from the table (a failure the owner also marked wrong counts double; a failure the owner called fine is not a lesson).

## Phases (each shippable alone)

- **P1 Cross-check engine + measurement.** Both judges, the B protocol, on labelled pictures; results written up; gate decides.
- **P2 Storage + API + MCP query.**
- **P3 Desktop review page + banner/badge/bell.**
- **P4 Feedback loop**: lessons from the table, judge-accuracy report, per-judge weights.

## Calls I made (the owner can change them)

- Persist `--disable-dynamic-vram` in `engine/system/setup.py` so the app starts ComfyUI the way the second judge needs.
- No OS toast in v1 (new dependency); in-app banner, badge and bell instead.
- Judges run sequentially, second judge only inside the review job, never during drawing.
- Labels for the gate come from my own reading of known pictures until the owner's feedback exists.

## Left to the builder

Table column details, JSON shapes, exact prompts for the cross-check, the page's layout and styling, tag lists, the order of judges, retry and timeout behaviour.

## Risks / unproven

Whether the second look fixes wrong answers or just spreads them; whether Qwen3-VL 8B adds accuracy or only time; the extra seconds per review; ComfyUI memory behaviour with the flag over a long session.
