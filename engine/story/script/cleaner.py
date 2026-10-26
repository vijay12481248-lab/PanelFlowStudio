import re
from typing import List
from engine.story.models import ScriptSegment, SegmentType, EmotionType
from engine.story.script.duration import estimate_segment_duration

REPLACEMENTS = [
    (r"\bHUPPY\b", "Hurry"),
    (r"\bDAO\b", "Dad"),
    (r"\bEVE[-]?PYONE\b", "everyone"),
    (r"\bAPE\b", "are"),
    (r"\beeTTlNe\b", "getting"),
    (r"\bLONeep\b", "longer"),
    (r"\bovep\b", "over"),
    (r"\bFOP\b", "for"),
    (r"\bePOUP\b", "group"),
    (r"\bPEAL[-]?LY\b", "really"),
    (r"\bOPEPATION\b", "operation"),
    (r"\bMATTEP\b", "matter"),
    (r"\bT HE EST\b", "the best"),
    (r"\bMOPE\b", "more"),
    (r"\bEASEP\b", "easier"),
    (r"\bTPICK\b", "trick"),
    (r"\bSTPATeey\b", "strategy"),
    (r"\bWATCHINe\b", "watching"),
    (r"\bFPOM\b", "from"),
    (r"\bge\b", "be"),
    (r"\beveN\b", "even"),
    (r"\bsucceeo\b", "succeed"),
    (r"\bSIP eu\b", "Sir Gu"),
    (r"\bSOPPY\b", "sorry"),
    (r"\beoT\b", "got"),
    (r"\bexclTeo\b", "excited"),
    (r"\bTHE[-]?Pe\b", "there"),
    (r"\buNcce\b|\burqcce\b|\burcce\b", "Uncle"),
    (r"\bPEST EASY\b", "rest easy"),
    (r"\bTHEPE'S\b", "There's"),
    (r"\bMANOP\b", "manor"),
    (r"\bCUT WHepe\b", "But where"),
    (r"\bave\b", "five"),
    (r"\beUAPD[S]?\b", "guard"),
    (r"\bPESTPICTEO\b", "restricted"),
    (r"\bOF COUPSE\b", "Of course"),
    (r"\bE[-]NDANeEPlNe\b", "endangering"),
    (r"\bBPOTHEPS\b", "brothers"),
    (r"\bTPEASUPY\b", "treasury"),
    (r"\bacceo\b", "packed"),
    (r"\bCAPPACKS\b", "barracks"),
    (r"\bPOTATE\b", "rotate"),
    (r"\bAPMOPY\b", "armory"),
    (r"\bDE[-]MONIC\b", "demonic"),
    (r"\bTPEASUPE[-]?S\b|\bTPEASUPE\b", "treasure"),
    (r"\bSPIPITUAC\b|\bSPIPITUAL\b", "spiritual"),
    (r"\bPPIVATE QUAPTEPS\b", "private quarters"),
    (r"\bCHICOPEN\b", "children"),
    (r"\bPAPTNEPS\b", "partners"),
    (r"\bPOTTEN\b", "rotten"),
    (r"\boeeeNEPATe\b", "degenerate"),
    (r"\bSCOUTINe\b", "scouting"),
    (r"\bHAEM\b", "harem"),
    (r"\bACPEAOY\b", "already"),
    (r"\bpopeeT\b", "forget"),
    (r"\bYOUP\b", "your"),
    (r"\bwtfe\b|\bwtf-e\b", "wife"),
    (r"\bWESTEPN LANDS\b", "Western Lands"),
    (r"\bEASTEPN LANDS\b|\bEASTE[-]PN LANDS\b", "Eastern Lands"),
    (r"\bgecAuse\b|\bgecause\b", "because"),
    (r"\beeNU!?NE\b", "genuine"),
    (r"\bHOPN Doe\b", "horn dog"),
    (r"\bSWOPD\b", "sword"),
    (r"\bSWOPDS\b", "swords"),
    (r"\bDOMINEEPlNe\b", "domineering"),
    (r"\bOPDINAPY\b", "ordinary"),
    (r"\bpeopce\b", "people"),
    (r"\bMALEVOLENT\b", "malevolent"),
    (r"\betqeeey\b|\bENepey\b", "energy"),
    (r"\becse\b", "else"),
    (r"\bDAMAee\b", "damage"),
    (r"\bME[-]PIDIANS\b", "meridians"),
    (r"\bgesT\b", "best"),
    (r"\bOUST\b", "just"),
    (r"\bPEPSONALCY\b", "personally"),
    (r"\bPUSH IT\b", "rush it"),
    (r"\bPICHT\b|\bPGHT\b|\bPl.HT\b", "right"),
    (r"\bPEST!?Ne 200M\b|\bPEST!?Ne POO\b", "resting room"),
    (r"\bTl.HT\b", "tight"),
    (r"\bOADE FALLS\b", "Jade Falls"),
    (r"\bPAPADISE\b", "paradise"),
    (r"\bPECUUAP\b", "peculiar"),
    (r"\bSOAPINe SWOPD\b|\bSOAPINe\b", "Soaring Sword"),
    (r"\bEAPCEP\b", "Earlier"),
    (r"\bTAPeeT\b", "target"),
    (r"\bEFFOPTS\b", "efforts"),
    (r"\bPPECISECY\b", "precisely"),
    (r"\bsepvlce\b", "service"),
    (r"\bHICHEST\b", "highest"),
    (r"\bPOWEPS\b", "powers"),
    (r"\bOOUPNEY\b", "journey"),
    (r"\bCENTPAL APEA\b", "Central Area"),
    (r"\bTPAITOP\b", "traitor"),
    (r"\bstNce\b", "since"),
    (r"\bTUPF\b", "turf"),
    (r"\bHAPO\b", "hard"),
    (r"\bIMAelNe\b", "imagine"),
    (r"\bIMPOPTANT\b", "important"),
    (r"\baet[-]fTlNe\b", "fighting"),
    (r"\bgplNe\b", "bring"),
    (r"\bSACPED\b", "sacred"),
    (r"\be[-]OPY\b", "glory"),
    (r"\beLOPlOUS\b", "glorious"),
    (r"\bMemgep\b", "member"),
    (r"\bSTPUT APOUNO\b", "strut around"),
    (r"\bSWOPD KINes\b|\bSWOPD KIN.S\b", "Sword Kings"),
    (r"\bPE[-]MAINS\b", "remains"),
    (r"wurs GOING 0M", "What's going on"),
    (r"\bOINeWE[-]l\b|\b01NeWE[-]l\b", "Baili Jingwei"),
    (r"\bWOPPEO\b|\bWOPPED\b", "worried"),
    (r"\bCPOWN PPINCE'S\b", "Crown Prince's"),
    (r"\bIMPE[-]P!?AL\b", "Imperial"),
    (r"\bDPAeON cceAvlNe\b", "Dragon Cleaving"),
    (r"\bPETUPN\b", "return"),
    (r"\bgeope we eo\b", "before we go"),
    (r"\bPPOVIDE[-]NCE\b", "providence"),
    (r"\bWE[-]EL\b", "well"),
    (r"SHANeeUAN|SHAN%UAN|Shanxuan", "Shangguan"),
    (r"\beotNe\b", "going"),
    (r"\beeT\b", "get"),
]

def clean_script_segments(segments: List[ScriptSegment]) -> List[ScriptSegment]:
    """
    Cleans raw script segments:
    - Removes scanlation credit words and SFX noises from spoken dialogue
    - Deduplicates repeated lines and prunes partial substring fragments
    - Applies regex typography cleanup for comic OCR misrecognitions
    - Merges consecutive lines from the same speaker on the same panel
    - Recalculates pacing and timing
    """
    raw_cleaned: List[ScriptSegment] = []
    seen_texts = set()

    for seg in segments:
        if seg.type == SegmentType.PAUSE:
            raw_cleaned.append(seg)
            continue

        if seg.type == SegmentType.NARRATOR:
            text = seg.text.strip()
            text = re.sub(r"^(?:Scene|Panel|Shot)\s*#?\d+\s*[-:—–.]\s*", "", text, flags=re.IGNORECASE).strip()
            for pat, rep in [(r"Shanxuan", "Shangguan"), (r"Oade Falls", "Jade Falls"), (r"One-Wei-Li", "Baili Jingwei"), (r"Bali Jingwei", "Baili Jingwei")]:
                text = re.sub(pat, rep, text, flags=re.IGNORECASE)
            seg.text = text
            raw_cleaned.append(seg)
            continue

        # Character Dialogue
        text = seg.text.strip()
        speaker = seg.speaker_character_id or ""

        # Filter SFX, scanlation words, and tiny artifacts
        if speaker == "SFX" or text.upper() in ("READ", "FASTER", "RELEASE", "PLEASE", "MANHUAPLUS"):
            continue
        if len(text) < 4 or re.match(r"^[^\w\s]+$", text):
            continue
        if any(w in text.lower() for w in ("patreon.", "paypal.", "manhuaplus", "scanlation", "discord.gg")):
            continue

        # Apply typo replacements
        for pat, rep in REPLACEMENTS:
            text = re.sub(pat, rep, text, flags=re.IGNORECASE)

        # Clean multiple spaces and formatting
        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(r"[\ufffd]", "", text).strip()

        # Deduplication against seen texts in project
        norm = re.sub(r"[^a-zA-Z0-9]", "", text.lower())
        if not norm or norm in seen_texts:
            continue

        # Substring filter: if text is a short fragment of another segment in the same scene, skip
        is_sub = False
        for os in segments:
            if os.scene_id == seg.scene_id and os.segment_id != seg.segment_id and os.type == SegmentType.CHARACTER_DIALOGUE:
                ot = os.text.strip()
                if len(ot) > len(text) + 6 and text.lower() in ot.lower():
                    is_sub = True
                    break
        if is_sub:
            continue

        seen_texts.add(norm)
        seg.text = text
        raw_cleaned.append(seg)

    # Merge consecutive dialogue from same speaker on same panel
    merged: List[ScriptSegment] = []
    for s in raw_cleaned:
        if (
            merged
            and merged[-1].type == SegmentType.CHARACTER_DIALOGUE
            and s.type == SegmentType.CHARACTER_DIALOGUE
            and merged[-1].speaker_character_id == s.speaker_character_id
            and merged[-1].scene_id == s.scene_id
        ):
            m_pids = set(getattr(merged[-1].source_evidence, "panel_ids", []))
            s_pids = set(getattr(s.source_evidence, "panel_ids", []))
            if m_pids & s_pids or not m_pids or not s_pids:
                # Merge into previous segment
                sep = " " if merged[-1].text.endswith((".", "!", "?")) else ", "
                merged[-1].text = merged[-1].text.rstrip(" ,.") + sep + s.text.lstrip(" ,.")
                # Combine evidence
                m_regs = list(getattr(merged[-1].source_evidence, "text_region_ids", []))
                s_regs = list(getattr(s.source_evidence, "text_region_ids", []))
                merged[-1].source_evidence.text_region_ids = list(dict.fromkeys(m_regs + s_regs))
                continue
        merged.append(s)

    # Normalize dialogue text for natural spoken delivery and accurate duration estimation
    from engine.audio.sanitizer import clean_script_text
    for s in merged:
        if s.type != SegmentType.PAUSE and s.text:
            s.text = clean_script_text(s.text)

    # Recalculate durations and absolute timeline
    current_time = 0.0
    for idx, seg in enumerate(merged, start=1):
        seg.sequence = idx
        if seg.type == SegmentType.PAUSE:
            dur = seg.estimated_duration or 1.5
        elif seg.type == SegmentType.NARRATOR:
            dur = estimate_segment_duration(seg.text, segment_type="NARRATOR")
        else:
            dur = estimate_segment_duration(seg.text, segment_type="CHARACTER_DIALOGUE")

        seg.estimated_duration = dur
        seg.estimated_start = round(current_time, 2)
        seg.estimated_end = round(current_time + dur, 2)
        current_time += dur

    return merged
