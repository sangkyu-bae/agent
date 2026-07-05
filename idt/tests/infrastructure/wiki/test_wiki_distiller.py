"""Infrastructure 테스트: WikiDistiller (LLM 주입, LLM-WIKI-001 Phase 1/B)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.wiki.schemas import WikiSourceGroup
from src.infrastructure.wiki.wiki_distiller import WikiDistiller


def _llm(content="정제된 요약 본문"):
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=SimpleNamespace(content=content))
    return llm


def _distiller(llm=None):
    return WikiDistiller(llm=llm or _llm(), logger=MagicMock())


class TestDistill:

    @pytest.mark.asyncio
    async def test_returns_llm_content_as_body(self):
        d = _distiller(_llm("여신 한도는 ..."))
        group = WikiSourceGroup(topic_hint="여신 한도", texts=["원문A", "원문B"], refs=["d:1"])
        result = await d.distill(group, "r")
        assert result.content == "여신 한도는 ..."

    @pytest.mark.asyncio
    async def test_title_from_topic_hint(self):
        d = _distiller()
        group = WikiSourceGroup(topic_hint="정책 자금 금리", texts=["t"], refs=["d:1"])
        result = await d.distill(group, "r")
        assert result.title == "정책 자금 금리"

    @pytest.mark.asyncio
    async def test_title_derived_when_no_hint(self):
        d = _distiller(_llm("첫 문장 요약입니다. 두번째."))
        group = WikiSourceGroup(topic_hint=None, texts=["t"], refs=["d:1"])
        result = await d.distill(group, "r")
        assert result.title  # 비어있지 않은 제목 파생
        assert len(result.title) <= 200

    @pytest.mark.asyncio
    async def test_coerces_block_list_content(self):
        # chunk.content가 블록 리스트로 올 때 문자열로 정규화 (메모리 노트)
        blocks = [{"type": "text", "text": "정규화된"}, {"type": "text", "text": " 본문"}]
        d = _distiller(_llm(blocks))
        group = WikiSourceGroup(topic_hint="t", texts=["x"], refs=["d:1"])
        result = await d.distill(group, "r")
        assert result.content == "정규화된 본문"
