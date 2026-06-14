"""LangGraph 노드 실행 lifecycle을 ai_run_step 테이블에 영속화.

AGENT-OBS-003 (M3) — async context manager 패턴.
WorkflowCompiler가 모든 add_node 호출을 _with_step_tracking으로 wrapping할 때 사용.

Design §4.1 참조.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator, Final, Mapping, Optional, TYPE_CHECKING

from langchain_core.messages import AIMessage, BaseMessage

from src.application.agent_run.context import (
    get_current_run_context,
    set_current_run_context,
    with_step_id,
)
from src.application.agent_run.tracker import RunTracker
from src.domain.agent_run.value_objects import NodeType, RunId, StepStatus
from src.domain.logging.interfaces.logger_interface import LoggerInterface

if TYPE_CHECKING:  # 순환 import 회피
    from src.infrastructure.llm.usage_callback import UsageCallback


_INPUT_SUMMARY_MAX_CHARS: Final[int] = 1024
_OUTPUT_SUMMARY_MAX_CHARS: Final[int] = 1024
_ERROR_TEXT_MAX_CHARS: Final[int] = 1024
_USER_TEXT_SLICE: Final[int] = 600

# supervisor_node가 reasoning을 노출할 때 사용하는 dict key
STEP_OUTPUT_SUMMARY_KEY: Final[str] = "_step_output_summary"


@dataclass
class _StepContext:
    """track_step 컨텍스트 내부에서 노드 본문이 output_summary를 갱신할 수 있도록 노출."""

    step_id: Optional[str]
    output_summary: Optional[str] = None


def _truncate(text: Optional[str], max_chars: int) -> Optional[str]:
    if text is None:
        return None
    return text[:max_chars] if len(text) > max_chars else text


def _extract_content(msg: Any) -> str:
    """BaseMessage 또는 dict 모두 안전하게 content 추출."""
    if isinstance(msg, dict):
        return str(msg.get("content", ""))
    return str(getattr(msg, "content", ""))


def _find_last_message(
    messages: Any,
    *,
    role: Optional[str] = None,
    kind: Optional[type] = None,
) -> Optional[Any]:
    """messages list에서 마지막 매칭 메시지 반환 (dict + BaseMessage 안전)."""
    if not messages:
        return None
    for msg in reversed(messages):
        if kind is not None and isinstance(msg, kind):
            return msg
        if role is not None:
            msg_role = (
                msg.get("role") if isinstance(msg, dict)
                else getattr(msg, "type", None)
            )
            if msg_role == role:
                return msg
    return None


def _summarize_state_input(state: Mapping[str, Any]) -> Optional[str]:
    """LangGraph state → input_summary 1KB.

    마지막 user 메시지 + iteration_count + last_worker_id 결합.
    state 키 누락에 안전 (best-effort — 어떤 예외도 raise하지 않음).
    """
    try:
        messages = state.get("messages") if isinstance(state, Mapping) else None
        last_user = _find_last_message(messages, role="user") or _find_last_message(
            messages, role="human"
        )
        if last_user is None:
            user_text = "(no user message)"
        else:
            user_text = _extract_content(last_user)
        parts = [
            f"iter={state.get('iteration_count', 0)}",
            f"last_worker={state.get('last_worker_id', '')}",
            f"user={user_text[:_USER_TEXT_SLICE]}",
        ]
        return " | ".join(parts)[:_INPUT_SUMMARY_MAX_CHARS]
    except Exception:
        return None


def _summarize_state_output(result: Any) -> Optional[str]:
    """노드 return dict → output_summary 1KB.

    1순위: messages 중 마지막 AIMessage content
    2순위: routing keys (next_worker / quality_gate_result / retry_counts) snippet
    3순위: str(result)[:1024]
    """
    try:
        if not isinstance(result, dict):
            return str(result)[:_OUTPUT_SUMMARY_MAX_CHARS]
        new_messages = result.get("messages") or []
        last_ai = _find_last_message(new_messages, kind=AIMessage)
        if last_ai is not None:
            content = _extract_content(last_ai)
            if content:
                return content[:_OUTPUT_SUMMARY_MAX_CHARS]
        keys = ["next_worker", "quality_gate_result", "retry_counts"]
        snippet = {k: result.get(k) for k in keys if k in result}
        if snippet:
            return json.dumps(snippet, ensure_ascii=False, default=str)[
                :_OUTPUT_SUMMARY_MAX_CHARS
            ]
        return None
    except Exception:
        return None


async def _record_step_best_effort(
    *,
    tracker: RunTracker,
    run_id: RunId,
    step_index: int,
    node_name: str,
    node_type: NodeType,
    input_summary: Optional[str],
    logger: LoggerInterface,
) -> Optional[str]:
    """record_step 호출을 best-effort로 wrap. 실패 시 None 반환."""
    try:
        return await tracker.record_step(
            run_id=run_id,
            step_index=step_index,
            node_name=node_name,
            node_type=node_type,
            llm_model_id=None,
            status=StepStatus.STARTED,
            input_summary=input_summary,
        )
    except Exception as e:
        logger.warning(
            "track_step record_step failed (best-effort)",
            exception=e,
            run_id=run_id.value,
            node_name=node_name,
        )
        return None


async def _update_step_best_effort(
    *,
    tracker: RunTracker,
    run_id: RunId,
    step_id: Optional[str],
    status: StepStatus,
    output_summary: Optional[str],
    error_text: Optional[str],
    logger: LoggerInterface,
    node_name: str,
) -> None:
    """update_step을 best-effort로 wrap. step_id None이면 skip."""
    if step_id is None:
        return
    try:
        await tracker.update_step(
            step_id=step_id,
            run_id=run_id,
            status=status,
            output_summary=output_summary,
            error_text=error_text,
        )
    except Exception as e:
        logger.warning(
            "track_step update_step failed (best-effort)",
            exception=e,
            run_id=run_id.value,
            step_id=step_id,
            node_name=node_name,
        )


def _restore_context(
    callback: "UsageCallback",
    prev_step_id: Optional[str],
    prev_ctx: Any,
) -> None:
    """노드 종료 시 callback._current_step_id 와 RunContext 복원."""
    callback._current_step_id = prev_step_id
    if prev_ctx is not None:
        set_current_run_context(with_step_id(prev_ctx, prev_step_id))


@asynccontextmanager
async def track_step(
    *,
    tracker: RunTracker,
    callback: "UsageCallback",
    run_id: RunId,
    node_name: str,
    node_type: NodeType,
    input_summary: Optional[str] = None,
    logger: LoggerInterface,
) -> AsyncIterator[_StepContext]:
    """노드 실행 1회의 lifecycle 인터셉트 (Design §4.1).

    - enter: record_step(STARTED) + callback.enter_step + RunContext.step_id 갱신
    - exit (normal): update_step(SUCCESS, output_summary) + callback.exit_step + 복원
    - exit (exception): update_step(FAILED, error_text) + callback.exit_step + 복원 + re-raise
    - best-effort: record_step 실패 → step_id=None, enter_step skip, update_step skip
    """
    next_index = callback._step_index + 1  # M3: monotonic counter
    step_id = await _record_step_best_effort(
        tracker=tracker,
        run_id=run_id,
        step_index=next_index,
        node_name=node_name,
        node_type=node_type,
        input_summary=_truncate(input_summary, _INPUT_SUMMARY_MAX_CHARS),
        logger=logger,
    )

    prev_step_id = callback._current_step_id
    prev_ctx = get_current_run_context()

    if step_id is not None:
        callback.enter_step(step_id)  # _step_index 자동 increment
        if prev_ctx is not None:
            set_current_run_context(with_step_id(prev_ctx, step_id))

    step_ctx = _StepContext(step_id=step_id)
    try:
        yield step_ctx
    except BaseException as e:
        await _update_step_best_effort(
            tracker=tracker,
            run_id=run_id,
            step_id=step_id,
            status=StepStatus.FAILED,
            output_summary=None,
            error_text=_truncate(str(e), _ERROR_TEXT_MAX_CHARS),
            logger=logger,
            node_name=node_name,
        )
        _restore_context(callback, prev_step_id, prev_ctx)
        raise
    else:
        await _update_step_best_effort(
            tracker=tracker,
            run_id=run_id,
            step_id=step_id,
            status=StepStatus.SUCCESS,
            output_summary=_truncate(step_ctx.output_summary, _OUTPUT_SUMMARY_MAX_CHARS),
            error_text=None,
            logger=logger,
            node_name=node_name,
        )
        _restore_context(callback, prev_step_id, prev_ctx)
