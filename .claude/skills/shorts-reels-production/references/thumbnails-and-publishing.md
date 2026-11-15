# Thumbnails, covers and upload copy

`[research]` = from web search (vendor blogs, no primary platform docs): verify in the app. `[verified]` = done in this tree.

## Thumbnail / Reel cover rules `[research]` for the principle, `[verified]` that the pipeline produces them
- One huge expressive face (shock, fear, anger) or one clear clash; saturated high-contrast colours; clean background; 1-4 bold words.
- Do not overpromise: a thumbnail that sells more than the video delivers gives clicks and poor retention.
- Format: 1080x1920 (9:16). YouTube Shorts accept a custom thumbnail now. Instagram's profile grid shows a taller 3:4 centre crop (about 1080x1440), so keep the face and title inside y 240-1680.
- The art model draws NO text. `tools/reels/thumbs.py` draws two variants per reel (`art_a.png`, `art_b.png`), then `compose` adds the title in Impact with a 22 px black outline and drop shadow. Titles go where the picture is empty: set `FINAL[slug] = (variant, y)` after LOOKING at both variants; two-line titles cap at 200 px so they end before y 1680.
- Prompt shape (see `THUMBS` in `thumbs.py`): shared `LOOK` + a scene with the biggest emotion of the reel. Always show the prop that carries the idea (battery icon, remote, suitcase). If a key prop does not render, rewrite the scene prompt with the prop beside the character, large and "fully visible" (the brain-in-the-head version failed twice, the brain-beside-the-student version worked).
- Pick the winner by eye on a contact sheet; compare variants A/B in YouTube Studio once real views exist.

## Title, description, tags (`tools/reels/publish.py`)
- YouTube title: hook first, 1-2 emoji, a curiosity bracket, <= 100 characters (the script asserts it); real titles stay near 50-65.
- Description: line 1 = the joke or promise; one question as a comment prompt; one subscribe line; three hashtags (YouTube shows the first three above the title). No invented statistics, no claims the video does not keep.
- Tags: 8-16, specific first, generic last, total <= 500 characters (asserted). Include the audience phrase ("husband wife comedy") and the format ("shorts", "stick figure").
- Instagram: a short caption with the joke, 6-8 hashtags, tag-a-friend ask. A pinned comment with a question per reel.
- Output: each reel's `PUBLISH.md` and `output/reels/_READY_TO_UPLOAD/PUBLISH_ALL.md`.

## Before the owner uploads
- Altered/synthetic content disclosure on YouTube and the AI label on Instagram: voice and pictures are AI.
- Upload PRIVATE first; watch it once with sound; then publish. Public or scheduled releases need the owner's explicit confirmation. "Made for kids" is the owner's own declaration, no default.
- Monetisation: YPP thresholds above. YouTube may treat many near-identical templated videos as repetitive/inauthentic content: see the variety rule in `concept-formula.md`.
- Licences for Qwen-Image (research-only), H3-Image/H3 video, ACE-Step and the voice-reference recordings are unresolved (`SKILL.md` rule 7).
