import re

with open('tests/unit/test_storyboard_asset_reuse.py', 'r') as f:
    content = f.read()

# Pattern: find the script addition, then segments, then scene creation
pattern = (r'(        db\.add\(script\)\n'
           r'        # 5 segments across 2 scenes - use the dynamic scene IDs\n'
           r'        segments = \[\n'
           r'            \(f"seg-1-\{uuid\.uuid4\(\)\.hex\[:8\]\}", scene1_id, 1, "CHARACTER_DIALOGUE", "Hero enters the ruins\.", "NEUTRAL", 0\.5, 3\.0\),\n'
           r'            \(f"seg-2-\{uuid\.uuid4\(\)\.hex\[:8\]\}", scene1_id, 2, "NARRATION", "The ancient stones glow\.", "MYSTERIOUS", 0\.6, 4\.0\),\n'
           r'            \(f"seg-3-\{uuid\.uuid4\(\)\.hex\[:8\]\}", scene1_id, 3, "CHARACTER_DIALOGUE", "I sense danger ahead\.", "TENSE", 0\.8, 3\.5\),\n'
           r'            \(f"seg-4-\{uuid\.uuid4\(\)\.hex\[:8\]\}", scene2_id, 1, "NARRATION", "A guardian awakens\.", "DRAMATIC", 0\.7, 4\.5\),\n'
           r'            \(f"seg-5-\{uuid\.uuid4\(\)\.hex\[:8\]\}", scene2_id, 2, "CHARACTER_DIALOGUE", "We must fight\!", "EXCITED", 0\.9, 3\.0\),\n'
           r'        \]\n'
           r'        for seg_id, scene_id, seq, seg_type, text, emotion, intensity, dur in segments:\n'
           r'            db\.add\(ScriptSegmentRecord\(\n'
           r'                id=seg_id, script_id="script-1", project_id=project_id,\n'
           r'                scene_id=scene_id, sequence=seq, type=seg_type,\n'
           r'                speaker_character_id=None, text=text, emotion=emotion,\n'
           r'                intensity=intensity, estimated_duration=dur,\n'
           r'                estimated_start=0\.0, estimated_end=dur,\n'
           r'                source_evidence=\{\}, production_intent="",\n'
           r'            \)\)\n'
           r'        # Scenes - use unique IDs per test run\n'
           r'        scene1_id = f"scene-1-\{uuid\.uuid4\(\)\.hex\[:8\]\}"\n'
           r'        scene2_id = f"scene-2-\{uuid\.uuid4\(\)\.hex\[:8\]\}"\n'
           r'        # Use first panel of first page as scene-1 start, last panel of first page as scene-1 end\n'
           r'        # Use first panel of second page as scene-2 start, last panel of third page as scene-2 end\n'
           r'        scene1_start = panel_ids_by_page\[0\]\[0\] if panel_ids_by_page\[0\] else page_ids\[0\]\n'
           r'        scene1_end = panel_ids_by_page\[0\]\[-1\] if panel_ids_by_page\[0\] else page_ids\[0\]\n'
           r'        scene2_start = panel_ids_by_page\[1\]\[0\] if len\(panel_ids_by_page\) > 1 and panel_ids_by_page\[1\] else page_ids\[1\]\n'
           r'        scene2_end = panel_ids_by_page\[-1\]\[-1\] if panel_ids_by_page\[-1\] else page_ids\[-1\]\n'
           r'        \n'
           r'        db\.add\(SceneRecord\(\n'
           r'            id=scene1_id, project_id=project_id, sequence=1,\n'
           r'            title="The Ruins", panel_start=scene1_start, panel_end=scene1_end,\n'
           r'            character_ids=\[\], summary="Hero explores ruins\.",\n'
           r'        \)\)\n'
           r'        db\.add\(SceneRecord\(\n'
           r'            id=scene2_id, project_id=project_id, sequence=2,\n'
           r'            title="The Guardian", panel_start=scene2_start, panel_end=scene2_end,\n'
           r'            character_ids=\[\], summary="Guardian battle\.",\n'
           r'        \)\))')

replacement = ('''        db.add(script)
        # Scenes - use unique IDs per test run
        scene1_id = f"scene-1-{uuid.uuid4().hex[:8]}"
        scene2_id = f"scene-2-{uuid.uuid4().hex[:8]}"
        # Use first panel of first page as scene-1 start, last panel of first page as scene-1 end
        # Use first panel of second page as scene-2 start, last panel of third page as scene-2 end
        scene1_start = panel_ids_by_page[0][0] if panel_ids_by_page[0] else page_ids[0]
        scene1_end = panel_ids_by_page[0][-1] if panel_ids_by_page[0] else page_ids[0]
        scene2_start = panel_ids_by_page[1][0] if len(panel_ids_by_page) > 1 and panel_ids_by_page[1] else page_ids[1]
        scene2_end = panel_ids_by_page[-1][-1] if panel_ids_by_page[-1] else page_ids[-1]
        
        db.add(SceneRecord(
            id=scene1_id, project_id=project_id, sequence=1,
            title="The Ruins", panel_start=scene1_start, panel_end=scene1_end,
            character_ids=[], summary="Hero explores ruins.",
        ))
        db.add(SceneRecord(
            id=scene2_id, project_id=project_id, sequence=2,
            title="The Guardian", panel_start=scene2_start, panel_end=scene2_end,
            character_ids=[], summary="Guardian battle.",
        ))
        # 5 segments across 2 scenes - use the dynamic scene IDs
        segments = [
            (f"seg-1-{uuid.uuid4().hex[:8]}", scene1_id, 1, "CHARACTER_DIALOGUE", "Hero enters the ruins.", "NEUTRAL", 0.5, 3.0),
            (f"seg-2-{uuid.uuid4().hex[:8]}", scene1_id, 2, "NARRATION", "The ancient stones glow.", "MYSTERIOUS", 0.6, 4.0),
            (f"seg-3-{uuid.uuid4().hex[:8]}", scene1_id, 3, "CHARACTER_DIALOGUE", "I sense danger ahead.", "TENSE", 0.8, 3.5),
            (f"seg-4-{uuid.uuid4().hex[:8]}", scene2_id, 1, "NARRATION", "A guardian awakens.", "DRAMATIC", 0.7, 4.5),
            (f"seg-5-{uuid.uuid4().hex[:8]}", scene2_id, 2, "CHARACTER_DIALOGUE", "We must fight!", "EXCITED", 0.9, 3.0),
        ]
        for seg_id, scene_id, seq, seg_type, text, emotion, intensity, dur in segments:
            db.add(ScriptSegmentRecord(
                id=seg_id, script_id="script-1", project_id=project_id,
                scene_id=scene_id, sequence=seq, type=seg_type,
                speaker_character_id=None, text=text, emotion=emotion,
                intensity=intensity, estimated_duration=dur,
                estimated_start=0.0, estimated_end=dur,
                source_evidence={}, production_intent="",
            ))''')

content = re.sub(pattern, replacement, content, flags=re.DOTALL)

with open('tests/unit/test_storyboard_asset_reuse.py', 'w') as f:
    f.write(content)

print('Fixed using regex')