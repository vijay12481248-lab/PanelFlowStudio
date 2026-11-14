# Concept formula for Shorts / Reels

Evidence tiers: `[verified]` seen in this tree, `[research]` from web search (mostly marketing blogs, no primary YouTube source: treat as direction), `[hypothesis]` untested.

## What the research said (2026-11-14) `[research]`
- The first 2-3 seconds decide distribution; put the hook there. Emotion beats information in the opening. A face early helps retention.
- Most Shorts are watched muted at first: burned-in captions are essential.
- 15-30 s is the common sweet spot; comedy sketches with a twist ending were listed among top performers.
- No hard data found for marriage, study or phone-addiction jokes specifically. Instagram bonus payouts and AI-disclosure rules were not covered.
- YouTube Partner Program: 1,000 subscribers + 4,000 watch hours in 12 months, or 10M Shorts views in 90 days; thresholds double for new applicants from 2027-02-01 (vidIQ and press, confirm in YouTube Studio).
- Sources: vidIQ blog, Submagic, Miraflow, dev.to "Hook Engineering", exchange4media.

## The formula `[verified]` that it renders well, `[hypothesis]` that it retains
1. **Hook (scene 1, on screen 2.6 s in yellow Impact + spoken):** a POV, a universal claim, or a question the video answers. 3-7 words. Do not give away the twist.
2. **Three escalating beats (scenes 2-4):** each one funnier or more extreme than the last; one action per scene.
3. **Payoff (scene 5):** a twist ("It's Sunday"), a reversal (the lazy ones get the credit), or an emotional turn (mom stays awake all night).
4. **Comment bait** in the last line or a pinned comment: "tag someone who...", "which hour did you give up?".
5. Length 20-32 s, five scenes, one idea per reel, loops back to the hook.

## Writing the lines
- 8-14 words per line (about 3-6 s of Qwen3-TTS speech). A line over about 7 s makes the last shot hold a frozen frame (clip is ~6.5 s), so keep the CTA short.
- Spell numbers the way they should be spoken ("one percent", "five AM"); keep punctuation light, the captions strip it.
- Do not ask the picture to show numbers, letters or speech bubbles: the model cannot spell. Words come from captions and the title overlay only.

## Picture and motion text per scene
- `img` describes the still: who, doing what, where, the one prop that carries the joke. `chars` (repeated in every prompt) says what each character LOOKS like **and what they do not have** ("wife ... no mustache").
- `act` is the one thing that moves, in one sentence, no camera moves. H3 invents things around cheering or crowds (emoji faces appeared), so keep `act` literal.
- Emotional reels (warm music, soft palette) work with the same formula; the payoff is a quiet image, not a gag.

## The ten shipped concepts (2026-11-14), as worked examples
1 phone at 1% / 2 marriage AC war / 3 study plan vs reality / 4 "5 more minutes" scrolling / 5 mom radar (emotional) / 6 brain leaves in the exam / 7 snooze mafia (twist: Sunday) / 8 Wi-Fi down, family talks (wholesome) / 9 group project, one worker / 10 dad never said I love you (emotional). Full specs: `tools/reels/specs.py`; per-reel results and defects: `output/reels/` (git-ignored).

## Variety rule
Ten reels from one template can read as repetitive content to the platform. Vary hooks, palettes, one reel in three with a different structure, add a human element (the owner's own voice or a recurring character), and post a few a week.
