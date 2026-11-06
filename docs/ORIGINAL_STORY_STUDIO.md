# Original Story Studio - plan

Goal: PanelFlow writes an **original** story, draws it as manga panels with a local image model, lettered by us, then
reuses the existing narration, motion, render and packaging pipeline to publish a long video plus Shorts. The same
story is also exported as a manga chapter (pages). Everything is the user's own work: no source-rights problem.

## What exists (reuse)

| Need | Existing | State |
|---|---|---|
| Image generation | `engine/comfyui` (client, approved-workflow registry, job service), `ComfyImageScreen` | Code only. **ComfyUI is not installed or running** and none of the registry's models (`longcat_image`, `qwen_2.5_vl_7b_fp8`, `ae`) are on disk. No `diffusers`. |
| GPU | RTX 5060 Ti 16 GB, torch 2.14+cu130 works | Enough for SDXL or Flux-fp8 in ComfyUI; Blackwell needs a current torch (already there). |
| Story/characters | `SeriesBible` store (`engine/narration/bible`), narration compiler (`ChapterInputs` = panels + dialogue) | Consumes panel images + dialogue text, so generated panels can enter as if OCR'd. |
| Narration/TTS/music/render/packaging/queue | narration compiler, Kokoro, `engine/audio`, `engine/render`, packaging router, `JobManager` | Working on real manga (acceptance runs) and the anime review workflow. |
| LLM | Ollama `qwen3.5:9b` (text + vision) | Used for the anime review; adequate for outlines, weaker for long coherent plots. |

## Existing problems to solve first

1. **No image engine on disk.** Blocker for everything visual. Needs ComfyUI + a checkpoint (multi-GB download, licence check).
2. **Character consistency.** The hardest part: the same face/outfit across 30+ panels. Needs per-character reference
   sheet + IP-Adapter/LoRA or consistent-seed tricks, and an automatic check (vision model compares each panel to the sheet).
3. **No text in images.** Diffusion models cannot letter. Speech balloons and SFX must be drawn by us (we know the text, so
   this is deterministic) - a new lettering step.
4. **Panel layout.** Models output single images, not pages. We generate panels one by one at set aspect ratios and compose
   pages from layout templates (for the manga export); the video uses panels directly.
5. **Story quality.** A 9B model drifts over long plots. Use the sectioned approach that fixed the anime script:
   premise -> series bible -> episode outline -> scene list -> panel list, each step small and validated.
6. **Throughput.** ~20-60 s per SDXL panel; a 40-panel episode is 15-40 min of GPU time. Must queue, cache and resume.
7. **Fact-check does not apply** (fiction) but a *continuity check* does (names, ages, places, who knows what).
8. **Platform risk.** YouTube "inauthentic/mass-produced content" policy and the synthetic-media label: a human must
   approve scripts and keep stories distinct. Pure AI art is probably not copyrightable, so "no one else can claim it" is
   true, but neither may you be able to enforce rights. Model licence must allow commercial use.

## Architecture

New package `engine/original/`:

- `premise.py`  genre preset (bedtime / horror / mystery / fantasy) + hook -> premise, tone, length.
- `bible.py`    characters (name, age, look prompt, voice), locations, rules; writes into the existing `SeriesBible`.
- `outline.py`  episode outline -> scenes -> panel script `[{panel_id, shot, camera, action, dialogue[], sfx[], caption}]`.
- `art.py`      panel prompt builder (character look + shot + style lock) -> ComfyUI job per panel; seed + prompt stored.
- `consistency.py` vision-model check of each panel vs character sheet; regenerate up to N times; flag the rest.
- `lettering.py` draw balloons/captions/SFX onto panels (Pillow, real fonts) for the manga export; the video keeps
  clean panels and burned captions instead.
- `compose.py`  manga page layouts (1-5 panels) -> page PNG/PDF.
- `project.py`  create a normal PanelFlow project (pages, panels, dialogue as OCR) so narration/motion/render/packaging
  run unchanged. Rights status: `USER_OWNED`.
- API `/api/original/...`, a "New Original Story" screen, jobs through `JobManager`.

Data contracts (JSON in the project workspace): `premise.json`, `bible.json`, `outline.json`, `panels.json`
(every panel: prompt, seed, image path, check result), `pages.json`.

## Milestones (each: tests + a real end-to-end run + commit, as with Anime Review)

- **S0 Image engine.** Install ComfyUI (portable) + one checkpoint, approve a manga/anime-style workflow in the registry,
  verify `capabilities`, generate and inspect a real panel. *Needs the user's decisions below.*
- **S1 Story engine.** Premise -> bible -> outline -> panel script with validation and a continuity check; real run on a
  bedtime story and a horror story; read the output for quality.
- **S2 Art engine.** Panel prompts + ComfyUI jobs, queue/cache/resume; character sheets; consistency check; measure
  how often the same character is recognisably the same.
- **S3 Video from panels.** Build the project, run existing narration + motion + render; verify sync and watch the video.
- **S4 Lettering + manga export.** Balloons/SFX, page layouts, PDF chapter.
- **S5 Shorts.** 9:16 re-render of the best 30-60 s from the timeline with hook caption (also useful for Anime Review).
- **S6 Series + channel automation.** Series bible persists across episodes, channel presets, daily queue, packaging,
  desktop screen. (YouTube upload/analytics, comments assistant are the separate M7+ items.)

## Decisions needed from the user

1. **Image model.** Recommended: SDXL-based anime/manga checkpoint with an OpenRAIL++/permissive licence, or FLUX.1
   schnell (Apache-2.0, ~12 GB, fits 16 GB in fp8, better prompt following, weaker "manga" look without a LoRA).
   Downloads are 6-24 GB; I will not download without approval.
2. **Style.** Black-and-white manga or colour webtoon/anime stills (colour is far easier to keep consistent and looks better as video).
3. **First genre/channel.** Bedtime and horror are the cheapest to make consistent (few characters, simple settings).

## Verification rules

Real generated images and a real rendered video are inspected at every milestone; consistency and story quality are
judged by reading/looking, not by passing tests alone. Anything not verified is listed in the milestone notes.

## S0 result (2026-11-02): image engine installed and verified

- ComfyUI 0.43.0 cloned to `E:\VIJAY SEKAR\ComfyUI` (outside the repo, GPL-3.0) with its own venv (torch 2.14.1+cu130);
  start it with `venv\Scripts\python.exe main.py --listen 127.0.0.1 --port 8188`.
- Checkpoint `animagine-xl-4.0.safetensors` (6.94 GB, CreativeML Open RAIL++-M, commercial use allowed) in
  `ComfyUI\models\checkpoints`.
- New approved workflow `anime_sdxl` (SDXL, euler_ancestral, 28 steps, cfg 5) bundled at
  `engine/comfyui/workflows/anime_sdxl.api.json` and registered with its checksum; `api_workflow_root()` now falls back
  to the bundled folder.
- PanelFlow discovers installed models through `<PANELFLOW_COMFYUI_WORKFLOW_DIR>/../models`, so set
  `PANELFLOW_COMFYUI_WORKFLOW_DIR=E:\VIJAY SEKAR\ComfyUI\workflow` for the engine (the empty `workflow` folder exists).
  With it set, preflight reports `ready: true`; without it the model shows as missing.
- Real check: one 832x1216 panel (silver-haired girl, candle, dark hallway) generated through the approved workflow in
  30.5 s on the RTX 5060 Ti; sharp, correct anime style, prompt followed except the requested "scared" expression
  (she smiles) - expression control needs work in S2, and prompts must keep characters clearly adult or explicitly
  not child-like in suggestive framing; for kids' bedtime content use child-safe tags and review every image.
- Not verified yet: generation through the `JobManager`/`/api/comfyui` job path, consistent characters, B&W/manga look.

## S1 result (2026-11-02): story engine

`engine/original/` (`models.py`, `genres.py`, `story.py`) and `POST /api/original/story`, `GET /api/original/story/{slug}`,
`GET /api/original/genres`. Steps: premise -> bible (cast, places, world rules) -> scene outline -> panel script per scene,
one small LLM call each, with deterministic validation and retries that name the concrete problems. Panels carry shot,
angle, characters, a visual `action` for the art model, dialogue (<=2 lines, <=18 words), a narrator `caption` (the storyteller
voice that carries the video) and SFX. Genres: bedtime, horror, mystery, fantasy (tone, structure, length, art style tags,
forbidden words; bedtime is child-safe: child protagonist, no antagonist, no gore/scary words).

Real runs with local `qwen3.5:9b` (about 4 minutes each):
- **Bedtime** ("a small child who cannot sleep"): 35 panels, ~8.8 min of narration, child protagonist, gentle arc.
- **Horror** ("an old lighthouse keeper's last night shift"): 40 panels, ~8.3 min, atmospheric, no gore.

What the real runs broke, and the fixes: hyphenated/odd ids and `age_group` words ("kid", "ageless") -> normalised, not failed;
no or two protagonists -> repaired; characters named "They"/"It"/"protagonist" -> rejected (proper name required);
ids drifting from names ("fenrir" for "Mist-Walker") -> id now derived from the name; the first bedtime draft had an adult
protagonist and terrifying wording (nightmare, panic, sweat) -> child protagonist enforced, scary words forbidden for
bedtime; only 175 words for 35 panels (1.2 min) -> every panel needs a 25-45 word storyteller caption (15-35 for horror);
a real term ("Fresnel lens") looked like an invented name -> soft warning after two retries.

Not verified / known weak: stories are coherent but generic; repeated beats appear (two near-identical "tossing and turning"
panels); the model sometimes confuses camera terms with places; the `unknown names` checks are lexical, so invented
*events* are not caught (fiction has no ground truth; a human must read the story); mystery/fantasy not run; no
continuity check of facts across scenes beyond names and cast.

S1 reliability note: on a fresh idea ("a sleepy fox who collects lullabies") the first two attempts failed validation after
retries (a character `look` written as a sentence, mild words like "trapped" in the bedtime forbidden list, panels that
included a character not listed in the scene). Rules were relaxed where they were stricter than needed (look: 4 tags or 8
words; panels may use any bible character; the scary-word list is shorter) and the third run produced a 28-panel, ~7.1 min
story. Expect an occasional failed job with this local model; the job layer (S6) should retry automatically.

## S2 result (2026-11-02): art engine

`engine/original/art.py` + `POST /api/original/story/{slug}/art?limit=&check=`: per story it renders a character sheet
per character, then every panel through the approved `anime_sdxl` ComfyUI workflow (1344x768), storing `art.json`
(prompt hash, seed, attempts, consistency score, missing tags). Reruns reuse any panel whose prompt is unchanged and redo
only edited ones. Prompts repeat each character's exact `look` tags plus shot/angle tags, the location look and the genre
art style; the negative prompt blocks nsfw/text/bubbles. A vision check then confirms the character's core look tags and
a panel scoring below 0.6 is regenerated once with a new seed and the missing tags emphasised `(tag:1.3)`.

Real runs on stored stories (RTX 5060 Ti, ~28 s per image; ~40 s per panel with the check):
- **Fox bedtime story**, 10 panels: the fox is recognisable in every panel by eye; the vision check's core-tag score is
  mean 0.70 (0.5-1.0, one 0.0 on an extreme close-up). Images are clean, colourful, storybook style.
- **Horror story**, 6 panels: atmospheric, dark, the keeper is recognisably the same figure (long white hair, dark coat,
  goggles) in 3 of the 4 panels I inspected; the character sheet shows him with darker, shorter hair.

What the runs broke and the fixes: (1) the first check asked the vision model to match characters by *name* and it answered
with tag names, so every panel scored 0 -> the check is now one call per character with an explicit tag list; (2) it demanded
all 5-8 tags, including the carried item and textures ("salt-crusted hair"), which the 9B vision model cannot confirm (it denied
a clearly visible fox cub) -> only the first 3 core tags (2 for close-ups) are checked; (3) `look` fields that described another
character ("glowing moth companion perched on shoulder") are now rejected and the bible prompt asks for drawable colour-and-shape
tags; (4) retries capped at 2 attempts.

Not solved / honest limits: consistency is a *prompt-tag baseline* - same outfit and species yes, same face no (that needs
IP-Adapter or a LoRA: an extra ~1.5 GB of downloads and a ComfyUI custom node, to be decided in S2b); two characters in one
prompt blend features (a fox grew moth wings); the checker is noisy, so scores are a coarse signal and a human should skim
the contact sheet; the character sheet prompt sometimes draws several copies of the character; the horror run was made before
the drawable-tags prompt change and the new bible prompt itself was not re-run against the LLM; not yet verified through the
`JobManager`/API path (long call, S6 queues it).

## S2b result (2026-11-02): IP-Adapter for consistent faces

Installed (approved, 3.4 GB): `ip-adapter-plus_sdxl_vit-h.safetensors` (848 MB, Apache-2.0) and the CLIP ViT-H image encoder
(`CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors`, 2.53 GB) from `h94/IP-Adapter`, plus the `ComfyUI_IPAdapter_plus` custom
node (GPL-3.0) in `ComfyUI\custom_nodes` (ComfyUI restarted to load it). New approved workflow `anime_sdxl_ipa`
(`engine/comfyui/workflows/`, registry entry with an optional `reference_image` patch slot; registry/service accept it only
for workflows that declare it). `ComfyRunner` uploads the reference to ComfyUI and uses this workflow whenever a panel
shows a character; the first character on screen is pinned to its sheet, and the reference name is part of the cache key.
Character sheets are now one clean portrait (they double as the reference). If the adapter models or nodes are missing the
runner silently falls back to prompt-only consistency.

Real A/B on the fox story (same 8 panels, same checker):
- prompt-tags only: core-tag score mean **0.70**, ~40 s/panel (frequent regeneration);
- IP-Adapter weight 0.6: **0.96**, all first attempts, ~20 s/panel, but compositions copied the portrait (same pose/framing);
- IP-Adapter weight 0.45, ends at 65% of the steps (shipped): **0.92**, all first attempts, faces clearly the same fox across
  panels (blue eyes, forehead spots, orange fur) with real variety of pose and setting.

Still wrong: panels with two characters (fox + moth) draw several foxes - only one reference is applied, and the second
character is not drawn from its own reference; the pastel style washes out strong genre mood (horror was not re-tested with the
adapter); small "ghost" creatures clutter backgrounds. Next ideas: two-reference regional prompting for two-character panels
(a second IPAdapter node with an attention mask) and re-testing horror.

## S3 result (2026-11-02): video from panels

`engine/original/video.py`, `POST /api/original/story/{slug}/video`. Each panel is voiced by the genre's storyteller
(bedtime `af_heart` at 0.88x, horror `bm_george`, mystery `am_adam`, fantasy `bm_fable`; only voices cached offline are
used) with a distinct voice per character for dialogue; the panel's audio length (frame-aligned, min 3 s, 0.6 s closing
pause) is its length on screen, as in the anime review sync. Rendering: the panel image is cropped to 16:9 and gets a slow
push-in / pan-right / push-out / pan-left (zoompan on a 2x upscale), burned-in captions, fade in/out at the ends, NVENC with
CPU fallback; segments are concatenated and mixed with the music bed, then loudness-normalised to -16 LUFS. Reruns reuse
unchanged voice and segment files (per-panel content hash). `package()` writes title, description with chapters per scene and
an AI-content disclosure, tags and a thumbnail from a close/medium panel.

**Deviation from the plan**: the existing manga project pipeline was not used. It OCRs page images and rewrites narration
from them, while stories here already carry narration and dialogue, so a direct path reusing the Kokoro adapter, caption/SRT
helpers, encoder detection and music bed was smaller and verifiable. Registering generated stories as normal projects
(dashboard, auto-pilot, story editor) is not done.

Real run, fox bedtime story (28 panels, all generated with IP-Adapter, check score mean 0.875, none below threshold):
**6:32 1080p video built in 75 s**, 11776 frames = timeline 392.53 s x 30 fps exactly, -16.1 LUFS (the first mix was -28.6
dB mean, too quiet, hence the normalisation), SRT sidecar, 5 chapters. Frames inspected at 4 points: clean storybook look,
readable captions, correct motion.

Visible problems: the hero fox comes out white/pink in one panel and orange in the others; the two-character panels draw
three foxes and winged foxes (character blending, see S2b); captions are verbose (whole narration is burned in); the same
music bed as the anime review (not genre-specific); voices were not listened to; chapter labels are just the first 7 words of
each scene summary; only one story/genre was rendered; the API route was not exercised and nothing is queued via `JobManager` yet.

## S2c result (2026-11-02): two-character panels

New approved workflow `anime_sdxl_ipa2` (`registry` optional slot `reference_image_b`, fixed 1344x768): two IP-Adapter
nodes chained on the same model, each with an attention mask - the first character's portrait owns the left half of the
frame, the second the right half (SolidMask + MaskComposite). `ComfyRunner` uses it for panels with two characters and the
prompt now says `2others` instead of `multiple others`; cache keys include both reference names; if the workflow or its nodes
are missing it falls back to the single-reference workflow.

Real check on the four fox+moth panels that had produced three foxes and winged foxes: **3 of 4 now show exactly one fox
and one winged girl (Lumina) side by side**, recognisably the same characters as their portraits; the fourth shows the fox
and only a tiny moth (Lumina is shrunk or missing). Vision check mean 0.92, all first attempts, ~20 s/panel.

Limits: the left/right split is a fixed layout (first character left, second right), so compositions with a character in
front of another, or three-character scenes (only the first two are drawn), are not handled; the second character
occasionally disappears; the other panels of the fox video were not regenerated yet.

## S4 result (2026-11-02): lettering and comic pages

`engine/original/lettering.py` (balloons, narrator box, SFX; Comic Sans/Impact with fallbacks) and
`engine/original/pages.py`; `POST /api/original/story/{slug}/pages` writes `pages/page_XXX.png` (1600x2400), `lettered/`
and `comic.pdf`. A cover page (hero art, title, logline, AI-content line) is followed by pages of three full-width lettered
strips each (webtoon-style stacking: landscape art would lose its left/right characters in tall manga cells). Dialogue
balloons sit over the speaker's half of the frame (first character left, second right, matching the two-reference art
layout) with the tail pointing down; two lines of the same speaker stack; the narrator text becomes a cream box at the bottom,
shortened to its first ~22 words (the full 25-45 word storyteller text is for the video); SFX are drawn in yellow Impact with a
dark outline. Missing images are reported, never faked.

Real export of the fox story (28 panels): **11 pages (cover + 10) and a 4 MB PDF in 6.5 s**. Inspected: cover and body
pages read well, balloons are legible and no longer collide after I narrowed their width (the first version let two
balloons touch because the text width ignored the padding), tails point at the speaker's half.

Limits: balloon positions are layout-based, not face-aware (a single centred character with two speakers off-frame gets
tails pointing at empty space, as in one inspected panel); caption boxes cover the bottom of the art; this story contains no
SFX so the SFX drawing is only covered by unit tests; right-to-left manga reading order, black-and-white screentone and
non-stacked page layouts are not done; the fox art in this export predates the two-character fix.

## S6 result (2026-11-02): series, channel presets and the daily queue

- **Series** (`engine/original/series.py`): `<root>/<series_id>/series.json` holds the bible (world, cast, places, rules),
  the episode records (title, continuity summary, publish slot, status, video/pdf paths, warnings) and `sheets/` - the
  character portraits drawn once and copied into every episode's workspace, so faces stay the same across episodes.
  `generate_story(..., series_bible=, previous=)` writes the next episode with the same cast/places/rules, a new premise and
  the earlier episodes' summaries in the prompt.
- **Episode run** (`episode.py`): story -> art (with the shared portraits) -> voiced video (the channel preset's voice,
  rate, music, captions) -> package (preset tags/footer) -> comic pages; every stage resumes from its files. An episode waits
  until the previous one is done/failed (its summary feeds the next), so a series is written in order.
- **Queue** (`queue.py`): `POST /api/original/series/{id}/episodes {count, start_date, scenes}` creates one durable
  `ORIGINAL_EPISODE` job per episode in the existing `JobManager` (retries x2, rehydrates after a restart) with one publish slot
  per day at 18:00; plus `POST /api/original/series`, `GET /series`, `GET /series/{id}`, `GET /jobs`. Channel presets are the
  same store as the anime review (`/api/anime/review/channels`). Desktop: Quick Actions -> "Original Stories" (create a
  series, queue N episodes, watch the jobs); `tsc --noEmit` is clean.
- Tests: 9 new (store/path safety, portraits shared, continuity prompt, ordering/wait, queue through the JobManager,
  rejects); related suites still pass.

Real run (isolated app data, local qwen3.5:9b + ComfyUI + Kokoro): created the series "Moon Tales" (bedtime, "a sleepy fox who
collects lullabies") in 22 s and queued 2 episodes of 3 scenes. **Both jobs SUCCEEDED unattended in about 20 minutes total**:
episode 1 "The Song of the Silver Leaves" (15 panels, 4.0 min video, 1080p, 7157 frames, -16.1 LUFS) and episode 2 "The Moonbeam
Waltz" (14 panels, 3.0 min, -16.0 LUFS) with publish slots 2026-11-10 and 2026-11-11 18:00. Episode 2 continued from
episode 1's summary with the same cast and places, and the three portraits were byte-identical across both episodes (reused,
not redrawn); Pip is recognisably the same fox in both. Package has the channel's tags and footer, an AI-content disclosure and
3 chapters.

Not done / honest limits: **no YouTube upload** (publish slots are a plan, not a schedule that posts - that needs Google OAuth
and the Data API, with the API-audit caveat); the consistency scores of this run are only 0.33-1.0 (mean about 0.6) because
the check is noisy and the generated looks were hard to draw; episodes of 3 scenes are 3-4 minutes, real ad-eligible videos need
8+ scenes (about 20+ min of generation each); a failed episode lets the next one start without its summary, and the retry
then runs out of order; series are not per-user or deleted/edited from the UI; channel watermark is not applied to
original-story videos; the UI was type-checked, not opened; nobody has listened to the voices or read the stories for quality.

## YouTube upload (added after S6)

`engine/youtube/` (`auth.py`, `client.py`), `engine/original/upload.py`, routes `PUT /api/youtube/client`,
`GET /api/youtube/status`, `POST /api/youtube/connect`, `POST /api/youtube/disconnect` and
`POST /api/original/series/{id}/episodes/{n}/upload` (starts a background upload; poll the series for `upload_status`,
`youtube_url`). Desktop: "Original Stories" screen -> YouTube section.

**One-time setup (yours; I cannot do it for you):** in Google Cloud Console create a project, enable *YouTube Data API v3*,
configure the OAuth consent screen (add yourself as a test user while the app is in testing), create an *OAuth client ID* of type
*Desktop app*, paste the client id and secret into the screen, press Connect, approve in the browser. Scope requested: `youtube.upload`
only. The secret and tokens are kept in the app-data config folder, never returned by the API or logged. Note that an app left in
"testing" mode has refresh tokens that expire after about 7 days.

How it behaves: OAuth with a loopback redirect and PKCE; resumable upload in 8 MiB chunks that resumes from the byte the server
has after a network error or 5xx; custom thumbnail (<= 2 MB; failing to set it does not undo the upload); metadata checked
(title <= 100, description <= 5000 bytes, tags fitted into 500 characters). **Everything uploads PRIVATE by default.** A public
upload or a scheduled release (private + `publishAt` at the episode's slot, 20 minutes or more in the future) is refused unless
`confirm_public` is sent, the desktop button asks for confirmation, and a second upload of the same episode needs `force`.
`made_for_kids` has no default (a legal declaration only the channel owner can make) and `containsSyntheticMedia` is set.
Upload is never part of the episode queue: producing and publishing are separate decisions.

Verified: 20 mock-server tests (PKCE URL, code exchange with verifier, state-mismatch rejection, refresh keeps the refresh token,
chunking, resume after 503, give-up, quota message, thumbnail limits, privacy gates, double upload, failure recorded, secrets not echoed,
route refusals) and concurrency of episode records; `tsc --noEmit` clean. **NOT verified against the real YouTube API** - that needs
your OAuth client. Facts I could not settle: Google's docs currently list `videos.insert` at 1 unit in a separate "Video Uploads" bucket
(100 calls/day) and say unverified projects are not forced private, while older text said the opposite; check on the first upload.
While building it a real bug surfaced: two episode jobs writing `series.json` at once crashed on Windows (shared temp file) - the store
now locks read-modify-write and uses unique temp names (covered by a concurrency test).
Not covered: the anime-review videos (the module is generic but only the original-story route exists), comment replies, analytics.

## Picture/narration match (fix after the first real episode, 2026-11-03)

Reported by the user: the narrated sentence ("Pip closes his eyes, drifting peacefully into dreams...") did not match the picture on
screen. Diagnosis on the real episode: one image stayed up 13-19 s while 2-3 sentences played, and its prompt came from a separately
written `action`, not from the narration; the shot for that sentence was a wide group shot.

Fix (`engine/original/beats.py`, wired into the episode run and the API as `POST /story/{slug}/beats`): each panel's narration is
split into beats of at most ~24 words; each beat gets its own picture and a brief written FROM the spoken text (shot, who is
visible, pose/expression, key things that must be visible). Rules that do not depend on the LLM: a moment about one named character's
eyes/sleep/expression must be a close/medium shot of that character alone; requirements like "eyes closed", "sleeping", "yawning",
"smiling", "tears" are detected by pattern from the words and always added (weighted 1.4, with "open eyes" negated); the character
portrait pin is lowered for such poses (it was forcing open eyes); a failed brief falls back to the spoken words themselves. The
art step then asks the vision model whether the key visuals are visible and redraws (2 attempts) when not; the identity score no
longer triggers redraws (too noisy), only what the narration says does.

Real result, Moon Tales episode 1 rebuilt: 15 panels -> 30 narrated moments, picture changes every 7.9 s on average (was ~15 s),
3:57 video, 7131 frames, -16.1 LUFS. The user's sentence now shows Pip close-up, asleep, eyes closed. Contact sheet of 6 beats vs
their sentences: 4 match well (sleeping Pip, Barnaby stepping into Pip's shadow, the glowing basket, Barnaby whispering), 1
abstract line ("he realizes that if the forest stops its noisy song...") has no good picture, 1 ("He drifts into a slumber") first
missed the sleep rule (added "slumber/doze/nods off") and now shows a sleeper, though it is the girl character, not Pip.
Vision match score mean 0.62 with 12 of 30 beats still under the 0.6 threshold after retries - the 9B vision model is a noisy judge and
the briefs' key visuals often describe the bible instead of the sentence, so treat those scores as a coarse signal and skim the
video. Cost: about 1 minute per picture (2x the pictures plus checks), ~20 min for a 4-minute episode. Abstract sentences, several
characters in one shot and "he/she" without a name remain the weak spots.

## Generic picture pipeline v2 (2026-11-03): the system writes the prompts, for any story

The user's requirement: images must follow the narration for ANY future story, with detailed prompts produced by the tool itself
(not typed by hand per chapter), carrying consistency, actions and emotions. The first fix (one picture per narrated moment) was
not enough: on a brand-new horror story (a night-shift nurse; different genre, cast and setting) the pictures showed the wrong
people, the wrong place and bizarre camera angles. What was wrong and what the tool now does by itself:

1. **Narration must be drawable** (story engine): every caption has to name the characters on screen and describe what can be SEEN
   (body, face, eyes, objects, place); abstract captions ("realizes", "sanctuary", "profound") and captions that name nobody are
   rejected and rewritten. The new horror story's captions came out concrete.
2. **Shot director** (`beats.py`): per narrated moment (<= ~24 words) an LLM writes a structured `ShotSpec`: shot, camera, who is
   on screen and where (max 2), each character's pose, expression and action, specific place details, lighting, mood and the
   phrases that must be visible. Hard rules in code: every named character must be on screen and nobody else; a narration that
   names nobody is a wide shot of the place with no characters; one character's eyes/sleep/expression = close-up of that character
   alone; objects need a medium/wide shot; eye-level camera unless the text says otherwise; pose words ("closes his eyes", "asleep",
   "yawns", "smiles", "cries", "slumber") always become required visuals; the previous shot is shown for continuity.
3. **Prompt composer** (`shotspec.py`): turns the spec into the image prompt deterministically, most important first and inside a
   word budget (subject, pose, expression, action, visible items, place, light, camera, then style): a vocabulary maps plain words to
   booru tags, weights the narration's requirements, negates "open eyes" for closed-eye shots, drops dutch angles (they distort anatomy).
4. **Characters** carry `species` and `gender`; the bible must decide man/woman for humans (a missing gender produced a grey-haired man
   drawn as a girl); kind-of-person tags (old man, little girl...) go in every prompt and portrait.
5. **Verification loop** (`art.py`): each picture is described by the vision model in free text, a text judge compares that to the
   spec's required items, and a mismatch redraws (3 attempts) with the missed items weighted and the portrait pin loosened.
   Description, score and misses are stored per picture.

Real result, new horror story, first 4 panels (8 pictures, 13 min): scene-setting beats are now empty corridors (no wrong people),
Elena appears alone exactly when named, the corridor, fluorescent lights, scrubs and stethoscope are right and consistent, reading the
logbook is shown. Still wrong: objects that matter (the silver bell she looks up at) are not drawn, "scans the empty hall" gives a
messy pose, and the vision judge still scores most pictures 0.5, so 7 of 8 are flagged for review. The cause is the image model: SDXL
anime follows tags, not sentences, and drops objects and complex actions. The honest next step is a prompt-following model
(e.g. FLUX.1 schnell, Apache-2.0, ~12 GB) or pose/object control (ControlNet), both extra downloads that need approval.

## FLUX.1 schnell engine (2026-11-03)

Installed (approved): `flux1-schnell-fp8.safetensors`, 17.24 GB, FLUX.1 schnell (Apache-2.0) from `Comfy-Org/flux1-schnell`, in
`ComfyUI\models\checkpoints` (the download needed about 75 min at 3.3 MB/s). New approved workflow `flux_schnell` (4 steps, cfg 1,
1344x768, multiples of 16). `ComfyRunner` picks FLUX automatically when its model is present (`PANELFLOW_IMAGE_ENGINE=auto|flux|sdxl`
forces a choice) and the prompt composer then writes plain English instead of tags (`shotspec.compose_natural`: framing, each
character with the SAME description sentence every time, left/right placement, pose/expression/action, setting, lighting, mood, a
"must clearly show" list, anything the last attempt missed, no-text constraints). The SDXL anime + IP-Adapter path remains the
fallback. FLUX has no face-pinning (IP-Adapter is SDXL-only): consistency comes from the identical character sentence.

Real A/B on the same 8 directed beats of the hospital story (identical shot specs):

| | SDXL anime + IP-Adapter | FLUX schnell |
|---|---|---|
| judged match to the shot spec (mean) | 0.51 (7 of 8 flagged) | **0.82 (2 of 8 flagged)** |
| time for 8 pictures | 13 min (3 attempts most) | **6 min** |
| right place (arched windows, peeling yellow paint, fluorescent tubes) | no | **yes, every picture** |
| right person, outfit, props (scrubs, stethoscope, clipboard, logbook) | partly | **yes** |
| silver bell she looks up at | not drawn | small bell above her head, pose only partly right |

Remaining weaknesses: face consistency is looser than with the IP-Adapter (hair length varies between pictures; same person
recognisable by outfit and features, not pixel-consistent); the judge still flags 2 pictures; two-character panels on FLUX were not
tested yet; the fox bedtime episode was not regenerated with the new director + FLUX (its stored beats predate the shot director).
A FLUX identity-pinning adapter (XLabs/InstantX IP-Adapter for FLUX, plus a custom node) is the next option if consistency needs it.

## Image reviewer (user request, 2026-11-03): analyse, compare, get a confidence, then accept or regenerate

The user showed one FLUX picture (narration: "Elena turns her head upward, her eyes locking onto the single silver bell hanging high
on the wall") and asked whether it was acceptable and for a review step that analyses and compares every picture against the
narration and decides from a confidence. Verdict on that picture: **not acceptable** - the bell was a speck on her head, she
looked sideways. Why the old loop accepted it: the director's key-visual list had lost the bell (phrases over 5 words were dropped),
the judge marked nearly everything missing, and the loop kept the best of three anyway.

`engine/original/review.py`, used inside `generate_art` for every directed picture:
1. **Claims** from the narration itself, independent of the shot director (LLM), then cleaned in code: positive statements only, no names
   or negations, each must share content words with the narration (a small model otherwise parrots the cast list - seen once).
2. **Witness A**: the vision model answers one numbered question per requirement (yes/partly/no + the visible evidence).
3. **Witness B**: a free description of the picture, and a text-only model says whether it states each requirement.
4. **Verdict per requirement**: both agree -> shown/missing (confidence 0.9); they disagree -> partial or low confidence.
5. **Decision**: accept (no critical miss, score >= 0.75, confidence >= 0.6); accept_low (no critical miss, score >= 0.6, flagged);
   otherwise regenerate. Retry ladder: weight what was missed; 3rd attempt: "Most important: ..." first, fewer details, a wider frame.
   A picture still failing after the last attempt is **needs_review**, never silently accepted.
6. Everything is saved per picture (`art.json`: status, claims, every requirement with both answers) and `review_report.html` shows each
   picture beside its narration, the decision and the evidence.

Real run, hospital story, 8 beats on FLUX (9.5 min): 4 accepted, 2 accepted with low confidence, 2 needs_review. The user's picture
(p004_1) is now: Elena looks up at a silver bell hanging high on the wall - accepted on the first attempt (score 0.96, confidence 0.68).
The two needs_review are honest: "the windows rattle" cannot be drawn, and "her hand touches a metal desk" is not clearly shown.
Limits: the reviewer is the same 9B vision/text model family as the other steps, so confidence is a calibrated-by-agreement signal, not
ground truth; it adds ~20 s per attempt; claims about sound or ideas are flagged for a human instead of fixed.

## One art workflow (2026-11-06): Qwen Image 2.1 for everything

There were four copies of "patch a graph, submit to ComfyUI, poll, download": `ComfyRunner` (Qwen / FLUX / SDXL branches), ChronoFlow's
hard-coded Qwen and FLUX graphs (served twice: the aiohttp `server.py` and the FastAPI router), the Comfy image screen's
`generate_image_operation` (`manga_image_generation`), and three private poll loops in `ComfyRunner` itself. Now:

- `engine/comfyui/art.py` - `ArtEngine.generate(...)` is the only text-to-image path; it runs the registered `qwen_image_21` workflow,
  rejects sizes the workflow cannot honour (multiples of 16, 256-2048) before any GPU time, verifies the returned PNG, and
  `ArtEngine.run(...)` is the shared submit/poll/download used by the SDXL edit tools too.
- Callers: `ComfyRunner.generate` (Original Stories), `ChronoFlowPipeline.generate_art_image` (ChronoFlow API + MCP tool),
  `generate_image_operation` (Comfy image screen, job-queued, asset persisted), YouTube thumbnails (`packaging.py`, which maps old saved
  `workflow_id`s to the single workflow), autopilot.
- Removed: `flux_schnell`, `flux_pulid`, `manga_image_generation` (registry entries, files), `PANELFLOW_IMAGE_ENGINE=flux|auto`, ChronoFlow's
  `build_qwen_image_prompt` / `build_flux_image_prompt`, the `model` / `steps` options of the image APIs and MCP tools, the FLUX/PuLID scripts.
- Verified on the real engine: a ChronoFlow MCP image (1344x768) and an Original Stories picture (one attempt) were made by `qwen_image_21`
  only (embedded ComfyUI workflow read back from the PNGs); the ChronoFlow gallery lists the new `art_*` files.
- **Not unified yet (needs a decision):** the SDXL stack - `anime_sdxl`, `anime_sdxl_ipa(2)`, `anime_sdxl_controlnet` (relabelled
  `sdxl_conditioning`), `anime_sdxl_inpaint`, `anime_alpha_matting` - and ChronoFlow's own FLUX-checkpoint inpaint graph. ControlNet pose/depth,
  IP-Adapter, inpaint and matting have no Qwen equivalent, and about a dozen tests of the rigging work are built on them.

## Still, whole pictures (2026-11-06): no zoom, no pan, no shake, no cropping

Reported on the cat explainer: pictures shook a little and parts of them were cut off (top/bottom). Causes, measured on the real video: the
render zoomed/panned every picture with `zoompan` (it moves in whole-pixel steps, which jitters, and it crops the edges: up to 12%),
and square or portrait pictures (11 of 24 here) were centre-cropped to 16:9, cutting heads, glasses and feeders.

Now `engine/original/video.py` shows every picture whole and still: a picture within 3% of 16:9 is scaled to fill (the art step's
1344x768 is 1.6% off, not visible); any other shape sits centred on a blurred, darkened copy of itself. `zoompan`, the 4-motion cycle and
the `action_shake` effect are removed (the older "push-in / pan" description in S3 above is history). The cached-segment key includes
`RENDER_LOOK`, so clips rendered by an older look are never reused. Measured per panel (picture change between near the start and near the end,
captions masked): old video mean 33.6 (max 50.9), new video mean 0.10 (max 0.55 = encoder noise). The new file is 22 MB instead of 120 MB.
Not changed: the anime-review renderer (`engine/anime/review/render.py`) has its own slow zoom.

## Image refinement (2026-11-06): review any image, keep every candidate, plan the correction, repair on the art model

Plan and research: the investigation report of 2026-11-06 (reuse the reviewer, no new model). Built in small committed steps:

- **Review of any image against any prompt** (`review.evaluate_prompt_image`): requirements from the prompt, five-way status (correct / missing /
  incorrect / uncertain / not_verifiable), a model-reported box (validated, never invented; none for an absent thing), severity,
  `repairable_locally`. One full review took ~70 s on `qwen3.5:9b` (9 requirements + anatomy + contact + boxes). Measured on the real model:
  `qwen3.5:9b` boxes on a 0-1000 grid matched what is in the picture (head, paw, plant, cat, table).
- **Fixed false anatomy flags:** the negation check split on commas, so "no duplicate heads, fused faces, or polycephaly" flagged polycephaly.
  Three stored cat-table panels were flagged that way. Two more (contact checks) were re-audited without the story's claims, so they are NOT shown fixed.
- **History** (`ArtRecord.iterations`, `panels/_candidates/<panel>/`): every generated or repaired candidate is kept with seed, prompt, size, engine,
  review summary, repair parent and mask; a re-run never overwrites; an older picture is archived as `imported`.
- **Planner** (`engine/original/planner.py`): pure rules (accept / repair_local / regenerate / accept_low / human_review). Not wired into `generate_art` yet.
- **Qwen masked redraw** (`qwen_image_21_inpaint`, `ComfyRunner.inpaint_qwen`, purpose `inpaint`, the art model's own files, nothing to download).
  Measured on the real engine with the installed weights: (1) giving the picture as a *reference* plus an instruction ("make the collar red",
  "remove the plant") **ignores the instruction** and returns a blurrier copy; (2) the picture as a reference seen only by the text encoder draws a
  different scene; (3) **VAE-encode the picture + noise mask + a prompt that describes the whole picture with the corrected area** works: ~20-30 s, the
  collar turned red with its tag intact. Outside the mask the raw result drifts by 0.8-0.9 (0-255 mean), so the original is spliced back
  (`review.splice_repaired_image`): 0 pixels changed outside the mask. Weakness: the redraw also changes what is inside the mask box (a paw
  shifted a little), so keep boxes tight. `generate_art` still repairs with the SDXL inpaint until the loop is wired.
- **Generic loop** (`engine/original/refine.py`): `refine_image` (generate -> review -> `plan_correction` -> repair | redraw | stop, callables injected) and
  `refine_prompt_image` / `refine_art_image` for any prompt. Opt-in everywhere, default off: `generate_art(..., refine=True)` or `PANELFLOW_REFINE_LOOP=1`
  (directed panels; repairs only on the Qwen engine), `generate_image_operation(..., refine=True)` (Comfy image screen operation; candidates under
  `generated/comfyui_candidates/`, iterations in the asset provenance), `ChronoFlowPipeline.generate_art_image(..., refine=True)`. If the local vision model is
  unreachable `refine_art_image` raises rather than returning an unreviewed picture. Not exposed in the HTTP/MCP schemas or the desktop UI yet.
- **Real runs, live engine** (Qwen art + `qwen3.5:9b` review, 1344x768): a 10-requirement prompt was accepted on the first generation in 58 s; a 9-requirement
  prompt (mug in the right hand, umbrella in the left, crowned cat with a collar on a table, cactus on the sill) was first marked `needs_review` after
  3 redraws (176 s) although the picture matched: the contact audit read "the scene must take **place** in a kitchen" as holding an object called "place".
  Fixed (idiom objects such as place/part/care are never held things); the same prompt and seed now accept in 55 s.
- **Real repair inside the loop** (seeded with a real picture whose cat has a blue collar, prompt asks for a red one; review, planner, Qwen repair and
  re-review all real, 105 s): the reviewer marked the collar failed with a box, the planner chose `repair_local`, the collar became red, the re-review passed,
  the repair was kept; 0 pixels changed outside the mask (3.4% of the picture). **Quality is not clean:** the redraw also changed the raised paw and
  tongue inside the mask, and the gold tag came out small and faint, which the reviewer still accepted ("gold tag: correct"), so the 9B judge is lenient
  on small details. Keep boxes tight and check repaired pictures by eye. Still untested on a real engine: a full redraw (regenerate) that fixes a real failure.
