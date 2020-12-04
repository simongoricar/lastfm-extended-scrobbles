from typing import Any

from mutagen import FileType


def get_mutagen_attribute(file: FileType, tag_name: str, fallback: Any = None) -> str:
    tag_raw = file.tags.get(tag_name)

    if type(tag_raw) is list:
        return tag_raw[0] if len(tag_raw) > 0 else fallback
    else:
        return tag_raw
