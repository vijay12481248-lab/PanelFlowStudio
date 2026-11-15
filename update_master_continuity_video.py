"""Update Episode 1 Master Video with All Refined Micro-Continuity Panels.

Re-encodes all updated shots:
- Panel 004 (True MCU, amethyst eyes & brow scar, hands down)
- Panel 010 (Clash with Commander Meng brandishing broadsword)
- Panel 011 (Broadsword shattering into shards on basalt ground)
- Panel 012 (Void strike into Commander Meng's chestplate, no sword)
- Panel 013 (Commander Meng embedded in wall crater, cracked chestplate, NO sword, silver dragon pauldron)
- Panel 016 (Sovereign ascendance inside purple beam of light)
"""
from pathlib import Path
import shutil
import subprocess
import time

def main():
    ep_dir = Path("output/series_1000/episode_0001_perfect_continuity")

    # 1. Promote refined panels to official panel files
    p12_ref = ep_dir / "panel_012_refined.png"
    p12_official = ep_dir / "panel_012.png"
    if p12_ref.exists():
        shutil.copy2(p12_ref, p12_official)
        print("✓ Promoted panel_012_refined.png -> panel_012.png")

    p13_ref = ep_dir / "panel_013_refined.png"
    p13_official = ep_dir / "panel_013.png"
    if p13_ref.exists():
        shutil.copy2(p13_ref, p13_official)
        print("✓ Promoted panel_013_refined.png -> panel_013.png")

    # 2. Re-encode the video shots
    from produce_perfect_continuity_manhua import SHOT_SEQUENCE, SceneContinuityDirector
    director = SceneContinuityDirector()

    # Clean old shot files for updated panels
    for idx in [4, 10, 12, 13, 16]:
        s_file = ep_dir / f"shot_{idx:03d}.mp4"
        if s_file.exists():
            s_file.unlink()
            print(f"Removed old shot file: {s_file.name}")

    shot_video_paths = []
    for idx, shot in enumerate(SHOT_SEQUENCE, 1):
        panel_path = ep_dir / f"panel_{idx:03d}.png"
        audio_path = ep_dir / f"audio_{idx:03d}.mp3"
        shot_video_path = ep_dir / f"shot_{idx:03d}.mp4"

        audio_dur = director._get_audio_duration(audio_path)
        exact_duration = round(audio_dur + shot.intentional_pause_after_seconds, 2)
        total_frames = int(exact_duration * 30)
        vf_filter = shot.camera_movement.replace("{frames}", str(total_frames))

        if not shot_video_path.exists():
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
        shot_video_paths.append(shot_video_path)

    # 3. Concatenate Master Episode Video
    master_video = ep_dir / "episode_0001_perfect_continuity_master.mp4"
    concat_manifest = ep_dir / "shots_manifest.txt"
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
    print(f"\n🎉 MASTER EPISODE RE-ENCODED SUCCESSFULLY: {master_video.name}")
    print(f"Master Video Size: {master_video.stat().st_size / (1024*1024):.2f} MB")

if __name__ == "__main__":
    main()
