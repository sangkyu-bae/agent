"""Supervisor 그래프 노드 함수: supervisor, quality_gate, routing."""
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field

from src.application.agent_builder.supervisor_hooks import SupervisorHooks
from src.application.agent_builder.supervisor_state import SupervisorState
from src.domain.agent_builder.policies import QualityGatePolicy
from src.domain.agent_builder.schemas import SupervisorConfig, WorkerDefinition
from src.domain.logging.interfaces.logger_interface import LoggerInterface


def build_initial_state(
    messages: list[dict],
    config: SupervisorConfig,
    available_workers: list[str],
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
        "quality_gate_result": "",
    }


class SupervisorDecision(BaseModel):
    next: str = Field(description="다음 호출할 worker_id 또는 'FINISH'")
    reasoning: str = Field(description="선택 이유")


def create_supervisor_node(
    llm: BaseChatModel,
    workers: list[WorkerDefinition],
    supervisor_prompt: str,
    hooks: SupervisorHooks,
    logger: LoggerInterface,
):
    worker_descriptions = "\n".join(
        f"- {w.worker_id}: {w.description}" for w in workers
    )
    available_ids = {w.worker_id for w in workers}

    async def supervisor_node(state: SupervisorState) -> dict:
        if state["iteration_count"] >= state["max_iterations"]:
            logger.warning("max_iterations reached",
                           iteration_count=state["iteration_count"])
            return {"next_worker": "__end__"}

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

        decision_prompt = (
            f"{supervisor_prompt}\n\n"
            f"사용 가능한 워커:\n{worker_descriptions}\n\n"
            f"다음 중 선택하세요:\n"
            f"- 워커 호출이 필요하면 해당 worker_id를 선택\n"
            f"- 모든 작업이 완료되었으면 'FINISH'를 선택\n"
            f"스킵된 워커(사용 불가): {skipped}"
        )

        messages = state["messages"] + [
            {"role": "system", "content": decision_prompt}
        ]

        try:
            llm_with_structure = llm.with_structured_output(SupervisorDecision)
            decision = await llm_with_structure.ainvoke(messages)
            next_worker = decision.next
        except Exception:
            logger.error("supervisor LLM decision failed, falling back to __end__")
            return {"next_worker": "__end__"}

        if next_worker == "FINISH":
            next_worker = "__end__"
        elif next_worker in skipped:
            next_worker = "__end__"
        elif next_worker not in available_ids and next_worker != "__end__":
            logger.warning("invalid worker selected", selected=next_worker)
            next_worker = "__end__"

        return {
            "next_worker": next_worker,
            "skipped_workers": skipped,
            "iteration_count": state["iteration_count"] + 1,
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
                f"[품질검증 실패] 응답이 기준에 미달합니다. "
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


def route_after_quality(state: SupervisorState) -> str:
    next_worker = state.get("next_worker", "")
    if next_worker and next_worker != "__end__":
        return next_worker
    return "supervisor"
