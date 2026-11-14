"""Production Script for Short #1: The Dumbest Man Who Changed History.
Phase 3: Animates all 7 scenes using MiniMax Fast H3 Turbo (ComfyUI) and stitches the final 35-second vertical 9:16 Short with synced narration.
"""
import os
import sys
import subprocess
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.comfyui import ComfyUIClient, ComfyWorkflowRegistry
from engine.comfyui.art import ArtEngine, _patch_workflow
from engine.comfyui.service import _history_videos
from engine.original.animate import release_ollama

PROJECT_DIR = Path("output/shorts/wheel_short")
PANELS_DIR = PROJECT_DIR / "panels"
AUDIO_DIR = PROJECT_DIR / "audio"
CLIPS_DIR = PROJECT_DIR / "clips"
MUXED_DIR = PROJECT_DIR / "muxed"
CLIPS_DIR.mkdir(exist_ok=True)
MUXED_DIR.mkdir(exist_ok=True)

CLIPS_CONFIG = [
    (1, "The caveman proudly raises the wooden wheel above his head and smiles. The tribe members behind him laugh, point at him, and shake their heads. One caveman bends forward laughing. Subtle character movements, natural hand gestures, slight camera push-in. Preserve original character designs, clothing, proportions, background and hand-drawn art style."),
    (2, "The caveman carefully pushes the wooden wheel underneath the heavy stone. He gives the stone a small push, and it begins rolling forward. His eyes widen with excitement. The watching tribe members lean forward in disbelief. Gentle camera movement, maintain consistent character identity and original illustration texture."),
    (3, "The wooden cart begins moving slowly. The inventor raises both arms and celebrates. The two tribe members jump excitedly and clap their hands. The cart moves a short distance from left to right. Keep movement controlled and preserve the illustration style."),
    (4, "The cart suddenly accelerates downhill. The inventor desperately grabs the wooden sides, his hair flapping as he screams. Tribe members run behind him, waving their arms. Dust rises beneath the wheels. Dynamic but readable movement, slight tracking camera, no morphing or unnecessary visual effects."),
    (5, "The cart bumps into a wooden basket and spins sideways. Clay pots tumble and tribe members jump out of the way. The inventor lands in a pile of straw. Exaggerated cartoon physical comedy, controlled motion, preserve character designs and illustration texture."),
    (6, "The elderly man picks up the wooden wheel, examines it, then gives an approving nod. The inventor slowly looks up, surprised. Other tribe members gather closer and begin clapping. Slow camera push-in, subtle expressive movements."),
    (7, "The tribe happily rolls away in their carts. The inventor runs behind them, shouting and waving his arms, trying to catch up. The elderly man turns around and laughs. End with the inventor looking directly at the camera with a disappointed expression."),
]

def main():
    print("Releasing Ollama LLM to guarantee full VRAM for MiniMax H3...")
    release_ollama()
    time.sleep(1.0)

    workflow_id = "fastvideo_h3_i2v"
    client = ComfyUIClient()
    registry = ComfyWorkflowRegistry(client)

    pre = registry.preflight(workflow_id)
    if not pre.get("ready"):
        print("Preflight failed for H3:", pre)
        return

    workflow, sha = registry.load(workflow_id)
    slots = registry.metadata(workflow_id)["patch_slots"]
    engine = ArtEngine(client, registry)

    muxed_list = []

    for num, motion_desc in CLIPS_CONFIG:
        panel_path = PANELS_DIR / f"scene_{num}.png"
        audio_path = AUDIO_DIR / f"scene_{num}.wav"
        clip_path = CLIPS_DIR / f"clip_{num}.mp4"
        muxed_path = MUXED_DIR / f"scene_{num}_muxed.mp4"

        if not clip_path.exists() or clip_path.stat().st_size == 0:
            print(f"\n==========================================")
            print(f"Animating Scene {num}/7 with MiniMax Fast H3...")
            print(f"==========================================")
            ref_name = client.upload_image(panel_path)

            prompt = (
                "For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.\n"
                f"integrated_multimodal_description: [Shot 1] {motion_desc} Only the action of this moment moves; everything else stays exactly as drawn in the naive folk-art storybook illustration.\n\n"
                "overall_soundscape: prehistoric savanna ambient sounds, no dialogue.\n\nnon_diegetic_music: none."
            )

            patched = _patch_workflow(
                workflow,
                slots,
                prompt,
                negative_prompt="",
                width=480,
                height=832,
                seed=200 + num,
                prefix=f"shorts/wheel_clip_{num}",
                reference_image=ref_name,
                duration=5.0,
            )

            t0 = time.monotonic()
            raw, prompt_id, _ = engine.run(patched, timeout=600.0, collect=_history_videos)
            elapsed = time.monotonic() - t0
            clip_path.write_bytes(raw)
            print(f"  -> Generated clip_{num}.mp4 ({len(raw)} bytes) in {elapsed:.1f}s")
        else:
            print(f"Scene {num} clip already exists, reusing: {clip_path.name}")

        # Mux with narration audio (clip is ~6.5s from H3, audio is ~3.5-4.9s; trim cleanly to 5.0s)
        if audio_path.exists() and (not muxed_path.exists() or muxed_path.stat().st_size == 0):
            print(f"Muxing Scene {num} video + audio...")
            cmd = [
                "ffmpeg", "-y",
                "-i", str(clip_path),
                "-i", str(audio_path),
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k",
                "-t", "5.0",
                str(muxed_path)
            ]
            subprocess.run(cmd, check=True)
            print(f"  -> Created {muxed_path.name}")

        muxed_list.append(muxed_path)

    # Stitch all 7 into master video
    concat_txt = PROJECT_DIR / "concat.txt"
    concat_lines = [f"file '{p.resolve().as_posix()}'" for p in muxed_list]
    concat_txt.write_text("\n".join(concat_lines), encoding="utf-8")

    master_path = PROJECT_DIR / "the_dumbest_man_who_changed_history_master.mp4"
    print(f"\nStitching all 7 scenes into Master Short: {master_path.name}...")
    cmd_concat = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_txt),
        "-c", "copy",
        str(master_path)
    ]
    subprocess.run(cmd_concat, check=True)
    print(f"\n🎉 MASTER SHORT READY! File: {master_path} ({master_path.stat().st_size} bytes)")

if __name__ == "__main__":
    main()
