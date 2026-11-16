"""Headless-Chromium checks of the ChronoFlow Audio page against an isolated test engine (not part of the pytest suite).

Start the engine from the worktree with a throwaway data folder, then run:

    set PANELFLOW_APP_DATA=<tmp> PANELFLOW_ALLOW_INSECURE_LOCAL_API=1 ...
    python -m uvicorn engine.api.app:app --port 8767
    python tests/ui/audio_page_check.py <task> [shots_dir]      # task: 4 | 5 | 6 | 7 | 8 | all

Each check drives the real page, asserts, and saves a screenshot you should open and look at.
"""
import json
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8767"
SHOTS = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(tempfile.gettempdir()) / "audio_ui_shots"
SHOTS.mkdir(parents=True, exist_ok=True)


def make_video(path: Path, seconds_per_segment=2, segments=4):
    """A small video with hard cuts (black/white) and a tone: cuts at 2, 4, 6 s."""
    cmd = ["ffmpeg", "-v", "error", "-y"]
    for i in range(segments):
        cmd += ["-f", "lavfi", "-i", f"color=c={'black' if i % 2 == 0 else 'white'}:s=640x360:d={seconds_per_segment}:r=24"]
    cmd += ["-f", "lavfi", "-i", f"sine=frequency=300:duration={seconds_per_segment * segments}"]
    concat = "".join(f"[{i}:v]" for i in range(segments)) + f"concat=n={segments}:v=1:a=0[v]"
    cmd += ["-filter_complex", concat, "-map", "[v]", "-map", f"{segments}:a", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)]
    subprocess.run(cmd, check=True)
    return path


def api(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


class Session:
    def __init__(self, pw, width=1600, height=900):
        self.browser = pw.chromium.launch(headless=True, args=["--autoplay-policy=no-user-gesture-required"])
        self.page = self.browser.new_page(viewport={"width": width, "height": height})
        self.errors = []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.on("console", lambda m: self.errors.append(f"console.error: {m.text}") if m.type == "error" else None)
        self.page.goto(f"{BASE}/chronoflow/ui", wait_until="networkidle")
        self.page.wait_for_function("window.NLEAudio && window.AudioModel")
        self.page.evaluate("switchResolvePage('audio')")
        self.page.wait_for_timeout(500)

    def shot(self, name):
        p = SHOTS / f"{name}.png"
        self.page.screenshot(path=str(p))
        print("screenshot:", p)

    def ev(self, js, arg=None):
        return self.page.evaluate(js, arg)

    def finish(self):
        # the engine returns 404 for the favicon etc.; only script errors and our own API failures matter
        bad = [e for e in self.errors if "favicon" not in e and "404" not in e]
        assert not bad, f"console/page errors: {bad[:5]}"
        self.browser.close()


def open_video(s, video):
    s.ev("p => NLEAudio.openVideo(p)", str(video))
    s.page.wait_for_function("NLEAudio.state.plan && NLEAudio.state.plan.id", timeout=30000)
    s.page.wait_for_timeout(300)


# ---------------------------------------------------------------- task 4: page shell, plan open, cue list
def check_4(tmp):
    video = make_video(tmp / "cuts.mp4")
    with sync_playwright() as pw:
        s = Session(pw)
        assert s.ev("document.getElementById('cfWorkspace').dataset.page") == "audio"
        assert s.ev("[...document.querySelectorAll('.resolve-rail-item')].map(b => b.id)") == ["railMedia", "railEdit", "railFusion", "railColor", "railAudio", "railDeliver"]
        assert "active" in s.ev("document.getElementById('railAudio').className")
        box = lambda sel: s.ev("sel => { const r = document.querySelector(sel).getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; }", sel)
        left, mon, insp, panel = box("#audioPlanPane"), box("#audioMonitor"), box("#audioInspector"), box("#audioPanel")
        assert all(b[2] > 100 and b[3] > 60 for b in (left, mon, insp, panel)), (left, mon, insp, panel)
        assert left[0] < mon[0] < insp[0] and panel[1] > mon[1] + mon[3] - 5, "left | centre | right, lanes underneath"
        assert s.ev("getComputedStyle(document.querySelector('#nleTimeline')).display") == "none"
        assert "Open a finished video" in s.ev("document.querySelector('.au-cues').innerText")
        open_video(s, video)
        plan = s.ev("NLEAudio.state.plan")
        assert plan["fps"] == 24 and abs(plan["duration"] - 8) < 0.2 and plan["cues"] == []
        assert "No cues yet" in s.ev("document.querySelector('.au-cues').innerText")
        s.page.click("#auSpot")
        s.page.wait_for_function("document.querySelectorAll('.au-cue').length === 4", timeout=60000)
        rows = s.ev("[...document.querySelectorAll('.au-cue')].map(r => r.innerText.replace(/\\s+/g, ' '))")
        assert any("draft" in r for r in rows) and any("00:00:02:00" in r for r in rows), rows
        assert "3 picture cut" in s.ev("document.querySelector('.au-status').innerText")
        s.page.select_option(".audio-plan-pane select >> nth=1", "ask")
        s.page.wait_for_function("NLEAudio.state.plan.mode === 'ask'")
        assert api("GET", f"/api/audio/studio/plans/{plan['id']}")["mode"] == "ask", "the mode is saved on the server"
        s.page.click(".au-cue >> nth=0")
        assert s.ev("NLEAudio.state.sel") is not None and "sel" in s.ev("document.querySelector('.au-cue.sel').className")
        s.page.evaluate("switchResolvePage('edit')")
        assert s.ev("getComputedStyle(document.querySelector('#audioPlanPane')).display") == "none", "leaving the page hides it"
        s.page.evaluate("switchResolvePage('audio')")
        s.page.wait_for_timeout(300)
        assert s.ev("NLEAudio.state.plan && NLEAudio.state.plan.id") == plan["id"], "the page remembers the open plan"
        s.shot("task4_shell")
        s.finish()
    print("task 4 OK")


CHECKS = {"4": check_4}

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    tmp = Path(tempfile.mkdtemp(prefix="audio_ui_"))
    for k, fn in CHECKS.items():
        if which in ("all", k):
            fn(tmp)
