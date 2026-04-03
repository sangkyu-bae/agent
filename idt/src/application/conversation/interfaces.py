"""Conversation UseCase용 외부 서비스 추상 인터페이스."""
from abc import ABC, abstractmethod

from src.domain.conversation.entities import ConversationMessage


class ConversationSummarizerInterface(ABC):
    """대화 히스토리 요약 추상 인터페이스."""

    @abstractmethod
    async def summarize(
        self,
        messages: list[ConversationMessage],
        request_id: str,
    ) -> str:
        """메시지 목록을 사실 중심으로 요약하여 문자열 반환.

        CLAUDE.md 7.4 정책:
        - 사실 중심 요약 (결정사항, 사용자 의도, 중요한 제약 포함)
        - 질문/답변 형식 금지
        """


class ConversationLLMInterface(ABC):
    """대화 컨텍스트 기반 LLM 응답 생성 추상 인터페이스."""

    @abstractmethod
    async def generate(
        self,
        messages: list[dict],
        request_id: str,
    ) -> str:
        """messages: [{"role": "system"|"user"|"assistant", "content": "..."}] 형식."""
