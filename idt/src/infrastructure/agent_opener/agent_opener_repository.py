"""AgentOpenerRepository: MySQLBaseRepository 기반 agent_opener 저장소.

Design Ref: agent-opener §3.4 — replace 는 DELETE→INSERT 전체 교체,
list_by_agent_ids 는 IN 쿼리 1회(목록 API N+1 방지).
commit/rollback 호출 금지 — 세션 미들웨어가 트랜잭션을 관리한다.
"""
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.agent_opener.interfaces import AgentOpenerRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.persistence.models.agent_opener.models import (
    AgentOpenerModel,
)
from src.infrastructure.persistence.mysql_base_repository import MySQLBaseRepository


class AgentOpenerRepository(
    MySQLBaseRepository[AgentOpenerModel],
    AgentOpenerRepositoryInterface,
):
    def __init__(self, session: AsyncSession, logger: LoggerInterface):
        super().__init__(session, AgentOpenerModel, logger)

    async def list_by_agent_id(
        self, agent_id: str, request_id: str
    ) -> list[str]:
        stmt = (
            select(AgentOpenerModel.text)
            .where(AgentOpenerModel.agent_id == agent_id)
            .order_by(AgentOpenerModel.sort_order, AgentOpenerModel.id)
        )
        result = await self._session.execute(stmt)
        return [row[0] for row in result.all()]

    async def list_by_agent_ids(
        self, agent_ids: list[str], request_id: str
    ) -> dict[str, list[str]]:
        if not agent_ids:
            return {}
        stmt = (
            select(AgentOpenerModel.agent_id, AgentOpenerModel.text)
            .where(AgentOpenerModel.agent_id.in_(agent_ids))
            .order_by(AgentOpenerModel.sort_order, AgentOpenerModel.id)
        )
        result = await self._session.execute(stmt)
        grouped: dict[str, list[str]] = defaultdict(list)
        for agent_id, text in result.all():
            grouped[agent_id].append(text)
        return dict(grouped)

    async def replace(
        self, agent_id: str, texts: list[str], request_id: str
    ) -> list[str]:
        self._logger.info(
            "AgentOpener replace",
            request_id=request_id, agent_id=agent_id, count=len(texts),
        )
        await self._session.execute(
            delete(AgentOpenerModel).where(AgentOpenerModel.agent_id == agent_id)
        )
        now = datetime.now(timezone.utc)
        for order, text in enumerate(texts):
            self._session.add(
                AgentOpenerModel(
                    id=str(uuid.uuid4()),
                    agent_id=agent_id,
                    text=text,
                    sort_order=order,
                    created_at=now,
                )
            )
        await self._session.flush()
        return list(texts)
