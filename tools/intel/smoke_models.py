"""Phase 0 capability smoke test: one picture per art model, one clip per video model, timed, VRAM sampled, probed with ffprobe.

Run (ComfyUI up on :8188, PANELFLOW_COMFYUI_WORKFLOW_DIR set):
    .venv\\Scripts\\python.exe -u tools/intel/smoke_models.py [stage ...]    stages: klein h3img fasth3 wan (default: all)
Results append to output/intel/capability_smoke.json. One model family on the GPU at a time (stages run in order).
"""
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "output" / "intel"
OUT.mkdir(parents=True, exist_ok=True)
RESULTS = OUT / "capability_smoke.json"

# Original, generic test subject: no story, no franchise character.
PIC = ("Flat 2D cartoon illustration, clean bold outlines, a small orange fox in a red scarf standing on a grassy hill at sunset, "
       "front three-quarter view, one paw raised to wave, full body in frame, simple warm colours.")
MOVE = ("The fox waves its raised paw twice and its scarf blows gently to the right. The camera is a Static Shot, fixed on a tripod. "
        "Everything else stays exactly as drawn in the same flat cartoon style.")
W, H = 768, 1344  # 9:16 picture size the reels pipeline uses
CW, CH = 480, 832  # clip size


class Vram:
    """Samples nvidia-smi once a second; .peak is the highest used MiB seen."""

    def __init__(self):
        self.peak, self._run = 0, True
        self._t = threading.Thread(target=self._loop, daemon=True)

    def _loop(self):
        while self._run:
            try:
                v = int(subprocess.check_output(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], text=True).split()[0])
                self.peak = max(self.peak, v)
            except Exception:
                pass
            time.sleep(1)

    def __enter__(self):
        self._t.start()
        return self

    def __exit__(self, *a):
        self._run = False


def probe(path: Path) -> dict:
    out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,r_frame_rate,nb_frames:format=duration",
                                   "-of", "json", str(path)], text=True)
    j = json.loads(out)
    v = next((s for s in j["streams"] if s["codec_type"] == "video"), {})
    return {"width": v.get("width"), "height": v.get("height"), "fps": v.get("r_frame_rate"), "frames": v.get("nb_frames"),
            "duration_s": float(j["format"]["duration"]), "has_audio": any(s["codec_type"] == "audio" for s in j["streams"])}


def save(name: str, rec: dict):
    data = json.loads(RESULTS.read_text()) if RESULTS.exists() else {}
    data[name] = rec
    RESULTS.write_text(json.dumps(data, indent=2))
    print(name, json.dumps(rec), flush=True)


def main(stages):
    from engine.comfyui import ComfyUIClient, ComfyWorkflowRegistry
    from engine.comfyui.art import ArtEngine, _patch_workflow
    from engine.comfyui.service import _history_videos
    from engine.original.animate import release_ollama
    release_ollama()
    client = ComfyUIClient()
    reg = ComfyWorkflowRegistry(client)
    engine = ArtEngine(client, reg)
    pic = OUT / "smoke_klein.png"

    def still(name, wf):
        with Vram() as vr:
            t0 = time.monotonic()
            img = engine.generate(PIC, width=W, height=H, seed=7, prefix=f"intel/{name}", workflow_id=wf)
            dt = time.monotonic() - t0
        p = OUT / f"smoke_{name}.png"
        p.write_bytes(img.png)
        save(name, {"workflow": wf, "size": [img.width, img.height], "seconds": round(dt, 1), "peak_vram_mib": vr.peak, "file": str(p)})

    def clip(name, wf, **extra):
        pre = reg.preflight(wf)
        assert pre.get("ready"), pre
        workflow, _ = reg.load(wf)
        slots = reg.metadata(wf)["patch_slots"]
        with Vram() as vr:
            t0 = time.monotonic()
            patched = _patch_workflow(workflow, slots, extra.pop("prompt"), negative_prompt=extra.pop("neg", ""), width=CW, height=CH, seed=7,
                                      prefix=f"intel/{name}", reference_image=client.upload_image(pic), **extra)
            raw, _, _ = engine.run(patched, timeout=1500.0, collect=_history_videos)
            dt = time.monotonic() - t0
        p = OUT / f"smoke_{name}.mp4"
        p.write_bytes(raw)
        save(name, {"workflow": wf, "seconds": round(dt, 1), "peak_vram_mib": vr.peak, "file": str(p), **probe(p)})

    if "klein" in stages:
        still("klein", "flux2_klein_4b")
    if "h3img" in stages:
        still("h3img", "minimax_h3_image_edit")
    if "fasth3" in stages:
        prompt = ("For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.\n"
                  f"integrated_multimodal_description: [Shot 1] {MOVE}\n\noverall_soundscape: light wind.\n\nnon_diegetic_music: none.")
        clip("fasth3_5s", "fastvideo_h3_i2v", prompt=prompt, duration=5.0)
    if "wan" in stages:
        clip("wan21", "wan21_14b_i2v", prompt=f"{PIC} {MOVE}", neg="blurry, distorted, extra limbs, text")


if __name__ == "__main__":
    main(set(sys.argv[1:]) or {"klein", "h3img", "fasth3", "wan"})
