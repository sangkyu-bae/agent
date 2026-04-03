"""ConversationUseCase: Multi-Turn 대화 메모리 관리 UseCase.

동작 흐름 (CLAUDE.md §7):
1. 기존 메시지 조회
2. 유저 메시지 DB 저장
3. 6턴 초과 여부 체크 (SummarizationPolicy)
   ├─ 괜찮으면 → 전체 히스토리로 LLM 전송
   └─ 초과면   → 오래된 부분 요약 → summary 저장 → 압축 히스토리로 LLM 전송
4. LLM 응답 받아서 DB 저장
5. ConversationChatResponse 반환
"""
from datetime import datetime

from src.application.conversation.interfaces import (
    ConversationLLMInterface,
    ConversationSummarizerInterface,
)
from src.application.repositories.conversation_repository import (
    ConversationMessageRepository,
)
from src.application.repositories.conversation_summary_repository import (
    ConversationSummaryRepository,
)
from src.domain.conversation.entities import ConversationMessage, ConversationSummary
from src.domain.conversation.policies import SummarizationPolicy
from src.domain.conversation.schemas import ConversationChatRequest, ConversationChatResponse
from src.domain.conversation.value_objects import MessageRole, SessionId, TurnIndex, UserId
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class ConversationUseCase:
    """Multi-Turn 대화 메모리 관리 UseCase.

    6턴 초과 시 SummarizationPolicy에 따라 오래된 히스토리를 LLM으로 요약하고,
    (요약본 + 최근 3턴)만 컨텍스트로 사용하여 토큰 폭증을 방지한다.
    """

    def __init__(
        self,
        message_repo: ConversationMessageRepository,
        summary_repo: ConversationSummaryRepository,
        summarizer: ConversationSummarizerInterface,
        llm: ConversationLLMInterface,
        policy: SummarizationPolicy,
        logger: LoggerInterface,
    ) -> None:
        self._msg_repo = message_repo
        self._summary_repo = summary_repo
        self._summarizer = summarizer
        self._llm = llm
        self._policy = policy
        self._logger = logger

    async def execute(
        self, request: ConversationChatRequest, request_id: str
    ) -> ConversationChatResponse:
        """대화 질의 처리.

        Args:
            request: 사용자 ID, 세션 ID, 메시지
            request_id: 요청 추적 ID

        Returns:
            LLM 생성 답변 + 요약 발생 여부
        """
        self._logger.info(
            "ConversationUseCase started",
            request_id=request_id,
            user_id=request.user_id,
            session_id=request.session_id,
        )
        try:
            user_id = UserId(request.user_id)
            session_id = SessionId(request.session_id)

            # 1. 기존 메시지 조회
            existing = await self._msg_repo.find_by_session(user_id, session_id)

            # 2. 유저 메시지 저장
            user_turn = TurnIndex(len(existing) + 1)
            user_msg = ConversationMessage(
                id=None,
                user_id=user_id,
                session_id=session_id,
                role=MessageRole.USER,
                content=request.message,
                turn_index=user_turn,
                created_at=datetime.utcnow(),
            )
            await self._msg_repo.save(user_msg)

            # 3. 요약 필요 여부 체크 (새 유저 메시지 제외한 기존 메시지 기준)
            was_summarized = False
            if self._policy.needs_summarization(existing):
                was_summarized = True
                context = await self._build_summarized_context(
                    existing, request.message, user_id, session_id, request_id
                )
            else:
                context = self._build_full_context(existing, request.message)

            # 4. LLM 호출
            answer = await self._llm.generate(context, request_id)

            # 5. 어시스턴트 응답 저장
            assistant_turn = TurnIndex(len(existing) + 2)
            assistant_msg = ConversationMessage(
                id=None,
                user_id=user_id,
                session_id=session_id,
                role=MessageRole.ASSISTANT,
                content=answer,
                turn_index=assistant_turn,
                created_at=datetime.utcnow(),
            )
            await self._msg_repo.save(assistant_msg)

            self._logger.info(
                "ConversationUseCase completed",
                request_id=request_id,
                was_summarized=was_summarized,
            )
            return ConversationChatResponse(
                user_id=request.user_id,
                session_id=request.session_id,
                answer=answer,
                was_summarized=was_summarized,
                request_id=request_id,
            )
        except Exception as e:
            self._logger.error(
                "ConversationUseCase failed", exception=e, request_id=request_id
            )
            raise

    async def _build_summarized_context(
        self,
        existing: list[ConversationMessage],
        new_message: str,
        user_id: UserId,
        session_id: SessionId,
        request_id: str,
    ) -> list[dict]:
        """요약 컨텍스트 구성: 오래된 턴 요약 → 저장 → (요약 + 최근 3턴 + 새 메시지)."""
        to_summarize = self._policy.get_turns_to_summarize(existing)
        start_turn, end_turn = self._policy.get_summary_range(existing)

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

        recent = self._policy.get_recent_turns(existing)
        context: list[dict] = [
            {"role": "system", "content": f"[이전 대화 요약]\n{summary_text}"}
        ]
        for msg in sorted(recent, key=lambda m: m.turn_index.value):
            context.append({"role": msg.role.value, "content": msg.content})
        context.append({"role": "user", "content": new_message})
        return context

    def _build_full_context(
        self,
        existing: list[ConversationMessage],
        new_message: str,
    ) -> list[dict]:
        """전체 히스토리 + 새 메시지로 컨텍스트 구성."""
        context: list[dict] = []
        for msg in sorted(existing, key=lambda m: m.turn_index.value):
            context.append({"role": msg.role.value, "content": msg.content})
        context.append({"role": "user", "content": new_message})
        return context
