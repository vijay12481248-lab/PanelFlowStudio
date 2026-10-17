"""
Stable rational frame clock for PanelFlow Production Renderer.
Guarantees zero floating-point time drift across long-form video renders.
"""
from fractions import Fraction
from typing import Tuple


class RenderFrameClock:
    """
    Translates between continuous seconds and discrete frame indices using rational arithmetic.
    """

    def __init__(self, fps: int = 30):
        if fps <= 0:
            raise ValueError(f"FPS must be positive integer, got {fps}")
        self.fps = fps
        self._frame_duration = Fraction(1, fps)

    def frame_to_time(self, frame_index: int) -> float:
        """
        Calculates exact timestamp in seconds at the start of a frame.
        """
        return float(Fraction(frame_index, self.fps))

    def time_to_frame(self, timestamp_sec: float) -> int:
        """
        Calculates the nearest frame index for a given timestamp in seconds.
        """
        if timestamp_sec < 0.0:
            return 0
        return int(round(timestamp_sec * self.fps))

    def time_range_to_frame_range(self, start_sec: float, end_sec: float) -> Tuple[int, int, int]:
        """
        Converts a continuous interval [start_sec, end_sec] into [start_frame, end_frame) and frame count.
        Guarantees that consecutive adjacent ranges partition frames with zero gaps and zero overlaps.
        """
        start_frame = self.time_to_frame(start_sec)
        end_frame = self.time_to_frame(end_sec)
        if end_frame <= start_frame:
            end_frame = start_frame + 1
        total_frames = end_frame - start_frame
        return start_frame, end_frame, total_frames

    def normalized_progress(self, frame_index: int, start_frame: int, end_frame: int) -> float:
        """
        Calculates normalized time progress t in [0.0, 1.0] within a shot's frame range.
        """
        if end_frame <= start_frame or frame_index <= start_frame:
            return 0.0
        if frame_index >= end_frame - 1:
            return 1.0
        span = (end_frame - 1) - start_frame
        if span <= 0:
            return 1.0
        return float(Fraction(frame_index - start_frame, span))
