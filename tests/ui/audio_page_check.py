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


# ---------------------------------------------------------------- task 5: inspector and cue actions
def server_plan(s):
    return api("GET", f"/api/audio/studio/plans/{s.ev('NLEAudio.state.plan.id')}")


def cue_on_server(s, cid):
    return next(c for c in server_plan(s)["cues"] if c["id"] == cid)


def check_5(tmp):
    video = make_video(tmp / "cuts5.mp4")
    with sync_playwright() as pw:
        s = Session(pw)
        open_video(s, video)
        s.page.click("#auSpot")
        s.page.wait_for_function("document.querySelectorAll('.au-cue').length === 4", timeout=60000)
        s.page.click(".au-cue[data-cue=cut_01]")
        assert "Select a cue" not in s.ev("document.getElementById('audioInspector').innerText")
        s.page.fill(".au-intent", "heavy whoosh swish")
        s.page.press(".au-intent", "Tab")
        s.page.wait_for_function("NLEAudio.state.plan.cues.find(c => c.id === 'cut_01').intent === 'heavy whoosh swish'")
        assert cue_on_server(s, "cut_01")["intent"] == "heavy whoosh swish", "the edit is saved on the server"
        before = cue_on_server(s, "cut_01")["hit_t"]
        s.page.click(".au-nudge .dl-btn >> nth=1")
        s.page.wait_for_function("b => NLEAudio.state.plan.cues.find(c => c.id === 'cut_01').hit_t > b + 0.01", arg=before)
        assert abs(cue_on_server(s, "cut_01")["hit_t"] - (before + 1 / 24)) < 1e-3, "one frame later"
        s.page.click("#auAddCue")
        s.page.wait_for_function("NLEAudio.state.plan.cues.length === 5")
        new_id = s.ev("NLEAudio.state.sel")
        assert new_id == "cue_01" and "whoosh swish" in s.ev("document.querySelector('.au-intent').value")
        s.page.click("#auDeleteCue")
        s.page.wait_for_function("NLEAudio.state.plan.cues.length === 4")
        assert all(c["id"] != new_id for c in server_plan(s)["cues"])
        # source a whoosh cue (Openverse CC0 when reachable, else the code-made effect)
        s.page.click(".au-cue[data-cue=cut_01]")
        s.page.click("#auSourceCue")
        s.page.wait_for_function("NLEAudio.state.plan.cues.find(c => c.id === 'cut_01').status === 'ready'", timeout=120000)
        txt = s.ev("document.getElementById('audioInspector').innerText")
        assert "Licence:" in txt and "ready" in txt, txt
        shot_ready = True
        # a cue nothing can serve fails with its reason, shown in the inspector
        s.page.click("#auAddCue")
        s.page.wait_for_function("NLEAudio.state.plan.cues.length === 5")
        s.page.fill(".au-intent", "zzzqqxxyy")
        s.page.press(".au-intent", "Tab")
        s.page.fill("input[list=auKinds]", "zzzqq")
        s.page.press("input[list=auKinds]", "Tab")
        s.page.wait_for_function("NLEAudio.state.plan.cues.find(c => c.id === 'cue_01').kind === 'zzzqq'")
        s.page.click("#auSourceCue")
        s.page.wait_for_function("NLEAudio.state.plan.cues.find(c => c.id === 'cue_01').status === 'failed'", timeout=120000)
        assert "ace-step" in s.ev("document.querySelector('#audioInspector .dl-error').innerText").lower()
        # Ask me: candidates appear, Pick makes the cue ready
        s.page.click(".au-cue[data-cue=cut_03]")
        s.page.select_option("#audioInspector select >> nth=1", "ask") if False else None
        s.ev("NLEAudio.edit({cues: [{id: 'cut_03', mode: 'ask'}]})")
        s.page.wait_for_function("NLEAudio.state.plan.cues.find(c => c.id === 'cut_03').mode === 'ask'")
        s.page.click("#auSourceCue")
        s.page.wait_for_function("NLEAudio.state.plan.cues.find(c => c.id === 'cut_03').status === 'needs_pick'", timeout=120000)
        assert s.ev("document.querySelectorAll('.au-cand').length") >= 1
        s.shot("task5_ask")
        s.page.click(".au-cand .dl-btn >> nth=0")
        s.page.wait_for_function("NLEAudio.state.plan.cues.find(c => c.id === 'cut_03').status === 'ready'")
        s.page.click(".au-cue[data-cue=cut_01]")
        s.shot("task5_ready")
        s.finish()
    print("task 5 OK")


# ---------------------------------------------------------------- task 6: lanes
def check_6(tmp):
    video = make_video(tmp / "cuts6.mp4")
    with sync_playwright() as pw:
        s = Session(pw)
        open_video(s, video)
        s.page.click("#auSpot")
        s.page.wait_for_function("document.querySelectorAll('.au-cue').length === 4", timeout=60000)
        s.page.click("#auSourceAll")
        s.page.wait_for_function("NLEAudio.state.plan.cues.every(c => c.status !== 'draft')", timeout=240000)
        s.page.wait_for_function("NLEAudio.state.plan.cues.filter(c => c.status === 'ready').every(c => (NLEAudio.peaks[c.chosen_take] || []).length > 0)", timeout=30000)
        s.page.wait_for_timeout(300)
        assert s.ev("document.querySelectorAll('.au-cv').length") == 6, "ruler + five lanes"
        w = s.ev("document.querySelector('.au-rulercv').clientWidth")
        assert w > 500, w
        view = s.ev("NLEAudio.view")
        assert view["t0"] == 0 and abs(view["pps"] * 8 - w) < 2, ("fitted to the video", view, w)
        cue = s.ev("NLEAudio.state.plan.cues.find(c => c.id === 'cut_01')")
        assert cue["status"] == "ready", cue
        lane_box = s.ev("(() => { const r = document.querySelector('.au-cv[data-lane=sfx]').getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; })()")
        pixel = lambda lane, x, y: s.ev("([lane, x, y]) => { const cv = document.querySelector(`.au-cv[data-lane=${lane}]`); return [...cv.getContext('2d').getImageData(x * (cv.width / cv.clientWidth), y, 1, 1).data]; }", [lane, x, y])
        hx = round(cue["hit_t"] * view["pps"])
        r, g, b, a = pixel("sfx", hx, 26)
        assert r > 230 and g > 180 and b < 140, ("the yellow hit marker is drawn on the hit", (r, g, b))
        s.shot("task6_lanes")
        # clicking the ruler seeks the video and moves the playhead
        s.page.mouse.click(lane_box[0] + 3.0 * view["pps"], lane_box[1] - 60)
        t = s.ev("document.querySelector('.au-video').currentTime")
        assert False if abs(t - 3.0) > 0.35 else True, t
        # drag the block one second to the right: the hit moves by 1.0 s, snapped to the frame, and is saved
        x0 = lane_box[0] + cue["hit_t"] * view["pps"] + 6
        y0 = lane_box[1] + 26
        s.page.mouse.move(x0, y0)
        s.page.mouse.down()
        s.page.mouse.move(x0 + 0.5 * view["pps"], y0, steps=4)
        s.page.mouse.move(x0 + 1.0 * view["pps"], y0, steps=4)
        s.page.mouse.up()
        s.page.wait_for_function("NLEAudio.state.plan.cues.find(c => c.id === 'cut_01').hit_t > 2.9", timeout=15000)
        moved = cue_on_server(s, "cut_01")["hit_t"]
        assert abs(moved - 3.0) < 1 / 24 + 1e-6 and abs(moved * 24 - round(moved * 24)) < 1e-6, moved
        assert s.ev("NLEAudio.state.sel") == "cut_01"
        # keyboard: one frame right
        s.page.keyboard.press("ArrowRight")
        s.page.wait_for_function("b => NLEAudio.state.plan.cues.find(c => c.id === 'cut_01').hit_t > b + 0.01", arg=moved, timeout=15000)
        assert abs(cue_on_server(s, "cut_01")["hit_t"] - (moved + 1 / 24)) < 1e-3
        # wheel zoom keeps the time under the cursor
        cx = lane_box[0] + 4.0 * view["pps"]
        before = s.ev("(x => NLEAudio.view.t0 + x / NLEAudio.view.pps)(" + str(4.0 * view["pps"]) + ")")
        s.page.mouse.move(cx, lane_box[1] + 20)
        s.page.mouse.wheel(0, -300)
        s.page.wait_for_timeout(200)
        v2 = s.ev("NLEAudio.view")
        assert v2["pps"] > view["pps"] * 1.4, v2
        under = v2["t0"] + (cx - lane_box[0]) / v2["pps"]
        assert abs(under - before) < 0.05, (under, before)
        s.shot("task6_zoomed")
        s.finish()
    print("task 6 OK")


# ---------------------------------------------------------------- task 7: playback, mixer, meters
def check_7(tmp):
    video = make_video(tmp / "cuts7.mp4")
    with sync_playwright() as pw:
        s = Session(pw)
        open_video(s, video)
        s.page.click("#auSpot")
        s.page.wait_for_function("document.querySelectorAll('.au-cue').length === 4", timeout=60000)
        s.page.click("#auSourceAll")
        s.page.wait_for_function("NLEAudio.state.plan.cues.every(c => c.status !== 'draft')", timeout=240000)
        assert s.ev("document.querySelector('.au-pvstate').innerText") == "not rendered"
        s.page.click("#auPlay")
        assert "Preview mix" in s.ev("document.querySelector('.au-status').innerText"), "Play before rendering tells you what to do"
        s.page.click("#auPreview")
        s.page.wait_for_function("document.querySelector('.au-pvstate').innerText === 'up to date'", timeout=240000)
        s.page.wait_for_timeout(400)
        dx = s.ev("(() => { const cv = document.querySelector('.au-cv[data-lane=dialogue]'); const g = cv.getContext('2d'); const d = g.getImageData(0, 0, cv.width, cv.height).data; let n = 0; for (let i = 0; i < d.length; i += 4) if (d[i + 1] > 120 && d[i] < 110 && d[i + 2] > 100 && d[i + 2] < 190) n++; return n; })()")
        assert dx > 200, f"the dialogue waveform is drawn in the DX lane ({dx} green pixels)"
        s.page.click("#auPlay")
        s.page.wait_for_function("NLEAudio.mixer.playing === true", timeout=15000)
        s.page.wait_for_timeout(2200)
        sync = s.ev("({v: document.querySelector('.au-video').currentTime, a: Object.values(NLEAudio.mixer.els).map(e => e.currentTime), state: NLEAudio.mixer.ctx.state})")
        assert sync["state"] == "running" and sync["v"] > 1.5, sync
        assert all(abs(x - sync["v"]) < 0.15 for x in sync["a"]), ("stems follow the video", sync)
        lvl = s.ev("NLEAudio.mixer.lvl")
        assert lvl.get("dialogue", -90) > -60 and lvl.get("master", -90) > -60, ("the meters move", lvl)
        s.shot("task7_playing")
        # mute / solo act on the gain nodes immediately
        s.page.click(".au-strip[data-stem=music] .au-ms >> nth=0")
        assert s.ev("NLEAudio.mixer.nodes.music.gain.gain.value") == 0 and s.ev("NLEAudio.mixer.nodes.dialogue.gain.gain.value") > 0.9
        s.page.click(".au-strip[data-stem=music] .au-ms >> nth=0")
        s.page.click(".au-strip[data-stem=dialogue] .au-ms.solo")
        assert s.ev("NLEAudio.mixer.nodes.effects.gain.gain.value") == 0 and s.ev("NLEAudio.mixer.nodes.dialogue.gain.gain.value") > 0.9
        s.page.click(".au-strip[data-stem=dialogue] .au-ms.solo")
        # a fader move is a live trim and is saved on the plan; the preview then reads 'out of date'
        s.ev("(() => { const f = document.querySelector('.au-strip[data-stem=music] .au-fader'); f.value = -6; f.dispatchEvent(new Event('input')); })()")
        assert abs(s.ev("NLEAudio.mixer.nodes.music.gain.gain.value") - 0.501) < 0.01
        s.ev("document.querySelector('.au-strip[data-stem=music] .au-fader').dispatchEvent(new Event('change'))")
        s.page.wait_for_function("NLEAudio.state.plan.tracks.find(t => t.id === 'music').gain_db === -6", timeout=15000)
        assert server_plan(s)["tracks"][1]["gain_db"] == -6
        s.page.wait_for_function("document.querySelector('.au-pvstate').innerText === 'out of date'", timeout=15000)
        assert abs(s.ev("NLEAudio.mixer.nodes.music.gain.gain.value") - 0.501) < 0.01, "the trim stays after the save"
        # seeking while playing resyncs the stems
        box = s.ev("(() => { const r = document.querySelector('.au-rulercv').getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; })()")
        s.page.mouse.click(box[0] + box[2] * 0.75, box[1] + 10)
        s.page.wait_for_timeout(700)
        sync = s.ev("({v: document.querySelector('.au-video').currentTime, a: Object.values(NLEAudio.mixer.els).map(e => e.currentTime)})")
        assert 5.5 < sync["v"] < 7.5 and all(abs(x - sync["v"]) < 0.25 for x in sync["a"]), sync
        s.page.click("#auPlay")
        s.page.wait_for_function("NLEAudio.mixer.playing === false")
        s.page.click("#auMaster")
        s.page.wait_for_function("document.querySelector('.au-master-info').innerText.includes('LUFS')", timeout=240000)
        lufs = float(s.ev("document.querySelector('.au-master-info').innerText").split()[0])
        assert abs(lufs + 14) < 1.0, lufs
        s.page.click("#auExport")
        s.page.wait_for_function("document.querySelector('.au-status').innerText.startsWith('Exported')", timeout=300000)
        s.shot("task7_mixer")
        s.finish()
    print("task 7 OK")


CHECKS = {"4": check_4, "5": check_5, "6": check_6, "7": check_7}

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    tmp = Path(tempfile.mkdtemp(prefix="audio_ui_"))
    for k, fn in CHECKS.items():
        if which in ("all", k):
            fn(tmp)
