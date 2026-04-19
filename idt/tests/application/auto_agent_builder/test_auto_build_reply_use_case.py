"""AutoBuildReplyUseCase 테스트."""
from datetime import datetime, timedelta

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.application.auto_agent_builder.schemas import AutoBuildReplyRequest
from src.domain.auto_agent_builder.schemas import AgentSpecResult, AutoBuildSession, ConversationTurn
from src.application.auto_agent_builder.auto_build_reply_use_case import AutoBuildReplyUseCase


def _make_reply_request(answers: list[str] | None = None) -> AutoBuildReplyRequest:
    return AutoBuildReplyRequest(
        answers=answers or ["내부 문서"],
        request_id="req-reply-1",
    )


def _make_session(attempt_count: int = 1) -> AutoBuildSession:
    now = datetime(2026, 3, 24, 12, 0, 0)
    s = AutoBuildSession(
        session_id="sess-1",
        user_id="user-1",
        user_request="보고서 만들어줘",
        model_name="gpt-4o",
        created_at=now,
        expires_at=now + timedelta(hours=24),
    )
    s.conversation_turns = [
        ConversationTurn(questions=["데이터 소스는?"], answers=[])
    ]
    s.attempt_count = attempt_count
    return s


def _make_spec(confident: bool = True, questions: list[str] | None = None) -> AgentSpecResult:
    return AgentSpecResult(
        confidence=0.9 if confident else 0.5,
        tool_ids=["internal_document_search"],
        middleware_configs=[],
        system_prompt="문서 검색 에이전트",
        clarifying_questions=questions or ([] if confident else ["출력 형식은?"]),
        reasoning="내부 문서 검색",
    )


def _make_uc(session: AutoBuildSession, spec: AgentSpecResult):
    inference = AsyncMock()
    inference.infer = AsyncMock(return_value=spec)

    session_repo = AsyncMock()
    session_repo.find = AsyncMock(return_value=session)
    session_repo.save = AsyncMock()

    created_agent = MagicMock()
    created_agent.agent_id = "agent-uuid"
    create_agent_uc = AsyncMock()
    create_agent_uc.execute = AsyncMock(return_value=created_agent)

    logger = MagicMock()
    logger.info = MagicMock()
    logger.error = MagicMock()

    uc = AutoBuildReplyUseCase(
        inference_service=inference,
        session_repository=session_repo,
        logger=logger,
    )
    return uc, inference, session_repo, create_agent_uc


class TestReplyConfident:

    @pytest.mark.asyncio
    async def test_returns_created_when_now_confident(self):
        session = _make_session()
        spec = _make_spec(confident=True)
        uc, _, _, create_agent_uc = _make_uc(session, spec)

        result = await uc.execute("sess-1", _make_reply_request(), create_agent_use_case=create_agent_uc)

        assert result.status == "created"
        assert result.agent_id == "agent-uuid"

    @pytest.mark.asyncio
    async def test_saves_session_created_status(self):
        session = _make_session()
        spec = _make_spec(confident=True)
        uc, _, session_repo, create_agent_uc = _make_uc(session, spec)

        await uc.execute("sess-1", _make_reply_request(), create_agent_use_case=create_agent_uc)

        session_repo.save.assert_awaited()
        assert session.status == "created"
        assert session.created_agent_id == "agent-uuid"


class TestReplyStillUncertain:

    @pytest.mark.asyncio
    async def test_returns_needs_clarification_when_still_uncertain(self):
        session = _make_session(attempt_count=1)
        spec = _make_spec(confident=False, questions=["출력 형식은?"])
        uc, _, _, create_agent_uc = _make_uc(session, spec)

        result = await uc.execute("sess-1", _make_reply_request(), create_agent_use_case=create_agent_uc)

        assert result.status == "needs_clarification"
        assert result.questions == ["출력 형식은?"]

    @pytest.mark.asyncio
    async def test_adds_new_turn_to_session(self):
        session = _make_session(attempt_count=1)
        spec = _make_spec(confident=False, questions=["출력 형식은?"])
        uc, _, session_repo, create_agent_uc = _make_uc(session, spec)

        await uc.execute("sess-1", _make_reply_request(), create_agent_use_case=create_agent_uc)

        session_repo.save.assert_awaited()
        assert len(session.conversation_turns) == 2


class TestReplyForceCreate:

    @pytest.mark.asyncio
    async def test_force_creates_at_max_attempts(self):
        session = _make_session(attempt_count=3)
        spec = _make_spec(confident=False, questions=["아직도 질문"])
        uc, _, _, create_agent_uc = _make_uc(session, spec)

        result = await uc.execute("sess-1", _make_reply_request(), create_agent_use_case=create_agent_uc)

        assert result.status == "created"

    @pytest.mark.asyncio
    async def test_force_create_ignores_questions(self):
        session = _make_session(attempt_count=3)
        # spec has questions but should be forced to create
        spec = _make_spec(confident=False, questions=["무시될 질문"])
        uc, _, _, create_agent_uc = _make_uc(session, spec)

        result = await uc.execute("sess-1", _make_reply_request(), create_agent_use_case=create_agent_uc)

        create_agent_uc.execute.assert_awaited_once()
        assert result.status == "created"


class TestReplySessionNotFound:

    @pytest.mark.asyncio
    async def test_raises_when_session_not_found(self):
        inference = AsyncMock()
        session_repo = AsyncMock()
        session_repo.find = AsyncMock(return_value=None)
        create_agent_uc = AsyncMock()
        logger = MagicMock()
        logger.info = MagicMock()
        logger.error = MagicMock()

        uc = AutoBuildReplyUseCase(
            inference_service=inference,
            session_repository=session_repo,
            logger=logger,
        )

        with pytest.raises(ValueError, match="Session not found"):
            await uc.execute("no-such-session", _make_reply_request(), create_agent_use_case=create_agent_uc)

        logger.error.assert_called_once()
