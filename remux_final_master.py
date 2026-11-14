"""Re-encode Shot 12 and re-mux master episode video."""
from pathlib import Path
import subprocess
from produce_perfect_continuity_manhua import SHOT_SEQUENCE, SceneContinuityDirector

def main():
    ep_dir = Path("output/series_1000/episode_0001_perfect_continuity")
    director = SceneContinuityDirector()

    shot12 = SHOT_SEQUENCE[11]
    panel_path = ep_dir / "panel_012.png"
    audio_path = ep_dir / "audio_012.mp3"
    shot_video_path = ep_dir / "shot_012.mp4"

    audio_dur = director._get_audio_duration(audio_path)
    exact_duration = round(audio_dur + shot12.intentional_pause_after_seconds, 2)
    total_frames = int(exact_duration * 30)
    vf_filter = shot12.camera_movement.replace("{frames}", str(total_frames))

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
    print(f"✓ Re-encoded Shot 12: {exact_duration:.2f}s")

    # Concatenate master
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
    print(f"✓ Final Master Re-muxed: {master_video.name} ({master_video.stat().st_size / (1024*1024):.2f} MB)")

if __name__ == "__main__":
    main()
