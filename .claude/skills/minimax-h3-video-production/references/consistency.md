# Character and scene consistency

A prompt cannot guarantee identity. Say what each layer can and cannot enforce.

| Requirement | Enforced by | Prompt role | Checked by |
|---|---|---|---|
| Face, hair, outfit, palette at frame 0 | The **first frame** (Qwen via `ArtEngine`, ShotSpec from the story bible; IP-Adapter/PuLID/inpaint only on the still-image side) | None: do not re-describe | You, by eye, before spending GPU on the clip |
| Same look in every frame of the clip | Short clips (3-5 s), one action, static camera, first frame; `minimax_h3_facerefine_i2v` for faces (untested on drift here) | "consistent character appearance in every frame" is weak; the real levers are length and action size | `clip_eval` drift flag (colour histogram vs frame 0) + contact sheet |
| Same look across shots | A fresh first frame per shot from the same bible, same seed policy, same style words | Same sentence per character/location | Compare first frames of neighbouring shots; drift at the cut (not built) |
| Lighting continuity | First frame + "lighting stays the same" | Name the one light change, if any | Drift/flicker flags; contact sheet |
| Character-to-character layout | First frame composition | Say who moves, who stays | By eye |
| Voice identity | One fixed Kokoro voice per character (`film.DEFAULT_VOICES`), anchored with `MiniMaxH3AddGuide` | Name the speaker | ASR + listening (nobody has listened yet) |

## What we saw `[verified]`
- Colour/lighting collapses inside a clip: `p004_1` (hair turned blue, water curtain), `p019_1` (went dark and back), Dawn Gate `p070/p072` (light shafts changed the whole picture). The drift trigger caught all of them; it cannot say outfit vs lighting.
- Action beats invent things H3 sees implied in the picture (glass -> juice).
- Faceless speakers get a drawn mouth when their voice is anchored (`film.FACELESS`): anchor silence, mix the voice at the master.

## Not available locally `[verified]`
Reference images/video/audio for identity (Ref2VA) - no weights. Last-frame anchoring - no registered workflow. Character sheets therefore help only through the first frame. `MiniMaxH3AddGuide` can anchor a short clip at a frame index (tail of the previous clip) `[hypothesis]`: test on two clips before relying on it.

## Protocol
1. Character card (from the story bible): id, age group, face/hair, outfit, colours, accessories, voice. Reuse the exact words in every first-frame prompt.
2. Per shot: state card (`multi-clip.md`) - who, where in frame, scale, outfit, light.
3. After generation: `evaluate`; open the contact sheet; compare frames 0 and last against the card.
4. On drift: redraw the first frame or shorten/simplify the action before touching H3 settings (`regeneration.md`).
