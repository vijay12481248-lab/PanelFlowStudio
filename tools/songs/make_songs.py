"""Generate the song catalog with the local ACE-Step 1.5 server (http://127.0.0.1:8001).

  python tools/songs/make_songs.py gen   [--model turbo|sft] [--n 4] [ids...]   several takes per song (resumable)
  python tools/songs/make_songs.py score [--model turbo|sft] [ids...]           transcribe vocals, pick best take
  python tools/songs/make_songs.py status

Order matters for the 16 GB GPU: gen (ACE-Step up) -> stop ACE-Step -> score (faster-whisper on GPU).
Songs live in tools/songs/catalog_*.py (SONGS lists). Output: output/Songs/<id>_<slug>/<model>_take<k>.flac
An existing take is never redone. Nothing here downloads a model: the server runs HF_HUB_OFFLINE=1.
"""
from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output" / "Songs"
API = "http://127.0.0.1:8001"
MODELS = {"turbo": ("acestep-v15-turbo", 8), "sft": ("acestep-v15-sft", 50)}


def catalog() -> list[dict]:
    sys.path.insert(0, str(Path(__file__).parent))
    songs: list[dict] = []
    for f in sorted(Path(__file__).parent.glob("catalog_*.py")):
        songs += importlib.import_module(f.stem).SONGS
    ids = [s["id"] for s in songs]
    assert len(ids) == len(set(ids)), "duplicate song ids"
    return songs


def slug(s: dict) -> str:
    return f"{s['id']}_{re.sub(r'[^a-z0-9]+', '-', s['title'].lower()).strip('-')}"


def post(path: str, body: dict) -> dict:
    req = urllib.request.Request(API + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def submit_and_wait(payload: dict, timeout_s: int = 7200, src: Path | None = None) -> list[dict]:
    if src:  # the server refuses absolute paths: upload the source take as multipart form data instead
        import requests
        form = {k: (str(v).lower() if isinstance(v, bool) else str(v)) for k, v in payload.items() if k != "src_audio_path"}
        with open(src, "rb") as fh:
            r = requests.post(API + "/release_task", data=form, files={"src_audio": (src.name, fh, "audio/flac")}, timeout=120)
        r.raise_for_status()
        task = r.json()["data"]["task_id"]
    else:
        task = post("/release_task", payload)["data"]["task_id"]
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        time.sleep(3)
        row = post("/query_result", {"task_id_list": [task]})["data"][0]
        if row["status"] == 1:
            res = row["result"]
            return json.loads(res) if isinstance(res, str) else res
        if row["status"] == 2:
            raise RuntimeError(f"ACE-Step failed: {row.get('result')}")
    raise TimeoutError(task)


def stage_gen(songs, model, n, tag=None, cfg=None, cover_from=None, strength=0.7):
    tag = tag or model
    mid, steps = MODELS[model]
    for s in songs:
        d = OUT / slug(s)
        d.mkdir(parents=True, exist_ok=True)
        if len(list(d.glob(f"{tag}_take*.flac"))) >= n:
            continue
        payload = {
            "prompt": s["caption"], "lyrics": s["lyrics"].strip(), "vocal_language": s.get("lang", "en"),
            "audio_duration": s["dur"], "bpm": s["bpm"], "key_scale": s["key"], "time_signature": s.get("ts", "4"),
            "audio_format": "flac", "batch_size": n, "use_random_seed": True, "model": mid,
            "inference_steps": steps, "thinking": True,
            # keep my caption/metas: the LM only plans codes, it must not rewrite what the song is about
            "use_cot_caption": False, "use_cot_language": False,
        }
        if cfg is not None:
            payload["guidance_scale"] = cfg
        if cover_from:  # keep the arrangement of an existing best take, re-render it with `model` (e.g. turbo music, SFT vocals)
            b = best_take(d, cover_from)  # pooled over every run of that family, e.g. turbo + turboB
            if not b:
                continue
            src = b[1]
            payload |= {"task_type": "cover", "audio_cover_strength": strength, "thinking": False}
        else:
            src = None
        t0 = time.time()
        rows = submit_and_wait(payload, src=src)
        for k, row in enumerate(rows, 1):
            url = API + row["file"] if row["file"].startswith("/") else f"{API}/{row['file']}"
            (d / f"{tag}_take{k}.flac").write_bytes(urllib.request.urlopen(url, timeout=120).read())
        (d / "meta.json").write_text(json.dumps({k: v for k, v in s.items() if k != "lyrics"} | {"lyrics": s["lyrics"]}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{slug(s)}: {len(rows)} takes in {time.time() - t0:.0f}s", flush=True)


def words(text: str, lang: str) -> list[str]:
    text = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", text)  # structure tags and backing vocals are not transcribed reliably
    if lang in ("ja", "te"):  # no word spaces / unreliable segmentation: character error rate
        return list(re.sub(r"[\s、。！？!?,.\-ー…]", "", text))
    return re.findall(r"[a-z']+", text.lower())


def wer(ref: list[str], hyp: list[str]) -> float:
    d = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        prev, d[0] = d[0], i
        for j, h in enumerate(hyp, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (r != h))
    return d[-1] / max(1, len(ref))


def stage_score(songs, tag):
    import numpy as np
    import soundfile as sf
    from faster_whisper import WhisperModel
    wm = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=3, local_files_only=True)  # local_files_only: never download
    for s in songs:
        d = OUT / slug(s)
        takes = sorted(d.glob(f"{tag}_take*.flac"))
        if not takes or (d / f"{tag}_score.json").exists():  # already scored
            continue
        ref = words(s["lyrics"], s.get("lang", "en"))
        report = []
        for t in takes:
            a, sr = sf.read(t, dtype="float32")
            peak = float(np.abs(a).max())
            mono = a.mean(axis=1) if a.ndim > 1 else a
            rms_db = 20 * np.log10(float(np.sqrt((mono ** 2).mean())) + 1e-9)
            from math import gcd
            from scipy.signal import resample_poly  # decode ourselves: this venv's PyAV is too old for faster-whisper's file reader
            g = gcd(16000, sr)
            x16 = resample_poly(mono, 16000 // g, sr // g).astype("float32")
            segs, _ = wm.transcribe(x16, language=s.get("lang", "en"), vad_filter=False, beam_size=5)
            hyp = words(" ".join(x.text for x in segs), s.get("lang", "en"))
            err = wer(ref, hyp)
            # lyric accuracy is the main signal; clipping or a dead take is disqualifying
            report.append({"take": t.name, "wer": round(err, 3), "peak": round(peak, 3), "rms_db": round(rms_db, 1),
                           "dur": round(len(mono) / sr, 1), "ok": bool(peak < 0.999 and rms_db > -35)})
        good = [r for r in report if r["ok"]] or report
        best = min(good, key=lambda r: r["wer"])
        (d / f"{tag}_score.json").write_text(json.dumps({"best": best["take"], "takes": report}, indent=1), encoding="utf-8")
        print(f"{slug(s)}: best {best['take']} wer={best['wer']}  all={[r['wer'] for r in report]}", flush=True)


def stage_status(songs):
    for s in songs:
        d = OUT / slug(s)
        tags = sorted({f.name.split("_take")[0] for f in d.glob("*_take*.flac")})
        print(slug(s), {g: len(list(d.glob(f"{g}_take*.flac"))) for g in tags}, "scored:", [f.name[:-11] for f in d.glob("*_score.json")])


def best_take(d: Path, prefix: str = ""):
    """Lowest lyric error across every scored run whose tag starts with `prefix`; None if nothing is scored yet."""
    cands = []
    for f in d.glob(f"{prefix}*_score.json"):
        sc = json.loads(f.read_text(encoding="utf-8"))
        cands += [(t["wer"], d / t["take"]) for t in sc["takes"] if t["ok"]]
    return min(cands) if cands else None


def stage_master(songs):
    """Copy each song's best take to output/Songs/_final as -14 LUFS FLAC + 320k MP3 (YouTube loudness)."""
    import subprocess
    fin = OUT / "_final"
    fin.mkdir(parents=True, exist_ok=True)
    for s in songs:
        b = best_take(OUT / slug(s))
        if not b:
            continue
        stem = fin / slug(s)
        if stem.with_suffix(".mp3").exists():
            continue
        af = "loudnorm=I=-14:TP=-1.0:LRA=11"
        for ext, extra in ((".flac", []), (".mp3", ["-b:a", "320k"])):
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(b[1]), "-af", af, "-ar", "48000", *extra, str(stem.with_suffix(ext))], check=True)
        (fin / f"{slug(s)}.json").write_text(json.dumps({"take": b[1].name, "wer": b[0]}), encoding="utf-8")
        print(f"{slug(s)}: {b[1].name} (lyric error {b[0]:.1%})", flush=True)


def encode(src: Path, dst: Path):
    import subprocess
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-af", "loudnorm=I=-14:TP=-1.0:LRA=11", "-ar", "48000", "-b:a", "320k", str(dst)], check=True)


def stage_showcase(songs):
    """Per song, master the best take of each family (turbo, sft, hyb) into _showcase so they can be compared by ear."""
    out = OUT / "_showcase"
    out.mkdir(exist_ok=True)
    for s in songs:
        for fam in ("turbo", "sft", "hyb"):
            b = best_take(OUT / slug(s), fam)
            if b:
                encode(b[1], out / f"{slug(s)}__{fam}.mp3")
                print(f"{slug(s)} {fam}: {b[1].name} lyric error {b[0]:.1%}", flush=True)


def stage_index(songs):
    """output/Songs/index.html: every mastered song with a player, theme, caption and lyrics. Open it from disk."""
    import html
    rows = []
    for s in songs:
        mp3 = OUT / "_final" / f"{slug(s)}.mp3"
        if not mp3.exists():
            continue
        rows.append(f"<section><h2>{s['id']} · {html.escape(s['title'])} <small>{s.get('lang', 'en')} · {s['bpm']} BPM · {s['key']}</small></h2>"
                    f"<p><i>{html.escape(s['theme'])}</i></p><audio controls preload=none src='_final/{mp3.name}'></audio>"
                    f"<details><summary>lyrics and style</summary><p><b>Style:</b> {html.escape(s['caption'])}</p><pre>{html.escape(s['lyrics'].strip())}</pre></details></section>")
    (OUT / "index.html").write_text("<!doctype html><meta charset=utf-8><title>Songs</title><style>body{font:16px system-ui;max-width:760px;margin:2em auto;padding:0 1em}"
                                    "section{border-bottom:1px solid #8884;padding:1em 0}audio{width:100%}small{font-weight:400;opacity:.6}pre{white-space:pre-wrap}</style>"
                                    f"<h1>{len(rows)} songs</h1>" + "".join(rows), encoding="utf-8")
    print(f"index: {len(rows)} songs -> {OUT / 'index.html'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["gen", "score", "status", "master", "index", "showcase"])
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--model", choices=list(MODELS), default="turbo")
    ap.add_argument("--n", type=int, default=4)
    ap.add_argument("--tag", help="label for this run (default: model name), e.g. sft_cfg4")
    ap.add_argument("--cfg", type=float, help="guidance_scale override (sft only)")
    ap.add_argument("--cover-from", help="re-render the best scored take of this tag (cover task), e.g. turbo")
    ap.add_argument("--strength", type=float, default=0.7, help="cover strength 0-1: higher keeps the source closer")
    a = ap.parse_args()
    all_songs = catalog()
    pick = [s for s in all_songs if not a.ids or s["id"] in a.ids]
    {"gen": lambda: stage_gen(pick, a.model, a.n, a.tag, a.cfg, a.cover_from, a.strength), "score": lambda: stage_score(pick, a.tag or a.model), "status": lambda: stage_status(pick),
     "master": lambda: stage_master(pick), "index": lambda: stage_index(pick), "showcase": lambda: stage_showcase(pick)}[a.stage]()
