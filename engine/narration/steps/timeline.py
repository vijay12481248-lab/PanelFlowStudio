"""Step 8 LOCK TIMELINE: cut each panel 120 ms before its line's first word, then measure the sync."""
from __future__ import annotations

from statistics import median

from engine.narration.artifacts import (
    BeatSheet, LockedTimeline, PerformancePlan, ScriptIR, TimelineClip, TimelinePanel, VoiceTake,
)

LEAD_CUT = 0.120
MIN_HOLD = 1.2
MAX_HOLD = 6.0
UNVOICED_HOLD = 1.6
_NO_WORDS = 0.08
_EPS = 1e-6


def _first(take: VoiceTake) -> float:
    return take.words[0].start if take.words else _NO_WORDS


def _scene_of(sheet: BeatSheet, story_ids: list[str]) -> dict[str, str]:
    """Every story panel inside a scene's range belongs to it, beat or not; strays join the scene before them."""
    pos = {p: i for i, p in enumerate(story_ids)}
    out, last = {}, sheet.scenes[0].scene_id
    for i, pid in enumerate(story_ids):
        last = next((s.scene_id for s in sheet.scenes
                     if pos.get(s.first_panel_id, len(pos)) <= i <= pos.get(s.last_panel_id, -1)), last)
        out[pid] = last
    return out


def lock_timeline(script: ScriptIR, plan: PerformancePlan, takes: list[VoiceTake], sheet: BeatSheet,
                  story_ids: list[str]) -> LockedTimeline:
    lines = script.lines
    if not lines or not takes:
        raise ValueError("cannot lock a timeline from an empty script or empty takes")
    by_take = {t.line_id: t for t in takes}
    pause = {m.line_id: m.pause_after_ms / 1000 for m in plan.lines}
    for ln in lines:
        if ln.line_id not in by_take or ln.line_id not in pause:
            raise ValueError(f"line {ln.line_id} has no voice take or no performance marks")
    scene = _scene_of(sheet, story_ids)
    c = max(0.0, LEAD_CUT - _first(by_take[lines[0].line_id]))
    starts, cuts = [], []
    for i, ln in enumerate(lines):
        t = by_take[ln.line_id]
        cuts.append(0.0 if i == 0 else c + min(_first(t) - LEAD_CUT, 0.0))
        starts.append(c)
        if i + 1 < len(lines):
            nxt = _first(by_take[lines[i + 1].line_id])
            c = max(c + t.duration + pause[ln.line_id], cuts[i] + MIN_HOLD - min(nxt - LEAD_CUT, 0.0))
    end = max(starts[-1] + by_take[lines[-1].line_id].duration + 0.5, cuts[-1] + MIN_HOLD)
    ends = cuts[1:] + [end]
    # A story panel no line cites is still shown: held silently after the narrated panel before it.
    pos = {p: i for i, p in enumerate(story_ids)}
    cited = {ln.panel_id for ln in lines}
    after: dict[int, list[str]] = {}
    for pid in story_ids:
        if pid in cited:
            continue
        before = [i for i, ln in enumerate(lines) if pos.get(ln.panel_id, -1) < pos[pid]]
        after.setdefault(max(before, key=lambda i: pos.get(lines[i].panel_id, -1)) if before else -1, []).append(pid)
    panels, clips, shift = [], [], 0.0

    def hold(pids):
        nonlocal shift
        for pid in pids:
            start = panels[-1].end if panels else 0.0
            panels.append(TimelinePanel(panel_id=pid, start=start, end=start + UNVOICED_HOLD,
                                        cut_reason="hold", scene_id=scene[pid]))
            shift += UNVOICED_HOLD

    hold(after.get(-1, []))
    for i, ln in enumerate(lines):
        panels.append(TimelinePanel(panel_id=ln.panel_id, start=cuts[i] + shift, end=ends[i] + shift,
                                    cut_reason="line-start", scene_id=scene[ln.panel_id]))
        clips.append(TimelineClip(line_id=ln.line_id, panel_id=ln.panel_id, start=starts[i] + shift,
                                  end=starts[i] + shift + by_take[ln.line_id].duration,
                                  audio_path=by_take[ln.line_id].audio_path))
        hold(after.get(i, []))
    return LockedTimeline(project_id=script.project_id, duration=end + shift, panels=panels, clips=clips)


def sync_metrics(tl: LockedTimeline, takes: list[VoiceTake], script: ScriptIR) -> dict:
    if not takes:
        raise ValueError("cannot measure sync from empty takes")
    by_take = {t.line_id: t for t in takes}
    for c in tl.clips:
        if c.line_id not in by_take:
            raise ValueError(f"line {c.line_id} has no voice take")
    holds = [p.end - p.start for p in tl.panels]
    words = sum(len(ln.text.split()) for ln in script.lines)
    secs = sum((t.words[-1].end - t.words[0].start) if t.words else t.duration for t in takes)
    span = {p.panel_id: p for p in tl.panels}
    onsets = [c.start + _first(by_take[c.line_id]) - span[c.panel_id].start for c in tl.clips]
    wers = [t.wer for t in takes]
    m = {
        "speech_rate": words / secs,
        "cut_median": median(holds),
        "holds_under_1_2": sum(h < MIN_HOLD - _EPS for h in holds),
        "holds_over_6": sum(h > MAX_HOLD + _EPS for h in holds),
        "onset_ok_share": sum(0.08 - _EPS <= o <= 0.2 + _EPS for o in onsets) / len(onsets),
        "wer_median": median(wers),
        "wer_max": max(wers),
    }
    m["targets_met"] = {
        "speech_rate": 2.5 <= m["speech_rate"] <= 3.0,
        "cut_median": 1.8 <= m["cut_median"] <= 3.5,
        "hold_range": m["holds_under_1_2"] == 0 and m["holds_over_6"] == 0,
        "onset": m["onset_ok_share"] >= 0.98,
        "wer_median": m["wer_median"] <= 0.05,
        "wer_max": m["wer_max"] <= 0.15,
    }
    return m

