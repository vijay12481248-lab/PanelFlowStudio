# Narration Compiler — Design Spec

**Date:** 2026-10-30
**Status:** Draft for review
**Owner:** PanelFlow Studio engine
**Supersedes:** `VisualStoryEngine.narrate`, scene-level `ScriptAdapter` narration, `engine/story/narration.py` three-tier draft path, guessed timing in `engine/pipeline/semantic_sync.py`

---

## 1. Brief

### 1.1 Goal
Produce the best possible **recap-storyteller narration** for manga / manhwa / manhua / webtoon chapters (the style of channels such as Manhwa Fresh): one narrator retelling the chapter in their own words — condensed, punchy, with stakes and personality — that is **accurate to the panels** and **locked in sync** with the visuals.

### 1.2 Decisions (agreed with the owner)
| Topic | Decision |
|---|---|
| Narration style | Recap storyteller. Dialogue is paraphrased, never read out. Single narrator voice. |
| Speed vs quality | Quality first. Multiple model passes per chapter are acceptable (≈ 8–11 min for a 40-panel chapter, ≈ 35–50 min for a 300-panel webtoon). |
| Continuity | Per-series memory (**Series Bible**) carried across chapters. |
| Human review | Runs unattended; chapters failing quality gates park in a **review queue** in Narration Studio. Passing chapters render automatically. |
| Models | Local only, pluggable. Each step is assigned a model **role**; roles map to local models via config. Cloud is never required and is not supported in v1. |
| Approach | Staged **Narration Compiler**: small single-purpose steps, each with validated, cached, versioned artifacts and targeted repair. (Rejected: agent "director" loop — unreliable on 9B models; better single prompt — low quality ceiling.) |

### 1.3 Target environment
- GPU: NVIDIA RTX 5060 Ti, 16 GB VRAM. RAM: 31 GB. Windows 11.
- LLM/VLM: Ollama, `qwen3.5:9b` (vision-capable). TTS: Kokoro-82M. Local STT/alignment models added by this design.

### 1.4 Problems this design fixes (observed in production renders, Oct 2026)
1. Model invents claims not shown in the panel (e.g. "The giant mocks the attacker's weak cultivation level" on a panel of a winged fighter lunging).
2. Model skips panels or bundles 2–4 panels into one line, leaving panels to flash on screen.
3. The whole chapter script is produced by one large prompt; failures can only be fixed by regenerating everything.
4. Grounding is only checked after writing, by word overlap, and failures drop lines rather than repair them.
5. Fixed pacing and flat delivery: one TTS speed for every line, no planned pauses or emphasis.
6. Cuts are placed at clip starts, not on speech; no word-level timing exists.
7. No memory across chapters: names and context drift.

### 1.5 Success criteria (measured on the gold set, §8)
| Metric | Target |
|---|---|
| Grounded lines (judge) | ≥ 95 % |
| Story-panel coverage (own line) | ≥ 95 % |
| Hallucinated character names | 0 |
| Speech rate | 2.5–3.0 words/s |
| Cut cadence | median 1.8–3.5 s; no panel < 1.2 s or > 6 s |
| Sync: voice onset after its cut | 80–200 ms on ≥ 98 % of cuts |
| TTS word error rate (STT check) | ≤ 5 % median, ≤ 15 % per take |
| Preference vs current production narration | ≥ 55 % win rate (judge A/B, both orders) |

---

## 2. Architecture

### 2.1 Pipeline

```
 Panels + OCR ─▶ ① PERCEIVE ─▶ ② UNDERSTAND ─▶ ③ WRITE ─▶ ④ CRITIQUE ─▶ ⑤ REPAIR ─┐
                 per-panel      chapter beats    per-scene   rule checks + rewrite    │
                 facts (VLM)    + Series Bible   1 line per  LLM judges    failed     │
                                (read)           panel                     lines only ◀┘ (≤ 2 loops)
                                                                 │
                         ┌───────── gate fails ──────────────────┤ gate passes
                         ▼                                       ▼
                   Review Queue                     ⑥ PERFORM ─▶ ⑦ VOICE + ALIGN ─▶ ⑧ LOCK TIMELINE ─▶ motion/render (unchanged)
                   (Narration Studio)               delivery     TTS + word          cuts on word
                                                    marks        timestamps + STT QA timings, holds
                                                                                     │
                                                       on chapter approval ─────────▶ Series Bible update
```

### 2.2 Principles
1. **One job per step**, sized for a 9B model.
2. **Typed artifacts between steps** (Pydantic, JSON on disk). No step consumes free text.
3. **Content-addressed cache**: each step's output is keyed by hash(inputs, prompt version, model id, params). Steps are resumable, re-runnable alone, and diffable across versions.
4. **Facts flow forward only.** Steps ③–⑥ may only use facts from ① and ②. Critics enforce this.
5. **Local repair.** A failing line is rewritten; the chapter is never regenerated wholesale because of one line.
6. **No silent fabrication.** When a step cannot produce grounded output, the chapter goes to the review queue. Placeholder or canned text is never substituted.
7. **Role-based models.** Steps request a role (`vision`, `planner`, `writer`, `judge`, `stt`, `align`, `tts`), never a model name.

### 2.3 Module layout (new: `engine/narration/`)
```
engine/narration/
  artifacts.py          # Pydantic models for every artifact in §3 + id validators
  compiler.py           # NarrationCompiler: runs steps, cache, gate routing, run log
  cache.py              # content-addressed artifact cache under <workspace>/narration/
  bible/store.py        # SeriesBible load/save/versioning, proposal apply
  steps/perceive.py     # ①
  steps/understand.py   # ②
  steps/write.py        # ③
  steps/critique.py     # ④ (rules.py + judges.py)
  steps/repair.py       # ⑤
  steps/perform.py      # ⑥
  steps/voice.py        # ⑦ (tts, align, stt_qa)
  steps/timeline.py     # ⑧
  runtime/roles.py      # role → model routing from narration_models.yaml
  runtime/client.py     # OpenAI-compatible + Ollama adapter, JSON-schema constrained calls
  runtime/scheduler.py  # model-grouped execution, keep_alive, VRAM-aware batching
  prompts/<step>/<version>.md     # versioned prompt assets
  fewshot/<pack>.jsonl            # curated exemplar lines
  eval/                 # gold-set runner, metrics, HTML report
```
Each module has one purpose and is testable with a fake model client.

---

## 3. Artifacts (data contracts)

Stored under `<workspace>/narration/<run_id>/<artifact>.json`. All ids are validated against input artifacts before save; unknown ids are rejected.

### 3.1 PanelFacts (one per panel) — written by ①
| Field | Type | Notes |
|---|---|---|
| `panel_id` | str | required; must exist in project panels |
| `order` | int | reading order |
| `is_story` | bool | false for credits, ads, watermark-only, translator notes |
| `shot` | enum | wide / medium / close / insert |
| `characters_visible` | list[str] | Series Bible ids or `unknown_<n>` |
| `action` | str | one sentence, ≤ 20 words |
| `emotion` | str | dominant emotion |
| `dialogue` | list[{text, speaker_id?, speaker_confidence, region_id}] | `text` copied verbatim from OCR, never generated |
| `sfx` | list[str] | |
| `setting` | str | short |
| `importance` | int 1–5 | |
| `confidence` | float 0–1 | low values flagged for review |

### 3.2 SeriesBible (one per series, versioned) — read by ②, updated on approval
| Field | Notes |
|---|---|
| `characters[]` | id, canonical name, aliases, appearance cues, role, relationships, catchphrases, pronunciation |
| `locations[]` | id, name, description |
| `plot_so_far` | ≤ 150 words |
| `open_threads[]` | unresolved plot threads |
| `glossary` | power ranks, sects, techniques, with pronunciations |
| `narrator_voice` | style notes, banned phrases, signature transitions |
| `version`, `history[]` | each approved chapter appends a version with its applied proposals |

### 3.3 BeatSheet (one per chapter) — written by ②
- `scenes[]`: `scene_id`, `panel_range` (first/last panel id), `goal`, `conflict`, `turn`, `beats[]`
- `beats[]`: `beat_id`, `panel_ids`, `what_happens`, `function` (setup / escalate / reveal / payoff / cliffhanger), `intensity` 0–1
- `hook` (opening idea), `chapter_summary`, `bible_proposals[]` (new characters, renamed unknowns, plot update)

### 3.4 ScriptIR (one per chapter, revisioned) — written by ③, revised by ⑤
- `revision`, `parent_revision`, `changed_line_ids[]`
- `lines[]`: `line_id`, `panel_id` (exactly one), `text`, `facts_used[]` (refs into PanelFacts fields / beat ids), `kind` (hook / narration / paraphrase / transition / cliffhanger), `target_words`, `status` (draft / passed / repaired / fallback / needs_review)

### 3.5 CritiqueReport — written by ④
- per line: `checks[]` = {`rule`, `pass`, `severity` (block / warn), `reason`}, `scores` {grounded, clear, voice, flow}
- chapter: `coverage`, `pace_estimate`, `repetition`, `gate` (pass / repair / review), `gate_reasons[]`

### 3.6 PerformancePlan — written by ⑥
- per line: `emotion`, `energy` (low / med / high), `rate` (0.9–1.1), `pause_after_ms`, `emphasis_words[]`, `pronunciations{}`

### 3.7 VoiceTake (one per line) — written by ⑦
- `audio_path`, `duration`, `words[]` = {`text`, `start`, `end`}, `lead_ms`, `tail_ms`, `stt_text`, `wer`, `tts_model`, `voice_id`, `attempt`

### 3.8 LockedTimeline — written by ⑧
- panels: `panel_id`, `start`, `end`, `cut_reason` (line-start / beat-word / hold), `camera` {mode: scroll / zoom / push, params}
- clips: `line_id`, `start`, `end`, `audio_path`
- Projection: written into existing `story_editor_state` (`scenes[].layers[]`, `narration_clips[]`) and `VideoScript` so the editor, history and render remain unchanged.

---

## 4. Stages

### 4.1 ① PERCEIVE — per panel, role `vision`
- **Input:** panel crop, its OCR regions, previous panel's facts, Series Bible character cards (name + appearance cues).
- **Prompt:** fill a single-panel JSON form (who is visible, action, emotion, speaker for each bubble, shot, importance, is_story).
- **Rules:** dialogue text is copied from OCR, never generated; the model only assigns speakers. Unrecognised characters become `unknown_<n>`. Non-story classification happens here, once.
- **Execution:** parallel batches of 2–4 panels; ≈ 2–4 s per panel on the 9B model.
- **Reuse:** builds on the existing per-panel vision analysis in `VisualStoryEngine.analyze`.

### 4.2 ② UNDERSTAND — chapter, role `planner`
- **Window pass:** windows of ~30 panels with 5-panel overlap propose scenes and beats, each beat citing panel ids.
- **Merge pass:** stitches windows, resolves `unknown_<n>` against the bible, writes `hook`, `chapter_summary`, `bible_proposals`.
- **Deterministic checks:** every story panel in exactly one scene; beats in reading order; cited ids exist. On failure: one re-ask with the violation, then review queue.
- **Reuse:** builds on `SectionPlanner` windowing.

### 4.3 ③ WRITE — per scene, role `writer`
- **Input:** scene beats, PanelFacts for its panels, last 3 written lines, bible narrator voice, few-shot pack, line budget.
- **Output:** exactly one line per story panel, in order, each with `panel_id` and `facts_used`.
- **Pacing policy:** 5–10 words per line (≈ 2.5 s at rate 1.0); scene-opening lines may carry a transition.
- **Style:** few-shot pack of 6–10 curated exemplar lines; paraphrase dialogue ("He calls the master a fool"), never quote; stakes and transitions at scene boundaries.
- **Hook and cliffhanger:** separate prompts generate 3 candidates each; ④ picks via pairwise judging.
- **Structural check:** code verifies count, order, ids; one re-ask on failure.

### 4.4 ④ CRITIQUE — rules + judges
- **Rule checks (code):** one line per story panel in order; word budget; banned phrases ("in this panel", "the image shows", …); names ∈ bible ∪ OCR; no unresolved `unknown_<n>` in text; no repeated sentence openers within 3 lines; adjacent-line similarity ≤ 0.8.
- **Judge checks (role `judge`, temperature 0):** one yes/no question per line per check, each with a one-sentence reason:
  - Grounded — "Is every claim in this line supported by these facts?" (judge sees only the line's facts)
  - Clear — "Would a viewer who hasn't read the manga follow this?"
  - Voice — "Does this match the narrator style notes?"
  - Flow — "Does it follow naturally from the previous line?"
- **Pairwise judging** for hook / cliffhanger candidates and for eval preference, run in both orders to cancel position bias.
- **Severity:** `block` = count/order, word budget, banned phrase, unknown name, unresolved `unknown_<n>`, and every judge check; `warn` = repeated openers and adjacent-line similarity (reported, sent to repair once, never gate on their own).
- **Gate:** any line failing a `block` check → repair. After repair, > 15 % of lines still failing a `block` check → review queue. Otherwise pass.

### 4.5 ⑤ REPAIR — failed lines only, role `writer`
- **Input:** original line, failed checks with reasons, its facts, neighbouring lines.
- **Loop:** at most 2 repair rounds, re-critiquing only changed lines.
- **Fallback:** a line still failing becomes a fact-only sentence built in code from PanelFacts ("<Character> <action>.") with `status = fallback`, or the chapter goes to review if fallbacks exceed 10 % of lines.
- Each round writes a new ScriptIR revision with `changed_line_ids`.

### 4.6 ⑥ PERFORM — per scene, role `writer`
- Marks per line: emotion, energy, emphasis words, pause after.
- Code maps marks to TTS parameters: rate 0.9–1.1; pause 150–350 ms between lines, 500–800 ms at scene turns and before reveals; tension lines slightly faster, reveals slightly slower.
- Pronunciations come from the bible glossary.

### 4.7 ⑦ VOICE + ALIGN — roles `tts`, `align`, `stt`
- Kokoro synthesises each line separately (regenerable alone).
- Forced alignment (local CTC aligner, wav2vec2 / whisper-family) yields word timestamps.
- Leading and trailing silence measured and normalised to 80 ms.
- STT QA: local faster-whisper transcribes each take; WER vs text > 15 % → regenerate (max 2), then flag for review.

### 4.8 ⑧ LOCK TIMELINE — code only
- Default cut: first word onset − 120 ms (picture leads voice, editor "L-cut").
- Beat-word cut: when the line's facts mark a reveal word, cut may land on that word's onset instead.
- Holds: each panel ≥ 1.2 s, ≤ 6 s. Panels without their own line hold during a narration pause (current behaviour in `synchronize_narration`, preserved).
- Camera: tall panels scroll ≤ 0.2 screens/s; wide panels slow zoom-in; reveal beats get a slight push-in. Hard cuts between panels.
- Writes `story_editor_state` and `VideoScript`; motion and render stages are unchanged.

---

## 5. Local model runtime

### 5.1 Role routing
`narration_models.yaml` (also editable in Settings):

| Role | Steps | Default | Params |
|---|---|---|---|
| `vision` | ① | `qwen3.5:9b` | temperature 0.1 |
| `planner` | ② | `qwen3.5:9b` | temperature 0.2 |
| `writer` | ③ ⑤ ⑥ | `qwen3.5:9b` | temperature 0.7, top_p 0.9 |
| `judge` | ④ | `qwen3.5:9b` (prefer a different 7–9B family when available) | temperature 0 |
| `stt` | ⑦ | faster-whisper `small` | |
| `align` | ⑦ | wav2vec2 CTC aligner | |
| `tts` | ⑦ | Kokoro-82M | |

### 5.2 Client
- Adapters: Ollama (v1), then LM Studio / llama.cpp-server / vLLM via an OpenAI-compatible client. Backends are configuration, not code changes in steps.
- Built on existing `engine/llm/registry` and `engine/ai_gateway`.
- Every call passes a JSON schema (Ollama `format`) for constrained decoding, then Pydantic validation; on failure one retry including the validation error; then the step fails cleanly.

### 5.3 Prompts as assets
- `prompts/<step>/<version>.md` with variables; few-shot packs in `fewshot/*.jsonl`.
- The prompt hash is part of the cache key, enabling A/B of prompt versions against cached outputs.

### 5.4 Scheduling on 16 GB VRAM
- One heavy model loaded at a time. The scheduler groups work by model (all ① for a chapter, then ②, ③ …).
- `keep_alive` holds a model until its group finishes, then unloads.
- Kokoro + aligner + STT (≈ 3 GB) run in ⑦ after the LLM is unloaded.
- Concurrency: ① 2–4 parallel requests; text steps sequential.
- OOM: unload all, retry with halved batch size.

### 5.5 Context budgets
- Per-step token budget; no prompt exceeds ≈ 6k tokens.
- PanelFacts are compacted for ② and ③; `plot_so_far` capped at 150 words; ② windowed.

### 5.6 Expected timings (40-panel chapter, 9B model)
① 2–3 min · ② 1 min · ③ 1–2 min · ④ 1–2 min · ⑤ 0–1 min · ⑥ 0.5 min · ⑦ 1–2 min → **≈ 8–11 min**. Scales roughly linearly with panel count.

---

## 6. Quality system

### 6.1 Gold set
`fixtures/narration_gold/`: ~10 chapters (mix of manhua, manhwa, webtoon; 40–300 panels) with panels, OCR, hand-corrected PanelFacts, and one approved reference script each. Frozen; changed only by deliberate review.

### 6.2 `narration eval`
CLI that runs the compiler on the gold set and reports the §1.5 metrics as JSON + an HTML report. The grounding judge's agreement with the owner is calibrated once by spot-checking 20 lines.

### 6.3 Regression gate
A prompt or model change merges only if, on the gold set, no metric regresses beyond tolerance and the judge preference win rate vs the previous version is ≥ 55 %.

### 6.4 Review queue (Narration Studio)
- Chapters failing the gate are parked with reasons ("3 lines ungrounded", "pace too fast in scene 4").
- Failing lines are shown next to their panel, the facts they used, and the judge's reason.
- Per line: accept, edit, regenerate with a hint, or use the fact-only fallback.
- Approval releases the chapter to ⑥–⑧ and render, and applies its bible proposals.

### 6.5 Learning loop
- Owner edits and approvals are stored as preference pairs (before / after).
- Used to refresh few-shot packs and extend bible style notes / banned phrases.
- Data is retained for an optional future LoRA fine-tune of the writer (out of scope for v1).

### 6.6 Observability
- `run.json` per chapter run: per-step model, prompt version, tokens, timings, cache hits, gate decisions.
- Narration Studio run inspector: browse each step's input and output for a chapter, to trace any line to the step and prompt that produced it.

---

## 7. Integration and migration

- **Autopilot:** `story` + `script` + `audio` stages collapse into one `narration` stage that invokes `NarrationCompiler`. `motion` and `render` are unchanged; they read `story_editor_state`.
- **Narration Studio:** gains review queue, run inspector, per-line actions. The three-tier draft path in `engine/story/narration.py` is removed once the compiler covers its use.
- **Kept and reused:** `VisualStoryEngine.analyze` and `SectionPlanner` become the basis of ① and ②; `synchronize_narration` hold rules move into ⑧; composer camera/scroll behaviour is unchanged.
- **Retired:** `VisualStoryEngine.narrate`, `ScriptAdapter` scene narration, `semantic_sync` clip-level guessing (replaced by word-level ⑧).
- **Feature flag:** `narration.engine = legacy | compiler`, default `legacy` until the compiler beats legacy on the gold set; then default flips; legacy deleted one release later.
- **Data:** existing projects keep their current scripts and timelines. Running the compiler on a project writes a new run; previous `VideoScript` rows are preserved as prior versions.

---

## 8. Error handling

| Failure | Behaviour |
|---|---|
| Model timeout | 2 retries with backoff, then step fails |
| Invalid JSON / schema | 1 retry with the validation error in the prompt, then step fails |
| Ollama unreachable | Batch queue pauses (not every chapter fails); resumes when healthy |
| GPU OOM | Unload models, retry with halved batch |
| Step cannot produce grounded output | Chapter → review queue with reason; never fabricated text |
| Crash / cancel | Resume from last completed step via cache |
| TTS take fails STT QA twice | Line flagged; chapter → review if > 10 % of lines flagged |

---

## 9. Testing

- **Unit:** each step with a scripted fake model client (no GPU): schema validation, rule checks, gate routing, repair loop bounds, fallback construction, hold maths, alignment-to-cut maths, scheduler grouping.
- **Contract:** every artifact round-trips its schema; unknown ids rejected; ScriptIR revision lineage valid.
- **Golden run:** one small gold chapter end-to-end with recorded model responses (cassettes); deterministic, offline, runs in CI.
- **Eval:** full gold set with real local models; manual or nightly; blocks regressions per §6.3.

---

## 10. Delivery phases

Each phase gets its own implementation plan and ships behind the feature flag.

| Phase | Scope | Exit criteria |
|---|---|---|
| **P1 Foundation + Understand** | artifacts, cache, runtime (roles, client, scheduler), run log; ① PERCEIVE; ② UNDERSTAND; Series Bible store | PanelFacts + BeatSheet produced for 3 gold chapters; contract + unit tests green |
| **P2 Write + Quality** | ③ WRITE, ④ CRITIQUE, ⑤ REPAIR, review-queue backend; gold set; `narration eval` | grounding ≥ 95 %, coverage ≥ 95 % on gold set |
| **P3 Voice + Sync** | ⑥ PERFORM, ⑦ VOICE + ALIGN + STT QA, ⑧ LOCK TIMELINE; autopilot integration behind flag | sync and pace targets met; full chapter renders via compiler |
| **P4 Studio + Rollout** | review UI, run inspector, learning loop (few-shot refresh); flip default; remove legacy | preference ≥ 55 % vs legacy on gold set; owner sign-off |

---

## 11. Out of scope (v1)
- Multiple character voices / faithful dub mode.
- LoRA or other fine-tuning.
- Cloud models.
- Translation or non-English narration.

## 12. Risks
| Risk | Mitigation |
|---|---|
| Same-model judge shares the writer's blind spots | Judge sees only the line's facts; owner calibration of 20 lines; swap judge to a different local model family when available |
| 9B vision misidentifies characters | `unknown_<n>` + bible appearance cues + merge-pass resolution; review queue for low confidence |
| Alignment errors on fantasy names | Bible pronunciations to TTS; STT QA; fall back to clip-start cut (current behaviour) when alignment confidence is low |
| Runtime too slow for long webtoons | Overnight batch queue; caching makes reruns cheap; windowed ② |
| Gold set too small to detect regressions | Start at 10 chapters; grow from review-queue approvals |
