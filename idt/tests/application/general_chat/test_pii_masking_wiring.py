"""pii-masking-integration module-4 — GeneralChatUseCase 배선 테스트.

Design Ref: §2.1 (FR-03), §4.5 (FR-09). 일반 채팅은 STEP_REASONING 이 내부 모델의
on_chat_model_end 원문(마스킹된 텍스트)을 그대로 보내므로 이것도 원복해야 한다.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import AIMessage, HumanMessage
from src.application.general_chat.use_case import GeneralChatUseCase
from src.application.pii_masking.middleware import PiiMaskingMiddleware
from src.domain.general_chat.schemas import GeneralChatRequest
from src.domain.general_chat.value_objects import ChatEventType
from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm_model.entity import LlmModel

from tests.application.pii_masking._support import make_masker

PHONE = "010-1234-5678"


def _llm_model() -> LlmModel:
    return LlmModel(
        id="t",
        provider="openai",
        model_name="gpt-4o",
        display_name="x",
        description=None,
        api_key_env="OPENAI_API_KEY",
        max_tokens=1000,
        is_active=True,
        is_default=True,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )


def _chunk(text: str):
    chunk = MagicMock()
    chunk.content = text
    return chunk


def _make_uc(masker=None, chunks=("[PH", "ONE_1]", " 로 안내")):
    tool_builder = AsyncMock()
    tool_builder.build.return_value = []
    msg_repo = AsyncMock()
    msg_repo.find_by_session.return_value = []
    msg_repo.save.return_value = MagicMock()
    policy = MagicMock()
    policy.needs_summarization = MagicMock(return_value=False)
    llm_factory = MagicMock(spec=LLMFactoryInterface)
    llm_factory.create.return_value = MagicMock()
    uc = GeneralChatUseCase(
        chat_tool_builder=tool_builder,
        message_repo=msg_repo,
        summary_repo=AsyncMock(),
        summarizer=AsyncMock(),
        summarization_policy=policy,
        logger=MagicMock(),
        llm_factory=llm_factory,
        llm_model=_llm_model(),
        pii_masker=masker,
    )
    captured: dict = {}

    def _create_agent(tools, auth_ctx=None, memory_block="", middlewares=None):
        captured["middlewares"] = middlewares
        pii = [m for m in middlewares or [] if isinstance(m, PiiMaskingMiddleware)]
        if pii and masker is not None:
            masker.mask_messages([HumanMessage(content=PHONE)], pii[0].scope)
        agent = MagicMock()

        async def _events(input_dict, **kwargs):
            for text in chunks:
                yield {
                    "event": "on_chat_model_stream",
                    "run_id": "llm-1",
                    "data": {"chunk": _chunk(text)},
                }
            yield {
                "event": "on_chat_model_end",
                "run_id": "llm-1",
                "data": {
                    "output": AIMessage(
                        content="[PHONE_1] 로 조회합니다",
                        tool_calls=[{"name": "lookup", "args": {}, "id": "c1"}],
                    )
                },
            }
            yield {
                "event": "on_chain_end",
                "name": "agent",
                "data": {
                    "output": {"messages": [AIMessage(content=f"{PHONE} 로 안내")]}
                },
            }

        agent.astream_events = _events
        return agent

    uc._create_agent = _create_agent
    return uc, captured


async def _events(uc) -> list:
    req = GeneralChatRequest(user_id="u1", session_id="s1", message="안내해줘")
    return [ev async for ev in uc.stream(req, request_id="r1")]


def _tokens(events) -> list[str]:
    return [e.payload["chunk"] for e in events if e.event_type == ChatEventType.TOKEN]


async def test_pii_middleware_first_in_chain():
    uc, captured = _make_uc(make_masker())
    await _events(uc)
    assert isinstance(captured["middlewares"][0], PiiMaskingMiddleware)


async def test_without_masker_no_pii_middleware():
    uc, captured = _make_uc()
    await _events(uc)
    assert not any(
        isinstance(m, PiiMaskingMiddleware) for m in captured["middlewares"] or []
    )


async def test_tokens_restored_without_fragments():
    uc, _ = _make_uc(make_masker())
    tokens = _tokens(await _events(uc))
    assert "".join(tokens) == f"{PHONE} 로 안내"
    assert not any("[" in t or "PH" in t for t in tokens)


async def test_pending_tail_flushed_at_model_end():
    uc, _ = _make_uc(make_masker(), chunks=("끝 [PHO",))
    assert _tokens(await _events(uc)) == ["끝 ", "[PHO"]


async def test_step_reasoning_restored():
    uc, _ = _make_uc(make_masker())
    events = await _events(uc)
    reasoning = [
        e.payload["reasoning"]
        for e in events
        if e.event_type == ChatEventType.STEP_REASONING
    ]
    assert reasoning == [f"{PHONE} 로 조회합니다"]


async def test_without_masker_tokens_and_reasoning_unchanged():
    uc, _ = _make_uc()
    events = await _events(uc)
    assert _tokens(events) == ["[PH", "ONE_1]", " 로 안내"]
    reasoning = [
        e.payload["reasoning"]
        for e in events
        if e.event_type == ChatEventType.STEP_REASONING
    ]
    assert reasoning == ["[PHONE_1] 로 조회합니다"]


def _summaries(logger) -> list[str]:
    return [
        c.kwargs["summary"]
        for c in logger.info.call_args_list
        if c.args and c.args[0] == "PII masking summary"
    ]


async def test_summary_logged_at_stream_end():
    # Check G-2 — shadow 집계가 일반 채팅도 포함하도록 런 요약을 남긴다.
    uc, _ = _make_uc(make_masker())
    await _events(uc)
    assert _summaries(uc._logger) == ["mode=on phone=1"]


async def test_no_summary_without_masker():
    uc, _ = _make_uc()
    await _events(uc)
    assert _summaries(uc._logger) == []


def test_class_default_masker_is_none_for_new_fixtures():
    assert GeneralChatUseCase.__new__(GeneralChatUseCase)._pii_masker is None
