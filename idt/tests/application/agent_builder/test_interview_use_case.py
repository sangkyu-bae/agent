"""InterviewUseCase 단위 테스트."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.interview_use_case import InterviewUseCase
from src.application.agent_builder.schemas import (
    InterviewStartRequest,
    InterviewStartResponse,
    InterviewAnswerRequest,
    InterviewAnswerResponse,
    InterviewFinalizeRequest,
    CreateAgentResponse,
)
from src.application.agent_builder.interview_session_store import (
    InterviewSession,
    InMemoryInterviewSessionStore,
    QAPair,
)
from src.domain.agent_builder.schemas import WorkerDefinition, WorkflowSkeleton
from src.domain.llm_model.entity import LlmModel


def _make_default_llm_model() -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="model-default",
        provider="openai",
        model_name="gpt-4o",
        display_name="GPT-4o",
        description=None,
        api_key_env="OPENAI_API_KEY",
        max_tokens=128000,
        is_active=True,
        is_default=True,
        created_at=now,
        updated_at=now,
    )


def _make_use_case():
    interviewer = MagicMock()
    tool_selector = MagicMock()
    prompt_generator = MagicMock()
    repository = MagicMock()
    llm_model_repository = MagicMock()
    session_store = InMemoryInterviewSessionStore()
    logger = MagicMock()

    default_model = _make_default_llm_model()
    llm_model_repository.find_by_id = AsyncMock(return_value=default_model)
    llm_model_repository.find_default = AsyncMock(return_value=default_model)

    interviewer.generate_initial_questions = AsyncMock(
        return_value=["어떤 주제?", "저장 경로?", "몇 개?"]
    )
    interviewer.evaluate_and_get_followup = AsyncMock(return_value=(True, []))
    interviewer.build_enriched_context = MagicMock(return_value="AI 뉴스 + OpenAI 관련 + 10개")

    skeleton = WorkflowSkeleton(
        workers=[WorkerDefinition("tavily_search", "search_worker", "웹 검색", 0)],
        flow_hint="search 후 export",
    )
    tool_selector.select = AsyncMock(return_value=skeleton)
    prompt_generator.generate = AsyncMock(return_value="당신은 AI 뉴스 수집 에이전트입니다.")

    async def _save_agent(agent, request_id):
        return agent
    repository.save = _save_agent

    use_case = InterviewUseCase(
        interviewer=interviewer,
        tool_selector=tool_selector,
        prompt_generator=prompt_generator,
        repository=repository,
        llm_model_repository=llm_model_repository,
        session_store=session_store,
        logger=logger,
    )
    return use_case, interviewer, session_store


class TestInterviewUseCase:
    @pytest.mark.asyncio
    async def test_start_returns_start_response(self):
        use_case, _, _ = _make_use_case()
        request = InterviewStartRequest(
            user_request="AI 뉴스 수집 에이전트 만들어줘",
            name="AI 뉴스 수집기",
            user_id="user-1",
        )
        result = await use_case.start(request, "req-1")
        assert isinstance(result, InterviewStartResponse)
        assert result.session_id is not None
        assert len(result.questions) == 3

    @pytest.mark.asyncio
    async def test_start_stores_session(self):
        use_case, _, session_store = _make_use_case()
        request = InterviewStartRequest(
            user_request="AI 뉴스 수집",
            name="뉴스봇",
            user_id="user-1",
        )
        result = await use_case.start(request, "req-1")
        session = session_store.get(result.session_id)
        assert session is not None
        assert session.user_request == "AI 뉴스 수집"

    @pytest.mark.asyncio
    async def test_answer_with_sufficient_returns_reviewing_status(self):
        use_case, _, session_store = _make_use_case()
        # Start first
        start_req = InterviewStartRequest(
            user_request="AI 뉴스 수집", name="봇", user_id="user-1"
        )
        start_result = await use_case.start(start_req, "req-1")
        # Answer
        answer_req = InterviewAnswerRequest(answers=["OpenAI 뉴스", "/data/news", "10개"])
        result = await use_case.answer(start_result.session_id, answer_req, "req-2")
        assert isinstance(result, InterviewAnswerResponse)
        assert result.status == "reviewing"
        assert result.preview is not None

    @pytest.mark.asyncio
    async def test_answer_with_insufficient_returns_questioning_status(self):
        use_case, interviewer, _ = _make_use_case()
        interviewer.evaluate_and_get_followup = AsyncMock(
            return_value=(False, ["저장 경로는?", "몇 개?"])
        )
        start_req = InterviewStartRequest(
            user_request="AI 뉴스 수집", name="봇", user_id="user-1"
        )
        start_result = await use_case.start(start_req, "req-1")
        answer_req = InterviewAnswerRequest(answers=["OpenAI 뉴스만"])
        result = await use_case.answer(start_result.session_id, answer_req, "req-2")
        assert result.status == "questioning"
        assert len(result.questions) == 2

    @pytest.mark.asyncio
    async def test_finalize_returns_create_agent_response(self):
        use_case, _, session_store = _make_use_case()
        # Start + Answer to get to reviewing status
        start_req = InterviewStartRequest(
            user_request="AI 뉴스 수집", name="봇", user_id="user-1"
        )
        start_result = await use_case.start(start_req, "req-1")
        answer_req = InterviewAnswerRequest(answers=["OpenAI", "/data", "10"])
        await use_case.answer(start_result.session_id, answer_req, "req-2")
        # Finalize
        finalize_req = InterviewFinalizeRequest()
        result = await use_case.finalize(start_result.session_id, finalize_req, "req-3")
        assert isinstance(result, CreateAgentResponse)
        assert result.agent_id is not None

    @pytest.mark.asyncio
    async def test_finalize_with_system_prompt_override(self):
        use_case, _, _ = _make_use_case()
        start_req = InterviewStartRequest(
            user_request="AI 뉴스 수집", name="봇", user_id="user-1"
        )
        start_result = await use_case.start(start_req, "req-1")
        await use_case.answer(
            start_result.session_id,
            InterviewAnswerRequest(answers=["OpenAI", "/data", "10"]),
            "req-2",
        )
        finalize_req = InterviewFinalizeRequest(system_prompt="사용자 정의 프롬프트")
        result = await use_case.finalize(start_result.session_id, finalize_req, "req-3")
        assert result.system_prompt == "사용자 정의 프롬프트"

    @pytest.mark.asyncio
    async def test_answer_raises_on_invalid_session(self):
        use_case, _, _ = _make_use_case()
        with pytest.raises(ValueError, match="세션"):
            await use_case.answer(
                "non-existent-id",
                InterviewAnswerRequest(answers=["답변"]),
                "req-1",
            )
