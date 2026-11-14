"""Test stickman animation with MiniMax Fast H3 Turbo and mux with Kokoro TTS audio."""
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

def main():
    print("Releasing Ollama LLM from VRAM...")
    release_ollama()
    time.sleep(1.0)

    workflow_id = "fastvideo_h3_i2v"
    client = ComfyUIClient()
    registry = ComfyWorkflowRegistry(client)

    print(f"Preflighting {workflow_id}...")
    pre = registry.preflight(workflow_id)
    if not pre.get("ready"):
        print("Preflight failed:", pre)
        return

    workflow, sha = registry.load(workflow_id)
    slots = registry.metadata(workflow_id)["patch_slots"]
    engine = ArtEngine(client, registry)

    picture_path = Path("output/stickman_test/stickman_neon.png")
    if not picture_path.exists():
        print(f"Picture {picture_path} does not exist!")
        return

    print("Uploading reference image to ComfyUI...")
    ref_name = client.upload_image(picture_path)
    print("Uploaded image name:", ref_name)

    scene = (
        "A neon stick figure warrior stands in the dark void holding glowing cyan energy daggers. "
        "The figure fluidly spins the glowing daggers in dynamic circular motions, casting vibrant electric blue light ribbons and sparkling energy bursts into the dark space. "
        "Glowing cyan particles drift and swirl around the figure."
    )
    camera = "a slow dramatic push-in toward the glowing neon stickman, keeping the figure centered"
    prompt = (
        "For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.\n"
        f"integrated_multimodal_description: [Shot 1] {scene} The camera does {camera}. Only the action of this moment moves; everything else stays exactly as drawn.\n\n"
        "overall_soundscape: subtle low hum of electricity and soft crackle of energy sparks.\n\nnon_diegetic_music: none."
    )

    duration = 4.5
    seed = 42
    prefix = "video/stickman_test"

    print("Patching workflow...")
    patched = _patch_workflow(
        workflow,
        slots,
        prompt,
        negative_prompt="",
        width=832,
        height=480,
        seed=seed,
        prefix=prefix,
        reference_image=ref_name,
        duration=duration,
    )

    print("Running MiniMax Fast H3 Turbo in ComfyUI (estimated ~60s)...")
    t0 = time.monotonic()
    raw, prompt_id, _ = engine.run(patched, timeout=600.0, collect=_history_videos)
    elapsed = time.monotonic() - t0
    print(f"Video generated in {elapsed:.1f}s! Size: {len(raw)} bytes.")

    clip_path = Path("output/stickman_test/clip.mp4")
    clip_path.write_bytes(raw)
    print(f"Saved raw clip to {clip_path}")

    # Now mux with Kokoro audio if available
    audio_path = Path("output/stickman_test/audio.wav")
    final_path = Path("output/stickman_test/final_stickman_video.mp4")
    if audio_path.exists():
        print("Muxing video with Kokoro audio using FFmpeg...")
        cmd = [
            "ffmpeg", "-y",
            "-i", str(clip_path),
            "-i", str(audio_path),
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            str(final_path)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            print(f"SUCCESS! Final video created at: {final_path} ({final_path.stat().st_size} bytes)")
        else:
            print("FFmpeg muxing error:", res.stderr)
    else:
        print("Audio file not found, raw clip remains.")

if __name__ == "__main__":
    main()
