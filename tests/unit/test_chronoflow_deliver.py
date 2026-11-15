"""ChronoFlow Deliver: settings validation, the final encode (size, fit, fps, codec, range, loudness) and the render queue."""
import json
import re
import shutil
import subprocess
import time

import pytest

from engine.chronoflow import deliver as D

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_name,codec_type,width,height,r_frame_rate", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    v = next(s for s in data["streams"] if s["codec_type"] == "video")
    a = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    return {"w": v["width"], "h": v["height"], "vcodec": v["codec_name"], "fps": v["r_frame_rate"], "dur": float(data["format"]["duration"]), "acodec": a and a["codec_name"]}


def loudness(path):
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True).stderr
    return float(re.findall(r"I:\s+(-?\d+\.\d)\s+LUFS", err)[-1])


@pytest.fixture(scope="module")
def source(tmp_path_factory):
    p = tmp_path_factory.mktemp("src") / "src.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=640x360:d=3:r=30", "-f", "lavfi", "-i", "sine=frequency=440:duration=3:sample_rate=48000",
                    "-af", "volume=-30dB", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(p)], check=True)
    return p


@pytest.fixture()
def queue(tmp_path, source):
    def fake_master(clips, path, overlays=None, luts=None):          # stands in for the EDL renderer
        if clips[0].get("filename") == "missing.mp4":
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(source, path)
        return path
    return D.DeliverQueue(tmp_path / "out", fake_master)


PAYLOAD = {"clips": [{"filename": "src.mp4"}], "overlays": [], "luts": {}}


def wait_done(q, rid, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        rec = q.get(rid)
        if rec["status"] in D.TERMINAL:
            return rec
        time.sleep(0.2)
    raise AssertionError(f"render {rid} did not finish: {q.get(rid)}")


def render(q, **settings):
    rec = wait_done(q, q.submit(PAYLOAD, settings)["id"])
    assert rec["status"] == "done", rec["error"]
    return rec, q.dir / rec["file"]


# ---- settings ----
def test_every_preset_is_valid_and_defaults_fill_in():
    for p in D.PRESETS:
        s = D.normalize_settings({**p["settings"], "preset": p["id"]})
        assert s["codec"] in D.EXT
    s = D.normalize_settings({})
    assert (s["codec"], s["width"], s["fit"], s["quality"], s["audio"], s["loudness"]) == ("h264", 0, "fit", 18, True, None)


@pytest.mark.parametrize("bad,msg", [
    ({"codec": "divx"}, "codec must be"), ({"width": 1920}, "both width and height"), ({"width": 100, "height": 100}, "at least 160"),
    ({"fps": 17}, "fps must be one of"), ({"quality": 99}, "quality must be between"), ({"loudness": -5}, "loudness target"),
    ({"codec": "vp9", "encoder": "nvenc"}, "NVENC"), ({"range_in": 5, "range_out": 3}, "end after it starts"), ({"fit": "zoom"}, "fit must be"),
])
def test_bad_settings_are_refused_with_a_sentence(bad, msg):
    with pytest.raises(ValueError, match=msg):
        D.normalize_settings(bad)


def test_file_names_are_cleaned():
    name = D.normalize_settings({"name": "../../evil/..\\name?.mp4"})["name"]
    assert not any(c in name for c in '/\\?:*"<>|') and not name.startswith("."), name   # cannot leave the deliver folder
    assert D.normalize_settings({"name": "   "})["name"] == "chronoflow"


# ---- encode ----
def test_youtube_1080p_scales_with_bars_and_keeps_h264_aac(queue):
    rec, f = render(queue, codec="h264", width=1920, height=1080, fit="fit", quality=26)
    p = probe(f)
    assert (p["w"], p["h"], p["vcodec"], p["acodec"]) == (1920, 1080, "h264", "aac")
    assert abs(p["dur"] - 3) < 0.2 and rec["size"] > 0 and rec["url"].endswith(rec["file"])


def test_vertical_fill_crops_to_exact_size_and_30fps(queue):
    _, f = render(queue, codec="h264", width=1080, height=1920, fit="fill", fps=30, quality=28)
    p = probe(f)
    assert (p["w"], p["h"], p["fps"]) == (1080, 1920, "30/1")


def test_frame_rate_conversion(queue):
    _, f = render(queue, fps=24, quality=28)
    assert probe(f)["fps"] == "24/1"


def test_range_renders_only_the_chosen_seconds(queue):
    _, f = render(queue, range_in=1.0, range_out=2.5, quality=28)
    assert abs(probe(f)["dur"] - 1.5) < 0.15


def test_loudness_normalises_a_quiet_clip_to_the_target(queue):
    _, quiet = render(queue, loudness=None, quality=28)
    _, loud = render(queue, loudness=-14, quality=28)
    assert loudness(quiet) < -25, "test clip should start quiet"
    assert abs(loudness(loud) - (-14)) < 1.5, f"got {loudness(loud)} LUFS"


def test_prores_and_h265_and_no_audio(queue):
    _, f = render(queue, codec="prores", quality=2)
    p = probe(f)
    assert f.suffix == ".mov" and p["vcodec"] == "prores" and p["acodec"] == "pcm_s16le"
    _, f2 = render(queue, codec="h265", quality=30, audio=False)
    p2 = probe(f2)
    assert p2["vcodec"] == "hevc" and p2["acodec"] is None


# ---- queue ----
def test_a_render_that_cannot_make_a_master_fails_with_a_message_and_leaves_no_file(queue):
    rec = wait_done(queue, queue.submit({"clips": [{"filename": "missing.mp4"}]}, {})["id"])
    assert rec["status"] == "failed" and "no video" in rec["error"]
    assert not any(queue.dir.glob("*.mp4")) and not (queue.dir / "_work").exists() or not any((queue.dir / "_work").iterdir())


def test_an_empty_timeline_is_refused_up_front(queue):
    with pytest.raises(ValueError, match="no clips"):
        queue.submit({"clips": []}, {})


def test_same_name_twice_gets_two_files_and_history_lists_newest_first(queue):
    a = queue.submit(PAYLOAD, {"name": "same", "quality": 30})
    b = queue.submit(PAYLOAD, {"name": "same", "quality": 30})
    assert a["file"] != b["file"] and b["file"] == "same_2.mp4"
    wait_done(queue, a["id"]); wait_done(queue, b["id"])
    assert [r["id"] for r in queue.list()][:2] == [b["id"], a["id"]]


def test_cancel_a_queued_render_and_delete_a_finished_one(queue):
    first = queue.submit(PAYLOAD, {"name": "first", "quality": 30})
    second = queue.submit(PAYLOAD, {"name": "second", "quality": 30})
    assert queue.cancel(second["id"]) is True
    assert wait_done(queue, second["id"])["status"] == "cancelled"
    done = wait_done(queue, first["id"])
    assert done["status"] == "done" and (queue.dir / done["file"]).exists()
    assert queue.delete(first["id"]) is True and not (queue.dir / done["file"]).exists() and queue.get(first["id"]) is None
    assert queue.delete("nope") is False and queue.cancel("nope") is False


def test_history_survives_a_restart_and_unfinished_renders_are_marked_failed(queue, tmp_path):
    rec, _ = render(queue, name="kept", quality=30)
    stuck = {**queue.get(rec["id"]), "id": "stuck00001", "status": "rendering", "stage": "encoding"}
    (queue.records_dir / "stuck00001.json").write_text(json.dumps(stuck), encoding="utf-8")
    again = D.DeliverQueue(tmp_path / "out", lambda *a, **k: None)
    assert again.get(rec["id"])["status"] == "done"
    s = again.get("stuck00001")
    assert s["status"] == "failed" and "restarted" in s["error"]
