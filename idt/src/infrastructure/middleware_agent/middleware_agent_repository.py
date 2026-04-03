"""MiddlewareAgentRepository: MySQL CRUD (selectinload JOIN)."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.domain.middleware_agent.interfaces import MiddlewareAgentRepositoryInterface
from src.domain.middleware_agent.schemas import (
    MiddlewareAgentDefinition,
    MiddlewareConfig,
    MiddlewareType,
)
from src.infrastructure.middleware_agent.models import (
    MiddlewareAgentModel,
    MiddlewareAgentToolModel,
    MiddlewareConfigModel,
)


class MiddlewareAgentRepository(MiddlewareAgentRepositoryInterface):

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, agent: MiddlewareAgentDefinition) -> MiddlewareAgentDefinition:
        model = MiddlewareAgentModel(
            id=agent.id,
            user_id=agent.user_id,
            name=agent.name,
            description=agent.description,
            system_prompt=agent.system_prompt,
            model_name=agent.model_name,
            status=agent.status,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
            tools=[
                MiddlewareAgentToolModel(tool_id=tid, sort_order=i)
                for i, tid in enumerate(agent.tool_ids)
            ],
            middleware_configs=[
                MiddlewareConfigModel(
                    middleware_type=mc.middleware_type.value,
                    config_json=mc.config,
                    sort_order=mc.sort_order,
                )
                for mc in agent.middleware_configs
            ],
        )
        self._session.add(model)
        await self._session.flush()
        return agent

    async def find_by_id(self, agent_id: str) -> MiddlewareAgentDefinition | None:
        stmt = (
            select(MiddlewareAgentModel)
            .options(
                selectinload(MiddlewareAgentModel.tools),
                selectinload(MiddlewareAgentModel.middleware_configs),
            )
            .where(MiddlewareAgentModel.id == agent_id)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_domain(model)

    async def update(self, agent: MiddlewareAgentDefinition) -> MiddlewareAgentDefinition:
        model = await self._session.get(MiddlewareAgentModel, agent.id)
        if model is None:
            raise ValueError(f"Agent not found: {agent.id}")
        model.name = agent.name
        model.system_prompt = agent.system_prompt
        model.updated_at = datetime.utcnow()
        model.middleware_configs = [
            MiddlewareConfigModel(
                middleware_type=mc.middleware_type.value,
                config_json=mc.config,
                sort_order=mc.sort_order,
            )
            for mc in agent.middleware_configs
        ]
        await self._session.flush()
        return agent

    @staticmethod
    def _to_domain(model: MiddlewareAgentModel) -> MiddlewareAgentDefinition:
        return MiddlewareAgentDefinition(
            id=model.id,
            user_id=model.user_id,
            name=model.name,
            description=model.description or "",
            system_prompt=model.system_prompt,
            model_name=model.model_name,
            tool_ids=[t.tool_id for t in model.tools],
            middleware_configs=[
                MiddlewareConfig(
                    middleware_type=MiddlewareType(mc.middleware_type),
                    config=mc.config_json or {},
                    sort_order=mc.sort_order,
                )
                for mc in model.middleware_configs
            ],
            status=model.status,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
