"""SQLAlchemy DB 쿼리 로깅 리스너.

before_cursor_execute / after_cursor_execute 이벤트를 통해
SQL, 바인딩 파라미터, 실행 시간(ms)을 DEBUG 레벨로 로깅한다.

LOG_LEVEL=DEBUG 설정 시에만 출력됨 (INFO 이상 환경에서는 자동 비활성화).
"""

import time
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine

from src.infrastructure.logging import get_logger

logger = get_logger("db.query")

_SENSITIVE_PARAM_KEYS = {"password", "token", "secret", "api_key", "refresh_token"}


class DBQueryListener:
    """SQLAlchemy 쿼리 실행 로깅 리스너.

    엔진에 before/after cursor execute 이벤트를 등록하여
    SQL 문과 실행 시간을 구조화된 형식으로 로깅한다.
    """

    def register(self, engine: AsyncEngine) -> None:
        """엔진에 이벤트 리스너를 등록한다.

        Args:
            engine: AsyncEngine 인스턴스
        """
        event.listen(
            engine.sync_engine, "before_cursor_execute", self._before_execute
        )
        event.listen(
            engine.sync_engine, "after_cursor_execute", self._after_execute
        )

    def _before_execute(
        self,
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        """쿼리 시작 시각을 conn.info에 기록한다."""
        conn.info["query_start_time"] = time.perf_counter()

    def _after_execute(
        self,
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        """쿼리 완료 후 SQL + 파라미터 + 응답 정보 + 실행 시간을 DEBUG 레벨로 로깅한다."""
        start = conn.info.get("query_start_time")
        duration_ms = (
            round((time.perf_counter() - start) * 1000, 2) if start is not None else None
        )

        row_count = getattr(cursor, "rowcount", None)
        description = getattr(cursor, "description", None)
        columns = [col[0] for col in description] if description else None

        logger.debug(
            "DB Query",
            sql=statement.strip(),
            params=_mask_sensitive_params(parameters),
            row_count=row_count,
            columns=columns,
            duration_ms=duration_ms,
        )


def _mask_sensitive_params(parameters: Any) -> Any:
    """바인딩 파라미터에서 민감 키를 마스킹한다.

    Args:
        parameters: SQLAlchemy 바인딩 파라미터 (dict, list[dict], 또는 None)

    Returns:
        마스킹된 파라미터. 원본 타입 유지.
    """
    if isinstance(parameters, dict):
        return {
            k: "***MASKED***" if k.lower() in _SENSITIVE_PARAM_KEYS else v
            for k, v in parameters.items()
        }
    if isinstance(parameters, (list, tuple)):
        return [_mask_sensitive_params(p) for p in parameters]
    return parameters
