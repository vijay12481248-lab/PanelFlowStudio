"""
Script and Prompt Direction Sanitizer for PanelFlow Studio.

Strips stage directions, acting cues, speaker attributions, meta-commentary,
and LLM hallucinations from narration scripts before speech synthesis.
Prevents prompt leakage where characters vocalize descriptions, panel notes,
or stage actions.
"""
from __future__ import annotations

import re
from typing import Tuple


# Regex patterns for stage directions and acting cues
_BRACKETED_DIR_RE = re.compile(r"\[[^\]]*\]")
_PARENTHETICAL_CUE_RE = re.compile(r"\([^\)]*\)")
_ASTERISK_ACTION_RE = re.compile(r"\*[^*]+\*")

# Speaker label prefix (e.g. "Protagonist: ", "Narrator: ", "Marcus: ", "Grandmaster Gu: ")
_SPEAKER_PREFIX_RE = re.compile(
    r"^(?:The\s+)?(?:Narrator|Marcus|Aria|Seraphina|Leon|Zhuo\s+Fan|Protagonist|Speaker|Grandmaster\s+[A-Z][a-zA-Z]*|[A-Z][a-zA-Z0-9_]{1,24})\s*:\s*",
    flags=re.IGNORECASE,
)

# Scene/panel/shot prefix (e.g. "Scene 1 — Panel #1:", "Panel 3:", "Shot 2 - ")
_SCENE_PREFIX_RE = re.compile(
    r"^(?:Scene|Panel|Shot)\s*#?\d+\s*(?:[—–\-:]|\s*(?:—|–|-)\s*Panel\s*#?\d+)?\s*[:—–\-.]\s*",
    flags=re.IGNORECASE,
)

# Dummy scene/panel labels that should produce empty text
_DUMMY_LABEL_RE = re.compile(
    r"^(?:Scene|Panel|Shot)\s*#?\d+(?:\s*[-—–.]\s*(?:Panel\s*#?\d+)?)?\.?$",
    flags=re.IGNORECASE,
)

# Trailing stage attribution patterns:
# e.g. 'Protagonist exclaims, refusing to yield an inch.'
# e.g. 'Grandmaster Gu signals his departure as the chapter concludes.'
# e.g. 'Grandmaster Gu signals solemnly.'
# e.g. 'he said solemnly.'
_TRAILING_ATTRIBUTION_RE = re.compile(
    r"""(?:\s+|^)
    (?:
        (?:The\s+)?(?:Protagonist|Narrator|Grandmaster\s+[A-Za-z]+|[A-Z][a-zA-Z0-9_]{1,20}|he|she|they)
        \s+
        (?:exclaims?|whispers?|says?|said|remarks?|remarked|notes?|noted|shouts?|shouted|yells?|yelled|mutters?|muttered|growls?|growled|replies?|replied|answers?|answered|signals?|signaled|stands?|stood|looks?|looked|watches?|watched)
        (?:\s*,\s*[^.!?\n]*|\s+[a-zA-Z]+)*
        [\.!?]?
    )$""",
    flags=re.IGNORECASE | re.VERBOSE,
)

# Meta-commentary patterns describing the scene/panel rather than spoken dialogue/narration
_META_COMMENTARY_PATTERNS = [
    re.compile(r"^(?:Zero dialogue,\s*\w+\s*panels? of pure flex.*)$", flags=re.IGNORECASE),
    re.compile(r"^(?:This page screams.*)$", flags=re.IGNORECASE),
    re.compile(r"^(?:Standing in the courtyard,\s*the two characters exchange.*)$", flags=re.IGNORECASE),
    re.compile(r"^(?:In the courtyard,\s*[A-Z].*address recent attacks.*)$", flags=re.IGNORECASE),
]


ACRONYMS = {
    "AI", "FBI", "CIA", "USA", "UK", "UN", "TV", "VIP", "ID", "OK", "DNA", "CEO", "CFO", "CTO", "HQ"
}

PROPER_NOUNS = [
    "Shangguan", "Baili", "Jingwei", "Yifan", "Yifu", "Gu", "Feiyun", "Luo", "Yunhai",
    "Zhuo", "Fan", "Soaring Sword", "Dragon Cleaving", "Jade Falls", "Crown Prince",
    "Eastern Lands", "Western Lands", "Southern Lands", "Northern Lands", "Central Area",
    "Imperial", "Sect Master"
]

OCR_SPEECH_FIXES = [
    (r"\bEAPTH\b", "earth"),
    (r"\bAFTE[-]?P\b", "after"),
    (r"\bTOMOPPOW\b", "tomorrow"),
    (r"\bCUAPD\b|\beUAPD\b|\beUAPO\b", "guard"),
    (r"\bKINe\b", "king"),
    (r"\bACTINe\b", "acting"),
    (r"\bHOLDINe\b", "holding"),
    (r"\bHELPINe\b", "helping"),
    (r"\bKNOWINe\b", "knowing"),
    (r"\bWATCHINe\b", "watching"),
    (r"\bSCOUTINe\b", "scouting"),
    (r"\bSOMETHINe\b", "something"),
    (r"\bWHepe\b|\bWHE-PE\b", "where"),
    (r"\bHE-PE\b", "here"),
    (r"\bCALLE-O\b", "called"),
    (r"\bePEATEST\b", "greatest"),
    (r"\bePEAT\b", "great"),
    (r"\bCPEAT\b", "great"),
    (r"\bANYMOPE\b", "anymore"),
    (r"\bUNDEP\b", "under"),
    (r"\bHOUP\b", "hour"),
    (r"\bNE-APLY\b", "nearly"),
    (r"\bTHE-Y\b", "they"),
    (r"\bTHE-PE\b", "there"),
    (r"\bDE-MONIC\b", "demonic"),
    (r"\bEVE[-]?PYONE\b", "everyone"),
    (r"\bPE[-]MAINS\b", "remains"),
    (r"\bBPOTHEPS\b", "brothers"),
    (r"\bTPEASUPY\b", "treasury"),
    (r"\bCAPPACKS\b", "barracks"),
    (r"\bAPMOPY\b", "armory"),
    (r"\bMANOP\b", "manor"),
    (r"\bPEST\b", "rest"),
    (r"\bPEST!?Ne POO[M]?\b|\bPEST!?Ne 200M\b", "resting room"),
    (r"\bHUPPY\b", "Hurry"),
    (r"\bSTPATeey\b", "strategy"),
    (r"\bTAPeeT\b", "target"),
    (r"\bPOWEPS\b", "powers"),
    (r"\bOOUPNEY\b", "journey"),
    (r"\bTPAITOP\b", "traitor"),
    (r"\bSWOPD\b", "sword"),
    (r"\bSWOPDS\b", "swords"),
    (r"\bBAcz\b", "back"),
    (r"\bBali Jingwei\b|\bOINeWE[-]l\b", "Baili Jingwei"),
    (r"\bShanxuan\b|\bSHANeeUAN\b", "Shangguan"),
]

def normalize_speech_text(text: str) -> str:
    """
    Normalizes speech text for neural TTS engines:
    - Strips comic OCR font distortions and line break hyphens (e.g. THE-Y -> they)
    - Converts ALL CAPS dialogue to natural sentence case so short words like 'BUT', 'AND',
      'NOT', 'WHY', 'HOW' are vocalized fluently rather than spelled out as acronyms (B-U-T)
    - Preserves genuine acronyms (AI, FBI, VIP, OK, TV, etc.)
    - Retains proper capitalization for canonical story entities (Shangguan, Baili Jingwei, etc.)
    - Removes stutter repetitions from overlapping OCR speech bubbles
    """
    if not text or not text.strip():
        return ""

    # 1. Strip non-ASCII OCR junk and gibberish artifacts
    text = re.sub(r"[\ufffd\x80-\xff]", "", text)
    text = re.sub(r"[-–—]?\?[a-zA-Z0-9,.:;~]+", "", text)
    text = re.sub(r"\b[A-Za-z]+'[A-Za-z0-9_]{3,}\b", "", text)
    text = re.sub(r"\b[a-zA-Z]{1,2}\s+[a-zA-Z]{1,2}\s+resting room\s+[a-zA-Z0-9\s]{4,}\b", "", text)
    text = re.sub(r"\bjr[n]{3,}[a-z]*\b", "", text)

    # 2. Fix hyphenated word splits from comic line wrapping (e.g. THE-Y -> THEY)
    text = re.sub(r"\b([A-Za-z]{1,5})-([A-Za-z]{1,5})\b", r"\1\2", text)

    # 3. Apply comic OCR typography fixes
    for pat, rep in OCR_SPEECH_FIXES:
        text = re.sub(pat, rep, text, flags=re.IGNORECASE)

    # Clean double words: "Soaring Sword sword" -> "Soaring Sword"
    text = re.sub(r"\bSoaring Sword sword\b", "Soaring Sword", text, flags=re.IGNORECASE)

    # 4. Remove stutter repetitions from speech bubbles
    text = re.sub(r"\b(WHAT\?\s+THE\s+Soaring\s+Sword)[,\s]+\1\b", r"\1", text, flags=re.IGNORECASE)
    text = re.sub(r",\s*OW YOU'VE SUCH [A-Za-z]+ I'LL TELL YOU.*", "", text, flags=re.IGNORECASE)
    text = re.sub(r",\s*IT'S NOT TWO [A-Za-z\s]+ ONLY$", "", text, flags=re.IGNORECASE)
    text = re.sub(r",\s*WAN FEIYUN'S [A-Za-z]+.*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bworried ABOUT\s+'S\s+CONDITION\s+AND,?\s*", "", text, flags=re.IGNORECASE)

    # 5. Convert all-caps words to lowercase (preventing TTS acronym spell-out like B-U-T)
    def lower_word(m):
        full_word = m.group(0)
        if full_word.upper() in ACRONYMS:
            return full_word.upper()
        if "'" in full_word:
            parts = full_word.split("'", 1)
            left = parts[0]
            right = parts[1].lower()
            if left.upper() == "I":
                return f"I'{right}"
            return f"{left.lower()}'{right}"
        if full_word.upper() == "I":
            return "I"
        return full_word.lower()

    text = re.sub(r"\b[A-Za-z]+(?:'[A-Za-z]+)?\b", lower_word, text)

    # 6. Apply proper sentence casing
    def sentence_case(match):
        prefix = match.group(1)
        letter = match.group(2)
        return prefix + letter.upper()

    # Capitalize start of string
    text = re.sub(r"^(\s*['\"]?\s*)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)
    # Capitalize after . ! ?
    text = re.sub(r"([.!?]\s+['\"]?\s*)([a-z])", sentence_case, text)

    # Capitalize standalone "I" and contractions
    text = re.sub(r"\b(i)\b", "I", text)
    text = re.sub(r"\b(i'll)\b", "I'll", text)
    text = re.sub(r"\b(i'm)\b", "I'm", text)
    text = re.sub(r"\b(i'd)\b", "I'd", text)
    text = re.sub(r"\b(i've)\b", "I've", text)

    # 7. Restore proper nouns casing
    for pn in PROPER_NOUNS:
        text = re.sub(rf"\b{re.escape(pn)}\b", pn, text, flags=re.IGNORECASE)

    # 8. Clean trailing dangling commas and whitespace
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r",+$", ".", text).strip()
    if text and text[-1] not in (".", "!", "?", '"', "'"):
        text += "."

    return text

def clean_script_text(text: str) -> str:
    """
    Cleans dialogue and narration text for speech synthesis and alignment.

    1. Removes bracketed directions ([whisper], [sigh], [gasp])
    2. Removes parenthetical cues ((whispering), (sighs))
    3. Removes asterisk actions (*smiles*, *turns around*)
    4. Normalizes Japanese brackets, typographic quotes, and dashes
    5. Strips leading speaker labels and scene prefixes
    6. Strips trailing LLM stage attributions
    7. Cleans surrounding quotes when text is wrapped in quotes
    """
    if not text:
        return ""

    cleaned = text

    # Strip bracketed, parenthetical, and asterisk directions
    cleaned = _BRACKETED_DIR_RE.sub(" ", cleaned)
    cleaned = _PARENTHETICAL_CUE_RE.sub(" ", cleaned)
    cleaned = _ASTERISK_ACTION_RE.sub(" ", cleaned)

    # Normalize typographic quotes and brackets
    cleaned = cleaned.replace("「", '"').replace("」", '"')
    cleaned = cleaned.replace("『", '"').replace("』", '"')
    cleaned = cleaned.replace("【", "").replace("】", "")
    cleaned = cleaned.replace("\u201c", '"').replace("\u201d", '"')
    cleaned = cleaned.replace("\u2018", "'").replace("\u2019", "'")
    cleaned = cleaned.replace("\u2014", " - ").replace("\u2013", " - ")
    cleaned = cleaned.replace("\u2026", "...")

    # Normalize whitespace
    cleaned = " ".join(cleaned.split()).strip()

    # Strip leading speaker prefixes
    cleaned = _SPEAKER_PREFIX_RE.sub("", cleaned).strip()

    # Strip leading scene/panel prefixes
    cleaned = _SCENE_PREFIX_RE.sub("", cleaned).strip()

    # If purely dummy label, return empty
    if _DUMMY_LABEL_RE.match(cleaned):
        return ""

    # Check for quote-wrapped speech with trailing attribution:
    # e.g.: "Standing in the courtyard..." Protagonist exclaims, refusing to yield an inch.
    # or: "I will never yield!" he shouted angrily.
    quote_match = re.match(r'^"(.*?)"\s*(.*)$', cleaned, flags=re.DOTALL)
    if quote_match:
        quoted_body, trailing_text = quote_match.groups()
        quoted_body = quoted_body.strip()
        trailing_text = trailing_text.strip()
        if trailing_text:
            # Check if trailing text is an attribution
            if _TRAILING_ATTRIBUTION_RE.search(" " + trailing_text):
                cleaned = quoted_body
            else:
                # If trailing text is not attribution, keep whole text
                cleaned = f'"{quoted_body}" {trailing_text}'
        else:
            cleaned = quoted_body
    else:
        # Unquoted action sentences are narration, including "Yifan shouts...".
        # Only remove a short, lowercase dialogue tag after spoken punctuation.
        cleaned = re.sub(
            r'(?<=[.!?])\s+(?:he|she|they)\s+(?:said|shouted|whispered|replied|asked)'
            r'(?:\s+[a-z]+ly)?[.!?]?$', '', cleaned,
        ).strip()

    # Strip stray dangling punctuation
    cleaned = re.sub(r"^[:—–\-\s]+", "", cleaned)
    cleaned = re.sub(r"[:—–\-]+$", "", cleaned)

    # If entire text is wrapped in quotes, unwrap it
    if cleaned.startswith('"') and cleaned.endswith('"') and len(cleaned) > 2:
        cleaned = cleaned[1:-1].strip()

    cleaned = cleaned.strip()
    return normalize_speech_text(cleaned)


def detect_prompt_leakage(text: str) -> Tuple[bool, str]:
    """
    Detects if text contains meta-commentary, prompt directions, or unvocalizable text.
    Returns (is_leakage, reason).
    """
    if not text or not text.strip():
        return False, ""

    for pat in _META_COMMENTARY_PATTERNS:
        if pat.search(text):
            return True, f"Matched meta-commentary pattern: {pat.pattern}"

    if "without saying a word" in text.lower() and "zero dialogue" in text.lower():
        return True, "Meta-commentary describing silent scene"

    if "signals his departure as the chapter concludes" in text.lower():
        return True, "Stage direction describing chapter conclusion"

    return False, ""
