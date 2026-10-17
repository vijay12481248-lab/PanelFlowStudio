# PanelFlow Studio — Output Profiles Specification

## 1. Supported Output Profiles

PanelFlow provides predefined, broadcast-tested encoding profiles configured for distinct distribution channels:

| Profile Identifier | Resolution | Aspect Ratio | FPS | Video Codec | Pixel Format | CRF / Bitrate | Audio Codec | Audio Bitrate | Target Use Case |
|---|---|---|---|---|---|---|---|---|---|
| `standard_1080p` | $1920 \times 1080$ | 16:9 | 30 | `libx264` | `yuv420p` | CRF 18 (fast) | `aac` | 192 kbps | YouTube Landscape, Web Video, Broadcast Master |
| `vertical_shorts` | $1080 \times 1920$ | 9:16 | 30 | `libx264` | `yuv420p` | CRF 20 (fast) | `aac` | 192 kbps | YouTube Shorts, TikTok, Instagram Reels |
| `square_feed` | $1080 \times 1080$ | 1:1 | 30 | `libx264` | `yuv420p` | CRF 20 (fast) | `aac` | 192 kbps | Social Feeds, Instagram Post, Square Thumbnails |
| `draft_720p` | $1280 \times 720$ | 16:9 | 24 | `libx264` | `yuv420p` | CRF 23 (veryfast) | `aac` | 128 kbps | Fast Iteration Preview, Automated Test Verification |
| `preview_1080p` | $1920 \times 1080$ | 16:9 | 30 | `libx264` | `yuv420p` | CRF 22 (veryfast) | `aac` | 160 kbps | Rapid Quality Review |

---

## 2. Container Configuration

All profiles output to the standard **MP4** container (`ISO/IEC 14496-14`) with the following strict settings:
- **FastStart Moov Atom Relocation** (`-movflags +faststart`): The `moov` atom containing stream index metadata is relocated to the beginning of the file, allowing immediate web playback before full download completes.
- **Color Compatibility** (`-pix_fmt yuv420p`): Downsamples chroma from 4:4:4 RGB to 4:2:0 YUV, ensuring compatibility with mobile decoders, older browsers, and hardware video players.
- **Audio Stream Sync** (`-shortest`): Clamps video and audio stream durations to eliminate trailing silent black frames.
