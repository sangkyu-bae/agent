"""PlatformStructuredExtractor — 보조 LLM 재구조화 (design §4 ③, DD8)."""

from __future__ import annotations

from unittest.mock import MagicMock

from pydantic import BaseModel
from src.infrastructure.market_analysis.adapters.structured import (
    PlatformStructuredExtractor,
)


class Verdict(BaseModel):
    score: int
    decision: str


class FakeProvider:
    def __init__(self, llm):
        self.llm = llm

    async def get(self, temperature: float = 0.0):
        return self.llm


class FakeCaller:
    def __init__(self, result=None, fail: Exception | None = None):
        self.result = result
        self.fail = fail
        self.messages = None

    async def call(self, messages, schema):
        self.messages = messages
        if self.fail:
            raise self.fail
        return self.result, "json_schema", None


def _extractor(llm="llm", caller=None):
    caller = caller or FakeCaller(Verdict(score=7, decision="enter"))
    return PlatformStructuredExtractor(
        provider=FakeProvider(llm),
        caller_factory=lambda llm: caller,
        logger=MagicMock(),
    ), caller


async def test_extracts_with_utility_llm():
    ex, caller = _extractor()
    out = await ex.extract(text="점수 7, 진입", schema=Verdict, request_id="r")
    assert out == Verdict(score=7, decision="enter")
    assert "점수 7, 진입" in str(caller.messages)


async def test_no_utility_llm_returns_none():
    ex, _ = _extractor(llm=None)
    assert await ex.extract(text="x", schema=Verdict, request_id="r") is None


async def test_caller_failure_returns_none():
    ex, _ = _extractor(caller=FakeCaller(fail=RuntimeError("all modes failed")))
    assert await ex.extract(text="x", schema=Verdict, request_id="r") is None


async def test_text_is_bounded():
    ex, caller = _extractor()
    await ex.extract(text="y" * 50_000, schema=Verdict, request_id="r")
    assert len(str(caller.messages)) < 30_000
