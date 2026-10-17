# PanelFlow Studio — Production Renderer Architecture (Milestone 7)

## 1. Subsystem Overview

The **Production Renderer** is the terminal visual synthesis engine of PanelFlow Studio. It takes the deterministic motion plan produced by the Motion Director (`VisualTimeline`) and the authoritative audio timings produced by the Audio Director (`MasterAudioTimeline`), and renders a broadcast-quality, synchronized MP4 video presentation.

```
+-------------------------------------------------------------------------+
|                           PANELFLOW PIPELINE                            |
|                                                                         |
| Acquisition -> Normalization -> Panels -> OCR -> Story -> Script        |
|                                                                         |
|        [Approved Script + Audio]          [Visual Sources / Panels]     |
|                   │                                   │                 |
|                   ▼                                   ▼                 |
|         MasterAudioTimeline                    Motion Director          |
|                   │                                   │                 |
|                   └───────────────┬───────────────────┘                 |
|                                   │                                     |
|                                   ▼                                     |
|                             VisualTimeline                              |
|                                   │                                     |
|                                   ▼                                     |
|                        +─────────────────────+                          |
|                        |    RenderEngine     |                          |
|                        | compile_render_plan |                          |
|                        +──────────┬──────────+                          |
|                                   │                                     |
|                            RenderPlan (JSON)                            |
|                                   │                                     |
|            ┌──────────────────────┴──────────────────────┐              |
|            ▼                                             ▼              |
|     [AudioMixer]                                  [FrameComposer]       |
|  - 48 kHz Stereo Master                        - Camera Pan / Zoom      |
|  - Dialogue Ducking (-8 dB)                    - COVER / CONTAIN Fit    |
|  - Peak Soft Limiting (-1 dBFS)                - Cinematic Effects      |
|            │                                   - Contrast Subtitles     |
|            ▼                                             │              |
|    mixed_audio.wav                                       ▼              |
|            │                                  Raw RGB24 Frame Pipe      |
|            │                                             │              |
|            └──────────────────────┬──────────────────────┘              |
|                                   ▼                                     |
|                         [FFmpegEncoder]                                 |
|                       - libx264 / yuv420p                               |
|                       - aac stereo 48 kHz                               |
|                       - faststart MP4 container                         |
|                                   │                                     |
|                                   ▼                                     |
|                           output_video.mp4                              |
|                                   │                                     |
|                                   ▼                                     |
|                         [RenderValidator]                               |
|                       - ffprobe format audit                            |
|                       - 5-point frame sampling                          |
|                       - Luminance / black frame audit                   |
|                       - contact_sheet.jpg                               |
+-------------------------------------------------------------------------+
```

---

## 2. Core Architectural Pillars

### A. Rational Frame Clock (`RenderFrameClock`)
Floating-point time arithmetic inevitably introduces cumulative rounding errors (`0.1 + 0.2 != 0.3`). Over a 10-minute video rendered at 30 fps (18,000 frames), floating-point drift can misalign speech syllables with camera cuts by dozens of frames.

PanelFlow eliminates drift using rational arithmetic (`fractions.Fraction`):
- Exactly $1/30$ second per frame.
- Continuous time ranges $[t_{\text{start}}, t_{\text{end}}]$ are mapped into discrete, half-open frame intervals $[f_{\text{start}}, f_{\text{end}})$.
- Consecutive adjacent ranges partition the timeline with **zero gaps and zero frame overlaps**:
  $$\text{start\_frame}_{i+1} \equiv \text{end\_frame}_i$$

### B. Streaming Raw Frame Pipe (`FFmpegEncoder`)
Rendering full 1080p videos by dumping uncompressed PNG images to disk causes severe disk exhaustion and I/O bottlenecks. A 1-minute video generates 1,800 frames ($\approx 11 \text{ GB}$ of uncompressed image data).

PanelFlow streams raw `rgb24` byte buffers directly into FFmpeg's `stdin` via `subprocess.Popen`:
- **Command Line**: `ffmpeg -y -f rawvideo -vcodec rawvideo -s 1920x1080 -pix_fmt rgb24 -r 30 -i - -i audio.wav -c:v libx264 -pix_fmt yuv420p -crf 18 -preset fast -c:a aac -b:a 192k -shortest -movflags +faststart output.mp4`
- Eliminates intermediate PNG disk writes.
- To prevent OS pipe buffer deadlocks on verbose FFmpeg logs, `stderr` is directed to a local log file and `stdout` to `DEVNULL`.

### C. Authoritative Multi-Track Audio Mixing (`AudioMixer`)
The Audio Director provides an authoritative master audio timeline. The Renderer mixes all audio assets using `numpy` and `soundfile` at 48 kHz stereo:
- **Dialogue Tracks**: Authoritative speech audio mapped to exact timeline intervals with volume balance.
- **Background Music (BGM)**: Continuous music loop or pad, ducked by $-8\text{ dB}$ with a $0.25\text{s}$ attack ramp and $0.40\text{s}$ release ramp around all active dialogue intervals.
- **Sound Effects (SFX)**: Time-aligned impact and atmospheric stingers mixed into the master bed.
- **Broadcast Safety**: Sanitizes all `NaN` and `Inf` values, audits for clipping, and soft-limits signal peaks to $-1.0\text{ dBFS}$ ($\approx 0.891$).

### D. Bounded Frame Composition (`FrameComposer`)
Transforms static illustrations into cinematic shots:
- **Camera Pan & Zoom**: Lanczos-interpolated camera viewports with `COVER` (full bleed) or `CONTAIN` (pillarboxed/letterboxed with black or blurred background fill).
- **Cinematic Effects**: Decaying impact shakes, brightness flashes, subtle radial vignettes, and focus glow.
- **Subtitles & Captions**: Safe-area positioned dialogue text wrapped inside a semi-transparent dark pill background for guaranteed contrast on any art style.

### E. Post-Render Audit & Contact Sheet (`RenderValidator`)
A render is not considered complete until verified by `ffprobe`:
- Codec compliance: H.264 video, AAC audio, MP4 container.
- Resolution & Frame Rate: Exactly 1920x1080 at 30.0 fps.
- Multi-point frame sampling at 5%, 25%, 50%, 75%, and 95% of duration.
- Luminance audit ensuring zero pure-black frames.
- Automated contact sheet generation for human review.
