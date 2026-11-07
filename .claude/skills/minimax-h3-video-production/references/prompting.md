# Prompting H3 (local I2VA first)

## Official skeleton `[official]`
Part 1 (instruction line) then blank line, then the core fields. Keep exact field names and order.
- **I2VA:** `For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.`
- **FL2VA:** `How the reference pictures align with the target video - Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from Shot N) aligns with the S.SS-second mark of the target video.` (no brackets in the official FL2VA text; S.SS = clip seconds, two decimals)
- **L2VA:** `How the reference pictures align with the target video - <Picture 1> (from [Shot N]) aligns with the S.SS-second mark of the target video.`
- **T2VA:** no instruction line.
- Fields: `integrated_multimodal_description:` (shots, actions, camera, speakers, dialogue, diegetic sound), `overall_soundscape:` (1-4 sentences, ambient/action sounds, no dialogue repeated), `non_diegetic_music:` (instrumentation/tempo, no mood words; `none` if none).
- Shots: `[Shot 1]` has no timestamp; later `[Shot 2] At 00:03.500, the camera cuts to ...`, strictly increasing and inside the duration. A cut must add new information; distance-only changes are camera motion. FL2VA/L2VA favour a single shot.
- Write concrete visual and audio details, not abstract words ("cinematic", "beautiful").

## Local rules for I2VA (what the pipeline does and what was measured)
1. **The first frame carries the look. The prompt carries only the change.** Do not re-describe faces/outfits; re-describing makes faces melt `[verified: owner's observation in film.py, project guide]`.
2. **State what must stay put and what the camera does** - every time (`camera-and-motion.md`). Default camera sentence (now what `film.motion_prompt` and `animate.motion_prompt` emit unless `Panel.camera` is set): *"The camera does nothing; it is a Static Shot, fixed on a tripod, with no zoom, no pan and no tilt."* `[verified, Phase 1: zoom 38% -> 0.8%]`
3. **H3 continues any action it sees in the picture.** A tilted glass becomes poured juice; keep the picture's implied action equal to the wanted action `[verified: cat video]`. First = last frame loops make calm beats minimal but action beats still invent things.
4. **Name things so they cannot be read as something else.** "flying machine" became jets; `film.motion_prompt` rewrites to "cloth-winged glider" and adds "no jets, no airplanes, no propellers" `[verified]`.
5. **One shot, one action, 3-5 s.** Longer clips fill extra time with invention (`p088`: golem changed shape at 5.17 s) `[verified, 6 shots]`.
6. **Sound sentence is part of the prompt**: silent shots say "no speech, no singing" or are rendered `quiet` (`audio-and-dialogue.md`).
7. **Plain words.** The 9B writes weak text; avoid quality adjectives ("masterpiece", "hyperdetailed"): they add noise/jitter `[hypothesis from project guide]`.

## Scenario templates (I2VA; only the first was exercised in production)
Fill `{}`; keep the skeleton lines above them unchanged.
- **Character acting (tested, Dawn Gate):** `[Shot 1] {what changes in the face/body, in order}. {camera sentence}. Single continuous take, {style} animation, smooth natural motion, consistent character appearance in every frame.`
- **Walk/run `[hypothesis]`:** `[Shot 1] {Subject} walks {direction} at a steady pace, arms swinging, staying the same size and distance from the camera. {camera sentence} Background and ground do not change.`
- **Object interaction `[hypothesis]`:** name the object and its final state: `{Subject} lifts the cup to their mouth and drinks; the cup stays the same shape and colour.` Avoid motion words that imply a result not in the frame (pouring, spilling).
- **Dialogue:** use the anchored-voice path, not prompt-only speech (`audio-and-dialogue.md`).
- **Minimalist / stickman, cartoon, 2D, 3D, product ad, explainer `[hypothesis]`:** same skeleton; the style word comes from the first frame, the prompt adds only motion and "background stays flat/unchanged". Product ad: "the product stays centred and sharp, only {light/reflection/rotation} changes".
- **Transition between shots:** do not ask H3 for a cut inside one clip unless wanted (`p005` cut by itself at 0.58 s). Make each clip one shot and cut in the editor.

## T2VA / FL2VA / L2VA locally
Not exercised. Before using: add or approve a registered workflow that wires `last_frame` (FL2VA/L2VA) or no frames (T2VA); then test on 3 shots and evaluate. Prompt text follows the official skeleton above; use a single shot and say how the last frame is reached ("the last frame is reached by the end of [Shot 1]").

## Do not
Put identity phrases inside `<d>`; translate dialogue; add a timestamp to `[Shot 1]`; write plot summaries; mix reference and first/last-frame modes `[official]`. Do not pass a prompt through the hosted Context-IR.
