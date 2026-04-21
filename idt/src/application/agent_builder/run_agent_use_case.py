"""RunAgentUseCase: DB에서 워크플로우 로드 → LangGraph 동적 컴파일 → 실행."""
from src.application.agent_builder.schemas import RunAgentRequest, RunAgentResponse
from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.agent_builder.policies import AccessCheckInput, VisibilityPolicy
from src.domain.llm_model.interfaces import LlmModelRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class RunAgentUseCase:
    def __init__(
        self,
        repository: AgentDefinitionRepositoryInterface,
        llm_model_repository: LlmModelRepositoryInterface,
        compiler: WorkflowCompiler,
        logger: LoggerInterface,
    ) -> None:
        self._repository = repository
        self._llm_model_repository = llm_model_repository
        self._compiler = compiler
        self._logger = logger

    async def execute(
        self,
        agent_id: str,
        request: RunAgentRequest,
        request_id: str,
        viewer_user_id: str | None = None,
        viewer_department_ids: list[str] | None = None,
    ) -> RunAgentResponse:
        self._logger.info(
            "RunAgentUseCase start", request_id=request_id, agent_id=agent_id
        )
        try:
            agent = await self._repository.find_by_id(agent_id, request_id)
            if agent is None:
                raise ValueError(f"에이전트를 찾을 수 없습니다: {agent_id}")

            if viewer_user_id is not None:
                ctx = AccessCheckInput(
                    agent_owner_id=agent.user_id,
                    agent_visibility=agent.visibility,
                    agent_department_id=agent.department_id,
                    viewer_user_id=viewer_user_id,
                    viewer_department_ids=viewer_department_ids or [],
                    viewer_role="user",
                )
                if not VisibilityPolicy.can_access(ctx):
                    raise PermissionError("이 에이전트에 대한 실행 권한이 없습니다")

            llm_model = await self._llm_model_repository.find_by_id(
                agent.llm_model_id, request_id
            )
            if llm_model is None:
                raise ValueError(
                    f"에이전트에 연결된 LLM 모델을 찾을 수 없습니다: {agent.llm_model_id}"
                )

            workflow = agent.to_workflow_definition()
            graph = self._compiler.compile(
                workflow=workflow,
                llm_model=llm_model,
                temperature=agent.temperature,
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
