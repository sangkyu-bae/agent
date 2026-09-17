"""deep-search-pipeline 서브그래프 조립 + 노드 팩토리 (Design §2.1, §4.1).

`create_deep_search_node`는 기존 `create_search_pipeline_node`와 파라미터
이름·순서·개수가 동일하며 동일한 반환 계약을 지킨다 (FR-12) — 컴파일러에서
한 줄로 교체 가능하게 하기 위함이다.
"""
from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage
from langgraph.graph import END, StateGraph

from src.application.agent_builder.search_pipeline import (
    format_search_result,
    is_worker_output,
    latest_user_question,
)
from src.application.agent_run.step_tracking import STEP_OUTPUT_SUMMARY_KEY
from src.application.deep_search.nodes import (
    NodeDeps,
    make_evaluate_node,
    make_execute_node,
    make_extract_node,
    make_finalize_node,
    make_plan_node,
    route_after_evaluate,
    safe_search,
)
from src.application.deep_search.rendering import SUMMARY_MAX_CHARS, render_summary
from src.domain.agent_builder.rag_tool_config import clamp_llm_name
from src.domain.deep_search.policies import DeepSearchBudgetPolicy
from src.domain.deep_search.schemas import DeepSearchState, StopReason
from src.domain.logging.interfaces.logger_interface import LoggerInterface

# 대화 맥락 직렬화 상수 — 기존 search_pipeline 관례와 동일하게 맞춘다 (D5).
_CONTEXT_MAX_MESSAGES = 6
_CONTEXT_MSG_SLICE = 500

# 최악 경로 노드 수(plan + (execute+extract+evaluate)×N + finalize)보다 크게 잡아
# state 가드(4중 종료 조건)가 항상 먼저 발동하게 한다.
_RECURSION_STEP_FACTOR = 4
_RECURSION_BUFFER = 10


def _message_text(msg: Any) -> str:
    if isinstance(msg, dict):
        return str(msg.get("content", ""))
    return str(getattr(msg, "content", ""))


def _message_role(msg: Any) -> str:
    if isinstance(msg, dict):
        return str(msg.get("role", ""))
    return str(getattr(msg, "type", ""))


def collect_context(messages: list) -> str:
    """워커 산출물을 제외한 최근 대화 맥락 직렬화."""
    conversation = [m for m in messages if not is_worker_output(m)]
    recent = conversation[-_CONTEXT_MAX_MESSAGES:]
    return "\n".join(
        f"{_message_role(m)}: {_message_text(m)[:_CONTEXT_MSG_SLICE]}" for m in recent
    )


def build_initial_state(
    question: str, context: str, user_context: str,
) -> DeepSearchState:
    return {
        "question": question,
        "context": context,
        "user_context": user_context,
        "strategy": "",
        "requirements": [],
        "pending_queries": [],
        "query_history": [],
        "raw_results": [],
        "evidence": [],
        "iteration": 0,
        "new_evidence_count": 0,
        "can_retry": True,
        "stop_reason": "",
        "search_ok": False,
        "extract_degraded": False,
        "plan_fallback": False,
        "llm_chars": 0,
        "body": "",
        "summary": "",
    }


def build_graph(deps: NodeDeps):
    """5노드 서브그래프 (Design §2.1). 팩토리 호출 시 1회만 compile된다 (D10)."""
    graph = StateGraph(DeepSearchState)
    graph.add_node("plan", make_plan_node(deps))
    graph.add_node("execute", make_execute_node(deps))
    graph.add_node("extract", make_extract_node(deps))
    graph.add_node("evaluate", make_evaluate_node(deps))
    graph.add_node("finalize", make_finalize_node(deps))

    graph.set_entry_point("plan")
    graph.add_edge("plan", "execute")
    graph.add_edge("execute", "extract")
    graph.add_edge("extract", "evaluate")
    graph.add_conditional_edges(
        "evaluate", route_after_evaluate,
        {"execute": "execute", "finalize": "finalize"},
    )
    graph.add_edge("finalize", END)

    limit = deps.budget.max_iteration * _RECURSION_STEP_FACTOR + _RECURSION_BUFFER
    return graph.compile().with_config({"recursion_limit": limit})


async def _run_graph(graph, state: DeepSearchState) -> dict:
    """서브그래프 실행 — 테스트에서 대체 가능한 이음매."""
    return await graph.ainvoke(state)


async def _legacy_fallback(deps: NodeDeps, question: str) -> tuple[str, str]:
    """E10: 서브그래프가 통째로 실패했을 때의 단일 쿼리 검색."""
    _, _, text = await safe_search(deps, question)
    summary = render_summary({
        "strategy": "fallback",
        "iteration": 0,
        "requirements": [],
        "stop_reason": StopReason.FALLBACK.value,
        "query_history": [question],
        "evidence": [],
    })
    return text, summary


def create_deep_search_node(
    worker_id: str,
    tool,
    pipeline_llm,
    policy: DeepSearchBudgetPolicy,
    logger: LoggerInterface,
    user_context_block: str = "",
    datetime_block: str = "",
    worker_context_block: str = "",
):
    """Requirement 분해 → 병렬 검색 → 근거 누적 → 커버리지 검증 → 선택적 재검색.

    시그니처·반환 계약 모두 `create_search_pipeline_node`와 동일하다 (AD-1/FR-12).

    runtime-datetime-context D4: datetime_block은 사용자 블록보다 앞에 prepend —
    쿼리를 작성하는 plan LLM과 시점 제약을 판정하는 evaluate LLM이 날짜를 알아야 한다.
    worker-context-injection §4.1 (GAP-01): worker_context_block은 사용자 블록 뒤 —
    쿼리를 작성하는 plan LLM이 에이전트 맥락과 자기 역할을 알아야 한다.
    """
    # Design Ref: runtime-datetime-context §D4 — 순서: 날짜 → 사용자 → 워커 → 본문
    context_block = datetime_block + user_context_block + worker_context_block
    deps = NodeDeps(
        tool=tool,
        llm=pipeline_llm,
        budget=policy,
        logger=logger,
        user_context=context_block,
    )
    graph = build_graph(deps)

    async def search_node(state) -> dict:
        messages = state["messages"]
        question = latest_user_question(messages) or _message_text(messages[-1])
        initial = build_initial_state(
            question, collect_context(messages), context_block,
        )
        llm_chars = 0
        try:
            final = await _run_graph(graph, initial)
            body, summary = final["body"], final["summary"]
            llm_chars = final.get("llm_chars", 0)
        except Exception as e:
            logger.error(
                "deep_search subgraph failed, falling back to single search", exception=e,
            )
            body, summary = await _legacy_fallback(deps, question)

        message = AIMessage(
            content=format_search_result(worker_id, body), name=clamp_llm_name(worker_id),
        )
        return {
            "messages": [message],
            "last_worker_id": worker_id,
            "token_usage": state["token_usage"] + (len(body) + llm_chars) // 4,
            STEP_OUTPUT_SUMMARY_KEY: summary[:SUMMARY_MAX_CHARS],
        }

    return search_node
