"""ChronoFlow Deliver: a render queue plus the final encode (preset, size and fit, frame rate, codec, quality, audio, loudness).

A render has two stages. First the timeline master (the existing EDL renderer: cuts, transitions, colour grades, Fusion effects) is made at the
timeline's own size. Then one FFmpeg encode turns that master into the file you asked for. One render runs at a time (they all want the GPU and CPU);
the rest wait in the queue. Every render keeps a small JSON record so the history survives a restart.
"""
from __future__ import annotations

import json
import queue
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

TERMINAL = ("done", "failed", "cancelled")
LOUDNESS_TARGETS = (-14.0, -16.0, -23.0)             # YouTube / streaming, podcast-ish, EBU R128 broadcast
FPS_CHOICES = (0, 23.976, 24, 25, 29.97, 30, 50, 59.94, 60)

PRESETS: list[dict[str, Any]] = [
    {"id": "youtube_1080p", "name": "YouTube 1080p", "note": "1920x1080, H.264, loudness -14 LUFS",
     "settings": {"codec": "h264", "width": 1920, "height": 1080, "fit": "fit", "fps": 0, "quality": 18, "loudness": -14}},
    {"id": "youtube_4k", "name": "YouTube 4K", "note": "3840x2160, H.264, loudness -14 LUFS",
     "settings": {"codec": "h264", "width": 3840, "height": 2160, "fit": "fit", "fps": 0, "quality": 18, "loudness": -14}},
    {"id": "shorts_9x16", "name": "Shorts / Reels 9:16", "note": "1080x1920 filled (crops the sides), H.264, -14 LUFS",
     "settings": {"codec": "h264", "width": 1080, "height": 1920, "fit": "fill", "fps": 30, "quality": 18, "loudness": -14}},
    {"id": "square_1x1", "name": "Square 1:1", "note": "1080x1080 filled, H.264, -14 LUFS",
     "settings": {"codec": "h264", "width": 1080, "height": 1080, "fit": "fill", "fps": 30, "quality": 20, "loudness": -14}},
    {"id": "h265_small", "name": "H.265 small file", "note": "timeline size, HEVC, about half the size of H.264",
     "settings": {"codec": "h265", "width": 0, "height": 0, "fit": "fit", "fps": 0, "quality": 24, "loudness": None}},
    {"id": "prores_master", "name": "ProRes 422 master", "note": "timeline size, 10-bit, .mov, PCM audio, for further editing",
     "settings": {"codec": "prores", "width": 0, "height": 0, "fit": "fit", "fps": 0, "quality": 2, "loudness": None}},
    {"id": "draft_720p", "name": "Draft 720p (fast)", "note": "1280x720, H.264, quick to render",
     "settings": {"codec": "h264", "width": 1280, "height": 720, "fit": "fit", "fps": 0, "quality": 26, "loudness": None}},
    {"id": "match_timeline", "name": "Match timeline", "note": "no scaling, H.264, no loudness change",
     "settings": {"codec": "h264", "width": 0, "height": 0, "fit": "fit", "fps": 0, "quality": 18, "loudness": None}},
]

DEFAULT_QUALITY = {"h264": 18, "h265": 24, "vp9": 32, "prores": 2}
QUALITY_RANGE = {"h264": (0, 51), "h265": (0, 51), "vp9": (0, 63), "prores": (0, 5)}
EXT = {"h264": "mp4", "h265": "mp4", "vp9": "webm", "prores": "mov"}


_nvenc: bool | None = None


def nvenc_available() -> bool:
    """True when this FFmpeg lists the NVENC encoders (it says nothing about whether a GPU is free right now)."""
    global _nvenc
    if _nvenc is None:
        try:
            out = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=15).stdout
            _nvenc = "h264_nvenc" in out and "hevc_nvenc" in out
        except (OSError, subprocess.SubprocessError):
            _nvenc = False
    return _nvenc


def normalize_settings(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Validate request settings and fill defaults. Raises ValueError with a sentence a person can act on."""
    raw = dict(raw or {})

    def num(key, default, lo, hi, kind=int):
        v = raw.get(key, default)
        if v is None:
            return default
        try:
            v = kind(v)
        except (TypeError, ValueError):
            raise ValueError(f"{key} must be a number")
        if not lo <= v <= hi:
            raise ValueError(f"{key} must be between {lo} and {hi}")
        return v

    codec = str(raw.get("codec", "h264")).lower()
    if codec not in EXT:
        raise ValueError(f"codec must be one of {', '.join(EXT)}")
    encoder = str(raw.get("encoder", "cpu")).lower()
    if encoder not in ("cpu", "nvenc"):
        raise ValueError("encoder must be cpu or nvenc")
    if encoder == "nvenc" and codec not in ("h264", "h265"):
        raise ValueError("NVENC can encode H.264 and H.265 only")
    width, height = num("width", 0, 0, 7680), num("height", 0, 0, 7680)
    if bool(width) != bool(height):
        raise ValueError("set both width and height, or neither (0 = match the timeline)")
    if width and (width < 160 or height < 160):
        raise ValueError("width and height must be at least 160")
    width, height = width - width % 2, height - height % 2
    fit = str(raw.get("fit", "fit")).lower()
    if fit not in ("fit", "fill", "stretch"):
        raise ValueError("fit must be fit, fill or stretch")
    fps = num("fps", 0, 0, 120, float)
    if fps and not any(abs(fps - c) < 0.01 for c in FPS_CHOICES):
        raise ValueError(f"fps must be one of {', '.join(str(c) for c in FPS_CHOICES)} (0 = keep the timeline's)")
    qlo, qhi = QUALITY_RANGE[codec]
    quality = num("quality", DEFAULT_QUALITY[codec], qlo, qhi)
    bitrate_k = num("bitrate_k", 0, 0, 400_000)
    loudness = raw.get("loudness")
    if loudness in (None, "", "off", False):
        loudness = None
    else:
        try:
            loudness = float(loudness)
        except (TypeError, ValueError):
            raise ValueError("loudness must be off or a LUFS number")
        if loudness not in LOUDNESS_TARGETS:
            raise ValueError(f"loudness target must be one of {', '.join(str(int(t)) for t in LOUDNESS_TARGETS)} LUFS, or off")
    audio = bool(raw.get("audio", True))
    audio_kbps = num("audio_kbps", 192, 64, 512)
    sample_rate = num("sample_rate", 48000, 22050, 96000)
    if sample_rate not in (32000, 44100, 48000, 96000):
        raise ValueError("sample_rate must be 32000, 44100, 48000 or 96000")
    r_in, r_out = raw.get("range_in"), raw.get("range_out")
    r_in = None if r_in in (None, "") else float(r_in)
    r_out = None if r_out in (None, "") else float(r_out)
    if (r_in is not None and r_in < 0) or (r_out is not None and r_in is not None and r_out <= r_in):
        raise ValueError("the render range must end after it starts")
    name = re.sub(r"[^A-Za-z0-9 _.\-]+", "_", str(raw.get("name") or "chronoflow").strip())[:80].strip(" .") or "chronoflow"
    return {"preset": str(raw.get("preset") or "")[:40], "codec": codec, "encoder": encoder, "width": width, "height": height, "fit": fit, "fps": fps,
            "quality": quality, "bitrate_k": bitrate_k, "loudness": loudness, "audio": audio, "audio_kbps": audio_kbps, "sample_rate": sample_rate,
            "range_in": r_in, "range_out": r_out, "name": name}


def video_filter(s: dict[str, Any]) -> str:
    parts = []
    if s["width"]:
        w, h = s["width"], s["height"]
        if s["fit"] == "fit":
            parts.append(f"scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black")
        elif s["fit"] == "fill":
            parts.append(f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h}")
        else:
            parts.append(f"scale={w}:{h}:flags=lanczos")
        parts.append("setsar=1")
    if s["fps"]:
        parts.append(f"fps={s['fps']:g}")
    return ",".join(parts)


def loudnorm_filter(target: float, measured: dict[str, str] | None) -> str:
    base = f"loudnorm=I={target:g}:TP=-1.5:LRA=11"
    if measured:
        base += (f":measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:measured_LRA={measured['input_lra']}"
                 f":measured_thresh={measured['input_thresh']}:offset={measured['target_offset']}:linear=true")
    return base


def encode_args(s: dict[str, Any]) -> list[str]:
    """The video+audio codec options for these settings (no inputs, filters or output)."""
    c, q, enc = s["codec"], s["quality"], s["encoder"]
    if c == "prores":
        v = ["-c:v", "prores_ks", "-profile:v", str(q), "-pix_fmt", "yuv422p10le"]
        a = ["-c:a", "pcm_s16le"]
    elif c == "vp9":
        v = ["-c:v", "libvpx-vp9", "-row-mt", "1", "-pix_fmt", "yuv420p"] + (["-b:v", f"{s['bitrate_k']}k"] if s["bitrate_k"] else ["-crf", str(q), "-b:v", "0"])
        a = ["-c:a", "libopus", "-b:a", f"{s['audio_kbps']}k"]
    elif enc == "nvenc":
        codec = "h264_nvenc" if c == "h264" else "hevc_nvenc"
        v = ["-c:v", codec, "-preset", "p5", "-pix_fmt", "yuv420p"] + (["-b:v", f"{s['bitrate_k']}k"] if s["bitrate_k"] else ["-rc", "vbr", "-cq", str(q), "-b:v", "0"])
        v += ["-tag:v", "hvc1"] if c == "h265" else ["-profile:v", "high"]
        a = ["-c:a", "aac", "-b:a", f"{s['audio_kbps']}k"]
    else:
        codec = "libx264" if c == "h264" else "libx265"
        v = ["-c:v", codec, "-preset", "medium", "-pix_fmt", "yuv420p"] + (["-b:v", f"{s['bitrate_k']}k"] if s["bitrate_k"] else ["-crf", str(q)])
        v += ["-tag:v", "hvc1", "-x265-params", "log-level=error"] if c == "h265" else ["-profile:v", "high"]
        a = ["-c:a", "aac", "-b:a", f"{s['audio_kbps']}k"]
    if c in ("h264", "h265"):
        v += ["-movflags", "+faststart"]
    return v + (a + ["-ar", str(s["sample_rate"])] if s["audio"] else ["-an"])


class DeliverQueue:
    """One worker thread, FIFO. render_master(clips, path, overlays, luts) -> path is the EDL renderer."""

    def __init__(self, output_dir: Path, render_master: Callable[..., Any], ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe"):
        self.dir = Path(output_dir) / "deliver"
        self.records_dir = self.dir / "_records"
        self.records_dir.mkdir(parents=True, exist_ok=True)
        self.render_master, self.ffmpeg, self.ffprobe = render_master, ffmpeg, ffprobe
        self._q: queue.Queue[str] = queue.Queue()
        self._lock = threading.Lock()
        self._records: dict[str, dict[str, Any]] = {}
        self._payloads: dict[str, dict[str, Any]] = {}
        self._procs: dict[str, subprocess.Popen] = {}
        self._cancel: set[str] = set()
        self._load()
        threading.Thread(target=self._worker, name="chronoflow-deliver", daemon=True).start()

    # ---- records ----
    def _path(self, rid: str) -> Path:
        return self.records_dir / f"{rid}.json"

    def _save(self, rec: dict[str, Any]) -> None:
        tmp = self._path(rec["id"]).with_suffix(".tmp")
        tmp.write_text(json.dumps(rec, indent=1), encoding="utf-8")
        tmp.replace(self._path(rec["id"]))

    def _load(self) -> None:
        for p in self.records_dir.glob("*.json"):
            try:
                rec = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if rec.get("status") not in TERMINAL:
                rec.update(status="failed", error="The engine restarted before this render finished.", finished=time.time())
                self._save(rec)
            self._records[rec["id"]] = rec

    def _update(self, rid: str, **fields: Any) -> None:
        with self._lock:
            rec = self._records[rid]
            rec.update(fields)
            self._save(rec)

    # ---- public ----
    def submit(self, payload: dict[str, Any], settings: dict[str, Any] | None) -> dict[str, Any]:
        """payload = {clips, overlays, luts}. Returns the new record. Raises ValueError for bad settings or an empty timeline."""
        if not payload.get("clips"):
            raise ValueError("The timeline has no clips to render.")
        s = normalize_settings(settings)
        rid = uuid.uuid4().hex[:10]
        out = self._unique(self.dir / f"{s['name']}.{EXT[s['codec']]}")
        rec = {"id": rid, "status": "queued", "stage": "queued", "progress": 0.0, "settings": s, "file": out.name, "path": str(out), "url": f"/chronoflow/outputs/deliver/{out.name}",
               "created": time.time(), "started": None, "finished": None, "error": "", "size": 0, "duration": 0.0}
        with self._lock:
            self._records[rid] = rec
            self._payloads[rid] = payload
            self._save(rec)
        self._q.put(rid)
        return dict(rec)

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return sorted((dict(r) for r in self._records.values()), key=lambda r: r["created"], reverse=True)

    def get(self, rid: str) -> dict[str, Any] | None:
        with self._lock:
            r = self._records.get(rid)
            return dict(r) if r else None

    def cancel(self, rid: str) -> bool:
        with self._lock:
            rec = self._records.get(rid)
            if not rec or rec["status"] in TERMINAL:
                return False
            self._cancel.add(rid)
            proc = self._procs.get(rid)
        if proc and proc.poll() is None:
            proc.terminate()
        if rec["status"] == "queued":
            self._update(rid, status="cancelled", stage="cancelled", finished=time.time())
        return True

    def delete(self, rid: str) -> bool:
        """Forget a finished render and remove its file. Refuses one that is still queued or running."""
        with self._lock:
            rec = self._records.get(rid)
            if not rec or rec["status"] not in TERMINAL:
                return False
            del self._records[rid]
        target = (self.dir / rec["file"]).resolve()
        if target.parent == self.dir.resolve() and target.is_file():
            target.unlink(missing_ok=True)
        self._path(rid).unlink(missing_ok=True)
        return True

    # ---- worker ----
    def _unique(self, path: Path) -> Path:
        """A free file name: not on disk, and not already promised to another queued render."""
        taken = {r["file"] for r in self._records.values()}
        n, p = 2, path
        while p.exists() or p.name in taken:
            p = path.with_name(f"{path.stem}_{n}{path.suffix}")
            n += 1
        return p

    def _worker(self) -> None:
        while True:
            rid = self._q.get()
            with self._lock:
                rec = self._records.get(rid)
                payload = self._payloads.pop(rid, None)
            if not rec or rec["status"] != "queued" or payload is None:
                continue
            try:
                self._run(rid, rec, payload)
            except Exception as exc:                                         # a render must never kill the worker
                state = "cancelled" if rid in self._cancel else "failed"
                self._update(rid, status=state, stage=state, error="" if state == "cancelled" else str(exc)[:600], finished=time.time())
            finally:
                self._cancel.discard(rid)
                self._procs.pop(rid, None)

    def _check_cancel(self, rid: str) -> None:
        if rid in self._cancel:
            raise RuntimeError("cancelled")

    def _probe(self, path: Path) -> dict[str, Any]:
        out = subprocess.run([self.ffprobe, "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height,r_frame_rate", "-of", "json", str(path)],
                             capture_output=True, text=True)
        data = json.loads(out.stdout or "{}")
        v = next((x for x in data.get("streams", []) if x.get("codec_type") == "video"), {})
        return {"duration": float(data.get("format", {}).get("duration") or 0), "has_audio": any(x.get("codec_type") == "audio" for x in data.get("streams", [])),
                "width": v.get("width"), "height": v.get("height")}

    def _run_ffmpeg(self, rid: str, cmd: list[str], total: float, on_progress: Callable[[float], None] | None) -> str:
        proc = subprocess.Popen(cmd[:1] + ["-progress", "pipe:1", "-nostats"] + cmd[1:], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)   # global options go before the output
        self._procs[rid] = proc
        err: list[str] = []
        threading.Thread(target=lambda: err.append(proc.stderr.read()), daemon=True).start()
        for line in proc.stdout:
            if line.startswith("out_time_us=") and on_progress and total > 0:
                try:
                    on_progress(min(1.0, int(line.split("=")[1]) / 1e6 / total))
                except ValueError:
                    pass
        proc.wait()
        stderr = "".join(err)
        self._check_cancel(rid)
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {stderr.strip()[-400:]}")
        return stderr

    def _run(self, rid: str, rec: dict[str, Any], payload: dict[str, Any]) -> None:
        s = rec["settings"]
        work = self.dir / "_work" / rid
        work.mkdir(parents=True, exist_ok=True)
        out = self.dir / rec["file"]
        w_master, w_measure = 0.35, (0.1 if s["loudness"] is not None and s["audio"] else 0.0)
        w_encode = 1.0 - w_master - w_measure
        self._update(rid, status="rendering", stage="timeline", progress=0.0, started=time.time())
        try:
            master = work / "master.mp4"
            self.render_master(payload["clips"], master, payload.get("overlays"), payload.get("luts"))
            self._check_cancel(rid)
            if not master.exists():
                raise RuntimeError("The timeline render produced no video (a clip may be missing on disk).")
            info = self._probe(master)
            start, end = s["range_in"] or 0.0, s["range_out"] if s["range_out"] is not None else info["duration"]
            end = min(end, info["duration"])
            if end - start < 0.1:
                raise RuntimeError("The render range is empty (it must lie inside the timeline).")
            length = end - start
            rng = ["-ss", f"{start:.3f}", "-to", f"{end:.3f}"] if (s["range_in"] is not None or s["range_out"] is not None) else []
            audio_on = s["audio"] and info["has_audio"]
            measured = None
            if s["loudness"] is not None and audio_on:
                self._update(rid, stage="measuring", progress=w_master)
                text = self._run_ffmpeg(rid, [self.ffmpeg, "-hide_banner", "-y", *rng, "-i", str(master), "-vn", "-af", f"{loudnorm_filter(s['loudness'], None)}:print_format=json", "-f", "null", "-"],
                                        length, lambda f: self._update(rid, progress=round(w_master + w_measure * f, 3)))
                m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", text, re.S)
                measured = json.loads(m.group(0)) if m else None
            vf = video_filter(s)
            af = []
            if s["loudness"] is not None and audio_on:
                af.append(loudnorm_filter(s["loudness"], measured))
                af.append(f"aresample={s['sample_rate']}")
            cmd = [self.ffmpeg, "-hide_banner", "-y", *rng, "-i", str(master)]
            if vf:
                cmd += ["-vf", vf]
            if af:
                cmd += ["-af", ",".join(af)]
            cmd += encode_args({**s, "audio": audio_on}) + [str(out)]
            self._update(rid, stage="encoding", progress=w_master + w_measure)
            self._run_ffmpeg(rid, cmd, length, lambda f: self._update(rid, progress=round(w_master + w_measure + w_encode * f, 3)))
            probe = self._probe(out)
            self._update(rid, status="done", stage="done", progress=1.0, finished=time.time(), size=out.stat().st_size, duration=probe["duration"],
                         width=probe["width"], height=probe["height"])
        except Exception:
            out.unlink(missing_ok=True)                                      # never leave a half-written file behind
            raise
        finally:
            shutil.rmtree(work, ignore_errors=True)
