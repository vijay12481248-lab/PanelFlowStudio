# Long H3 video: chained clips (`engine/original/chain.py`)

H3 renders 4-15 s per clip. A longer take is a chain of clips whose joins carry motion and sound. Method: Herrgott's *H3 Infinite Continuation Suite* v1.4
(GPL-3.0, community project, installed in `ComfyUI\custom_nodes`): clip 1 is FL2VA (first picture -> second picture); every later clip copies the previous clip's saved
video+audio latent into its target, protects it with ComfyUI's native H3 AV masks, and lands on the next picture. A last graph decodes the saved latents, trims the reused
head and the frozen tail and crossfades the clips. Needs ComfyUI with the H3 AV-mask support (PR #15375; the Nov 2026 build has it).

## Run it
`chain.run_chain(story, ws, ["p032", "p033", "p034"], "my_run")` -> `<ws>/film/chain/my_run/{clip_N.mp4, chain.mp4}`. The pictures must exist (`film.make_frames`).
Workflows (registered, checksummed): `herrgott_h3_chain_start`, `_continue`, `_stitch` (FastH3 8-step, 960x544, 4.5 s of new picture per clip, one size per chain).
`plan_chain` warns when neighbouring pictures change shot size.

## Measured (Dawn Gate, RTX 5060 Ti, one seed each, judged by eye + `clip_eval`)
| Trial | Result |
|---|---|
| Context Loop pack (ethanfel), p070 -> p071 with no picture for scene 2 | scene 2 lost the story (cave arch and a statue face instead of the sealed sun gate); worse than our per-shot clip |
| Context Loop, p056 -> p057 | seamless join but several duplicate gliders; never reached the beat |
| Herrgott, p056 first frame, p057 last frame | seamless join, one glider, smoke trail carried, landed on p057 |
| Herrgott 4-clip chain p032, p033, p034, p037, p039 (14.4 s) | look and characters held, story followed the pictures; `clip_eval` confirmed one hard cut at 11.8 s; the p033 picture is a close-up so the first ~6 s are faces |

Driver check (`chain.run_chain`, p032 -> p033 -> p034, same seeds as the manual run): 466 s for 2 clips + stitch (about 210 s per clip, model load included, the stitch ~25 s);
both clips are bit-identical to the manually queued ones (PSNR inf); the stitched file is 7.3 s, 175 frames, with audio.

## Known limits
- A change of shot size between neighbouring pictures produces a cut or morph inside the clip: choose pictures with the same framing.
- Each clip is queued one after another (each needs the previous latent); there is no resume (re-running a `run_name` overwrites it).
- Not wired into `JobManager`, the MCP tools or the desktop UI yet: call `run_chain` from Python (the engine does not need a restart for that).
- Not measured: other seeds, 3+ clip chains on a new story, a listening test (the 4-clip mix varied 12 LU in loudness).
- Context Loop (ethanfel) is installed but not used: without a picture to land on it drifted.
