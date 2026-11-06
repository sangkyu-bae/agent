"""대화 요약기·대화 LLM의 llm_guard 주입 — pii-masking-integration §11.1 (FR-06)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.infrastructure.conversation.langchain_llm import LangChainConversationLLM
from src.infrastructure.conversation.langchain_summarizer import LangChainSummarizer


class _Wrapped:
    def __init__(self, inner) -> None:
        self.inner = inner
        self.ainvoke = AsyncMock(return_value=MagicMock(content="ok"))


@pytest.mark.parametrize("cls", [LangChainSummarizer, LangChainConversationLLM])
def test_guard_applied_to_internal_model(cls):
    seen = []

    def guard(llm):
        seen.append(llm)
        return _Wrapped(llm)

    adapter = cls(
        model_name="gpt-4o-mini", api_key="sk-test", logger=MagicMock(), llm_guard=guard
    )
    assert isinstance(adapter._llm, _Wrapped)
    assert adapter._llm.inner is seen[0]


@pytest.mark.parametrize("cls", [LangChainSummarizer, LangChainConversationLLM])
def test_without_guard_model_unchanged(cls):
    adapter = cls(model_name="gpt-4o-mini", api_key="sk-test", logger=MagicMock())
    assert type(adapter._llm).__name__ == "ChatOpenAI"


async def test_summarizer_calls_guarded_model():
    adapter = LangChainSummarizer(
        model_name="gpt-4o-mini",
        api_key="sk-test",
        logger=MagicMock(),
        llm_guard=_Wrapped,
    )
    message = MagicMock()
    message.role.value = "user"
    message.content = "010-1234-5678"
    assert await adapter.summarize([message], "r1") == "ok"
    adapter._llm.ainvoke.assert_awaited_once()
