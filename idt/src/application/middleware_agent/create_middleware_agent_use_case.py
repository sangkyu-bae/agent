"""CreateMiddlewareAgentUseCase."""
import uuid
from datetime import datetime

from src.application.middleware_agent.schemas import (
    CreateMiddlewareAgentRequest,
    CreateMiddlewareAgentResponse,
)
from src.domain.middleware_agent.interfaces import MiddlewareAgentRepositoryInterface
from src.domain.middleware_agent.policies import MiddlewareAgentPolicy
from src.domain.middleware_agent.schemas import (
    MiddlewareAgentDefinition,
    MiddlewareConfig,
    MiddlewareType,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class CreateMiddlewareAgentUseCase:

    def __init__(
        self,
        repository: MiddlewareAgentRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repository = repository
        self._logger = logger

    async def execute(
        self, request: CreateMiddlewareAgentRequest
    ) -> CreateMiddlewareAgentResponse:
        self._logger.info(
            "CreateMiddlewareAgentUseCase start",
            request_id=request.request_id,
            user_id=request.user_id,
        )
        try:
            MiddlewareAgentPolicy.validate_tool_count(request.tool_ids)
            MiddlewareAgentPolicy.validate_system_prompt(request.system_prompt)

            middleware_configs = [
                MiddlewareConfig(
                    middleware_type=MiddlewareType(m.type),
                    config=m.config,
                    sort_order=m.sort_order,
                )
                for m in request.middleware
            ]
            MiddlewareAgentPolicy.validate_middleware_count(middleware_configs)
            MiddlewareAgentPolicy.validate_middleware_combination(middleware_configs)

            now = datetime.utcnow()
            agent_def = MiddlewareAgentDefinition(
                id=str(uuid.uuid4()),
                user_id=request.user_id,
                name=request.name,
                description=request.description,
                system_prompt=request.system_prompt,
                model_name=request.model_name,
                tool_ids=request.tool_ids,
                middleware_configs=middleware_configs,
                status="active",
                created_at=now,
                updated_at=now,
            )
            saved = await self._repository.save(agent_def)

            self._logger.info(
                "CreateMiddlewareAgentUseCase done",
                request_id=request.request_id,
                agent_id=saved.id,
            )
            return CreateMiddlewareAgentResponse(
                agent_id=saved.id,
                name=saved.name,
                middleware_count=len(saved.middleware_configs),
                status=saved.status,
            )
        except Exception as e:
            self._logger.error(
                "CreateMiddlewareAgentUseCase failed",
                exception=e,
                request_id=request.request_id,
            )
            raise
