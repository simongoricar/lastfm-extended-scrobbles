from typing import Any, Dict, Optional, Tuple

from mutagen import FileType


def get_mutagen_attribute(file: FileType, tag_name: str, fallback: Any = None) -> str:
    tag_raw = file.tags.get(tag_name)

    if type(tag_raw) is list:
        return tag_raw[0] if len(tag_raw) > 0 else fallback
    else:
        return tag_raw


def youtube_length_to_sec(human_time: str) -> int:
    total = 0
    separated = human_time.split(":")

    try:
        separated = [int(a) for a in separated]
    except ValueError:
        return 0

    total += separated[-1]

    if len(separated) > 1:
        total += int(separated[-2]) * 60
    if len(separated) > 2:
        total += int(separated[-3]) * 60 * 60

    return total


def get_best_attribute(item: Dict[str, Optional[str]], keys: Tuple, fallback: Any = None) -> Optional[str]:
    """
    Due to the weird nature of data exported from Last.fm, we need to check multiple keys to find the proper value.
    This function abstracts the search.

    Args:
        item:
            Dictionary to look on.
        keys:
            Tuple of keys to check.
        fallback:
            Value to return when no match can be found.

    Returns:
        First non-None/non-empty string result.
    """
    for k in keys:
        value = item.get(k)
        if value not in (None, ""):
            return value

    return fallback
