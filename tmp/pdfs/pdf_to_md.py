from pathlib import Path
import pdfplumber, re
pdf=Path('output/pdf/panelflow_stick_figure_shorts_prompt_pack.pdf')
out=Path('output/pdf/panelflow_stick_figure_shorts_prompt_pack.md')
pages=pdfplumber.open(pdf)
def clean(s):
    s=s.replace('\ufffd', "'").replace('\u2019', "'").replace('\u2018', "'").replace('\u201c','"').replace('\u201d','"').replace('\u2013','-').replace('\u2014',' - ')
    s=s.replace('\u00a0',' ')
    s=re.sub(r'PANELFLOW / STICK-FIGURE SHORTS PROMPT PACK\s*\d+\s*$', '', s)
    return s.strip()
parts=[clean(p.extract_text() or '') for p in pages.pages]
# reconstruct document in logical order from page text, remove running footer and preserve readable paragraphs
lines=[]
for i,part in enumerate(parts):
    if not part: continue
    for line in part.splitlines():
        line=line.strip()
        if not line or line=='PANELFLOW / STICK-FIGURE SHORTS PROMPT PACK': continue
        if line in ('PANELFLOW / SHORTS LAB',): continue
        if line.startswith('Prepared 13 November'): continue
        lines.append(line)
# convert known section labels and concepts into markdown, keep per-scene prompt text intact
out_lines=['# PanelFlow Shorts Lab: 10 Stick-Figure Video Concepts','', '> Production-ready prompt pack for vertical educational explainers. Virality cannot be guaranteed.','']
concept_heads={f'{i:02d} /' for i in range(1,11)}
for line in lines:
    if line.startswith('10 stick-figure') or line.startswith('video concepts'): continue
    if line.startswith('How to use this pack') or line.startswith('What the research suggests') or line.startswith('Upload and learning checklist') or line.startswith('Source notes'):
        out_lines += ['## '+line,'']; continue
    if re.match(r'^\d{2} / ',line):
        out_lines += ['---','', '## '+line,'']; continue
    if line in ('Narration script','Scene prompts / one keyframe + one short H3 clip per beat','Shared image prompt prefix','Shared H3 video prefix','Shared Qwen3-TTS voice direction','Audio mix','Pilot plan','ACE-Step 1.5 music prompt','Qwen3-TTS direction'):
        out_lines += ['### '+line,'']; continue
    if re.match(r'^Scene \d+ \| ',line):
        out_lines += ['', '**'+line+'**','']; continue
    if re.match(r'^0:\d\d-0:\d\d ',line):
        m=re.match(r'^(0:\d\d-0:\d\d)\s+(.*)$',line)
        out_lines.append(f'- **{m.group(1)}** {m.group(2)}'); continue
    for label in ('Premise.','Hook.','Takeaway.','Suggested title.','Visual:','MiniMax H3 Image:','MiniMax H3 video:','Caption:','Qwen3-TTS direction','ACE-Step 1.5 music prompt','End question:'):
        if line.startswith(label):
            key, val=line.split(' ',1)
            out_lines.append(f'**{key}** {val}')
            break
    else:
        if line.startswith('- YouTube') or line.startswith('- Meta') or line.startswith('- MiniMax') or line.startswith('- QwenLM') or line.startswith('- ACE-Step') or line.startswith('- PanelFlow'):
            out_lines.append(line)
        elif line.startswith('- First frame') or line.startswith('- Opening line') or line.startswith('- One clear') or line.startswith('- Stick-figure') or line.startswith('- No accidental') or line.startswith('- Captions') or line.startswith('- Voice') or line.startswith('- Sensitive') or line.startswith('- No guaranteed') or line.startswith('- Review retention'):
            out_lines.append(line)
        else:
            out_lines.append(line)
    if line.startswith('End question:') or line.startswith('PanelFlow'):
        out_lines.append('')
# Improve url source section by adding full clickable links
out_lines += ['', '## Research links', '', '- [YouTube Shorts deep dive](https://blog.youtube/creator-and-artist-stories/youtube-shorts-deep-dive/)','- [YouTube audience retention](https://support.google.com/youtube/answer/9314415?co=PLATFORM%3DDesktop&hl=en)','- [Instagram Best Practices](https://about.fb.com/news/2024/10/best-practices-education-hub-creators-instagram/)','- [MiniMax H3 video prompt guide](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md)','- [MiniMax H3 announcement](https://www.minimax.io/news/minimax-h3-open-source)','- [Qwen3-TTS repository](https://github.com/QwenLM/Qwen3-TTS)','- [ACE-Step 1.5 Gradio guide](https://github.com/ace-step/ACE-Step-1.5/blob/main/docs/en/GRADIO_GUIDE.md)','- [ACE-Step 1.5 musician guide](https://github.com/ace-step/ACE-Step-1.5/blob/main/docs/en/ace_step_musicians_guide.md)','- PanelFlow local references: `docs/H3_LONG_VIDEO.md`, `docs/H3_IMAGE_EDIT.md`','']
out.write_text('\n'.join(out_lines),encoding='utf-8')
print(out.resolve(), 'lines=',len(out_lines), 'bytes=',out.stat().st_size)

