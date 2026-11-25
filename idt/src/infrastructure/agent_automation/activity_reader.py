"""AgentActivityReader: 에이전트의 진행 중·대기 작업 존재 여부 (읽기 전용).

Design Ref: firewall-agent design §10.3. EXISTS 성격의 LIMIT 1 조회 세 개.
approval_request 는 (agent_id, status) 인덱스가 이미 있다.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.agent_automation.busy import (
    ACTIVE_JOB_STATUSES,
    OPEN_APPROVAL_STATUSES,
)
from src.domain.agent_automation.interfaces import AgentActivityReaderInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.agent_schedule.models import AgentScheduleRunModel
from src.infrastructure.approval.models import ApprovalRequestModel
from src.infrastructure.background_job.models import AgentBackgroundJobModel


class AgentActivityReader(AgentActivityReaderInterface):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def _exists(self, stmt) -> bool:
        result = await self._session.execute(stmt.limit(1))
        return result.first() is not None

    async def has_open_approval(self, agent_id: str, request_id: str) -> bool:
        return await self._exists(
            select(ApprovalRequestModel.id).where(
                ApprovalRequestModel.agent_id == agent_id,
                ApprovalRequestModel.status.in_(OPEN_APPROVAL_STATUSES),
            )
        )

    async def has_running_schedule_run(
        self, agent_id: str, started_after: datetime, request_id: str
    ) -> bool:
        return await self._exists(
            select(AgentScheduleRunModel.id).where(
                AgentScheduleRunModel.agent_id == agent_id,
                AgentScheduleRunModel.status == "running",
                AgentScheduleRunModel.started_at > started_after,
            )
        )

    async def has_active_job(self, agent_id: str, request_id: str) -> bool:
        return await self._exists(
            select(AgentBackgroundJobModel.id).where(
                AgentBackgroundJobModel.agent_id == agent_id,
                AgentBackgroundJobModel.status.in_(ACTIVE_JOB_STATUSES),
                AgentBackgroundJobModel.deleted_at.is_(None),
            )
        )
