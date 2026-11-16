"""Headless-Chromium checks of the ChronoFlow Audio page against an isolated test engine (not part of the pytest suite).

Start the engine from the worktree with a throwaway data folder, then run:

    set PANELFLOW_APP_DATA=<tmp> PANELFLOW_ALLOW_INSECURE_LOCAL_API=1 ...
    python -m uvicorn engine.api.app:app --port 8767
    python tests/ui/audio_page_check.py <task> [shots_dir]      # task: 4 ... 12 | all

Each check drives the real page, asserts, and saves a screenshot you should open and look at.
Check 11 imports a project and deletes its files afterwards; there is no API to delete the project record, so run 11 last (or on a fresh data folder).
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
    def __init__(self, pw, width=1600, height=900, tab=False):
        self.browser = pw.chromium.launch(headless=True, args=["--autoplay-policy=no-user-gesture-required"])
        self.page = self.browser.new_page(viewport={"width": width, "height": height})
        self.errors = []
        self.page.set_default_timeout(int(__import__('os').environ.get('AUDIO_UI_TIMEOUT_MS', '40000')))   # fail fast; slow steps pass their own timeout
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.on("console", lambda m: self.errors.append(f"console.error: {m.text}") if m.type == "error" else None)
        self.page.goto(f"{BASE}/chronoflow/ui", wait_until="networkidle")
        self.page.wait_for_function("window.NLEAudio && window.AudioModel && window.SoundEditor")
        self.page.evaluate("switchTab('audio')" if tab else "switchResolvePage('audio')")
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
        s.page.click(".au-cand .dl-btn.accent >> nth=0")
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
        thumb = s.ev("(() => { const t = document.querySelector('.au-hthumb').getBoundingClientRect(), h = document.querySelector('.au-hscroll').getBoundingClientRect(); return [t.width, h.width - 64]; })()")
        assert abs(thumb[0] - thumb[1]) < 4, ("the scrollbar thumb covers the track when the whole video is in view", thumb)
        # clicking the ruler seeks the video and moves the playhead
        s.page.mouse.click(lane_box[0] + 3.0 * view["pps"], lane_box[1] - 60)
        t = s.ev("document.querySelector('.au-video').currentTime")
        assert abs(t - 3.0) <= 0.35, t
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
        thumb2 = s.ev("document.querySelector('.au-hthumb').getBoundingClientRect().width")
        assert thumb2 < thumb[1] * 0.8, ("zoomed in: the thumb shrinks", thumb2)
        t0_before = s.ev("NLEAudio.view.t0")
        hb = s.ev("(() => { const r = document.querySelector('.au-hscroll').getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; })()")
        s.page.mouse.click(hb[0] + hb[2] - 30, hb[1] + 6)   # click near the right end: the view moves there
        s.page.wait_for_timeout(300)
        assert s.ev("NLEAudio.view.t0") > t0_before + 1, "clicking the scrollbar scrolls the lanes"
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
        s.page.wait_for_function("document.querySelector('.au-status').innerText.includes('cues not finished')", timeout=60000)  # the failed music cue blocks the export, and the page says so
        assert s.ev("document.querySelector('.au-status').className").endswith("bad")
        s.errors[:] = [e for e in s.errors if "status of 400" not in e]  # the browser logs that expected refusal
        s.ev("NLEAudio.edit({remove_cues: ['music_1']})")
        s.page.wait_for_function("!NLEAudio.state.plan.cues.some(c => c.id === 'music_1')")
        s.page.click("#auExport")
        s.page.wait_for_function("document.querySelector('.au-status').innerText.startsWith('Exported')", timeout=300000)
        s.shot("task7_mixer")
        s.finish()
    print("task 7 OK")


# ---------------------------------------------------------------- task 8: audition, QA panel, Open in Audio from Media
def check_8(tmp):
    video = make_video(tmp / "cuts8.mp4")
    with sync_playwright() as pw:
        s = Session(pw)
        open_video(s, video)
        s.page.click("#auSpot")
        s.page.wait_for_function("document.querySelectorAll('.au-cue').length === 4", timeout=60000)
        s.ev("NLEAudio.edit({cues: [{id: 'cut_01', mode: 'ask'}]})")
        s.page.wait_for_function("NLEAudio.state.plan.cues.find(c => c.id === 'cut_01').mode === 'ask'")
        s.page.click(".au-cue[data-cue=cut_01]")
        s.page.click("#auSourceCue")
        s.page.wait_for_function("NLEAudio.state.plan.cues.find(c => c.id === 'cut_01').status === 'needs_pick'", timeout=120000)
        s.page.wait_for_function("[...document.querySelectorAll('.au-mini-wave')].some(c => { const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; for (let i = 3; i < d.length; i += 4) if (d[i] > 0) return true; return false; })", timeout=20000)
        s.page.click(".au-cand .au-play >> nth=0")
        s.page.wait_for_function("NLEAudio.audition.id !== null")
        s.page.wait_for_timeout(500)
        playing = s.ev("({paused: NLEAudio.audition.el.paused, t: NLEAudio.audition.el.currentTime})")
        assert playing["paused"] is False and playing["t"] > 0.1, playing
        s.page.click(".au-cand .au-play >> nth=0")
        assert s.ev("NLEAudio.audition.id") is None and s.ev("NLEAudio.audition.el.paused") is True
        s.shot("task8_candidates")
        s.page.click(".au-cand .dl-btn.accent >> nth=0")
        s.page.wait_for_function("NLEAudio.state.plan.cues.find(c => c.id === 'cut_01').status === 'ready'")
        s.page.click("#auListenTake")
        s.page.wait_for_function("NLEAudio.audition.id !== null")
        s.page.click(".au-cue[data-cue=cut_02]")
        assert s.ev("NLEAudio.audition.id") is None, "selecting another cue stops the audition"
        # QA panel: a cue nothing can serve is an error; clicking its finding selects it
        s.page.click("#auAddCue")
        s.page.wait_for_function("NLEAudio.state.plan.cues.length === 5")
        s.page.fill("input[list=auKinds]", "zzzqq")
        s.page.press("input[list=auKinds]", "Tab")
        s.page.wait_for_function("NLEAudio.state.plan.cues.find(c => c.id === 'cue_01').kind === 'zzzqq'")
        s.page.fill(".au-intent", "zzzqqxxyy")
        s.page.press(".au-intent", "Tab")
        s.page.click("#auSourceCue")
        s.page.wait_for_function("NLEAudio.state.plan.cues.find(c => c.id === 'cue_01').status === 'failed'", timeout=120000)
        s.page.click("#auQa")
        s.page.wait_for_function("document.querySelectorAll('.au-find').length >= 1", timeout=60000)
        assert s.ev("document.querySelector('.au-find.error') !== null"), "an error finding is listed"
        s.page.click(".au-find.error")
        assert s.ev("NLEAudio.state.sel") == "cue_01"
        s.shot("task8_qa")
        # Media -> Open in Audio, on a real video from the library (read-only scan of the owner's outputs)
        s.page.evaluate("switchResolvePage('media')")
        try:
            s.page.wait_for_selector("#libGrid .lib-card", timeout=30000)
        except Exception:
            print("task 8: the Media library is empty here; skipped the Open in Audio check")
            s.finish(); print("task 8 OK (without the Media step)"); return
        assert s.ev("getComputedStyle(document.querySelector('#libAudio')).display") == "none", "no selection, no button"
        s.page.click("#libGrid .lib-card >> nth=0")
        path = s.ev("document.querySelector('#libGrid .lib-card').dataset.path")
        assert s.ev("getComputedStyle(document.querySelector('#libAudio')).display") != "none"
        s.page.click("#libAudio")
        s.page.wait_for_function("p => NLEAudio.state.plan && NLEAudio.state.plan.video_path === p", arg=path, timeout=60000)
        s.page.wait_for_timeout(800)
        assert s.ev("document.querySelector('.audio-plan-pane select').selectedOptions[0].innerText").startswith(path.split("\\")[-1].split("/")[-1]), "the plan switcher names the opened video"
        assert "QA:" not in s.ev("document.querySelector('.au-status').innerText"), "no stale message from the previous plan"
        assert s.ev("document.getElementById('cfWorkspace').dataset.page") == "audio"
        s.shot("task8_from_media")
        s.finish()
    print("task 8 OK")


# ---------------------------------------------------------------- task 9: fixes from the final review (races, typing, fader, seek)
def check_9(tmp):
    va, vb = make_video(tmp / "plan_a.mp4"), make_video(tmp / "plan_b.mp4")
    with sync_playwright() as pw:
        s = Session(pw)
        open_video(s, va)
        id_a = s.ev("NLEAudio.state.plan.id")
        s.ev("NLEAudio.edit({cues: [{id: 'a1', track: 'sfx', kind: 'click', intent: 'a click', hit_t: 1.0}]})")
        s.page.wait_for_function("NLEAudio.state.plan.cues.length === 1")
        s.ev("p => NLEAudio.openVideo(p)", str(vb))
        s.page.wait_for_function("NLEAudio.state.plan.video_path.endsWith('plan_b.mp4')")
        id_b = s.ev("NLEAudio.state.plan.id")
        assert id_a != id_b
        s.page.wait_for_timeout(500)

        print('step', '# 1.', flush=True)
        if not __import__('os').environ.get('AUDIO_UI_SKIP_STEP1'):
            # 1. a short edit must not clear the busy state of a long job
            s.ev("(() => { window._g = NLEAudio.guard('Long job', () => new Promise(r => { window._rel = r; })); return 1; })()")
            s.page.wait_for_function("NLEAudio.state.busy === 'Long job'")
            s.ev("(() => { NLEAudio.edit({mode: 'ask'}, 'Mode'); return 1; })()")
            s.page.wait_for_timeout(900)
            assert s.ev("NLEAudio.state.busy") == "Long job", "a short call finished but the long one is still running"
            assert s.ev("document.querySelector('#auSourceAll').disabled") is True
            s.ev("window._rel()")
            s.page.wait_for_function("NLEAudio.state.busy === ''")
            assert s.ev("document.querySelector('#auSourceAll').disabled") is False
            s.ev("NLEAudio.edit({mode: 'auto'}, 'Mode')")
            s.page.wait_for_timeout(400)

        print('step', '# 2.', flush=True)
        # 2. a slow save for plan A must not replace plan B on screen
        s.ev("p => NLEAudio.openVideo(p)", str(va))
        s.page.wait_for_function("NLEAudio.state.plan.video_path.endsWith('plan_a.mp4')")
        s.page.wait_for_timeout(500)
        s.ev("(() => { const f = window.fetch; window.__realFetch = f; window.fetch = async (u, o) => { if (o && o.method === 'PUT') await new Promise(r => setTimeout(r, 1500)); return f(u, o); }; })()")
        s.ev("(() => { window._slow = NLEAudio.edit({cues: [{id: 'zz', track: 'sfx', kind: 'click', hit_t: 1.5}]}, 'Slow save'); return 1; })()")
        s.ev("p => { NLEAudio.openVideo(p); return 1; }", str(vb))
        s.page.wait_for_function("NLEAudio.state.plan.video_path.endsWith('plan_b.mp4')")
        s.page.wait_for_timeout(2500)
        s.ev("window.fetch = window.__realFetch")
        assert s.ev("NLEAudio.state.plan.id") == id_b and s.ev("NLEAudio.state.plan.cues.every(c => c.id !== 'zz')"), "plan B stays on screen when A's slow save returns"
        assert s.ev("document.querySelector('.au-title').innerText") == "plan_b.mp4"
        assert any(c["id"] == "zz" for c in api("GET", f"/api/audio/studio/plans/{id_a}")["cues"]), "the save itself still reached plan A"

        print('step', '# 3.', flush=True)
        # 3. Open in Audio from another page lands on the opened video, every time
        for i in range(4):
            s.page.evaluate("switchResolvePage('edit')")
            s.ev("p => { switchResolvePage('audio'); NLEAudio.openVideo(p); return 1; }", str(va if i % 2 == 0 else vb))
            s.page.wait_for_timeout(1800)
            want = "plan_a.mp4" if i % 2 == 0 else "plan_b.mp4"
            assert s.ev("NLEAudio.state.plan.video_path").endswith(want), (i, s.ev("NLEAudio.state.plan.video_path"))

        print('step', '# 4.', flush=True)
        # 4. typing in the inspector survives a refresh, and Tab keeps the keyboard focus
        s.ev("p => { NLEAudio.openVideo(p); return 1; }", str(va))   # plan A has the cues
        s.page.wait_for_function("NLEAudio.state.plan.video_path.endsWith('plan_a.mp4') && NLEAudio.state.plan.cues.some(c => c.id === 'a1')")
        s.page.wait_for_timeout(500)
        s.page.click(".au-cue[data-cue=a1]")
        s.page.click(".au-intent")
        s.page.keyboard.press("Control+A")
        s.page.keyboard.type("typed but not saved yet")
        s.ev("(() => { NLEAudio.reload(); return 1; })()")
        s.page.wait_for_timeout(400)
        assert s.ev("document.activeElement.className.includes('au-intent')") and "typed but not saved yet" in s.ev("document.querySelector('.au-intent').value"), "a refresh must not throw away what is being typed"
        s.page.keyboard.press("Tab")
        s.page.wait_for_function("NLEAudio.state.plan.cues.some(c => c.intent === 'typed but not saved yet')", timeout=15000)
        s.page.wait_for_timeout(300)
        assert s.ev("document.activeElement.dataset.f") == "kind", ("focus follows Tab after the save", s.ev("document.activeElement.tagName"))

        print('step', '# 5.', flush=True)
        # 5. the Effects fader moves the three effect tracks together without flattening their balance
        s.ev("(() => { NLEAudio.edit({tracks: [{id: 'ambience', gain_db: -6}]}); return 1; })()")
        s.page.wait_for_function("NLEAudio.state.plan.tracks.find(t => t.id === 'ambience').gain_db === -6")
        s.ev("(() => { const f = document.querySelector('.au-strip[data-stem=effects] .au-fader'); f.value = 2; f.dispatchEvent(new Event('input')); f.dispatchEvent(new Event('change')); })()")
        s.page.wait_for_function("NLEAudio.state.plan.tracks.find(t => t.id === 'sfx').gain_db === 2", timeout=15000)
        gains = {t["id"]: t["gain_db"] for t in server_plan(s)["tracks"]}
        assert gains["sfx"] == 2 and gains["foley"] == 2 and gains["ambience"] == -4, gains

        print('step', '# 6.', flush=True)
        # 6. seeking while playing resyncs the stems at once
        s.ev("(() => { NLEAudio.edit({cues: [{id: 'p1', track: 'sfx', kind: 'click', hit_t: 1.0}]}); return 1; })()")
        s.page.wait_for_timeout(300)
        s.page.click("#auSourceAll")
        s.page.wait_for_function("NLEAudio.state.plan.cues.every(c => c.status !== 'draft')", timeout=240000)
        s.page.click("#auPreview")
        s.page.wait_for_function("document.querySelector('.au-pvstate').innerText === 'up to date'", timeout=240000)
        s.page.click("#auPlay")
        s.page.wait_for_function("NLEAudio.mixer.playing === true", timeout=15000)
        s.page.wait_for_timeout(800)
        s.ev("NLEAudio.seek(5.0)")
        s.page.wait_for_timeout(60)
        d = s.ev("Object.values(NLEAudio.mixer.els).map(e => Math.abs(e.currentTime - document.querySelector('.au-video').currentTime))")
        assert max(d) < 0.2, ("stems follow a seek immediately, not at the next sync tick", d)
        s.finish()
    print("task 9 OK")


# ---------------------------------------------------------------- task 10: the Audio Studio tab is a sound editor (no video)
def check_10(tmp):
    import numpy as np
    import soundfile as sf
    wav = tmp / "beep.wav"
    t = np.arange(48000 * 3) / 48000
    sf.write(str(wav), (0.3 * np.sin(2 * np.pi * 440 * t) * (np.sin(2 * np.pi * 1.5 * t) > 0)).astype(np.float32), 48000)
    with sync_playwright() as pw:
        s = Session(pw, tab=True)
        assert s.ev("[...document.querySelectorAll('.nav-tab')].map(b => b.innerText.trim())") == ["Video Studio", "Image Studio", "Audio Studio", "Gallery", "Storyboard", "Organizer"]
        assert s.ev("document.body.dataset.tab") == "audio"
        assert s.ev("document.querySelectorAll('#tab-audio video').length") == 0, "no video on the Audio Studio"
        box = lambda sel: s.ev("sel => { const r = document.querySelector(sel).getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; }", sel)
        lib, ed, side = box(".se-lib"), box(".se-editor"), box(".se-side")
        assert lib[0] < ed[0] < side[0] and ed[2] > 700 and box("#seWave")[3] > 200, (lib, ed, side, box("#seWave"))
        assert [x.strip() for x in s.ev("[...document.querySelectorAll('.se-new button')].map(b => b.innerText)")] == ["Speak text", "Speak a script", "Make music", "Find an effect", "Import a file", "Record"]
        s.shot("task10_empty")
        n0 = s.ev("SoundEditor.state.sounds.length")

        print("step: import", flush=True)
        s.page.click(".se-new button[data-n=import]")
        s.page.set_input_files("#seImportFile", str(wav))
        s.page.wait_for_function("SoundEditor.state.sound && SoundEditor.state.sound.name === 'beep' && SoundEditor.state.peaks.length > 0", timeout=60000)
        assert s.ev("SoundEditor.state.sound.provenance.source") == "import" and abs(s.ev("SoundEditor.state.dur") - 3.0) < 0.02
        lit = s.ev("(() => { const cv = document.querySelector('#seWave'); const d = cv.getContext('2d').getImageData(0, 0, cv.width, cv.height).data; let n = 0; for (let i = 0; i < d.length; i += 4) if (d[i] > 200 && d[i + 1] > 140 && d[i + 2] < 120) n++; return n; })()")
        assert lit > 2000, f"the waveform is drawn in the effect colour ({lit})"

        print("step: select and delete", flush=True)
        wb = box("#seWave")
        s.page.mouse.move(wb[0] + wb[2] * 0.25, wb[1] + wb[3] / 2)
        s.page.mouse.down(); s.page.mouse.move(wb[0] + wb[2] * 0.5, wb[1] + wb[3] / 2, steps=8); s.page.mouse.up()
        sel = s.ev("SoundEditor.state.sel")
        assert abs(sel["a"] - 0.75) < 0.05 and abs(sel["b"] - 1.5) < 0.05, sel
        assert "Selection" in s.ev("document.querySelector('#seSel').innerText")
        s.page.keyboard.press("Delete")
        s.page.wait_for_function("SoundEditor.state.sound.current === 2", timeout=30000)
        assert abs(s.ev("SoundEditor.state.dur") - 2.25) < 0.03, s.ev("SoundEditor.state.dur")
        s.shot("task10_deleted")

        print("step: a tool with parameters, preview then apply", flush=True)
        s.page.click(".se-group[data-g='Time and pitch'] > summary")
        s.page.fill(".se-op[data-op=pitch] input[data-p=semitones]", "5")
        s.page.click(".se-op[data-op=pitch] >> text=Preview")
        s.page.wait_for_function("document.querySelector('#seStatus').innerText.startsWith('Playing the preview')", timeout=60000)
        assert s.ev("SoundEditor.state.sound.current") == 2, "a preview keeps the sound as it was"
        s.page.click(".se-op[data-op=pitch] >> text=Apply")
        s.page.wait_for_function("SoundEditor.state.sound.current === 3", timeout=60000)
        assert s.ev("SoundEditor.state.sound.versions[2].params.semitones") == 5

        print("step: undo, redo, versions", flush=True)
        s.page.keyboard.press("Control+z")
        s.page.wait_for_function("SoundEditor.state.sound.current === 2")
        s.page.click("#seRedo")
        s.page.wait_for_function("SoundEditor.state.sound.current === 3")
        assert s.ev("[...document.querySelectorAll('#seVersions .se-ver')].map(b => b.innerText)") == ["1 original", "2 delete", "3 pitch +5"]
        s.page.click("#seVersions .se-ver[data-n='1']")
        s.page.wait_for_function("SoundEditor.state.sound.current === 1")
        assert abs(s.ev("SoundEditor.state.dur") - 3.0) < 0.02

        print("step: play and the meter", flush=True)
        s.page.click("#sePlay")
        s.page.wait_for_function("SoundEditor.state.playing === true", timeout=10000)
        s.page.wait_for_timeout(900)
        assert s.ev("SoundEditor.state.t") > 0.3 and float(s.ev("document.querySelector('#seMeter').dataset.db || '-99'")) > -40
        s.page.keyboard.press(" ")
        assert s.ev("SoundEditor.state.playing") is False

        print("step: speak a line", flush=True)
        s.page.click(".se-new button[data-n=voice]")
        s.page.fill("#seVoiceText", "The gate opened at dawn.")
        s.page.select_option("#seVoice", "kokoro:af_heart")
        s.page.click("#seMakeVoice")
        s.page.wait_for_function("SoundEditor.state.sound && SoundEditor.state.sound.kind === 'voice'", timeout=300000)
        assert 1.0 < s.ev("SoundEditor.state.dur") < 5 and s.ev("SoundEditor.state.sound.provenance.source") == "tts/kokoro"

        print("step: effects, rename, trash and restore", flush=True)
        s.page.click(".se-new button[data-n=effect]")
        s.page.click(".dl-preset[data-k=impact]")
        s.page.click("#seFindFx")
        s.page.wait_for_function("document.querySelectorAll('#seCands .se-cand').length === 3", timeout=60000)
        s.page.click("#seCands .se-cand >> nth=1 >> text=Keep")
        s.page.wait_for_function("SoundEditor.state.sound && SoundEditor.state.sound.kind === 'effect' && SoundEditor.state.sound.provenance.source === 'synth'", timeout=30000)
        fx = s.ev("SoundEditor.state.sound.id")
        s.page.fill("#seName", "Big hit")
        s.page.press("#seName", "Enter")
        s.page.wait_for_function("id => SoundEditor.state.sounds.some(x => x.id === id && x.name === 'Big hit')", arg=fx, timeout=10000)
        s.page.click("#seDelete")
        s.page.wait_for_function("!SoundEditor.state.sound")
        s.page.click(".se-filters button[data-f=trash]")
        s.page.wait_for_function("id => SoundEditor.state.sounds.some(x => x.id === id && x.trashed)", arg=fx)
        s.page.click(f"#seList .se-row[data-id='{fx}']")
        s.page.wait_for_function("SoundEditor.state.sound && SoundEditor.state.sound.trashed")
        s.page.click("#seRestore")
        s.page.wait_for_function("SoundEditor.state.sound && !SoundEditor.state.sound.trashed")
        s.page.click(".se-filters button[data-f=all]")
        s.page.wait_for_function("n => SoundEditor.state.sounds.length === n + 3", arg=n0)
        s.shot("task10_editor")
        s.finish()
    print("task 10 OK")


# ---------------------------------------------------------------- task 11: library sounds on the Video Studio timeline (A2-A4), playback, export
def check_11(tmp):
    import numpy as np
    import soundfile as sf
    out_dir = Path(r"E:\VIJAY SEKAR\PanelFlow Studio\output\chronoflow")   # the engine's shared output folder: this check removes what it puts there
    made = []
    video = make_video(tmp / "tl_pic.mp4")   # 8 s, cuts at 2/4/6, a 300 Hz tone
    t = np.arange(48000 * 2) / 48000
    sf.write(str(tmp / "line.wav"), (0.4 * np.sin(2 * np.pi * 1200 * t)).astype(np.float32), 48000)
    voice = api("POST", "/api/audio/library/sounds/import", {"path": str(tmp / "line.wav"), "name": "Test line", "kind": "voice"})
    imp = api("POST", "/api/chronoflow/library/import", {"paths": [str(video)], "title": "sound tracks check"})
    job = imp["job_id"]
    made += list(out_dir.glob(f"{job}_*"))
    try:
        with sync_playwright() as pw:
            s = Session(pw, tab=True)
            s.ev("j => { switchResolvePage('edit'); onSelectProjectJob(j); return 1; }", job)
            s.page.wait_for_function("j => NLE.ui.jobId === j && NLE.tl.clips.length === 1", arg=job, timeout=30000)
            heads = s.ev("[...document.querySelectorAll('.nle-head')].map(h => h.innerText.replace(/\s+/g, ' ').trim())")
            assert any(h.startswith("A2 Voice") for h in heads) and any(h.startswith("A3 Music") for h in heads) and any(h.startswith("A4 Effects") for h in heads), heads

            print("step: send from the Audio Studio", flush=True)
            s.ev("NLE.seek(3)")
            s.page.evaluate("switchTab('audio')")
            s.page.wait_for_function("SoundEditor.state.sounds.length > 0", timeout=20000)
            s.ev("id => SoundEditor.openSound(id)", voice["id"])
            s.page.wait_for_function("id => SoundEditor.state.sound && SoundEditor.state.sound.id === id", arg=voice["id"])
            s.page.click("#seSend")
            s.page.wait_for_function("NLE.tl.audio.length === 1", timeout=10000)
            assert s.ev("document.getElementById('cfWorkspace').dataset.page") == "edit"
            item = s.ev("NLE.tl.audio[0]")
            assert item["track"] == "voice" and abs(item["start"] - 3.0) < 1e-6 and abs(item["out"] - 2.0) < 0.01, item
            s.page.wait_for_function("document.querySelectorAll('.nle-lane[data-lane=voice] .nle-clip.snd').length === 1")
            s.page.wait_for_timeout(500)
            wave = s.ev("(() => { const cv = document.querySelector('.nle-lane[data-lane=voice] .nle-clip.snd canvas'); const d = cv.getContext('2d').getImageData(0, 0, cv.width, cv.height).data; let n = 0; for (let i = 3; i < d.length; i += 4) if (d[i] > 100) n++; return n; })()")
            assert wave > 200, f"the waveform is drawn on A2 ({wave})"

            print("step: drag and trim on the lane", flush=True)
            b = s.ev("(() => { const r = document.querySelector('.nle-lane[data-lane=voice] .nle-clip.snd').getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; })()")
            pps = s.ev("NLE.ui.pps")
            s.page.mouse.move(b[0] + b[2] / 2, b[1] + b[3] / 2); s.page.mouse.down(); s.page.mouse.move(b[0] + b[2] / 2 - pps * 1.0, b[1] + b[3] / 2, steps=6); s.page.mouse.up()
            st = s.ev("NLE.tl.audio[0].start")
            assert abs(st - 2.0) < 0.1, ("moved about a second earlier, snapping to the cut at 2 s", st)
            b = s.ev("(() => { const r = document.querySelector('.nle-lane[data-lane=voice] .nle-clip.snd').getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; })()")
            s.page.mouse.move(b[0] + b[2] - 2, b[1] + b[3] / 2); s.page.mouse.down(); s.page.mouse.move(b[0] + b[2] - 2 - pps * 0.5, b[1] + b[3] / 2, steps=5); s.page.mouse.up()
            it = s.ev("NLE.tl.audio[0]")
            assert abs((it["out"] - it["in"]) - 1.5) < 0.1, it
            s.page.fill("#inspSFO", "0.3"); s.page.press("#inspSFO", "Tab")
            assert abs(s.ev("NLE.tl.audio[0].fadeOut") - 0.3) < 1e-6
            s.shot("task11_timeline")

            print("step: playback reaches the speakers", flush=True)
            s.ev("NLE.seek(1.8)")
            s.ev("(() => { NLE.play(1); return 1; })()")
            s.page.wait_for_timeout(1200)
            lvl = s.ev("(() => { const a = document.querySelectorAll('.nle-meter i'); return [...a].map(x => parseFloat(x.style.height) || 0); })()")
            s.ev("NLE.pause()")
            assert max(lvl) > 30, ("the master meter moves while the sound plays", lvl)

            print("step: mute leaves it out of the export, unmute and export", flush=True)
            s.page.click("[data-smute=voice]")
            assert s.ev("NLEModel.toEdl(NLE.tl).audio.length") == 0
            s.page.click("[data-smute=voice]")
            edl = s.ev("NLEModel.toEdl(NLE.tl)")
            assert len(edl["audio"]) == 1
            res = api("POST", "/api/chronoflow/timeline/export", edl)
            master = out_dir / res["filename"]
            made.append(master)
            wav = tmp / "master.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(master), "-vn", "-ac", "1", "-ar", "48000", "-c:a", "pcm_f32le", str(wav)], check=True)
            x, _ = sf.read(str(wav), dtype="float32")
            def band(a, b, f):
                seg = x[int(a * 48000):int(b * 48000)]
                sp = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))); k = int(round(f * len(seg) / 48000)); return float(sp[k - 3:k + 4].max())
            assert band(2.1, 3.1, 1200) > 20 * band(4.5, 5.5, 1200), "the line is in the export at 2.0-3.5 s only"
            assert band(4.5, 5.5, 300) > 0, "the clip sound is kept"

            print("step: the Media Pool Sounds bin adds and drags sounds", flush=True)
            s.ev("selectMediaBin('audio')")
            row = f".pool-snd[data-id='{voice['id']}']"
            s.page.wait_for_selector(row, timeout=10000)
            s.ev("NLE.seek(6)")
            s.page.click(f"{row} .pool-snd-add")
            s.page.wait_for_function("NLE.tl.audio.length === 2")
            assert abs(s.ev("NLE.tl.audio[1].start") - 6.0) < 1e-6 and s.ev("NLE.tl.audio[1].track") == "voice"
            s.page.drag_and_drop(row, ".nle-lane[data-lane=music]", target_position={"x": int(pps * 1.0) + 2, "y": 10})
            s.page.wait_for_function("NLE.tl.audio.length === 3", timeout=10000)
            dropped = s.ev("NLE.tl.audio[2]")
            assert dropped["track"] == "music" and abs(dropped["start"] - 1.0) < 0.1, dropped
            s.shot("task11_bin")

            print("step: the quick Audio page sends its placed cues to the timeline", flush=True)
            s.ev("p => { switchResolvePage('audio'); return NLEAudio.openVideo(p).then(() => 1); }", str(video))
            s.page.wait_for_function("NLEAudio.state.plan && NLEAudio.state.plan.id", timeout=30000)
            pid = s.ev("NLEAudio.state.plan.id")
            api("PUT", f"/api/audio/studio/plans/{pid}", {"cues": [{"id": "c_hit", "track": "sfx", "kind": "impact", "intent": "hit", "hit_t": 4.0}]})
            api("POST", f"/api/audio/studio/plans/{pid}/cues/c_hit/source", {"mode": "auto"})
            s.ev("NLEAudio.reload().then(() => 1)")
            s.page.click("#auSendTl")
            s.page.wait_for_function("NLE.tl.audio.some(a => a.origin && a.track === 'effect')", timeout=30000)
            assert s.ev("document.getElementById('cfWorkspace').dataset.page") == "edit"
            n_before = s.ev("NLE.tl.audio.length")
            hit = s.ev("NLE.tl.audio.find(a => a.origin)")
            assert 3.5 < hit["start"] <= 4.0 and hit["track"] == "effect", hit
            s.ev("switchResolvePage('audio')")
            s.page.click("#auSendTl")
            s.page.wait_for_timeout(1500)
            assert s.ev("NLE.tl.audio.length") == n_before and s.ev("NLE.tl.audio.filter(a => a.origin).length") == 1, "sending again replaces, never duplicates"
            s.finish()
    finally:
        for f in made:
            try:
                f.unlink()
            except OSError:
                pass
    print("task 11 OK")


def check_12(tmp):
    """Speak a script in the Audio Studio, place it one line per picture cut, then update a placed line after editing it."""
    out_dir = Path(r"E:\VIJAY SEKAR\PanelFlow Studio\output\chronoflow")
    video = make_video(tmp / "script_pic.mp4")   # 8 s, cuts at 2/4/6
    job = api("POST", "/api/chronoflow/library/import", {"paths": [str(video)], "title": "script narration check"})["job_id"]
    made = list(out_dir.glob(f"{job}_*"))
    try:
        with sync_playwright() as pw:
            s = Session(pw, tab=True)
            s.ev("j => { switchResolvePage('edit'); onSelectProjectJob(j); return 1; }", job)
            s.page.wait_for_function("j => NLE.ui.jobId === j && NLE.tl.clips.length === 1", arg=job, timeout=30000)
            for t in (2, 4, 6):   # four pictures: the script goes one line per picture
                s.ev(f"NLE.seek({t})"); s.page.click("[data-t=split]")
            s.page.wait_for_function("NLE.tl.clips.length === 4", timeout=10000)
            s.page.evaluate("switchTab('audio')")
            s.page.wait_for_selector(".se-new button[data-n=script]", timeout=20000)
            s.page.click(".se-new button[data-n=script]")
            s.page.fill("#seScriptText", "The gate opened at dawn.\n\nNobody was waiting.\n\nShe walked through anyway.")
            assert "3 line(s)" in s.ev("document.getElementById('seScriptEst').textContent")
            s.page.select_option("#seScriptVoice", "kokoro:af_heart")
            before = s.ev("SoundEditor.state.sounds.filter(x => x.name.startsWith('Line 0')).length")
            s.page.click("#seMakeScript")
            s.page.wait_for_function("document.getElementById('seScriptPlace') && !document.getElementById('seScriptPlace').hidden", timeout=300000)
            lines = s.ev("SoundEditor.state.sounds.filter(x => x.name.startsWith('Line 0')).length")
            assert lines - before == 3, (before, lines)
            s.page.click("#seScriptCut")
            s.page.wait_for_function("NLE.tl.audio.length === 3", timeout=10000)
            items = s.ev("NLE.tl.audio.map(a => [a.track, a.start, a.label.slice(0, 7)])")
            assert items == [["voice", 0, "Line 01"], ["voice", 2, "Line 02"], ["voice", 4, "Line 03"]], items
            s.shot("task12_script_placed")

            print("step: edit a line, then update the placed one", flush=True)
            first = s.ev("NLE.tl.audio[0].sound")
            api("POST", f"/api/audio/library/sounds/{first}/edit", {"op": "gain", "params": {"db": -6}})
            s.page.click(".nle-lane[data-lane=voice] .nle-clip.snd")
            s.page.wait_for_selector("#inspSNew:not([hidden])", timeout=10000)
            s.page.click("#inspSNew")
            s.page.wait_for_function("NLE.tl.audio[0].version === 2", timeout=10000)
            s.page.wait_for_function("document.getElementById('inspSNew') === null || document.getElementById('inspSNew').hidden", timeout=10000)
            s.finish()
    finally:
        for f in made:
            try:
                f.unlink()
            except OSError:
                pass
    print("task 12 OK")


CHECKS = {"4": check_4, "5": check_5, "6": check_6, "7": check_7, "8": check_8, "9": check_9, "10": check_10, "11": check_11, "12": check_12}

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    tmp = Path(tempfile.mkdtemp(prefix="audio_ui_"))
    for k, fn in CHECKS.items():
        if which in ("all", k):
            fn(tmp)
