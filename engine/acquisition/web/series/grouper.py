"""
Smart Chapter Grouper and Duration Bin-Packer for Multi-Chapter Compilations.
Partitions consecutive manga chapters into optimized video bundles matching
user target runtimes (e.g., 25-minute episodic cuts, 1-hour movies, 2-hour mega-cuts).
"""
import math
from typing import List, Dict, Any, Optional
from engine.acquisition.web.series.models import (
    SeriesChapter,
    CompilationBundle,
    CompilationMode,
)

# Standard estimated duration per chapter (in seconds) if not yet rendered.
# Based on ~7-8 pages per chapter, 40-50 panels, ~24 narration beats = ~215s (3.58 min)
DEFAULT_ESTIMATED_CHAPTER_DURATION_SEC = 217.0


class SmartChapterGrouper:
    """
    Partitions a sequence of chapters into individual or compiled video bundles.
    """

    def __init__(
        self,
        default_chapter_duration_sec: float = DEFAULT_ESTIMATED_CHAPTER_DURATION_SEC,
        tolerance_factor: float = 0.15,
    ):
        self.default_chapter_duration_sec = default_chapter_duration_sec
        self.tolerance_factor = tolerance_factor  # Allow up to +15% over target rather than stranding 1 chapter

    def partition_chapters(
        self,
        chapters: List[SeriesChapter],
        series_title: str,
        compilation_mode: CompilationMode = CompilationMode.INDIVIDUAL,
        target_duration_minutes: float = 25.0,
        known_durations: Optional[Dict[float, float]] = None,
    ) -> List[CompilationBundle]:
        """
        Partitions the chapter list into CompilationBundle objects.
        """
        if not chapters:
            return []

        # Sort chapters strictly by sequence
        sorted_chapters = sorted(chapters, key=lambda c: c.sequence)
        known_durations = known_durations or {}

        clean_series_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in series_title).strip("_")

        # -------------------------------------------------------------------
        # Mode 1: Individual Chapter Videos
        # -------------------------------------------------------------------
        if compilation_mode == CompilationMode.INDIVIDUAL:
            bundles = []
            for ch in sorted_chapters:
                ch_dur = known_durations.get(ch.sequence, self.default_chapter_duration_sec)
                num_str = f"{int(ch.sequence)}" if ch.sequence.is_integer() else f"{ch.sequence:g}"
                bundle = CompilationBundle(
                    bundle_id=f"chapter_{num_str}",
                    title=f"{series_title} - Chapter {num_str}",
                    chapters=[ch],
                    target_duration_minutes=round(ch_dur / 60.0, 1),
                    estimated_duration_sec=ch_dur,
                    output_filename=f"{clean_series_name}_Chapter_{num_str}_1080p.mp4",
                    chapter_markers=[
                        {
                            "chapter_sequence": ch.sequence,
                            "title": ch.title,
                            "start_time_sec": 0.0,
                            "duration_sec": ch_dur,
                            "timestamp_str": "00:00",
                        }
                    ],
                )
                bundles.append(bundle)
            return bundles

        # -------------------------------------------------------------------
        # Mode 2: Smart Duration Compilation (e.g. 25m, 1h, 2h)
        # -------------------------------------------------------------------
        target_sec = max(60.0, target_duration_minutes * 60.0)
        bundles = []
        current_bundle_chapters: List[SeriesChapter] = []
        current_bundle_dur = 0.0
        part_idx = 1

        for idx, ch in enumerate(sorted_chapters):
            ch_dur = known_durations.get(ch.sequence, self.default_chapter_duration_sec)
            
            # Check if adding this chapter would exceed target duration
            projected_dur = current_bundle_dur + ch_dur
            # Close bundle if we have at least 1 chapter and adding this one exceeds target + tolerance
            if current_bundle_chapters and projected_dur > (target_sec * (1.0 + self.tolerance_factor)):
                # Finalize current bundle
                bundles.append(
                    self._create_compiled_bundle(
                        current_bundle_chapters,
                        series_title,
                        clean_series_name,
                        target_duration_minutes,
                        part_idx,
                        known_durations,
                    )
                )
                part_idx += 1
                current_bundle_chapters = [ch]
                current_bundle_dur = ch_dur
            else:
                current_bundle_chapters.append(ch)
                current_bundle_dur += ch_dur

        # Finalize remaining chapters in last bundle
        if current_bundle_chapters:
            bundles.append(
                self._create_compiled_bundle(
                    current_bundle_chapters,
                    series_title,
                    clean_series_name,
                    target_duration_minutes,
                    part_idx,
                    known_durations,
                )
            )

        return bundles

    def _create_compiled_bundle(
        self,
        chapters: List[SeriesChapter],
        series_title: str,
        clean_series_name: str,
        target_duration_minutes: float,
        part_idx: int,
        known_durations: Dict[float, float],
    ) -> CompilationBundle:
        first_num = chapters[0].sequence
        last_num = chapters[-1].sequence
        first_str = f"{int(first_num)}" if first_num.is_integer() else f"{first_num:g}"
        last_str = f"{int(last_num)}" if last_num.is_integer() else f"{last_num:g}"

        range_label = f"Chapters_{first_str}-{last_str}" if len(chapters) > 1 else f"Chapter_{first_str}"

        # Build chapter markers with exact relative offsets
        markers = []
        accum_time = 0.0
        for ch in chapters:
            dur = known_durations.get(ch.sequence, self.default_chapter_duration_sec)
            # Format timestamp as MM:SS or HH:MM:SS
            total_s = int(accum_time)
            hrs = total_s // 3600
            mins = (total_s % 3600) // 60
            secs = total_s % 60
            ts_str = f"{hrs:02d}:{mins:02d}:{secs:02d}" if hrs > 0 else f"{mins:02d}:{secs:02d}"

            markers.append({
                "chapter_sequence": ch.sequence,
                "title": ch.title,
                "start_time_sec": round(accum_time, 2),
                "duration_sec": round(dur, 2),
                "timestamp_str": ts_str,
            })
            accum_time += dur

        dur_tag = f"{int(target_duration_minutes)}min" if target_duration_minutes < 60 else f"{int(target_duration_minutes//60)}hr"
        filename = f"{clean_series_name}_{range_label}_{dur_tag}_Part{part_idx}_1080p.mp4"

        return CompilationBundle(
            bundle_id=f"bundle_part_{part_idx}_{first_str}_{last_str}",
            title=f"{series_title} - {range_label.replace('_', ' ')} ({dur_tag} Cut)",
            chapters=chapters,
            target_duration_minutes=target_duration_minutes,
            estimated_duration_sec=round(accum_time, 2),
            output_filename=filename,
            chapter_markers=markers,
        )
