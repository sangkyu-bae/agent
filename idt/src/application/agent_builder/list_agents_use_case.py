"""ListAgentsUseCase: 가시성 기반 에이전트 목록 조회."""
from src.application.agent_builder.schemas import (
    AgentSummary,
    ListAgentsRequest,
    ListAgentsResponse,
)
from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.agent_builder.policies import AccessCheckInput, VisibilityPolicy
from src.domain.agent_builder.schemas import AgentDefinition
from src.domain.department.interfaces import DepartmentRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class ListAgentsUseCase:
    def __init__(
        self,
        agent_repo: AgentDefinitionRepositoryInterface,
        dept_repo: DepartmentRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._agent_repo = agent_repo
        self._dept_repo = dept_repo
        self._logger = logger

    async def execute(
        self,
        viewer_user_id: str,
        viewer_role: str,
        request: ListAgentsRequest,
        request_id: str,
    ) -> ListAgentsResponse:
        self._logger.info(
            "ListAgentsUseCase start",
            request_id=request_id,
            scope=request.scope,
        )
        try:
            viewer_dept_ids = [
                ud.department_id
                for ud in await self._dept_repo.find_departments_by_user(
                    int(viewer_user_id), request_id
                )
            ]

            agents, total = await self._agent_repo.list_accessible(
                viewer_user_id=viewer_user_id,
                viewer_department_ids=viewer_dept_ids,
                scope=request.scope,
                search=request.search,
                page=request.page,
                size=request.size,
                request_id=request_id,
            )

            summaries = [
                self._to_summary(a, viewer_user_id, viewer_role)
                for a in agents
            ]

            self._logger.info(
                "ListAgentsUseCase done",
                request_id=request_id,
                total=total,
            )
            return ListAgentsResponse(
                agents=summaries,
                total=total,
                page=request.page,
                size=request.size,
            )
        except Exception as e:
            self._logger.error(
                "ListAgentsUseCase failed", exception=e, request_id=request_id
            )
            raise

    def _to_summary(
        self, agent: AgentDefinition, viewer_user_id: str, viewer_role: str
    ) -> AgentSummary:
        ctx = AccessCheckInput(
            agent_owner_id=agent.user_id,
            agent_visibility=agent.visibility,
            agent_department_id=agent.department_id,
            viewer_user_id=viewer_user_id,
            viewer_department_ids=[],
            viewer_role=viewer_role,
        )
        return AgentSummary(
            agent_id=agent.id,
            name=agent.name,
            description=agent.description,
            visibility=agent.visibility,
            department_name=None,
            owner_user_id=agent.user_id,
            owner_email=None,
            temperature=agent.temperature,
            can_edit=VisibilityPolicy.can_edit(ctx),
            can_delete=VisibilityPolicy.can_delete(ctx),
            created_at=agent.created_at.isoformat(),
        )
