"""Overnight batch runner for explainer videos: spec -> story -> pictures -> REVIEW SHEETS -> (human/agent approval) -> voiced video -> verification.

Why a runner: a video is ~40 pictures (about 15-25 min of GPU) plus a review of every picture against its narration line before it is voiced.
The GPU must never sit idle while somebody reviews, so the loop draws the next video's pictures while the previous one is being reviewed.

Files (all under output/Original_Stories/):
    _batch/state.json   per-slug stage and timings        _batch/log.txt   one line per event        _batch/STOP   create to stop after the current job
    <slug>/review/sheet_N.jpg   8 pictures per sheet, each with its beat id, its narration and what the art reviewer missed
    <slug>/approved.flag        (written after the review) -> the loop voices and renders the video, then verifies it
    <slug>/redo.flag            (written after editing the spec) -> the loop rebuilds story.json, redraws only changed pictures, rebuilds the sheets
Stages in state.json: queued -> drawing -> review -> (approved) -> rendering -> done | failed | error.

Run:  python -m engine.original.batch run [specs_dir]     (default stories/explainers)
"""
from __future__ import annotations

import asyncio
import json
import re
import subprocess
import sys
import textwrap
import time
import traceback
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STORIES = ROOT / "output" / "Original_Stories"
BATCH = STORIES / "_batch"
FONT = Path("C:/Windows/Fonts/arial.ttf")
MIN_SECONDS = 180.0


def log(msg: str) -> None:
    BATCH.mkdir(parents=True, exist_ok=True)
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(BATCH / "log.txt", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_state() -> dict:
    f = BATCH / "state.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def save_state(st: dict) -> None:
    BATCH.mkdir(parents=True, exist_ok=True)
    tmp = BATCH / "state.json.tmp"
    tmp.write_text(json.dumps(st, indent=1), encoding="utf-8")
    tmp.replace(BATCH / "state.json")


def set_stage(slug: str, stage: str, **extra) -> None:
    st = load_state()
    st.setdefault(slug, {}).update({"stage": stage, "at": time.strftime("%Y-%m-%d %H:%M:%S"), **extra})
    save_state(st)
    log(f"{slug}: {stage} {extra if extra else ''}")


def engine_alive() -> bool:
    try:
        urllib.request.urlopen("http://127.0.0.1:8765/health", timeout=4)
        return True
    except urllib.error.HTTPError:  # the engine answers (e.g. 401 without a token): it is up
        return True
    except Exception:
        return False


def ensure_engine() -> None:
    """The engine has no supervisor: if it is down, start it the way the owner does (and with the workflow dir the art step needs)."""
    if engine_alive():
        return
    log("engine is down: starting it")
    env = {**__import__("os").environ, "PANELFLOW_COMFYUI_WORKFLOW_DIR": r"E:\VIJAY SEKAR\ComfyUI\workflow"}
    subprocess.run(["powershell", "-NoProfile", "-File", str(ROOT / "launch_panelflow.ps1"), "-EngineOnly"], cwd=ROOT, env=env, timeout=300,
                   capture_output=True)
    for _ in range(30):
        if engine_alive():
            return
        time.sleep(5)
    raise RuntimeError("engine did not come up")


def review_sheets(ws: Path, only: list[str] | None = None, name: str = "sheet") -> list[Path]:
    """8 pictures per sheet with beat id + narration + cast + what the art reviewer reported missing: enough to judge picture vs script at a glance.
    The vision reviewer's "missed" list is noisy about plain character attributes ("dark brown eyes" behind round glasses), so a miss that is
    just a fragment of a character's look string is not shown; `only` makes a small sheet of just those beat ids (to re-check a redraw)."""
    from PIL import Image, ImageDraw, ImageFont

    story = json.loads((ws / "story.json").read_text(encoding="utf-8"))
    art = {a["panel_id"]: a for a in json.loads((ws / "art.json").read_text(encoding="utf-8"))} if (ws / "art.json").exists() else {}
    out_dir = ws / "review"
    out_dir.mkdir(exist_ok=True)
    for old in out_dir.glob(f"{name}_*.jpg"):
        old.unlink()
    looks = " ; ".join(c["look"].lower() for c in story["bible"]["characters"])
    f_id = ImageFont.truetype(str(FONT), 17) if FONT.exists() else ImageFont.load_default()
    f_tx = ImageFont.truetype(str(FONT), 14) if FONT.exists() else ImageFont.load_default()
    W, H, TXT = 480, 270, 78
    panels = [p for p in story["panels"] if not only or p["id"] in only]
    paths = []
    for n in range(0, len(panels), 8):
        grp = panels[n:n + 8]
        sheet = Image.new("RGB", (W * 4, (H + TXT) * 2), "#101418")
        d = ImageDraw.Draw(sheet)
        for i, p in enumerate(grp):
            x, y = (i % 4) * W, (i // 4) * (H + TXT)
            img = ws / "panels" / f"{p['id']}.png"
            if img.exists():
                sheet.paste(Image.open(img).convert("RGB").resize((W, H)), (x, y))
            else:
                d.text((x + 10, y + 120), "MISSING PICTURE", fill="red", font=f_id)
            d.rectangle((x, y, x + 150, y + 22), fill="black")
            d.text((x + 4, y + 2), f"{p['id']}  {','.join(p['character_ids']) or '-'}", fill="#ffd400", font=f_id)
            a = art.get(p["id"], {})
            miss = [m for m in a.get("missing", []) if m and m.lower() not in looks]
            if miss:
                d.rectangle((x, y + H - 20, x + W, y + H), fill="#7a1010")
                d.text((x + 4, y + H - 19), ("reviewer missed: " + "; ".join(miss))[:70], fill="white", font=f_tx)
            for k, line in enumerate(textwrap.wrap(p["caption"], 62)[:3]):
                d.text((x + 4, y + H + 3 + k * 17), line, fill="white", font=f_tx)
        path = out_dir / f"{name}_{n // 8 + 1}.jpg"
        sheet.save(path, quality=88)
        paths.append(path)
    return paths


def _ff(args: list[str]) -> str:
    r = subprocess.run(args, capture_output=True, text=True)
    return (r.stdout or "") + (r.stderr or "")


def verify_video(ws: Path, story_text: str, est_seconds: float) -> dict:
    """Measured checks on the finished mp4: size, length floor, loudness, frozen/black stretches and that the narration says what the script says."""
    mp4 = ws / "story_1080p.mp4"
    res: dict = {"ok": True, "problems": []}
    probe = _ff(["ffprobe", "-v", "error", "-show_entries", "stream=width,height:format=duration", "-of", "json", str(mp4)])
    j = json.loads(probe)
    dur = float(j["format"]["duration"])
    w, h = j["streams"][0]["width"], j["streams"][0]["height"]
    res.update(duration=round(dur, 1), size=f"{w}x{h}")
    if (w, h) != (1920, 1080):
        res["problems"].append(f"size {w}x{h}")
    if dur < MIN_SECONDS:
        res["problems"].append(f"duration {dur:.0f}s is under {MIN_SECONDS:.0f}s")
    if abs(dur - est_seconds) > 0.25 * est_seconds:
        res["problems"].append(f"duration {dur:.0f}s is far from the estimate {est_seconds:.0f}s")
    out = _ff(["ffmpeg", "-hide_banner", "-nostats", "-i", str(mp4), "-af", "ebur128", "-f", "null", "-"])
    m = re.findall(r"I:\s+(-?\d+\.\d) LUFS", out)
    lufs = float(m[-1]) if m else None
    res["lufs"] = lufs
    if lufs is None or not -19.5 <= lufs <= -13.5:
        res["problems"].append(f"loudness {lufs}")
    black = _ff(["ffmpeg", "-hide_banner", "-nostats", "-i", str(mp4), "-vf", "blackdetect=d=1:pix_th=0.05", "-an", "-f", "null", "-"])
    if "black_start" in black:
        res["problems"].append("black frames for 1 s or more")
    sil = _ff(["ffmpeg", "-hide_banner", "-nostats", "-i", str(mp4), "-af", "silencedetect=n=-45dB:d=3", "-f", "null", "-"])
    res["silences_3s"] = sil.count("silence_start")
    if res["silences_3s"]:
        res["problems"].append(f"{res['silences_3s']} silent stretch(es) of 3 s or more")
    try:  # does the narration say the script? (CPU int8 whisper small, no VAD: VAD drops synthetic speech)
        import wave

        import numpy as np
        from faster_whisper import WhisperModel

        wav = ws / "_verify.wav"
        _ff(["ffmpeg", "-y", "-v", "error", "-i", str(mp4), "-ac", "1", "-ar", "16000", str(wav)])
        with wave.open(str(wav)) as wf:
            audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        wav.unlink(missing_ok=True)
        segs, _ = WhisperModel("small", device="cpu", compute_type="int8", local_files_only=True).transcribe(audio, language="en", vad_filter=False, beam_size=1)
        heard = " ".join(s.text for s in segs)
        norm = lambda t: re.findall(r"[a-z0-9']+", t.lower().replace("-", " "))  # noqa: E731
        r, hw = norm(story_text), norm(heard)
        d = list(range(len(hw) + 1))
        for i, rw in enumerate(r, 1):
            prev, d[0] = d[:], i
            for k, x in enumerate(hw, 1):
                d[k] = min(prev[k] + 1, d[k - 1] + 1, prev[k - 1] + (rw != x))
        res["wer_pct"] = round(100 * d[-1] / max(1, len(r)), 1)
        if res["wer_pct"] > 6:
            res["problems"].append(f"narration word errors {res['wer_pct']}%")
    except Exception as e:  # verification must not crash the run; the gap is reported
        res["wer_pct"] = None
        res["problems"].append(f"speech check not run: {type(e).__name__}")
    res["ok"] = not [p for p in res["problems"] if not p.startswith("speech check not run")]
    return res


def _build(spec: Path) -> tuple:
    from engine.original import explainer as ex

    story, ws = ex.write_story(spec, STORIES)
    return story, ws, ex.estimate_seconds(story), ex.lint(story)


async def _art(slug: str) -> dict:
    from engine.mcp.tools.original_story_tools import panelflow_original_generate_art

    return await panelflow_original_generate_art(slug, check=True, refine=False)


async def _render(slug: str) -> dict:
    from engine.mcp.tools.original_story_tools import panelflow_original_render_video

    return await panelflow_original_render_video(slug, burn_captions=True)


def do_art(spec: Path, st: dict) -> None:
    from engine.original import explainer as ex

    slug = ex.parse(spec.read_text(encoding="utf-8"))["slug"]
    try:
        story, ws, est, warns = _build(spec)
    except ValueError as e:
        set_stage(slug, "error", error=f"spec invalid: {e}")
        return
    set_stage(slug, "drawing", beats=len(story.panels), est_seconds=round(est), warnings=warns)
    t0 = time.time()
    try:
        ensure_engine()
        res = asyncio.run(_art(slug))
        sheets = review_sheets(ws)
    except Exception as e:  # one bad video must not stall the queue; `redo.flag` retries it
        set_stage(slug, "error", error=f"{type(e).__name__}: {e}"[:400])
        return
    set_stage(slug, "review", art_seconds=round(time.time() - t0), generated=res.get("generated"), reused=res.get("reused"),
              below_threshold=res.get("below_threshold", []), sheets=len(sheets))


def do_render(spec: Path) -> None:
    from engine.original import explainer as ex

    text = spec.read_text(encoding="utf-8")
    slug = ex.parse(text)["slug"]
    ws = STORIES / slug
    story = ex.build_story(text)
    set_stage(slug, "rendering")
    t0 = time.time()
    try:
        ensure_engine()
        res = asyncio.run(_render(slug))
        if res.get("missing_panels"):
            set_stage(slug, "failed", error=f"missing panels {res['missing_panels']}")
            return
        ver = verify_video(ws, " ".join(p.caption for p in story.panels), ex.estimate_seconds(story))
    except Exception as e:
        set_stage(slug, "error", error=f"{type(e).__name__}: {e}"[:400])
        return
    (ws / "verify.json").write_text(json.dumps(ver, indent=1), encoding="utf-8")
    set_stage(slug, "done" if ver["ok"] else "failed", render_seconds=round(time.time() - t0), verify=ver)


def run(specs_dir: Path) -> None:
    from engine.original import explainer as ex

    log(f"batch runner started, specs in {specs_dir}")
    st0 = load_state()
    for slug, v in st0.items():  # a crash mid-job: drawing is idempotent (pictures are reused), so just queue it again
        if v.get("stage") in ("drawing", "rendering"):
            v["stage"] = "queued" if v["stage"] == "drawing" else "review"
    save_state(st0)
    while True:
        if (BATCH / "STOP").exists():
            log("STOP file found: exiting")
            return
        specs = sorted(specs_dir.glob("*.txt"))
        did = False
        info = []
        for sp in specs:
            try:
                info.append((sp, ex.parse(sp.read_text(encoding="utf-8"))["slug"]))
            except Exception as e:
                log(f"{sp.name}: unreadable: {e}")
        st = load_state()
        try:
            # 1. approved videos are voiced and rendered first (cheap, and they finish a video)
            for sp, slug in info:
                if (STORIES / slug / "approved.flag").exists() and st.get(slug, {}).get("stage") not in ("done", "failed", "rendering"):
                    do_render(sp)
                    did = True
                    break
            # 2. redo requests (a spec edited after review): only changed pictures redraw
            if not did:
                for sp, slug in info:
                    flag = STORIES / slug / "redo.flag"
                    if flag.exists():
                        flag.unlink()
                        (STORIES / slug / "approved.flag").unlink(missing_ok=True)
                        do_art(sp, st)
                        did = True
                        break
            # 3. the next video that has no pictures yet
            if not did:
                for sp, slug in info:
                    if slug not in st or st[slug].get("stage") in ("queued",):
                        do_art(sp, st)
                        did = True
                        break
        except Exception as e:
            log(f"ERROR {type(e).__name__}: {e}\n{traceback.format_exc()[-800:]}")
            time.sleep(60)
            continue
        if not did:
            time.sleep(20)


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "run":
        sys.path.insert(0, str(ROOT))
        run(Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "stories" / "explainers")
    elif len(sys.argv) >= 3 and sys.argv[1] == "sheets":
        print(*review_sheets(STORIES / sys.argv[2]), sep="\n")
    elif len(sys.argv) >= 4 and sys.argv[1] == "pick":  # pick <slug> p003,p006 -> review/picked_1.jpg
        print(*review_sheets(STORIES / sys.argv[2], only=sys.argv[3].split(","), name="picked"), sep="\n")
    elif len(sys.argv) >= 3 and sys.argv[1] == "approve":
        (STORIES / sys.argv[2] / "approved.flag").write_text("ok", encoding="utf-8")
    elif len(sys.argv) >= 3 and sys.argv[1] == "redo":
        (STORIES / sys.argv[2] / "redo.flag").write_text("redo", encoding="utf-8")
    elif len(sys.argv) >= 2 and sys.argv[1] == "status":
        for k, v in load_state().items():
            print(k, v.get("stage"), {x: v[x] for x in ("beats", "est_seconds", "art_seconds", "render_seconds") if x in v})
    else:
        print(__doc__)
