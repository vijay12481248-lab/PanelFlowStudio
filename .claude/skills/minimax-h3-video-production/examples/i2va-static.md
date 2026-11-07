# Example: I2VA, character acting, fixed camera (tested)

Shot `p012` of Dawn Gate: a close-up, silent, 73 frames (3.04 s), first frame `film/frames/p012.png`. This is the exact prompt `film.motion_prompt` produced with the Static Shot camera sentence in Phase 1:

```
For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.
integrated_multimodal_description: [Shot 1] her smile slowly falls, she swallows, Pip's ears droop. The camera does nothing; it is a Static Shot, fixed on a tripod, with no zoom, no pan and no tilt. Single continuous take, anime film animation, smooth natural motion, consistent character appearance in every frame.

overall_soundscape: realistic sound effects that match the action (wind, footsteps, rustle, impacts, creaks), no speech, no singing.

non_diegetic_music: none.
```

Measured result (`clip_eval`, expect static): zoom +0.3% (current push-in prompt: +12.9%), no flags. Contact sheet: smile falls, eyes close, ears droop, camera fixed, same face/outfit. Not checked: sound (silent-shot SFX were not listened to).

Why it works: the picture carries the look; the prompt gives one action in order and one camera statement. Why not more: any extra sentence about the face or style adds nothing H3 can use.

# Example: wanted camera move

Replace only the camera sentence: `The camera pushes in with small amplitude at slow speed toward her face.` Run `evaluate(path, "any")` and read `camera.zoom_pct`; the "slow, steady" push-in measured about +6 to +13% over 3-4 s.

# Example: official FL2VA/L2VA shape (not runnable locally yet; no registered workflow wires `last_frame`)

```
How the reference pictures align with the target video - Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from Shot 1) aligns with the 3.75-second mark of the target video.
integrated_multimodal_description: [Shot 1] Static Shot. The cup sits on the table. A hand enters from the right, lifts it, and the cup stays the same shape and colour until it reaches her lips in the last frame.

overall_soundscape: soft ceramic touch, quiet room, no speech.

non_diegetic_music: none.
```
`S.SS` must be the clip's actual seconds on the frame grid: 90 frames = 3.75 s here (4.00 s = 96 frames is not on the 17k+5 grid; it snaps up to 107 = 4.46 s).
