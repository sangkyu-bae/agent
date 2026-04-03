"""GetMiddlewareAgentUseCase."""
from src.application.middleware_agent.schemas import (
    GetMiddlewareAgentResponse,
    MiddlewareConfigRequest,
)
from src.domain.middleware_agent.interfaces import MiddlewareAgentRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class GetMiddlewareAgentUseCase:

    def __init__(
        self,
        repository: MiddlewareAgentRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repository = repository
        self._logger = logger

    async def execute(self, agent_id: str, request_id: str) -> GetMiddlewareAgentResponse:
        self._logger.info(
            "GetMiddlewareAgentUseCase start",
            request_id=request_id,
            agent_id=agent_id,
        )
        try:
            agent = await self._repository.find_by_id(agent_id)
            if agent is None:
                raise ValueError(f"Agent not found: {agent_id}")

            self._logger.info(
                "GetMiddlewareAgentUseCase done",
                request_id=request_id,
                agent_id=agent_id,
            )
            return GetMiddlewareAgentResponse(
                agent_id=agent.id,
                name=agent.name,
                description=agent.description,
                system_prompt=agent.system_prompt,
                model_name=agent.model_name,
                tool_ids=agent.tool_ids,
                middleware=[
                    MiddlewareConfigRequest(
                        type=mc.middleware_type.value,
                        config=mc.config,
                        sort_order=mc.sort_order,
                    )
                    for mc in agent.sorted_middleware()
                ],
                status=agent.status,
            )
        except Exception as e:
            self._logger.error(
                "GetMiddlewareAgentUseCase failed",
                exception=e,
                request_id=request_id,
                agent_id=agent_id,
            )
            raise
