"""Tests for ElasticsearchRepository CRUD and search operations."""
import pytest
from unittest.mock import AsyncMock, MagicMock, call


REQUEST_ID = "req-test-001"


@pytest.fixture
def mock_es():
    """Mock AsyncElasticsearch instance."""
    es = MagicMock()
    es.index = AsyncMock(return_value={"_id": "doc-1"})
    es.bulk = AsyncMock(return_value={"errors": False, "items": []})
    es.get = AsyncMock(return_value={"_source": {"title": "hello"}})
    es.delete = AsyncMock(return_value={"result": "deleted"})
    es.search = AsyncMock(
        return_value={
            "hits": {
                "hits": [
                    {"_id": "doc-1", "_score": 0.9, "_source": {"title": "x"}, "_index": "idx"},
                ]
            }
        }
    )
    es.exists = AsyncMock(return_value=True)
    es.delete_by_query = AsyncMock(return_value={"deleted": 3})
    return es


@pytest.fixture
def mock_client(mock_es):
    """Mock ElasticsearchClient that returns mock_es."""
    client = MagicMock()
    client.get_client.return_value = mock_es
    return client


@pytest.fixture
def mock_logger():
    """Mock LoggerInterface."""
    logger = MagicMock()
    logger.info = MagicMock()
    logger.warning = MagicMock()
    logger.error = MagicMock()
    return logger


@pytest.fixture
def repo(mock_client, mock_logger):
    """ElasticsearchRepository instance with mocked deps."""
    from src.infrastructure.elasticsearch.es_repository import ElasticsearchRepository
    return ElasticsearchRepository(client=mock_client, logger=mock_logger)


class TestElasticsearchRepositoryIndex:
    """index() 메서드 테스트."""

    @pytest.mark.asyncio
    async def test_index_returns_doc_id(self, repo, mock_es):
        """정상 색인 시 document id를 반환한다."""
        from src.domain.elasticsearch.schemas import ESDocument

        doc = ESDocument(id="doc-1", body={"title": "hello"}, index="my-index")
        result = await repo.index(doc, REQUEST_ID)

        assert result == "doc-1"

    @pytest.mark.asyncio
    async def test_index_calls_es_with_correct_params(self, repo, mock_es):
        """es.index()가 올바른 파라미터로 호출된다."""
        from src.domain.elasticsearch.schemas import ESDocument

        doc = ESDocument(id="doc-1", body={"title": "hello"}, index="my-index")
        await repo.index(doc, REQUEST_ID)

        mock_es.index.assert_called_once_with(
            index="my-index", id="doc-1", document={"title": "hello"}
        )

    @pytest.mark.asyncio
    async def test_index_logs_start_and_completion(self, repo, mock_logger):
        """INFO 로그가 시작과 완료 시 각각 기록된다."""
        from src.domain.elasticsearch.schemas import ESDocument

        doc = ESDocument(id="doc-1", body={}, index="idx")
        await repo.index(doc, REQUEST_ID)

        assert mock_logger.info.call_count == 2

    @pytest.mark.asyncio
    async def test_index_logs_error_and_reraises_on_exception(self, repo, mock_es, mock_logger):
        """예외 발생 시 ERROR 로그를 남기고 예외를 다시 raise한다."""
        from src.domain.elasticsearch.schemas import ESDocument

        mock_es.index.side_effect = RuntimeError("ES down")
        doc = ESDocument(id="doc-1", body={}, index="idx")

        with pytest.raises(RuntimeError):
            await repo.index(doc, REQUEST_ID)

        mock_logger.error.assert_called_once()
        error_kwargs = mock_logger.error.call_args[1]
        assert "exception" in error_kwargs


class TestElasticsearchRepositoryBulkIndex:
    """bulk_index() 메서드 테스트."""

    @pytest.mark.asyncio
    async def test_bulk_index_returns_success_count(self, repo, mock_es):
        """성공한 문서 수를 반환한다."""
        from src.domain.elasticsearch.schemas import ESDocument

        mock_es.bulk.return_value = {
            "errors": False,
            "items": [
                {"index": {"_id": "d1", "status": 200}},
                {"index": {"_id": "d2", "status": 200}},
            ],
        }
        docs = [
            ESDocument(id="d1", body={"x": 1}, index="idx"),
            ESDocument(id="d2", body={"x": 2}, index="idx"),
        ]
        result = await repo.bulk_index(docs, REQUEST_ID)

        assert result == 2

    @pytest.mark.asyncio
    async def test_bulk_index_logs_warning_on_partial_failure(self, repo, mock_es, mock_logger):
        """일부 실패 시 WARNING 로그를 기록한다."""
        from src.domain.elasticsearch.schemas import ESDocument

        mock_es.bulk.return_value = {
            "errors": True,
            "items": [
                {"index": {"_id": "d1", "status": 200}},
                {"index": {"_id": "d2", "status": 400, "error": {"reason": "bad"}}},
            ],
        }
        docs = [
            ESDocument(id="d1", body={}, index="idx"),
            ESDocument(id="d2", body={}, index="idx"),
        ]
        await repo.bulk_index(docs, REQUEST_ID)

        mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_bulk_index_logs_error_and_reraises_on_exception(
        self, repo, mock_es, mock_logger
    ):
        """예외 발생 시 ERROR 로그를 남기고 재raise한다."""
        from src.domain.elasticsearch.schemas import ESDocument

        mock_es.bulk.side_effect = RuntimeError("bulk failed")
        docs = [ESDocument(id="d1", body={}, index="idx")]

        with pytest.raises(RuntimeError):
            await repo.bulk_index(docs, REQUEST_ID)

        mock_logger.error.assert_called_once()


class TestElasticsearchRepositoryGet:
    """get() 메서드 테스트."""

    @pytest.mark.asyncio
    async def test_get_returns_source_when_found(self, repo, mock_es):
        """문서가 존재하면 _source를 반환한다."""
        mock_es.get.return_value = {"_source": {"title": "found"}}
        result = await repo.get("my-index", "doc-1", REQUEST_ID)

        assert result == {"title": "found"}

    @pytest.mark.asyncio
    async def test_get_returns_none_when_not_found(self, repo, mock_es):
        """문서가 없으면 None을 반환한다."""
        from elasticsearch import NotFoundError

        mock_es.get.side_effect = NotFoundError(404, {"_id": "missing"}, {"_id": "missing"})
        result = await repo.get("my-index", "missing-doc", REQUEST_ID)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_calls_es_with_correct_params(self, repo, mock_es):
        """es.get()이 올바른 파라미터로 호출된다."""
        await repo.get("test-index", "doc-123", REQUEST_ID)

        mock_es.get.assert_called_once_with(index="test-index", id="doc-123")


class TestElasticsearchRepositoryDelete:
    """delete() 메서드 테스트."""

    @pytest.mark.asyncio
    async def test_delete_returns_true_when_deleted(self, repo, mock_es):
        """삭제 성공 시 True를 반환한다."""
        mock_es.delete.return_value = {"result": "deleted"}
        result = await repo.delete("idx", "doc-1", REQUEST_ID)

        assert result is True

    @pytest.mark.asyncio
    async def test_delete_returns_false_when_not_found(self, repo, mock_es):
        """문서가 없으면 False를 반환한다."""
        from elasticsearch import NotFoundError

        mock_es.delete.side_effect = NotFoundError(404, {"_id": "x"}, {"_id": "x"})
        result = await repo.delete("idx", "missing-doc", REQUEST_ID)

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_logs_error_and_reraises_on_unexpected_exception(
        self, repo, mock_es, mock_logger
    ):
        """예상치 못한 예외는 ERROR 로그 후 재raise한다."""
        mock_es.delete.side_effect = RuntimeError("unexpected")

        with pytest.raises(RuntimeError):
            await repo.delete("idx", "doc-1", REQUEST_ID)

        mock_logger.error.assert_called_once()


class TestElasticsearchRepositorySearch:
    """search() 메서드 테스트."""

    @pytest.mark.asyncio
    async def test_search_returns_hits_as_es_search_result_list(self, repo, mock_es):
        """검색 결과를 ESSearchResult 목록으로 반환한다."""
        from src.domain.elasticsearch.schemas import ESSearchQuery, ESSearchResult

        mock_es.search.return_value = {
            "hits": {
                "hits": [
                    {"_id": "h1", "_score": 0.85, "_source": {"title": "t"}, "_index": "idx"},
                    {"_id": "h2", "_score": 0.70, "_source": {"title": "u"}, "_index": "idx"},
                ]
            }
        }
        q = ESSearchQuery(index="idx", query={"match": {"title": "hello"}})
        results = await repo.search(q, REQUEST_ID)

        assert len(results) == 2
        assert all(isinstance(r, ESSearchResult) for r in results)
        assert results[0].id == "h1"
        assert results[0].score == 0.85

    @pytest.mark.asyncio
    async def test_search_passes_size_and_from_to_es(self, repo, mock_es):
        """size와 from_이 es.search()에 전달된다."""
        from src.domain.elasticsearch.schemas import ESSearchQuery

        q = ESSearchQuery(index="idx", query={}, size=5, from_=10)
        await repo.search(q, REQUEST_ID)

        call_kwargs = mock_es.search.call_args[1]
        assert call_kwargs["size"] == 5
        assert call_kwargs["from_"] == 10

    @pytest.mark.asyncio
    async def test_search_passes_source_fields_when_specified(self, repo, mock_es):
        """source_fields가 지정되면 _source 파라미터로 전달된다."""
        from src.domain.elasticsearch.schemas import ESSearchQuery

        q = ESSearchQuery(index="idx", query={}, source_fields=["title", "content"])
        await repo.search(q, REQUEST_ID)

        call_kwargs = mock_es.search.call_args[1]
        assert call_kwargs["source"] == ["title", "content"]

    @pytest.mark.asyncio
    async def test_search_returns_empty_list_on_no_hits(self, repo, mock_es):
        """검색 결과가 없으면 빈 리스트를 반환한다."""
        from src.domain.elasticsearch.schemas import ESSearchQuery

        mock_es.search.return_value = {"hits": {"hits": []}}
        q = ESSearchQuery(index="idx", query={})
        results = await repo.search(q, REQUEST_ID)

        assert results == []

    @pytest.mark.asyncio
    async def test_search_returns_empty_list_on_index_not_found(
        self, repo, mock_es, mock_logger
    ):
        """인덱스가 존재하지 않으면 빈 리스트를 반환하고 warning 로그를 남긴다."""
        from elasticsearch import NotFoundError
        from src.domain.elasticsearch.schemas import ESSearchQuery

        mock_es.search.side_effect = NotFoundError(
            404, "index_not_found_exception", "no such index [documents]"
        )
        q = ESSearchQuery(index="documents", query={"match_all": {}})
        results = await repo.search(q, REQUEST_ID)

        assert results == []
        mock_logger.warning.assert_called_once()
        mock_logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_search_logs_error_and_reraises_on_exception(
        self, repo, mock_es, mock_logger
    ):
        """예외 발생 시 ERROR 로그 후 재raise한다."""
        from src.domain.elasticsearch.schemas import ESSearchQuery

        mock_es.search.side_effect = RuntimeError("search failed")
        q = ESSearchQuery(index="idx", query={})

        with pytest.raises(RuntimeError):
            await repo.search(q, REQUEST_ID)

        mock_logger.error.assert_called_once()


class TestElasticsearchRepositoryExists:
    """exists() 메서드 테스트."""

    @pytest.mark.asyncio
    async def test_exists_returns_true_when_document_found(self, repo, mock_es):
        """문서가 존재하면 True를 반환한다."""
        mock_es.exists.return_value = True
        result = await repo.exists("idx", "doc-1", REQUEST_ID)

        assert result is True

    @pytest.mark.asyncio
    async def test_exists_returns_false_when_not_found(self, repo, mock_es):
        """문서가 없으면 False를 반환한다."""
        from elasticsearch import NotFoundError

        mock_es.exists.side_effect = NotFoundError(404, {"_id": "x"}, {"_id": "x"})
        result = await repo.exists("idx", "missing", REQUEST_ID)

        assert result is False

    @pytest.mark.asyncio
    async def test_exists_calls_es_with_correct_params(self, repo, mock_es):
        """es.exists()가 올바른 파라미터로 호출된다."""
        await repo.exists("test-index", "doc-999", REQUEST_ID)

        mock_es.exists.assert_called_once_with(index="test-index", id="doc-999")


class TestElasticsearchRepositoryDeleteByQuery:
    """delete_by_query() 메서드 테스트."""

    @pytest.mark.asyncio
    async def test_delete_by_query_returns_deleted_count(self, repo, mock_es):
        """삭제된 문서 수를 반환한다."""
        mock_es.delete_by_query.return_value = {"deleted": 5}
        result = await repo.delete_by_query("idx", {"term": {"status": "old"}}, REQUEST_ID)

        assert result == 5

    @pytest.mark.asyncio
    async def test_delete_by_query_calls_es_with_correct_params(self, repo, mock_es):
        """es.delete_by_query()가 올바른 파라미터로 호출된다."""
        query = {"term": {"type": "temp"}}
        await repo.delete_by_query("my-index", query, REQUEST_ID)

        mock_es.delete_by_query.assert_called_once_with(index="my-index", query=query)

    @pytest.mark.asyncio
    async def test_delete_by_query_logs_error_and_reraises_on_exception(
        self, repo, mock_es, mock_logger
    ):
        """예외 발생 시 ERROR 로그 후 재raise한다."""
        mock_es.delete_by_query.side_effect = RuntimeError("query failed")

        with pytest.raises(RuntimeError):
            await repo.delete_by_query("idx", {}, REQUEST_ID)

        mock_logger.error.assert_called_once()


class TestElasticsearchRepositoryEnsureIndexExists:
    """ensure_index_exists() 메서드 테스트."""

    @pytest.mark.asyncio
    async def test_ensure_index_exists_creates_when_missing(self, repo, mock_es, mock_logger):
        """인덱스가 없으면 생성하고 True를 반환한다."""
        mock_es.indices = MagicMock()
        mock_es.indices.exists = AsyncMock(return_value=False)
        mock_es.indices.create = AsyncMock(return_value={"acknowledged": True})

        result = await repo.ensure_index_exists("documents", {"properties": {}})

        assert result is True
        mock_es.indices.create.assert_called_once()
        mock_logger.info.assert_called()

    @pytest.mark.asyncio
    async def test_ensure_index_exists_skips_when_present(self, repo, mock_es):
        """인덱스가 이미 존재하면 생성하지 않고 False를 반환한다."""
        mock_es.indices = MagicMock()
        mock_es.indices.exists = AsyncMock(return_value=True)
        mock_es.indices.create = AsyncMock()

        result = await repo.ensure_index_exists("documents", {"properties": {}})

        assert result is False
        mock_es.indices.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_index_exists_returns_false_on_error(self, repo, mock_es, mock_logger):
        """ES 연결 실패 시 False를 반환하고 warning 로그를 남긴다."""
        mock_es.indices = MagicMock()
        mock_es.indices.exists = AsyncMock(side_effect=ConnectionError("ES down"))

        result = await repo.ensure_index_exists("documents", {"properties": {}})

        assert result is False
        mock_logger.warning.assert_called()
