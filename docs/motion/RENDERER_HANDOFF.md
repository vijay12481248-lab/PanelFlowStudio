# Motion Director -> Video Renderer Handoff Contract

## 1. Scope & Boundary

This document specifies the downstream contract consumed by the future video rendering pipeline (Milestone 7: FFmpeg / GPU composition engine).

The Motion Director produces a complete `VisualTimeline` JSON document. The renderer consumes this document without having to calculate scene flow, camera easing, or audio synchronization.

---

## 2. Invariants Guaranteed by Motion Director

1. **Continuous Clock Coverage**:
   - Shot 1 starts at `0.000s`.
   - Every subsequent shot $i$ satisfies $|start_i - end_{i-1}| \le 0.05s$.
   - The final shot matches `VisualTimeline.total_duration_sec`.

2. **Bounds Safe Coordinates**:
   - Visible frustums never leave $[0.0, 1.0] \times [0.0, 1.0]$.
   - Zoom factors are always $\ge 1.0$.

3. **Deterministic Evaluation**:
   - `interpolate_camera(start, end, t, easing)` yields the exact camera state at normalized progress $t \in [0.0, 1.0]$.
   - `compute_pixel_crop_at_time(start, end, t, src_w, src_h, tgt_w, tgt_h)` yields the exact source pixel rectangle $(left, top, right, bottom)$ to crop.

4. **Multi-Plane Parallax Ready**:
   - If `shot.layer_instructions` contains segmented planes, each layer specifies `relative_offset_x`, `relative_offset_y`, `motion_factor`, and `blend_mode`.
   - If layers are absent, `fallback_flat=True` instructs the renderer to apply standard 2D pan/zoom on the primary source asset.

---

## 3. Renderer Processing Loop (Milestone 7 Architecture)

```python
# Conceptual Renderer Frame Loop
for shot in visual_timeline.all_shots():
    # 1. Load source asset
    source_img = load_image(shot.source_image_path)
    
    # 2. Iterate frames across shot duration
    shot_frames = int(round(shot.duration * visual_timeline.target_resolution.fps))
    for frame_idx in range(shot_frames):
        t = frame_idx / max(1, shot_frames - 1)
        
        # 3. Compute crop
        crop_box = compute_pixel_crop_at_time(
            shot.camera_start, shot.camera_end, t,
            source_width, source_height,
            target_width, target_height,
            easing=shot.easing
        )
        frame_canvas = source_img.crop(crop_box).resize((target_width, target_height))
        
        # 4. Apply active effects
        for eff in shot.effect_instructions:
            if eff.is_active_at(shot.start_time + (t * shot.duration)):
                apply_effect(frame_canvas, eff)
                
        # 5. Overlay subtitles
        for cap in shot.caption_cues:
            if cap.is_active_at(shot.start_time + (t * shot.duration)):
                render_subtitle(frame_canvas, cap.text)
                
        pipe_frame_to_encoder(frame_canvas)
```
