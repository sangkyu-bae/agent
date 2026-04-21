"""DeleteAgentUseCase: 에이전트 소프트 삭제."""
from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.agent_builder.policies import AccessCheckInput, VisibilityPolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class DeleteAgentUseCase:
    def __init__(
        self,
        repository: AgentDefinitionRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repository = repository
        self._logger = logger

    async def execute(
        self,
        agent_id: str,
        viewer_user_id: str,
        viewer_role: str,
        request_id: str,
    ) -> None:
        self._logger.info(
            "DeleteAgentUseCase start",
            request_id=request_id,
            agent_id=agent_id,
        )
        try:
            agent = await self._repository.find_by_id(agent_id, request_id)
            if agent is None:
                raise ValueError(f"에이전트를 찾을 수 없습니다: {agent_id}")

            ctx = AccessCheckInput(
                agent_owner_id=agent.user_id,
                agent_visibility=agent.visibility,
                agent_department_id=agent.department_id,
                viewer_user_id=viewer_user_id,
                viewer_department_ids=[],
                viewer_role=viewer_role,
            )
            if not VisibilityPolicy.can_delete(ctx):
                raise PermissionError("삭제 권한이 없습니다")

            await self._repository.soft_delete(agent_id, request_id)
            self._logger.info(
                "DeleteAgentUseCase done",
                request_id=request_id,
                agent_id=agent_id,
            )
        except Exception as e:
            self._logger.error(
                "DeleteAgentUseCase failed", exception=e, request_id=request_id
            )
            raise
