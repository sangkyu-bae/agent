"""AuthContext ContextVar — RunContext와 독립적인 비즈니스 컨텍스트.

agent-user-context Design §4.1:
- RunContext(`context.py`)와 분리한 이유:
  - RunContext: 관측성 전용 (run_id/step_id/callback) — 라이프사이클이 ai_run에 종속
  - AuthContext: 비즈니스 (user_id/permissions) — 라이프사이클이 HTTP request에 종속
  - 책임 분리 + 한쪽이 없어도 다른 쪽이 동작해야 함

asyncio Task별 자동 격리 — 동시 다중 사용자 요청에서 컨텍스트 혼선 없음.
"""
from contextvars import ContextVar, Token
from typing import Optional

from src.domain.agent_run.auth_context import AuthContext


_current_auth_context: ContextVar[Optional[AuthContext]] = ContextVar(
    "_current_auth_context", default=None
)


def get_current_auth_context() -> Optional[AuthContext]:
    """현재 Task의 AuthContext를 반환. 미설정이면 None.

    Tool/Repository 내부에서 fallback으로 사용하지만, 우선 명시적 시그니처를
    선호한다 (Defense in Depth).
    """
    return _current_auth_context.get()


def set_current_auth_context(ctx: AuthContext) -> Token:
    """AuthContext 설정 후 reset에 전달할 Token 반환.

    호출자는 finally 블록에서 반드시 reset_current_auth_context(token)을 호출해야 한다.
    """
    return _current_auth_context.set(ctx)


def reset_current_auth_context(token: Token) -> None:
    """set_current_auth_context()로 받은 토큰으로 이전 컨텍스트 복원."""
    _current_auth_context.reset(token)
