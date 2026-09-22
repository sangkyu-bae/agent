"""요청 추적 컨텍스트 (ContextVar 기반).

LOG-001 "request_id 컨텍스트 전파" 요구사항의 구현체.

DB 쿼리 리스너처럼 호출 계층을 모르는 하위 모듈도, 여기 바인딩된
`LogContext`를 통해 요청 출처(request_id / endpoint / method)를 로그에 실을 수 있다.
`StructuredLogger._log()`가 모든 로그에 자동 주입하므로 호출부 변경은 필요 없다.

바인딩 지점:
    - HTTP 요청: RequestLoggingMiddleware
    - 그 외 진입점(WebSocket / 스케줄 / LangGraph run): 해당 진입점에서 직접 bind()

주의:
    ContextVar는 asyncio 태스크 경계를 넘어 자동 전파되지만,
    `run_in_executor`로 넘기는 스레드 작업에는 전파되지 않는다.
    필요 시 `contextvars.copy_context()`로 명시 래핑할 것.
"""

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any, Iterator

from src.domain.logging.value_objects import LogContext

# LogContext가 전용 속성으로 갖는 필드. 그 외 키는 extra로 수납된다.
_KNOWN_FIELDS: frozenset[str] = frozenset(
    {"request_id", "user_id", "session_id", "endpoint", "method"}
)

_log_context: ContextVar[LogContext | None] = ContextVar(
    "log_context", default=None
)


def get_log_context() -> LogContext | None:
    """현재 바인딩된 LogContext를 반환한다. 없으면 None."""
    return _log_context.get()


def get_context_fields() -> dict[str, Any]:
    """현재 컨텍스트를 로그 필드 dict로 반환한다.

    Returns:
        바인딩된 컨텍스트가 없으면 빈 dict. 반환값은 매번 새 dict이므로
        호출자가 변경해도 컨텍스트는 오염되지 않는다.
    """
    context = _log_context.get()
    return context.to_dict() if context is not None else {}


def bind(**fields: Any) -> Token:
    """현재 컨텍스트에 필드를 병합한다.

    기존 필드는 유지되고, 같은 이름의 필드는 새 값이 이긴다.
    `LogContext`가 모르는 키는 extra로 수납된다.
    request_id를 한 번도 준 적이 없으면 UUID가 자동 생성된다.

    Args:
        **fields: 바인딩할 로그 필드

    Returns:
        reset()에 넘겨 이전 상태로 되돌릴 수 있는 Token
    """
    known = {k: v for k, v in fields.items() if k in _KNOWN_FIELDS}
    extra = {k: v for k, v in fields.items() if k not in _KNOWN_FIELDS}

    current = _log_context.get()
    if current is not None:
        base = {k: getattr(current, k) for k in _KNOWN_FIELDS}
        base.update(known)
        merged_extra = {**(current.extra or {}), **extra}
    else:
        base = known
        merged_extra = extra

    return _log_context.set(
        LogContext(**base, extra=merged_extra or None)
    )


def reset(token: Token) -> None:
    """bind()가 돌려준 토큰으로 이전 컨텍스트를 복원한다."""
    _log_context.reset(token)


def clear() -> None:
    """컨텍스트를 비운다 (테스트·워커 재사용 시 누수 방지용)."""
    _log_context.set(None)


@contextmanager
def log_context(**fields: Any) -> Iterator[LogContext]:
    """블록 범위로 로그 필드를 바인딩한다.

    예외가 발생해도 블록을 벗어나면 이전 컨텍스트로 복원된다.

    Example:
        with log_context(agent_run_id=run_id, node_name="search"):
            await do_work()
    """
    token = bind(**fields)
    try:
        yield _log_context.get()
    finally:
        reset(token)
