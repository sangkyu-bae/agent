"""Interview 세션 상태 관리 (In-Memory)."""
from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.domain.agent_builder.schemas import WorkerDefinition, WorkflowSkeleton


@dataclass
class QAPair:
    """질문-답변 쌍."""
    question: str
    answer: str


@dataclass
class InterviewSession:
    """인터뷰 세션 상태."""
    session_id: str
    user_request: str
    name: str
    user_id: str
    model_name: str
    status: str  # "questioning" | "reviewing" | "confirmed"
    current_questions: list[str] = field(default_factory=list)
    qa_pairs: list[QAPair] = field(default_factory=list)
    draft_skeleton: WorkflowSkeleton | None = None
    draft_system_prompt: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class InMemoryInterviewSessionStore:
    """인터뷰 세션 인메모리 저장소."""

    def __init__(self) -> None:
        self._sessions: dict[str, InterviewSession] = {}

    def create(self, session: InterviewSession) -> None:
        self._sessions[session.session_id] = session

    def get(self, session_id: str) -> InterviewSession | None:
        return self._sessions.get(session_id)

    def update(self, session: InterviewSession) -> None:
        self._sessions[session.session_id] = session

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
