"""AgentBusyChecker: 자동 실행 직전 바쁨 판정 (스케줄·알림 수신 공용).

Design Ref: firewall-agent design §2.2 / §10.3.
- 판정마다 자체 짧은 읽기 세션을 쓴다 — 호출자(스케줄 트리거)는 회차별로 세션을 나누므로
  여기서 트랜잭션을 공유할 대상이 없다 (DbScheduleRunSink 와 같은 session_factory 주입
  선례).
- 조회 예외는 바쁨(check_failed)으로 돌려준다 (fail-closed). 스택은 로그에 남긴다.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.agent_automation.busy import BusyVerdict, decide_busy
from src.domain.agent_automation.interfaces import AgentActivityReaderInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class AgentBusyChecker:
    def __init__(
        self,
        session_factory,
        reader_builder: Callable[[AsyncSession], AgentActivityReaderInterface],
        logger: LoggerInterface,
        stale_seconds: int,
        now_fn: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._session_factory = session_factory
        self._reader_builder = reader_builder
        self._logger = logger
        self._stale = timedelta(seconds=stale_seconds)
        self._now_fn = now_fn

    async def check(self, agent_id: str, request_id: str) -> BusyVerdict:
        try:
            async with self._session_factory() as session:
                reader = self._reader_builder(session)
                verdict = decide_busy(
                    open_approval=await reader.has_open_approval(agent_id, request_id),
                    running_run=await reader.has_running_schedule_run(
                        agent_id, self._now_fn() - self._stale, request_id
                    ),
                    active_job=await reader.has_active_job(agent_id, request_id),
                )
        except Exception as e:
            self._logger.error(
                "agent busy check failed — treating as busy",
                exception=e,
                request_id=request_id,
                agent_id=agent_id,
            )
            return BusyVerdict.check_failed()
        if verdict.busy:
            self._logger.info(
                "agent busy",
                request_id=request_id,
                agent_id=agent_id,
                reason=verdict.reason,
            )
        return verdict
