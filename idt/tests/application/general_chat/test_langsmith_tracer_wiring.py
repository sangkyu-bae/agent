"""general_chat 의 per-run LangSmith tracer 배선 — Design §4-2(편차).

`stream()` 은 async generator 이고 그래프 호출(`astream_events`)이 `yield` 를
가로지르므로 `scoped_tracing` 컨텍스트 매니저를 쓸 수 없다 (Design §7-2).
대신 이미 존재하던 `stream_kwargs["config"]["callbacks"]` 에 tracer 를 얹는다
(`run_agent_use_case._build_graph_config` 와 동형).

여기서 고정하는 계약:
  · 키 없음 → tracer 없음 → callbacks 에 아무것도 더해지지 않는다(기존 동작)
  · 키 있음 → tracer 가 callbacks **선두**에 붙고, 기존 callback 은 뒤따른다
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tracers import LangChainTracer

from src.application.general_chat.use_case import GeneralChatUseCase
from src.domain.general_chat.schemas import GeneralChatRequest
from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm_model.entity import LlmModel

_DUMMY_KEY = "lsv2_dummy_key_for_test"


def _make_llm_model() -> LlmModel:
    return LlmModel(
        id="model-1", provider="openai", model_name="gpt-4o",
        display_name="GPT-4o", description=None, api_key_env="OPENAI_API_KEY",
        max_tokens=128000, is_active=True, is_default=True,
        created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1),
    )


def _make_use_case() -> tuple[GeneralChatUseCase, dict]:
    """협력자 최소 구성 + astream_events 호출 kwargs 캡처."""
    seen: dict = {}

    async def _fake_astream_events(input_dict, version=None, config=None):
        seen["config"] = config
        yield {
            "event": "on_chain_end",
            "data": {"output": {"messages": [AIMessage(content="답변")]}},
            "name": "agent",
        }

    mock_agent = MagicMock()
    mock_agent.astream_events = _fake_astream_events

    tool_builder = AsyncMock()
    tool_builder.build.return_value = []

    msg_repo = AsyncMock()
    msg_repo.find_by_session.return_value = []

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
        llm_model=_make_llm_model(),
    )
    uc._create_agent = MagicMock(return_value=mock_agent)
    return uc, seen


async def _run(uc: GeneralChatUseCase) -> None:
    req = GeneralChatRequest(user_id="u1", session_id="s1", message="질문")
    async for _ in uc.stream(req, request_id="req-1"):
        pass


class TestTracerWiring:
    async def test_no_config_without_key(self) -> None:
        """키가 없으면 기존과 동일하게 config 를 넘기지 않는다."""
        uc, seen = _make_use_case()
        await _run(uc)
        assert seen["config"] is None

    async def test_tracer_attached_with_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LANGCHAIN_API_KEY", _DUMMY_KEY)
        uc, seen = _make_use_case()
        await _run(uc)

        callbacks = (seen["config"] or {}).get("callbacks", [])
        tracers = [cb for cb in callbacks if isinstance(cb, LangChainTracer)]
        assert len(tracers) == 1

    async def test_tracer_uses_general_chat_project(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """FR-06 — 전역 `langsmith()` 가 쓰던 프로젝트명을 승계한다."""
        monkeypatch.setenv("LANGCHAIN_API_KEY", _DUMMY_KEY)
        uc, seen = _make_use_case()
        await _run(uc)

        tracer = seen["config"]["callbacks"][0]
        assert tracer.project_name == "general-chat"


class TestGlobalEnvUntouched:
    """FR-06 — 스트림이 돌아도 전역 추적 환경변수를 건드리지 않는다."""

    async def test_env_unchanged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import os

        monkeypatch.setenv("LANGCHAIN_API_KEY", _DUMMY_KEY)
        uc, _ = _make_use_case()
        await _run(uc)

        assert os.environ.get("LANGSMITH_TRACING") is None
        assert os.environ.get("LANGSMITH_PROJECT") is None
