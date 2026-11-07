# Multi-clip production (5-minute-plus videos)

Never ask H3 for the story in one clip (limit 4-15 s `[official]`; our clips 1.6-8 s, median 4.5 s). Each clip is one shot of a larger film. Dawn Gate: 158 shots = 9:25, about 3.6 s per shot `[verified]`. A 5-minute film is roughly 70-90 shots.

## Pipeline (existing code; do not duplicate)
1. Story + bible + shot list: `engine/original/story.py`, `planner`, story.json (characters, locations, panels with shot size, action, motion, dialogue).
2. First frames, one per shot, 16:9 (1344x768): `film.make_frames` -> `ArtEngine` (the only art workflow). Reroll with `rerolls={id: n}`.
3. Voices: `film.voice_shot` (Kokoro, per-character voice, frame-grid padding).
4. Clips: `film.make_clips` (FREE or VOICE workflow; `quiet`, `native_voice`, `seeds`). Resumable.
5. Evaluate every clip (`clip_eval`), fix per `regeneration.md`.
6. Score: `score.py` (ACE-Step on :8001, ~8-10 s per cue). 7. Master: `film_master.render` (cut, mix, SRT, title, loudness).
8. Check the final file: duration, no still windows, ASR WER, loudness. Upload private only; the owner declares made-for-kids and confirms any public/scheduled release.
MCP tools: `panelflow_original_film_{frames,clips,score,master,job,status}` (restart the engine after code edits; never mid-job).

## Shot state card (write before generating; check after)
```
shot: p0NN   duration: 3.0 s   mode: I2VA   frame: film/frames/p0NN.png
incoming: who/where in frame/scale, outfit, light, time of day, held objects
action (one): ...                         camera: Static Shot (or the one move)
outgoing: who/where/scale, outfit, light, objects        (must match incoming state of next shot unless a cut is intended)
sound: anchored voice | native | quiet | sfx      continuity: voice id, ambience, music cue
```
Continuity comes from regenerating each first frame from the same bible and from matching outgoing -> incoming states. Do not chain last frame -> next first frame as the default: drift accumulates `[hypothesis]`. `MiniMaxH3AddGuide` could anchor the tail frames of one clip into the next `[hypothesis, untested]`.

## Cuts and transitions
Plan transitions in the edit, not inside H3: a hard cut inside a clip is a defect unless asked (`p005`). Check both sides of each cut: last frame of clip n vs first frame of clip n+1 (not automated yet); audio: same ambience level, voices at the same loudness (`film_master.voice_gain_db`).

## Reuse and storage
Clips: `<workspace>/film/clips/<id>.mp4`; frames/voices alongside. Back up before regenerating a batch; another job may be writing there (check ComfyUI `:8188/queue` first).
