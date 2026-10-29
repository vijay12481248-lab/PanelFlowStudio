"""
Anime Review Story Script Generator.
Converts episode transcripts, scene cuts, and plot points into a captivating,
structured 4-act anime review & recap commentary script.
"""
from typing import List, Dict, Any, Optional
from engine.anime.models import (
    ActType,
    ReviewStoryBeat,
    AnimeSceneCut,
    AnimeEpisodeSource,
)


class AnimeReviewStoryEngine:
    """
    Generates structured review commentary beats synchronized with episode scene cuts.
    """

    def generate_review_script(
        self,
        source: AnimeEpisodeSource,
        cuts: List[AnimeSceneCut],
        transcript_segments: Optional[List[Dict[str, Any]]] = None,
        custom_outline: Optional[List[str]] = None,
    ) -> List[ReviewStoryBeat]:
        """
        Creates an episodic review/recap script divided into narrative beats,
        mapping each beat to corresponding scene cuts.
        """
        series_name = source.series_title
        ep_num = f"{int(source.episode_number)}" if source.episode_number.is_integer() else f"{source.episode_number:g}"
        ep_title = source.episode_title or f"Episode {ep_num}"

        # If custom outline lines provided, use them
        if custom_outline:
            beats = []
            cuts_per_beat = max(1, len(cuts) // len(custom_outline))
            for i, line in enumerate(custom_outline, 1):
                c_start = (i - 1) * cuts_per_beat
                c_end = min(len(cuts), i * cuts_per_beat) if i < len(custom_outline) else len(cuts)
                assigned = [cuts[c].cut_id for c in range(c_start, c_end)] or ([cuts[0].cut_id] if cuts else [])
                beats.append(
                    ReviewStoryBeat(
                        beat_id=f"beat_{i:02d}",
                        sequence=i,
                        act_type=ActType.PLOT_DEVELOPMENT,
                        voiceover_text=line.strip(),
                        emotion="SERIOUS",
                        assigned_cut_ids=assigned,
                    )
                )
            return beats

        # Auto-generate a structured 4-act review commentary
        beats: List[ReviewStoryBeat] = []

        total_cuts = len(cuts)
        # Partition cuts into 4 acts
        idx_act1_end = max(1, int(total_cuts * 0.20))
        idx_act2_end = max(idx_act1_end + 1, int(total_cuts * 0.55))
        idx_act3_end = max(idx_act2_end + 1, int(total_cuts * 0.85))

        # --- Act 1: Hook & Episode Setup ---
        beats.append(
            ReviewStoryBeat(
                beat_id="beat_01",
                sequence=1,
                act_type=ActType.HOOK_AND_SETUP,
                voiceover_text=f"Welcome back anime fans. Today we are diving into {series_name} Episode {ep_num}, titled {ep_title}.",
                emotion="EXCITED",
                assigned_cut_ids=[c.cut_id for c in cuts[: max(1, idx_act1_end // 2)]],
            )
        )
        beats.append(
            ReviewStoryBeat(
                beat_id="beat_02",
                sequence=2,
                act_type=ActType.HOOK_AND_SETUP,
                voiceover_text=f"Right from the opening sequence, the tension picks up where the previous events left off, establishing a dark and perilous atmosphere.",
                emotion="MYSTERIOUS",
                assigned_cut_ids=[c.cut_id for c in cuts[max(1, idx_act1_end // 2) : idx_act1_end]],
            )
        )

        # --- Act 2: Plot Development ---
        act2_cuts = cuts[idx_act1_end:idx_act2_end]
        half_act2 = len(act2_cuts) // 2
        beats.append(
            ReviewStoryBeat(
                beat_id="beat_03",
                sequence=3,
                act_type=ActType.PLOT_DEVELOPMENT,
                voiceover_text=f"As our protagonist navigates the unfolding crisis, critical details and character dynamics begin to surface, raising the stakes to a boiling point.",
                emotion="SERIOUS",
                assigned_cut_ids=[c.cut_id for c in act2_cuts[:half_act2]] if half_act2 > 0 else [cuts[0].cut_id],
            )
        )
        beats.append(
            ReviewStoryBeat(
                beat_id="beat_04",
                sequence=4,
                act_type=ActType.PLOT_DEVELOPMENT,
                voiceover_text=f"The tactical dialogue and shifting alliances keep the momentum relentless, testing both resolve and survival instincts.",
                emotion="SUSPENSEFUL",
                assigned_cut_ids=[c.cut_id for c in act2_cuts[half_act2:]] if half_act2 > 0 else [cuts[0].cut_id],
            )
        )

        # --- Act 3: Key Battle & Turning Point Climax ---
        act3_cuts = cuts[idx_act2_end:idx_act3_end]
        half_act3 = len(act3_cuts) // 2
        beats.append(
            ReviewStoryBeat(
                beat_id="beat_05",
                sequence=5,
                act_type=ActType.KEY_BATTLE,
                voiceover_text=f"Then comes the centerpiece encounter of the entire episode. The animation ramps up with breathtaking choreography and raw power on full display.",
                emotion="DETERMINED",
                assigned_cut_ids=[c.cut_id for c in act3_cuts[:half_act3]] if half_act3 > 0 else [cuts[0].cut_id],
            )
        )
        beats.append(
            ReviewStoryBeat(
                beat_id="beat_06",
                sequence=6,
                act_type=ActType.TURNING_POINT_CLIMAX,
                voiceover_text=f"In a stunning turning point, a hidden trump card alters the entire battlefield, leaving no doubt that the story has reached a whole new tier.",
                emotion="EXCITED",
                assigned_cut_ids=[c.cut_id for c in act3_cuts[half_act3:]] if half_act3 > 0 else [cuts[0].cut_id],
            )
        )

        # --- Act 4: Reviewer Verdict & Teaser ---
        act4_cuts = cuts[idx_act3_end:]
        beats.append(
            ReviewStoryBeat(
                beat_id="beat_07",
                sequence=7,
                act_type=ActType.REVIEWER_VERDICT,
                voiceover_text=f"Overall, this episode delivers stellar pacing and impactful visual flair, making it one of the strongest installments of the season.",
                emotion="CALM",
                assigned_cut_ids=[c.cut_id for c in act4_cuts[: len(act4_cuts) // 2]] if act4_cuts else [cuts[0].cut_id],
            )
        )
        beats.append(
            ReviewStoryBeat(
                beat_id="beat_08",
                sequence=8,
                act_type=ActType.REVIEWER_VERDICT,
                voiceover_text=f"With that cliffhanger ending, expectations for the next episode are through the roof. Make sure to subscribe and drop your thoughts in the comments below!",
                emotion="EXCITED",
                assigned_cut_ids=[c.cut_id for c in act4_cuts[len(act4_cuts) // 2 :]] if act4_cuts else [cuts[0].cut_id],
            )
        )

        return beats
