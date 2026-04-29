"""Tests for HybridSearchUseCase."""
import pytest
from unittest.mock import AsyncMock, MagicMock


REQUEST_ID = "req-hybrid-001"


def make_es_result(id_, content="내용", score=5.0):
    from src.domain.elasticsearch.schemas import ESSearchResult
    return ESSearchResult(id=id_, score=score, source={"content": content, "type": "pdf"}, index="docs")


def make_vector_doc(id_, content="내용", score=0.8):
    from src.domain.vector.entities import Document
    from src.domain.vector.value_objects import DocumentId
    return Document(
        id=DocumentId(id_),
        content=content,
        vector=[0.1, 0.2, 0.3],
        metadata={"type": "pdf"},
        score=score,
    )


@pytest.fixture
def mock_es_repo():
    repo = MagicMock()
    repo.search = AsyncMock(return_value=[make_es_result("doc-1"), make_es_result("doc-2")])
    return repo


@pytest.fixture
def mock_embedding():
    emb = MagicMock()
    emb.embed_text = AsyncMock(return_value=[0.1, 0.2, 0.3])
    return emb


@pytest.fixture
def mock_vector_store():
    vs = MagicMock()
    vs.search_by_vector = AsyncMock(
        return_value=[make_vector_doc("doc-2"), make_vector_doc("doc-3")]
    )
    return vs


@pytest.fixture
def mock_logger():
    logger = MagicMock()
    logger.info = MagicMock()
    logger.error = MagicMock()
    return logger


@pytest.fixture
def use_case(mock_es_repo, mock_embedding, mock_vector_store, mock_logger):
    from src.application.hybrid_search.use_case import HybridSearchUseCase
    return HybridSearchUseCase(
        es_repo=mock_es_repo,
        embedding=mock_embedding,
        vector_store=mock_vector_store,
        es_index="documents",
        logger=mock_logger,
    )


class TestHybridSearchUseCaseExecute:
    @pytest.mark.asyncio
    async def test_execute_returns_hybrid_search_response(self, use_case):
        from src.domain.hybrid_search.schemas import HybridSearchRequest, HybridSearchResponse

        req = HybridSearchRequest(query="금융 정책")
        result = await use_case.execute(req, REQUEST_ID)

        assert isinstance(result, HybridSearchResponse)
        assert result.query == "금융 정책"
        assert result.request_id == REQUEST_ID

    @pytest.mark.asyncio
    async def test_execute_calls_bm25_search_with_query(self, use_case, mock_es_repo):
        from src.domain.hybrid_search.schemas import HybridSearchRequest

        req = HybridSearchRequest(query="test query")
        await use_case.execute(req, REQUEST_ID)

        mock_es_repo.search.assert_called_once()
        call_args = mock_es_repo.search.call_args
        es_query = call_args[0][0]
        mm = es_query.query["multi_match"]
        assert mm["query"] == "test query"
        assert mm["fields"] == ["content", "morph_text^1.5"]
        assert mm["type"] == "most_fields"

    @pytest.mark.asyncio
    async def test_execute_embeds_query_for_vector_search(self, use_case, mock_embedding):
        from src.domain.hybrid_search.schemas import HybridSearchRequest

        req = HybridSearchRequest(query="test query")
        await use_case.execute(req, REQUEST_ID)

        mock_embedding.embed_text.assert_called_once_with("test query")

    @pytest.mark.asyncio
    async def test_execute_calls_vector_search_with_embedded_vector(
        self, use_case, mock_vector_store
    ):
        from src.domain.hybrid_search.schemas import HybridSearchRequest

        req = HybridSearchRequest(query="q", vector_top_k=15)
        await use_case.execute(req, REQUEST_ID)

        mock_vector_store.search_by_vector.assert_called_once_with(
            vector=[0.1, 0.2, 0.3], top_k=15, filter=None
        )

    @pytest.mark.asyncio
    async def test_execute_returns_merged_results(self, use_case):
        """doc-2는 BM25+Vector 양쪽에 있으므로 결합 점수로 상위에 위치해야 한다."""
        from src.domain.hybrid_search.schemas import HybridSearchRequest

        req = HybridSearchRequest(query="q")
        result = await use_case.execute(req, REQUEST_ID)

        ids = [r.id for r in result.results]
        assert "doc-2" in ids
        # doc-2 is in both lists → higher RRF score
        doc2 = next(r for r in result.results if r.id == "doc-2")
        assert doc2.source == "both"

    @pytest.mark.asyncio
    async def test_execute_respects_top_k(self, use_case, mock_es_repo, mock_vector_store):
        """top_k=1이면 결과가 1개만 반환된다."""
        from src.domain.hybrid_search.schemas import HybridSearchRequest

        mock_es_repo.search.return_value = [make_es_result(f"d{i}") for i in range(5)]
        mock_vector_store.search_by_vector.return_value = [
            make_vector_doc(f"v{i}") for i in range(5)
        ]
        req = HybridSearchRequest(query="q", top_k=1)
        result = await use_case.execute(req, REQUEST_ID)

        assert len(result.results) <= 1

    @pytest.mark.asyncio
    async def test_execute_logs_start_and_completion(self, use_case, mock_logger):
        from src.domain.hybrid_search.schemas import HybridSearchRequest

        req = HybridSearchRequest(query="q")
        await use_case.execute(req, REQUEST_ID)

        assert mock_logger.info.call_count >= 2

    @pytest.mark.asyncio
    async def test_execute_returns_vector_only_when_es_fails(
        self, use_case, mock_es_repo, mock_vector_store, mock_logger
    ):
        """ES 실패 시 Vector 결과만으로 응답한다."""
        from src.domain.hybrid_search.schemas import HybridSearchRequest

        mock_es_repo.search.side_effect = RuntimeError("ES unavailable")
        req = HybridSearchRequest(query="q")
        result = await use_case.execute(req, REQUEST_ID)

        assert result.total_found > 0
        mock_vector_store.search_by_vector.assert_called_once()
        mock_logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_execute_returns_bm25_only_when_vector_fails(
        self, use_case, mock_es_repo, mock_vector_store, mock_embedding, mock_logger
    ):
        """Vector 실패 시 BM25 결과만으로 응답한다."""
        from src.domain.hybrid_search.schemas import HybridSearchRequest

        mock_embedding.embed_text.side_effect = RuntimeError("Embedding unavailable")
        req = HybridSearchRequest(query="q")
        result = await use_case.execute(req, REQUEST_ID)

        assert result.total_found > 0
        mock_es_repo.search.assert_called_once()
        mock_logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_execute_returns_empty_when_both_fail(
        self, use_case, mock_es_repo, mock_embedding, mock_logger
    ):
        """양쪽 모두 실패 시 빈 결과를 반환한다."""
        from src.domain.hybrid_search.schemas import HybridSearchRequest

        mock_es_repo.search.side_effect = RuntimeError("ES down")
        mock_embedding.embed_text.side_effect = RuntimeError("Embedding down")
        req = HybridSearchRequest(query="q")
        result = await use_case.execute(req, REQUEST_ID)

        assert result.total_found == 0
        assert result.results == []

    @pytest.mark.asyncio
    async def test_execute_passes_bm25_top_k_to_es_search(self, use_case, mock_es_repo):
        from src.domain.hybrid_search.schemas import HybridSearchRequest

        req = HybridSearchRequest(query="q", bm25_top_k=30)
        await use_case.execute(req, REQUEST_ID)

        call_args = mock_es_repo.search.call_args
        es_query = call_args[0][0]
        assert es_query.size == 30

    @pytest.mark.asyncio
    async def test_metadata_filter_applied_to_es_query(self, use_case, mock_es_repo):
        from src.domain.hybrid_search.schemas import HybridSearchRequest

        req = HybridSearchRequest(
            query="q", metadata_filter={"department": "finance"}
        )
        await use_case.execute(req, REQUEST_ID)

        call_args = mock_es_repo.search.call_args
        es_query = call_args[0][0]
        assert "bool" in es_query.query
        must_clause = es_query.query["bool"]["must"][0]
        assert must_clause["multi_match"]["query"] == "q"
        assert must_clause["multi_match"]["fields"] == ["content", "morph_text^1.5"]
        assert es_query.query["bool"]["filter"] == [
            {"term": {"department": "finance"}}
        ]

    @pytest.mark.asyncio
    async def test_metadata_filter_applied_to_vector_search(
        self, use_case, mock_vector_store
    ):
        from src.domain.hybrid_search.schemas import HybridSearchRequest

        req = HybridSearchRequest(
            query="q", metadata_filter={"category": "policy"}
        )
        await use_case.execute(req, REQUEST_ID)

        call_args = mock_vector_store.search_by_vector.call_args
        assert call_args.kwargs["filter"] is not None

    @pytest.mark.asyncio
    async def test_no_metadata_filter_uses_simple_match_query(
        self, use_case, mock_es_repo
    ):
        from src.domain.hybrid_search.schemas import HybridSearchRequest

        req = HybridSearchRequest(query="test")
        await use_case.execute(req, REQUEST_ID)

        call_args = mock_es_repo.search.call_args
        es_query = call_args[0][0]
        assert "multi_match" in es_query.query
        assert "bool" not in es_query.query
