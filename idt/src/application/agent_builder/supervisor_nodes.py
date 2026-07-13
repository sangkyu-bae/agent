"""Supervisor 그래프 노드 함수: supervisor, quality_gate, routing."""
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field

from src.application.agent_builder.message_normalization import ensure_user_tail
from src.application.agent_builder.search_pipeline import (
    QUALITY_FEEDBACK_PREFIX,
    is_search_result,
    latest_user_question,
)
from src.application.agent_builder.supervisor_hooks import SupervisorHooks
from src.application.agent_builder.supervisor_state import SupervisorState
from src.application.agent_run.context import get_current_run_context
from src.domain.agent_builder.policies import QualityGatePolicy
from src.domain.agent_builder.schemas import SupervisorConfig, WorkerDefinition
from src.domain.agent_run.value_objects import RunPurpose
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.visualization.policies import VisualizationRoutingPolicy


def _render_attachment_block(attachments: list[dict] | None) -> str:
    """첨부 목록 → supervisor decision용 인지 블록 (없으면 빈 문자열).

    임시경로 노출 방지: file_name이 있으면 표기, 없으면 타입만 표기.
    """
    if not attachments:
        return ""
    labels = []
    for a in attachments:
        kind = a.get("type", "파일")
        name = a.get("file_name")
        labels.append(f"{kind}({name})" if name else kind)
    joined = ", ".join(labels)
    return (
        f"\n\n[첨부된 데이터]\n사용자가 다음을 첨부했습니다: {joined}.\n"
        f"이 데이터를 분석할 수 있는 워커가 사용 가능 목록에 있으면, "
        f"권한이 없다고 거부하지 말고 반드시 그 워커로 라우팅하세요."
    )


def _summarize_data_entry(index: int, msg) -> str:
    """검색결과 메시지 1건 → 인지 블록 요약 1줄 (본문 미포함 — 토큰 절약)."""
    content = getattr(msg, "content", "")
    body_lines = content.splitlines()[1:]  # 첫 줄은 "[worker 검색결과]" 헤더
    head = body_lines[0][:80] if body_lines else ""
    return f"{index}. {getattr(msg, 'name', '')} — {head} ({len(content)}자)"


def _render_data_context_block(messages: list) -> str:
    """state 내 검색결과(현재 턴 수집분 + 재주입분) → 보유 데이터 인지 블록.

    analysis-data-continuity Design §3.5 (D5): supervisor가 보유 데이터 범위를
    근거로 재사용(분석 직행) vs 재수집(검색 워커 우선)을 판단하게 한다.
    없으면 빈 문자열.
    """
    entries = [m for m in messages if is_search_result(m)]
    if not entries:
        return ""
    lines = "\n".join(
        _summarize_data_entry(i, m) for i, m in enumerate(entries, 1)
    )
    return (
        f"\n\n[보유 분석 데이터]\n{lines}\n"
        f"- 요청이 보유 데이터 범위 안이면 데이터 재수집 없이 분석 워커를 호출하세요.\n"
        f"- 요청이 보유 데이터 범위를 벗어나면(대상·기간·집단 확대 등) "
        f"먼저 검색 워커로 새 데이터를 수집한 뒤 분석 워커를 호출하세요."
    )


def _render_viz_guidance_block(
    messages: list,
    analysis_worker_ids: list[str],
    viz_policy: VisualizationRoutingPolicy | None,
) -> str:
    """시각화 요청 감지 시 supervisor decision용 인지 블록 (아니면 빈 문자열).

    차트는 분석 워커 직후 경로(chart_router → chart_builder)에서만 생성되므로,
    LLM이 검색 결과만으로 FINISH 하지 않도록 경로 제약을 명시한다.
    판단 기준은 강제 라우팅 Hook·chart_router와 동일한 도메인 정책을 공유한다.
    """
    if viz_policy is None or not analysis_worker_ids:
        return ""
    if not viz_policy.explicit_request(latest_user_question(messages)):
        return ""
    ids = ", ".join(analysis_worker_ids)
    return (
        f"\n\n[시각화 안내]\n"
        f"사용자가 그래프/차트 시각화를 요청했습니다. "
        f"차트는 분석 워커({ids})를 거쳐야만 생성됩니다.\n"
        f"외부 데이터가 필요하면 먼저 검색 워커로 데이터를 수집한 뒤, "
        f"반드시 분석 워커를 호출하세요. "
        f"검색 결과만 모은 상태에서 FINISH 하지 마세요."
    )


def _set_purpose_if_context(purpose: RunPurpose) -> None:
    """AGENT-OBS-001 §14-1: 노드 진입 시 purpose 명시.

    ContextVar에 RunContext가 없는 경우(테스트·외부 호출) 조용히 통과.
    """
    ctx = get_current_run_context()
    if ctx is not None:
        try:
            ctx.callback.set_purpose(purpose)
        except Exception:
            pass  # 관측성 실패는 본 흐름 차단 X


def build_initial_state(
    messages: list[dict],
    config: SupervisorConfig,
    available_workers: list[str],
    attachments: list[dict] | None = None,
) -> SupervisorState:
    return {
        "messages": messages,
        "iteration_count": 0,
        "max_iterations": config.max_iterations,
        "token_usage": 0,
        "token_limit": config.token_limit,
        "next_worker": "",
        "last_worker_id": "",
        "available_workers": available_workers,
        "quality_gate_enabled": config.quality_gate_enabled,
        "retry_counts": {},
        "max_retries_per_worker": config.max_retries_per_worker,
        "forced_worker": "",
        "skipped_workers": [],
        "limit_reached": False,
        "quality_gate_result": "",
        "attachments": attachments or [],
        "viz_decision": "",
        "charts": [],
        "visualization_done": False,
        "analysis_source": [],
    }


SUPERVISOR_TAIL_INSTRUCTION = (
    "위 대화와 워커 결과를 바탕으로 다음 행동(워커 선택 또는 FINISH)을 결정하세요."
)


class SupervisorDecision(BaseModel):
    next: str = Field(description="다음 호출할 worker_id 또는 'FINISH'")
    reasoning: str = Field(description="선택 이유")
    answer: str = Field(
        default="",
        description="FINISH 선택 시 사용자에게 전달할 응답. 워커 호출 없이 직접 답변할 때 작성.",
    )


def create_supervisor_node(
    llm: BaseChatModel,
    workers: list[WorkerDefinition],
    supervisor_prompt: str,
    hooks: SupervisorHooks,
    logger: LoggerInterface,
    analysis_worker_ids: list[str] | None = None,
    viz_policy: VisualizationRoutingPolicy | None = None,
):
    worker_descriptions = "\n".join(
        f"- {w.worker_id}: {w.description}" for w in workers
    )
    available_ids = {w.worker_id for w in workers}

    async def supervisor_node(state: SupervisorState) -> dict:
        _set_purpose_if_context(RunPurpose.SUPERVISOR)
        if state["iteration_count"] >= state["max_iterations"]:
            # agent-recursion-limit D5: 오류·침묵 종료가 아니라 조기 답변 경로로.
            # limit_reached는 라우팅(final_answer 우회)·안내 지시·payload 플래그의 신호.
            logger.warning("max_iterations reached",
                           iteration_count=state["iteration_count"])
            return {"next_worker": "__end__", "limit_reached": True}

        if state["token_usage"] >= state["token_limit"]:
            logger.warning("token_limit reached",
                           token_usage=state["token_usage"])
            return {"next_worker": "__end__"}

        forced = hooks.force_worker(state)
        if forced:
            return {
                "next_worker": forced,
                "forced_worker": forced,
                "iteration_count": state["iteration_count"] + 1,
            }

        skipped = hooks.skip_workers(state)

        # 첨부 인지 블록 — supervisor가 첨부 데이터의 존재를 알게 한다.
        attachment_block = _render_attachment_block(state.get("attachments", []))
        # 보유 데이터 인지 블록 — 재사용 vs 재수집 판단 근거 (analysis-data-continuity).
        data_block = _render_data_context_block(state["messages"])
        # 시각화 인지 블록 — 차트는 분석 워커 경유 필수임을 LLM에 알린다.
        viz_block = _render_viz_guidance_block(
            state["messages"], analysis_worker_ids or [], viz_policy,
        )

        decision_prompt = (
            f"{supervisor_prompt}\n\n"
            f"사용 가능한 워커:\n{worker_descriptions}"
            f"{attachment_block}"
            f"{data_block}"
            f"{viz_block}\n\n"
            f"다음 중 선택하세요:\n"
            f"- 워커 호출이 필요하면 해당 worker_id를 선택\n"
            f"- 처리 가능한 워커가 사용 가능 목록에 있으면 거부하지 말고 그 워커를 선택\n"
            f"- 어떤 워커로도 처리할 수 없을 때만 'FINISH'를 선택하고 "
            f"answer 필드에 사용자에게 전달할 자연스러운 응답을 작성하세요\n"
            f"- 모든 작업이 완료되었으면 'FINISH'를 선택 (워커를 이미 호출했다면 "
            f"최종 답변은 시스템이 워커 결과를 종합해 생성하므로 answer는 비워두세요)\n"
            f"스킵된 워커(사용 불가): {skipped}"
        )

        # fix-anthropic-prefill-error D2: 결정 프롬프트를 끝 system으로 두면
        # langchain_anthropic이 top-level system으로 끌어올려 배열이 워커
        # AIMessage로 끝남(=prefill) → Claude 4.6+ 400. system 선두 배치 +
        # assistant-last면 지시 HumanMessage를 후미에 append.
        messages = ensure_user_tail(
            [{"role": "system", "content": decision_prompt}, *state["messages"]],
            instruction=SUPERVISOR_TAIL_INSTRUCTION,
        )

        try:
            llm_with_structure = llm.with_structured_output(SupervisorDecision)
            decision = await llm_with_structure.ainvoke(messages)
            next_worker = decision.next
        except Exception as e:
            logger.error(
                "supervisor LLM decision failed, falling back to __end__",
                exception=e,
            )
            return {"next_worker": "__end__"}

        # M3 (AGENT-OBS-003): reasoning을 step output_summary로 노출.
        # SupervisorDecision.reasoning은 이미 required 필드라 추가 LLM 토큰 비용 없음.
        step_summary = (decision.reasoning or f"next={next_worker}")[:1024]

        if next_worker == "FINISH":
            next_worker = "__end__"
            # final-answer-node DQ1: 워커가 실행된 런은 final_answer 노드가 최종 답변을
            # 생성하므로 supervisor의 draft answer를 폐기한다(이중 답변·대화 본체 오염 방지).
            if decision.answer and not state["last_worker_id"]:
                from langchain_core.messages import AIMessage
                return {
                    "next_worker": next_worker,
                    "messages": [AIMessage(content=decision.answer)],
                    "skipped_workers": skipped,
                    "iteration_count": state["iteration_count"] + 1,
                    "_step_output_summary": step_summary,
                }
        elif next_worker in skipped:
            next_worker = "__end__"
        elif next_worker not in available_ids and next_worker != "__end__":
            logger.warning("invalid worker selected", selected=next_worker)
            next_worker = "__end__"

        return {
            "next_worker": next_worker,
            "skipped_workers": skipped,
            "iteration_count": state["iteration_count"] + 1,
            "_step_output_summary": step_summary,
        }

    return supervisor_node


def create_quality_gate_node(
    policy: QualityGatePolicy,
    logger: LoggerInterface,
):
    async def quality_gate_node(state: SupervisorState) -> dict:
        if not state["quality_gate_enabled"]:
            return {"next_worker": "", "quality_gate_result": "skipped"}

        last_worker = state["last_worker_id"]
        messages = state["messages"]

        last_ai_msg = None
        for msg in reversed(messages):
            if hasattr(msg, "type") and msg.type == "ai":
                last_ai_msg = msg
                break

        if last_ai_msg is None:
            return {"next_worker": "", "quality_gate_result": "skipped"}

        is_acceptable = policy.check_response(last_ai_msg.content)

        if is_acceptable:
            logger.info("quality_gate passed", worker_id=last_worker)
            return {"next_worker": "", "quality_gate_result": "passed"}

        retry_counts = dict(state["retry_counts"])
        current_retries = retry_counts.get(last_worker, 0)

        if current_retries >= state["max_retries_per_worker"]:
            logger.warning(
                "quality_gate max_retries reached, forcing pass",
                worker_id=last_worker, retries=current_retries,
            )
            return {"next_worker": "", "quality_gate_result": "max_retries"}

        retry_counts[last_worker] = current_retries + 1
        feedback_msg = {
            "role": "user",
            "content": (
                f"{QUALITY_FEEDBACK_PREFIX} 응답이 기준에 미달합니다. "
                f"더 정확하고 구체적인 답변을 다시 생성해주세요. "
                f"(재시도 {current_retries + 1}/{state['max_retries_per_worker']})"
            ),
        }

        logger.info(
            "quality_gate failed, retrying",
            worker_id=last_worker, retry=current_retries + 1,
        )

        return {
            "messages": [feedback_msg],
            "retry_counts": retry_counts,
            "next_worker": last_worker,
            "quality_gate_result": "failed",
        }

    return quality_gate_node


def route_to_worker(state: SupervisorState) -> str:
    return state["next_worker"]


def route_to_worker_or_final(state: SupervisorState) -> str:
    """depth=0 전용: FINISH 시 워커 실행 이력이 있으면 final_answer로 우회.

    final-answer-node Design §3-1 — supervisor LLM의 선택이 아닌 라우팅 함수가
    최종 답변 노드 경유를 구조적으로 보장한다. 워커 미실행(단순 대화)은 즉시 종료.

    agent-recursion-limit D6: 반복 한도 도달(limit_reached) 시에는 워커 미실행이라도
    final_answer로 우회 — 답변 없이 END 직행하는 경로를 차단한다.
    """
    next_worker = state["next_worker"]
    if next_worker == "__end__" and (
        state.get("last_worker_id") or state.get("limit_reached")
    ):
        return "final_answer"
    return next_worker


def route_after_quality(state: SupervisorState) -> str:
    next_worker = state.get("next_worker", "")
    if next_worker and next_worker != "__end__":
        return next_worker
    return "supervisor"
