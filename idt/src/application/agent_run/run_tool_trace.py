"""실행 기록에서 표시용 도구 실행 내역을 모은다.

Design Ref: agent-run-tool-trace §2.1 — 실시간(답변 완료 payload)과 재진입(세션 API)이
공유하는 단일 경로. 같은 서비스·같은 정책을 지나 두 화면의 내역이 일치한다 (Plan R4).
Design Ref: §6 — 내역은 부가 정보이므로 실패는 여기서 흡수하고 답변을 막지 않는다.
"""
from src.application.agent_run.tool_catalog_lookup import ToolCatalogLookup
from src.domain.agent_run.interfaces import AgentRunRepositoryInterface
from src.domain.agent_run.tool_trace_policy import (
    ToolTrace,
    ToolTraceEvidence,
    ToolTracePolicy,
)
from src.domain.agent_run.value_objects import RunId
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.tool_catalog.interfaces import ToolCatalogRepositoryInterface


class RunToolTraceService:
    def __init__(
        self,
        agent_run_repo: AgentRunRepositoryInterface,
        tool_catalog_repo: ToolCatalogRepositoryInterface,
        logger: LoggerInterface,
        *,
        max_items: int,
    ) -> None:
        self._agent_run_repo = agent_run_repo
        self._catalog = ToolCatalogLookup(tool_catalog_repo, logger)
        self._logger = logger
        self._max_items = max_items

    async def build_for_runs(
        self, run_ids: list[RunId], request_id: str,
    ) -> dict[str, ToolTrace]:
        """run_id 문자열 → 내역. 도구 호출이 없는 런은 키가 없다.

        쿼리 수는 런 개수와 무관하다: 도구 호출 1 + step 1 + 카탈로그 1.
        """
        if not run_ids:
            return {}
        try:
            tool_calls = await self._agent_run_repo.find_tool_calls_by_runs(run_ids)
            if not any(tool_calls.values()):
                return {}
            steps = await self._agent_run_repo.find_steps_by_runs(run_ids)
        except Exception as e:
            self._logger.warning(
                "run tool trace evidence read failed",
                exception=e, request_id=request_id, run_count=len(run_ids),
            )
            return {}
        all_calls = [call for calls in tool_calls.values() for call in calls]
        # 카탈로그 실패는 lookup 이 흡수한다 — 내역은 이름 폴백(R-03)으로 계속 낸다.
        tools = await self._catalog.resolve(all_calls, request_id)
        built: dict[str, ToolTrace] = {}
        for run_id in run_ids:
            calls = tool_calls.get(run_id.value, [])
            if not calls:
                continue
            evidence = ToolTraceEvidence(
                tool_calls=calls, steps=steps.get(run_id.value, []), tools=tools,
            )
            try:
                trace = ToolTracePolicy.build(evidence, max_items=self._max_items)
            except Exception as e:
                # 한 런의 예상 밖 데이터가 같은 세션의 다른 런 내역까지 막지 않게 한다.
                self._logger.warning(
                    "run tool trace build failed",
                    exception=e, request_id=request_id, run_id=run_id.value,
                )
                continue
            if trace.items:
                built[run_id.value] = trace
        return built
