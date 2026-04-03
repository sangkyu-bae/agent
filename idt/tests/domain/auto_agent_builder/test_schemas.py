"""AutoBuildSession, AgentSpecResult, ConversationTurn 도메인 스키마 테스트."""
from datetime import datetime, timedelta
import pytest

from src.domain.auto_agent_builder.schemas import (
    AgentSpecResult,
    AutoBuildSession,
    ConversationTurn,
)


class TestConversationTurn:

    def test_frozen_immutable(self):
        turn = ConversationTurn(questions=["Q1"], answers=["A1"])
        with pytest.raises((AttributeError, TypeError)):
            turn.questions = ["other"]  # type: ignore

    def test_fields(self):
        turn = ConversationTurn(questions=["Q1", "Q2"], answers=["A1", "A2"])
        assert turn.questions == ["Q1", "Q2"]
        assert turn.answers == ["A1", "A2"]


class TestAgentSpecResult:

    def test_frozen_immutable(self):
        spec = AgentSpecResult(
            confidence=0.9,
            tool_ids=["internal_document_search"],
            middleware_configs=[],
            system_prompt="prompt",
            clarifying_questions=[],
            reasoning="reason",
        )
        with pytest.raises((AttributeError, TypeError)):
            spec.confidence = 0.5  # type: ignore

    def test_all_fields_accessible(self):
        spec = AgentSpecResult(
            confidence=0.85,
            tool_ids=["excel_export"],
            middleware_configs=[{"type": "pii", "config": {}}],
            system_prompt="sys",
            clarifying_questions=["Is PII present?"],
            reasoning="chose pii",
        )
        assert spec.confidence == 0.85
        assert spec.tool_ids == ["excel_export"]
        assert len(spec.middleware_configs) == 1
        assert spec.clarifying_questions == ["Is PII present?"]
        assert spec.reasoning == "chose pii"


class TestAutoBuildSession:

    def _make_session(self) -> AutoBuildSession:
        now = datetime.utcnow()
        return AutoBuildSession(
            session_id="sess-1",
            user_id="user-1",
            user_request="분석 에이전트 만들어줘",
            model_name="gpt-4o",
            created_at=now,
            expires_at=now + timedelta(hours=24),
        )

    def test_default_status_is_pending(self):
        session = self._make_session()
        assert session.status == "pending"
        assert session.attempt_count == 0
        assert session.created_agent_id is None
        assert session.conversation_turns == []

    def test_add_questions_appends_new_turn(self):
        session = self._make_session()
        session.add_questions(["PII 데이터 있나요?"])
        assert len(session.conversation_turns) == 1
        assert session.conversation_turns[0].questions == ["PII 데이터 있나요?"]
        assert session.conversation_turns[0].answers == []

    def test_add_answers_fills_last_turn(self):
        session = self._make_session()
        session.add_questions(["PII 데이터 있나요?"])
        session.add_answers(["네, 이메일 포함"])
        assert session.conversation_turns[0].answers == ["네, 이메일 포함"]

    def test_add_answers_no_turns_does_nothing(self):
        session = self._make_session()
        session.add_answers(["answer"])  # no turns → should not raise
        assert session.conversation_turns == []

    def test_add_multiple_turns(self):
        session = self._make_session()
        session.add_questions(["Q1"])
        session.add_answers(["A1"])
        session.add_questions(["Q2"])
        assert len(session.conversation_turns) == 2
        assert session.conversation_turns[0].answers == ["A1"]
        assert session.conversation_turns[1].answers == []

    def test_build_context_empty(self):
        session = self._make_session()
        assert session.build_context() == ""

    def test_build_context_with_turns(self):
        session = self._make_session()
        session.add_questions(["PII 있나요?"])
        session.add_answers(["네"])
        context = session.build_context()
        assert "[Round 1] Q: PII 있나요?" in context
        assert "[Round 1] A: 네" in context

    def test_status_mutation(self):
        session = self._make_session()
        session.status = "created"
        session.created_agent_id = "agent-uuid"
        assert session.status == "created"
        assert session.created_agent_id == "agent-uuid"
