"""UpdateMiddlewareAgentUseCase."""
from src.application.middleware_agent.schemas import (
    GetMiddlewareAgentResponse,
    MiddlewareConfigRequest,
    UpdateMiddlewareAgentRequest,
)
from src.domain.middleware_agent.interfaces import MiddlewareAgentRepositoryInterface
from src.domain.middleware_agent.policies import MiddlewareAgentPolicy
from src.domain.middleware_agent.schemas import MiddlewareConfig, MiddlewareType
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class UpdateMiddlewareAgentUseCase:

    def __init__(
        self,
        repository: MiddlewareAgentRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repository = repository
        self._logger = logger

    async def execute(
        self, agent_id: str, request: UpdateMiddlewareAgentRequest
    ) -> GetMiddlewareAgentResponse:
        self._logger.info(
            "UpdateMiddlewareAgentUseCase start",
            request_id=request.request_id,
            agent_id=agent_id,
        )
        try:
            agent = await self._repository.find_by_id(agent_id)
            if agent is None:
                raise ValueError(f"Agent not found: {agent_id}")

            if request.system_prompt is not None:
                MiddlewareAgentPolicy.validate_system_prompt(request.system_prompt)

            new_middleware = None
            if request.middleware is not None:
                new_middleware = [
                    MiddlewareConfig(
                        middleware_type=MiddlewareType(m.type),
                        config=m.config,
                        sort_order=m.sort_order,
                    )
                    for m in request.middleware
                ]
                MiddlewareAgentPolicy.validate_middleware_count(new_middleware)
                MiddlewareAgentPolicy.validate_middleware_combination(new_middleware)

            agent.apply_update(
                system_prompt=request.system_prompt,
                name=request.name,
                middleware_configs=new_middleware,
            )
            updated = await self._repository.update(agent)

            self._logger.info(
                "UpdateMiddlewareAgentUseCase done",
                request_id=request.request_id,
                agent_id=agent_id,
            )
            return GetMiddlewareAgentResponse(
                agent_id=updated.id,
                name=updated.name,
                description=updated.description,
                system_prompt=updated.system_prompt,
                model_name=updated.model_name,
                tool_ids=updated.tool_ids,
                middleware=[
                    MiddlewareConfigRequest(
                        type=mc.middleware_type.value,
                        config=mc.config,
                        sort_order=mc.sort_order,
                    )
                    for mc in updated.sorted_middleware()
                ],
                status=updated.status,
            )
        except Exception as e:
            self._logger.error(
                "UpdateMiddlewareAgentUseCase failed",
                exception=e,
                request_id=request.request_id,
                agent_id=agent_id,
            )
            raise
