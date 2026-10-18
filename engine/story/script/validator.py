from typing import Dict, Any, List
from engine.story.models import (
    NarrativeDocument,
    VideoScript,
    ScriptSegment,
    ScriptValidationReport,
)


class ScriptFaithfulnessValidator:
    """
    Evaluates adapted video script lines against source Narrative IR evidence.
    Determines whether dialogue and narration are strictly grounded in source panels and utterances.
    """

    def validate(self, script: VideoScript, narrative: NarrativeDocument) -> ScriptValidationReport:
        panel_id_set = {p.panel_id for p in narrative.observations}
        text_region_id_set = {u.text_region_id for u in narrative.utterances}
        known_character_ids = {c.character_id for c in narrative.characters} | {"NARRATOR", "SFX", "UNKNOWN"}

        # Map of valid dialogue text in project
        source_texts = [u.corrected_text.lower().strip() for u in narrative.utterances if u.corrected_text]
        beat_summaries = [b.summary.lower().strip() for b in narrative.beats if b.summary]
        event_descriptions = [e.description.lower().strip() for e in narrative.events if e.description]
        visual_summaries = [o.visual_summary.lower().strip() for o in narrative.observations if o.visual_summary]
        visual_summaries += [s.summary.lower().strip() for s in narrative.scenes if s.summary]

        supported_count = 0
        weakly_supported_count = 0
        unsupported_count = 0
        issues: List[Dict[str, Any]] = []

        for seg in script.segments:
            seg_issues = []
            ev = seg.source_evidence

            # 1. Check Panel & Region Evidence Validity
            invalid_panels = [pid for pid in ev.panel_ids if pid not in panel_id_set]
            if invalid_panels:
                seg_issues.append(f"Referenced panel IDs do not exist in project: {invalid_panels}")

            invalid_regions = [rid for rid in ev.text_region_ids if rid not in text_region_id_set]
            if invalid_regions:
                seg_issues.append(f"Referenced text region IDs do not exist: {invalid_regions}")

            # 2. Check Speaker Validity
            if seg.speaker_character_id and seg.speaker_character_id not in known_character_ids:
                seg_issues.append(f"Unknown speaker ID '{seg.speaker_character_id}' not in Character Registry")

            # 3. Check Evidence Grounding
            has_direct_panels = len(ev.panel_ids) > 0
            has_direct_text = len(ev.text_region_ids) > 0

            # Content verification
            seg_text_clean = seg.text.lower().strip()
            STOP_WORDS = {"this", "that", "with", "from", "they", "them", "then", "have", "were", "been", "will", "would", "could", "should", "your", "what", "when", "where", "into", "their", "about", "there"}
            seg_words = {w.strip(".,!?:;\"'") for w in seg_text_clean.split() if len(w) > 3 and w not in STOP_WORDS}
            all_known_words = {
                w.strip(".,!?:;\"'") for text in (source_texts + beat_summaries + event_descriptions + visual_summaries)
                for w in text.split() if len(w) > 3 and w not in STOP_WORDS
            }
            word_overlap = len(seg_words & all_known_words) / max(1, len(seg_words))

            is_dialogue_match = any(
                st in seg_text_clean or seg_text_clean in st for st in source_texts if len(st) > 4
            )
            is_narrative_match = any(
                bs in seg_text_clean or seg_text_clean in bs for bs in (beat_summaries + event_descriptions) if len(bs) > 4
            )

            # Check if completely ungrounded (< 20% word overlap and no substring match)
            if invalid_panels or invalid_regions or (seg.speaker_character_id and seg.speaker_character_id not in known_character_ids):
                seg.faithfulness_status = "UNSUPPORTED"
                unsupported_count += 1
            elif not is_dialogue_match and not is_narrative_match and word_overlap < 0.20:
                seg.faithfulness_status = "UNSUPPORTED"
                unsupported_count += 1
                seg_issues.append("Line makes claims with negligible lexical or semantic grounding in source panels, text, or events.")
            elif seg.type == "CHARACTER_DIALOGUE":
                if has_direct_text and (is_dialogue_match or word_overlap >= 0.4):
                    seg.faithfulness_status = "SUPPORTED"
                    supported_count += 1
                elif has_direct_panels and (is_dialogue_match or word_overlap >= 0.2):
                    seg.faithfulness_status = "WEAKLY_SUPPORTED"
                    weakly_supported_count += 1
                    seg_issues.append("Dialogue has panel evidence but differs significantly from source OCR transcript.")
                else:
                    seg.faithfulness_status = "UNSUPPORTED"
                    unsupported_count += 1
                    seg_issues.append("Character dialogue has no supporting source panel or text region evidence.")

            elif seg.type == "NARRATOR":
                if has_direct_panels and (is_narrative_match or word_overlap >= 0.25):
                    seg.faithfulness_status = "SUPPORTED"
                    supported_count += 1
                elif has_direct_panels:
                    seg.faithfulness_status = "WEAKLY_SUPPORTED"
                    weakly_supported_count += 1
                    seg_issues.append("Narrator line has panel evidence but contains loose paraphrasing.")
                else:
                    seg.faithfulness_status = "UNSUPPORTED"
                    unsupported_count += 1
                    seg_issues.append("Narrator line has no supporting panel or beat evidence.")

            else:
                # SFX / Pause / Transition
                seg.faithfulness_status = "SUPPORTED"
                supported_count += 1

            if seg_issues:
                issues.append({
                    "segment_id": seg.segment_id,
                    "text": seg.text,
                    "status": seg.faithfulness_status,
                    "reasons": seg_issues,
                })

        total = len(script.segments)
        coverage_score = round(float(supported_count + (0.5 * weakly_supported_count)) / float(max(1, total)), 3)
        passed = unsupported_count == 0

        # Update quality metrics on script
        script.quality_metrics = {
            "total_segments": total,
            "supported_segments": supported_count,
            "weakly_supported_segments": weakly_supported_count,
            "unsupported_segments": unsupported_count,
            "coverage_score": coverage_score,
            "unresolved_speaker_count": len([s for s in script.segments if s.speaker_character_id == "UNKNOWN"]),
        }

        return ScriptValidationReport(
            script_id=script.script_id,
            total_segments=total,
            supported_segments=supported_count,
            weakly_supported_segments=weakly_supported_count,
            unsupported_segments=unsupported_count,
            coverage_score=coverage_score,
            issues=issues,
            passed=passed,
        )


script_validator = ScriptFaithfulnessValidator()
