import re

def natural_sort_key(s: str) -> list[int | str]:
    """
    Returns a key that can be used for natural/human-friendly sorting.
    Example: ['page1', 'page2', 'page10'] instead of ['page1', 'page10', 'page2'].
    """
    return [
        int(text) if text.isdigit() else text.lower()
        for text in re.split(r"(\d+)", str(s))
    ]
