"""Finalize Episode 1 Master Video with True Visceral Somatic Trauma Panels 12 and 13.
"""
from pathlib import Path
import shutil
import subprocess
import time

def main():
    ep_dir = Path("output/series_1000/episode_0001_perfect_continuity")
    art_dir = Path("C:/Users/user/.gemini/antigravity/brain/2e58828d-731a-431e-8ffa-02767884fcbc")

    visc_p12 = Path("output/series_1000/emotional_tests/panel_012_visceral_agony.png")
    visc_p13 = Path("E:/VIJAY SEKAR/ComfyUI/output/visceral_p013_trauma_00001_.png")

    assert visc_p12.exists(), f"Missing {visc_p12}"
    assert visc_p13.exists(), f"Missing {visc_p13}"

    # 1. Update Episode Directory
    shutil.copy2(visc_p12, ep_dir / "panel_012.png")
    shutil.copy2(visc_p12, ep_dir / "panel_012_refined.png")
    print(f"✓ Copied visceral panel 12 ({visc_p12.stat().st_size} bytes)")

    shutil.copy2(visc_p13, ep_dir / "panel_013.png")
    shutil.copy2(visc_p13, ep_dir / "panel_013_refined.png")
    print(f"✓ Copied visceral panel 13 ({visc_p13.stat().st_size} bytes)")

    # 2. Update Artifact Directory
    shutil.copy2(visc_p12, art_dir / "continuity_panel_012_visceral.png")
    shutil.copy2(visc_p13, art_dir / "continuity_panel_013_visceral.png")
    print("✓ Copied visceral panels 12 & 13 to artifact directory.")

    # 3. Clean old shot videos
    for idx in [12, 13]:
        s_file = ep_dir / f"shot_{idx:03d}.mp4"
        if s_file.exists():
            s_file.unlink()
            print(f"Removed old shot file: {s_file.name}")

    # 4. Re-encode Shot 12 and Shot 13
    from produce_perfect_continuity_manhua import SHOT_SEQUENCE, SceneContinuityDirector
    director = SceneContinuityDirector()

    for idx in [12, 13]:
        shot = SHOT_SEQUENCE[idx - 1]
        panel_path = ep_dir / f"panel_{idx:03d}.png"
        audio_path = ep_dir / f"audio_{idx:03d}.mp3"
        shot_video_path = ep_dir / f"shot_{idx:03d}.mp4"

        audio_dur = director._get_audio_duration(audio_path)
        exact_duration = round(audio_dur + shot.intentional_pause_after_seconds, 2)
        total_frames = int(exact_duration * 30)
        vf_filter = shot.camera_movement.replace("{frames}", str(total_frames))

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(panel_path),
            "-i", str(audio_path),
            "-vf", vf_filter,
            "-c:v", "h264_nvenc",
            "-c:a", "aac", "-b:a", "192k",
            "-t", str(exact_duration),
            "-pix_fmt", "yuv420p",
            "-shortest",
            str(shot_video_path),
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"✓ Re-encoded Shot {idx:02d}: {exact_duration:.2f}s ({panel_path.name})")

    # 5. Re-concatenate Master Episode Video
    master_video = ep_dir / "episode_0001_perfect_continuity_master.mp4"
    concat_manifest = ep_dir / "shots_manifest.txt"
    shot_video_paths = [ep_dir / f"shot_{i:03d}.mp4" for i in range(1, 17)]
    with open(concat_manifest, "w", encoding="utf-8") as f:
        for p in shot_video_paths:
            f.write(f"file '{p.resolve().as_posix()}'\n")

    cmd_concat = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_manifest.resolve().as_posix(),
        "-c", "copy",
        str(master_video),
    ]
    subprocess.run(cmd_concat, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"\n🎉 MASTER EPISODE RE-ENCODED SUCCESSFULLY WITH TRUE VISCERAL TRAUMA: {master_video.name}")
    print(f"Master Video Size: {master_video.stat().st_size / (1024*1024):.2f} MB")

if __name__ == "__main__":
    main()
