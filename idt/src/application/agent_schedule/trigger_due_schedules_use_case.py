"""TriggerDueSchedulesUseCase: 외부 트리거 진입점 (Design §5.2).

- claim → 회차별 실행 → 이력 기록. 각 단계는 자체 짧은 트랜잭션.
  (단일 트랜잭션에 N개 LLM 실행을 묶으면 락 장기 점유 — session_factory 주입
  선례: RunAgentUseCase, src/api/main.py)
- lifespan 싱글턴으로 배선하되 AsyncSession 은 보유하지 않는다 (DB-001).
- 개별 실행 실패는 이력 failed 로 기록하고 다음 스케줄을 계속 처리한다.
"""
from datetime import datetime, timezone
from typing import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from src.application.agent_builder.schemas import RunAgentRequest
from src.application.agent_schedule.schemas import (
    TriggerResponse,
    TriggerStatusResponse,
)
from src.domain.agent_schedule.interfaces import (
    ClaimedSchedule,
    ScheduleRepositoryInterface,
    ScheduleRunSinkInterface,
)
from src.domain.agent_schedule.policies import SchedulePolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface

_ERROR_MESSAGE_MAX = 2000


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TriggerDueSchedulesUseCase:
    def __init__(
        self,
        session_factory,
        schedule_repo_builder: Callable[[AsyncSession], ScheduleRepositoryInterface],
        run_agent_uc_builder: Callable[[AsyncSession], object],
        sink: ScheduleRunSinkInterface,
        logger: LoggerInterface,
    ) -> None:
        self._session_factory = session_factory
        self._schedule_repo_builder = schedule_repo_builder
        self._run_agent_uc_builder = run_agent_uc_builder
        self._sink = sink
        self._logger = logger
        self._last_triggered_at: datetime | None = None
        self._last_result: TriggerResponse | None = None

    async def execute(self, request_id: str) -> TriggerResponse:
        now = _utc_now()
        claimed = await self._claim(now, request_id)
        success = 0
        for item in claimed:
            if await self._run_one(item, request_id):
                success += 1
        result = TriggerResponse(
            claimed=len(claimed),
            success=success,
            failed=len(claimed) - success,
            request_id=request_id,
        )
        self._last_triggered_at = now
        self._last_result = result
        self._logger.info(
            "TriggerDueSchedulesUseCase done",
            request_id=request_id,
            claimed=result.claimed,
            success=result.success,
            failed=result.failed,
        )
        return result

    def status(self) -> TriggerStatusResponse:
        """마지막 트리거 시각/결과 스냅샷 — 외부 cron 정지 감지용."""
        return TriggerStatusResponse(
            last_triggered_at=(
                self._last_triggered_at.isoformat()
                if self._last_triggered_at is not None
                else None
            ),
            last_result=self._last_result,
        )

    async def _claim(
        self, now: datetime, request_id: str
    ) -> list[ClaimedSchedule]:
        """[tx1] due 스케줄 선점 + next_run_at 재계산. 커밋 즉시 가시화."""
        async with self._session_factory() as session:
            async with session.begin():
                repo = self._schedule_repo_builder(session)
                return await repo.claim_due(now, request_id)

    async def _run_one(self, item: ClaimedSchedule, request_id: str) -> bool:
        schedule = item.schedule
        record_id = await self._sink.on_started(
            schedule, item.scheduled_for, request_id
        )
        try:
            response = await self._execute_agent(item, request_id)
            await self._sink.on_finished(
                record_id,
                "success",
                request_id,
                session_id=response.session_id,
                run_id=response.run_id,
            )
            succeeded = True
        except Exception as e:
            self._logger.error(
                "schedule run failed",
                exception=e,
                request_id=request_id,
                schedule_id=schedule.id,
            )
            await self._sink.on_finished(
                record_id,
                "failed",
                request_id,
                error_message=str(e)[:_ERROR_MESSAGE_MAX],
            )
            succeeded = False
        # last_run_at 은 성공/실패 무관 '마지막 실행 시도' 시각 (analysis A안)
        await self._touch_last_run(schedule.id, request_id)
        return succeeded

    async def _execute_agent(self, item: ClaimedSchedule, request_id: str):
        """[run tx] 회차별 독립 세션으로 에이전트 실행.

        R9: 지침을 시점 변수 치환 후 실제 사용자 질문(query)으로 전송 —
        RunAgentUseCase 가 새 세션 생성 + user 메시지 저장까지 수행한다.
        """
        schedule = item.schedule
        rendered = SchedulePolicy.render_instruction(
            schedule.instruction, schedule.timezone, _utc_now()
        )
        async with self._session_factory() as session:
            async with session.begin():
                run_uc = self._run_agent_uc_builder(session)
                return await run_uc.execute(
                    schedule.agent_id,
                    RunAgentRequest(query=rendered, user_id=schedule.user_id),
                    request_id,
                    viewer_user_id=schedule.user_id,
                )

    async def _touch_last_run(self, schedule_id: str, request_id: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                repo = self._schedule_repo_builder(session)
                await repo.touch_last_run(schedule_id, _utc_now(), request_id)
