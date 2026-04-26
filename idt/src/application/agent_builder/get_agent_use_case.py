"""GetAgentUseCase: 에이전트 정의 조회."""
from src.application.agent_builder.schemas import GetAgentResponse, WorkerInfo
from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.agent_builder.policies import AccessCheckInput, VisibilityPolicy
from src.domain.department.interfaces import DepartmentRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class GetAgentUseCase:
    def __init__(
        self,
        repository: AgentDefinitionRepositoryInterface,
        dept_repository: DepartmentRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repository = repository
        self._dept_repository = dept_repository
        self._logger = logger

    async def execute(
        self,
        agent_id: str,
        request_id: str,
        viewer_user_id: str | None = None,
        viewer_role: str = "user",
    ) -> GetAgentResponse | None:
        self._logger.info(
            "GetAgentUseCase start", request_id=request_id, agent_id=agent_id
        )
        try:
            agent = await self._repository.find_by_id(agent_id, request_id)
            if agent is None:
                return None

            can_edit = False
            can_delete = False
            if viewer_user_id is not None:
                ctx = AccessCheckInput(
                    agent_owner_id=agent.user_id,
                    agent_visibility=agent.visibility,
                    agent_department_id=agent.department_id,
                    viewer_user_id=viewer_user_id,
                    viewer_department_ids=[],
                    viewer_role=viewer_role,
                )
                can_edit = VisibilityPolicy.can_edit(ctx)
                can_delete = VisibilityPolicy.can_delete(ctx)

            department_name: str | None = None
            if agent.department_id is not None:
                dept = await self._dept_repository.find_by_id(
                    agent.department_id, request_id
                )
                if dept is not None:
                    department_name = dept.name

            return GetAgentResponse(
                agent_id=agent.id,
                name=agent.name,
                description=agent.description,
                system_prompt=agent.system_prompt,
                tool_ids=[w.tool_id for w in agent.workers],
                workers=[
                    WorkerInfo(
                        tool_id=w.tool_id,
                        worker_id=w.worker_id,
                        description=w.description,
                        sort_order=w.sort_order,
                        tool_config=w.tool_config,
                    )
                    for w in agent.workers
                ],
                flow_hint=agent.flow_hint,
                llm_model_id=agent.llm_model_id,
                status=agent.status,
                visibility=agent.visibility,
                department_id=agent.department_id,
                department_name=department_name,
                temperature=agent.temperature,
                owner_user_id=agent.user_id,
                can_edit=can_edit,
                can_delete=can_delete,
                created_at=agent.created_at.isoformat(),
                updated_at=agent.updated_at.isoformat(),
            )
        except Exception as e:
            self._logger.error(
                "GetAgentUseCase failed", exception=e, request_id=request_id
            )
            raise
