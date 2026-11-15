# Gotchas (each one cost time on 2026-11-14)

| Symptom | Cause | Fix |
|---|---|---|
| Later scenes keep the bedroom/sunset of scene 1 (exam hall drawn as a bedroom) | scenes 2+ use the scene-1 picture as `reference_image`, which carries the old room along | list location-changing scenes in `NO_REF` in `specs.py`; describe the new place strongly in `img` |
| Wife drawn with the husband's mustache | the model blends traits across characters in one prompt | `chars` must say what a character does NOT have ("smooth face with no mustache") |
| Key prop missing (the brain in the thumbnail) | the model drops small or hidden props | make it large, beside the character, "fully visible"; redraw; stills are cheap (10-30 s) |
| Title covers the face on a thumbnail | art fills the frame even when asked for empty bands | per-picture title y in `FINAL`; single-line option `ONE_LINE`; font cap 200 px so two lines end before y 1680 |
| H3 invented emoji faces in a "cheering" scene | H3 continues crowd/celebration action | reword `act` literally; try one new seed (`REEL_SEED_BUMP`); the rejected clip is kept in `rejected/` |
| Last shot is a frozen frame for 2+ s | narration line longer than the ~6.5 s clip | shorten the CTA line; assemble holds the last frame (`tpad`) rather than loop a jump |
| ffmpeg `subtitles=` fails with exit 4294967274 | `fontsdir=C\\:/Windows/Fonts` escaping | use `subtitles=captions.ass` alone; Impact is found by the system |
| Log file stays empty while a stage runs | Python buffers stdout under nohup | run `python -u` |
| Self-written "wait until the stage ends" watcher never fires | its own command line matched the process filter | wait on the stage's output file or a specific PID, not on a regex of its own command |
| ComfyUI "offline" after the session restarted | it was a child process of the old session | start it again (`venv\Scripts\python.exe main.py --listen 127.0.0.1 --port 8188` in `E:\VIJAY SEKAR\ComfyUI`), wait for `/system_stats` |
| `ArtEngine.generate` rejects a workflow | only `IMAGE_WORKFLOW_IDS` are allowed (`qwen_image_21`, `minimax_h3_image_edit`) | do not register a third text-to-image path; `tests/unit/test_art_engine.py` guards it |
| A passing background command killed by the tool timeout | foreground waits are capped at 10 min | run long waits in the background and read the log |
| Qwen3-TTS reads a line oddly (WER 12-14% on two reels) | proper nouns, "ha.", "centimetres" | respell the line for speech; re-run only that wav |

## Timings measured (RTX 5060 Ti 16 GB)
Qwen3-TTS 50 lines ~4 min · ACE-Step 32 s bed ~6 s · Qwen still 8-25 s · H3-Image still 17-32 s · FastH3 clip (480x832, 5 s) ~86 s · assemble ~1 min per reel. A 10-reel batch is about 25 min of pictures plus ~75 min of clips.

## Not done / not verified
Voices never listened to; jokes untested on an audience; no click-through, retention or revenue data; nothing uploaded; no test for the `tools/reels` code (the helpers `chunks`, `ass_time`, `build_ass` are simple but untested).
