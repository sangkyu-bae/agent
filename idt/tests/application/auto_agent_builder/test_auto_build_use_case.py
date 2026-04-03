"""AutoBuildUseCase 테스트 (Application Layer Mock)."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.application.auto_agent_builder.schemas import AutoBuildRequest, AutoBuildResponse
from src.domain.auto_agent_builder.schemas import AgentSpecResult, AutoBuildSession
from src.application.auto_agent_builder.auto_build_use_case import AutoBuildUseCase


def _make_request(request_id: str = "req-1") -> AutoBuildRequest:
    return AutoBuildRequest(
        user_request="분기 보고서 엑셀로 만들어줘",
        user_id="user-1",
        model_name="gpt-4o",
        request_id=request_id,
    )


def _make_spec(confident: bool = True) -> AgentSpecResult:
    return AgentSpecResult(
        confidence=0.9 if confident else 0.5,
        tool_ids=["excel_export"],
        middleware_configs=[{"type": "summarization", "config": {}}],
        system_prompt="보고서 에이전트",
        clarifying_questions=[] if confident else ["데이터 소스는 어디인가요?"],
        reasoning="엑셀 내보내기 필요",
    )


def _make_use_case(spec: AgentSpecResult):
    inference = AsyncMock()
    inference.infer = AsyncMock(return_value=spec)

    session_repo = AsyncMock()
    session_repo.save = AsyncMock()

    created_agent = MagicMock()
    created_agent.agent_id = "agent-uuid"

    create_agent_uc = AsyncMock()
    create_agent_uc.execute = AsyncMock(return_value=created_agent)

    logger = MagicMock()
    logger.info = MagicMock()
    logger.error = MagicMock()

    uc = AutoBuildUseCase(
        inference_service=inference,
        session_repository=session_repo,
        create_agent_use_case=create_agent_uc,
        logger=logger,
    )
    return uc, inference, session_repo, create_agent_uc


class TestExecuteConfident:

    @pytest.mark.asyncio
    async def test_returns_created_status_when_confident(self):
        spec = _make_spec(confident=True)
        uc, _, _, _ = _make_use_case(spec)

        result = await uc.execute(_make_request())

        assert result.status == "created"
        assert result.agent_id == "agent-uuid"

    @pytest.mark.asyncio
    async def test_calls_create_agent_use_case_when_confident(self):
        spec = _make_spec(confident=True)
        uc, _, _, create_agent_uc = _make_use_case(spec)

        await uc.execute(_make_request())

        create_agent_uc.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_saves_session_with_created_status(self):
        spec = _make_spec(confident=True)
        uc, _, session_repo, _ = _make_use_case(spec)

        await uc.execute(_make_request())

        session_repo.save.assert_awaited_once()
        saved: AutoBuildSession = session_repo.save.call_args[0][0]
        assert saved.status == "created"
        assert saved.created_agent_id == "agent-uuid"

    @pytest.mark.asyncio
    async def test_response_includes_tool_ids_and_middlewares(self):
        spec = _make_spec(confident=True)
        uc, _, _, _ = _make_use_case(spec)

        result = await uc.execute(_make_request())

        assert result.tool_ids == ["excel_export"]
        assert result.middlewares_applied == ["summarization"]


class TestExecuteNeedsClarity:

    @pytest.mark.asyncio
    async def test_returns_needs_clarification_when_uncertain(self):
        spec = _make_spec(confident=False)
        uc, _, _, _ = _make_use_case(spec)

        result = await uc.execute(_make_request())

        assert result.status == "needs_clarification"
        assert result.questions == ["데이터 소스는 어디인가요?"]

    @pytest.mark.asyncio
    async def test_saves_session_pending_when_uncertain(self):
        spec = _make_spec(confident=False)
        uc, _, session_repo, _ = _make_use_case(spec)

        await uc.execute(_make_request())

        session_repo.save.assert_awaited_once()
        saved: AutoBuildSession = session_repo.save.call_args[0][0]
        assert saved.status == "pending"
        assert saved.attempt_count == 1

    @pytest.mark.asyncio
    async def test_does_not_call_create_agent_when_uncertain(self):
        spec = _make_spec(confident=False)
        uc, _, _, create_agent_uc = _make_use_case(spec)

        await uc.execute(_make_request())

        create_agent_uc.execute.assert_not_awaited()


class TestExecuteErrorHandling:

    @pytest.mark.asyncio
    async def test_logs_error_and_reraises_on_exception(self):
        spec = _make_spec(confident=True)
        uc, inference, _, _ = _make_use_case(spec)
        inference.infer = AsyncMock(side_effect=RuntimeError("LLM down"))

        with pytest.raises(RuntimeError, match="LLM down"):
            await uc.execute(_make_request())

        uc._logger.error.assert_called_once()
