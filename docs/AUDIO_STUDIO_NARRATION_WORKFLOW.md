# Audio Studio — Autonomous Narration Workflow

> Architecture for the end-to-end workflow the Audio Studio guides a story through.
> Written against the engine as it exists today (`engine/narration/`).

## Goal

A story enters the Audio Studio and comes out as a narrated, reviewed, approved
audio timeline — with the system pausing for the owner only where a decision is
genuinely theirs.

## The workflow

### 1. Choose the source and scope

Select an approved story, chapter, or scene. The system loads its script,
characters, scene order, and relevant visual context.

### 2. Prepare the story brief

The Story Analyst builds a structured brief: what happens, who is speaking, what
the audience should understand, and where the important reveals or emotional
shifts occur. Each conclusion links back to the relevant story or scene evidence.
Uncertain details stay marked as uncertain.

### 3. Draft narration and direction

The Narration Director creates narration segments and a chapter-level emotional
arc. Each segment gets a proposed speaker, intent, delivery direction, pause
plan, emphasis, and target duration. This is where the system decides *how the
story should be told*, not just which emotion label to apply.

### 4. Check and resolve the cast

The Casting Assistant maps characters to approved voice profiles. It favors your
voice for the narrator when configured, maintains existing assignments, and flags
characters that lack a suitable voice. It can recommend a profile, but should not
silently replace a creator's assignment.

### 5. Generate takes through durable jobs

The system submits approved synthesis requests to PanelFlow's job manager. Each
generated take records its script, direction, voice, provider, and model
revisions. If a job fails or becomes outdated, the current approved take remains
available.

### 6. Review and repair

Audio QA checks intelligibility, pronunciation, duration, clipping, silence, and
timing. The Audio Reviewer can suggest specific repairs, such as adjusting a
pronunciation or regenerating a line with a slower pace. You can audition
alternate takes in context with neighboring lines.

### 7. Approve and assemble

Approved takes are placed into the audio timeline, then reviewed alongside music
and sound effects. A readiness report identifies remaining issues before the
project moves to rendering.

### Stop points

The system pauses for your input when:

- the story brief is uncertain,
- a new or cloned voice needs approval,
- a proposed casting change affects an existing assignment, or
- no take passes the configured quality checks.

Routine generation and repair continue automatically within your settings.

---

## How this maps onto the engine today

The narration compiler already runs an eight-stage pipeline over a chapter. The
workflow above is that pipeline, re-aimed at the Audio Studio's seven steps.

| Workflow step | Engine stage today | Artifact |
| --- | --- | --- |
| 1. Choose source and scope | `inputs.py` | `ChapterInputs` |
| 2. Story brief | ② UNDERSTAND | `BeatSheet` |
| 3. Narration and direction | ③ WRITE + ⑥ PERFORM | `ScriptIR` + `PerformancePlan` |
| 4. Check and resolve the cast | `casting.py` | `CastPlan` |
| 5. Generate takes through jobs | ⑦ VOICE | `VoiceTake` |
| 6. Review and repair | ④⑤ CRITIQUE + REPAIR, `review.py` | `CritiqueReport` + `ReviewItem` |
| 7. Approve and assemble | ⑧ TIMELINE + `project.py` | `LockedTimeline` + `AudioTimelineRecord` |

### What already works

- **Grounding.** Every line cites the facts it drew on (`facts_used`), and the
  rules block a line that invents a name, a place, or an event.
- **Scene structure.** The brief is windowed, stitched in code, and re-asked
  until the scene and beat ranges tile the chapter exactly.
- **Delivery direction.** `LineMarks` carries emotion, energy, rate, pause,
  emphasis and the intent of the line, mapped in code to a TTS rate and a pause.
- **Speech verification.** Every take is transcribed and scored; a line that
  fails the speech check is retried slower, then parked for review.
- **Approval.** `review.py` can edit, accept, fall back and regenerate a line,
  and refuses to approve while a line is still open.
- **Assembly.** The locked timeline is projected into the story editor state and
  a draft audio timeline that the real `approve_audio` accepts.

### What the workflow has added

**The speaker and the cast (steps 3 and 4).** A line names who reads it. The
writer proposes a speaker from the characters present, and only a line that
quotes a character may be read in their voice. The Casting Assistant maps those
characters to approved voice profiles: it keeps every assignment the owner
already made, recommends a voice that fits the character's pronouns without
applying it, and flags a character that has no suitable voice. The voice step
then reads each line with the voice of its speaker.

**The take ledger (step 5).** Every take carries the script revision, the
direction revision, the cast profile and the provider it came from, so a take
that no longer matches its line is recognised as outdated instead of being
mistaken for the current one.

**The audio QA (step 6).** Every take is checked for intelligibility,
pronunciation, duration, clipping, silence and timing. Each failed check names
the repair that would fix it: regenerate the line at a slower pace, adjust the
pronunciation in the series bible, regenerate at a lower level, trim the
silence around the take.

### What the workflow still needs

**Gap B — an uncertain brief (stop point 1).** `Understand` already raises
`NeedsReview` when the model cannot produce a coherent beat sheet, but a brief
can be *coherent and still uncertain* — a reveal the analyst inferred rather than
read. The brief needs to carry its own confidence and cite the evidence per
conclusion, so "uncertain" is visible rather than inferred.

### The readiness report (step 7)

`sync_metrics` already computes the sync targets. The readiness report is that
plus what is still open: lines awaiting review, characters without a voice,
takes that failed QA, and the BGM/SFX state.

---

## Milestones

Each milestone lands with tests and keeps the pipeline runnable.

1. ~~**Speaker on the line.**~~ A line names its speaker. The writer proposes
   the speaker; the rules check it against the bible. Cast dialogue stays a
   paraphrase in the recap, so this is a field first and a behaviour second.
2. ~~**The voice catalog and the cast.**~~ Approved voice profiles, an
   assignment map stored beside the bible, and the casting assistant that
   resolves it: narrator preference, existing assignments kept, missing voices
   flagged, a recommendation never applied on its own.
3. ~~**The take ledger.**~~ Every take records the script revision, the
   direction revision, the voice profile and the provider. An outdated take is
   detected and the approved take survives.
4. ~~**Audio QA.**~~ The full check set, with reviewer suggestions and an auditable
   QA report per take.
5. **The readiness report.** What is still open, before rendering.
6. **Stop points.** The brief's uncertainty, the voice approval and the casting
   change become explicit review items instead of silent behaviour.

## Invariants

- The narrator voice you configure is the default for the narrator.
- A voice assignment you made is never replaced without asking.
- A failed or outdated take never removes the take you approved.
- Every claim in the brief points back to the story evidence it came from.
- Nothing in the workflow falls back to the cloud or to a mock.
