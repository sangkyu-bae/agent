"""RunAgentRequest 모델/temperature 오버라이드 + 대화 저장 생략 검증.

Design Ref: D1 — 오버라이드 해석은 _prepare_graph 단일 지점.
Design Ref: D2 — 평가 실행은 conversation_message를 남기지 않는다.
Design Ref: Plan FR-02 — 오버라이드된 모델이 ai_run.llm_model_id에 반영되어야
                          비용 집계가 올바른 모델에 귀속된다.
Plan NFR(하위호환): 오버라이드 미지정 시 기존 동작이 1바이트도 바뀌지 않는다.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.run_agent_use_case import RunAgentUseCase
from src.application.agent_builder.schemas import RunAgentRequest
from src.application.agent_run.tracker import RunTracker
from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition
from src.domain.conversation.policies import SummarizationPolicy
from src.domain.llm_model.entity import LlmModel

AGENT_MODEL_ID = "model-agent"
OVERRIDE_MODEL_ID = "model-override"
AGENT_TEMPERATURE = 0.70


def _make_llm_model(model_id: str) -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id=model_id,
        provider="openai",
        model_name=f"name-of-{model_id}",
        display_name=model_id,
        description=None,
        api_key_env="OPENAI_API_KEY",
        max_tokens=128000,
        is_active=True,
        is_default=False,
        created_at=now,
        updated_at=now,
    )


def _make_agent() -> AgentDefinition:
    now = datetime.now(timezone.utc)
    return AgentDefinition(
        id=str(uuid.uuid4()),
        user_id="user-1",
        name="테스트 에이전트",
        description="설명",
        system_prompt="시스템 프롬프트",
        flow_hint="힌트",
        workers=[WorkerDefinition("tavily_search", "search_worker", "검색", 0)],
        llm_model_id=AGENT_MODEL_ID,
        status="active",
        temperature=AGENT_TEMPERATURE,
        created_at=now,
        updated_at=now,
    )


def _make_use_case():
    repository = MagicMock()
    llm_model_repository = MagicMock()
    compiler = MagicMock()
    message_repo = MagicMock()
    summary_repo = MagicMock()
    summarizer = MagicMock()
    tracker = MagicMock(spec=RunTracker)
    tracker.start_run = AsyncMock()
    tracker.complete_run = AsyncMock()
    tracker.fail_run = AsyncMock()

    agent = _make_agent()
    repository.find_by_id = AsyncMock(return_value=agent)
    # 요청된 model_id를 그대로 돌려준다 — 어떤 id로 조회했는지 추적 가능.
    llm_model_repository.find_by_id = AsyncMock(
        side_effect=lambda model_id, request_id: _make_llm_model(model_id)
    )

    message_repo.find_by_session = AsyncMock(return_value=[])
    saved_msg = MagicMock()
    saved_msg.id.value = 42
    message_repo.save = AsyncMock(return_value=saved_msg)
    summary_repo.find_latest_by_session = AsyncMock(return_value=None)
    summary_repo.save = AsyncMock()
    summarizer.summarize = AsyncMock(return_value="요약")

    mock_graph = MagicMock()
    last_msg = MagicMock()
    last_msg.content = "응답입니다"
    last_msg.name = None
    mock_graph.ainvoke = AsyncMock(return_value={"messages": [last_msg]})

    def _astream_side_effect(*args, **kwargs):
        async def _gen():
            result = await mock_graph.ainvoke(*args, **kwargs)
            yield {
                "event": "on_chain_end",
                "name": "LangGraph",
                "data": {"output": {"messages": result.get("messages", [])}},
                "metadata": {},
                "run_id": "top",
            }
        return _gen()

    mock_graph.astream_events = MagicMock(side_effect=_astream_side_effect)
    compiler.compile = AsyncMock(return_value=mock_graph)

    use_case = RunAgentUseCase(
        repository=repository,
        llm_model_repository=llm_model_repository,
        compiler=compiler,
        logger=MagicMock(),
        message_repo=message_repo,
        summary_repo=summary_repo,
        summarizer=summarizer,
        policy=SummarizationPolicy(),
        tracker=tracker,
    )
    return use_case, agent, {
        "llm_model_repo": llm_model_repository,
        "compiler": compiler,
        "tracker": tracker,
        "message_repo": message_repo,
    }


def _compile_kwargs(mocks) -> dict:
    return mocks["compiler"].compile.await_args.kwargs


class TestRequestDefaults:
    """오버라이드 필드는 전부 선택 — 기존 호출자는 아무것도 바꾸지 않는다."""

    def test_new_fields_default_to_passthrough(self):
        request = RunAgentRequest(query="q", user_id="u")

        assert request.llm_model_id_override is None
        assert request.temperature_override is None
        assert request.persist_conversation is True


class TestBackwardCompatibility:
    """Plan NFR — 오버라이드 미지정 경로는 기존과 동일해야 한다."""

    @pytest.mark.asyncio
    async def test_uses_agent_model_and_temperature(self):
        use_case, agent, mocks = _make_use_case()

        await use_case.execute(agent.id, RunAgentRequest(query="q", user_id="u"), "req-1")

        mocks["llm_model_repo"].find_by_id.assert_awaited_once_with(
            AGENT_MODEL_ID, "req-1"
        )
        assert _compile_kwargs(mocks)["temperature"] == AGENT_TEMPERATURE

    @pytest.mark.asyncio
    async def test_observability_records_agent_model(self):
        use_case, agent, mocks = _make_use_case()

        await use_case.execute(agent.id, RunAgentRequest(query="q", user_id="u"), "req-1")

        kwargs = mocks["tracker"].start_run.await_args.kwargs
        assert kwargs["agent_llm_model_id"] == AGENT_MODEL_ID

    @pytest.mark.asyncio
    async def test_conversation_is_persisted_by_default(self):
        use_case, agent, mocks = _make_use_case()

        await use_case.execute(agent.id, RunAgentRequest(query="q", user_id="u"), "req-1")

        # user message + assistant message
        assert mocks["message_repo"].save.await_count == 2


class TestModelOverride:
    @pytest.mark.asyncio
    async def test_loads_overridden_model_instead_of_agent_model(self):
        use_case, agent, mocks = _make_use_case()

        await use_case.execute(
            agent.id,
            RunAgentRequest(
                query="q", user_id="u", llm_model_id_override=OVERRIDE_MODEL_ID
            ),
            "req-1",
        )

        mocks["llm_model_repo"].find_by_id.assert_awaited_once_with(
            OVERRIDE_MODEL_ID, "req-1"
        )
        assert _compile_kwargs(mocks)["llm_model"].id == OVERRIDE_MODEL_ID

    @pytest.mark.asyncio
    async def test_observability_records_effective_model_not_agent_model(self):
        """Plan FR-02 — ai_run.llm_model_id가 원본 모델로 찍히면 스윕의 비용·토큰
        집계가 전부 엉뚱한 모델에 귀속된다. 매트릭스가 통째로 틀어지는 지점."""
        use_case, agent, mocks = _make_use_case()

        await use_case.execute(
            agent.id,
            RunAgentRequest(
                query="q", user_id="u", llm_model_id_override=OVERRIDE_MODEL_ID
            ),
            "req-1",
        )

        kwargs = mocks["tracker"].start_run.await_args.kwargs
        assert kwargs["agent_llm_model_id"] == OVERRIDE_MODEL_ID

    @pytest.mark.asyncio
    async def test_agent_definition_is_not_mutated(self):
        """D1 — 오버라이드는 요청 범위다. 에이전트 정의는 건드리지 않는다."""
        use_case, agent, _ = _make_use_case()

        await use_case.execute(
            agent.id,
            RunAgentRequest(
                query="q",
                user_id="u",
                llm_model_id_override=OVERRIDE_MODEL_ID,
                temperature_override=0.0,
            ),
            "req-1",
        )

        assert agent.llm_model_id == AGENT_MODEL_ID
        assert agent.temperature == AGENT_TEMPERATURE


class TestTemperatureOverride:
    @pytest.mark.asyncio
    async def test_zero_override_is_honoured(self):
        """D9의 핵심 — 0.0은 falsy다. `or`로 구현하면 에이전트 값(0.70)으로
        새어 재현성이 깨진다. 반드시 `is not None` 판정이어야 한다."""
        use_case, agent, mocks = _make_use_case()

        await use_case.execute(
            agent.id,
            RunAgentRequest(query="q", user_id="u", temperature_override=0.0),
            "req-1",
        )

        assert _compile_kwargs(mocks)["temperature"] == 0.0

    @pytest.mark.asyncio
    async def test_nonzero_override_is_honoured(self):
        use_case, agent, mocks = _make_use_case()

        await use_case.execute(
            agent.id,
            RunAgentRequest(query="q", user_id="u", temperature_override=1.5),
            "req-1",
        )

        assert _compile_kwargs(mocks)["temperature"] == 1.5


class TestPersistConversation:
    @pytest.mark.asyncio
    async def test_disabled_saves_no_messages(self):
        """D2 — 스윕은 세션 100개를 만든다. 평가 실행은 이력을 남기지 않는다."""
        use_case, agent, mocks = _make_use_case()

        await use_case.execute(
            agent.id,
            RunAgentRequest(query="q", user_id="u", persist_conversation=False),
            "req-1",
        )

        mocks["message_repo"].save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_disabled_still_returns_answer(self):
        use_case, agent, _ = _make_use_case()

        result = await use_case.execute(
            agent.id,
            RunAgentRequest(query="q", user_id="u", persist_conversation=False),
            "req-1",
        )

        assert result.answer == "응답입니다"

    @pytest.mark.asyncio
    async def test_disabled_keeps_observability_with_null_message_id(self):
        """관측은 계속 남아야 비용·지연을 회수할 수 있다(D10).
        user_message_id는 nullable(V021)이라 None으로 두어도 안전하다."""
        use_case, agent, mocks = _make_use_case()

        await use_case.execute(
            agent.id,
            RunAgentRequest(query="q", user_id="u", persist_conversation=False),
            "req-1",
        )

        mocks["tracker"].start_run.assert_awaited_once()
        assert mocks["tracker"].start_run.await_args.kwargs["user_message_id"] is None


class TestSweepCombination:
    @pytest.mark.asyncio
    async def test_full_sweep_request_shape(self):
        """스윕 실행기가 실제로 보내는 조합 (Design §2.2)."""
        use_case, agent, mocks = _make_use_case()

        await use_case.execute(
            agent.id,
            RunAgentRequest(
                query="q",
                user_id="u",
                llm_model_id_override=OVERRIDE_MODEL_ID,
                temperature_override=0.0,
                persist_conversation=False,
            ),
            "req-1",
        )

        assert _compile_kwargs(mocks)["llm_model"].id == OVERRIDE_MODEL_ID
        assert _compile_kwargs(mocks)["temperature"] == 0.0
        mocks["message_repo"].save.assert_not_awaited()
        assert (
            mocks["tracker"].start_run.await_args.kwargs["agent_llm_model_id"]
            == OVERRIDE_MODEL_ID
        )
