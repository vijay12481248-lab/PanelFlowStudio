# PanelFlow Studio — Video Script Adaptation (Layer C)

## 1. Overview & Role of Layer C

The **Video Script Adaptation Layer (Layer C)** translates the semantic facts of the **Narrative IR (Layer B)** into a formatted, timed, spoken script suitable for video synthesis.

Layer C content represents *presentation choices* (pacing, rhythm, narrator phrasing, emotion guidance, camera movement intents). It is strictly segregated from source truth (Layer A) and narrative interpretation (Layer B).

---

## 2. Adaptation Profiles

PanelFlow Studio provides four distinct adaptation profiles:

| Profile | Target Audience / Use Case | Adaptation Behavior |
|---------|---------------------------|---------------------|
| `FAITHFUL` | Manga purists, direct visual translations | Preserves 100% of corrected source dialogue verbatim. Generates minimal establishing narrator lines only where scene transitions require context. |
| `CONDENSED` | Fast-paced short-form reels, high-action summaries | Prunes filler dialogue, trims repetitive lines, accelerates transition times between story beats. |
| `DRAMATIC_NARRATION` | Cinematic motion comics, YouTube audiobooks | Pairs character dialogue with expressive third-person dramatic narrator commentary establishing mood, tension, and stakes. |
| `ACCESSIBLE_RECAP` | Visually impaired audiences, comprehensive recaps | Supplements dialogue with descriptive audio narration explaining visual actions, character expressions, and setting details. |

---

## 3. Pacing & Duration Estimation Model

Timing in PanelFlow Studio is deterministic, calculated via word-count cadence with punctuation adjustments:

$$\text{Base Words-Per-Minute (WPM)} = \begin{cases} 150 \text{ WPM} & \text{if Narrator} \\ 135 \text{ WPM} & \text{if Character Dialogue} \end{cases}$$

$$\text{Word Duration} = \frac{\text{Word Count}}{\text{WPM} / 60}$$

### Cadence Punctuation Adjustments:
- Comma (`,`), semicolon (`;`): $+0.20\text{s}$ pause
- Period (`.`), exclamation mark (`!`), question mark (`?`): $+0.40\text{s}$ pause
- Ellipsis (`...`): $+0.60\text{s}$ dramatic pause
- Inter-segment pause: $+0.30\text{s}$ default breath pause

### Duration Bounds:
- Minimum dialogue clamp: $1.20\text{s}$
- Minimum narration clamp: $1.50\text{s}$

---

## 4. Faithfulness Validator

Every generated or edited script segment is audited by the `ScriptFaithfulnessValidator`:

- `SUPPORTED` (Green): Every phrase is grounded directly in source text regions or approved beat summaries; referenced panels and speakers exist in the project registry.
- `WEAKLY_SUPPORTED` (Yellow): Dialogue matches source meaning but contains creative rephrasing or minor inferred details.
- `UNSUPPORTED` (Red): The statement introduces character actions, dialogue, or events with zero grounding in source panels or text regions (hallucination).

The overall **Coverage Score** is computed as:
$$\text{Coverage Score} = \frac{\text{Supported} + 0.5 \times \text{Weakly Supported}}{\text{Total Segments}}$$

---

## 5. Script Approval Gate

- Advancing to `SCRIPT_APPROVED` (`POST /api/projects/{id}/scripts/{id}/approve`) finalizes the script for downstream motion planning.
- **Strict Guardrail**: No TTS generation, voice cloning, audio synthesis, or FFmpeg rendering takes place in Milestone 4.
