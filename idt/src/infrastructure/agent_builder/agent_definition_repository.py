"""AgentDefinitionRepository: agent_definition + agent_tool MySQL CRUD."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.agent_builder.models import AgentDefinitionModel, AgentToolModel


class AgentDefinitionRepository(AgentDefinitionRepositoryInterface):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def save(self, agent: AgentDefinition, request_id: str) -> AgentDefinition:
        self._logger.info(
            "AgentDefinition save start", request_id=request_id, agent_id=agent.id
        )
        try:
            model = AgentDefinitionModel(
                id=agent.id,
                user_id=agent.user_id,
                name=agent.name,
                description=agent.description,
                system_prompt=agent.system_prompt,
                flow_hint=agent.flow_hint,
                llm_model_id=agent.llm_model_id,
                status=agent.status,
                visibility=agent.visibility,
                department_id=agent.department_id,
                temperature=agent.temperature,
                created_at=agent.created_at,
                updated_at=agent.updated_at,
                tools=[
                    AgentToolModel(
                        id=str(uuid.uuid4()),
                        agent_id=agent.id,
                        tool_id=w.tool_id,
                        worker_id=w.worker_id,
                        description=w.description,
                        sort_order=w.sort_order,
                        tool_config=w.tool_config,
                    )
                    for w in agent.workers
                ],
            )
            self._session.add(model)
            await self._session.flush()
            self._logger.info(
                "AgentDefinition save done", request_id=request_id, agent_id=agent.id
            )
            return agent
        except Exception as e:
            self._logger.error(
                "AgentDefinition save failed", exception=e, request_id=request_id
            )
            raise

    async def find_by_id(
        self, agent_id: str, request_id: str
    ) -> AgentDefinition | None:
        self._logger.info(
            "AgentDefinition find_by_id", request_id=request_id, agent_id=agent_id
        )
        try:
            stmt = (
                select(AgentDefinitionModel)
                .options(selectinload(AgentDefinitionModel.tools))
                .where(AgentDefinitionModel.id == agent_id)
            )
            result = await self._session.execute(stmt)
            model = result.scalar_one_or_none()
            if model is None:
                return None
            return self._to_domain(model)
        except Exception as e:
            self._logger.error(
                "AgentDefinition find_by_id failed", exception=e, request_id=request_id
            )
            raise

    async def update(self, agent: AgentDefinition, request_id: str) -> AgentDefinition:
        self._logger.info(
            "AgentDefinition update", request_id=request_id, agent_id=agent.id
        )
        try:
            stmt = select(AgentDefinitionModel).where(
                AgentDefinitionModel.id == agent.id
            )
            result = await self._session.execute(stmt)
            model = result.scalar_one()
            model.system_prompt = agent.system_prompt
            model.name = agent.name
            model.visibility = agent.visibility
            model.department_id = agent.department_id
            model.temperature = agent.temperature
            model.updated_at = datetime.now(timezone.utc)
            await self._session.flush()
            self._logger.info(
                "AgentDefinition update done", request_id=request_id, agent_id=agent.id
            )
            return agent
        except Exception as e:
            self._logger.error(
                "AgentDefinition update failed", exception=e, request_id=request_id
            )
            raise

    async def list_by_user(
        self, user_id: str, request_id: str
    ) -> list[AgentDefinition]:
        self._logger.info(
            "AgentDefinition list_by_user", request_id=request_id, user_id=user_id
        )
        try:
            stmt = (
                select(AgentDefinitionModel)
                .options(selectinload(AgentDefinitionModel.tools))
                .where(AgentDefinitionModel.user_id == user_id)
                .order_by(AgentDefinitionModel.created_at.desc())
            )
            result = await self._session.execute(stmt)
            return [self._to_domain(m) for m in result.scalars().all()]
        except Exception as e:
            self._logger.error(
                "AgentDefinition list_by_user failed", exception=e, request_id=request_id
            )
            raise

    async def list_accessible(
        self,
        viewer_user_id: str,
        viewer_department_ids: list[str],
        scope: str,
        search: str | None,
        page: int,
        size: int,
        request_id: str,
    ) -> tuple[list[AgentDefinition], int]:
        self._logger.info(
            "AgentDefinition list_accessible",
            request_id=request_id,
            scope=scope,
        )
        try:
            base = select(AgentDefinitionModel).where(
                AgentDefinitionModel.status != "deleted"
            )

            if scope == "mine":
                base = base.where(AgentDefinitionModel.user_id == viewer_user_id)
            elif scope == "department":
                base = base.where(
                    AgentDefinitionModel.visibility == "department",
                    AgentDefinitionModel.department_id.in_(viewer_department_ids),
                )
            elif scope == "public":
                base = base.where(AgentDefinitionModel.visibility == "public")
            else:
                base = base.where(
                    or_(
                        AgentDefinitionModel.user_id == viewer_user_id,
                        AgentDefinitionModel.visibility == "public",
                        and_(
                            AgentDefinitionModel.visibility == "department",
                            AgentDefinitionModel.department_id.in_(
                                viewer_department_ids if viewer_department_ids else [""]
                            ),
                        ),
                    )
                )

            if search:
                like_pattern = f"%{search}%"
                base = base.where(
                    or_(
                        AgentDefinitionModel.name.ilike(like_pattern),
                        AgentDefinitionModel.description.ilike(like_pattern),
                    )
                )

            count_stmt = select(func.count()).select_from(base.subquery())
            total = (await self._session.execute(count_stmt)).scalar_one()

            offset = (page - 1) * size
            data_stmt = (
                base.options(selectinload(AgentDefinitionModel.tools))
                .order_by(AgentDefinitionModel.created_at.desc())
                .offset(offset)
                .limit(size)
            )
            result = await self._session.execute(data_stmt)
            agents = [self._to_domain(m) for m in result.scalars().all()]

            return agents, total
        except Exception as e:
            self._logger.error(
                "AgentDefinition list_accessible failed",
                exception=e, request_id=request_id,
            )
            raise

    async def soft_delete(self, agent_id: str, request_id: str) -> None:
        self._logger.info(
            "AgentDefinition soft_delete", request_id=request_id, agent_id=agent_id
        )
        try:
            stmt = (
                update(AgentDefinitionModel)
                .where(AgentDefinitionModel.id == agent_id)
                .values(status="deleted", updated_at=datetime.now(timezone.utc))
            )
            await self._session.execute(stmt)
            await self._session.flush()
        except Exception as e:
            self._logger.error(
                "AgentDefinition soft_delete failed",
                exception=e, request_id=request_id,
            )
            raise

    def _to_domain(self, model: AgentDefinitionModel) -> AgentDefinition:
        return AgentDefinition(
            id=model.id,
            user_id=model.user_id,
            name=model.name,
            description=model.description or "",
            system_prompt=model.system_prompt,
            flow_hint=model.flow_hint or "",
            workers=[
                WorkerDefinition(
                    tool_id=t.tool_id,
                    worker_id=t.worker_id,
                    description=t.description or "",
                    sort_order=t.sort_order,
                    tool_config=t.tool_config,
                )
                for t in sorted(model.tools, key=lambda x: x.sort_order)
            ],
            llm_model_id=model.llm_model_id,
            status=model.status,
            visibility=model.visibility,
            department_id=model.department_id,
            temperature=model.temperature,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
