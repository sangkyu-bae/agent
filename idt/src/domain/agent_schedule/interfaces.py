"""agent-schedule 도메인 인터페이스 (Repository / RunSink 포트)."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from src.domain.agent_schedule.entity import AgentSchedule, RunStatus, ScheduleRun


@dataclass(frozen=True)
class ClaimedSchedule:
    """claim_due 결과: 스케줄 + 원래 예정 시각(재계산 전 next_run_at)."""

    schedule: AgentSchedule
    scheduled_for: datetime


class ScheduleRepositoryInterface(ABC):
    @abstractmethod
    async def save(self, schedule: AgentSchedule, request_id: str) -> None: ...

    @abstractmethod
    async def find_by_id(
        self, schedule_id: str, request_id: str
    ) -> AgentSchedule | None: ...

    @abstractmethod
    async def list_by_agent(
        self, agent_id: str, request_id: str
    ) -> list[AgentSchedule]: ...

    @abstractmethod
    async def count_by_agent(self, agent_id: str, request_id: str) -> int: ...

    @abstractmethod
    async def update(self, schedule: AgentSchedule, request_id: str) -> None: ...

    @abstractmethod
    async def delete(self, schedule_id: str, request_id: str) -> None: ...

    @abstractmethod
    async def claim_due(
        self, now_utc: datetime, request_id: str
    ) -> list[ClaimedSchedule]:
        """due 스케줄 선점: next_run_at 재계산 UPDATE 까지 수행 (트랜잭션은 호출측)."""
        ...

    @abstractmethod
    async def touch_last_run(
        self, schedule_id: str, ran_at: datetime, request_id: str
    ) -> None: ...


class ScheduleRunRepositoryInterface(ABC):
    @abstractmethod
    async def save(self, run: ScheduleRun, request_id: str) -> None: ...

    @abstractmethod
    async def update(self, run: ScheduleRun, request_id: str) -> None: ...

    @abstractmethod
    async def find_by_id(
        self, run_record_id: str, request_id: str
    ) -> ScheduleRun | None: ...

    @abstractmethod
    async def list_by_schedule(
        self, schedule_id: str, limit: int, offset: int, request_id: str
    ) -> list[ScheduleRun]: ...


class ScheduleRunSinkInterface(ABC):
    """실행 결과 처리 포트 (R6): 기본 구현은 이력 테이블 기록.

    추후 알림/웹훅 등 sink 를 additive 로 추가할 수 있는 seam.
    """

    @abstractmethod
    async def on_started(
        self, schedule: AgentSchedule, scheduled_for: datetime, request_id: str
    ) -> str:
        """실행 시작 기록. run_record_id 반환."""
        ...

    @abstractmethod
    async def on_finished(
        self,
        run_record_id: str,
        status: RunStatus,
        request_id: str,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
        error_message: str | None = None,
    ) -> None: ...
