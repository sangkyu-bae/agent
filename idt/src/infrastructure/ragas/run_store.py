"""SessionScopedEvalRunStore — 배치 실행기용 독립 짧은 세션 스토어.

section_summary JobStore(D11) 패턴: 연산마다 session_factory로 새 세션을 열고
begin 블록 종료 시 자동 commit. 요청 스코프 세션과 분리되어 백그라운드
태스크에서 안전하게 사용한다. (Repository 내부 commit 금지 규칙과 무관 —
commit은 begin 컨텍스트가 수행)
"""
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.ragas.entities import EvaluationResult, EvaluationRun
from src.domain.ragas.interfaces import EvalRunStoreInterface
from src.infrastructure.ragas.repository import EvaluationRepository


class SessionScopedEvalRunStore(EvalRunStoreInterface):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        logger: LoggerInterface,
    ) -> None:
        self._session_factory = session_factory
        self._logger = logger

    async def get_run(self, run_id: str, request_id: str) -> EvaluationRun | None:
        async with self._session_factory() as session:
            async with session.begin():
                repo = EvaluationRepository(session=session, logger=self._logger)
                return await repo.get_run(run_id, request_id)

    async def update_run(self, run: EvaluationRun, request_id: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                repo = EvaluationRepository(session=session, logger=self._logger)
                await repo.update_run(run, request_id)

    async def save_results_bulk(
        self, results: list[EvaluationResult], request_id: str
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                repo = EvaluationRepository(session=session, logger=self._logger)
                await repo.save_results_bulk(results, request_id)
