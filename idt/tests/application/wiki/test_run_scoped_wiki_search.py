"""Application 테스트: RunScopedWikiSearch 런타임 어댑터 (LLM-WIKI-001, Step6 와이어링).

기존 hybrid search와 동일한 execute(request, request_id) 시그니처를 유지하면서,
RunContext의 agent_id로 승인 위키를 우선 검색하고, 컨텍스트 없으면 폴백한다.
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_run.context import (
    RunContext,
    reset_run_context,
    set_current_run_context,
)
from src.application.wiki.run_scoped_wiki_search import RunScopedWikiSearch
from src.domain.hybrid_search.schemas import (
    HybridSearchRequest,
    HybridSearchResponse,
    HybridSearchResult,
)
from src.domain.wiki.entity import WikiArticle, WikiSourceType, WikiStatus


def _approved(id="w1") -> WikiArticle:
    return WikiArticle(
        id=id, agent_id="agent_1", title=f"t-{id}", content=f"c-{id}",
        source_type=WikiSourceType.DISTILLED, source_refs=["doc:1"],
        status=WikiStatus.APPROVED, confidence=0.8,
    )


def _fallback(id="f1") -> HybridSearchResult:
    return HybridSearchResult(
        id=id, content=f"orig-{id}", score=0.5, bm25_rank=1, bm25_score=1.0,
        vector_rank=1, vector_score=0.5, source="both", metadata={},
    )


class _SessionCtx:
    def __init__(self, counter): self._counter = counter
    async def __aenter__(self):
        self._counter["opened"] += 1
        return MagicMock()
    async def __aexit__(self, *a):
        self._counter["closed"] += 1
        return False


def _make(inner_results, wiki_hits):
    counter = {"opened": 0, "closed": 0, "repo_built": 0}

    def session_factory():
        return _SessionCtx(counter)

    repo = MagicMock()
    repo.search_similar = AsyncMock(return_value=wiki_hits)

    def repo_builder(session):
        counter["repo_built"] += 1
        return repo

    inner = MagicMock()
    inner.execute = AsyncMock(return_value=HybridSearchResponse(
        query="q", results=inner_results, total_found=len(inner_results), request_id="r"
    ))
    adapter = RunScopedWikiSearch(
        session_factory=session_factory, repo_builder=repo_builder,
        inner_search_getter=lambda: inner, logger=MagicMock(),
    )
    return adapter, inner, repo, counter


def _req(top_k=3):
    return HybridSearchRequest(query="여신", top_k=top_k, collection_name="policy")


def _set_ctx(agent_id="agent_1"):
    return set_current_run_context(RunContext(
        run_id=MagicMock(), user_id="u", agent_id=agent_id, callback=MagicMock(),
    ))


class TestWithAgentContext:

    @pytest.mark.asyncio
    async def test_wiki_first_then_fallback(self):
        adapter, inner, repo, counter = _make([_fallback("f1")], [_approved("w1")])
        token = _set_ctx("agent_1")
        try:
            resp = await adapter.execute(_req(top_k=3), "r")
        finally:
            reset_run_context(token)
        assert [r.id for r in resp.results] == ["w1", "f1"]
        assert resp.results[0].source == "wiki"
        repo.search_similar.assert_awaited_once()
        assert counter["opened"] == 1 and counter["closed"] == 1

    @pytest.mark.asyncio
    async def test_passes_agent_id_to_repo(self):
        adapter, _, repo, _ = _make([], [_approved("w1")])
        token = _set_ctx("agent_42")
        try:
            await adapter.execute(_req(), "r")
        finally:
            reset_run_context(token)
        assert repo.search_similar.await_args.args[0] == "agent_42"


class TestWithoutContext:

    @pytest.mark.asyncio
    async def test_falls_back_to_inner_no_session(self):
        adapter, inner, repo, counter = _make([_fallback("f1")], [_approved("w1")])
        # no run context set
        resp = await adapter.execute(_req(), "r")
        assert [r.id for r in resp.results] == ["f1"]
        inner.execute.assert_awaited_once()
        repo.search_similar.assert_not_awaited()
        assert counter["opened"] == 0  # 세션 안 엶

    @pytest.mark.asyncio
    async def test_empty_agent_id_falls_back(self):
        adapter, inner, repo, counter = _make([_fallback("f1")], [])
        token = _set_ctx("")  # 빈 agent_id
        try:
            resp = await adapter.execute(_req(), "r")
        finally:
            reset_run_context(token)
        assert [r.id for r in resp.results] == ["f1"]
        assert counter["opened"] == 0
