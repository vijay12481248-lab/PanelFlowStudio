import re

# Standard speech-rate assumptions in words per minute (WPM)
NARRATOR_WPM = 150.0
DIALOGUE_WPM = 135.0
MIN_SEGMENT_DURATION = 1.2  # seconds
PAUSE_DURATION_DEFAULT = 1.5  # seconds
TRANSITION_DURATION_DEFAULT = 2.0  # seconds

def count_words(text: str) -> int:
    """Counts words or non-whitespace characters for CJK languages."""
    if not text:
        return 0
    words = re.findall(r"\b\w+\b", text)
    if words:
        return len(words)
    # Fallback for non-space delimited scripts (e.g. Japanese/Chinese)
    return max(1, len(text.strip()) // 2)

def estimate_segment_duration(
    text: str,
    segment_type: str = "CHARACTER_DIALOGUE",
    wpm_override: float | None = None,
) -> float:
    """
    Estimates spoken segment duration in seconds using word-count pacing,
    plus punctuation cadence pauses (commas, periods, exclamation).
    """
    if segment_type == "PAUSE":
        return PAUSE_DURATION_DEFAULT
    if segment_type == "TRANSITION":
        return TRANSITION_DURATION_DEFAULT
    if segment_type == "SFX_CUE":
        return 1.0

    wpm = wpm_override or (NARRATOR_WPM if segment_type == "NARRATOR" else DIALOGUE_WPM)
    word_count = count_words(text)

    # Base duration from speech rate
    seconds = (word_count / wpm) * 60.0

    # Punctuation pauses
    comma_count = text.count(",") + text.count("、")
    period_count = text.count(".") + text.count("!") + text.count("?") + text.count("。") + text.count("！") + text.count("？")
    seconds += (comma_count * 0.25) + (period_count * 0.45)

    return max(MIN_SEGMENT_DURATION, round(seconds, 2))
