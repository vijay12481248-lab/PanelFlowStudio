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
