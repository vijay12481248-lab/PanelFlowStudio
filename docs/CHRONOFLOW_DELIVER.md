# ChronoFlow Deliver page

The **Deliver** button on the page rail opens render settings (left), the normal monitor (centre) and a render queue (right). It used to start a
download at once with no choices. "Bake Master Cut" on the timeline stays as the quick export at timeline size.

## How a render runs (`engine/chronoflow/deliver.py`, API under `/api/chronoflow/deliver/*`)
1. **Timeline master**: the existing EDL renderer (cuts, transitions, colour grades, Fusion effects) at the timeline's own size.
2. **One final encode** with your settings: size and fit, frame rate, codec, quality or bitrate, audio, loudness.
One render runs at a time (they all want the CPU or GPU); the rest wait. Progress is real (FFmpeg's own), and a render can be cancelled while queued or
while it encodes (the timeline-master stage cannot be interrupted once it starts). Each render keeps a JSON record in `output/chronoflow/deliver/_records`,
so the list survives a restart; a render the engine lost mid-way is shown as failed. Finished files are in `output/chronoflow/deliver/`.

## Settings
| Setting | Choices |
|---|---|
| Presets | YouTube 1080p, YouTube 4K, Shorts / Reels 9:16 (fill), Square 1:1, H.265 small file, ProRes 422 master, Draft 720p, Match timeline |
| Range | whole timeline, or the In/Out marks (I and O keys) |
| Format | H.264 MP4, H.265 MP4, ProRes 422 MOV (PCM audio), VP9 WebM (Opus) |
| Encoder | CPU, or NVIDIA NVENC for H.264/H.265 (shares the GPU with ComfyUI and Ollama) |
| Resolution + fit | match timeline, 720p to 4K, vertical, square, or custom; fit (bars), fill (crop) or stretch |
| Frame rate | keep, 23.976, 24, 25, 29.97, 30, 50, 59.94, 60 |
| Quality | CRF (lower = better and bigger), ProRes profile, or an explicit video bitrate |
| Audio | on/off, AAC 128 to 320 kbps, 44.1 or 48 kHz, loudness off or -14 / -16 / -23 LUFS (two-pass `loudnorm`, true peak -1.5 dBTP) |

## Verified
- `tests/unit/test_chronoflow_deliver.py` (22): validation, scaling and fill-crop to exact size, fps, range length, loudness within 1.5 LU, ProRes/HEVC/no audio,
  queue order, unique names, cancel, delete, restart recovery.
- A real render of the 31 s, 6-clip graded job through the page: 1080x1920 H.264 30 fps, AAC 48 kHz, 31.03 s, integrated loudness exactly -14.0 LUFS, grades visible
  in the picture, finished in about 16 s on the CPU encoder. A 2 s to 6 s range gave exactly 4.0 s; a queued render was cancelled.

## Limits
- The timeline master is encoded once at CRF 18 before the final encode, so the result is one generation lossier than a single-pass render.
- NVENC, VP9 and the 4K preset are covered by option building but were not rendered on real footage here.
- Output goes to `output/chronoflow/deliver/`; there is no folder picker yet. The page shows the full path and offers Download.
- No upload step: publishing stays a separate, explicit action (YouTube uploads are private by default).
