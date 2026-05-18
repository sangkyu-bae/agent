"""RunAgentUseCase: DB에서 워크플로우 로드 → LangGraph 동적 컴파일 → 실행."""
import uuid
from datetime import datetime, timezone

from src.application.agent_builder.schemas import RunAgentRequest, RunAgentResponse
from src.application.agent_builder.supervisor_nodes import build_initial_state
from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.domain.agent_builder.schemas import SupervisorConfig
from src.application.conversation.interfaces import ConversationSummarizerInterface
from src.application.repositories.conversation_repository import (
    ConversationMessageRepository,
)
from src.application.repositories.conversation_summary_repository import (
    ConversationSummaryRepository,
)
from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.agent_builder.policies import AccessCheckInput, VisibilityPolicy
from src.domain.conversation.entities import ConversationMessage, ConversationSummary
from src.domain.conversation.policies import SummarizationPolicy
from src.domain.conversation.value_objects import (
    AgentId,
    MessageRole,
    SessionId,
    TurnIndex,
    UserId,
)
from src.domain.llm_model.interfaces import LlmModelRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.langsmith.langsmith import langsmith


class RunAgentUseCase:
    def __init__(
        self,
        repository: AgentDefinitionRepositoryInterface,
        llm_model_repository: LlmModelRepositoryInterface,
        compiler: WorkflowCompiler,
        logger: LoggerInterface,
        message_repo: ConversationMessageRepository,
        summary_repo: ConversationSummaryRepository,
        summarizer: ConversationSummarizerInterface,
        policy: SummarizationPolicy,
    ) -> None:
        self._repository = repository
        self._llm_model_repository = llm_model_repository
        self._compiler = compiler
        self._logger = logger
        self._message_repo = message_repo
        self._summary_repo = summary_repo
        self._summarizer = summarizer
        self._policy = policy

    async def execute(
        self,
        agent_id: str,
        request: RunAgentRequest,
        request_id: str,
        viewer_user_id: str | None = None,
        viewer_department_ids: list[str] | None = None,
    ) -> RunAgentResponse:
        langsmith(project_name="agent-run")
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

            session_id = request.session_id or str(uuid.uuid4())

            messages = await self._build_messages(
                request.query, request.user_id, session_id, request.session_id is not None
            )

            llm_model = await self._llm_model_repository.find_by_id(
                agent.llm_model_id, request_id
            )
            if llm_model is None:
                raise ValueError(
                    f"에이전트에 연결된 LLM 모델을 찾을 수 없습니다: {agent.llm_model_id}"
                )

            workflow = agent.to_workflow_definition()
            config = SupervisorConfig()
            graph = await self._compiler.compile(
                workflow=workflow,
                llm_model=llm_model,
                temperature=agent.temperature,
                request_id=request_id,
                supervisor_config=config,
                depth=0,
                visited={agent_id},
            )

            initial_state = build_initial_state(
                messages=messages,
                config=config,
                available_workers=[w.worker_id for w in workflow.workers],
            )
            result = await graph.ainvoke(initial_state)
            answer, tools_used = self._parse_result(result)

            await self._save_turn(
                request.query, answer, request.user_id, session_id, agent_id
            )

            self._logger.info(
                "RunAgentUseCase done", request_id=request_id, agent_id=agent_id
            )
            return RunAgentResponse(
                agent_id=agent_id,
                query=request.query,
                answer=answer,
                tools_used=tools_used,
                request_id=request_id,
                session_id=session_id,
            )
        except Exception as e:
            self._logger.error(
                "RunAgentUseCase failed", exception=e, request_id=request_id
            )
            raise

    async def _build_messages(
        self,
        query: str,
        user_id: str,
        session_id: str,
        has_session: bool,
    ) -> list[dict]:
        if not has_session:
            return [{"role": "user", "content": query}]

        existing = await self._message_repo.find_by_session(
            UserId(user_id), SessionId(session_id)
        )

        if not existing:
            return [{"role": "user", "content": query}]

        if self._policy.needs_summarization(existing):
            return await self._build_summarized_context(
                existing, query, user_id, session_id
            )

        messages: list[dict] = []
        for msg in sorted(existing, key=lambda m: m.turn_index.value):
            messages.append({"role": msg.role.value, "content": msg.content})
        messages.append({"role": "user", "content": query})
        return messages

    async def _build_summarized_context(
        self,
        existing: list[ConversationMessage],
        query: str,
        user_id: str,
        session_id: str,
    ) -> list[dict]:
        to_summarize = self._policy.get_turns_to_summarize(existing)
        start_turn, end_turn = self._policy.get_summary_range(existing)

        summary_text = await self._summarizer.summarize(to_summarize, session_id)

        summary = ConversationSummary(
            id=None,
            user_id=UserId(user_id),
            session_id=SessionId(session_id),
            agent_id=existing[0].agent_id,
            summary_content=summary_text,
            start_turn=start_turn,
            end_turn=end_turn,
            created_at=datetime.now(timezone.utc),
        )
        await self._summary_repo.save(summary)

        recent = self._policy.get_recent_turns(existing)
        messages: list[dict] = [
            {"role": "system", "content": f"[이전 대화 요약]\n{summary_text}"}
        ]
        for msg in sorted(recent, key=lambda m: m.turn_index.value):
            messages.append({"role": msg.role.value, "content": msg.content})
        messages.append({"role": "user", "content": query})
        return messages

    async def _save_turn(
        self,
        query: str,
        answer: str,
        user_id: str,
        session_id: str,
        agent_id: str,
    ) -> None:
        existing = await self._message_repo.find_by_session(
            UserId(user_id), SessionId(session_id)
        )
        base_turn = len(existing)

        user_msg = ConversationMessage(
            id=None,
            user_id=UserId(user_id),
            session_id=SessionId(session_id),
            agent_id=AgentId(agent_id),
            role=MessageRole.USER,
            content=query,
            turn_index=TurnIndex(base_turn + 1),
            created_at=datetime.now(timezone.utc),
        )
        await self._message_repo.save(user_msg)

        assistant_msg = ConversationMessage(
            id=None,
            user_id=UserId(user_id),
            session_id=SessionId(session_id),
            agent_id=AgentId(agent_id),
            role=MessageRole.ASSISTANT,
            content=answer,
            turn_index=TurnIndex(base_turn + 2),
            created_at=datetime.now(timezone.utc),
        )
        await self._message_repo.save(assistant_msg)

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
