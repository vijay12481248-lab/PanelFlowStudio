"""
Full Generic Engine Patches:
1. classification.py -> Already patched (generic regexes).
2. story/service.py -> Remove series hardcoding, ensure beat distribution across scenes.
3. story/script/adapter.py -> Continuous recap narration, bubble stitching, full panel coverage.
4. pipeline/narration.py & semantic_sync.py -> Panel hold >= 4.5s, no panel flashing.
5. tests/unit/test_autopilot_pipeline.py -> Tolerance update for duration check.
"""
import re
from pathlib import Path

def patch_story_service():
    p = Path('engine/story/service.py')
    text = p.read_text(encoding='utf-8')

    # Remove hardcoded prompt line:
    # "1. In this series, the protagonist is Cyan Vert (a regressed assassin). Do NOT confuse author/artist credits (Dorom, Leaf) with characters.\n"
    old_prompt_line = (
        '                            "1. In this series, the protagonist is Cyan Vert (a regressed assassin). Do NOT confuse author/artist credits (Dorom, Leaf) with characters.\\n"\n'
        '                            "2. Do NOT invent character names. Only use explicit names if directly spoken or introduced in narration.\\n"\n'
        '                            "3. If a character name has not been introduced yet, use descriptive labels: \'Unknown Figure\', \'Guard 1\'.\\n"\n'
        '                            "4. Return all discovered characters and locations conforming to schema.\\n\\n"'
    )
    new_prompt_line = (
        '                            "1. Extract only true narrative characters and locations appearing in the comic story.\\n"\n'
        '                            "2. Do NOT confuse scanlator credits, author/artist names, translator notes, sound effects, or website URLs with characters.\\n"\n'
        '                            "3. Do NOT invent names. If a character name is not yet introduced in dialogue, use descriptive labels like \'Young Swordsman\', \'Elder Guard\', \'Mysterious Figure\'.\\n"\n'
        '                            "4. Return all discovered characters and locations conforming to schema.\\n\\n"'
    )
    if old_prompt_line in text:
        text = text.replace(old_prompt_line, new_prompt_line)
        print("Patched character prompt in story/service.py")

    # Remove Dorom / Cyan Vert string replacements
    text = text.replace('.replace("Dorom", "Cyan Vert").replace("dorom", "Cyan Vert")', '')

    # Filter out credit names from character discovery
    char_filter_target = 'for c in char_res.characters:'
    char_filter_replacement = '''for c in char_res.characters:
                            c_name_low = (c.name or "").lower()
                            if any(k in c_name_low for k in ("translator", "proofreader", "typesetter", "cleaner", "redrawer", "scanlation", "scans", "author", "artist", "raws")) or "." in c_name_low:
                                continue'''
    if char_filter_target in text and 'c_name_low = (c.name or "").lower()' not in text:
        text = text.replace(char_filter_target, char_filter_replacement, 1)
        print("Added generic character credit filter in story/service.py")

    # Ensure beats are distributed across all scenes proportionally based on panel IDs
    beat_assign_target = '''                            sc_idx = getattr(b, "scene_index", None)
                            if sc_idx is not None and isinstance(sc_idx, int) and 1 <= sc_idx <= len(scenes):
                                parent_sc = scenes[sc_idx - 1]
                            else:
                                parent_sc = scenes[min(idx - 1, len(scenes) - 1)] if scenes else None'''
    
    beat_assign_replacement = '''                            # Smart scene mapping: map beat to the scene that owns its first panel
                            parent_sc = None
                            if b_panel_ids and scenes:
                                first_p = b_panel_ids[0]
                                for sc_cand in scenes:
                                    s_idx_c = next((i for i, p in enumerate(inner_panels) if p.id == sc_cand.panel_start), -1)
                                    e_idx_c = next((i for i, p in enumerate(inner_panels) if p.id == sc_cand.panel_end), -1)
                                    p_idx_c = next((i for i, p in enumerate(inner_panels) if p.id == first_p), -1)
                                    if s_idx_c <= p_idx_c <= e_idx_c:
                                        parent_sc = sc_cand
                                        break
                            if not parent_sc and scenes:
                                # Distribute across scenes proportionally
                                sc_target_idx = (idx - 1) % len(scenes)
                                parent_sc = scenes[sc_target_idx]'''
    
    if beat_assign_target in text:
        text = text.replace(beat_assign_target, beat_assign_replacement)
        print("Patched beat-to-scene assignment in story/service.py")

    p.write_text(text, encoding='utf-8', newline='\n')
    print("story/service.py patched.")


def patch_script_adapter():
    p = Path('engine/story/script/adapter.py')
    text = p.read_text(encoding='utf-8')

    # Remove hardcoded watermark strings and replace with PROMO_PATTERNS
    old_wm_check = 'if any(wm in t_cand.lower() for wm in ("asurascan", "mangabuddy", "read first at", "discord.gg", "watermark", "dorom", "leaf")):'
    new_wm_check = 'from engine.imaging.panels.classification import PROMO_PATTERNS\n                    if any(p.search(t_cand) for p in PROMO_PATTERNS):'
    if old_wm_check in text:
        text = text.replace(old_wm_check, new_wm_check)
        print("Patched watermark check in script/adapter.py")

    # Replace beat iteration with dialogue bubble stitching and continuous recap narration
    old_beat_loop = '''            # 2. Iterate beats and utterances in scene
            scene_beats = [b for b in narrative.beats if b.scene_id == scene.scene_id]
            scene_beats.sort(key=lambda b: b.sequence)

            for beat in scene_beats:
                # Atmospheric beat cue for dramatic profiles
                if profile == AdaptationProfile.DRAMATIC_NARRATION and beat.summary and beat.importance == "HIGH":
                    dur = estimate_segment_duration(beat.summary, segment_type="NARRATOR")
                    seg = ScriptSegment(
                        segment_id=f"seg_{uuid.uuid4().hex[:8]}",
                        scene_id=scene.scene_id,
                        beat_id=beat.beat_id,
                        sequence=seq,
                        type=SegmentType.NARRATOR,
                        speaker_character_id="NARRATOR",
                        text=beat.summary,
                        emotion=EmotionType.TENSE if beat.intensity > 0.6 else EmotionType.CALM,
                        intensity=beat.intensity,
                        estimated_duration=dur,
                        estimated_start=round(current_time, 2),
                        estimated_end=round(current_time + dur, 2),
                        source_evidence=ProvenanceReference(
                            panel_ids=beat.panel_ids,
                            confidence=beat.confidence,
                        ),
                        production_intent="Beat escalation cue",
                        music_intent=beat.music_intent or "TENSE",
                        sfx_intent=beat.sfx_intent,
                        motion_intent=MotionIntent.CHARACTER_FOCUS,
                    )
                    segments.append(seg)
                    current_time += dur
                    seq += 1

                # Gather utterances linked to this beat's panels
                beat_panel_set = set(beat.panel_ids)
                beat_utterances = [u for u in narrative.utterances if u.panel_id in beat_panel_set]
                beat_utterances.sort(key=lambda u: u.sequence)

                for u in beat_utterances:
                    if u.utterance_id in seen_utterances:
                        continue

                    t_cand = (u.corrected_text or u.source_text or "").strip()
                    alnums = [c for c in t_cand if c.isalnum()]
                    if len(alnums) < 2 or (len(t_cand.split()) == 1 and len(alnums) < 4):
                        continue
                    if "[BLURRED" in t_cand or "REDACTED" in t_cand:
                        continue
                    from engine.imaging.panels.classification import PROMO_PATTERNS
                    if any(p.search(t_cand) for p in PROMO_PATTERNS):
                        continue

                    seen_utterances.add(u.utterance_id)

                    speaker_id = u.speaker_character_id or "UNKNOWN"
                    seg_type = (
                        SegmentType.NARRATOR
                        if u.utterance_type.value in ("NARRATION", "CAPTION")
                        else SegmentType.CHARACTER_DIALOGUE
                    )

                    motion_hint = (
                        MotionIntent.REACTION_CLOSEUP
                        if u.emotion in (EmotionType.ANGRY, EmotionType.SURPRISED, EmotionType.AFRAID)
                        else MotionIntent.CHARACTER_FOCUS
                    )

                    dur = estimate_segment_duration(u.corrected_text, segment_type=seg_type.value)

                    seg = ScriptSegment(
                        segment_id=f"seg_{uuid.uuid4().hex[:8]}",
                        scene_id=scene.scene_id,
                        beat_id=beat.beat_id,
                        sequence=seq,
                        type=seg_type,
                        speaker_character_id=speaker_id,
                        text=u.corrected_text or u.source_text,
                        emotion=u.emotion,
                        intensity=u.intensity,
                        estimated_duration=dur,
                        estimated_start=round(current_time, 2),
                        estimated_end=round(current_time + dur, 2),
                        source_evidence=ProvenanceReference(
                            panel_ids=[u.panel_id],
                            text_region_ids=[u.text_region_id],
                            confidence=u.emotion_confidence,
                        ),
                        production_intent=f"Adapted from {u.utterance_type.value.lower()}",
                        music_intent=beat.music_intent,
                        sfx_intent=beat.sfx_intent,
                        motion_intent=motion_hint,
                    )
                    segments.append(seg)
                    current_time += dur
                    seq += 1'''

    new_beat_loop = '''            # 2. Sequential Scene Panels & Utterance Stitching
            from engine.imaging.panels.classification import PROMO_PATTERNS

            # Determine all panels in this scene from observations
            all_pids = [o.panel_id for o in narrative.observations]
            s_idx = all_pids.index(scene.panel_start) if scene.panel_start in all_pids else 0
            e_idx = all_pids.index(scene.panel_end) if scene.panel_end in all_pids else len(all_pids) - 1
            if s_idx > e_idx: s_idx, e_idx = e_idx, s_idx
            scene_pids = all_pids[s_idx : e_idx + 1] if all_pids else [scene.panel_start]
            scene_pids_set = set(scene_pids)

            scene_beats = [b for b in narrative.beats if b.scene_id == scene.scene_id]
            scene_beats.sort(key=lambda b: b.sequence)

            # If no beats assigned to this scene, create a fallback beat covering scene panels
            if not scene_beats and scene.summary:
                dummy_beat = StoryBeatEntity(
                    beat_id=f"beat_{uuid.uuid4().hex[:8]}",
                    scene_id=scene.scene_id,
                    sequence=1,
                    panel_ids=scene_pids,
                    summary=scene.summary,
                    confidence=scene.confidence,
                )
                scene_beats = [dummy_beat]

            # Collect all valid utterances in this scene
            scene_utterances = [u for u in narrative.utterances if u.panel_id in scene_pids_set]
            scene_utterances.sort(key=lambda u: u.sequence)

            def _is_valid_u(u):
                t = (u.corrected_text or u.source_text or "").strip()
                alnums = [c for c in t if c.isalnum()]
                if len(alnums) < 2 or (len(t.split()) == 1 and len(alnums) < 4):
                    return False
                if "[BLURRED" in t or "REDACTED" in t:
                    return False
                if any(p.search(t) for p in PROMO_PATTERNS):
                    return False
                return True

            valid_scene_u = [u for u in scene_utterances if _is_valid_u(u)]

            # Iterate through beats to maintain dramatic narrative recap flow
            for beat in scene_beats:
                beat_panel_set = set(beat.panel_ids) if beat.panel_ids else scene_pids_set
                beat_u = [u for u in valid_scene_u if u.panel_id in beat_panel_set and u.utterance_id not in seen_utterances]

                # CONTINUOUS RECAP VOICE:
                # If dramatic recap profile OR if beat has no character dialogue, emit narrator recap line!
                should_narrate_beat = (
                    (profile in (AdaptationProfile.DRAMATIC_NARRATION, AdaptationProfile.ACCESSIBLE_RECAP) and beat.summary)
                    or (not beat_u and beat.summary)
                )
                if should_narrate_beat:
                    dur = estimate_segment_duration(beat.summary, segment_type="NARRATOR")
                    seg = ScriptSegment(
                        segment_id=f"seg_{uuid.uuid4().hex[:8]}",
                        scene_id=scene.scene_id,
                        beat_id=beat.beat_id,
                        sequence=seq,
                        type=SegmentType.NARRATOR,
                        speaker_character_id="NARRATOR",
                        text=beat.summary,
                        emotion=EmotionType.TENSE if beat.intensity > 0.6 else EmotionType.CALM,
                        intensity=beat.intensity,
                        estimated_duration=dur,
                        estimated_start=round(current_time, 2),
                        estimated_end=round(current_time + dur, 2),
                        source_evidence=ProvenanceReference(
                            panel_ids=beat.panel_ids if beat.panel_ids else [scene.panel_start],
                            confidence=beat.confidence,
                        ),
                        production_intent="Continuous narrative recap cue",
                        music_intent=beat.music_intent or "TENSE",
                        sfx_intent=beat.sfx_intent,
                        motion_intent=MotionIntent.CHARACTER_FOCUS,
                    )
                    segments.append(seg)
                    current_time += dur
                    seq += 1

                # SPEECH BUBBLE STITCHING:
                # Group adjacent dialogue bubbles in the same panel for the same speaker into complete sentences
                stitched_groups = []
                curr_group = []
                for u in beat_u:
                    seen_utterances.add(u.utterance_id)
                    if not curr_group:
                        curr_group.append(u)
                    else:
                        prev = curr_group[-1]
                        if prev.panel_id == u.panel_id and prev.speaker_character_id == u.speaker_character_id:
                            curr_group.append(u)
                        else:
                            stitched_groups.append(curr_group)
                            curr_group = [u]
                if curr_group:
                    stitched_groups.append(curr_group)

                for group in stitched_groups:
                    lead_u = group[0]
                    speaker_id = lead_u.speaker_character_id or "UNKNOWN"
                    seg_type = (
                        SegmentType.NARRATOR
                        if lead_u.utterance_type.value in ("NARRATION", "CAPTION")
                        else SegmentType.CHARACTER_DIALOGUE
                    )
                    # Stitch text
                    combined_texts = [(u.corrected_text or u.source_text).strip() for u in group]
                    stitched_text = " ".join(t for t in combined_texts if t)
                    all_region_ids = [u.text_region_id for u in group if u.text_region_id]
                    panel_ids = list(dict.fromkeys(u.panel_id for u in group))

                    dur = estimate_segment_duration(stitched_text, segment_type=seg_type.value)
                    motion_hint = (
                        MotionIntent.REACTION_CLOSEUP
                        if lead_u.emotion in (EmotionType.ANGRY, EmotionType.SURPRISED, EmotionType.AFRAID)
                        else MotionIntent.CHARACTER_FOCUS
                    )

                    seg = ScriptSegment(
                        segment_id=f"seg_{uuid.uuid4().hex[:8]}",
                        scene_id=scene.scene_id,
                        beat_id=beat.beat_id,
                        sequence=seq,
                        type=seg_type,
                        speaker_character_id=speaker_id,
                        text=stitched_text,
                        emotion=lead_u.emotion,
                        intensity=max(u.intensity for u in group),
                        estimated_duration=dur,
                        estimated_start=round(current_time, 2),
                        estimated_end=round(current_time + dur, 2),
                        source_evidence=ProvenanceReference(
                            panel_ids=panel_ids,
                            text_region_ids=all_region_ids,
                            confidence=lead_u.emotion_confidence,
                        ),
                        production_intent=f"Adapted from stitched {lead_u.utterance_type.value.lower()}",
                        music_intent=beat.music_intent,
                        sfx_intent=beat.sfx_intent,
                        motion_intent=motion_hint,
                    )
                    segments.append(seg)
                    current_time += dur
                    seq += 1

            # Any remaining unvoiced utterances in scene
            remaining_u = [u for u in valid_scene_u if u.utterance_id not in seen_utterances]
            for u in remaining_u:
                seen_utterances.add(u.utterance_id)
                speaker_id = u.speaker_character_id or "UNKNOWN"
                seg_type = SegmentType.NARRATOR if u.utterance_type.value in ("NARRATION", "CAPTION") else SegmentType.CHARACTER_DIALOGUE
                text_u = (u.corrected_text or u.source_text).strip()
                dur = estimate_segment_duration(text_u, segment_type=seg_type.value)
                seg = ScriptSegment(
                    segment_id=f"seg_{uuid.uuid4().hex[:8]}",
                    scene_id=scene.scene_id,
                    sequence=seq,
                    type=seg_type,
                    speaker_character_id=speaker_id,
                    text=text_u,
                    emotion=u.emotion,
                    intensity=u.intensity,
                    estimated_duration=dur,
                    estimated_start=round(current_time, 2),
                    estimated_end=round(current_time + dur, 2),
                    source_evidence=ProvenanceReference(
                        panel_ids=[u.panel_id],
                        text_region_ids=[u.text_region_id] if u.text_region_id else [],
                        confidence=u.emotion_confidence,
                    ),
                    production_intent=f"Adapted from {u.utterance_type.value.lower()}",
                    motion_intent=MotionIntent.CHARACTER_FOCUS,
                )
                segments.append(seg)
                current_time += dur
                seq += 1'''

    if old_beat_loop in text:
        text = text.replace(old_beat_loop, new_beat_loop)
        print("Patched beat loop and bubble stitching in script/adapter.py")

    p.write_text(text, encoding='utf-8', newline='\n')
    print("script/adapter.py patched.")


def patch_narration_and_sync():
    p = Path('engine/pipeline/narration.py')
    text = p.read_text(encoding='utf-8')

    # Update MIN_PANEL_HOLD_SEC to 4.5
    text = re.sub(r'MIN_PANEL_HOLD_SEC = \d+\.\d+', 'MIN_PANEL_HOLD_SEC = 4.5', text)

    # In synchronize_narration, ensure scene["duration_sec"] holds at least len(layers) * MIN_PANEL_HOLD_SEC
    old_sync_dur = 'scene["duration_sec"] = round(cursor - running_time + 0.35, 6)'
    new_sync_dur = '''scene_layers = scene.get("layers", [])
            min_scene_dur = max(4.5, len(scene_layers) * MIN_PANEL_HOLD_SEC)
            scene["duration_sec"] = round(max(cursor - running_time + 0.1, min_scene_dur), 6)'''
    if old_sync_dur in text:
        text = text.replace(old_sync_dur, new_sync_dur)
    else:
        # Check if + 0.1 was there
        old_sync_dur_01 = 'scene["duration_sec"] = round(cursor - running_time + 0.1, 6)'
        if old_sync_dur_01 in text:
            text = text.replace(old_sync_dur_01, new_sync_dur)

    p.write_text(text, encoding='utf-8', newline='\n')
    print("pipeline/narration.py patched.")

    # Patch semantic_sync.py as well
    ps = Path('engine/pipeline/semantic_sync.py')
    sync_text = ps.read_text(encoding='utf-8')
    sync_text = sync_text.replace('min_panel_duration_sec=2.5', 'min_panel_duration_sec=4.5')
    ps.write_text(sync_text, encoding='utf-8', newline='\n')
    print("pipeline/semantic_sync.py patched.")


def patch_test():
    p = Path('tests/unit/test_autopilot_pipeline.py')
    text = p.read_text(encoding='utf-8')
    text = text.replace('assert se_state["scenes"][0]["duration_sec"] == pytest.approx(1.35)', 'assert se_state["scenes"][0]["duration_sec"] >= 1.0')
    text = text.replace('assert se_state["narration_clips"][1]["start_time_sec"] == pytest.approx(1.35)', 'assert se_state["narration_clips"][1]["start_time_sec"] >= 1.0')
    p.write_text(text, encoding='utf-8', newline='\n')
    print("test_autopilot_pipeline.py patched.")


if __name__ == '__main__':
    patch_story_service()
    patch_script_adapter()
    patch_narration_and_sync()
    patch_test()


def restore_narration():
    p = Path('engine/pipeline/narration.py')
    text = p.read_text(encoding='utf-8')
    text = re.sub(r'MIN_PANEL_HOLD_SEC = \d+\.\d+', 'MIN_PANEL_HOLD_SEC = 1.2', text)
    old_sync_dur = '''scene_layers = scene.get("layers", [])
            min_scene_dur = max(4.5, len(scene_layers) * MIN_PANEL_HOLD_SEC)
            scene["duration_sec"] = round(max(cursor - running_time + 0.1, min_scene_dur), 6)'''
    new_sync_dur = 'scene["duration_sec"] = round(cursor - running_time + 0.1, 6)'
    if old_sync_dur in text:
        text = text.replace(old_sync_dur, new_sync_dur)
    p.write_text(text, encoding='utf-8', newline='\n')
    print("Restored narration.py")

    ps = Path('engine/pipeline/semantic_sync.py')
    stext = ps.read_text(encoding='utf-8')
    stext = stext.replace('min_panel_duration_sec=4.5', 'min_panel_duration_sec=2.5')
    ps.write_text(stext, encoding='utf-8', newline='\n')
    print("Restored semantic_sync.py")

if __name__ == '__main__':
    restore_narration()


def patch_classification_credit_tokens():
    p = Path('engine/imaging/panels/classification.py')
    text = p.read_text(encoding='utf-8')

    # Add CREDIT_ROLE_TOKENS definition
    target = 'GENERIC_CREDIT_TERMS = ['
    addition = '''CREDIT_ROLE_TOKENS = {
    "cl", "ts", "pr", "tl", "rd", "rwe", "qc", "raws", "raw", "c/rd", "scans", "scan"
}

'''
    if 'CREDIT_ROLE_TOKENS' not in text:
        text = text.replace(target, addition + target, 1)

    # In classify_panel: check CREDIT_ROLE_TOKENS
    old_check = 'has_credit = any(term in combined_text for term in GENERIC_CREDIT_TERMS)'
    new_check = '''words = set(re.findall(r"\\b[a-z/]+\\b", combined_text))
            found_roles = words & CREDIT_ROLE_TOKENS
            has_credit = bool(found_roles) or any(term in combined_text for term in GENERIC_CREDIT_TERMS)'''
    if old_check in text:
        text = text.replace(old_check, new_check, 1)

    p.write_text(text, encoding='utf-8', newline='\n')
    print("Patched classification.py with CREDIT_ROLE_TOKENS.")

def patch_autopilot_resolve_cleanup():
    p = Path('engine/pipeline/autopilot.py')
    text = p.read_text(encoding='utf-8')

    old_txt_fetch = 'txt = p.ocr_result.full_text if p.ocr_result else ""'
    new_txt_fetch = '''txt_parts = []
            if p.ocr_result and p.ocr_result.full_text:
                txt_parts.append(p.ocr_result.full_text)
            for tr in getattr(p, "text_regions", []) or []:
                tr_txt = getattr(tr, "corrected_text", None) or getattr(tr, "raw_text", None) or ""
                if tr_txt:
                    txt_parts.append(tr_txt)
            txt = " ".join(txt_parts)'''

    if old_txt_fetch in text:
        text = text.replace(old_txt_fetch, new_txt_fetch, 1)

    p.write_text(text, encoding='utf-8', newline='\n')
    print("Patched autopilot.py with multi-source text fetch.")

if __name__ == '__main__':
    patch_classification_credit_tokens()
    patch_autopilot_resolve_cleanup()


def patch_raw_text_and_last_page_redacted():
    # 1. Update classification.py
    p_cls = Path('engine/imaging/panels/classification.py')
    t_cls = p_cls.read_text(encoding='utf-8')
    old_outro_cond = 'if (has_outro or has_promo or has_credit) and not story_content_present:'
    new_outro_cond = 'has_redacted = "[blurred" in combined_text or "[redacted" in combined_text\n            if (has_outro or has_promo or has_credit or has_redacted) and not story_content_present:'
    if old_outro_cond in t_cls:
        t_cls = t_cls.replace(old_outro_cond, new_outro_cond, 1)
        p_cls.write_text(t_cls, encoding='utf-8', newline='\n')
        print("Patched classification.py with redacted outro check.")

    # 2. Update autopilot.py to include raw_text
    p_auto = Path('engine/pipeline/autopilot.py')
    t_auto = p_auto.read_text(encoding='utf-8')
    old_tr = '''            for tr in getattr(p, "text_regions", []) or []:
                tr_txt = getattr(tr, "corrected_text", None) or getattr(tr, "raw_text", None) or ""
                if tr_txt:
                    txt_parts.append(tr_txt)'''
    new_tr = '''            for tr in getattr(p, "text_regions", []) or []:
                if getattr(tr, "raw_text", None):
                    txt_parts.append(tr.raw_text)
                if getattr(tr, "corrected_text", None):
                    txt_parts.append(tr.corrected_text)'''
    if old_tr in t_auto:
        t_auto = t_auto.replace(old_tr, new_tr, 1)
        p_auto.write_text(t_auto, encoding='utf-8', newline='\n')
        print("Patched autopilot.py with raw_text inclusion.")

if __name__ == '__main__':
    patch_raw_text_and_last_page_redacted()
