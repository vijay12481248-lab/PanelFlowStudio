# Camera Model & Coordinate Space Specification

## 1. Normalized Coordinate Space

The PanelFlow camera system operates in normalized unit coordinates $[0.0, 1.0] \times [0.0, 1.0]$:
- Top-Left origin: `(0.0, 0.0)`
- Center: `(0.5, 0.5)`
- Bottom-Right: `(1.0, 1.0)`

A `CameraState` is defined as:
```python
class CameraState(BaseModel):
    center_x: float  # [0.0, 1.0]
    center_y: float  # [0.0, 1.0]
    zoom: float      # [1.0, 4.0] (sub-1.0 prohibited)
    rotation: float  # [-45.0, 45.0] degrees
    crop: Optional[NormalizedRect]
```

---

## 2. Bounds Clamping & Visible Frustum Mathematics

To guarantee that camera motion never reveals empty borders or content outside the illustrated panel, the visible window dimensions $(W_{vis}, H_{vis})$ in source coordinate space are computed as:

Given:
- Source Aspect Ratio $A_{src} = W_{src} / H_{src}$
- Target Aspect Ratio $A_{tgt} = W_{tgt} / H_{tgt}$ (e.g. 16:9 = 1.777)
- Zoom factor $z \ge 1.0$

```
if A_src >= A_tgt:
    H_vis = 1.0 / z
    W_vis = (H_vis * A_tgt) / A_src
else:
    W_vis = 1.0 / z
    H_vis = (W_vis / A_tgt) * A_src

W_vis = min(1.0, W_vis)
H_vis = min(1.0, H_vis)
```

The camera center $(c_x, c_y)$ is then bounded:
$$c_x \in \left[\frac{W_{vis}}{2},\; 1.0 - \frac{W_{vis}}{2}\right]$$
$$c_y \in \left[\frac{H_{vis}}{2},\; 1.0 - \frac{H_{vis}}{2}\right]$$

If $W_{vis} \ge 1.0$ or $H_{vis} \ge 1.0$, the coordinate is centered at `0.5`.

---

## 3. Easing Functions

Motion interpolation evaluates normalized time $t \in [0.0, 1.0]$:

1. **LINEAR**:
   $$f(t) = t$$

2. **EASE_IN** (Quadratic):
   $$f(t) = t^2$$

3. **EASE_OUT** (Quadratic):
   $$f(t) = 1 - (1 - t)^2$$

4. **EASE_IN_OUT**:
   $$f(t) = \begin{cases} 2t^2 & t < 0.5 \\ 1 - \frac{(-2t + 2)^2}{2} & t \ge 0.5 \end{cases}$$

5. **SMOOTHSTEP** (Cubic Hermite):
   $$f(t) = 3t^2 - 2t^3$$

---

## 4. Pixel Crop Calculation

Downstream preview generators and renderers evaluate the exact source image crop $(left, top, right, bottom)$ at any time $t$ via `compute_pixel_crop_at_time()`:

```python
state_t = interpolate_camera(start, end, t, easing)
vis_rect = state_t.visible_rect(target_aspect, source_aspect)
pixel_box = vis_rect.to_pixel_box(source_width, source_height)
```
This guarantees sub-pixel accuracy and eliminates border jitter during pans and zooms.
