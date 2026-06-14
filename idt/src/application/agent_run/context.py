"""RunContext ContextVar — 현재 활성 LangGraph run의 컨텍스트.

AGENT-OBS-001 §3-2-1 / §14-2:
LangGraph 외부에서 호출되는 RAG 어댑터·Summarizer·외부 툴이 이 ContextVar에서
run_id / step_id / tool_call_id를 읽어 tracker.record_*() 를 호출한다.

asyncio Task별 자동 격리 — 동시 다중 사용자 요청에서 컨텍스트 혼선 없음.
"""
from contextvars import ContextVar, Token
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Optional

from src.domain.agent_run.value_objects import RunId

if TYPE_CHECKING:  # 순환 import 방지: callback 타입은 런타임에 duck-typed
    from src.infrastructure.llm.usage_callback import UsageCallback


@dataclass(frozen=True)
class RunContext:
    """활성 run의 컨텍스트 스냅샷."""

    run_id: RunId
    user_id: str
    agent_id: str
    callback: "UsageCallback"
    step_id: Optional[str] = None
    tool_call_id: Optional[str] = None


_current_run_context: ContextVar[Optional[RunContext]] = ContextVar(
    "_current_run_context", default=None
)


def get_current_run_context() -> Optional[RunContext]:
    """현재 Task의 RunContext를 반환. graph 외부 호출이면 None."""
    return _current_run_context.get()


def set_current_run_context(ctx: Optional[RunContext]) -> Token:
    """RunContext 설정 후 reset_run_context()에 전달할 토큰 반환."""
    return _current_run_context.set(ctx)


def reset_run_context(token: Token) -> None:
    """set_current_run_context()로 받은 토큰으로 이전 컨텍스트 복원."""
    _current_run_context.reset(token)


def with_tool_call_id(ctx: RunContext, tool_call_id: Optional[str]) -> RunContext:
    """ctx를 복사하면서 tool_call_id만 갱신."""
    return replace(ctx, tool_call_id=tool_call_id)


def with_step_id(ctx: RunContext, step_id: Optional[str]) -> RunContext:
    """ctx를 복사하면서 step_id만 갱신."""
    return replace(ctx, step_id=step_id)
