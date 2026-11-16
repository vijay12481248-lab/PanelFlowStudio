# Audience intelligence - phases 0-2 (2026-11-16)

Code: `engine/intel/` (store, metrics), `tools/intel/` (smoke test, ingest). Data: `%LOCALAPPDATA%\PanelFlow Studio\intel.db`, `output/intel/channels.csv`.
All vidIQ numbers were retrieved 2026-11-16 through the vidIQ connector (140 credits; 100 spent, ledger in `credit_ledger`). Nothing was downloaded or scraped.

## Phase 0 - measured capability (RTX 5060 Ti 16 GB, one run each, seed 7, `tools/intel/smoke_models.py`)
| Model (workflow) | Result | Time | Peak VRAM | Notes |
|---|---|---|---|---|
| FLUX.2 klein 4B (`flux2_klein_4b`) | 768x1344 picture, clean, identity-simple cartoon | 11.2 s | 15.4 GB | Apache-2.0; up to 4 reference pictures (`_ref`). Hand drawn as a black mitten (minor). |
| MiniMax H3 Image (`minimax_h3_image_edit`, no picture) | 768x1344, richer shading | 17.5 s | 15.6 GB | Licence excludes US/EU/UK/South Korea. |
| FastH3 image-to-video (`fastvideo_h3_i2v`) | 6.5 s clip, 19 fps, 480x864, with audio track | 92 s | 15.7 GB | Identity, wave and scarf motion held across 8 sampled frames; small grass tufts appear late (invented detail). Asked 480x832, got 864 (multiple-of-32 rounding). |
| Wan 2.1 i2v 14B (`wan21_14b_i2v`) | see below | | | |

The card is effectively full during every stage: one model family at a time (as the repo already does). LTX 2.3: no weights on disk, only ComfyUI template files; treated as not installed.
ACE-Step in this repo is 1.5, not 2.1. Kokoro was not found in the repo (voice is Qwen3-TTS per the shorts skill). Neither audio model was run today.

## Phase 1 - store
`metrics.py`: views-to-subscribers, summary (mean, median, top-10 mean, share over 100K/500K/1M/10M), outlier score. Unknown stays NULL, never 0. `store.py`: SQLite snapshots with `retrieved_at` + `source` on every metric row, credit ledger. 4 unit tests pass (`tests/unit/test_intel.py`).

## Phase 2 - what the data says
### Reference channel @Anim_legends98 ("Anim Legends")
2,980 subscribers, 1,572,963 lifetime views, 114 videos, India. One Short ("Realistic Lightning Animation", 2023, 8 s) has 1,410,145 views = **89.6% of the channel's lifetime views**. Among its 50 most-viewed Shorts the median is 2,058 views (this list is the top 50, so the true median is lower). It is stickman power fights, often Goku/Naruto fan content. Verdict: an isolated hit, not a repeatable model. Use it for the format (very short stickman power animation), not as proof of demand.

### Channels (150 unique, `output/intel/channels.csv`)
From three vidIQ channel searches (stickman Shorts; AI fantasy animation stories; breakout animation Shorts). Lifetime average views per video is used as the sort, so channels with 1-3 videos are noise (e.g. one with 1 video). Video-level data was pulled for four channels only (credit limit):

| Channel | Subs | Videos listed | Median views | Top video | Top / median | Top video views per sub | Videos >1M |
|---|---:|---:|---:|---:|---:|---:|---:|
| meowneow (AI cat stories) | 1.56M | 50 of 77 | 2.2M | 204M | 92x | 131 | 72% |
| Rukmini Verse (anime montage) | 448K | 50 | 58K | 30M | 523x | 68 | 24% |
| Bozoeys (fan-IP doll stories) | 49.7K | 26 | 38K | 20.3M | 528x | 409 | 19% |
| Anim Legends (reference) | 2,980 | 50 | 2.1K | 1.41M | 685x | 473 | 2% |

Lists are each channel's most-viewed uploads, so medians are biased upward. A fifth channel returned no Shorts (5 credits spent).

### Outliers (vidIQ breakout score = views vs the channel's typical video; Shorts, 6 niche queries, 30 each)
- **Small channels do hit millions**: 3K-30K-subscriber channels with 1-8M-view Shorts appear in every query. Short loops (6-36 s) dominate the satisfying/surreal group.
- **Most stickman/funny/transformation hits depend on someone else's IP**: Alan Becker fan edits, Roblox (Steal an Egg, Dandy's World), Sprunki, Rumi/KPop Demon Hunters, anime montages. Not usable for an original channel (rule 11).
- **Original-IP examples with real numbers**: "Mother of the year" animation (151K subs, 19.2M views); Ghibli-style emotional story "The Painted Frame" (61.9K subs, 9.5M views, 1:52); "Be Kind" animal-loyalty animation (26K subs, 4.3M); "Kindness Always Comes Back" (10K subs, 1.1M); "The Wizard Who Married a Goose" (85.8K subs, 3.2M, 7.3% engagement).
- **Satisfying/physics loops**: "How Pencil Sharpeners Work" 8M views on 16.9K subs; bowling-ball shatter loops 3.5-7M; 6-second table-drop loop 7.8M. These are 3D/physics renders, not AI video; our stack has no 3D engine, so feasibility is low unless done as AI-video imitation.

### What one video looks like (vidIQ watched it; 10 credits)
"The Painted Frame" (9.5M views): 112 s, Ghibli-style 2D, 2 characters, about 35 cuts, no dialogue, foley + acoustic score, calm opening, storm turn at 0:43, rescue, reunion ending. Pacing is about one cut every 3 s. 112 s of that is far beyond one H3 clip (4-15 s), so it needs chained clips and about 35 pictures.

### Audience comments (vidIQ comment_insights, sampled, indexed comments only)
- Animation Shorts: 240 threads from 15 channels. Strongest clusters are small: requests for specific existing characters/cameos (derivative), "more / part 2" (2 threads on one channel), nothing under pain points.
- AI stories: 48 threads from 5 channels. "Next part / more please" (10 threads, 5 channels, 161 likes) and "which AI tool / how do you join scenes" (4 threads, 2 channels).
Both samples are thin. They support series continuation and cliffhangers as an audience wish; they do not support any claim about complaints.

### Hypotheses (not proven; each has at least two channels behind it unless stated)
1. Recurring original characters + escalating slapstick, 25-58 s (meowneow: 36 of 50 listed Shorts over 1M). Strongest and most repeatable; fits our tools.
2. Emotional wordless story with a reversal (Painted Frame, Be Kind, Kindness Always Comes Back).
3. Satisfying loops of 6-36 s (several tiny channels). Needs a physics/3D source we do not have.
4. "Part 2" series demand (comments, two niches).
5. Fandom crossover (huge numbers, but IP risk): rejected for production.

## Limits of this pass
- vidIQ credits (140) allow about 28 calls: video-level data for 4 channels, not 30; no per-video comment sweeps; no likes/comments for outlier videos; thumbnails not analysed; one video watched.
- "Views" are lifetime views at retrieval; recent-vs-old split exists only through vidIQ's publish dates.
- No YouTube channel is linked to vidIQ, so there are no own-channel analytics.
- Licences are not resolved (see AGENTS.md); only klein 4B is cleared for monetised use.
