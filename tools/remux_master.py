import subprocess
from pathlib import Path

project_dir = Path("output/shorts/wheel_short")
clips_dir = project_dir / "clips"
audio_dir = project_dir / "audio"
muxed_dir = project_dir / "muxed"

muxed_list = []
for i in range(1, 8):
    clip = clips_dir / f"clip_{i}.mp4"
    audio = audio_dir / f"scene_{i}.wav"
    out = muxed_dir / f"scene_{i}_muxed.mp4"
    print(f"Muxing Scene {i} with Kokoro narration audio...")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(clip),
        "-i", str(audio),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-t", "5.0",
        str(out)
    ]
    subprocess.run(cmd, check=True)
    muxed_list.append(out)

concat_txt = project_dir / "concat.txt"
concat_lines = [f"file '{p.resolve().as_posix()}'" for p in muxed_list]
concat_txt.write_text("\n".join(concat_lines), encoding="utf-8")

master_path = project_dir / "the_dumbest_man_who_changed_history_master.mp4"
print("Concatenating into master video...")
cmd_concat = [
    "ffmpeg", "-y",
    "-f", "concat", "-safe", "0",
    "-i", str(concat_txt),
    "-c", "copy",
    str(master_path)
]
subprocess.run(cmd_concat, check=True)
print(f"SUCCESS! Master Short updated with narration: {master_path} ({master_path.stat().st_size} bytes)")
