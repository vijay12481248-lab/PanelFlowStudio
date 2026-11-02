# Anime Review workflow

Paste an episode URL or local file -> a narrated, human-style review video. Commentary is the product; footage is
illustration. This extends the existing `engine/anime` prototype (scene cuts -> template script -> Kokoro -> concat)
and reuses the rest of PanelFlow instead of duplicating it.

## Findings from the existing code (what we reuse / fix)

| Need | Reuse | Gap |
|---|---|---|
| Rights | `engine/acquisition/rights` (`RightsStatus`, `RightsDeclaration.validate_for_acquisition`) | Anime router/pipeline never checked it. Statuses are manga-oriented (no "commentary/review basis"). |
| Jobs / queue | `engine/jobs/manager.py` `JobManager.enqueue_async` (durable, leases, retries, resource admission) | Anime router uses an in-memory dict + `BackgroundTasks`. |
| LLM | `engine/llm/registry.py` (`get_ollama_provider`, local first), Ollama has `qwen3.5:9b` | Prototype script is fixed text templates, ignores transcript. |
| TTS / ASR | `engine/narration/runtime/audio.py` (`KokoroTts`, `WhisperStt`, `write_wav_atomic`) | Prototype re-implements both, imports `kokoro` at module import time. |
| Music | `engine/audio` (`music_director`, `bgm_defaults`) | not wired to anime. |
| Render / packaging | `engine/render` (NVENC detection), YouTube packaging router | Prototype shells ffmpeg directly, own packaging text. |
| Legal-risk code | - | `anti_copyright_transform` (scale/contrast tweak "anti-content-ID") is detection evasion. **Removed.** |

## Principles (copyright)

1. **Rights gate**: no ingest without a declaration. `UNKNOWN` is refused. A new basis `COMMENTARY_REVIEW`
   (transformative review/criticism, user attests they accept responsibility) is accepted in addition to the
   existing statuses; `permission_notes` is mandatory for it. Persisted in `source.json`.
2. **Footage budget** (enforced in clip selection, M2): each clip <= 20 s, total reused footage <= 25 % of the
   final video and <= 20 % of the source runtime; never contiguous long runs; narration is the main content.
3. **No evasion**: no pitch/scale/contrast tricks to dodge Content ID. Visual changes are limited to editorial
   ones (crop to 16:9, speed for sync, captions, branding).

## Data contracts (`engine/anime/review/models.py`)

Workspace: `output/Anime_Reviews/<slug>/` containing

- `source.json` - `IngestRecord` {source_uri, local_path, sha256, title, duration, w/h/fps, has_audio, rights, ingested_at}
- `analysis.json` - `EpisodeAnalysis` {scenes: [Shot{idx,start,end}], transcript: [Segment{start,end,text}],
  transcript_source: "embedded_subs"|"asr"|"none", language}
- (M2) `understanding.json` - plot summary, beats, highlights, funny moments, weak points, characters
- (M2) `clips.json` - `ClipPlan` [Clip{id, start, end, purpose, beat_id}] + budget report
- (M3) `script.json` - segments each tied to `clip_id`
- (M4) `timeline.json` - per segment: audio path, measured audio seconds, clip trim/speed/hold plan
- (M5) final mp4, srt, packaging

## Milestones

- **M1** (this change): rights gate, ingest (URL via yt-dlp if installed / local file), probe+validation,
  ffmpeg scene detection, audio extraction, transcript (embedded subs first, faster-whisper fallback), `analysis.json`,
  API `POST /api/anime/review/ingest`, `.../analyze`; removal of evasion filter; legacy `/generate-review` gated.
- **M2** episode understanding (LLM over transcript + shot stats + audio-energy peaks) and clip selection with the budget.
- **M3** review script from Ollama, per-segment clip binding, human-voice prompt + de-AI-ism checks.
- **M4** per-segment TTS (reuse `KokoroTts`), measured durations, sync timeline (audio drives clip length:
  trim / slow <=0.8x / hold last frame / loop; original audio ducked or dropped).
- **M5** FFmpeg render 1080p (NVENC -> libx264 fallback), SRT, music mix, YouTube packaging per channel.
- **M6** channel presets (voice, tone, language, intro/outro, music, branding), durable queue via `JobManager`,
  desktop UI (Anime Review screen), auto-pilot hook.

## Verification rule

Each milestone is run on a real media file and the artifacts inspected before it is called done (see the
milestone notes appended below).

## M1 verification (2026-11-02)

Run on a 60 s excerpt of a real narrated 1080p video already in `output/` (not anime): rights `UNKNOWN` -> HTTP 422;
`COMMENTARY_REVIEW` + notes -> ingested; 11 shots found whose boundaries line up with the source's panel changes;
faster-whisper (cached model, 3.6 s) produced a coherent English transcript. Synthetic clip tests cover embedded-subtitle
extraction. **Not verified**: URL download (`yt-dlp` is not installed in `.venv`; the code path raises a clear error),
Japanese-audio `task="translate"` quality on real anime, files > 1 h.

## M2 verification (2026-11-02)

Endpoints: `POST /api/anime/review/{slug}/understand` (local Ollama `qwen3.5:9b`, no cloud/mock fallback) and
`POST .../clips?target_video_sec=`. Real run on the same 60 s excerpt: 17 s for the LLM; summary, characters and 8 beats
were all grounded in the transcript (no invented events). Clip plan respected the budget (12.02 s = 20 % of 60 s) and
kept the opening and a highlight, dropping 6 beats. Limits seen: beat kinds `smooth`/`weak` are inferred from the
transcript only (no visual/animation judgement yet); on a 60 s excerpt the "ending" beat is just the last scene; transcripts
over ~24k chars are thinned evenly (not chunked) - long-episode quality is unverified.

## M3 verification (2026-11-02)

`POST /api/anime/review/{slug}/script` -> `script.json` (7 segments, each bound to a `clip_id`). Output is validated
(first=hook, last=cta, verdict+critique present, 12-70 words/segment, no stock AI phrases, every clip narrated, rating 0-10,
no "funny" segment unless a funny beat exists) and re-prompted with the concrete problems up to 3 times. Real run (qwen3.5:9b,
16 s) on the 60 s excerpt read naturally and stayed on the transcript. The first real attempt failed validation (no hook
segment; an invented "I laughed" joke) - those two rules and prompt fixes came from that run. Limits: the excerpt gives only 2
clips, so recap text is not matched to what the clip shows; segment order beyond hook/cta is not enforced; the rating is the
model's opinion from a transcript, not from watching the episode; non-English `language` is untested.

## M4 verification (2026-11-02)

`POST /api/anime/review/{slug}/voice` -> `voice/*.wav` + `timeline.json`. Each segment is synthesised with the existing
`KokoroTts`, dead air trimmed, +0.25 s pause, padded to a whole video frame, then the length is **read back from the wav**
and becomes the segment's timeline length (audio drives the clip). Per segment the clip is consumed from a per-clip cursor:
trimmed if long enough; else slowed to >= 0.8x; else the last frame is held; footage reuse and holds > 3 s are flagged as
warnings. Real run (Kokoro `am_michael`, 7 segments, 6 s): timeline total 64.0667 s vs ffprobe sum of the wavs 64.067 s, every
segment matched ffprobe to the millisecond. **Found by the run**: the 60 s excerpt yields only 2 clips (12 s budget) for 64 s of
narration, so clips were reused 5 times and 3 segments carry long freezes. That is the footage-budget rule working against a
tiny source; on a full episode more beats/clips exist, but M5/M6 should size the clip plan from the narration length
(re-plan after voicing) and the render must show these warnings. Not verified: how it sounds (no listening test), video-side
sync (render is M5), non-default voices.

## M5 verification (2026-11-02)

`POST /api/anime/review/{slug}/render` -> `review_1080p.mp4`, `review.srt` (sidecar) and `youtube_package.json` + `thumbnail.jpg`.
Per segment, one ffmpeg pass: clip trimmed/slowed/frozen per the timeline, cropped to 1920x1080, original audio at -22 dB under
the narration, captions burned in, exactly `round(audio_sec*fps)` frames; segments are concatenated with stream copy and the
bundled BGM is mixed at -24 dB with a 2 s fade. NVENC is used when a 1-frame test encode works, with a libx264 retry. Real run
(NVENC, 7 s for 64 s of video): 1920x1080 h264, 1922 frames = 64.0667 s x 30 fps exactly (audio track 21 ms longer from AAC
padding); frames inspected at 4/20/45 s show the right clip, readable captions, and a 3-line thumbnail. Chapters: 0:00 Intro,
0:17, 0:30, 0:48 (chapters closer than 10 s to the previous are folded, so the short "critique" segment has no chapter of its
own). Not verified: how the mix sounds (no listening test; levels are fixed constants), CPU fallback end-to-end on a real
episode, Intro/outro/branding (M6), non-Windows fonts for the thumbnail.

## M6 verification (2026-11-02)

Added: channel presets (`/api/anime/review/channels`, stored in `app_data/config/anime_channels.json`: voice, rate, tone,
language, target length, music, watermark logo, extra tags, description footer, captions), a hands-off orchestrator
(`engine/anime/review/pipeline.py`, resumes from existing artifacts, rights re-checked inside the worker), durable queue
(`POST /api/anime/review/queue`, `GET .../jobs`; each episode = one `ANIME_REVIEW` job in the existing `JobManager`,
rehydratable after restart via `workflow.build_operation`), and a desktop screen (Quick Actions -> "Anime Review"):
paste links/paths, pick channel, declare rights basis, watch the queue.
Each queued episode also creates a tracking project (kind `anime_review`) because `JobRecord.project_id` is a foreign key;
it will show up in the dashboard project list.

Real run (isolated app-data dir): two 60-75 s excerpts queued at once with two channels. Both jobs SUCCEEDED unattended
(~2 min total): "Hype Channel" (am_michael, logo watermark, footer text) and "Calm Critic" (af_heart, rate 0.95). Outputs: 1080p
h264, frame counts equal timeline seconds x 30 (2273 = 75.7667 s, 2226 = 74.2 s); the watermark appears only on the Hype video;
voices differ; footer appears only in the Hype description. `tsc --noEmit` on the desktop app is clean; 77 backend tests pass.

Not done / not verified: intro/outro clips (preset has no such field yet); clip plan is NOT re-sized after voicing, so short
sources still get long freezes (Hype episode: 3.8 s and 5.4 s freezes, flagged in `warnings` and in the job output); the UI was
type-checked but never opened in a browser/Tauri window; URL download (`yt-dlp` not installed); no real anime or Japanese
audio was ever used; no listening test; cancelling a running job mid-FFmpeg is cooperative only between stages; concurrency
relies on the existing admission control (both jobs ran in parallel here); "Anime Review" shares the Ollama model with
other jobs.

## Real-episode run (2026-11-02): Sintel, 14:48, 1080p, CC-BY 3.0

Source: Blender Foundation's *Sintel* (CC-BY, declared as `CREATIVE_COMMONS`). Not anime and English-language, but a real
full-length animated episode with a score, action and ten embedded subtitle tracks. Ingested through the **URL path**
(yt-dlp against a local HTTP server; `yt-dlp` is now a declared dependency) and run unattended through the queue.

What the real run found and what was fixed:

1. **Wrong subtitle track**: the first embedded track was German. Now the first *English text* track is used; otherwise ASR
   translation. Test added.
2. **One-shot script failed** on 8 clips: 262-541 words instead of ~1000 and invented role names. Script writing is now
   sectioned (hook/recap, one block per clip with its dialogue and a vision description, critique, verdict+CTA), with the
   structure, order and clip binding fixed in code.
3. **Dialogue-only understanding** missed the visual story (only 26 subtitle lines in 14 min). Added: a keyframe description
   per beat from the local vision model, plus loud no-dialogue moments as extra beats (end-credit fades are dropped).
4. **Long freezes** (up to 19.7 s): long holds now get a slow push-in instead of a frozen frame; clip length adapts to the budget.
5. **Footage share**: the first run used 39% of the final video's length. The budget is now computed from the expected
   narration length and the real share is reported in the job output.
6. Shot detection now runs on a 320 px downscale (much faster on 1080p).

Final run: job SUCCEEDED in ~2 min wall time for a 242 s review (5814 frames, 1080p h264 + AAC), 24 segments, 611 words,
rating 9.0, 65.7 s of source footage = **27% of the video, over the 25% limit; the job flags this as a warning** (script length
varies per run). Holds of up to 9.5 s remain (flagged). **Content quality is not trustworthy yet**: the narration said Sintel
is hunting "her missing sister, Scales" - Scales is the dragon. The model only sees dialogue lines and one frame per beat,
so it can hallucinate plot; there is no fact-check step, and a human should read `script.json` before publishing.
Still unverified: real anime and Japanese audio, how it sounds, the desktop UI in a window.

## Fact-check (added after the Sintel run)

`engine/anime/review/factcheck.py`, run inside the pipeline and the `/understand` and `/script` endpoints. The summary is
grounded first (dialogue + beat notes + vision descriptions), then every script paragraph is checked.

- **Layer 1, deterministic**: invented names, kinship words (sister, father, family...), quotations absent from the
  dialogue, and numbers (not in verdict/cta) must literally appear in the evidence.
- **Layer 2, LLM judge**: looks for invented events, but only counts phrases that really occur in the narration. A first
  version asking the 9B model to judge everything was worse than useless on real data (it echoed the evidence back as
  "unsupported" and flagged plain paraphrases), hence the layering.
- Failing paragraphs are rewritten (max 2 rounds); if still failing they are dropped when optional or kept with `flags` when
  required (hook, critique, verdict, cta), and flagged ones are listed in the job's `warnings`.

Real check on the earlier Sintel script (which said Sintel hunts "her missing sister, Scales"): the invented "sister" was
caught in all 6 places, "family" in the verdict, all were rewritten without them, 0 left flagged. Full re-run:
242 s review, 24 segments, no kinship invention, footage 23.5% of the video (under the limit). Limits: the checker cannot
catch an invented *event* that uses only words from the evidence, or plausible vision-model errors (it trusts the per-beat frame
descriptions); the summary of that run could not be grounded and fell back to a terse list of moments, so the YouTube
description is poor; still no real anime, no Japanese audio, still read `script.json` before publishing.
