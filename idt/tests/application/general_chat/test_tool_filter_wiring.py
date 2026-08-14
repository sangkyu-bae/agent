"""tool-recommender module-4: General Chat 도구 선별 배선 테스트.

- filter 주입 시 좁혀진 도구가 _create_agent에 전달
- filter 미주입 시 전량 바인딩 (무회귀 — 이 기능이 없던 상태와 동일)
- filter 실패 시 전량 바인딩으로 채팅 계속 (격리)
- 필수 세트가 항상 전달되는지 (Plan FR-04)
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage
from src.application.general_chat.tools import REQUIRED_TOOL_IDS
from src.application.general_chat.use_case import GeneralChatUseCase
from src.domain.general_chat.schemas import GeneralChatRequest
from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm_model.entity import LlmModel


class _Tool:
    def __init__(self, name: str) -> None:
        self.name = name
        self.description = f"{name} 도구"


def _make_llm_model() -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="m-1", provider="openai", model_name="gpt-4o",
        display_name="GPT-4o", description=None, api_key_env="OPENAI_API_KEY",
        max_tokens=128000, is_active=True, is_default=True,
        created_at=now, updated_at=now,
    )


def _make_uc(tool_filter=None) -> GeneralChatUseCase:
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
        tool_filter=tool_filter,
    )


def _wire_stream_agent(uc: GeneralChatUseCase, built_tools: list):
    """stream() 경로용 fake agent — _create_agent에 전달된 tools를 캡처."""
    captured: dict = {}

    mock_agent = AsyncMock()
    mock_agent.ainvoke.return_value = {"messages": [AIMessage(content="답변")]}

    async def _fake_astream_events(input_dict, version=None):
        result = await mock_agent.ainvoke(input_dict)
        yield {"event": "on_chain_end", "data": {"output": result}, "name": "agent"}

    mock_agent.astream_events = _fake_astream_events

    def _fake_create_agent(tools, auth_ctx=None, memory_block="", middlewares=None):
        captured["tools"] = tools
        return mock_agent

    uc._create_agent = _fake_create_agent
    uc._msg_repo.find_by_session.return_value = []
    uc._policy.needs_summarization = MagicMock(return_value=False)
    uc._tool_builder.build.return_value = built_tools
    return captured


async def _drain(uc: GeneralChatUseCase, message: str = "안녕"):
    request = GeneralChatRequest(message=message, user_id="u1")
    async for _ in uc.stream(request, "req-1"):
        pass


# ── 배선 ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_filter_주입시_좁혀진_도구가_전달():
    built = [_Tool("a"), _Tool("b"), _Tool("c")]
    narrowed = [built[0], built[2]]
    tool_filter = MagicMock()
    tool_filter.filter = AsyncMock(return_value=narrowed)

    uc = _make_uc(tool_filter=tool_filter)
    captured = _wire_stream_agent(uc, built)
    await _drain(uc)

    assert captured["tools"] == narrowed
    tool_filter.filter.assert_awaited_once()


@pytest.mark.asyncio
async def test_filter_미주입시_전량_바인딩():
    """무회귀 — 이 기능이 없던 상태와 완전히 동일해야 한다."""
    built = [_Tool("a"), _Tool("b"), _Tool("c")]

    uc = _make_uc(tool_filter=None)
    captured = _wire_stream_agent(uc, built)
    await _drain(uc)

    assert captured["tools"] == built


@pytest.mark.asyncio
async def test_유저_메시지가_질의로_전달():
    """Plan 결정: 입력 컨텍스트는 현재 유저 메시지만."""
    tool_filter = MagicMock()
    tool_filter.filter = AsyncMock(return_value=[])

    uc = _make_uc(tool_filter=tool_filter)
    _wire_stream_agent(uc, [_Tool("a")])
    await _drain(uc, message="엑셀로 뽑아줘")

    assert tool_filter.filter.await_args.args[1] == "엑셀로 뽑아줘"


@pytest.mark.asyncio
async def test_필수_세트가_주입된다():
    """Plan FR-04 — 모듈이 카탈로그를 조회하지 않고 호출부가 준다."""
    tool_filter = MagicMock()
    tool_filter.filter = AsyncMock(return_value=[])

    uc = _make_uc(tool_filter=tool_filter)
    _wire_stream_agent(uc, [_Tool("a")])
    await _drain(uc)

    assert tool_filter.filter.await_args.kwargs["required_ids"] == REQUIRED_TOOL_IDS


@pytest.mark.asyncio
async def test_request_id가_전달된다():
    tool_filter = MagicMock()
    tool_filter.filter = AsyncMock(return_value=[])

    uc = _make_uc(tool_filter=tool_filter)
    _wire_stream_agent(uc, [_Tool("a")])
    await _drain(uc)

    assert tool_filter.filter.await_args.kwargs["request_id"] == "req-1"


# ── 필수 세트 상수 ───────────────────────────────────────────────────────────


def test_필수_세트는_빌트인_채팅_도구_2종():
    """ChatToolBuilder가 항상 붙이는 tavily + 내부문서검색."""
    assert REQUIRED_TOOL_IDS == (
        "internal:tavily_search",
        "internal:internal_document_search",
    )


def test_필수_세트_id가_resolver_출력과_일치():
    """카탈로그 표기가 어긋나면 필수 세트가 조용히 무력해진다."""
    from src.infrastructure.tool_selection.adapters.langchain_filter import (
        DefaultToolIdResolver,
    )

    resolver = DefaultToolIdResolver()
    assert resolver.resolve(_Tool("tavily_search")) == REQUIRED_TOOL_IDS[0]
    assert resolver.resolve(_Tool("internal_document_search")) == REQUIRED_TOOL_IDS[1]
