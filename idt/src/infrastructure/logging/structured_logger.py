"""StructuredLogger Implementation.

LoggerInterface를 구현하는 구조화된 JSON 로거입니다.
"""

import logging
import os
import sys
from typing import Any

_LOGRECORD_RESERVED_KEYS: frozenset[str] = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()
) | {"message", "asctime"}

from src.domain.logging.interfaces import LoggerInterface
from src.infrastructure.logging.formatters import get_formatter
from src.infrastructure.logging.log_context import get_context_fields


def _resolve_log_level() -> int:
    """LOG_LEVEL 환경변수를 읽어 logging 레벨 정수로 반환한다.

    유효하지 않은 값이면 INFO로 fallback.
    """
    level_str = os.getenv("LOG_LEVEL", "INFO").upper().strip()
    return getattr(logging, level_str, logging.INFO)


class StructuredLogger(LoggerInterface):
    """구조화된 JSON 로거.

    LoggerInterface를 구현하며, 모든 로그를 JSON 형식으로 출력합니다.
    """

    def __init__(
        self,
        name: str = "app",
        level: int = logging.INFO,
    ):
        """StructuredLogger 초기화.

        Args:
            name: 로거 이름
            level: 로그 레벨 (기본값: INFO)
        """
        self._logger = logging.getLogger(name)
        self._logger.setLevel(level)
        self._logger.propagate = False

        # 핸들러가 없으면 기본 핸들러 추가
        if not self._logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setLevel(level)
            handler.setFormatter(get_formatter())
            self._logger.addHandler(handler)

    def debug(self, message: str, **kwargs: Any) -> None:
        """디버그 레벨 로그 기록.

        Args:
            message: 로그 메시지
            **kwargs: 추가 컨텍스트 정보
        """
        self._log(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        """정보 레벨 로그 기록.

        Args:
            message: 로그 메시지
            **kwargs: 추가 컨텍스트 정보
        """
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        """경고 레벨 로그 기록.

        Args:
            message: 로그 메시지
            **kwargs: 추가 컨텍스트 정보
        """
        self._log(logging.WARNING, message, **kwargs)

    def error(
        self, message: str, exception: Exception | None = None, **kwargs: Any
    ) -> None:
        """에러 레벨 로그 기록.

        Args:
            message: 로그 메시지
            exception: 예외 객체 (스택 트레이스 포함 시)
            **kwargs: 추가 컨텍스트 정보
        """
        self._log(logging.ERROR, message, exception=exception, **kwargs)

    def critical(
        self, message: str, exception: Exception | None = None, **kwargs: Any
    ) -> None:
        """치명적 에러 레벨 로그 기록.

        Args:
            message: 로그 메시지
            exception: 예외 객체 (스택 트레이스 포함 시)
            **kwargs: 추가 컨텍스트 정보
        """
        self._log(logging.CRITICAL, message, exception=exception, **kwargs)

    def is_enabled_for(self, level: int) -> bool:
        """해당 레벨의 로그가 실제로 출력되는지 확인한다.

        로그 페이로드 구성이 비싼 호출부(예: DB 쿼리 리스너)에서
        불필요한 계산을 건너뛰기 위한 가드.

        Args:
            level: logging 레벨 정수

        Returns:
            출력되면 True
        """
        return self._logger.isEnabledFor(level)

    def _log(
        self,
        level: int,
        message: str,
        exception: Exception | None = None,
        **kwargs: Any,
    ) -> None:
        """내부 로그 기록 메서드.

        ContextVar에 바인딩된 로그 컨텍스트(request_id / endpoint / ...)를
        자동으로 병합한다. 호출부가 명시한 kwargs가 컨텍스트보다 우선한다.

        Args:
            level: 로그 레벨
            message: 로그 메시지
            exception: 예외 객체
            **kwargs: 추가 컨텍스트 정보
        """
        merged = {**get_context_fields(), **kwargs}
        extra = {
            (f"ctx_{k}" if k in _LOGRECORD_RESERVED_KEYS else k): v
            for k, v in merged.items()
        }

        # stacklevel=3: _log -> info/error/etc -> 실제 호출 위치
        if exception is not None:
            exc_info = (type(exception), exception, exception.__traceback__)
            self._logger.log(
                level, message, exc_info=exc_info, extra=extra, stacklevel=3
            )
        else:
            self._logger.log(level, message, extra=extra, stacklevel=3)


# 캐시된 로거 저장소
_loggers: dict[str, StructuredLogger] = {}


def get_logger(name: str = "app") -> StructuredLogger:
    """모듈에서 사용할 로거를 가져옵니다.

    같은 이름으로 호출하면 캐시된 로거를 반환합니다.

    Args:
        name: 로거 이름 (보통 __name__ 사용)

    Returns:
        StructuredLogger 인스턴스

    Example:
        from src.infrastructure.logging import get_logger

        logger = get_logger(__name__)
        logger.info("Processing started", count=10)
    """
    if name not in _loggers:
        _loggers[name] = StructuredLogger(name=name, level=_resolve_log_level())
    return _loggers[name]
