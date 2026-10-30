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
            # Ordered clip anchors divide the full reading sequence into groups.
            # Uncited panels remain visible; they must never disappear just because
            # a summary cites only selected evidence. Multi-panel groups have only
            # clip-level timing, not word-level alignment.
            ordered = (bool(clips) and all(a is not None for a in anchors)
                       and all(a < b for a, b in zip(anchors, anchors[1:])))
            clip_starts = []
            cursor = origin
            for clip in clips:
                start = float(clip.get("start_time_sec", cursor))
                clip_starts.append(start - origin)
                cursor = start + float(clip["duration_sec"])
            groups = []
            if ordered:
                bounds = [0] + anchors[1:] + [len(layers)]
                for i, clip in enumerate(clips):
                    start = 0.0 if i == 0 else clip_starts[i]
                    end = (clip_starts[i + 1]
                           if i + 1 < len(clips) else duration)
                    groups.append((bounds[i], bounds[i + 1], start, end))
            else:
                groups = [(0, len(layers), 0.0, duration)]
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
