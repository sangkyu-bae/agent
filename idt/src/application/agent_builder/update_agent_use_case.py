"""UpdateAgentUseCase: 시스템 프롬프트 / 이름 수정."""
from src.application.agent_builder.schemas import UpdateAgentRequest, UpdateAgentResponse
from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.agent_builder.policies import UpdateAgentPolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class UpdateAgentUseCase:
    def __init__(
        self,
        repository: AgentDefinitionRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repository = repository
        self._logger = logger

    async def execute(
        self, agent_id: str, request: UpdateAgentRequest, request_id: str
    ) -> UpdateAgentResponse:
        self._logger.info(
            "UpdateAgentUseCase start", request_id=request_id, agent_id=agent_id
        )
        try:
            agent = await self._repository.find_by_id(agent_id, request_id)
            if agent is None:
                raise ValueError(f"에이전트를 찾을 수 없습니다: {agent_id}")

            UpdateAgentPolicy.validate_update(
                status=agent.status, system_prompt=request.system_prompt
            )
            agent.apply_update(
                system_prompt=request.system_prompt, name=request.name
            )
            updated = await self._repository.update(agent, request_id)

            self._logger.info(
                "UpdateAgentUseCase done", request_id=request_id, agent_id=agent_id
            )
            return UpdateAgentResponse(
                agent_id=updated.id,
                name=updated.name,
                system_prompt=updated.system_prompt,
                updated_at=updated.updated_at.isoformat(),
            )
        except Exception as e:
            self._logger.error(
                "UpdateAgentUseCase failed", exception=e, request_id=request_id
            )
            raise
