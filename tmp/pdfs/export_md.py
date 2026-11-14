import runpy
from pathlib import Path

ns = runpy.run_path('tmp/pdfs/build_pack.py')
concepts = ns['concepts']
out = Path('output/pdf/panelflow_stick_figure_shorts_prompt_pack.md')

def safe(text):
    return str(text).replace('\r', '').replace('\n', ' ').strip()

lines = [
    '# PanelFlow Shorts Lab: 10 Stick-Figure Video Concepts', '',
    '> Production-ready prompt pack for vertical educational explainers. Virality cannot be guaranteed.', '',
    '**Format:** Vox-inspired editorial stick-figure animation  ',
    '**Target length:** 45-56 seconds per concept  ',
    '**Pipeline:** MiniMax H3 Image + MiniMax H3 video + Qwen3-TTS + ACE-Step 1.5*', '',
    '## How to use this pack', '',
    'Treat each scene as an individual short H3 shot, then assemble clips, narration, captions, music and effects in PanelFlow. Match clip duration to the registered graph limits and trim to narration.', '',
    '### Shared image prompt prefix', '',
    '> Vertical 9:16 educational explainer; Vox-inspired editorial stick-figure animation, original generic visual language; recurring protagonist: black circular head, thin consistent limbs, small teal scarf, expressive pose; crisp black outlines, flat limited palette, geometric backgrounds, high contrast, readable silhouette, negative space for captions added later; coherent 2D vector-like illustration; no photorealism, 3D, logos, watermarks, readable text, extra limbs or clutter.', '',
    'Reuse the host reference wherever image reference conditioning is supported. Keep neighboring keyframes close in character scale and camera distance.', '',
    '### Shared H3 video prompt prefix', '',
    '> Animate the supplied keyframe as a clean 2D editorial stick-figure explainer. Preserve exact host, props, palette and layout. One simple action only, with the gentle camera move stated below. Stable line art and flat shapes; no morphing, new people or objects, cuts, readable text, dialogue or soundtrack. End on a stable frame. Append each scene motion direction.', '',
    '### Shared Qwen3-TTS voice direction', '',
    '> English, warm bright adult explainer voice, conversational and precise, lightly witty on comic lines, calm and respectful on sensitive topics; natural Indian English accent if supported; clear consonants, 145-155 words per minute, varied emphasis and short pauses; no shout or influencer exaggeration. Read supplied text verbatim; add no words. Generate per timed beat if needed, then join.', '',
    '### Audio mix', '',
    'Keep narration clearly in front and duck music under speech. Add listed SFX manually at the marked beats. Burn captions inside the mobile safe area. Use rights-cleared audio.', '',
    '> **Model name note:** The request said “DSC Step 140.” This pack assumes ACE-Step 1.5, the closest verifiable name. Confirm PanelFlow’s exact registered ID before generation; local graph syntax may vary.', '',
    '## Research approach', '',
    'No reliable recipe guarantees virality. The concepts use clear openings, compact mini-stories, an honest payoff, a single useful takeaway, and a genuine discussion question. Use retention and audience response to learn what to make next; do not optimize for compulsive use.', '',
    '### Pilot plan', '',
    'Make three pilots from comedy, practical safety, and relationship/communication. Keep style consistent and change one major variable at a time. Compare with your own recent, similar-length videos.', '',
]

for i, c in enumerate(concepts, 1):
    lines += [
        '---', '', f'## {i:02d}. {safe(c["title"])}', '',
        f'**Lane:** {safe(c["tag"])}', '',
        f'**Premise:** {safe(c["prem"])}', '',
        f'**Hook:** {safe(c["hook"])}', '',
        f'**Takeaway:** {safe(c["take"])}', '',
        f'**Suggested title:** {safe(c["card"])}', '',
        '### Narration script', '',
    ]
    for tm, spoken in c['narr']:
        lines.append(f'- **{tm}:** {safe(spoken)}')
    lines += ['', '### Scene prompts', '']
    for j, (name, beat, image, video, sfx, caption) in enumerate(c['scenes'], 1):
        lines += [
            f'#### Scene {j}: {safe(name)} ({c["narr"][j-1][0]})', '',
            f'**Visual beat:** {safe(beat)}', '',
            f'**MiniMax H3 Image prompt:** {safe(image)}', '',
            f'**MiniMax H3 video prompt:** {safe(video)}', '',
            f'**On-screen caption:** {safe(caption)}  ',
            f'**Sound effect:** {safe(sfx)}', '',
        ]
    lines += [
        '### Qwen3-TTS direction', '',
        ('Use the shared direction. Lightly amused at setup; soften on the takeaway; never sneer at the person.' if 'COMEDY' in c['tag'] else 'Use the shared direction. Measured, empathetic and direct; avoid melodrama.'), '',
        '### ACE-Step 1.5 music prompt', '',
        f'> {safe(c["music"])}', '',
        f'**End question:** {safe(c["cta"])}', '',
        '**Production check:** Sync narration and captions, cut on visual beats, keep effects sparse, inspect for accidental text, and review sensitive-topic accuracy.', '',
    ]

lines += [
    '## Upload and learning checklist', '',
    '- First frame presents the premise immediately; no logo intro.',
    '- Opening line and title promise the same thing.',
    '- One clear idea; advice includes sensible limits.',
    '- Stick-figure design and palette stay consistent.',
    '- No accidental text, brands or unsafe generated details.',
    '- Captions are legible on mobile and clear of interface controls.',
    '- Voice is intelligible; music sits below it; SFX match the action.',
    '- Sensitive scenes show adults, consent, agency and safety.',
    '- No guaranteed results or misleading shock framing.',
    '- Review retention and compare similar-length uploads before changing one major element.', '',
    '## Research links', '',
    '- [YouTube Shorts deep dive](https://blog.youtube/creator-and-artist-stories/youtube-shorts-deep-dive/)',
    '- [YouTube audience retention](https://support.google.com/youtube/answer/9314415?co=PLATFORM%3DDesktop&hl=en)',
    '- [Instagram Best Practices](https://about.fb.com/news/2024/10/best-practices-education-hub-creators-instagram/)',
    '- [MiniMax H3 video prompt guide](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md)',
    '- [MiniMax H3 announcement](https://www.minimax.io/news/minimax-h3-open-source)',
    '- [Qwen3-TTS repository](https://github.com/QwenLM/Qwen3-TTS)',
    '- [ACE-Step 1.5 Gradio guide](https://github.com/ace-step/ACE-Step-1.5/blob/main/docs/en/GRADIO_GUIDE.md)',
    '- [ACE-Step 1.5 musician guide](https://github.com/ace-step/ACE-Step-1.5/blob/main/docs/en/ace_step_musicians_guide.md)',
    '- PanelFlow local references: `docs/H3_LONG_VIDEO.md` and `docs/H3_IMAGE_EDIT.md`', '',
    '*Research checked 13 November 2026. Platform guidance is not a guarantee of reach. Verify local PanelFlow model IDs and workflow syntax before generation.*', '',
]

out.write_text('\n'.join(lines), encoding='utf-8')
print(out.resolve(), f'{len(lines)} lines', f'{out.stat().st_size} bytes')
