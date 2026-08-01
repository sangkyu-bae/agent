"""Infrastructure 테스트: FolderSummaryDistiller (wiki-folder-summaries D3).

계층 증류 — 직속 문서 스니펫 + 하위 폴더 요약을 입력으로 폴더 안내 설명을 생성.
입력 상한(문서당 500자 / 총 20,000자)을 조립 단계에서 고정한다.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.infrastructure.wiki.folder_summary_distiller import (
    _DOC_SNIPPET_MAX,
    _TOTAL_INPUT_MAX,
    FolderSummaryDistiller,
)


def _llm(reply="폴더 설명입니다."):
    llm = MagicMock()
    response = MagicMock()
    response.content = reply
    llm.ainvoke = AsyncMock(return_value=response)
    return llm


class TestFolderSummaryDistiller:

    @pytest.mark.asyncio
    async def test_returns_llm_text(self):
        d = FolderSummaryDistiller(llm=_llm("여신 한도 지식 폴더"), logger=MagicMock())
        out = await d.summarize_folder(
            "여신/한도", ["제목A: 본문A"], ["하위 요약"], "r"
        )
        assert out == "여신 한도 지식 폴더"

    @pytest.mark.asyncio
    async def test_input_includes_docs_and_child_summaries(self):
        llm = _llm()
        d = FolderSummaryDistiller(llm=llm, logger=MagicMock())
        await d.summarize_folder("여신", ["제목A: 본문A"], ["하위폴더 요약B"], "r")
        human = llm.ainvoke.await_args.args[0][1].content
        assert "제목A: 본문A" in human
        assert "하위폴더 요약B" in human
        assert "여신" in human

    @pytest.mark.asyncio
    async def test_doc_snippet_truncated_to_cap(self):
        llm = _llm()
        d = FolderSummaryDistiller(llm=llm, logger=MagicMock())
        await d.summarize_folder("여신", ["x" * (_DOC_SNIPPET_MAX + 500)], [], "r")
        human = llm.ainvoke.await_args.args[0][1].content
        assert "x" * _DOC_SNIPPET_MAX in human
        assert "x" * (_DOC_SNIPPET_MAX + 1) not in human

    @pytest.mark.asyncio
    async def test_total_input_truncated(self):
        llm = _llm()
        d = FolderSummaryDistiller(llm=llm, logger=MagicMock())
        docs = ["y" * _DOC_SNIPPET_MAX for _ in range(100)]  # 500*100 > 20000
        await d.summarize_folder("여신", docs, [], "r")
        human = llm.ainvoke.await_args.args[0][1].content
        assert len(human) <= _TOTAL_INPUT_MAX + 200  # 헤더 여유

    @pytest.mark.asyncio
    async def test_block_list_content_coerced(self):
        """LLM content가 블록 리스트여도 문자열로 정규화 (기존 교훈 재사용)."""
        llm = _llm()
        llm.ainvoke.return_value.content = [{"text": "블록 "}, {"text": "요약"}]
        d = FolderSummaryDistiller(llm=llm, logger=MagicMock())
        out = await d.summarize_folder("여신", ["t: c"], [], "r")
        assert out == "블록 요약"
