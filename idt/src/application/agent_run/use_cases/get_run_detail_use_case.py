"""GetRunDetailUseCase: 한 run의 실행 트리 조립 (M4).

agent-run-observability-m4 Design §3.1.

조립 결과: run + steps[] (각 step 안에 llm_calls[] + tool_calls[] (각 tool_call 안에
retrievals[] + llm_calls[])) + orphan_llm_calls[] (step_id NULL).

5회 batch fetch만 사용 (N+1 회피).
"""
from dataclasses import dataclass, field
from typing import Dict, List

from src.application.agent_run.exceptions import (
    RunAccessDeniedError,
    RunNotFoundError,
)
from src.domain.agent_run.entities import (
    AgentRun,
    AgentRunStep,
    LlmCall,
    RetrievalSource,
    ToolCall,
)
from src.domain.agent_run.interfaces import (
    AgentRunRepositoryInterface,
    LlmCallRepositoryInterface,
)
from src.domain.agent_run.value_objects import RunId
from src.domain.logging.interfaces.logger_interface import LoggerInterface


# ── DTO (application 레이어 — Pydantic 변환은 router에서) ──────────────


@dataclass(frozen=True)
class ToolCallNode:
    tool_call: ToolCall
    retrievals: List[RetrievalSource] = field(default_factory=list)
    llm_calls: List[LlmCall] = field(default_factory=list)


@dataclass(frozen=True)
class StepNode:
    step: AgentRunStep
    llm_calls: List[LlmCall] = field(default_factory=list)  # tool_call_id NULL + step_id 있음
    tool_calls: List[ToolCallNode] = field(default_factory=list)


@dataclass(frozen=True)
class RunDetailDto:
    run: AgentRun
    steps: List[StepNode]
    orphan_llm_calls: List[LlmCall]  # step_id IS NULL


class GetRunDetailUseCase:
    def __init__(
        self,
        agent_run_repo: AgentRunRepositoryInterface,
        llm_call_repo: LlmCallRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._agent_run_repo = agent_run_repo
        self._llm_call_repo = llm_call_repo
        self._logger = logger

    async def execute(
        self,
        run_id: str,
        requesting_user_id: str,
        is_admin: bool,
    ) -> RunDetailDto:
        """run + steps + tool_calls + retrievals + llm_calls 트리 조립.

        Raises:
            RunNotFoundError: run 미존재 → router 404
            RunAccessDeniedError: 본인 아님 + non-admin → router 403
        """
        rid = RunId(run_id)
        run = await self._agent_run_repo.find_run(rid)
        if run is None:
            raise RunNotFoundError(run_id)
        if run.user_id != requesting_user_id and not is_admin:
            raise RunAccessDeniedError(run_id)

        # 4 batch fetch (모두 run_id 단일 인덱스)
        steps = await self._agent_run_repo.find_steps(rid)
        tool_calls = await self._agent_run_repo.find_tool_calls(rid)
        retrievals = await self._agent_run_repo.find_retrievals(rid)
        llm_calls = await self._llm_call_repo.find_by_run(rid)

        return _assemble(run, steps, tool_calls, retrievals, llm_calls)


def _assemble(
    run: AgentRun,
    steps: List[AgentRunStep],
    tool_calls: List[ToolCall],
    retrievals: List[RetrievalSource],
    llm_calls: List[LlmCall],
) -> RunDetailDto:
    """client-side join — 모두 in-memory dict."""
    tool_calls_by_step: Dict[str, List[ToolCall]] = {}
    for tc in tool_calls:
        if tc.step_id is None:
            continue
        tool_calls_by_step.setdefault(tc.step_id, []).append(tc)

    retrievals_by_tc: Dict[str, List[RetrievalSource]] = {}
    for r in retrievals:
        if r.tool_call_id is None:
            continue
        retrievals_by_tc.setdefault(r.tool_call_id, []).append(r)

    llm_by_tool_call: Dict[str, List[LlmCall]] = {}
    llm_by_step_no_tool: Dict[str, List[LlmCall]] = {}
    orphan_llms: List[LlmCall] = []
    for lc in llm_calls:
        if lc.tool_call_id is not None:
            llm_by_tool_call.setdefault(lc.tool_call_id, []).append(lc)
        elif lc.step_id is not None:
            llm_by_step_no_tool.setdefault(lc.step_id, []).append(lc)
        else:
            orphan_llms.append(lc)

    step_nodes: List[StepNode] = []
    for step in steps:
        tcs = [
            ToolCallNode(
                tool_call=tc,
                retrievals=retrievals_by_tc.get(tc.id, []),
                llm_calls=llm_by_tool_call.get(tc.id, []),
            )
            for tc in tool_calls_by_step.get(step.id, [])
        ]
        step_nodes.append(
            StepNode(
                step=step,
                llm_calls=llm_by_step_no_tool.get(step.id, []),
                tool_calls=tcs,
            )
        )

    return RunDetailDto(run=run, steps=step_nodes, orphan_llm_calls=orphan_llms)
