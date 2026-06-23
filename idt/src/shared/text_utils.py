"""Pure text helper utilities with no external dependencies."""

import re

_NON_SLUG_CHARS = re.compile(r"[^a-z0-9\s-]")
_WHITESPACE = re.compile(r"\s+")


def slugify(text: str) -> str:
    """Convert text into a URL-friendly slug.

    Lowercases the input, removes any character that is not an ASCII
    alphanumeric, whitespace, or hyphen (e.g. punctuation and non-ASCII
    letters such as Hangul), then collapses runs of whitespace into single
    hyphens and trims leading/trailing hyphens.

    Args:
        text: The raw input string.

    Returns:
        The slugified string containing only lowercase ASCII letters,
        digits, and hyphens. Returns an empty string when nothing remains.
    """
    lowered = text.lower()
    cleaned = _NON_SLUG_CHARS.sub("", lowered)
    hyphenated = _WHITESPACE.sub("-", cleaned.strip())
    return hyphenated.strip("-")
