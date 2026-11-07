"""How long can ONE H3 clip be on this machine? Generates an image-to-video clip of the given length from an existing first frame and records time and peak VRAM.
Run: .venv\Scripts\python.exe tools\h3_length_probe.py <seconds> [frame.png]   (output/H3_LongTake/)"""
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.original import h3_modes as hm  # noqa: E402
from engine.original.animate import release_ollama  # noqa: E402
from engine.original.clip_eval import evaluate  # noqa: E402

OUT = Path("output/H3_LongTake")
peak = {"mib": 0}


def watch():
    while True:
        try:
            v = int(subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], capture_output=True, text=True).stdout.split()[0])
            peak["mib"] = max(peak["mib"], v)
        except Exception:
            pass
        time.sleep(5)


def main() -> None:
    secs = float(sys.argv[1])
    frame = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("output/H3_Validation/girl.png")
    OUT.mkdir(parents=True, exist_ok=True)
    release_ollama()
    threading.Thread(target=watch, daemon=True).start()
    action = ("She sips from the cup and lowers it to the table. Then she turns her head and looks out of the window at the rain, watching it for a moment. "
              "Then she turns back, smiles softly and lifts the cup again. She stays seated in the same chair the whole time and is the only person in the room.")
    t = time.time()
    path = OUT / f"probe_{int(secs)}s.mp4"
    path.write_bytes(hm.make_clip("i2va", hm.i2va_prompt(action), seed=7, seconds=secs, first=frame, prefix="video/h3_probe", timeout=7200))
    rep = evaluate(path, expect_camera="static", expect_audio=True)
    print(f"{secs}s -> {rep['frames']} frames in {round(time.time() - t)} s, peak VRAM {peak['mib']} MiB; zoom {rep['camera']['zoom_pct']:+.1f}% drift {rep['drift']['max']} flicker {rep['flicker']} cuts {rep['cuts_s']} flags {[f['axis'] + ':' + f['status'][:4] for f in rep['flags']]}", flush=True)


main()
