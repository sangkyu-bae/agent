"""AgentDefinitionRepository: agent_definition + agent_tool MySQL CRUD."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.agent_builder.models import AgentDefinitionModel, AgentToolModel
from src.infrastructure.middleware.models import AgentMiddlewareModel
from src.infrastructure.agent_builder.subscription_model import UserAgentSubscriptionModel


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
                max_iterations=agent.max_iterations,
                include_user_context=agent.include_user_context,
                forked_from=agent.forked_from,
                forked_at=agent.forked_at,
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
                        worker_type=w.worker_type,
                        ref_agent_id=w.ref_agent_id,
                        category=w.category,
                    )
                    for w in agent.workers
                ],
            )
            self._session.add(model)
            # builtin-middleware D5: 미들웨어 스냅샷 동승 (동일 세션·단일 flush —
            # FK 삽입 순서는 SQLAlchemy 의존성 정렬이 보장)
            self._insert_middleware_rows(agent.id, agent.middleware_types or [])
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
            stmt = (
                select(AgentDefinitionModel)
                .options(selectinload(AgentDefinitionModel.tools))
                .where(AgentDefinitionModel.id == agent.id)
            )
            result = await self._session.execute(stmt)
            model = result.scalar_one()
            model.system_prompt = agent.system_prompt
            model.name = agent.name
            model.visibility = agent.visibility
            model.department_id = agent.department_id
            model.temperature = agent.temperature
            model.max_iterations = agent.max_iterations
            # agent-builder-edit-mapping FR-5: 미반영 시 모델 변경이 조용히 무효
            model.llm_model_id = agent.llm_model_id
            # agent-update-tool-editing: 도구 재구성 시 flow_hint 도 바뀐다 —
            # 미반영 시 supervisor 프롬프트가 옛 도구 체인을 계속 가리킨다.
            model.flow_hint = agent.flow_hint
            model.updated_at = datetime.now(timezone.utc)
            await self._sync_workers(model, agent.workers)
            # builtin-middleware D5: None = 미변경 (미로드 상태에서 스냅샷 소실 방지)
            if agent.middleware_types is not None:
                await self._sync_middleware(agent.id, agent.middleware_types)
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

    async def _sync_workers(
        self, model: AgentDefinitionModel, workers: list[WorkerDefinition]
    ) -> None:
        """모델의 워커 row를 도메인 workers와 일치하도록 재구성한다.

        서브에이전트 변경(수정 경로)을 반영하기 위해 기존 row를 비우고 다시 생성한다.
        delete-orphan + 중간 flush로 uq_agent_worker 제약 충돌을 피한다.
        """
        model.tools.clear()
        await self._session.flush()
        for w in workers:
            model.tools.append(
                AgentToolModel(
                    id=str(uuid.uuid4()),
                    agent_id=model.id,
                    tool_id=w.tool_id,
                    worker_id=w.worker_id,
                    description=w.description,
                    sort_order=w.sort_order,
                    tool_config=w.tool_config,
                    worker_type=w.worker_type,
                    ref_agent_id=w.ref_agent_id,
                    category=w.category,
                )
            )

    def _insert_middleware_rows(
        self, agent_id: str, middleware_types: list[str]
    ) -> None:
        """스냅샷 행 생성 — 순서는 전달 리스트 순서(카탈로그 sort_order 반영)."""
        for i, mw_type in enumerate(middleware_types):
            self._session.add(
                AgentMiddlewareModel(
                    id=str(uuid.uuid4()),
                    agent_id=agent_id,
                    middleware_type=mw_type,
                    config=None,
                    sort_order=i,
                    created_at=datetime.now(timezone.utc),
                )
            )

    async def _sync_middleware(
        self, agent_id: str, middleware_types: list[str]
    ) -> None:
        """builtin-middleware D5: 전체 교체 (delete 후 재삽입 — _sync_workers 대칭)."""
        await self._session.execute(
            delete(AgentMiddlewareModel).where(
                AgentMiddlewareModel.agent_id == agent_id
            )
        )
        await self._session.flush()
        self._insert_middleware_rows(agent_id, middleware_types)

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

    async def find_by_id_with_status(
        self, agent_id: str, request_id: str
    ) -> AgentDefinition | None:
        """삭제된 에이전트 포함 조회."""
        self._logger.info(
            "AgentDefinition find_by_id_with_status",
            request_id=request_id,
            agent_id=agent_id,
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
                "AgentDefinition find_by_id_with_status failed",
                exception=e,
                request_id=request_id,
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

    async def count_forks(self, source_agent_id: str, request_id: str) -> int:
        self._logger.info(
            "AgentDefinition count_forks",
            request_id=request_id,
            agent_id=source_agent_id,
        )
        try:
            stmt = select(func.count()).where(
                AgentDefinitionModel.forked_from == source_agent_id,
                AgentDefinitionModel.status != "deleted",
            )
            return (await self._session.execute(stmt)).scalar_one()
        except Exception as e:
            self._logger.error(
                "AgentDefinition count_forks failed",
                exception=e,
                request_id=request_id,
            )
            raise

    async def count_subscribers(self, agent_id: str, request_id: str) -> int:
        self._logger.info(
            "AgentDefinition count_subscribers",
            request_id=request_id,
            agent_id=agent_id,
        )
        try:
            stmt = select(func.count()).where(
                UserAgentSubscriptionModel.agent_id == agent_id
            )
            return (await self._session.execute(stmt)).scalar_one()
        except Exception as e:
            self._logger.error(
                "AgentDefinition count_subscribers failed",
                exception=e,
                request_id=request_id,
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
                    worker_type=t.worker_type,
                    ref_agent_id=t.ref_agent_id,
                    category=t.category,
                )
                for t in sorted(model.tools, key=lambda x: x.sort_order)
            ],
            llm_model_id=model.llm_model_id,
            status=model.status,
            visibility=model.visibility,
            department_id=model.department_id,
            temperature=model.temperature,
            max_iterations=model.max_iterations,
            include_user_context=model.include_user_context,
            forked_from=model.forked_from,
            forked_at=model.forked_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
