"""builtin-middleware D7: General Chat 미들웨어 배선 테스트.

- provider 주입 시 prepare(None) → instantiate 결과가 _create_agent에 전달
- provider 미주입 시 미들웨어 없이 동작 (무회귀)
- prepare 실패 시 미들웨어 없이 채팅 계속 (격리)
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage

from src.application.general_chat.use_case import GeneralChatUseCase
from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm_model.entity import LlmModel
from src.domain.general_chat.schemas import GeneralChatRequest


def _make_llm_model() -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="m-1", provider="openai", model_name="gpt-4o",
        display_name="GPT-4o", description=None, api_key_env="OPENAI_API_KEY",
        max_tokens=128000, is_active=True, is_default=True,
        created_at=now, updated_at=now,
    )


def _make_uc(middleware_provider=None) -> GeneralChatUseCase:
    mock_llm_factory = MagicMock(spec=LLMFactoryInterface)
    mock_llm_factory.create.return_value = MagicMock()
    return GeneralChatUseCase(
        chat_tool_builder=AsyncMock(),
        message_repo=AsyncMock(),
        summary_repo=AsyncMock(),
        summarizer=AsyncMock(),
        summarization_policy=MagicMock(),
        logger=MagicMock(),
        llm_factory=mock_llm_factory,
        llm_model=_make_llm_model(),
        middleware_provider=middleware_provider,
    )


def _wire_stream_agent(uc: GeneralChatUseCase):
    """stream() 경로용 fake agent — 전달된 middlewares를 캡처."""
    captured: dict = {}

    mock_agent = AsyncMock()
    mock_agent.ainvoke.return_value = {"messages": [AIMessage(content="답변")]}

    async def _fake_astream_events(input_dict, version=None):
        result = await mock_agent.ainvoke(input_dict)
        yield {"event": "on_chain_end", "data": {"output": result}, "name": "agent"}

    mock_agent.astream_events = _fake_astream_events

    def _fake_create_agent(tools, auth_ctx=None, memory_block="", middlewares=None):
        captured["middlewares"] = middlewares
        return mock_agent

    uc._create_agent = _fake_create_agent
    uc._msg_repo.find_by_session.return_value = []
    uc._policy.needs_summarization = MagicMock(return_value=False)
    uc._tool_builder.build.return_value = []
    return captured


async def _drain(uc: GeneralChatUseCase):
    request = GeneralChatRequest(message="안녕", user_id="u1")
    async for _ in uc.stream(request, "req-1"):
        pass


@pytest.mark.asyncio
async def test_provider_주입시_instantiate_결과가_전달():
    instance = MagicMock()
    plan = MagicMock()
    plan.instantiate = MagicMock(return_value=[instance])
    provider = MagicMock()
    provider.prepare = AsyncMock(return_value=plan)

    uc = _make_uc(middleware_provider=provider)
    captured = _wire_stream_agent(uc)
    await _drain(uc)

    provider.prepare.assert_awaited_once()
    assert provider.prepare.await_args.args[0] is None  # General Chat = agent_id None
    assert captured["middlewares"] == [instance]


@pytest.mark.asyncio
async def test_provider_미주입시_미들웨어_없음():
    uc = _make_uc(middleware_provider=None)
    captured = _wire_stream_agent(uc)
    await _drain(uc)
    assert captured["middlewares"] == []


@pytest.mark.asyncio
async def test_prepare_실패시_미들웨어_없이_계속():
    provider = MagicMock()
    provider.prepare = AsyncMock(side_effect=RuntimeError("DB down"))

    uc = _make_uc(middleware_provider=provider)
    captured = _wire_stream_agent(uc)
    await _drain(uc)  # 예외 전파 없이 완료

    assert captured["middlewares"] == []
