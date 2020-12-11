import time
from typing import Any, Dict, Optional, Tuple, Callable

from mutagen import FileType


def get_mutagen_attribute(file: FileType, tag_name: str, fallback: Any = None) -> str:
    if file.tags is None:
        return fallback

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


class TimedContext:
    __slots__ = (
        "_end_text", "_start_time",
        "_callback", "_decimal_places",
        "_output_on_exception"
    )

    def __init__(
            self, end_text: str,
            callback: Callable = print,
            decimal_places: int = 1,
            output_on_exception: bool = False
    ):
        """
        Custom context manager - prints the time spent inside the context.

        Args:
            end_text:
                String to format at the end. {time} is replaced with the spent time.
            callback:
                Callable to call on context exit. Defaults to print.
            decimal_places:
                Integer with how many decimal places you need in the measured time.
            output_on_exception:
                Whether to print/call the callback if an exception was raised inside the context.
        """
        self._end_text = end_text
        self._start_time: Optional[float] = None

        self._callback: Callable = callback
        self._decimal_places: int = decimal_places
        self._output_on_exception: bool = output_on_exception

    def __enter__(self):
        self._start_time = time.time()

    def format_output(self) -> str:
        """
        Format the end text with the time.

        Returns:
            Formatted string.
        """
        rounded = round(time.time() - self._start_time, self._decimal_places)
        return self._end_text.format(time=str(rounded))

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Only output if no exception was triggered or if configured that way
        if not any((exc_type, exc_val, exc_tb)) or self._output_on_exception:
            # Print the output / call the callback with the output
            self._callback(self.format_output())

        # Returning True will trigger a possible exception
        # We don't want to interrupt any exception chains so we should return False (or None)
        return False
