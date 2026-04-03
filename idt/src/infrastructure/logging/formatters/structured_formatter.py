"""Structured Formatter for JSON logging.

로그 레코드를 JSON 형식으로 포맷하는 포매터입니다.
"""

import json
import logging
import traceback
from datetime import datetime, timezone
from typing import Any


class StructuredFormatter(logging.Formatter):
    """구조화된 JSON 로그 포매터.

    로그 레코드를 JSON 형식으로 변환합니다.
    에러 발생 시 스택트레이스를 가독성 좋게 출력합니다.
    """

    # 기본 LogRecord 속성 (extra 필드 식별 시 제외용)
    _RESERVED_ATTRS = {
        "name",
        "msg",
        "args",
        "created",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "exc_info",
        "exc_text",
        "thread",
        "threadName",
        "taskName",
        "message",
    }

    def format(self, record: logging.LogRecord) -> str:
        """로그 레코드를 포맷.

        Args:
            record: 로그 레코드

        Returns:
            포맷된 문자열
        """
        log_dict = self._build_log_dict(record)

        # extra 필드 추가
        for key, value in record.__dict__.items():
            if key not in self._RESERVED_ATTRS and not key.startswith("_"):
                log_dict[key] = value

        # 기본 로그 라인
        log_line = json.dumps(log_dict, ensure_ascii=False, default=str)

        # 에러일 경우 스택트레이스를 별도 줄로 추가
        if record.exc_info:
            stacktrace = "".join(traceback.format_exception(*record.exc_info))
            return f"{log_line}\n{stacktrace}"

        return log_line

    def _build_log_dict(self, record: logging.LogRecord) -> dict[str, Any]:
        """기본 로그 딕셔너리 생성.

        Args:
            record: 로그 레코드

        Returns:
            기본 필드가 포함된 딕셔너리
        """
        log_dict = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "location": f"{record.filename}:{record.funcName}:{record.lineno}",
        }

        # 에러일 경우 에러 타입과 메시지 추가
        if record.exc_info and record.exc_info[1]:
            exc_type, exc_value, _ = record.exc_info
            log_dict["error_type"] = exc_type.__name__ if exc_type else "Unknown"
            log_dict["error_message"] = str(exc_value) if exc_value else ""

        return log_dict
