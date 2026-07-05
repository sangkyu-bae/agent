"""AgentSkillRepository: MySQLBaseRepository 기반 agent_skill 저장소.

list_attached_skills는 agent_skill ⨝ skill_definition 조인으로 주입 본문(instruction)까지
한 쿼리로 확보한다. skill_builder 매퍼(_to_entity)를 재사용한다.
commit/rollback 호출 금지 — 세션 미들웨어가 트랜잭션을 관리한다.
"""
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.agent_skill.interfaces import AgentSkillRepositoryInterface
from src.domain.agent_skill.schemas import AgentSkillLink
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.skill_builder.schemas import SkillDefinition
from src.infrastructure.persistence.models.agent_skill.models import AgentSkillModel
from src.infrastructure.persistence.models.skill_builder.models import (
    SkillDefinitionModel,
)
from src.infrastructure.persistence.mysql_base_repository import MySQLBaseRepository
from src.infrastructure.skill_builder.skill_repository import (
    _to_entity as _skill_to_entity,
)


def _to_link(model: AgentSkillModel) -> AgentSkillLink:
    return AgentSkillLink(
        agent_id=model.agent_id,
        skill_id=model.skill_id,
        sort_order=model.sort_order,
        created_at=model.created_at,
    )


class AgentSkillRepository(
    MySQLBaseRepository[AgentSkillModel],
    AgentSkillRepositoryInterface,
):
    def __init__(self, session: AsyncSession, logger: LoggerInterface):
        super().__init__(session, AgentSkillModel, logger)

    async def _base_save(
        self, model: AgentSkillModel, request_id: str
    ) -> AgentSkillModel:
        return await MySQLBaseRepository.save(self, model, request_id)

    async def attach(
        self, link: AgentSkillLink, request_id: str
    ) -> AgentSkillLink:
        model = AgentSkillModel(
            id=str(uuid.uuid4()),
            agent_id=link.agent_id,
            skill_id=link.skill_id,
            sort_order=link.sort_order,
            created_at=link.created_at,
        )
        saved = await self._base_save(model, request_id)
        return _to_link(saved)

    async def detach(
        self, agent_id: str, skill_id: str, request_id: str
    ) -> None:
        stmt = delete(AgentSkillModel).where(
            AgentSkillModel.agent_id == agent_id,
            AgentSkillModel.skill_id == skill_id,
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def list_links(
        self, agent_id: str, request_id: str
    ) -> list[AgentSkillLink]:
        stmt = (
            select(AgentSkillModel)
            .where(AgentSkillModel.agent_id == agent_id)
            .order_by(AgentSkillModel.sort_order)
        )
        result = await self._session.execute(stmt)
        return [_to_link(m) for m in result.scalars().all()]

    async def list_attached_skills(
        self, agent_id: str, request_id: str
    ) -> list[SkillDefinition]:
        stmt = (
            select(SkillDefinitionModel)
            .join(
                AgentSkillModel,
                AgentSkillModel.skill_id == SkillDefinitionModel.id,
            )
            .where(
                AgentSkillModel.agent_id == agent_id,
                SkillDefinitionModel.status == "active",
            )
            .order_by(AgentSkillModel.sort_order)
        )
        result = await self._session.execute(stmt)
        return [_skill_to_entity(m) for m in result.scalars().all()]
