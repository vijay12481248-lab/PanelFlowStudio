"""Cinematic assembler for reels whose spec has cine=True (see spec_mosquito.py for the extra keys).

  python tools/reels/cine.py r11 [--scale 0.5] [--stills]     (--scale: preview at lower resolution, --stills: use panels when a clip is missing)

What it adds to make_reel.stage_assemble: a virtual camera per shot (push, pull, punch with hit-stop, shake, drift, dutch), cuts snapped to the
music's beat grid, transitions (flash, whip, zoom, glitch, dip), a colour look per scene, vignette + grain, synthesized sound effects
(no downloads), word-by-word captions timed by Whisper, and a ducked music bed. Frames are rendered in numpy/cv2 and piped to ffmpeg.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt, stft

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_reel as mr  # noqa: E402

SR, FPS = mr.SR, 30
LEAD, TAIL = 0.15, 0.18  # silence before / after a spoken line inside its shot
rng = np.random.default_rng(11)

# ------------------------------------------------------------------ sound effects (all synthesized)
def _t(d): return np.arange(int(d * SR)) / SR
def _bp(x, lo, hi): return sosfilt(butter(2, [lo, hi], "band", fs=SR, output="sos"), x)
def _lp(x, f): return sosfilt(butter(2, f, "low", fs=SR, output="sos"), x)
def _hp(x, f): return sosfilt(butter(2, f, "high", fs=SR, output="sos"), x)
def _st(x, pan=0.5): return np.stack([x * np.sqrt(1 - pan), x * np.sqrt(pan)], 1)  # pan 0 = left, 1 = right
def _sweep_pan(x, a, b):
    p = np.linspace(a, b, x.size)
    return np.stack([x * np.sqrt(1 - p), x * np.sqrt(p)], 1)


def sfx_buzz(d=2.4, f0=520.0, loud=0.5, pan=(0.15, 0.85)):
    t = _t(d)
    f = f0 * (1 + 0.035 * np.sin(2 * np.pi * 6.5 * t) + 0.02 * np.sin(2 * np.pi * 2.1 * t)) + 80 * np.sin(2 * np.pi * 0.7 * t)
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = sum(np.sin(k * ph) / k for k in range(1, 8)) * (1 + 0.45 * np.sin(2 * np.pi * 31 * t))
    x = _bp(x, 280, 3800) * np.sin(np.pi * np.clip(t / d, 0, 1)) ** 0.6
    return _sweep_pan(x / np.abs(x).max() * loud, *pan)


def sfx_swarm(d=2.6):
    out = sum(sfx_buzz(d, f0=f, loud=0.22, pan=(p, 1 - p)) for f, p in [(430, .1), (480, .9), (520, .3), (560, .7), (610, .5), (390, .2), (650, .8)])
    return out


def sfx_boom(d=1.3, loud=1.0):
    t = _t(d)
    ph = 2 * np.pi * np.cumsum(35 + 85 * np.exp(-t * 7)) / SR
    x = np.sin(ph) * np.exp(-t * 2.8) + 0.5 * _lp(rng.standard_normal(t.size), 180) * np.exp(-t * 4) * 4
    return _st(x / np.abs(x).max() * loud, 0.5)


def sfx_thud(d=0.3):
    t = _t(d)
    x = np.sin(2 * np.pi * np.cumsum(50 + 90 * np.exp(-t * 30)) / SR) * np.exp(-t * 14)
    return _st(x * 0.9)


def sfx_whoosh(d=0.5, loud=0.9, a=0.15, b=0.85):
    t = _t(d)
    n = rng.standard_normal(t.size)
    env = np.sin(np.pi * np.clip(t / d, 0, 1)) ** 1.5
    out = np.zeros_like(n)
    for (lo, hi), c in zip([(300, 900), (900, 2500), (2500, 6000)], (0.2, 0.5, 0.8)):  # sweep up by cross-fading three bands
        out += _bp(n, lo, hi) * np.exp(-((t / d - c) ** 2) / 0.05)
    return _sweep_pan(out / np.abs(out).max() * env * loud, a, b)


def sfx_slap(d=0.35):
    t = _t(d)
    x = _hp(rng.standard_normal(t.size), 1200) * np.exp(-t * 55) + np.sin(2 * np.pi * 180 * t) * np.exp(-t * 40) * 0.8
    return _st(x / np.abs(x).max() * 0.95)


def sfx_click(d=0.25):
    t = _t(d)
    x = np.zeros(t.size)
    for off in (0.0, 0.11):
        i = int(off * SR)
        tt = _t(0.03)
        x[i:i + tt.size] += np.sin(2 * np.pi * 3200 * tt) * np.exp(-tt * 200)
    return _st(x * 0.6)


def sfx_stinger(d=0.9):
    t = _t(d)
    x = sum(np.sign(np.sin(2 * np.pi * f * t * (1 + 0.15 * t))) for f in (466, 493, 740, 784)) * np.exp(-t * 4) * (1 + 0.4 * np.sin(2 * np.pi * 45 * t))
    return _st(_bp(x, 400, 5000) / np.abs(x).max() * 0.7)


def sfx_ding(d=1.0):
    t = _t(d)
    x = (np.sin(2 * np.pi * 1760 * t) + 0.5 * np.sin(2 * np.pi * 2637 * t)) * np.exp(-t * 5)
    return _st(x * 0.45)


def sfx_heart(d=0.6):
    t = _t(d)
    x = np.zeros(t.size)
    for off in (0.0, 0.2):
        i = int(off * SR)
        tt = _t(0.25)
        x[i:i + tt.size] += np.sin(2 * np.pi * 58 * tt) * np.exp(-tt * 16)
    return _st(x * 1.0)


def sfx_riser(d=2.2):
    t = _t(d)
    n = rng.standard_normal(t.size)
    x = _bp(n, 250, 7000) * (t / d) ** 2.2 * (1 + 0.5 * np.sin(2 * np.pi * (3 + 10 * t / d) * t))
    return _st(x / np.abs(x).max() * 0.6)


def sfx_tada(d=1.2):
    t = _t(d)
    x = np.zeros(t.size)
    for k, f in enumerate((523, 659, 784, 1047)):
        i = int(k * 0.07 * SR)
        tt = t[: t.size - i]
        x[i:] += _lp(sum(np.sign(np.sin(2 * np.pi * f * h * tt)) / h for h in (1, 2)), 3500) * np.exp(-tt * 2.2)
    return _st(x / np.abs(x).max() * 0.55)


def sfx_birds(d=2.0):
    x = np.zeros(int(d * SR))
    for off in np.sort(rng.uniform(0, d - 0.3, 9)):
        tt = _t(0.12)
        f = rng.uniform(3200, 5200)
        i = int(off * SR)
        x[i:i + tt.size] += np.sin(2 * np.pi * np.cumsum(f * (1 + 0.25 * np.sin(2 * np.pi * 18 * tt))) / SR) * np.exp(-tt * 18)
    return _st(x * 0.18)


def sfx_crash(d=0.9):
    t = _t(d)
    x = _bp(rng.standard_normal(t.size), 400, 6000) * np.exp(-t * 6) + np.sin(2 * np.pi * 70 * t) * np.exp(-t * 12)
    return _st(x / np.abs(x).max() * 0.8)


def sfx_zap(d=0.35):
    t = _t(d)
    gate = (rng.random(t.size // 400 + 1) > 0.45).repeat(400)[: t.size]
    x = _hp(rng.standard_normal(t.size), 800) * gate * np.exp(-t * 6)
    return _st(x / np.abs(x).max() * 0.6)


SFX = dict(buzz=sfx_buzz, swarm=sfx_swarm, boom=sfx_boom, thud=sfx_thud, whoosh=sfx_whoosh, swoosh=lambda: sfx_whoosh(0.25, 0.7),
           slap=sfx_slap, click=sfx_click, stinger=sfx_stinger, ding=sfx_ding, heart=sfx_heart, riser=sfx_riser, tada=sfx_tada,
           birds=sfx_birds, crash=sfx_crash, zap=sfx_zap)
_cache: dict = {}


def sfx(name):
    if name not in _cache:
        _cache[name] = SFX[name]()
    return _cache[name]


# ------------------------------------------------------------------ beat grid from the real music file
def beat_grid(music: np.ndarray, hint: float) -> tuple[float, float]:
    """(beat period s, phase s) of the best pulse near the requested bpm, measured on the generated audio (ACE-Step only approximates bpm)."""
    _, _, z = stft(music, SR, nperseg=1024, noverlap=512)
    flux = np.maximum(0, np.diff(np.log1p(np.abs(z) * 10), axis=1)).sum(0)
    flux /= flux.max() + 1e-9
    fs, best = SR / 512, (-1.0, hint, 0.0)
    for bpm in np.arange(hint * 0.92, hint * 1.08, 0.1):
        per = 60 / bpm * fs
        for ph in np.arange(0, per, 0.5):
            idx = np.round(ph + per * np.arange(int((flux.size - ph) / per))).astype(int)
            score = flux[idx[idx < flux.size]].mean()
            if score > best[0]:
                best = (score, bpm, ph / fs)
    return 60 / best[1], best[2]


# ------------------------------------------------------------------ virtual camera
ease = lambda u: u * u * (3 - 2 * u)
out3 = lambda u: 1 - (1 - min(max(u, 0), 1)) ** 3


def shot_state(move, tt, u, f, nf):
    """-> zoom, focus (x, y), rotation deg, shake px (before scaling)."""
    if move == "push":
        return 1.05 + 0.17 * ease(u), f, 0.0, 0.0
    if move == "pull":
        return 1.25 - 0.2 * ease(u), f, 0.0, 0.0
    if move == "punch":
        return 1.08 + 0.47 * out3(tt / 0.12) + 0.1 * u, f, 2.5 * np.exp(-tt / 0.2) * np.sin(40 * tt), 22 * np.exp(-tt / 0.22)
    if move == "punchout":
        return 1.7 - 0.6 * out3(tt / 0.15), f, 0.0, 26 * np.exp(-tt / 0.3)
    if move == "shake":
        return 1.14, f, 0.8 * np.sin(9 * tt), 12.0
    if move == "drift":
        t2 = nf or (min(f[0] + 0.12, 0.8), f[1])
        return 1.28, (f[0] + (t2[0] - f[0]) * ease(u), f[1] + (t2[1] - f[1]) * ease(u)), 0.0, 0.0
    if move == "dutch":
        return 1.30 + 0.08 * ease(u), f, -2 - 6 * ease(u), 3.0
    raise ValueError(move)


def cam(scene, t):
    """Camera for local time t. Returns the state plus the hit-stop-adjusted source time and a punch flash 0-1."""
    d = scene["d"]
    shots = scene["cam"]
    starts = [s[1] * d for s in shots] + [d]
    tc = max(t, 0.0)
    k = max(i for i in range(len(shots)) if starts[i] <= tc + 1e-9)
    tt, span = tc - starts[k], max(starts[k + 1] - starts[k], 1e-3)
    u = min(tt / span, 1.0)
    nf = shots[k + 1][2] if k + 1 < len(shots) and shots[k][0] == "drift" else None
    z, f, rot, sh = shot_state(shots[k][0], tt, u, shots[k][2], nf)
    src, flash = tc, 0.0
    for i, (mv, _, _) in enumerate(shots):  # hit-stop: freeze the picture for 0.1 s at every punch
        if mv in ("punch", "punchout"):
            if starts[i] < tc < starts[i] + 0.1:
                src = starts[i]
            elif tc >= starts[i] + 0.1:
                src -= 0.1
            if tc >= starts[i]:
                flash = max(flash, 0.3 * np.exp(-(tc - starts[i]) / 0.07))
    # handheld life + shake
    n = (np.sin(tc * 7.3) + np.sin(tc * 12.9 + 1) * 0.6, np.sin(tc * 9.1 + 2) + np.sin(tc * 15.7) * 0.6)
    sh_x, sh_y = (sh + 2.5) * n[0], (sh + 2.5) * n[1]
    return z, f, rot, sh_x, sh_y, src, flash


GRADES = dict(  # (R, G, B gain), contrast, saturation, gamma, vignette
    night=((0.85, 0.95, 1.15), 1.15, 1.10, 0.92, 0.50), alarm=((1.25, 0.80, 0.78), 1.20, 1.15, 0.95, 0.60),
    day=((1.05, 1.0, 0.95), 1.05, 1.15, 1.0, 0.25), warm=((1.12, 1.0, 0.85), 1.10, 1.10, 0.97, 0.35),
    cold=((0.85, 1.0, 1.2), 1.20, 0.95, 0.9, 0.55), calm=((0.95, 1.0, 1.1), 0.95, 0.9, 1.05, 0.35))
_lut: dict = {}
_vig: dict = {}


def grade(img, name):
    gains, con, sat, gam, vig = GRADES[name]
    if name not in _lut:
        x = np.arange(256) / 255.0
        _lut[name] = [np.clip(((np.clip(x * g, 0, 1) ** gam - 0.5) * con + 0.5) * 255, 0, 255).astype(np.uint8) for g in (gains[2], gains[1], gains[0])]  # BGR
    img = cv2.merge([cv2.LUT(img[..., c], _lut[name][c]) for c in range(3)])
    gray = cv2.cvtColor(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    img = cv2.addWeighted(gray, 1 - sat, img, sat, 0)
    key = (name, img.shape[:2])
    if key not in _vig:
        h, w = img.shape[:2]
        yy, xx = np.mgrid[0:h, 0:w]
        r = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2) / 1.41
        _vig[key] = cv2.merge([(255 * (1 - vig * np.clip(r, 0, 1) ** 2.2)).astype(np.uint8)] * 3)
    return cv2.multiply(img, _vig[key], scale=1 / 255)


class Source:
    """Frames of a scene: the H3 clip, or the still picture (inserts, or --stills when the clip is missing)."""

    def __init__(self, scene, d, allow_stills):
        self.frames, self.fps = None, 24.0
        clip, panel = d / "clips" / f"s{scene['i']}.mp4", d / "panels" / f"s{scene['i']}.png"
        if not scene.get("still") and mr.have(clip):
            cap = cv2.VideoCapture(str(clip))
            self.fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
            fr = []
            while True:
                ok, f = cap.read()
                if not ok:
                    break
                fr.append(f)
            self.frames = fr
        elif scene.get("still") or allow_stills:
            if not mr.have(panel):
                sys.exit(f"{panel} missing")
            self.frames = [cv2.imread(str(panel))]
        else:
            sys.exit(f"{clip} missing (run the clips stage, or pass --stills to preview with the pictures)")

    def at(self, t):
        return self.frames[min(int(max(t, 0) * self.fps), len(self.frames) - 1)]


def render_scene(scene, src, t, W, H, k):
    """One graded frame of a scene at local time t (may be <0 or > duration while a transition overlaps)."""
    z, f, rot, sx, sy, st, flash = cam(scene, t)
    fr = src.at(st)
    sh, sw = fr.shape[:2]
    s = max(W / sw, H / sh) * z
    hw, hh = W / 2 / s, H / 2 / s
    cx, cy = np.clip(f[0] * sw, hw, sw - hw), np.clip(f[1] * sh, hh, sh - hh)
    a = np.deg2rad(rot)
    m = np.array([[s * np.cos(a), s * np.sin(a)], [-s * np.sin(a), s * np.cos(a)]])
    off = np.array([W / 2 + sx * k, H / 2 + sy * k]) - m @ np.array([cx, cy])
    img = cv2.warpAffine(fr, np.hstack([m, off[:, None]]), (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    img = cv2.addWeighted(img, 1.35, cv2.GaussianBlur(img, (0, 0), 1.6 * k), -0.35, 0)  # the clips are 480 px wide: bring back some edge
    if flash > 0.02:
        img = cv2.addWeighted(img, 1 - flash, np.full_like(img, 255), flash, 0)
    return grade(img, scene["grade"])


def zoom_img(img, s, blur=0.0):
    h, w = img.shape[:2]
    outs = [cv2.warpAffine(img, np.array([[q, 0, w / 2 * (1 - q)], [0, q, h / 2 * (1 - q)]], np.float32), (w, h), flags=cv2.INTER_LINEAR,
                           borderMode=cv2.BORDER_REPLICATE) for q in np.linspace(s, s * (1 + blur), 6 if blur else 1)]
    return np.mean(outs, 0).astype(np.uint8) if blur else outs[0]


def transition(kind, a, b, T, tc, W, H, fi, color):
    """Frame at global time T for the cut at tc; a / b are the outgoing / incoming rendered frames (None -> black)."""
    blk = np.zeros((H, W, 3), np.uint8)
    a = blk if a is None else a
    if kind == "dip":
        return cv2.addWeighted(a, max(0.0, 1 - (T - (tc - 0.2)) / 0.2), blk, 0, 0) if T < tc else cv2.multiply(b, np.full_like(b, int(255 * min(1, (T - tc) / 0.3))), scale=1 / 255)
    if kind == "flash":
        base = b if T >= tc else a
        al = min(1.0, (T - (tc - 0.03)) / 0.03) if T < tc else max(0.0, 1 - (T - tc) / 0.18) ** 1.5
        return cv2.addWeighted(base, 1 - al, np.full_like(base, color), al, 0)
    if kind == "whip":
        p = ease(min(max((T - (tc - 0.13)) / 0.26, 0), 1))
        sh = int(p * W)
        out = np.empty_like(a)
        out[:, : W - sh], out[:, W - sh:] = a[:, sh:], b[:, :sh]
        kk = 1 + 2 * int(np.sin(np.pi * p) * 0.1 * W)
        return cv2.blur(out, (kk, 1))
    if kind == "zoom":
        p = min(max((T - (tc - 0.12)) / 0.24, 0), 1)
        return zoom_img(a, 1 + 1.4 * (p * 2) ** 2, 0.18) if p < 0.5 else zoom_img(b, 1 + 0.6 * ((1 - p) * 2) ** 2, 0.18)
    if kind == "glitch":
        base = (b if T >= tc else a).copy()
        g = np.random.default_rng(fi)
        for _ in range(7):
            y, hgt = int(g.integers(0, H - 200)), int(g.integers(30, 200))
            base[y:y + hgt] = np.roll(base[y:y + hgt], int(g.integers(-110, 110)), axis=1)
        sh = int(g.integers(14, 40))
        base[..., 0], base[..., 2] = np.roll(base[..., 0], sh, 1), np.roll(base[..., 2], -sh, 1)
        base[::4] = (base[::4] * 0.6).astype(np.uint8)
        return base
    return b


TR_WINDOW = dict(dip=(0.2, 0.3), flash=(0.03, 0.18), whip=(0.13, 0.13), zoom=(0.12, 0.12), glitch=(0.1, 0.2))
TR_SFX = dict(whip=("whoosh", -0.25), zoom=("swoosh", -0.1), flash=("boom", 0.0), glitch=("zap", -0.05))


# ------------------------------------------------------------------ captions (word by word, pop)
def build_ass(r, plan):
    head = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 0\n\n[V4+ Styles]\n"
            "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n"
            f"Style: Cap,{mr.FONT},96,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,1,0,1,9,3,2,60,60,420,1\n"
            f"Style: Hook,{mr.FONT},124,&H0000E5FF,&H0000E5FF,&H00000000,&H80000000,0,0,0,0,100,100,1,0,1,10,3,8,60,60,230,1\n\n"
            "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n")
    ev = [f"Dialogue: 1,{mr.ass_time(0.25)},{mr.ass_time(2.6)},Hook,,0,0,0,,{{\\fad(120,200)\\t(0,150,\\fscx108\\fscy108)}}{r['hook'].upper()}"]
    for sc in plan:
        if not sc.get("words"):
            continue
        words, tms = sc["line"].upper().replace('"', "").split(), sc["words"]
        chunks, cur = [], []
        for i, w in enumerate(words):
            cur.append(i)
            if len(cur) == 3 or w[-1] in ".?!" or (w[-1] == "," and len(cur) > 1):
                chunks.append(cur)
                cur = []
        if cur:
            chunks.append(cur)
        for ch in chunks:
            for j in ch:
                t0 = sc["start"] + LEAD + tms[j][0]
                nxt = ch[ch.index(j) + 1] if ch.index(j) + 1 < len(ch) else None
                t1 = sc["start"] + LEAD + (tms[nxt][0] if nxt is not None else tms[j][1] + 0.12)
                txt = " ".join(("{\\c&H0000E5FF&\\fscx122\\fscy122\\t(0,90,\\fscx100\\fscy100)}" + words[x].replace(".", "").replace(",", "") + "{\\r}") if x == j
                               else words[x].replace(".", "").replace(",", "") for x in ch)
                ev.append(f"Dialogue: 0,{mr.ass_time(t0)},{mr.ass_time(max(t1, t0 + 0.05))},Cap,,0,0,0,,{txt}")
    return head + "\n".join(ev) + "\n"


def word_times(d: Path, sc, stt):
    """Per-word (start, end) inside the narration file, from Whisper when its word count matches the script, else spread by length."""
    cache = d / "audio" / f"s{sc['i']}.words.json"
    if cache.exists():
        return json.loads(cache.read_text())
    n = len(sc["line"].split())
    _, w = stt.words(d / "audio" / f"s{sc['i']}.wav")
    if len(w) == n:
        out = [(x.start, x.end) for x in w]
    else:
        a, b = (w[0].start, w[-1].end) if w else (0.0, sc["a"])
        ln = [len(x) for x in sc["line"].split()]
        edges = np.concatenate([[0], np.cumsum(ln)]) / sum(ln)
        out = [(a + (b - a) * edges[i], a + (b - a) * edges[i + 1]) for i in range(n)]
        print(f"  s{sc['i']}: whisper heard {len(w)} words for {n}: spread by length")
    cache.write_text(json.dumps(out))
    return out


# ------------------------------------------------------------------ the whole reel
def build(r, scale, allow_stills):
    d = mr.rdir(r)
    W, H, k = int(1080 * scale), int(1920 * scale), scale
    from engine.narration.runtime.audio import WhisperStt
    stt = WhisperStt()
    mfiles = sorted((d / "audio" / "music").glob("music_*.wav"))
    music = mr.read_mono(mfiles[-1]) if mfiles else None
    period, phase = beat_grid(music, r["bpm"]) if music is not None else (60 / r["bpm"], 0.0)
    grid = period / 2
    print(f"beat grid: {60 / period:.1f} bpm (asked {r['bpm']}), first beat at {phase:.2f}s, cuts on every {grid:.3f}s")

    plan, t = [], 0.0
    for i, s in enumerate(r["scenes"], 1):
        sc = dict(s, i=i)
        sc.setdefault("cam", [("push", 0.0, (0.5, 0.5))])
        if s.get("line"):
            v = mr.read_mono(d / "audio" / f"s{i}.wav")
            loud = np.where(np.abs(v) > 0.02 * np.abs(v).max())[0]  # Qwen3-TTS leaves up to 1 s of silence before a line: cut it so the cut and the voice land together
            i0, i1 = max(0, loud[0] - int(0.05 * SR)), min(v.size, loud[-1] + int(0.08 * SR))
            v = v[i0:i1]
            sc["voice"] = v / (np.abs(v).max() + 1e-9) * 0.85
            sc["a"], sc["trim"] = v.size / SR, i0 / SR
            sc["d"] = max(2.1, np.ceil((sc["a"] + LEAD + TAIL) / grid - 1e-6) * grid)
            sc["words"] = [(max(0.0, a - sc["trim"]), max(0.0, b - sc["trim"])) for a, b in word_times(d, sc, stt)]
        else:
            sc["d"] = max(grid, round(s["dur"] / grid) * grid)
        sc["start"] = t
        t += sc["d"]
        plan.append(sc)
    total = t
    print(f"{len(plan)} shots, {sum(len(s['cam']) for s in plan)} camera setups, total {total:.1f}s")

    # ---- audio
    n = int((total + 1.0) * SR)
    mix = np.zeros((n, 2), np.float32)
    voice = np.zeros(n, np.float32)
    drop = np.ones(n, np.float32)
    for sc in plan:
        i0 = int(sc["start"] * SR)
        if "voice" in sc:
            o = i0 + int(LEAD * SR)
            voice[o:o + sc["voice"].size] += sc["voice"][: n - o]
        if sc.get("music") == "drop":
            drop[i0 + int(0.1 * SR): int((sc["start"] + sc["d"]) * SR)] = 0.0
    voice = _hp(voice, 70)
    voice = np.tanh(1.8 * voice) / np.tanh(1.8) * 0.95  # gentle compression so every line sits at the same level
    mix += voice[:, None]
    if music is not None:
        m = music[int(phase * SR):]
        m = np.pad(m, (0, max(0, n - m.size)))[:n]
        sm = lambda x, sec: np.convolve(x, np.ones(int(sec * SR)) / int(sec * SR), mode="same")
        duck = np.clip(sm(np.abs(voice), 0.2) / 0.03, 0, 1)
        gain = (0.34 - 0.2 * sm(duck, 0.25)) * (0.12 + 0.88 * sm(drop, 0.15))
        fade = np.clip((n - np.arange(n)) / (1.5 * SR), 0, 1)
        mix += (m * gain * fade)[:, None]

    def put(name, at, g=1.0):
        x = sfx(name) * g
        i = max(0, int(at * SR))
        mix[i:i + len(x)] += x[: n - i]

    events = []
    for j, sc in enumerate(plan):
        for name, at in sc.get("sfx", []):
            events.append((name, sc["start"] + at, 0.9))
        if j and sc["tr"] in TR_SFX:
            nm, off = TR_SFX[sc["tr"]]
            events.append((nm, sc["start"] + off, 0.9 if nm != "boom" else 0.75))
        for mv, fr, _ in sc["cam"]:
            if mv in ("punch", "punchout"):
                events.append(("thud", sc["start"] + fr * sc["d"], 0.8))
    for name, at, g in events:
        put(name, at, g)
    mix = np.clip(mix * 0.9, -1, 1)
    sf.write(str(d / "mix.wav"), mix, SR, subtype="PCM_16")

    # ---- captions + timeline report
    (d / "captions.ass").write_text(build_ass(r, plan), encoding="utf-8")
    (d / "timeline.json").write_text(json.dumps([dict(i=s["i"], start=round(s["start"], 3), d=round(s["d"], 3), tr=s["tr"], grade=s["grade"],
                                                    cam=[c[0] for c in s["cam"]], line=s.get("line", "")) for s in plan], indent=1), encoding="utf-8")

    # ---- video
    final = d / (f"{r['slug']}.mp4" if scale == 1 else f"{r['slug']}_preview.mp4")
    ff = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                           "-i", "mix.wav", "-vf", f"subtitles=captions.ass{'' if scale == 1 else ',scale=' + str(W) + ':' + str(H)}",
                           "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:v", "libx264", "-crf", "17", "-preset", "medium", "-pix_fmt", "yuv420p",
                           "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.3f}", "-movflags", "+faststart", final.name], stdin=subprocess.PIPE, cwd=d)
    srcs: dict = {}

    def src(j):
        if j not in srcs:
            srcs[j] = Source(plan[j], d, allow_stills)
            for old in [q for q in srcs if q < j - 1]:
                del srcs[old]
        return srcs[j]

    for fi in range(round(total * FPS)):
        T = fi / FPS
        j = max(q for q in range(len(plan)) if plan[q]["start"] <= T + 1e-9)
        frame, win = None, None
        for q in (j, j + 1):  # the cut into scene q may overlap this frame
            if q < len(plan) and plan[q]["tr"] in TR_WINDOW:
                pre, post = TR_WINDOW[plan[q]["tr"]]
                if plan[q]["start"] - pre <= T < plan[q]["start"] + post:
                    win = q
        if win is not None:
            sc = plan[win]
            b = render_scene(sc, src(win), T - sc["start"], W, H, k)
            a = render_scene(plan[win - 1], src(win - 1), T - plan[win - 1]["start"], W, H, k) if win else None
            color = (60, 60, 255) if sc["grade"] == "alarm" else (255, 255, 255)
            frame = transition(sc["tr"], a, b, T, sc["start"], W, H, fi, color)
        else:
            frame = render_scene(plan[j], src(j), T - plan[j]["start"], W, H, k)
        grain = np.random.default_rng(fi % 5).integers(0, 255, (H // 2, W // 2, 1), dtype=np.uint8)
        frame = cv2.addWeighted(frame, 0.95, cv2.resize(cv2.merge([grain] * 3), (W, H), interpolation=cv2.INTER_NEAREST), 0.05, -6)
        ff.stdin.write(frame.tobytes())
    ff.stdin.close()
    ff.wait()
    print(f"wrote {final} ({total:.1f}s)")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("reels", nargs="*")
    ap.add_argument("--scale", type=float, default=1.0, help="preview at a lower resolution, e.g. 0.5")
    ap.add_argument("--stills", action="store_true", help="use the panels where an H3 clip is missing (preview only)")
    a = ap.parse_args()
    for reel in mr.pick(a.reels):
        build(reel, a.scale, a.stills)
