"""AutoAgentBuilderPolicy 테스트 (mock 없음)."""
import pytest
from datetime import datetime, timedelta

from src.domain.auto_agent_builder.schemas import AgentSpecResult, AutoBuildSession
from src.domain.auto_agent_builder.policies import AutoAgentBuilderPolicy


def _make_spec(confidence: float, questions: list[str] | None = None) -> AgentSpecResult:
    return AgentSpecResult(
        confidence=confidence,
        tool_ids=["internal_document_search"],
        middleware_configs=[],
        system_prompt="prompt",
        clarifying_questions=questions or [],
        reasoning="reason",
    )


def _make_session(attempt_count: int) -> AutoBuildSession:
    now = datetime.utcnow()
    s = AutoBuildSession(
        session_id="s1",
        user_id="u1",
        user_request="req",
        model_name="gpt-4o",
        created_at=now,
        expires_at=now + timedelta(hours=24),
    )
    s.attempt_count = attempt_count
    return s


class TestIsConfidentEnough:

    def test_high_confidence_no_questions_returns_true(self):
        spec = _make_spec(0.9)
        assert AutoAgentBuilderPolicy.is_confident_enough(spec) is True

    def test_exact_threshold_returns_true(self):
        spec = _make_spec(0.8)
        assert AutoAgentBuilderPolicy.is_confident_enough(spec) is True

    def test_below_threshold_returns_false(self):
        spec = _make_spec(0.79)
        assert AutoAgentBuilderPolicy.is_confident_enough(spec) is False

    def test_high_confidence_but_has_questions_returns_false(self):
        spec = _make_spec(0.9, questions=["PII 있나요?"])
        assert AutoAgentBuilderPolicy.is_confident_enough(spec) is False

    def test_zero_confidence_returns_false(self):
        spec = _make_spec(0.0)
        assert AutoAgentBuilderPolicy.is_confident_enough(spec) is False


class TestShouldForceCreate:

    def test_at_max_attempts_returns_true(self):
        session = _make_session(3)
        assert AutoAgentBuilderPolicy.should_force_create(session) is True

    def test_above_max_attempts_returns_true(self):
        session = _make_session(5)
        assert AutoAgentBuilderPolicy.should_force_create(session) is True

    def test_below_max_attempts_returns_false(self):
        session = _make_session(2)
        assert AutoAgentBuilderPolicy.should_force_create(session) is False

    def test_zero_attempts_returns_false(self):
        session = _make_session(0)
        assert AutoAgentBuilderPolicy.should_force_create(session) is False


class TestValidateToolIds:

    def test_valid_tool_ids_no_error(self):
        available = {"internal_document_search", "excel_export", "tavily_search"}
        AutoAgentBuilderPolicy.validate_tool_ids(["internal_document_search"], available)

    def test_unknown_tool_id_raises(self):
        available = {"internal_document_search"}
        with pytest.raises(ValueError, match="Unknown tool_ids"):
            AutoAgentBuilderPolicy.validate_tool_ids(["unknown_tool"], available)

    def test_empty_tool_ids_no_error(self):
        available = {"internal_document_search"}
        AutoAgentBuilderPolicy.validate_tool_ids([], available)

    def test_multiple_unknown_raises(self):
        available = {"internal_document_search"}
        with pytest.raises(ValueError, match="Unknown tool_ids"):
            AutoAgentBuilderPolicy.validate_tool_ids(["a", "b"], available)


class TestPolicyConstants:

    def test_confidence_threshold(self):
        assert AutoAgentBuilderPolicy.CONFIDENCE_THRESHOLD == 0.8

    def test_max_attempts(self):
        assert AutoAgentBuilderPolicy.MAX_ATTEMPTS == 3

    def test_session_ttl(self):
        assert AutoAgentBuilderPolicy.SESSION_TTL_SECONDS == 86400
