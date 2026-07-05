"""Infrastructure 테스트: ElasticsearchWikiSourceProvider (LLM-WIKI-001 Phase 1/B)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.elasticsearch.schemas import ESSearchResult
from src.infrastructure.wiki.wiki_source_provider import ElasticsearchWikiSourceProvider


def _hit(id, source_key, content) -> ESSearchResult:
    return ESSearchResult(
        id=id, score=1.0, index="policy",
        source={"content": content, "source": source_key},
    )


def _provider(results, group_field="source"):
    es = MagicMock()
    es.search = AsyncMock(return_value=results)
    prov = ElasticsearchWikiSourceProvider(
        es_repo=es, logger=MagicMock(), group_field=group_field
    )
    return prov, es


class TestFetchSourceGroups:

    @pytest.mark.asyncio
    async def test_groups_by_field_with_refs(self):
        results = [
            _hit("c1", "docA", "내용1"),
            _hit("c2", "docA", "내용2"),
            _hit("c3", "docB", "내용3"),
        ]
        prov, _ = _provider(results)
        groups = await prov.fetch_source_groups("agent_1", "policy", 10, "r")
        assert len(groups) == 2
        a = next(g for g in groups if g.topic_hint == "docA")
        assert a.texts == ["내용1", "내용2"]
        assert a.refs == ["c1", "c2"]

    @pytest.mark.asyncio
    async def test_respects_max_articles(self):
        results = [_hit(f"c{i}", f"doc{i}", f"내용{i}") for i in range(5)]
        prov, _ = _provider(results)
        groups = await prov.fetch_source_groups("agent_1", "policy", 2, "r")
        assert len(groups) == 2

    @pytest.mark.asyncio
    async def test_queries_collection_as_index(self):
        prov, es = _provider([])
        await prov.fetch_source_groups("agent_1", "policy_docs", 10, "r")
        query = es.search.await_args.args[0]
        assert query.index == "policy_docs"

    @pytest.mark.asyncio
    async def test_missing_group_field_falls_back_to_own_id(self):
        results = [ESSearchResult(id="c1", score=1.0, index="policy", source={"content": "x"})]
        prov, _ = _provider(results)
        groups = await prov.fetch_source_groups("agent_1", "policy", 10, "r")
        assert len(groups) == 1
        assert groups[0].refs == ["c1"]

    @pytest.mark.asyncio
    async def test_skips_empty_content(self):
        results = [_hit("c1", "docA", ""), _hit("c2", "docA", "유효")]
        prov, _ = _provider(results)
        groups = await prov.fetch_source_groups("agent_1", "policy", 10, "r")
        assert groups[0].texts == ["유효"]
        assert groups[0].refs == ["c2"]

    @pytest.mark.asyncio
    async def test_empty_results_returns_empty(self):
        prov, _ = _provider([])
        groups = await prov.fetch_source_groups("agent_1", "policy", 10, "r")
        assert groups == []
