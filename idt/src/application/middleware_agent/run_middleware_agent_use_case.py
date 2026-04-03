"""RunMiddlewareAgentUseCase: create_agent + middleware 실행."""
try:
    from langchain.agents import create_agent
except ImportError:  # pragma: no cover
    create_agent = None  # type: ignore

from src.application.middleware_agent.middleware_builder import MiddlewareBuilder
from src.application.middleware_agent.schemas import (
    RunMiddlewareAgentRequest,
    RunMiddlewareAgentResponse,
)
from src.domain.middleware_agent.interfaces import MiddlewareAgentRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class RunMiddlewareAgentUseCase:

    def __init__(
        self,
        repository: MiddlewareAgentRepositoryInterface,
        tool_factory,
        middleware_builder: MiddlewareBuilder,
        logger: LoggerInterface,
    ) -> None:
        self._repository = repository
        self._tool_factory = tool_factory
        self._middleware_builder = middleware_builder
        self._logger = logger

    async def execute(
        self, agent_id: str, request: RunMiddlewareAgentRequest
    ) -> RunMiddlewareAgentResponse:
        self._logger.info(
            "RunMiddlewareAgentUseCase start",
            request_id=request.request_id,
            agent_id=agent_id,
        )
        try:
            agent_def = await self._repository.find_by_id(agent_id)
            if agent_def is None:
                raise ValueError(f"Agent not found: {agent_id}")

            tools = [
                await self._tool_factory.create_async(tool_id, request.request_id)
                for tool_id in agent_def.tool_ids
            ]
            middlewares = self._middleware_builder.build(
                agent_def.sorted_middleware(), request.request_id
            )

            agent = create_agent(
                model=agent_def.model_name,
                tools=tools,
                middleware=middlewares,
            )
            result = await agent.ainvoke(
                {"messages": [{"role": "user", "content": request.query}]}
            )

            answer, tools_used = self._parse_result(result)
            middleware_applied = [
                m.middleware_type.value for m in agent_def.sorted_middleware()
            ]

            self._logger.info(
                "RunMiddlewareAgentUseCase done",
                request_id=request.request_id,
                agent_id=agent_id,
            )
            return RunMiddlewareAgentResponse(
                answer=answer,
                tools_used=tools_used,
                middleware_applied=middleware_applied,
            )
        except Exception as e:
            self._logger.error(
                "RunMiddlewareAgentUseCase failed",
                exception=e,
                request_id=request.request_id,
                agent_id=agent_id,
            )
            raise

    @staticmethod
    def _parse_result(result: dict) -> tuple[str, list[str]]:
        messages = result.get("messages", [])
        answer = messages[-1].content if messages else ""
        tools_used = [m.name for m in messages if getattr(m, "name", None)]
        return answer, tools_used
