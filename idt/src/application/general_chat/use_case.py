"""GeneralChatUseCase: ReAct 에이전트 + 멀티턴 대화 메모리 오케스트레이션."""
from __future__ import annotations

import uuid
from datetime import datetime

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from src.application.conversation.interfaces import ConversationSummarizerInterface
from src.application.general_chat.tools import ChatToolBuilder
from src.application.repositories.conversation_repository import ConversationMessageRepository
from src.application.repositories.conversation_summary_repository import (
    ConversationSummaryRepository,
)
from src.domain.conversation.entities import ConversationMessage, ConversationSummary
from src.domain.conversation.policies import SummarizationPolicy
from src.domain.conversation.value_objects import MessageRole, SessionId, TurnIndex, UserId
from src.domain.general_chat.schemas import DocumentSource, GeneralChatRequest, GeneralChatResponse
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.langsmith.langsmith import langsmith

_SYSTEM_PROMPT = (
    "당신은 사용자의 일반 질문에 답하는 AI 어시스턴트입니다.\n"
    "필요에 따라 다음 도구를 사용하세요:\n"
    "- tavily_search: 최신 웹 정보 검색\n"
    "- internal_document_search: 내부 문서(금융/정책 등) 검색\n"
    "- MCP 도구: 등록된 외부 서비스 연동\n"
    "항상 한국어로 답변하세요."
)


class GeneralChatUseCase:
    """LangGraph ReAct 에이전트 기반 범용 채팅 UseCase.

    의존성 (CONV-001 재사용):
    - ConversationMessageRepository: 대화 저장/조회
    - ConversationSummaryRepository: 요약 저장
    - ConversationSummarizerInterface: 오래된 턴 요약
    - SummarizationPolicy: 요약 정책 판단
    """

    def __init__(
        self,
        chat_tool_builder: ChatToolBuilder,
        message_repo: ConversationMessageRepository,
        summary_repo: ConversationSummaryRepository,
        summarizer: ConversationSummarizerInterface,
        summarization_policy: SummarizationPolicy,
        logger: LoggerInterface,
        openai_api_key: str = "",
        model_name: str = "gpt-4o",
        max_iterations: int = 10,
    ) -> None:
        self._tool_builder = chat_tool_builder
        self._msg_repo = message_repo
        self._summary_repo = summary_repo
        self._summarizer = summarizer
        self._policy = summarization_policy
        self._logger = logger
        self._api_key = openai_api_key
        self._model_name = model_name
        self._max_iterations = max_iterations

    def _create_agent(self, tools: list):
        """ReAct 에이전트 생성 (테스트에서 패치 가능)."""
        llm = ChatOpenAI(
            model=self._model_name,
            api_key=self._api_key or None,
            temperature=0,
        )
        return create_react_agent(llm, tools=tools)

    async def execute(
        self, request: GeneralChatRequest, request_id: str
    ) -> GeneralChatResponse:
        """채팅 요청 처리.

        Args:
            request: 사용자 요청 (user_id, session_id, message, top_k)
            request_id: 요청 추적 ID

        Returns:
            에이전트 답변 + 사용 도구 목록 + 출처 + 요약 여부
        """
        langsmith(project_name="general-chat")
        self._logger.info(
            "GeneralChatUseCase started",
            request_id=request_id,
            user_id=request.user_id,
            session_id=request.session_id,
        )
        try:
            # 1. session_id 확보
            session_id_str = request.session_id or str(uuid.uuid4())
            user_id = UserId(request.user_id)
            session_id = SessionId(session_id_str)

            # 2. 대화 히스토리 조회
            history = await self._msg_repo.find_by_session(user_id, session_id)

            # 3. 요약 정책 체크
            was_summarized = False
            if self._policy.needs_summarization(history):
                was_summarized = True
                context_messages = await self._build_summarized_context(
                    history, request.message, user_id, session_id, request_id
                )
            else:
                context_messages = self._build_full_context(history, request.message)

            # 4. 도구 빌드
            tools = await self._tool_builder.build(
                top_k=request.top_k, request_id=request_id
            )

            # 5. ReAct 에이전트 실행
            agent = self._create_agent(tools)
            result = await agent.ainvoke({"messages": context_messages})

            # 6. 응답 파싱
            answer, tools_used, sources = self._parse_agent_output(result, tools)

            # 7. 사용자 메시지 + AI 응답 DB 저장
            turn_base = len(history)
            user_msg = ConversationMessage(
                id=None,
                user_id=user_id,
                session_id=session_id,
                role=MessageRole.USER,
                content=request.message,
                turn_index=TurnIndex(turn_base + 1),
                created_at=datetime.utcnow(),
            )
            await self._msg_repo.save(user_msg)

            ai_msg = ConversationMessage(
                id=None,
                user_id=user_id,
                session_id=session_id,
                role=MessageRole.ASSISTANT,
                content=answer,
                turn_index=TurnIndex(turn_base + 2),
                created_at=datetime.utcnow(),
            )
            await self._msg_repo.save(ai_msg)

            self._logger.info(
                "GeneralChatUseCase completed",
                request_id=request_id,
                was_summarized=was_summarized,
                tools_used=tools_used,
                sources_count=len(sources),
            )
            return GeneralChatResponse(
                user_id=request.user_id,
                session_id=session_id_str,
                answer=answer,
                tools_used=tools_used,
                sources=sources,
                was_summarized=was_summarized,
                request_id=request_id,
            )
        except Exception as e:
            self._logger.error(
                "GeneralChatUseCase failed", exception=e, request_id=request_id
            )
            raise

    async def _build_summarized_context(
        self,
        history: list[ConversationMessage],
        new_message: str,
        user_id: UserId,
        session_id: SessionId,
        request_id: str,
    ) -> list:
        """오래된 턴 요약 → 저장 → (SystemMessage(요약) + 최근 3턴 + 새 메시지)."""
        to_summarize = self._policy.get_turns_to_summarize(history)
        start_turn, end_turn = self._policy.get_summary_range(history)

        summary_text = await self._summarizer.summarize(to_summarize, request_id)

        summary = ConversationSummary(
            id=None,
            user_id=user_id,
            session_id=session_id,
            summary_content=summary_text,
            start_turn=start_turn,
            end_turn=end_turn,
            created_at=datetime.utcnow(),
        )
        await self._summary_repo.save(summary)

        recent = self._policy.get_recent_turns(history)
        messages = [SystemMessage(content=f"[이전 대화 요약]\n{summary_text}")]
        for msg in sorted(recent, key=lambda m: m.turn_index.value):
            if msg.role == MessageRole.USER:
                messages.append(HumanMessage(content=msg.content))
            else:
                messages.append(AIMessage(content=msg.content))
        messages.append(HumanMessage(content=new_message))
        return messages

    def _build_full_context(
        self,
        history: list[ConversationMessage],
        new_message: str,
    ) -> list:
        """전체 히스토리 + 새 메시지 → LangChain 메시지 목록."""
        messages = []
        for msg in sorted(history, key=lambda m: m.turn_index.value):
            if msg.role == MessageRole.USER:
                messages.append(HumanMessage(content=msg.content))
            else:
                messages.append(AIMessage(content=msg.content))
        messages.append(HumanMessage(content=new_message))
        return messages

    def _parse_agent_output(
        self,
        result: dict,
        tools: list,
    ) -> tuple[str, list[str], list[DocumentSource]]:
        """에이전트 결과 파싱.

        Returns:
            (answer, tools_used, sources)
        """
        raw_messages = result.get("messages", [])

        # 최종 AIMessage → answer
        answer = ""
        for msg in reversed(raw_messages):
            if isinstance(msg, AIMessage) and msg.content:
                answer = msg.content
                break

        # ToolMessage → tools_used
        tools_used = [
            msg.name
            for msg in raw_messages
            if isinstance(msg, ToolMessage) and getattr(msg, "name", None)
        ]

        # InternalDocumentSearchTool.collected_sources → sources
        sources: list[DocumentSource] = []
        for tool in tools:
            if getattr(tool, "name", None) == "internal_document_search":
                for src in getattr(tool, "collected_sources", []):
                    if isinstance(src, DocumentSource):
                        sources.append(src)
                    else:
                        # domain/rag_agent/schemas.DocumentSource 호환
                        sources.append(
                            DocumentSource(
                                content=src.content,
                                source=src.source,
                                chunk_id=src.chunk_id,
                                score=src.score,
                            )
                        )
                break

        return answer, tools_used, sources
