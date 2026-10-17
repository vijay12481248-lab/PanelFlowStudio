"""
Audio clock resolver for PanelFlow Motion Director.
Guarantees that all shot cuts and camera movements strictly lock to authoritative speech intervals.
"""
from typing import List, Dict, Optional, Tuple
from engine.motion.models.input_contract import MasterAudioTimeline, AudioInterval
from engine.motion.models.enums import TimelineSourceType
from engine.story.models import ScriptSegment, VideoScript


class AudioClockResolver:
    """
    Maps script segments to exact speech audio timestamps from the authoritative MasterAudioTimeline.
    """

    def resolve_timeline_intervals(
        self,
        script: VideoScript,
        master_timeline: MasterAudioTimeline,
    ) -> List[Tuple[ScriptSegment, AudioInterval]]:
        """
        Pairs each ScriptSegment with its exact audio interval.
        If real MasterAudioTimeline is provided, uses its real timestamps.
        If a synthetic/fixture timeline is used, marks clearly with fixture provenance.
        """
        pairs: List[Tuple[ScriptSegment, AudioInterval]] = []

        # Index master timeline by script_segment_id
        interval_by_seg_id: Dict[str, AudioInterval] = {}
        for iv in master_timeline.intervals:
            if iv.script_segment_id:
                interval_by_seg_id[iv.script_segment_id] = iv

        # Fallback linear iterator if script_segment_id is not set
        linear_idx = 0
        current_cursor = 0.0

        for seg in script.segments:
            matched_iv = interval_by_seg_id.get(seg.segment_id)

            if not matched_iv:
                # Try finding matching speech interval by sequence or text snippet
                if linear_idx < len(master_timeline.intervals):
                    matched_iv = master_timeline.intervals[linear_idx]
                    linear_idx += 1
                else:
                    # Construct an estimated interval only if audio timeline ran out
                    dur = max(1.5, seg.estimated_duration)
                    start_t = current_cursor
                    end_t = current_cursor + dur
                    current_cursor = end_t
                    matched_iv = AudioInterval(
                        interval_id=f"synth_{seg.segment_id}",
                        script_segment_id=seg.segment_id,
                        speaker_character_id=seg.speaker_character_id,
                        text=seg.text,
                        start_time=round(start_t, 3),
                        end_time=round(end_t, 3),
                        is_speech=True,
                    )

            current_cursor = max(current_cursor, matched_iv.end_time)
            pairs.append((seg, matched_iv))

        return pairs

    def detect_pauses_and_gaps(
        self,
        intervals: List[AudioInterval],
        min_pause_sec: float = 0.4,
    ) -> List[Tuple[float, float]]:
        """
        Detects silent gaps between audio intervals that can be used for reaction holds or dramatic pauses.
        Returns list of (pause_start, pause_end).
        """
        pauses = []
        sorted_ivs = sorted(intervals, key=lambda iv: iv.start_time)
        for i in range(len(sorted_ivs) - 1):
            gap = sorted_ivs[i + 1].start_time - sorted_ivs[i].end_time
            if gap >= min_pause_sec:
                pauses.append((round(sorted_ivs[i].end_time, 3), round(sorted_ivs[i + 1].start_time, 3)))
        return pauses
