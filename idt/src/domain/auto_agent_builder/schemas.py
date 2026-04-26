"""도메인 스키마: AgentSpecResult, AutoBuildSession, ConversationTurn."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class ConversationTurn:
    """Q&A 1회 교환 Value Object."""
    questions: list[str]
    answers: list[str]


@dataclass(frozen=True)
class AgentSpecResult:
    """LLM이 추론한 에이전트 명세 Value Object."""
    confidence: float
    tool_ids: list[str]
    middleware_configs: list[dict]
    system_prompt: str
    clarifying_questions: list[str]
    reasoning: str
    tool_configs: dict[str, dict] = field(default_factory=dict)


@dataclass
class AutoBuildSession:
    """자동 에이전트 빌드 세션 (Redis 저장)."""
    session_id: str
    user_id: str
    user_request: str
    model_name: str
    conversation_turns: list[ConversationTurn] = field(default_factory=list)
    attempt_count: int = 0
    status: str = "pending"
    created_agent_id: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime = field(default_factory=datetime.utcnow)

    def add_answers(self, answers: list[str]) -> None:
        """마지막 턴에 사용자 답변을 기록."""
        if not self.conversation_turns:
            return
        last = self.conversation_turns[-1]
        self.conversation_turns[-1] = ConversationTurn(
            questions=last.questions,
            answers=answers,
        )

    def add_questions(self, questions: list[str]) -> None:
        """새 질문 턴을 추가."""
        self.conversation_turns.append(
            ConversationTurn(questions=questions, answers=[])
        )

    def build_context(self) -> str:
        """추론 프롬프트용 대화 이력 문자열 반환."""
        lines = []
        for i, turn in enumerate(self.conversation_turns, 1):
            for q, a in zip(turn.questions, turn.answers):
                lines.append(f"[Round {i}] Q: {q}")
                lines.append(f"[Round {i}] A: {a}")
        return "\n".join(lines)
