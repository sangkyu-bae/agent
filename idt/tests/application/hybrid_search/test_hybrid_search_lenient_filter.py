"""HybridSearchUseCase lenient_filter·collection_name 필터 테스트 (rag-auth-filter-fix D2/D4)."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.application.hybrid_search.use_case import HybridSearchUseCase
from src.domain.hybrid_search.schemas import HybridSearchRequest

REQUEST_ID = "req-lenient-001"


@pytest.fixture
def mock_es_repo():
    repo = MagicMock()
    repo.search = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def mock_embedding():
    emb = MagicMock()
    emb.embed_text = AsyncMock(return_value=[0.1, 0.2, 0.3])
    return emb


@pytest.fixture
def mock_vector_store():
    vs = MagicMock()
    vs.search_by_vector = AsyncMock(return_value=[])
    return vs


@pytest.fixture
def use_case(mock_es_repo, mock_embedding, mock_vector_store):
    return HybridSearchUseCase(
        es_repo=mock_es_repo,
        embedding=mock_embedding,
        vector_store=mock_vector_store,
        es_index="documents",
        logger=MagicMock(),
    )


def _es_query(mock_es_repo) -> dict:
    return mock_es_repo.search.call_args[0][0].query


class TestLenientFilterES:
    @pytest.mark.asyncio
    async def test_lenient_filter_builds_should_term_or_missing(
        self, use_case, mock_es_repo
    ):
        req = HybridSearchRequest(
            query="q", lenient_filter={"visibility": "public"}
        )
        await use_case.execute(req, REQUEST_ID)

        query = _es_query(mock_es_repo)
        clauses = query["bool"]["filter"]
        assert clauses == [{
            "bool": {
                "should": [
                    {"term": {"visibility": "public"}},
                    {"bool": {"must_not": [{"exists": {"field": "visibility"}}]}},
                ],
                "minimum_should_match": 1,
            }
        }]

    @pytest.mark.asyncio
    async def test_no_filters_keeps_plain_multi_match(self, use_case, mock_es_repo):
        req = HybridSearchRequest(query="q")
        await use_case.execute(req, REQUEST_ID)

        query = _es_query(mock_es_repo)
        assert "multi_match" in query  # bool 래핑 없음 (기존 동작)

    @pytest.mark.asyncio
    async def test_collection_name_adds_term_filter(self, use_case, mock_es_repo):
        req = HybridSearchRequest(query="q", collection_name="test10")
        await use_case.execute(req, REQUEST_ID)

        query = _es_query(mock_es_repo)
        assert {"term": {"collection_name": "test10"}} in query["bool"]["filter"]

    @pytest.mark.asyncio
    async def test_hard_lenient_collection_compose(self, use_case, mock_es_repo):
        req = HybridSearchRequest(
            query="q",
            metadata_filter={"category": "policy"},
            lenient_filter={"visibility": "public"},
            collection_name="test10",
        )
        await use_case.execute(req, REQUEST_ID)

        clauses = _es_query(mock_es_repo)["bool"]["filter"]
        assert {"term": {"category": "policy"}} in clauses
        assert {"term": {"collection_name": "test10"}} in clauses
        assert any("should" in c.get("bool", {}) for c in clauses)


class TestLenientFilterVector:
    @pytest.mark.asyncio
    async def test_lenient_filter_passed_to_search_filter(
        self, use_case, mock_vector_store
    ):
        req = HybridSearchRequest(
            query="q", lenient_filter={"visibility": "public"}
        )
        await use_case.execute(req, REQUEST_ID)

        sf = mock_vector_store.search_by_vector.call_args.kwargs["filter"]
        assert sf.metadata_lenient == {"visibility": "public"}
        assert sf.metadata == {}

    @pytest.mark.asyncio
    async def test_no_filter_object_when_both_empty(
        self, use_case, mock_vector_store
    ):
        req = HybridSearchRequest(query="q")
        await use_case.execute(req, REQUEST_ID)

        assert mock_vector_store.search_by_vector.call_args.kwargs["filter"] is None
