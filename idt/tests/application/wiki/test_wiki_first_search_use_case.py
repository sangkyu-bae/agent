"""Application 테스트: WikiFirstSearchUseCase (LLM-WIKI-001, Phase 1/B 검색 확장).

승인된 위키 항목을 우선 노출하고, 부족분만 기존 하이브리드 검색으로 폴백한다.
기존 HybridSearchUseCase는 수정하지 않고 래핑한다.
"""
from datetime import datetime

import pytest

from src.application.wiki.wiki_first_search_use_case import WikiFirstSearchUseCase
from src.domain.hybrid_search.schemas import (
    HybridSearchRequest,
    HybridSearchResponse,
    HybridSearchResult,
)
from src.domain.wiki.entity import WikiArticle, WikiSourceType, WikiStatus

NOW = datetime(2026, 6, 28)


def _wiki(id="w1", confidence=0.8) -> WikiArticle:
    return WikiArticle(
        id=id, agent_id="agent_1", title=f"제목-{id}", content=f"본문-{id}",
        source_type=WikiSourceType.DISTILLED, source_refs=["doc:1"],
        status=WikiStatus.APPROVED, confidence=confidence,
    )


def _fallback_result(id) -> HybridSearchResult:
    return HybridSearchResult(
        id=id, content=f"orig-{id}", score=0.5,
        bm25_rank=1, bm25_score=1.0, vector_rank=1, vector_score=0.5,
        source="both", metadata={},
    )


class _FakeWikiRepo:
    def __init__(self, hits: list[WikiArticle]) -> None:
        self._hits = hits
        self.called = False

    async def search_similar(self, agent_id, query, top_k, now, request_id):
        self.called = True
        return self._hits[:top_k]


class _FakeInner:
    """HybridSearchUseCase 대역."""

    def __init__(self, results: list[HybridSearchResult]) -> None:
        self._results = results
        self.called = False

    async def execute(self, request, request_id) -> HybridSearchResponse:
        self.called = True
        return HybridSearchResponse(
            query=request.query, results=self._results,
            total_found=len(self._results), request_id=request_id,
        )


def _uc(wiki_hits, fallback_results):
    repo = _FakeWikiRepo(wiki_hits)
    inner = _FakeInner(fallback_results)
    uc = WikiFirstSearchUseCase(wiki_repo=repo, inner_search=inner)
    return uc, repo, inner


def _req(top_k=3):
    return HybridSearchRequest(query="여신 한도", top_k=top_k, collection_name="policy")


class TestWikiFirst:

    @pytest.mark.asyncio
    async def test_wiki_results_marked_source_wiki(self):
        uc, _, _ = _uc([_wiki("w1")], [])
        resp = await uc.execute(_req(), agent_id="agent_1", now=NOW, request_id="r")
        assert resp.results[0].source == "wiki"
        assert resp.results[0].id == "w1"
        assert resp.results[0].metadata["title"] == "제목-w1"

    @pytest.mark.asyncio
    async def test_score_from_confidence(self):
        uc, _, _ = _uc([_wiki("w1", confidence=0.9)], [])
        resp = await uc.execute(_req(), "agent_1", NOW, "r")
        assert resp.results[0].score == 0.9

    @pytest.mark.asyncio
    async def test_enough_wiki_skips_fallback(self):
        uc, _, inner = _uc([_wiki("w1"), _wiki("w2"), _wiki("w3")], [_fallback_result("f1")])
        resp = await uc.execute(_req(top_k=3), "agent_1", NOW, "r")
        assert len(resp.results) == 3
        assert inner.called is False  # 위키로 충분 → 비용 절감

    @pytest.mark.asyncio
    async def test_empty_wiki_falls_back(self):
        uc, _, inner = _uc([], [_fallback_result("f1"), _fallback_result("f2")])
        resp = await uc.execute(_req(), "agent_1", NOW, "r")
        assert inner.called is True
        assert [r.id for r in resp.results] == ["f1", "f2"]

    @pytest.mark.asyncio
    async def test_partial_wiki_then_fallback_order(self):
        uc, _, inner = _uc([_wiki("w1")], [_fallback_result("f1"), _fallback_result("f2")])
        resp = await uc.execute(_req(top_k=3), "agent_1", NOW, "r")
        assert inner.called is True
        assert [r.id for r in resp.results] == ["w1", "f1", "f2"]  # 위키 우선

    @pytest.mark.asyncio
    async def test_dedup_keeps_wiki(self):
        uc, _, _ = _uc([_wiki("dup")], [_fallback_result("dup"), _fallback_result("f2")])
        resp = await uc.execute(_req(top_k=3), "agent_1", NOW, "r")
        ids = [r.id for r in resp.results]
        assert ids == ["dup", "f2"]  # 중복 id는 위키 것만 유지
        assert resp.results[0].source == "wiki"

    @pytest.mark.asyncio
    async def test_truncates_to_top_k(self):
        uc, _, _ = _uc([_wiki("w1")], [_fallback_result("f1"), _fallback_result("f2")])
        resp = await uc.execute(_req(top_k=2), "agent_1", NOW, "r")
        assert len(resp.results) == 2
        assert [r.id for r in resp.results] == ["w1", "f1"]
