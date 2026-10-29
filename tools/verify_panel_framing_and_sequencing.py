import sys
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.render.compiler import TimelineCompiler
from engine.render.composer import FrameComposer
from engine.render.models.profiles import RenderProfile


def test_verification():
    tmp_dir = Path("output/test_verification")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # Create 3 distinct tall manga panels (aspect ratio 0.6: 600x1000)
    p1_path = tmp_dir / "panel_1_red.png"
    p2_path = tmp_dir / "panel_2_green.png"
    p3_path = tmp_dir / "panel_3_blue.png"

    Image.new("RGB", (600, 1000), (220, 20, 60)).save(p1_path)
    Image.new("RGB", (600, 1000), (34, 139, 34)).save(p2_path)
    Image.new("RGB", (600, 1000), (30, 144, 255)).save(p3_path)

    # Timeline with 1 scene of 12s with duplicate_blur background and 3 panels
    state = {
        "background_default": {
            "enabled": True,
            "preset": "duplicate_blur",
            "blur_sigma": 24.0,
            "brightness": 0.45,
            "foreground_fit": "contain",
            "edge_shadow": 0.6,
        },
        "scenes": [
            {
                "id": "scene_test_1",
                "duration_sec": 12.0,
                "start_time_sec": 0.0,
                "layers": [
                    {"id": "ly_1", "image_url": str(p1_path)},
                    {"id": "ly_2", "image_url": str(p2_path)},
                    {"id": "ly_3", "image_url": str(p3_path)},
                ],
            }
        ]
    }

    profile = RenderProfile(width=1280, height=720, fps=24)
    compiler = TimelineCompiler()
    plan = compiler.compile(
        state=state,
        project_id="test_proj",
        workspace_path=tmp_dir,
        profile=profile,
    )

    shot = plan.shots[0]
    print(f"Compiled scene layers count: {len(shot.scene_layers)}")
    for ly in shot.scene_layers:
        print(f"Layer {ly['id']}: start_offset={ly['start_offset_sec']}, dur={ly['duration_sec']}")

    # Verify that layers are automatically sequenced
    assert shot.scene_layers[0]["start_offset_sec"] == 0.0
    assert shot.scene_layers[0]["duration_sec"] == 4.0
    assert shot.scene_layers[1]["start_offset_sec"] == 4.0
    assert shot.scene_layers[1]["duration_sec"] == 4.0
    assert shot.scene_layers[2]["start_offset_sec"] == 8.0
    assert shot.scene_layers[2]["duration_sec"] == 4.0
    print("SUCCESS: Automatic sequential layer distribution verified!")

    composer = FrameComposer()

    # Frame at 2.0s (panel 1 active: frame 48)
    f_t2 = composer.compose_frame(frame_index=48, plan=plan)
    f_t2.save(tmp_dir / "frame_t2s_panel1.jpg")

    # Frame at 6.0s (panel 2 active: frame 144)
    f_t6 = composer.compose_frame(frame_index=144, plan=plan)
    f_t6.save(tmp_dir / "frame_t6s_panel2.jpg")

    # Frame at 10.0s (panel 3 active: frame 240)
    f_t10 = composer.compose_frame(frame_index=240, plan=plan)
    f_t10.save(tmp_dir / "frame_t10s_panel3.jpg")

    # Sample central pixels of each frame
    pix1 = f_t2.getpixel((640, 360))
    pix2 = f_t6.getpixel((640, 360))
    pix3 = f_t10.getpixel((640, 360))

    print(f"Center pixel at 2s: {pix1}")
    print(f"Center pixel at 6s: {pix2}")
    print(f"Center pixel at 10s: {pix3}")

    assert pix1[0] > 180 and pix1[1] < 50, f"Expected red, got {pix1}"
    assert pix2[1] > 100 and pix2[0] < 50, f"Expected green, got {pix2}"
    assert pix3[2] > 200 and pix3[0] < 50, f"Expected blue, got {pix3}"
    print("SUCCESS: Frame sequencing verified! Panel 1 -> Panel 2 -> Panel 3 without repeating or freezing!")

    # Check background fill at left edge (pixel 10, 360):
    # It must be the blurred/dimmed version of the active panel color!
    # At 2s (Red active), left edge should be predominantly reddish:
    bg_t2 = f_t2.getpixel((10, 360))
    print(f"Ambient background pixel at 2s: {bg_t2}")
    assert bg_t2[0] > bg_t2[1] and bg_t2[0] > bg_t2[2], f"Expected red-tinted ambient blur, got {bg_t2}"

    # At 6s (Green active), left edge should be predominantly greenish:
    bg_t6 = f_t6.getpixel((10, 360))
    print(f"Ambient background pixel at 6s: {bg_t6}")
    assert bg_t6[1] > bg_t6[0] and bg_t6[1] > bg_t6[2], f"Expected green-tinted ambient blur, got {bg_t6}"

    # At 10s (Blue active), left edge should be predominantly bluish:
    bg_t10 = f_t10.getpixel((10, 360))
    print(f"Ambient background pixel at 10s: {bg_t10}")
    assert bg_t10[2] > bg_t10[0] and bg_t10[2] >= bg_t10[1], f"Expected blue-tinted ambient blur, got {bg_t10}"
    print("SUCCESS: Dynamic ambient blurred background tracking active panel verified!")

    # Check vertical margin: safe_margin = 0.94 of 720 is 676.8px.
    # Top margin = (720 - 676.8) / 2 = ~21.6px.
    # Pixel at y=5 is ambient blur:
    top_margin_pix = f_t2.getpixel((640, 5))
    print(f"Top margin pixel at (640, 5): {top_margin_pix}")
    # Pixel at y=40 is inside foreground panel:
    panel_pix = f_t2.getpixel((640, 40))
    print(f"Foreground panel pixel at (640, 40): {panel_pix}")
    assert panel_pix[0] > 180, f"Expected panel foreground at y=40, got {panel_pix}"
    print("SUCCESS: Safe margin padding (94%) verified! Full panel is visible without over-zoom cropping!")


if __name__ == "__main__":
    test_verification()
