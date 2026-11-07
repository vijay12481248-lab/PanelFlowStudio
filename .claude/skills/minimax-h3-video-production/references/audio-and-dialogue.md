# Audio and dialogue

## Official syntax `[official]`
- Speakers get stable IDs `(S1)`, `(S2)`; same ID for the same voice in every shot. Describe the voice at first appearance (pitch, timbre, rate, accent).
- Identifying phrase, ID, action and delivery go OUTSIDE the tag; inside `<d>` only the language tag and the exact words: `The woman with a quiet, breathy voice (S1) says: <d>[English] I get off at the next station.</d>`
- Voice-over: write "says in an off-screen voiceover" and state the lips stay closed. Do not translate dialogue. On-screen text in plain double quotes.
- `overall_soundscape`: ambient, action and non-verbal sound only (1-4 sentences). `non_diegetic_music`: instrumentation and tempo, no mood words, `none` if none. Never repeat dialogue in either.

## Local paths `[verified]` (`engine/original/film.py`)
| Path | How | Evidence |
|---|---|---|
| **Anchored voice** (default for spoken shots) | Kokoro voice per character -> wav padded to the 17k+5 grid (0.15 s lead, 0.45 s tail) -> `fastvideo_h3_film_voice` (`MiniMaxH3AddGuide` at frame 0) | ASR of the clip returns the line; mouth follows (film.py measurement). Dawn Gate master: WER 1.7% |
| **Native voice** (`native_voice=True`) | H3 speaks; prompt names the speaker, delivery and says "only the spoken voice" | Works; voice varies by shot, so the same character may sound different |
| **Quiet shot** (`quiet=[ids]`) | silent wav anchored | H3 sometimes invents speech or music in silent shots; a new seed usually fixes it, silence always (costs SFX) |
| **Faceless speaker** | anchor silence, voice mixed at master with `FACELESS` + effect | anchoring would draw a mouth |

## Rules
1. Spoken line: anchored voice; exactly one line per clip; clip length = voice length on the frame grid.
2. Silent shots: say "no speech, no singing" in `overall_soundscape`; if ASR finds speech, set the shot `quiet`.
3. Music is separate (ACE-Step, `score.py`) and mixed at the master, about 27 dB under the voices; at 17 dB it buried quiet lines (WER 6.6% vs 1.7%) `[verified]`.
4. Master loudness target about -16 LUFS (Dawn Gate -16.7).

## Checking audio
Measured: audio stream present, RMS, silent fraction (`clip_eval.audio_stats`), loudness (`film_master.loudness`), ASR of the final file (Whisper; pass samples, not a path) and WER against the script. **Not measured:** lip-sync timing, how the voices and music sound. Nobody has listened to the voices or the score; say so in reports.
