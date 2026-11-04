"""실시간 경로용 도구 실행 내역 조회 — 세션 1개를 열어 서비스에 넘긴다.

Design Ref: agent-run-tool-trace §2.2 — SessionScopedRunSourcesReader 와 같은 이유로
스트림 중에는 요청 세션을 쓰지 않는다. 답변 직전 조회가 그래프 실행에 쓰인 세션
스냅샷에 묶이면 방금 기록된 도구 호출을 못 볼 수 있다.
"""
from typing import Any, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.agent_run.interfaces import RunToolTraceReaderPort
from src.domain.agent_run.tool_trace_policy import ToolTrace
from src.domain.agent_run.value_objects import RunId
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class SessionScopedRunToolTraceReader(RunToolTraceReaderPort):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        service_builder: Callable[[AsyncSession], Any],
        logger: LoggerInterface,
    ) -> None:
        self._session_factory = session_factory
        self._service_builder = service_builder
        self._logger = logger

    async def load_for_run(
        self, run_id: RunId, request_id: str,
    ) -> Optional[ToolTrace]:
        try:
            async with self._session_factory() as session:
                service = self._service_builder(session)
                built = await service.build_for_runs([run_id], request_id)
        except Exception as e:
            # 서비스 바깥(세션 획득)의 실패도 답변을 막지 않는다 (Design §6).
            self._logger.warning(
                "run tool trace load failed",
                exception=e, request_id=request_id, run_id=run_id.value,
            )
            return None
        return built.get(run_id.value)
