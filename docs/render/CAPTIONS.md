# PanelFlow Studio — Captions & Subtitles Specification

## 1. Subtitle Design Goals

Subtitles in PanelFlow Studio must fulfill three strict criteria:
1. **Perfect Audio Synchronization**: Subtitle appearance and disappearance are strictly locked to the millisecond-accurate `AudioInterval` timestamps produced by neural TTS speech synthesis.
2. **Universal Contrast & Readability**: Comic and manga artwork features extreme variations in local luminance (e.g. bright white explosions, pitch-black ink shading, colorful screentones). Plain black or white text frequently becomes unreadable. PanelFlow guarantees contrast through a dynamic contrast pill container.
3. **Broadcast Title-Safe Margins**: Text is contained within the standard 80% safe title zone, preventing UI clipping across diverse mobile displays and video players.

---

## 2. Visual Layout & Styling

- **Font & Rendering**: Clean typographic hierarchy with subpixel anti-aliasing.
- **Word Wrapping**: Automatically partitions sentences into balanced lines based on display width (maximum 30–45 characters per line on 1080p).
- **Positioning**: Bottom-centered, positioned at a $10\%$ vertical offset from the bottom canvas edge.
- **Contrast Pill Overlay**:
  - Background fill: `rgba(0, 0, 0, 185)` (semi-transparent obsidian).
  - Subtle border: `rgba(255, 255, 255, 40)` (1px outline).
  - Corner radius: `8px` rounded rectangle.
  - Padding: `16px` horizontal, `8px` vertical.
- **Drop Shadow**: Soft shadow `rgba(0, 0, 0, 240)` offset by `(+1px, +1px)` beneath pure white foreground text `rgba(255, 255, 255, 255)`.

---

## 3. Caption Lifecycle

Captions are attached to shots via `shot.captions: List[CaptionCue]`:
```python
CaptionCue(
    cue_id="cap_01",
    shot_id="shot_scene_01_01",
    text="Marcus paused at the precipice, reading the glowing conduits along the wall.",
    start_time=12.45,
    end_time=16.80,
    speaker_id="char_marcus"
)
```
During each frame $f$:
$$\text{timestamp\_sec} = \frac{f}{\text{fps}}$$
If $\text{start\_time} \le \text{timestamp\_sec} \le \text{end\_time}$, `CaptionRenderer` composites the contrast pill and wrapped text on top of the active camera and visual effects layer.
