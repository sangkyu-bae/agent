"""LangGraphPlanner: LangGraph StateGraph 기반 PlannerInterface 구현."""
from __future__ import annotations

import json
from typing import Optional

from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.planner.interfaces import PlannerInterface
from src.domain.planner.policies import PlannerPolicy
from src.domain.planner.schemas import PlanResult, PlanStep

_SYSTEM_PROMPT = """\
당신은 복잡한 질문을 단계별 실행 계획으로 분해하는 전문가입니다.
반드시 다음 JSON 형식으로만 응답하세요 (다른 텍스트 없이):
{
  "steps": [
    {
      "step_index": 0,
      "description": "이 단계에서 할 일",
      "tool_ids": [],
      "search_strategy": "hybrid",
      "expected_output": "이 단계의 예상 출력"
    }
  ],
  "confidence": 0.0,
  "reasoning": "계획 수립 근거",
  "requires_clarification": false,
  "clarifying_questions": []
}

search_strategy 값: "vector" | "bm25" | "hybrid" | null
confidence: 0.0 ~ 1.0 (0.75 이상이면 계획 확정)
"""

_REPLAN_SUFFIX = """\

이전 계획의 문제점을 고려하여 더 구체적이고 신뢰도 높은 계획을 다시 작성하세요.
이전 confidence: {prev_confidence:.2f}
이전 reasoning: {prev_reasoning}
"""


class _PlannerState(TypedDict):
    query: str
    context: dict
    plan_result: Optional[PlanResult]
    attempt_count: int
    request_id: str


class LangGraphPlanner(PlannerInterface):
    """LangGraph StateGraph 기반 Planner 구현체."""

    def __init__(self, llm: BaseChatModel, logger: LoggerInterface) -> None:
        self._llm = llm
        self._logger = logger
        self._graph = self._build_graph()

    def _build_graph(self):
        graph: StateGraph = StateGraph(_PlannerState)
        graph.add_node("plan_node", self._plan_node)
        graph.add_node("validate_node", self._validate_node)
        graph.add_node("replan_node", self._replan_node)

        graph.set_entry_point("plan_node")
        graph.add_edge("plan_node", "validate_node")
        graph.add_conditional_edges(
            "validate_node",
            self._route_after_validate,
            {"end": END, "replan": "replan_node"},
        )
        graph.add_edge("replan_node", "validate_node")
        return graph.compile()

    async def plan(self, query: str, context: dict, request_id: str) -> PlanResult:
        initial: _PlannerState = {
            "query": query,
            "context": context,
            "plan_result": None,
            "attempt_count": 0,
            "request_id": request_id,
        }
        final = await self._graph.ainvoke(initial)
        return final["plan_result"]

    async def _plan_node(self, state: _PlannerState) -> _PlannerState:
        prompt = self._build_prompt(state["query"], state["context"], replan=False)
        raw = await self._llm.ainvoke(prompt)
        plan_result = self._parse_llm_response(raw.content, state["query"], state["request_id"])
        return {**state, "plan_result": plan_result, "attempt_count": 1}

    async def _validate_node(self, state: _PlannerState) -> _PlannerState:
        return state

    async def _replan_node(self, state: _PlannerState) -> _PlannerState:
        self._logger.info(
            "Replanning",
            request_id=state["request_id"],
            attempt=state["attempt_count"],
            confidence=state["plan_result"].confidence if state["plan_result"] else 0.0,
        )
        prompt = self._build_prompt(
            state["query"],
            state["context"],
            replan=True,
            prev_result=state["plan_result"],
        )
        raw = await self._llm.ainvoke(prompt)
        plan_result = self._parse_llm_response(raw.content, state["query"], state["request_id"])
        return {**state, "plan_result": plan_result, "attempt_count": state["attempt_count"] + 1}

    def _route_after_validate(self, state: _PlannerState) -> str:
        result = state["plan_result"]
        if result is None:
            return "end"
        if PlannerPolicy.is_max_attempts_reached(state["attempt_count"]):
            self._logger.warning(
                "Max replan attempts reached",
                request_id=state["request_id"],
                attempt=state["attempt_count"],
                confidence=result.confidence,
            )
            return "end"
        if PlannerPolicy.is_plan_acceptable(result):
            return "end"
        return "replan"

    def _build_prompt(
        self,
        query: str,
        context: dict,
        replan: bool,
        prev_result: Optional[PlanResult] = None,
    ) -> list[dict]:
        system = _SYSTEM_PROMPT
        if replan and prev_result is not None:
            system += _REPLAN_SUFFIX.format(
                prev_confidence=prev_result.confidence,
                prev_reasoning=prev_result.reasoning,
            )
        user_content = f"질문: {query}"
        if context:
            user_content += f"\n컨텍스트: {json.dumps(context, ensure_ascii=False)}"

        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]

    def _parse_llm_response(
        self, content: str, query: str, request_id: str
    ) -> PlanResult:
        try:
            data = json.loads(content)
            steps = [PlanStep(**s) for s in data.get("steps", [])]
            return PlanResult(
                query=query,
                steps=steps,
                confidence=float(data.get("confidence", 0.0)),
                reasoning=data.get("reasoning", ""),
                requires_clarification=bool(data.get("requires_clarification", False)),
                clarifying_questions=data.get("clarifying_questions", []),
            )
        except Exception as e:
            self._logger.warning(
                "LLM response parse failed",
                exception=e,
                request_id=request_id,
            )
            return PlanResult(
                query=query,
                steps=[],
                confidence=0.0,
                reasoning="JSON parse failed",
            )
