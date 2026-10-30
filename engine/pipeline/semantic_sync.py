"""Panel coverage and clip-level timing; does not infer word timestamps."""
from copy import deepcopy


class SemanticStorySync:
    def __init__(self, min_panel_duration_sec=2.5, max_panel_duration_sec=10.0,
                 scene_cushion_sec=0.35):
        self.scene_cushion = scene_cushion_sec

    def synchronize_scenes_to_narration(self, scenes, narration_clips,
                                       panel_map=None, ignored_panel_ids=None):
        ignored = ignored_panel_ids or set()
        for scene in scenes:
            # The caller owns the absolute clock and measured audio durations.
            layers = [deepcopy(layer) for layer in scene.get("layers", [])
                      if layer.get("source_panel_id") not in ignored]
            if not layers:
                continue
            clips = [c for c in narration_clips if c.get("scene_id") == scene.get("id")]
            origin = float(scene.get("start_time_sec", 0))
            duration = float(scene["duration_sec"])
            ids = [layer.get("source_panel_id") for layer in layers]
            anchors = []
            for clip in clips:
                cited = (clip.get("source_evidence") or {}).get("panel_ids", [])
                positions = [ids.index(pid) for pid in cited if pid in ids]
                anchors.append(min(positions) if positions else None)
            # Each clip whose cited panel moves forward in reading order starts a
            # cut at that clip's start. Clips citing the same, an earlier, or no
            # panel keep the current shot on screen. Uncited panels between two
            # cuts share that span; they must never disappear. Timing is
            # clip-level, not word-level.
            cuts = []  # (first layer index, start offset in scene)
            cursor = origin
            for clip, anchor in zip(clips, anchors):
                start = float(clip.get("start_time_sec", cursor))
                cursor = start + float(clip["duration_sec"])
                if anchor is not None and (not cuts or anchor > cuts[-1][0]):
                    cuts.append((anchor, start - origin))
            # The opening shot always begins with the first panel at scene start.
            cuts = [(0, 0.0)] + [c for c in cuts if c[0] > 0 and c[1] > 0]
            groups = [(first, nxt[0] if nxt else len(layers), start, nxt[1] if nxt else duration)
                      for (first, start), nxt in zip(cuts, cuts[1:] + [None])]
            for first, last, start, end in groups:
                if end <= start or last <= first:
                    raise ValueError("Invalid narration timing or panel ordering")
                step = (end - start) / (last - first)
                for index in range(first, last):
                    offset = start + (index - first) * step
                    layers[index]["start_offset_sec"] = offset
                    layers[index]["duration_sec"] = start + (index - first + 1) * step - offset
            scene["layers"] = layers
        return scenes
