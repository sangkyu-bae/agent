"""RunAgentUseCase: DB에서 워크플로우 로드 → LangGraph 동적 컴파일 → 실행."""
from src.application.agent_builder.schemas import RunAgentRequest, RunAgentResponse
from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class RunAgentUseCase:
    def __init__(
        self,
        repository: AgentDefinitionRepositoryInterface,
        compiler: WorkflowCompiler,
        openai_api_key: str,
        logger: LoggerInterface,
    ) -> None:
        self._repository = repository
        self._compiler = compiler
        self._api_key = openai_api_key
        self._logger = logger

    async def execute(
        self, agent_id: str, request: RunAgentRequest, request_id: str
    ) -> RunAgentResponse:
        self._logger.info(
            "RunAgentUseCase start", request_id=request_id, agent_id=agent_id
        )
        try:
            agent = await self._repository.find_by_id(agent_id, request_id)
            if agent is None:
                raise ValueError(f"에이전트를 찾을 수 없습니다: {agent_id}")

            workflow = agent.to_workflow_definition()
            graph = self._compiler.compile(
                workflow=workflow,
                model_name=agent.model_name,
                api_key=self._api_key,
                request_id=request_id,
            )

            result = await graph.ainvoke({"messages": [
                {"role": "user", "content": request.query}
            ]})

            answer, tools_used = self._parse_result(result)

            self._logger.info(
                "RunAgentUseCase done", request_id=request_id, agent_id=agent_id
            )
            return RunAgentResponse(
                agent_id=agent_id,
                query=request.query,
                answer=answer,
                tools_used=tools_used,
                request_id=request_id,
            )
        except Exception as e:
            self._logger.error(
                "RunAgentUseCase failed", exception=e, request_id=request_id
            )
            raise

    def _parse_result(self, result: dict) -> tuple[str, list[str]]:
        messages = result.get("messages", [])
        answer = ""
        if messages:
            last = messages[-1]
            answer = last.content if hasattr(last, "content") else str(last)

        tools_used = list({
            getattr(m, "name", None)
            for m in messages
            if getattr(m, "name", None)
        })
        return answer, tools_used
