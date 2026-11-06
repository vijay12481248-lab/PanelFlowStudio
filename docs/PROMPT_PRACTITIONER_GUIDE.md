# PanelFlow Studio: Prompt Engineering & Directorial Practitioner Guide

**Version**: 1.0.0  
**Status**: Authoritative Architectural Standard  
**Target Systems**: Qwen Image 2.1 (`ArtEngine`), MiniMax Fast H3 Turbo (`ChronoFlow` / Video Pipeline), Legacy SDXL (`anime_sdxl_*`), Two-Witness Review Engine (`engine/original/review.py`)  
**Scope**: Requirements R1, R2, R3, R4 (Milestone M1 Baseline)

---

## 1. Executive Summary & Purpose

PanelFlow Studio is a local-first generative workstation engineered to transform manga, comic scripts, and original stories into publication-grade narrated videos and comic chapters. Running on local consumer hardware (NVIDIA RTX 5060 Ti 16 GB, 32 GB RAM) with dedicated local inference engines (FastAPI backend, Ollama `qwen3.5:9b` multimodal vision model, ComfyUI flow-matching and diffusion pipelines), the system demands deterministic control over visual consistency, character identity retention, and anatomical precision across 30 to 50 sequential panels per episode.

Modern diffusion transformers and flow-matching backends—principally **Qwen Image 2.1 Turbo** for image generation and **MiniMax Fast H3 Turbo** for image-to-video synthesis—possess immense generative capacity. However, when unguided or driven by naive qualitative prompts ("masterpiece", "high quality anime girl", "ultra-detailed"), these models suffer from well-documented generative failure modes:
1. **Art Style Drift**: Rapid oscillation between 2D cel animation, semi-realistic digital illustration, and 3D CGI plastic textures across consecutive panels.
2. **Facial Morphing**: Degradation and drift of facial geometry, bone structure, eye shape, and hair styling across shots of the same character.
3. **Anatomical and Digit Aberrations**: High-frequency topological failures including polydactyly (6–7 fingers), syndactyly (fused fingers), floating limbs, and conjoined heads.
4. **Spatial Decoupling**: Handheld props floating in mid-air adjacent to open palms ("hollow grasp") and unanchored environmental objects defying gravity.
5. **Compositional Clipping**: Severe decapitation of character crowns/hair or amputation of feet caused by aspect-ratio and canvas mismatches.
6. **Temporal Video Warping**: Frame-to-frame facial melting, jittery artifacts, and erratic camera jump cuts during temporal motion synthesis.

This guide establishes the **definitive engineering reference** for prompt construction, directorial beat compilation, and defect suppression in PanelFlow Studio. It codifies:
- The **17-Failure-Mode Generative Defect Taxonomy** with root cause analyses, mitigation directives, and negative suppression tokens.
- The **6 Core Engineering Principles** establishing physical optics over buzzwords, 4-tier invariant styling anchors, the character unnaming protocol, kinematic contact bindings, dynamic 1-MP resolution bucketing, and video directorial kinematics.
- The **Master Genre Visual Style Anchors Table** covering all active production genres (`bedtime`, `horror`, `mystery`, `fantasy`, `mythology`, `vox`).
- The **Master Camera Framing & Composition Anchors Table** governing shot geometry, headroom margins, and safe action zones.
- The **Review Witness & Quality Gate Alignment Matrix** directly coupling prompt guardrails with the dual-witness review system in `engine/original/review.py`.
- The **Target Model Parameterization Matrix** formalizing syntactic dispatch across Qwen Image 2.1, MiniMax H3, and Legacy SDXL.
- **Reference Multi-Panel Implementation Walk-Throughs** illustrating production-ready prompt sequences.

---

## 2. Generative Defect Taxonomy

Generative defects in PanelFlow Studio are classified into 17 formal failure modes spanning 6 operational categories. Each defect is assigned a canonical identifier, analyzed for its underlying latent diffusion root cause, and paired with explicit positive prompt mitigations, negative suppression tokens, and review witness verification criteria.

### 2.1 Master Defect Taxonomy Table

| Defect Category | Failure Mode Code | Observable Failure Mode | Generative Root Cause | Positive Prompt Mitigation Rule (Positive Anchor) | Negative Anchor (Suppression Tokens) | Review Witness Verification Rule |
|---|---|---|---|---|---|---|
| **Art Style** | `DEF-STYLE-001` | **Medium Leakage (3D CGI / Photorealism in 2D Anime)** | Missing medium constraints; default CLIP/VLM weights favoring dominant photographic training datasets | Specify explicit 2D medium: *"Hand-drawn 2D anime illustration, flat cel-shading, matte gouache background, clean graphic rendering, zero 3D CGI, zero photographic textures"* | `3d render, cgi, photorealistic skin, octane render, unreal engine, claymation, airbrushed textures, plastic skin, ray tracing` | Witness B description must assert 2D anime aesthetic; reject photographic, 3D CGI, or realistic skin terminology. |
| **Art Style** | `DEF-STYLE-002` | **Line-Work Degradation (Sketchy / Double Contours)** | Low-frequency noise in latent initialization; vague style descriptors associating with concept art drafts | Mandate line physics: *"Clean crisp dark ink outlines, uniform stroke weight, defined line contours, smooth finished linework, sharp vector-like silhouette edges"* | `sketchy outlines, double lines, messy line art, dirty sketches, uninked lines, scribble, draft, rough pencil, unfinished` | Witness B description verifies line clarity; rejects sketchy, rough, or unfinished contour edges. |
| **Art Style** | `DEF-STYLE-003` | **Palette Drift across Shots (Mismatched Color Grading)** | Omission of global scene lighting/color parameters; independent latent seeds sampling divergent color temperatures | Enforce immutable scene palette anchor: *"Cohesive scene color palette featuring [Palette Tokens], clean two-tone cel shading, consistent ambient tone, [Lighting Color Temperature]"* | `color bleeding, mismatched color grading, washed out colors, oversaturated neon, chromatic aberration, random color shift` | Cross-check panel color tones against scene location look in `story.bible.locations` and lighting spec. |
| **Character Identity** | `DEF-ID-001` | **Facial Morphing & Structural Drift** | Incomplete character description allowing model to invent facial geometry across shots | Lock invariant facial structure: *"Specific facial structure: [Mandible/Jaw Shape] face, [Color/Geometry] eyes with [Brow Detail], [Length/Parting/Texture] hair, [Distinguishing Mark]"* | `morphing face, inconsistent face, generic face, distorted facial features, changing eye color, changing hair style, different person` | Vision check verifies core identity tags (`VISIBLE_TAGS = 2` for close, `3` for medium/wide) against `Character.look`. |
| **Character Identity** | `DEF-ID-002` | **Proper Noun Semantic Confusion (Visual Literalism)** | Diffusion models interpreting character proper names as literal nouns (e.g. "Biscuit" $\rightarrow$ cookies, "Rose" $\rightarrow$ flower bouquet) | Execute mandatory unnaming filter (`shotspec.unname`): Replace proper names with descriptive role noun phrases (*"a little girl with short brown hair"*) | `[Character Name] as literal object, biscuit cookies, floral roses, hunting rifles, literal object confusion` | Prompt must contain zero character proper names; regex scan verifies all character references sanitized to descriptive nouns. |
| **Character Identity** | `DEF-ID-003` | **Multi-Character Feature Bleeding (Attention Cross-Contamination)** | Cross-attention cross-contamination between adjacent character noun-adjective tokens in latent space | Enforce strict spatial coordinate partitioning: *"On the left side: [Full Char A description, pose, attire]. On the right side: [Full Char B description, pose, attire]. Clear physical separation"* | `character blending, merged identities, shared features, duplicate faces, hybrid characters, feature swapping` | Check panel for exactly 2 distinct characters; confirm features of Char A do not appear on Char B. |
| **Character Identity** | `DEF-ID-004` | **Pose/Expression Identity Override (Frontal Gaze Bias)** | Reference portrait conditioning forcing open eyes or frontal gaze on sleeping or turned-away poses | Apply pose-sensitive weighting attenuation: For closed eyes, asleep, or rear views, inject *"closed eyes, serene face"* and attenuate portrait weight to 0.3 | `looking at viewer, direct eye contact, open eyes, frontal gaze, staring at camera` | Witness A & B verify eyes closed; flag failure if model produces open eyes or frontal gaze. |
| **Anatomy & Digits** | `DEF-ANAT-001` | **Polydactyly / Syndactyly (Extra/Fused Digits & Claw Hands)** | Complex hand geometry underspecified in high-frequency latent areas; lack of 3D skeletal constraints | Enforce exact digit and hand specification: *"Natural human hand anatomy, exactly five distinct separated fingers including thumb on each hand, clear knuckles, natural relaxed grip"* | `extra digits, fewer digits, missing fingers, fused fingers, six fingers, polydactyly, syndactyly, deformed digits, webbed fingers, mutated hands, claw hands` | VQA Question 4: *"natural hands and feet with anatomically correct digits and no extra or fused fingers"*; match `DEFECT_KEYWORDS["distorted_digits"]`. |
| **Anatomy & Digits** | `DEF-ANAT-002` | **Floating / Disconnected Limbs & Topology Aberrations** | Lack of global skeletal graph enforcement; limbs generated without topological connection to torso | Mandate unbroken skeletal connectivity: *"Continuous articulated limb structure, forearm connecting seamlessly into wrist and hand, natural biological joint angles, plausible human skeletal anatomy with exactly two arms and two legs"* | `floating hands, detached limbs, severed hands, disconnected wrists, amputated arms, extra arms, extra legs, three arms, bent backwards, impossible joints, twisted limbs` | VQA Question 2 (`extra_limbs`), Question 3 (`missing_limbs`), and Question 5 (`limb_topology`). |
| **Anatomy & Digits** | `DEF-ANAT-003` | **Polycephaly & Facial Duplication (Conjoined Heads)** | Subject token repetition triggering multiple cranial centroids in cross-attention map | Enforce singular subject architecture: *"Single head per person on a natural neck, single face, solitary subject focus, perfectly proportioned cranial anatomy, zero duplicate heads"* | `polycephaly, duplicate heads, two faces, multiple heads, fused heads, conjoined twins, second head, double head` | VQA Question 1: *"single head per person or creature with no polycephaly, duplicate heads, or fused faces"*; match `DEFECT_KEYWORDS["polycephaly"]`. |
| **Spatial Contact** | `DEF-SPAT-001` | **Unanchored Floating Objects (Gravity Physics Failure)** | Missing gravitational and support physics in prompt; objects generated as isolated visual nouns | Explicit surface contact and shadow directives: *"Resting flat and firmly on the [Surface Name], visible dark contact ambient occlusion shadow beneath the base, physically supported by the ground plane"* | `floating object, hovering in air, unanchored object, levitating, suspended in mid-air, floating cup, floating book, unsupported floating` | Spatial Audit 1: *"all objects, props, and furniture are physically supported or resting on surfaces with no unanchored floating objects"*; match `DEFECT_KEYWORDS["unanchored_object"]`. |
| **Spatial Contact** | `DEF-SPAT-002` | **Disconnected Interaction / Hollow Grasp (Air Gap)** | Action verb without explicit kinematic contact directives; model renders prop near open palm | Mandate kinematic contact binding (`compile_interaction_bindings_natural`): *"Fingers firmly wrapped 360 degrees around the handle, continuous physical grasp contact, palm pressing against surface, zero air gap between fingers and object"* | `disconnected grip, hovering near hand, floating prop, gap between hand and object, not touching, detached from grip` | Spatial Audit 2: *"the {obj} is physically held or touched with continuous grasp contact and is not floating or disconnected"*; match `DEFECT_KEYWORDS["disconnected_interaction"]`. |
| **Framing & Crop** | `DEF-FRAME-001`| **Decapitation / Headroom Truncation (Top Edge Clipping)** | Subject scaling exceeds canvas boundaries; model attempts to fill vertical frame height | Mandate headroom clearance directive (`MARGIN_NATURAL`): *"Medium shot from waist up with generous headroom above hair, subject completely within frame, upper canvas boundary positioned at least 15% above crown of head, zero top clipping"* | `cropped head, cut off hair, out of frame top, top boundary clipping, decapitated, partial head` | Verify complete head and hair are visible within safe action area; upper boundary clearance $\ge 15\%$. |
| **Framing & Crop** | `DEF-FRAME-002`| **Extremity / Footwear Truncation in Full-Body Shots** | Generating full-body shot inside wide aspect ratio canvas where vertical pixel budget is constrained | Force Portrait bucket `(832, 1216)` and ground margin: *"Full body shot from head to toe in vertical portrait orientation, visible shoes resting flat on ground plane with generous bottom margin (>= 10% bottom clearance), subject entirely in frame"* | `cut off feet, cropped legs, out of frame bottom, truncated shoes, partial body, truncated limbs` | VQA Question 3: *"complete body structure with no missing limbs... (accounting for frame cropping)"*; confirms shoes and floor contact visible. |
| **Framing & Crop** | `DEF-FRAME-003`| **Lateral Character Crowding & Mutual Occlusion** | Placing multiple characters inside square or portrait canvas with insufficient horizontal pixel budget | Force Widescreen Landscape bucket `(1344, 768)` and spatial positioning: *"Two characters side-by-side with clear horizontal separation. Character A on left third, Character B on right third, spacious room between them"* | `overlapping bodies, crowded framing, occluded characters, merged figures, cropped companion, cramped composition` | Confirm all named characters are visible simultaneously without lateral boundary clipping or mutual occlusion. |
| **Temporal Video** | `DEF-VID-001`  | **Inter-Frame Temporal Morphing & Jitter (Facial Melting)** | Video flow-matching layers lack temporal identity retention; high motion intensity causes cross-frame drift | Mandate temporal consistency tokens and secondary dynamics: *"Consistent character facial appearance across all frames, unbroken facial geometry, natural subtle secondary dynamics (gentle hair and cloth sway), steady 24fps frame rate"* | `morphing face, melted face, flickering facial features, jittery artifacts, twitching anatomy, faceless pedestrians, shape-shifting, temporal noise` | Video motion verification: Confirm subject cranial proportions and features remain invariant across clip duration (124 frames). |
| **Temporal Video** | `DEF-VID-002`  | **Camera Trajectory Instability & Jump Cuts (Erratic Jitter)** | Video prompt lacks explicit optical trajectory and speed constraints; model hallucinates editorial jump cuts | Explicit camera trajectory and motion pacing: *"Single continuous camera take: slow cinematic camera [push_in/pan_right/tilt_up] towards subject, steady optical center, smooth mechanical track, calm gentle pace, zero cuts"* | `fast jerky motion, abrupt camera jump cut, camera jitter, erratic panning, violent camera shake, handheld wobble, discontinuous edits` | Temporal smoothness verification: Zero jump cuts, frame-to-frame rotational jitter, or erratic panning across 124 frames. |

---

### 2.2 In-Depth Failure Mode Analysis & Mitigation Walk-Throughs

#### 2.2.1 Art Style Failure Modes (`DEF-STYLE-001` through `DEF-STYLE-003`)

##### DEF-STYLE-001: Medium Leakage (3D CGI / Photorealism in 2D Anime)
- **Latent Phenomenon**: Pretrained vision-language text encoders (`qwen3vl_8b`) were conditioned on billions of web images predominantly containing 3D game renders, Unreal Engine showcases, and digital photography. Generic evaluative tokens ("masterpiece", "high quality", "detailed") trigger these high-frequency photographic weights, causing 2D anime illustrations to exhibit glossy specular skin, subsurface scattering, and plastic doll textures.
- **Defective Formulation**:
  ```text
  A beautiful anime girl standing in a forest clearing, masterpiece, highly detailed, 8k, realistic lighting, trending on artstation.
  ```
- **Engineered Mitigation**:
  ```text
  Hand-drawn 2D anime illustration, flat two-tone cel-shading, matte gouache background plate, clean graphic rendering. A teenage girl with short brown bob haircut standing in a forest clearing. Crisp dark ink outlines, uniform stroke weight, zero 3D CGI, zero photographic textures, no ray tracing.
  ```
- **Suppression Negative**: `3d render, cgi, photorealistic skin, octane render, unreal engine, claymation, airbrushed textures, plastic skin, ray tracing, subsurface scattering`

##### DEF-STYLE-002: Line-Work Degradation (Sketchy / Double Contours)
- **Latent Phenomenon**: When prompts use loose artistic terms ("manga drawing", "dynamic sketch", "concept art"), the diffusion sampler maps toward early-stage production storyboards. Contours become scratchy, multiplied, or fragmented.
- **Defective Formulation**:
  ```text
  Manga drawing of a young warrior running through the village, dynamic action sketch.
  ```
- **Engineered Mitigation**:
  ```text
  Clean crisp dark ink outlines, uniform stroke weight, defined line contours, smooth finished linework, sharp vector-like silhouette edges. A teenage boy running along a stone village path. Finished anime production cel, zero sketch lines, zero double outlines.
  ```
- **Suppression Negative**: `sketchy outlines, double lines, messy line art, dirty sketches, uninked lines, scribble, draft, rough pencil, unfinished, construction lines`

##### DEF-STYLE-003: Palette Drift across Shots (Mismatched Color Grading)
- **Latent Phenomenon**: Without explicit scene illumination constraints, independent random diffusion seeds sample divergent color modes. A sunset library scene in Panel 1 might render in warm 3200K amber, while Panel 2 renders in cold 6500K fluorescent blue.
- **Defective Formulation**:
  ```text
  The scholar examining an ancient tome on the library bookshelf.
  ```
- **Engineered Mitigation**:
  ```text
  Cohesive scene color palette featuring rich amber, deep mahogany, and antique parchment gold. Clean two-tone cel shading, consistent warm ambient tone. Lighting: soft diffused 3000K lantern glow from top-left, warm contact shadows. The scholar examining an ancient tome on the wooden library bookshelf.
  ```
- **Suppression Negative**: `color bleeding, mismatched color grading, washed out colors, oversaturated neon, chromatic aberration, random color shift, cold fluorescent lighting`

---

#### 2.2.2 Character Identity Failure Modes (`DEF-ID-001` through `DEF-ID-004`)

##### DEF-ID-001: Facial Morphing & Structural Drift
- **Latent Phenomenon**: Vague character descriptors ("handsome hero", "young girl") allow the latent sampler to interpolate arbitrary facial geometry on each seed. Jawline angle, eye shape, and nose bridge drift wildly across shots.
- **Defective Formulation**:
  ```text
  A handsome teenage hero holding a crystal orb, medium shot.
  ```
- **Engineered Mitigation**:
  ```text
  A teenage boy with a sharp angular jawline, almond-shaped emerald-green eyes with delicate dark brows, short spiky auburn hair parted on the left with a forward fringe, and a distinct small horizontal scar over his right eyebrow, wearing a charcoal wool tunic, holding a crystal orb.
  ```
- **Suppression Negative**: `morphing face, inconsistent face, generic face, distorted facial features, changing eye color, changing hair style, different person, round jawline`

##### DEF-ID-002: Proper Noun Semantic Confusion (Visual Literalism)
- **Latent Phenomenon**: Modern LLM and diffusion tokenizers split unfamiliar proper names into subword dictionary tokens. A character named "Biscuit" generates literal confectionery; a character named "Rose" spawns floral bouquets.
- **Defective Formulation**:
  ```text
  Biscuit is sitting on the floor waiting patiently for food.
  ```
- **Engineered Mitigation (`shotspec.unname`)**:
  ```text
  A small orange domestic shorthair kitten with white paws and amber eyes is sitting on the wooden kitchen floor waiting patiently beside an empty ceramic bowl.
  ```
- **Suppression Negative**: `biscuit cookies, baked goods, snacks, food items on floor, literal noun confusion`

##### DEF-ID-003: Multi-Character Feature Bleeding (Attention Cross-Contamination)
- **Latent Phenomenon**: Cross-attention mechanisms calculate attention matrices across all tokens in the sequence. In sentences combining multiple characters, adjectives from Subject A ("blonde hair", "red dress") bind to Subject B ("boy in black suit").
- **Defective Formulation**:
  ```text
  A girl with blonde hair in a red dress and a boy with black hair in a blue jacket talking.
  ```
- **Engineered Mitigation**:
  ```text
  Widescreen landscape shot showing two distinct characters side-by-side with clear horizontal separation. On the left side of frame: a teenage girl with long straight blonde hair and blue eyes, wearing a red cotton dress. On the right side of frame: a teenage boy with short spiky black hair and brown eyes, wearing a navy blue denim jacket. Zero feature blending.
  ```
- **Suppression Negative**: `character blending, merged identities, shared features, duplicate faces, hybrid characters, feature swapping, swapped clothing`

##### DEF-ID-004: Pose/Expression Identity Override (Frontal Gaze Bias)
- **Latent Phenomenon**: Image reference priors (IP-Adapter or character sheets) are typically front-facing portraits with open eyes. When the narrative calls for sleep, weeping, or facing away, the reference prior pulls the eyes wide open, creating disturbing sleep portraits.
- **Defective Formulation**:
  ```text
  The little girl sleeping in her bed at night.
  ```
- **Engineered Mitigation (Pose-Sensitive Attenuation)**:
  ```text
  The little girl with short brown hair sleeping peacefully in her wooden bed, eyes completely closed, relaxed smooth eyelids, serene sleeping facial expression, head resting sideways on white pillow, zero eye contact, no open eyes, looking away.
  ```
- **Suppression Negative**: `looking at viewer, direct eye contact, open eyes, frontal gaze, staring at camera, awake, alert expression`

---

#### 2.2.3 Anatomy & Digit Failure Modes (`DEF-ANAT-001` through `DEF-ANAT-003`)

##### DEF-ANAT-001: Polydactyly / Syndactyly (Extra/Fused Digits & Claw Hands)
- **Latent Phenomenon**: Human hands occupy high-frequency latent territory with 27 degrees of freedom and complex self-occlusion. Without explicit anatomical finger counts and joint descriptors, the denoiser renders plausible skin patches without skeletal logic.
- **Defective Formulation**:
  ```text
  Close-up of a magician casting a spell with glowing hands.
  ```
- **Engineered Mitigation**:
  ```text
  Close-up of a magician casting a spell. Natural human hand anatomy, exactly five distinct separated fingers including thumb on each hand, clear individual knuckles and joints, thumb properly opposing index finger, relaxed natural hand posture, zero extra digits.
  ```
- **Suppression Negative**: `extra digits, fewer digits, missing fingers, fused fingers, six fingers, polydactyly, syndactyly, deformed digits, webbed fingers, mutated hands, claw hands, malformed joints`

##### DEF-ANAT-002: Floating / Disconnected Limbs & Topology Aberrations
- **Latent Phenomenon**: Diffusion denoisers lack an explicit kinematic graph. Extremities (forearms, hands, feet) can nucleate independently from the torso, resulting in dismembered limbs hovering in mid-air or impossible 180-degree reverse elbow bends.
- **Defective Formulation**:
  ```text
  An explorer climbing a steep rocky cliff face.
  ```
- **Engineered Mitigation**:
  ```text
  An explorer climbing a steep rocky cliff face. Continuous articulated human limb structure, forearm connecting seamlessly into wrist and hand, natural biological elbow bending angles, plausible human skeletal anatomy with exactly two arms and two legs, unbroken limb topology.
  ```
- **Suppression Negative**: `floating hands, detached limbs, severed hands, disconnected wrists, amputated arms, extra arms, extra legs, three arms, four arms, bent backwards, impossible joints, twisted limbs, broken bones`

##### DEF-ANAT-003: Polycephaly & Facial Duplication (Conjoined Heads)
- **Latent Phenomenon**: Repetition of subject tokens ("portrait of girl, girl face, female hero") creates multiple attention peaks in the cross-attention map, prompting the model to generate two heads emerging from one torso.
- **Defective Formulation**:
  ```text
  Portrait of a beautiful anime girl, girl face, female character close-up, anime female face.
  ```
- **Engineered Mitigation**:
  ```text
  Single solitary human subject with a single head on a natural neck. Centered close-up portrait of a teenage girl with green eyes. Symmetrical facial features, perfectly proportioned cranial anatomy, solitary subject focus, zero duplicate heads, no fused faces.
  ```
- **Suppression Negative**: `polycephaly, duplicate heads, two faces, multiple heads, fused heads, conjoined twins, second head, double head, phantom face`

---

#### 2.2.4 Spatial Contact Failure Modes (`DEF-SPAT-001` and `DEF-SPAT-002`)

##### DEF-SPAT-001: Unanchored Floating Objects (Gravity Physics Failure)
- **Latent Phenomenon**: Objects described in prompts as isolated nouns without support physics are placed randomly in the 2D plane by the denoiser, lacking downward gravitational contact shadows.
- **Defective Formulation**:
  ```text
  A magical spellbook and a crystal vial on the alchemist's wooden desk.
  ```
- **Engineered Mitigation**:
  ```text
  A thick leather spellbook resting completely flat and firmly on the dark wooden desk surface, casting a clear contact shadow beneath its binding. A glass crystal vial standing upright beside it with a visible dark ambient occlusion shadow at its base, physically supported by the wooden plane.
  ```
- **Suppression Negative**: `floating object, hovering in air, unanchored object, levitating, suspended in mid-air, floating book, floating vial, unsupported floating`

##### DEF-SPAT-002: Disconnected Interaction / Hollow Grasp (Air Gap)
- **Latent Phenomenon**: Standard verbs ("holding", "carrying") generate a hand and an object in close proximity, but fail to close the spatial gap, leaving a visible 10–30 pixel void where the palm should grip the hilt.
- **Defective Formulation**:
  ```text
  The knight holding a glowing sword in the dark cave.
  ```
- **Engineered Mitigation (`compile_interaction_bindings_natural`)**:
  ```text
  The knight in the dark cave. Physical contact: fingers firmly wrapped 360 degrees around the leather hilt of the glowing sword, establishing continuous unbroken physical grasp contact, palm pressing tightly against the grip with zero air gap between fingers and hilt.
  ```
- **Suppression Negative**: `disconnected grip, hovering near hand, floating prop, gap between hand and object, not touching, detached from grip, empty palm`

---

#### 2.2.5 Framing & Cropping Failure Modes (`DEF-FRAME-001` through `DEF-FRAME-003`)

##### DEF-FRAME-001: Decapitation / Headroom Truncation (Top Edge Clipping)
- **Latent Phenomenon**: When generating medium or close shots, the model attempts to maximize character resolution by expanding the torso upward, pushing the hair, hat, or forehead beyond the top canvas boundary.
- **Defective Formulation**:
  ```text
  Close-up portrait of an elven wizard wearing a pointed wizard hat.
  ```
- **Engineered Mitigation (`MARGIN_NATURAL`)**:
  ```text
  Close-up portrait of an elven wizard wearing a pointed wizard hat. Centered composition with generous headroom, upper canvas boundary positioned at least 15% above the tip of the hat, complete cranial silhouette and hat fully within frame, zero top cropping.
  ```
- **Suppression Negative**: `cropped head, cut off hair, out of frame top, top boundary clipping, decapitated, partial head, cut off hat`

##### DEF-FRAME-002: Extremity / Footwear Truncation in Full-Body Shots
- **Latent Phenomenon**: Requesting a full-body shot inside a 16:9 widescreen canvas (`1344x768`) leaves only 768 vertical pixels. The human 1:7.5 proportions cannot resolve, forcing the model to amputate the ankles and shoes.
- **Defective Formulation (on 1344x768)**:
  ```text
  Full body standing view of a warrior princess in gold armor.
  ```
- **Engineered Mitigation (on 832x1216 Portrait Bucket)**:
  ```text
  Full body shot from head to toe in vertical portrait orientation (832x1216). A warrior princess standing upright in gold armor, entire body visible from helmet crown down to boots, visible footwear resting flat on stone floor with generous empty floor margin below feet, zero bottom cropping.
  ```
- **Suppression Negative**: `cut off feet, cropped legs, out of frame bottom, truncated shoes, partial body, truncated limbs, knees down out of frame`

##### DEF-FRAME-003: Lateral Character Crowding & Mutual Occlusion
- **Latent Phenomenon**: Placing two characters in a square (`1024x1024`) canvas forces them into cramped lateral quarters, causing overlapping shoulders and one character being pushed 50% out of frame.
- **Defective Formulation (on 1024x1024)**:
  ```text
  The detective interrogating the suspect across the table.
  ```
- **Engineered Mitigation (on 1344x768 Widescreen Bucket)**:
  ```text
  Widescreen landscape composition (1344x768). Two characters seated across a table with clear horizontal separation. Detective positioned on the left third of frame, suspect positioned on the right third of frame, spacious empty space between them, both characters fully visible without mutual occlusion.
  ```
- **Suppression Negative**: `overlapping bodies, crowded framing, occluded characters, merged figures, cropped companion, cramped composition, squeezed framing`

---

#### 2.2.6 Temporal Video Failure Modes (`DEF-VID-001` and `DEF-VID-002`)

##### DEF-VID-001: Inter-Frame Temporal Morphing & Jitter (Facial Melting)
- **Latent Phenomenon**: In Image-to-Video diffusion (MiniMax Fast H3 Turbo), temporal cross-attention layers hallucinate new identities if the prompt re-describes static facial features instead of motion deltas. As movement occurs, the face melts into different bone structures.
- **Defective Video Prompt**:
  ```text
  The girl turns around quickly and smiles happily, highly detailed anime video.
  ```
- **Engineered Mitigation**:
  ```text
  Consistent character appearance across all frames. Slow cinematic head turn, unbroken facial geometry, delicate hair sway following momentum, natural gentle smile, smooth 24fps motion, steady lighting, zero facial morphing.
  ```
- **Suppression Negative**: `morphing face, melted face, flickering facial features, jittery artifacts, twitching anatomy, faceless pedestrians, shape-shifting, temporal noise, distorted eyes`

##### DEF-VID-002: Camera Trajectory Instability & Jump Cuts (Erratic Jitter)
- **Latent Phenomenon**: Without explicit mechanical camera directives, the video diffusion model treats independent action phrases as sequential editorial cuts, inserting abrupt jump cuts and camera shakes inside a 5-second take.
- **Defective Video Prompt**:
  ```text
  Camera moves around the courtyard while characters fight.
  ```
- **Engineered Mitigation**:
  ```text
  Single continuous camera take. Slow cinematic camera push in towards the character in the stone courtyard. Smooth steady optical track, calm pace, unbroken perspective, smooth mechanical dolly track, zero camera jump cuts, zero erratic jitter.
  ```
- **Suppression Negative**: `fast jerky motion, abrupt camera jump cut, camera jitter, erratic panning, violent camera shake, handheld wobble, discontinuous edits, multiple cuts`

---

## 3. The 6 Core Engineering Principles

PanelFlow Studio establishes six mandatory engineering principles governing prompt generation. Every compiled prompt must satisfy these rules before dispatching to inference engines.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                 PANELFLOW STUDIO: THE 6 CORE PRINCIPLES                     │
├─────────────────────────────────────────────────────────────────────────────┤
│ 1. ELIMINATION OF PSEUDO-QUALITY BUZZWORDS                                  │
│    Replace evaluative adjectives with concrete physical and optical physics │
├─────────────────────────────────────────────────────────────────────────────┤
│ 2. FOUR-TIER INVARIANT VISUAL STYLING ANCHORS                              │
│    Lock Medium, Line Geometry, Palette, and Lighting Physics per sequence   │
├─────────────────────────────────────────────────────────────────────────────┤
│ 3. CHARACTER IDENTITY ANCHORING & UNNAMING PROTOCOL                         │
│    Sanitize proper names into role noun phrases; separate immutable anatomy │
├─────────────────────────────────────────────────────────────────────────────┤
│ 4. KINEMATIC CONTACT & OBJECT GROUNDING                                     │
│    Mandate 360-degree finger grasp bindings and physical contact shadows    │
├─────────────────────────────────────────────────────────────────────────────┤
│ 5. DYNAMIC FRAMING & RESOLUTION-TO-SHOT ALIGNMENT                           │
│    Map shot types to 1-MP aspect ratio buckets; enforce headroom margins    │
├─────────────────────────────────────────────────────────────────────────────┤
│ 6. VIDEO DIRECTORIAL PROMPTING (MINIMAX H3)                                 │
│    Describe only kinematic motion deltas; suppress temporal warping         │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### Principle 1: Elimination of Pseudo-Quality Buzzwords

#### 1.1 The Rule
**Strictly eliminate all evaluative, subjective, and pseudo-quality buzzwords from prompt pipelines.**  
Forbidden tokens include: `masterpiece`, `best quality`, `high quality`, `ultra realistic`, `hyperrealistic`, `absurdres`, `8k`, `4k resolution`, `trending on artstation`, `award winning`, `stunning`, `breathtaking`, `highly detailed`, `photorealistic`.

#### 1.2 The Mechanism of Failure
Modern generative foundation models (Qwen Image 2.1, FLUX.1, MiniMax H3) employ large-scale multimodal language encoders (`qwen3vl_8b`, `qwen3vl_32b`, `T5-XXL`) trained on comprehensive web-scale image-text pairings. In these architectures:
1. **Centroid Attraction & Plastic Artifacts**: Evaluative tokens like "masterpiece" or "ultra realistic" are correlated in web scrape datasets with over-processed 3D promotional art, over-sharpened digital stock photography, and aggressive plastic airbrushing. When injected, they pull the sampling trajectory toward the generic centroid of these datasets, yielding waxy skin, unnatural specular sheen, and 3D CGI leakage into 2D anime styles.
2. **Token Dilution in VLM Encoders**: Multimodal encoders allocate finite self-attention capacity across the input sequence. Low-entropy buzzwords dilute the attention weight allocated to critical semantic tokens (exact digit count, character eye color, hand grasp bindings).
3. **Temporal Flickering in Video**: In video diffusion models (MiniMax H3), tokens like "hyperdetailed" force the model to hallucinate microscopic surface noise that cannot be coherently tracked across temporal attention layers, producing severe inter-frame jitter and texture crawling.

#### 1.3 Concrete Physical Replacement Strategy

| Banned Pseudo-Quality Buzzword | Physical/Optical Failure Induced | Concrete Engineering Replacement |
|---|---|---|
| `masterpiece`, `best quality` | Low-entropy centroid bias; waxy plastic sheen | Explicit medium & line physics: *"Hand-drawn 2D anime animation still, crisp dark ink outlines of uniform 1.5px stroke weight, flat two-tone cel shading, matte gouache background plate"* |
| `ultra realistic`, `photorealistic` | 3D CGI leakage; unnatural pores; stock photo look | Optical camera parameters: *"35mm prime lens optical capture, sharp focal plane locked on subject irises, natural sub-surface epidermal scattering, subtle optical falloff"* |
| `hyper detailed`, `extremely detailed` | High-frequency noise; video temporal flickering | Specific material texture: *"Intricate weave on unbleached raw cotton tunic, visible tactile thread texture, natural linen drape"* |
| `beautiful lighting`, `stunning lighting` | Ambiguous diffuse lighting; missing cast shadows | Explicit photon mechanics & angle: *"Warm golden hour sunlight entering at a 45-degree angle from top-left, casting sharp-edged directional cast shadows with warm ambient bounce"* |
| `8k`, `4k resolution`, `absurdres` | Over-sharpening halos; ringing artifacts | Compositional clarity & resolution bucket: *"Tack-sharp focal plane, pristine edge separation against background, 1024x1024 native sensor resolution"* |
| `trending on artstation` | Over-saturated digital painting; stylized glow | Historical/artistic reference: *"Traditional Japanese woodblock print aesthetic, mineral pigments, matte rice paper texture"* |

---

### Principle 2: Four-Tier Invariant Visual Styling Anchors

#### 2.1 The Rule
Every prompt compiled within a story, scene, or genre must enforce four orthogonal, bit-for-bit invariant visual styling anchors:
$$\text{Visual Style Anchor} = \mathcal{A}_{\text{Medium}} \oplus \mathcal{A}_{\text{Line}} \oplus \mathcal{A}_{\text{Palette}} \oplus \mathcal{A}_{\text{Light}}$$
These four anchors must remain constant across all panel prompts in a sequence, preventing style divergence across multi-panel narratives.

#### 2.2 The 4 Tiers Defined

1. **Tier 1: Medium & Renderer**: Governs material substrate, rendering engine simulation, and physical finish (e.g. 2D anime cel, 35mm film, flat vector).
   - *Anime*: `"Hand-drawn 2D anime animation still, matte finish, zero 3D CGI, zero photographic textures."`
   - *Historical Film*: `"35mm Arri Alexa cinematography, anamorphic lens optics, authentic historical cinematic film still."`
   - *Motion Explainer (Vox)*: `"Flat 2D vector motion graphic illustration, clean geometric shapes, zero gradients, zero photographic textures."`
2. **Tier 2: Line Geometry**: Governs stroke weight, contour continuity, and edge rendering physics.
   - *Anime*: `"Crisp uniform dark ink outlines, smooth finished linework, defined character silhouettes."`
   - *Graphic Novel*: `"Bold dark vector contours, sharp graphic silhouettes, high-precision edge boundaries."`
   - *Painterly*: `"Soft lost-and-found edges, expressive gouache brushwork, gentle edge transitions without hard outlines."`
3. **Tier 3: Palette & Tonal Range**: Governs chromatic harmony, saturation gamut, and contrast ratio across the sequence.
   - *Bedtime*: `"Soft warm pastel palette, creamy amber and soft peach tones, muted lavender shadows, low tonal contrast."`
   - *Horror*: `"Desaturated cool muted palette, sickly moss greens, deep slate blues, high-contrast chiaroscuro."`
   - *Fantasy*: `"Vivid saturated jewel tones, lapis lazuli blues, emerald greens, gold leaf highlights."`
   - *Mythology*: `"Authentic Indian heritage palette, warm turmeric gold, sacred vermilion, unbleached raw cotton ivory."`
4. **Tier 4: Lighting Physics**: Governs photon mechanics, directionality, specular highlights, and shadow geometry.
   - *Natural Ambient*: `"Soft diffused morning daylight from an overcast sky, even ambient illumination, gentle contact shadows."`
   - *Chiaroscuro / Dramatic*: `"Single key light from a low lantern, strong directional illumination with deep cast shadows and warm specular highlights."`
   - *Studio / Rigging*: `"Flat diffused three-point studio lighting, uniform illumination, zero harsh cast shadows."`

#### 2.3 Mathematical Invariance Across Sequence
Let $S$ represent the Visual Style space. In a narrative panel sequence $P = \{p_1, p_2, \dots, p_n\}$ belonging to scene $C$, the style specification function $f_{\text{style}}(p_i)$ must satisfy:
$$\forall i, j \in \{1, \dots, n\}, \quad f_{\text{style}}(p_i) \equiv f_{\text{style}}(p_j) = \mathcal{A}_{\text{Medium}} \oplus \mathcal{A}_{\text{Line}} \oplus \mathcal{A}_{\text{Palette}} \oplus \mathcal{A}_{\text{Light}}$$
Only situational components (character actions, camera framing, local props) are permitted to vary per panel.

---

### Principle 3: Character Identity Anchoring & The Unnaming Protocol

#### 3.1 The Unnaming Protocol (`shotspec.unname`)
1. **The Core Rule**: **Never inject character proper names (e.g. "Mira", "Biscuit", "Kael", "Dr. Stone") into natural language prompts.**
2. **The Linguistic Failure Mode**: Diffusion text encoders parse proper names using pre-trained subword tokenizers. Proper names that coincide with English nouns trigger literal semantic hallucinations:
   - A character named `"Biscuit"` causes the model to draw baked cookies or confectionery.
   - A character named `"Gravity"` causes the model to generate cosmic distortions or physics diagrams.
   - A character named `"April"` generates wall calendars or springtime blossoms.
   - Proper names of unfamiliar fictional characters have near-zero semantic mass in the latent space, forcing the model to invent arbitrary facial features on every invocation.
3. **The Unnaming Algorithm**:
   - Detect and extract all character proper names and titles (`dr`, `mr`, `ms`, `captain`, `professor`).
   - Programmatically replace every instance of the proper name with the character's invariant role noun phrase:
     $$\text{Name} \xrightarrow{\text{unname}} \text{Noun Phrase} = \text{NATURAL\_PERSON}[(\text{age\_group}, \text{gender})] + \text{Immutable Look}$$
     *Example*: `Mira` $\rightarrow$ `"the little girl with short brown hair and green eyes"`

#### 3.2 Invariant Anatomical Descriptors vs Mutable Situational States
Character schemas must strictly partition **Immutable Biological Anchors** from **Mutable Situational States**:
- **Immutable Biological Anchors (Invariant across all panels)**:
  - Bone & Jaw Structure: `"round youthful face, soft cheeks, pointed chin"`
  - Ocular Geometry: `"large expressive emerald-green almond-shaped eyes, delicate dark arched eyebrows"`
  - Hair Physics & Silhouette: `"short choppy dark brown bob haircut, straight bangs resting just above the brow line"`
  - Permanent Markings: `"light constellation of freckles across the bridge of the nose, small mole beneath left eye"`
  - Skin Tone: `"fair porcelain skin with warm undertones"`
- **Mutable Situational States (Varies per shot)**:
  - Wardrobe: `"wearing an oversized canary-yellow hooded raincoat with brass toggle buttons"`
  - Emotional Expression: `"serene smile, relaxed eyebrows, soft gaze"`
  - Physical Pose: `"sitting cross-legged on the floor, leaning slightly forward"`

#### 3.3 Pose-Sensitive Attenuation Protocol
When character reference images (turnaround sheets or frontal portraits) are utilized in the generation pipeline:
- **The Identity-Pose Conflict**: Reference portraits depict characters facing forward with wide-open eyes. When a story beat specifies sleeping, crying, closed eyes, or looking away from the camera (`"from behind"`, `"turned away"`), strong reference conditioning overrides the prompt, producing unnerving open-eyed sleeping characters or twisted necks.
- **The Attenuation Rule**:
  1. Detect pose sensitivity via `pose_sensitive(spec)` matching closed eyes, sleeping, or rear views.
  2. Attenuate portrait reference conditioning weight from standard `0.75` down to `0.30` (`POSE_WEIGHT = 0.3`).
  3. Inject explicit optical state descriptors: `"eyes completely closed, relaxed eyelids with dark eyelashes resting against cheeks, serene sleeping expression"`.
  4. Append negative overrides: `", open eyes, looking at viewer, direct gaze, frontal face"`.

#### 3.4 Spatial Disentanglement in Multi-Character Compositions
When two characters appear in the same frame, standard self-attention mechanisms suffer from **attribute bleeding** (Character A's blue hair transfers to Character B; Character B's red dress appears on Character A).
- **Enforcement Rules**:
  1. Force Widescreen `(1344, 768)` aspect ratio to provide adequate horizontal coordinate separation.
  2. Sort characters by screen position: left-most character first, right-most character second.
  3. Enforce strict spatial prepositional partitioning in prompt syntax:
     ```text
     Two distinct characters in frame:
     On the left: a little girl with short brown hair and green eyes, wearing a yellow raincoat, sitting quietly.
     On the right: an elderly man with silver hair and wire-rim glasses, wearing a dark tweed jacket, holding a wooden walking cane.
     Clear horizontal separation between both characters, distinct individual identities.
     ```
  4. In SDXL workflows, route through the dual IP-Adapter attention-masked workflow (`anime_sdxl_ipa2`) to bind character portraits to separate spatial halves.

---

### Principle 4: Kinematic Contact & Object Grounding

#### 4.1 The Defect Mechanism
In diffusion models, characters and objects are generated from distinct semantic clusters. When a prompt specifies an action like "holding a cup" or "reading a book" without physical contact physics, cross-attention fails to bind the hand coordinates to the object coordinates. This produces the two most common spatial defects in PanelFlow Studio:
1. `unanchored_object`: The prop hovers in mid-air near the character without physical support.
2. `disconnected_interaction`: The hand is positioned near the object with open or distorted fingers, leaving an empty air gap.

#### 4.2 Kinematic Grasp Binding Directives (`compile_interaction_bindings_natural`)
Every interaction verb must automatically expand into an explicit kinematic binding directive establishing **mechanical encirclement, surface contact, and zero air gap**:

| Interaction Verb | Mandated Kinematic Contact Binding Directive |
|---|---|
| `holding`, `holds`, `gripping`, `grips` | *"hands firmly gripping the object with fingers visibly curled 360 degrees around the handle, establishing unbroken physical contact, zero air gap between palm and surface"* |
| `carrying`, `carries` | *"arms securely supporting and carrying the object against the torso, visible physical load, solid arm contact"* |
| `wielding`, `wields` | *"hand firmly gripping the hilt with fingers wrapped tightly around it, knuckles articulated, solid grip"* |
| `reading`, `reads` | *"hands holding the open book, fingers visibly resting against and supporting the cover and lower page margins"* |
| `touching`, `touches` | *"hand and fingers resting flat and directly against the surface, visible tactile compression, zero gap"* |
| `drinking`, `drinks` | *"hands holding the cup securely against the lips with visible physical contact and finger wrap"* |

#### 4.3 Object Grounding & Contact Shadow Physics
For environmental props and furniture:
- **The Rule**: Never state an object exists without specifying its resting surface and gravitational grounding.
- **Physical Grounding Directive**:
  `"[Prop] resting flat and firmly on the [Surface], supported by the ground plane, with a distinct contact shadow cast directly beneath the base, zero hovering, physically anchored."`

#### 4.4 Hand Anatomy Guardrails
Every prompt featuring visible human characters must append the invariant anatomical hand guardrail:
```text
Hands rendered with natural human anatomy, exactly five distinct separated fingers including thumb, clear knuckles and joints, anatomically correct wrist connection, zero extra digits, zero fused fingers.
```

---

### Principle 5: Dynamic Framing & Resolution-to-Shot Alignment

#### 5.1 The Root Cause of Framing Defects
Diffusion latent spaces are calibrated to fixed token grids (e.g. 1-Megapixel latents). Aspect ratio mismatches force severe anatomical mutilations:
- **The Vertical Truncation Problem**: Attempting to generate a full-body character inside a wide landscape aspect ratio (16:9) compresses the vertical pixel allocation. The model cannot resolve head, torso, legs, and shoes within the constrained vertical dimension, resulting in severed feet, cropped legs, or decapitation.
- **The Lateral Crowding Problem**: Attempting to place two or three characters in a vertical portrait (9:16) or square (1:1) canvas leaves insufficient horizontal space, causing fused limbs, overlapping bodies, and character occlusion.

#### 5.2 The 1-Megapixel Resolution Alignment Matrix
PanelFlow Studio strictly enforces the 1-MP Resolution Matrix (`resolve_dimensions` in `shotspec.py`), adhering to model dimension policies (`multiple_of: 16` for Qwen Image 2.1, `multiple_of: 32` for MiniMax H3):

| Shot Classification | Aspect Ratio | Dimensions | Compositional Target |
|---|---|---|---|
| **Full Body** (`full`, `character_sheet`) | 9:13 (Portrait) | **832 x 1216** (~1.01 MP) | Head-to-toe single figure; ample vertical headroom and ground plane for feet |
| **Close & Medium** (`close`, `medium`, `cowboy`) | 1:1 (Square) | **1024 x 1024** (1.05 MP) | Centered portrait/bust; balanced margins around face and shoulders |
| **Wide & Group** (`wide`, $\ge 2$ characters) | 16:9 (Widescreen) | **1344 x 768** (1.03 MP) | Environmental landscape; lateral separation to prevent character overlap |
| **Turnaround Sheet** (`turnaround`) | 2:1 (Ultra-Wide) | **1536 x 768** (1.18 MP) | Orthographic 4-view sheet (front, 3/4, side, back); unobstructed limb space |

#### 5.3 Safe Action Zones & Headroom Clearance Directives
Prompt compilation must inject explicit spatial boundary directives based on shot classification:
1. **Close-Up & Medium Shots (`MARGIN_NATURAL['medium']`, `'close'`)**:
   `"Medium shot from waist up with generous headroom above the hair, subject completely within frame, upper canvas edge positioned at least 15% above the crown of the head, zero top clipping."`
2. **Full-Body Shots (`MARGIN_NATURAL['full']`)**:
   `"Full body shot from head to toe with visible feet resting flat on the ground plane, generous empty margins on all four sides, subject completely in frame with zero edge cropping."`
3. **Turnaround Sheets (`MARGIN_NATURAL['character_sheet']`)**:
   `"Full length standing character reference from head to toe, four sequential orthographic views (front, three-quarter, profile side, back), unobstructed A-pose, clear limb separation, wide empty margins around all views."`

---

### Principle 6: Video Directorial Prompting (MiniMax Fast H3 Turbo)

#### 6.1 The I2V Prompting Paradigm: Kinematic Delta vs Static Re-Description
In PanelFlow Studio's video pipeline, the video generation engine (`minimax_h3_turbo_i2v.api.json`) operates in **Image-to-Video (I2V)** mode, where a pre-generated, quality-verified static panel serves as `first_frame`.
- **The Core Video Failure Mode**: If a video prompt re-describes static visual features (e.g. re-describing the character's clothing, eye color, and background architecture), the video model's cross-attention layers experience semantic competition between the text prompt and the pixels of `first_frame`. This causes the model to "re-render" the character across frames, inducing violent facial morphing, clothing transformation, and flickering background details.
- **The Directorial Rule**: **Video prompts must describe only the KINEMATIC DELTA: camera kinematics, motion pacing, secondary cloth/hair dynamics, and lighting stability.**

#### 6.2 Standardized Camera Kinematics Vocabulary

| Direction Key | Directorial Camera Motion Prompt Directive |
|---|---|
| `push_in` | *"Slow cinematic camera push in towards the subject, smooth steady optical track, maintaining focal lock"* |
| `pull_out` | *"Smooth slow camera pull back revealing the wider scene and surroundings, steady fluid optical track"* |
| `pan_right` | *"Gentle cinematic camera pan from left to right across the scene, smooth mechanical track"* |
| `pan_left` | *"Gentle cinematic camera pan from right to left across the scene, smooth mechanical track"* |
| `tilt_up` | *"Slow deliberate camera tilt upwards, steady vertical tracking"* |
| `orbit` | *"Slow subtle camera orbit around the central focal point, steady rotational speed"* |
| `static` | *"Static camera framing, locked-off tripod shot, subtle ambient environmental motion"* |

#### 6.3 Motion Pacing & Secondary Dynamics
To prevent either static "freeze-frame" paralysis or violent turbulent warping, prompts must prescribe calibrated motion intensity and natural secondary physics:
- **Motion Pacing**:
  - Subtle (Narrative / Emotional): `"slow subtle gentle motion, calm and delicate pace, tranquil atmosphere"`
  - Action (Climactic): `"dynamic energetic movement, strong visual momentum, controlled anime action pacing"`
- **Secondary Cloth & Hair Dynamics**:
  `"natural subtle secondary movement, delicate hair strands and fabric clothing dynamics swaying gently in the ambient air, natural breathing chest movement"`

#### 6.4 Temporal Anti-Morphing Guardrails
Every video motion prompt must enforce temporal consistency and suppress video-specific artifacts:
- **Temporal Invariance Anchor**:
  `"steady consistent character facial appearance across all frames, unbroken lighting geometry, steady 24fps smooth playback rate, zero jump cuts"`
- **Universal Video Negative Prompt Anchor**:
  ```text
  fast jerky motion, abrupt camera jump cut, morphing face, distorted hands, flickering, twitching, text, watermark, bad anatomy, jittery artifacts, melted face, blurry facial features, faceless pedestrians, temporal tearing, frame stutter, rapid zoom, disfigured limbs
  ```

#### 6.5 The Native MiniMax H3 6-Heading Prompt Schema
For advanced video compilation (implemented in `engine/chronoflow/pipeline.py:93-115`), prompts are structured into MiniMax H3's native 6-heading schema:
```text
subject_definitions:
- Subject 1: A little girl with short brown hair, wearing a yellow raincoat. Facial features locked to reference frame.

summary:
The camera slowly pushes in as the little girl turns her head toward the warm morning light.

retention_analysis:
Retain exact facial geometry, hair shape, and raincoat texture from reference image. Zero morphing or clothing alteration across all 124 frames.

detailed_description:
camera_movement: Slow cinematic push-in towards the subject along the central optical axis.
subject_description: The girl gently turns her head to the right, hair swaying subtly with the movement, serene expression.
environmental_details: Dust motes drifting gently in warm sunbeams, background trees resting steady with subtle leaf rustle.
lighting_and_atmosphere: Warm golden sunlight consistent throughout sequence, stable shadows.

overall_soundscape:
Gentle morning breeze, distant soft birdsong.

non_diegetic_music:
Soft acoustic piano melody with warm string accompaniment.
```

---

## 4. Master Genre Visual Style Anchors Table

PanelFlow Studio supports six active narrative genres (`engine/original/genres.py`). The table below specifies the authoritative 4-tier visual anchors, standard negative prompts, and review witness verification criteria for each genre.

| Genre Key | Medium & Renderer Anchor | Line Geometry Anchor | Palette & Tonal Range Anchor | Lighting Physics Anchor | Standard Negative Prompt Anchor | Review Witness Verification Rule |
|---|---|---|---|---|---|---|
| **`bedtime`** | Hand-drawn 2D anime illustration, gentle storybook animation still, soft matte finish, zero 3D CGI, zero photographic textures | Clean, soft dark brown ink outlines, smooth uniform contours, gentle stroke weight | Warm pastel palette, soft cream and amber tones, muted lavender shadows, gentle low contrast | Diffused warm lamp light, soft golden ambient glow, even gentle illumination, soft-edged shadows | `lowres, bad anatomy, bad hands, text, cropped, blurry, nsfw, dark, gritty, scary, harsh shadows, 3d render, cgi, photorealistic skin, high contrast, oversaturated neon, violence, weapons` | Witness B must confirm gentle storybook anime tone; flags failure on dark/gritty aesthetics, harsh shadows, or 3D rendering. |
| **`horror`** | Atmospheric 2D cinematic horror anime illustration, fine filmic grain texture, vintage cel aesthetic | Razor-sharp, thin black ink contours, high-precision dark outlines, stark silhouette definition | Desaturated cool muted palette, slate blues, sickly moss greens, deep charcoal blacks, pale skin tones | Noir chiaroscuro lighting, deep cast shadows, harsh single directional beam, eerie volumetric fog, high contrast | `lowres, bad anatomy, bad hands, text, cropped, blurry, nsfw, bright, vibrant, pastel, cheerful, colorful, 3d render, cgi, flat lighting, gore, bloody, dismemberment, mutilated` | Witness B confirms unsettling noir atmosphere; verifies absence of forbidden overt gore (`GORE` filter) and cheerful lighting. |
| **`mystery`** | Detective noir anime style, atmospheric 2D graphic illustration, matte paper finish | Crisp bold ink outlines, defined silhouette contours, clean architectural line weight | Muted vintage palette, rich sepia and charcoal tones, deep umber accents, restrained amber highlights | High-contrast dramatic side-lighting, Venetian blind shadow patterns, atmospheric dim lantern lighting | `lowres, bad anatomy, bad hands, text, cropped, blurry, nsfw, colorful, neon, flat lighting, 3d render, cgi, bright cheerful colors, oversaturated, photorealistic` | Witness B confirms detective noir aesthetic and shadow patterns; verifies planted clue visibility. |
| **`fantasy`** | Epic fantasy anime feature film animation still, rich 2D anime rendering, vivid matte finish | Fine detailed ink outlines, clean elegant line art, defined dynamic contours | Vivid saturated jewel tones, lapis lazuli blues, emerald greens, gold leaf highlights, rich contrast | Dramatic cinematic golden hour temple sunlight, magical soft rim lighting, bioluminescent accents, ambient occlusion | `lowres, bad anatomy, bad hands, text, cropped, blurry, nsfw, washed out, dull, flat lighting, 3d render, cgi, photorealistic skin, modern clothing, modern buildings` | Witness B confirms epic fantasy animation aesthetic; checks vibrant jewel-toned palette and magical atmospheric lighting. |
| **`mythology`** | Authentic Indian historical cinema, 35mm Arri Alexa cinematography, naturalistic film still, documentary realism | Naturalistic photographic edge transitions, zero graphic ink outlines, natural physical edge falloff | Culturally authentic Indian heritage palette, warm turmeric gold, sacred vermilion, raw cotton ivory, deep bronze | Warm golden hour temple sunlight, brass diya oil lamp directional amber glow, floating dust motes, soft directional falloff | `lowres, bad anatomy, bad hands, text, cropped, blurry, nsfw, western comic, 2d cartoon, anime, 3d render, cgi, modern clothing, plastic skin, neon lighting, flat lighting` | Witness B confirms authentic Indian historical cinematography, natural skin textures, sacred attire (dhoti, zari, rudraksha), and absence of cartoonish lines. |
| **`vox`** | Signature Vox 2D motion explainer style, modern flat vector graphic illustration, high-end YouTube visual journalism | Crisp bold dark outlines, geometric precision, uniform stroke weight, clean vector paths | Solid vibrant color palette, bright canary yellow accents, deep navy background, stark graphic contrasts | Minimalist flat clean cel shading, graphic studio illumination, zero cast shadows, zero photographic gradients | `lowres, bad anatomy, bad hands, text, cropped, blurry, nsfw, photographic textures, 3d render, cgi, gradients, painterly, realistic skin, sketchy lines, soft brushstrokes` | Witness B confirms 2D flat vector motion explainer aesthetic; strictly rejects photographic textures, 3D CGI, and painterly gradients. |

---

## 5. Master Camera Framing & Composition Anchors Table

Framing parameters govern aspect ratio bucketing, headroom clearance, safe action zones, and visible anatomical thresholds (`engine/original/shotspec.py:56-165`).

| Shot Code | Description & Framing | Dimensions (1 Char) | Dimensions ($\ge 2$ Chars) | Aspect Ratio & Budget | Headroom & Margin Directives | Safe Action Zone Strategy | Anatomical & Contact Guardrails | Review Witness Verification Rule |
|---|---|---|---|---|---|---|---|---|
| **`extreme_close`** | Macro detail focus on eyes, mouth, expression, or handheld micro-prop | `(1024, 1024)` | `(1344, 768)` | Square 1:1 (1-char) / Landscape 16:9 | Macro framing focusing directly on facial features; tight crop on eyes/mouth with zero unnecessary empty border | Focal element centered within central 60% circle ($0.20 \le x, y \le 0.80$); eye-line centered horizontally; background heavily blurred | Facial symmetry, natural eyelashes/irises, zero extra eyes/pupils; hands excluded unless macro hand action is explicitly specified | Bypasses limb checks via `BENIGN_ANATOMY_EXPLANATION_PATTERN`; audits single head and eye integrity. |
| **`close`** | Close-up portrait focusing on face, collar, and shoulders | `(1024, 1024)` | `(1344, 768)` | Square 1:1 (1-char) / Landscape 16:9 | Centered framing focusing on face and shoulders, generous headroom above hair ($\ge 15\%$ clearance above crown), zero top edge clipping | Head and collar occupy vertical 20% to 80%; eye-line anchored at upper third (y = 35%); lateral margins $\ge 15\%$ on left and right | Natural jawline, hair parting, shoulder symmetry; hands only present if touching face/chin (kinematic contact required); torso cut off cleanly at chest | `_audit_anatomy` ignores missing lower limbs (`BENIGN_ANATOMY_EXPLANATION_PATTERN` matches portrait crop); checks `polycephaly` and facial landmarks. |
| **`medium`** | Cowboy shot framing subject from waist up | `(1024, 1024)` | `(1344, 768)` | Square 1:1 (1-char) / Landscape 16:9 | Medium shot from waist up with generous headroom above hair, subject completely in frame with zero top cropping | Head at top 15–35%, torso at 35–75%, belt/waist at 75–85%; lower margin $\ge 15\%$; lateral clearance $\ge 10\%$; 2 chars partitioned at x=25% and x=75% | Full upper torso, complete arms and elbows visible; wrists connect continuously to hands; exactly five distinct fingers; held objects bound by unbroken physical contact | Core audit zone for hands and props (`distorted_digits`, `limb_topology`, `unanchored_object`, `disconnected_interaction`); uses region `(0.15, 0.35, 0.85, 0.85)`. |
| **`full` / `full_body`** | Full-body shot framing character completely from head to toe | `(832, 1216)` | `(1344, 768)` | Portrait ~9:13.2 (1-char) / Landscape 16:9 | Full body shot from head to toe with visible feet resting on ground plane, wide empty margins around subject on all 4 boundaries, zero cropping | Head 12–25%, torso 25–55%, legs 55–88%, feet & ground contact 88–92%, bottom margin 92–100%; horizontal centering at x=50% | Complete skeletal chain: head $\rightarrow$ neck $\rightarrow$ torso $\rightarrow$ pelvis $\rightarrow$ thighs $\rightarrow$ knees $\rightarrow$ calves $\rightarrow$ ankles $\rightarrow$ feet; feet flat on floor with visible cast contact shadow; hands at sides or holding props | Critical gate for VQA Q2 (`extra_limbs`), Q3 (`missing_limbs`), and Q5 (`limb_topology`); audited across region `(0.10, 0.25, 0.90, 0.90)`. |
| **`wide` / `extreme_wide`** | Wide establishing shot of full environment and surroundings | `(1344, 768)` | `(1344, 768)` | Widescreen Landscape 16:9 | Wide shot showing full scene, architecture, horizon, and characters; characters fully in frame with generous environmental space | Horizon line positioned at upper or lower third (y=33% or y=66%); characters occupy 20–40% frame height positioned at rule-of-thirds intersections | Characters physically grounded on ground surfaces with contact shadows; small figure anatomy simplified; architectural planes (foreground/midground/background) clearly delineated | Spatial support verification (`unanchored_object`); 0-character scenes bypass character anatomy check (`review.py:461-462`); environmental objects audited for physical grounding. |
| **`turnaround`** | Orthographic 4-view character turnaround model sheet | `(1536, 768)` | `(1536, 768)` | Ultra-Wide Landscape 2:1 | Four sequential orthographic views from left to right (front, 3/4, side, back) in A-pose from head to toe; generous empty margins (top $\ge 15\%$, bottom $\ge 10\%$) | 4 equal horizontal quadrants (0–25% front, 25–50% three-quarter, 50–75% side, 75–100% back); uniform height alignment guidelines across all views; solid neutral gray background | Unobstructed A-pose (arms angled 45 degrees downward) or T-pose; fingers spread and clearly separated; zero limb overlap or occlusion; visible articulated joints at shoulders, elbows, wrists, hips, knees, ankles | High-precision symmetry and limb topology verification; `RIGGING_NEGATIVE` suppresses dynamic poses, foreshortening, and background props while permitting multiple views. |

---

## 6. Review Witness & Quality Gate Alignment Matrix

PanelFlow Studio employs an automated two-witness quality gate (`engine/original/review.py`). To prevent false rejections and streamline inpainting repairs, prompt compilation guardrails are mapped directly to review audit checks, defect keyword triggers, heuristic bounding regions, and inpaint repair prompts.

### 6.1 Direct Alignment Matrix

| Defect Identifier | Review Witness Audit Rule | Generative Defect Keyword Triggers | Prompt Mitigation Guardrail (Positive Token Anchor) | Prompt Mitigation Guardrail (Negative Token Anchor) | Defect Heuristic Region `(ymin, xmin, ymax, xmax)` | Automated Inpaint Repair Correction Prompt |
|---|---|---|---|---|---|---|
| **`polycephaly`** | VQA Q1: *"single head per person or creature with no polycephaly, duplicate heads, or fused faces"* | `two heads`, `extra head`, `multiple heads`, `duplicate head`, `polycephaly`, `fused head`, `two faces` | *"Single head on a natural neck, perfectly symmetrical facial features, solitary subject focus, single centered face"* | `polycephaly, duplicate heads, two faces, multiple heads, fused heads, conjoined head, double head` | `(0.15, 0.05, 0.85, 0.45)` | **Pos**: `"single head, symmetrical face, natural neck, serene anime face, perfect head proportions"`<br>**Neg**: `"multiple heads, two faces, duplicate head, fused heads, conjoined head, deformed face, two heads"` |
| **`extra_limbs`** | VQA Q2: *"correct number of limbs with no extra arms, extra legs, duplicate limbs, or mutated appendages"* | `extra arm`, `extra leg`, `three arms`, `three legs`, `four arms`, `extra limb`, `supernumerary` | *"Anatomically correct body, exactly two arms and two legs, clean limb separation, natural skeletal proportions"* | `extra limbs, extra arms, extra legs, mutated appendages, duplicate limbs, three arms, four arms, supernumerary` | `(0.10, 0.25, 0.90, 0.90)` | **Pos**: `"correct number of limbs, natural anatomical arms and legs, proper proportions, anatomically correct body"`<br>**Neg**: `"extra limbs, extra arms, extra legs, mutated appendages, duplicate limbs, three arms, four arms"` |
| **`missing_limbs`** | VQA Q3: *"complete body structure with no missing limbs, severed arms, or amputated body parts (accounting for frame cropping)"* | `missing arm`, `missing leg`, `amputated`, `severed arm`, `severed leg`, `missing limb`, `detached limb` | *"Complete body structure from head to toe, visible feet resting flat on ground plane, fully rendered limbs"* *(or explicit crop: "from the waist up")* | `missing limbs, amputated, severed limbs, truncated limbs, missing arms, missing legs, cut off feet` | `(0.10, 0.25, 0.90, 0.90)` | **Pos**: `"complete body structure, intact limbs, natural anatomy, fully rendered arms and legs"`<br>**Neg**: `"missing limbs, amputated, severed limbs, truncated limbs, missing arms"` |
| **`distorted_digits`** | VQA Q4: *"for any human characters visible, natural hands and feet with anatomically correct digits and no extra or fused fingers"* | `six fingers`, `fused fingers`, `distorted hand`, `extra finger`, `missing finger`, `polydactyly`, `syndactyly` | *"Hands drawn with natural anatomy, exactly five distinct separated fingers including thumb, clear articulated knuckles"* | `bad hands, extra digits, missing fingers, fused fingers, distorted hand, polydactyly, syndactyly, deformed digits, six fingers` | Derived from hand VQA bbox or `(0.25, 0.25, 0.75, 0.75)` | **Pos**: `"detailed anatomical hand, five fingers, correct digits, natural hand pose, well-defined fingers, perfect anatomy"`<br>**Neg**: `"bad anatomy, extra digits, missing fingers, fused fingers, distorted hand, polydactyly, syndactyly, deformed digits, six fingers"` |
| **`limb_topology`** | VQA Q5: *"valid limb topology and joint connections with natural bending angles and plausible skeletal structure"* | `bent backwards`, `impossible joint`, `broken joint`, `twisted limb`, `unnatural angle`, `inverted joint` | *"Natural limb topology and joint connections, natural bending angles, plausible articulated skeletal structure"* | `bent backwards, impossible joints, twisted limbs, broken bones, unnatural angles, inverted joints, dislocated` | `(0.15, 0.30, 0.85, 0.85)` | **Pos**: `"natural limb topology, natural bending angles, plausible skeletal joints, correct anatomy"`<br>**Neg**: `"bent backwards, impossible joints, twisted limbs, broken bones, unnatural angles, inverted joints"` |
| **`unanchored_object`** | Spatial Q1: *"all objects, props, and furniture are physically supported or resting on surfaces with no unanchored floating objects"* | `floating object`, `unanchored`, `floating in air`, `hovering in air`, `levitating`, `suspended in mid-air` | *"Resting flat and firmly on the surface, grounded placement with realistic cast contact shadow beneath the base"* | `floating object, hovering in air, unanchored object, levitating, suspended in mid-air, floating prop` | `(0.20, 0.35, 0.80, 0.85)` | **Pos**: `"grounded object resting firmly on surface, contact shadow, stable placement, realistic physics"`<br>**Neg**: `"floating object, hovering in air, unanchored object, levitating, suspended in mid-air"` |
| **`disconnected_interaction`**| Spatial Q2: *"the {obj} is physically held or touched with continuous grasp contact and is not floating or disconnected"* | `disconnected`, `not touching`, `hovering near hand`, `not held`, `no contact`, `gap between hand` | `compile_interaction_bindings_natural`: *"hands firmly gripping the object with fingers visibly curled around it, maintaining unbroken physical contact, zero air gap"* | `disconnected grip, hovering near hand, floating object, detached, gap between hand and object, not touching` | `(0.15, 0.35, 0.85, 0.85)` | **Pos**: `"firmly gripping object, fingers wrapped around handle, direct physical contact, continuous grasp, zero gap"`<br>**Neg**: `"disconnected grip, hovering near hand, floating object, detached, gap between hand and object, not touching"` |

### 6.2 Benign Framing Crop Recognition (`BENIGN_ANATOMY_EXPLANATION_PATTERN`)
In `engine/original/review.py:248-282`, the text judge filters out false-positive anatomy defects when the vision model's description indicates deliberate camera framing:
- **Waist-Up / Bust Framing**: When the prompt explicitly describes `"medium shot from the waist up"`, Witness B notes that lower limbs are out of frame. The regex pattern `\b(?:waist-up|bust|headshot|portrait|close-up)\s+(?:crop|framing|view)\b` prevents this from being flagged as `missing_limbs`.
- **Hands in Pockets**: When character poses state `"hands resting inside coat pockets"`, the pattern `\b(?:in|inside)\s+(?:[^\s,;.\!?]+\s+){0,3}pockets?\b` suppresses `missing_limbs` or `distorted_digits` penalties.
- **Occluded by Furniture**: When prompts specify `"seated behind the wooden desk"`, the pattern `\b(?:hidden|obscured|behind)\s+(?:the\s+)?(?:table|desk|counter|wall|blanket)\b` ensures the review engine correctly attributes obscured legs to natural scene geometry.

---

## 7. Target Model Parameterization & Compilation Directives

PanelFlow Studio dispatches compiled prompts across three primary inference backends. Each backend has distinct tokenization mechanics, dimension requirements, and syntactic preferences.

### 7.1 Target Model Parameterization Matrix

| Parameter / Feature | Qwen Image 2.1 (`qwen_image_21`) | MiniMax Fast H3 Turbo (`minimax_h3_turbo_i2v`) | Legacy SDXL / ControlNet (`anime_sdxl_*`) |
|---|---|---|---|
| **Primary Execution Path** | `ArtEngine.generate` (`engine/comfyui/art.py`) | Video workflow (`minimax_h3_turbo_i2v.api.json`) | `ComfyRunner` legacy SDXL paths |
| **Text Encoder** | `qwen3vl_8b_int8_convrot.safetensors` (VLM) | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | Dual CLIP (OpenCLIP ViT-bigG + CLIP ViT-L) |
| **Dimension Alignment** | `multiple_of: 16` | `multiple_of: 32` | `multiple_of: 64` (or 8) |
| **Standard Aspect Ratio** | 832x1216 (Full), 1024x1024 (Close/Med), 1344x768 (Wide) | 1344x768 (16:9 Widescreen, 124 frames @ 24fps) | 832x1216, 1024x1024, 1344x768 |
| **Prompt Syntax Structure** | Cohesive natural language prose paragraph | 6-Heading Directorial Schema or Camera Motion Prompt | Comma-delimited Danbooru tags with weight syntax `(tag:1.3)` |
| **Character Identity Syntax** | Unnamed role noun phrases (*"the teenage girl with short brown hair"*) | `subject_definitions:` and `retention_analysis:` | Tag lists (`1girl, brown_hair, short_hair, green_eyes`) |
| **Style Anchoring Syntax** | 4-tier natural sentences (*"Hand-drawn 2D anime illustration. Crisp dark ink outlines..."*) | Visual style anchor matched to `first_frame` image | Danbooru tags (`anime_style, cel_shading, clean_linework`) |
| **Negative Prompt Policy** | Dense anatomical & spatial contact defect suppression | Temporal jitter, abrupt jump cut, and face morphing suppression | Booru quality & defect tags (`lowres, bad anatomy, bad hands...`) |
| **Interaction Directives** | Natural kinematic contact sentences (`compile_interaction_bindings_natural`) | Subtle micro-actions and cloth/hair secondary physics | Kinematic binding tags (`compile_interaction_bindings_tags`) |

---

### 7.2 Canonical 7-Tier Positive Token Sequence (Qwen Image 2.1)

For Qwen Image 2.1 (`ArtEngine`), prompts are compiled into a dense, unified natural language prose paragraph following this strict 7-tier hierarchy:

```
[Tier 1: Medium & Renderer Anchor]
└── Material and rendering paradigm (e.g. "Hand-drawn 2D anime illustration, flat cel-shading, matte gouache background")

[Tier 2: Camera Framing, Resolution Bucket & Margins]
└── Shot type, aspect ratio, headroom clearance (e.g. "Medium shot from waist up with generous 15% headroom above hair")

[Tier 3: Subject Identity & Spatial Partitioning]
└── Unnamed role descriptions, spatial coordinate decoupling (e.g. "On the left: a teenage girl with short brown hair...")

[Tier 4: Action Kinematics & Physical Contact Bindings]
└── Interaction verbs with 360-degree contact (e.g. "Fingers firmly curled around handle with zero air gap")

[Tier 5: Environment, Palette & Lighting Physics]
└── Fixed scene palette, key light direction, shadow mechanics (e.g. "Warm amber palette, 3000K lantern illumination")

[Tier 6: Key Directorial Visual Requirements]
└── Narrative-critical visual elements from story beat (clues, props, environmental state)

[Tier 7: Technical Invariant Suffix]
└── Final boundary guardrails ("Clean single frame, zero text, zero speech bubbles, zero watermark")
```

---

## 8. Reference Implementation Examples

### 8.1 Multi-Panel Sequence Walk-Through (`mystery` Genre)

The following 3-panel sequence illustrates end-to-end prompt engineering in practice for an original mystery episode. Notice how the **Four-Tier Style Anchor** remains bit-for-bit invariant across all three panels, while framing, characters, actions, and camera directives adapt dynamically.

#### Panel 1: Establishing Scene (Wide Shot)
- **Shot Specification**: `shot="wide"`, `num_characters=1`, `location="victorian_study"`
- **Resolution Bucket**: `(1344, 768)` (Widescreen Landscape)
- **Compiled Positive Prompt**:
  ```text
  Detective noir anime style, atmospheric 2D graphic illustration, matte paper finish. Crisp bold ink outlines, defined silhouette contours, clean architectural line weight. Muted vintage palette, rich sepia and charcoal tones, deep umber accents, restrained amber highlights. High-contrast dramatic side-lighting, Venetian blind shadow patterns, atmospheric dim lantern lighting. Wide shot showing the whole scene and the surroundings, spacious empty room with characters fully in frame. In the center of the dimly lit Victorian study: an adult man with sharp angular features, short slicked-back black hair, and intense gray eyes, wearing a dark wool trench coat, standing beside a mahogany writing desk. On the desk: a scattered array of antique manuscripts and a brass magnifying glass resting flat and firmly on the polished wood with a dark contact shadow beneath its rim. Single clean illustration, no text, no captions, no speech bubbles, no watermark.
  ```
- **Compiled Negative Prompt**:
  ```text
  lowres, bad anatomy, bad hands, extra digits, missing fingers, fused fingers, six fingers, polydactyly, syndactyly, deformed digits, mutated hands, broken wrists, extra limbs, polycephaly, duplicate heads, floating object, disconnected grip, cropped head, cut off feet, blurry, text, watermark, colorful, neon, flat lighting, 3d render, cgi, bright cheerful colors, oversaturated, photorealistic
  ```

#### Panel 2: Investigation & Interaction (Medium Shot)
- **Shot Specification**: `shot="medium"`, `num_characters=1`, `action="examines torn letter"`
- **Resolution Bucket**: `(1024, 1024)` (Square, balanced bust framing)
- **Compiled Positive Prompt**:
  ```text
  Detective noir anime style, atmospheric 2D graphic illustration, matte paper finish. Crisp bold ink outlines, defined silhouette contours, clean architectural line weight. Muted vintage palette, rich sepia and charcoal tones, deep umber accents, restrained amber highlights. High-contrast dramatic side-lighting, Venetian blind shadow patterns, atmospheric dim lantern lighting. Medium shot from the waist up with generous headroom above the hair, subject completely in frame with zero top cropping. An adult man with sharp angular features, short slicked-back black hair, and intense gray eyes, wearing a dark wool trench coat over a white collared shirt. Physical contact: hands firmly holding the torn parchment letter, fingers visibly supporting the lower edge with unbroken physical contact and zero air gap. Hands drawn with natural human anatomy, exactly five distinct separated fingers including thumb, articulated knuckles. Single clean illustration, no text, no captions, no speech bubbles, no watermark.
  ```
- **Compiled Negative Prompt**:
  ```text
  lowres, bad anatomy, bad hands, extra digits, missing fingers, fused fingers, six fingers, polydactyly, syndactyly, deformed digits, mutated hands, broken wrists, extra limbs, polycephaly, duplicate heads, floating object, disconnected grip, cropped head, cut off feet, blurry, text, watermark, colorful, neon, flat lighting, 3d render, cgi, bright cheerful colors, oversaturated, photorealistic
  ```

#### Panel 3: Dramatic Clue Reveal (Extreme Close-Up)
- **Shot Specification**: `shot="extreme_close"`, `num_characters=1`, `focus="eyes reacting to cipher"`
- **Resolution Bucket**: `(1024, 1024)` (Macro Face Focus)
- **Compiled Positive Prompt**:
  ```text
  Detective noir anime style, atmospheric 2D graphic illustration, matte paper finish. Crisp bold ink outlines, defined silhouette contours, clean architectural line weight. Muted vintage palette, rich sepia and charcoal tones, deep umber accents, restrained amber highlights. High-contrast dramatic side-lighting, Venetian blind shadow patterns, atmospheric dim lantern lighting. Extreme close-up macro framing focusing tightly on the face and eyes, perfectly centered facial composition. An adult man with intense gray eyes, wide dilated pupils reflecting the amber glow of the lantern, furrowed dark eyebrows, sharp bridge of the nose. Natural facial symmetry, distinct eyelashes, zero extra eyes, perfectly proportioned cranial anatomy. Single clean illustration, no text, no captions, no speech bubbles, no watermark.
  ```
- **Compiled Negative Prompt**:
  ```text
  lowres, bad anatomy, bad eyes, extra eyes, missing pupils, distorted face, blurry irises, text, watermark, colorful, neon, flat lighting, 3d render, cgi, bright cheerful colors, oversaturated, photorealistic
  ```

---

### 8.2 Two-Character Dynamic Confrontation (`fantasy` Genre)

- **Shot Specification**: `shot="wide"`, `num_characters=2`, `characters=["Elena", "Valen"]`, `action="tense confrontation"`
- **Resolution Bucket**: `(1344, 768)` (Widescreen Landscape, horizontal partitioning)
- **Compiled Positive Prompt**:
  ```text
  Epic fantasy anime feature film animation still, rich 2D anime rendering, vivid matte finish. Fine detailed ink outlines, clean elegant line art, defined dynamic contours. Vivid saturated jewel tones, lapis lazuli blues, emerald greens, gold leaf highlights, rich contrast. Dramatic cinematic golden hour temple sunlight, magical soft rim lighting, bioluminescent accents, ambient occlusion. Widescreen landscape shot showing two distinct characters side-by-side with clear horizontal separation. On the left side of frame: a teenage girl with long braided silver hair and violet eyes, wearing an azure battle mage robe with silver embroidery, holding a wooden arcane staff with fingers firmly wrapped around the shaft. On the right side of frame: a young man with short spiky raven hair and amber eyes, wearing dark leather armor with iron pauldrons, hand resting flat against the pommel of his sheathed broadsword. Clear physical separation between both characters, distinct individual identities, zero feature blending. Single clean illustration, no text, no captions, no speech bubbles, no watermark.
  ```
- **Compiled Negative Prompt**:
  ```text
  character blending, merged identities, shared features, duplicate faces, hybrid characters, feature swapping, swapped clothing, overlapping bodies, crowded framing, occluded characters, lowres, bad anatomy, bad hands, extra digits, missing fingers, fused fingers, six fingers, polydactyly, syndactyly, deformed digits, floating object, disconnected grip, cropped head, 3d render, cgi, photorealistic skin, modern clothing, modern buildings
  ```

---

### 8.3 MiniMax H3 Turbo Video Motion Prompt Compilation

- **Input Static Asset**: Panel 2 from Section 8.1 (Investigator holding torn letter in study).
- **Directorial Intent**: Slow cinematic push-in toward the detective as he reads the cipher, subtle secondary dynamics on trench coat collar.
- **Compiled Video Motion Prompt (Native 6-Heading Schema)**:
  ```text
  subject_definitions:
  - Subject 1: An adult man with short slicked-back black hair and gray eyes, wearing a dark trench coat, holding a parchment letter with both hands. Identity and attire locked to reference frame.

  summary:
  The camera performs a slow cinematic push-in towards the detective as his eyes track down the parchment page in the dim lantern light.

  retention_analysis:
  Preserve exact facial bone structure, slicked-back hair shape, trench coat texture, and hand grip on the parchment from the first frame. Zero morphing of facial features, zero digit deformities, zero clothing alteration across all 124 frames.

  detailed_description:
  camera_movement: Slow cinematic camera push in towards the subject along the central optical axis, smooth steady optical track, maintaining crisp focal lock on irises.
  subject_description: The man's eyes move subtly from left to right as he reads the text, breathing naturally with subtle chest movement, hands holding the letter steady with unbroken physical contact.
  environmental_details: Dust motes drifting slowly through the amber lantern light beam, Venetian blind shadow patterns resting stable against the rear bookshelf.
  lighting_and_atmosphere: Warm amber 3000K lantern illumination consistent throughout the sequence, stable contact shadows.

  overall_soundscape:
  Quiet nighttime room ambiance, distant rain tapping against window glass, faint rustle of dry parchment.

  non_diegetic_music:
  Subtle low cello drone with contemplative solo piano notes.
  ```
- **Compiled Video Negative Prompt**:
  ```text
  fast jerky motion, abrupt camera jump cut, camera jitter, erratic panning, violent camera shake, handheld wobble, morphing face, melted face, flickering facial features, jittery artifacts, twitching anatomy, faceless pedestrians, shape-shifting, temporal noise, text, watermark, bad anatomy
  ```

---

### 8.4 Character Turnaround Reference Sheet (`turnaround` Framing)

- **Target Asset**: Model Sheet for 2D Rigging, 3D Mesh Animation, and Neural Alpha Matting (`engine/original/rigging.py`).
- **Resolution Bucket**: `(1536, 768)` (Ultra-Wide Landscape 2:1)
- **Compiled Positive Prompt**:
  ```text
  Hand-drawn 2D anime model sheet, clean orthographic character turnaround, matte finish. Crisp uniform dark ink outlines, smooth finished linework, defined silhouette edges. Authentic production model sheet palette, clean flat cel shading, neutral solid 18% gray background. Flat diffused three-point studio lighting, uniform illumination across all angles, zero harsh cast shadows. Full length standing character reference from head to toe, four sequential orthographic views from left to right: front view, three-quarter view, profile side view, back view. A teenage girl with short choppy chestnut-brown bob hair, almond-shaped emerald-green eyes, wearing a canary-yellow hooded raincoat with brass buttons and dark blue denim trousers. Unobstructed neutral A-pose with arms angled 45 degrees downward away from torso, hands open with fingers spread and clearly separated, visible articulated joints at elbows, wrists, hips, and knees. Clean horizontal alignment across all four views, wide empty margins around all figures, zero overlapping limbs, zero edge cropping. Single clean character sheet, no text, no labels, no watermark.
  ```
- **Compiled Negative Prompt (`RIGGING_NEGATIVE`)**:
  ```text
  occluded limbs, overlapping appendages, crossed limbs, hands in pockets, foreshortening, dramatic perspective, dynamic pose, action pose, motion blur, tilted head, bent posture, dramatic shadows, harsh directional light, deep cast shadows, complex background, background clutter, scenery, props, furniture, merged limbs, connected limbs, fused fingers, hidden hands, blurred joints, floating objects, disconnected hands, lowres, bad anatomy, bad hands, extra digits, missing fingers, text, watermark, signature
  ```

---

## 9. Conclusion & Implementation Checklist

The prompt engineering architecture codified in this guide provides a complete, deterministic defense-in-depth framework for PanelFlow Studio. By systematically eliminating subjective buzzwords, locking 4-tier style invariants, enforcing unnaming and kinematic bindings, aligning aspect ratios to 1-MP buckets, and structuring video prompts around motion deltas, the pipeline eliminates the primary causes of generative failure before inference occurs.

### Implementation Checklist for Downstream Milestones:
- [x] **Milestone M1**: Authoritative practitioner guide established in `docs/PROMPT_PRACTITIONER_GUIDE.md` (Requirement R1 complete).
- [ ] **Milestone M2**: Implement tool-agnostic Pydantic prompt schemas, 4-tier style presets, unnaming protocol, and model-specific compilers (`TargetModel.QWEN_IMAGE_21`, `TargetModel.MINIMAX_H3`, `TargetModel.SDXL`) in `engine/original/prompt.py`.
- [ ] **Milestone M3**: Integrate `PromptCompiler` into `engine/original/shotspec.py`, `engine/original/art.py`, and `engine/original/beats.py`; verify full test suite pass rate and clean TypeScript build.
