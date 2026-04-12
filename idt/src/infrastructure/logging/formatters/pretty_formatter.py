"""PrettyFormatter — 사람이 읽기 좋은 멀티라인 로그 포매터.

LOG_FORMAT=pretty 환경변수 설정 시 활성화된다.
개발/디버깅 환경 전용. 운영 환경에서는 StructuredFormatter(compact) 사용.
"""

import logging
import traceback
from datetime import datetime, timezone
from typing import Any

from src.infrastructure.logging.formatters.structured_formatter import (
    StructuredFormatter,
)


class PrettyFormatter(logging.Formatter):
    """사람이 읽기 좋은 멀티라인 로그 포매터."""

    SEPARATOR = "─" * 64

    LEVEL_COLORS = {
        "DEBUG": "\033[36m",    # cyan
        "INFO": "\033[32m",     # green
        "WARNING": "\033[33m",  # yellow
        "ERROR": "\033[31m",    # red
        "CRITICAL": "\033[35m", # magenta
    }
    RESET = "\033[0m"

    # StructuredFormatter의 예약 속성 재사용 (중복 정의 방지)
    _RESERVED_ATTRS = StructuredFormatter._RESERVED_ATTRS

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(
            record.created, tz=timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        level = record.levelname
        color = self.LEVEL_COLORS.get(level, "")
        location = f"{record.filename}:{record.funcName}:{record.lineno}"

        # 헤더 라인: [timestamp] LEVEL  message
        header = f"{color}[{timestamp}] {level:<8}{self.RESET} {record.getMessage()}"

        # extra 필드 (예약 속성 제외, location 제외 후 마지막에 추가)
        fields: dict[str, Any] = {
            k: v
            for k, v in record.__dict__.items()
            if k not in self._RESERVED_ATTRS and not k.startswith("_")
        }
        fields["location"] = location

        field_lines = self._format_fields(fields)

        lines = [self.SEPARATOR, header] + field_lines

        # 에러 스택트레이스 (별도 줄, 가독성 향상)
        if record.exc_info:
            stacktrace = "".join(traceback.format_exception(*record.exc_info))
            lines.append(stacktrace.rstrip())

        return "\n".join(lines)

    def _format_fields(self, fields: dict[str, Any]) -> list[str]:
        """key : value 형태로 들여쓰기 출력. 키 길이에 맞춰 정렬."""
        if not fields:
            return []

        max_key_len = max(len(k) for k in fields)
        lines = []
        for key, value in fields.items():
            padding = " " * (max_key_len - len(key))
            lines.append(f"  {key}{padding} : {value}")
        return lines
