import logging
import os

from .structured_formatter import StructuredFormatter
from .pretty_formatter import PrettyFormatter

__all__ = ["StructuredFormatter", "PrettyFormatter", "get_formatter"]


def get_formatter() -> logging.Formatter:
    """LOG_FORMAT 환경변수에 따라 포매터를 반환한다.

    Returns:
        LOG_FORMAT=compact  → StructuredFormatter (JSON 한 줄)
        그 외 (기본값 pretty) → PrettyFormatter (멀티라인)
    """
    fmt = os.getenv("LOG_FORMAT", "pretty").strip().lower()
    if fmt == "compact":
        return StructuredFormatter()
    return PrettyFormatter()
