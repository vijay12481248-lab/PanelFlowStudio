# PanelFlow Studio — Known Limitations & Scope Guardrails (v1.0.0)

This document defines the architectural guardrails, environmental constraints, and intended boundaries of PanelFlow Studio v1.

---

## 1. Out-of-Scope Capabilities (v1 Strictly Excluded)

The following features were intentionally excluded from v1 to ensure release stability and legal safety:
1. **Direct Social Media / Publishing Uploads**: No automated uploads to YouTube, TikTok, Instagram Reels, or X. All rendered video files are output locally as standard MP4 files.
2. **Cloud Rendering Services**: All composition and rendering occurs locally via FFmpeg. No remote render clusters or paid cloud queues.
3. **DRM / Paywall Circumvention**: Acquisition strictly respects rights verification declarations and does not include tools to defeat CAPTCHAs, paywalls, or subscription logins.
4. **AI Frame Interpolation**: Motion comics use 30fps camera transformations (pans, zooms, Ken Burns holds) rather than neural frame generation or morphing.

---

## 2. Platform & Hardware Boundaries

1. **GPU Acceleration**:
   - Primary video encoding uses software `libx264` (medium preset, CRF 18) for maximum cross-platform reproducibility and pixel perfection.
   - Video compositions run at 30 fps (1920×1080 standard).
2. **Aspect Ratio Letterboxing**:
   - Comic panels with extreme aspect ratios (e.g. ultra-tall webtoon strips) are letterboxed or contained within standard 16:9 or 9:16 frames with blurred background extension to avoid stretching.
3. **Memory Footprint**:
   - Panel composition pipes frames directly to the FFmpeg stdin stream without caching uncompressed frames on disk, keeping runtime RAM under 600 MB.
