"""서브에이전트 입력 조립 전략.

Design Ref: subagent-context-scope §3.2/§3.4 (Option C).

부모 SupervisorState → 서브에이전트 초기 messages. 판별·상한 규칙은 domain
`SubAgentContextPolicy`가 소유하고, 여기서는 LangChain 메시지를 MessageView로
바꾸고 블록을 메시지 배열로 조립만 한다.

`resolve_strategy`는 연결별 설정(context_mode, 다음 사이클)의 유일한 분기 지점
이다(FR-09). 지금은 항상 기본 전략을 돌려준다.
"""
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from src.application.agent_builder.search_pipeline import QUALITY_FEEDBACK_PREFIX
from src.application.agent_builder.supervisor_state import SupervisorState
from src.domain.agent_builder.rag_tool_config import clamp_llm_name
from src.domain.agent_builder.schemas import WorkerDefinition
from src.domain.agent_builder.sub_agent_context_policy import (
    MessageView,
    ReferenceBlock,
    SubAgentContextPolicy,
)


@dataclass(frozen=True)
class SubAgentInput:
    """서브 그래프 초기 messages(build_initial_state 입력) + step 요약."""

    messages: list[dict]
    summary: str


@runtime_checkable
class SubAgentContextStrategy(Protocol):
    def build(self, state: SupervisorState, worker_id: str) -> SubAgentInput: ...


def to_message_views(messages: list) -> list[MessageView]:
    """LangChain 메시지·dict → MessageView. 해석 불가 값은 빈 문자열로 둔다."""
    return [_to_view(msg) for msg in messages or ()]


def _to_view(msg) -> MessageView:
    if isinstance(msg, dict):
        raw_role = msg.get("role")
        name = msg.get("name")
        content = msg.get("content", "")
    else:
        raw_role = getattr(msg, "type", None)
        name = getattr(msg, "name", None)
        content = getattr(msg, "content", "")
    return MessageView(
        role=SubAgentContextPolicy.normalize_role(raw_role),
        name=name if isinstance(name, str) else "",
        content=content if isinstance(content, str) else str(content),
    )


def _legacy_content(messages: list) -> str:
    """현행 동작(마지막 메시지 1건)과 바이트 동일한 본문 — fail-safe 경로 (D-08)."""
    if not messages:
        return ""
    last = messages[-1]
    return last.content if hasattr(last, "content") else str(last)


def legacy_input(messages: list) -> SubAgentInput:
    """fail-safe 입력 — 조립 불가·전략 예외 시 현행 동작 그대로 (D-08)."""
    return SubAgentInput(
        messages=[{"role": "user", "content": _legacy_content(messages)}],
        summary=SubAgentContextPolicy.summarize(
            has_origin=False,
            ref=ReferenceBlock(text="", item_count=0, total_chars=0, truncated=False),
            retry=False,
            fallback=True,
        ),
    )


class TaskWithOriginStrategy:
    """기본 전략: [원 질문] + [참고 자료] + [현재 작업(+재시도 사유)]."""

    def __init__(self, policy: SubAgentContextPolicy | None = None) -> None:
        self._policy = policy or SubAgentContextPolicy(
            feedback_prefixes=(QUALITY_FEEDBACK_PREFIX,)
        )

    def build(self, state: SupervisorState, worker_id: str) -> SubAgentInput:
        messages = state.get("messages", [])
        views = to_message_views(messages)
        origin_index = self._policy.find_origin_index(views)
        origin = views[origin_index].content if origin_index is not None else ""
        task = (state.get("worker_task") or "").strip()

        # Design Ref: §3.4 fallback — 원 질문도 과제도 없으면 현행 입력 그대로.
        if not origin and not task:
            return legacy_input(messages)

        # FR-12: 산출 메시지 이름은 clamp_llm_name을 거친다 — 같은 기준으로 비교.
        refs = self._policy.collect_references(
            views, origin_index, clamp_llm_name(worker_id)
        )
        ref_block = self._policy.render_references(refs)
        feedback = self._policy.detect_retry_feedback(views)
        blocks = self._blocks(task, origin, ref_block.text, feedback)
        return SubAgentInput(
            messages=[{"role": "user", "content": b} for b in blocks],
            summary=self._policy.summarize(
                has_origin=bool(origin), ref=ref_block,
                retry=bool(feedback), fallback=False,
            ),
        )

    def _blocks(
        self, task: str, origin: str, references: str, feedback: str
    ) -> list[str]:
        """D-04: 마지막을 [현재 작업]으로 — 자식 latest_user_question()이 과제를 집는다.

        과제가 비어 원 질문이 과제가 되면 [원 질문] 블록은 중복이라 생략한다.
        """
        blocks: list[str] = []
        if origin and task:
            blocks.append(self._policy.origin_block(origin))
        if references:
            blocks.append(references)
        blocks.append(self._policy.compose_task(task, origin, feedback))
        return blocks


def resolve_strategy(
    worker_def: WorkerDefinition,
    default: SubAgentContextStrategy,
) -> SubAgentContextStrategy:
    """워커별 전략 선택 — 다음 사이클 context_mode 분기의 유일한 지점 (FR-09).

    현재는 연결별 설정이 없으므로 항상 default.
    """
    return default
