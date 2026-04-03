"""Tests for ChunkAndIndexUseCase."""
import pytest
from unittest.mock import AsyncMock, MagicMock


REQUEST_ID = "req-chunk-001"


def _make_langchain_doc(content, chunk_type="child", chunk_id="c1", parent_id="p1", chunk_index=0, total=1):
    from langchain_core.documents import Document
    meta = {
        "chunk_type": chunk_type,
        "chunk_id": chunk_id,
        "chunk_index": chunk_index,
        "total_chunks": total,
    }
    if chunk_type == "child":
        meta["parent_id"] = parent_id
    return Document(page_content=content, metadata=meta)


def _make_keyword_result(keywords=None):
    from src.domain.keyword.schemas import KeywordExtractionResult
    kws = keywords or ["금융", "정책"]
    return KeywordExtractionResult(
        keywords=kws,
        keyword_frequencies={k: 1 for k in kws},
    )


@pytest.fixture
def mock_strategy():
    strategy = MagicMock()
    strategy.chunk.return_value = [
        _make_langchain_doc("청크1 내용", chunk_id="c1"),
        _make_langchain_doc("청크2 내용", chunk_id="c2"),
    ]
    return strategy


@pytest.fixture
def mock_extractor():
    extractor = MagicMock()
    extractor.extract.return_value = _make_keyword_result()
    return extractor


@pytest.fixture
def mock_es_repo():
    repo = MagicMock()
    repo.bulk_index = AsyncMock(return_value=2)
    return repo


@pytest.fixture
def mock_logger():
    logger = MagicMock()
    logger.info = MagicMock()
    logger.error = MagicMock()
    return logger


@pytest.fixture
def use_case(mock_strategy, mock_extractor, mock_es_repo, mock_logger):
    from src.application.chunk_and_index.use_case import ChunkAndIndexUseCase
    return ChunkAndIndexUseCase(
        chunking_strategy=mock_strategy,
        keyword_extractor=mock_extractor,
        es_repo=mock_es_repo,
        es_index="documents",
        logger=mock_logger,
    )


class TestChunkAndIndexUseCase:
    @pytest.mark.asyncio
    async def test_execute_returns_result_with_document_id(self, use_case):
        from src.application.chunk_and_index.schemas import ChunkAndIndexRequest
        req = ChunkAndIndexRequest(document_id="doc-1", content="텍스트", user_id="u1")
        result = await use_case.execute(req, REQUEST_ID)
        assert result.document_id == "doc-1"

    @pytest.mark.asyncio
    async def test_execute_calls_chunking_strategy(self, use_case, mock_strategy):
        from src.application.chunk_and_index.schemas import ChunkAndIndexRequest
        req = ChunkAndIndexRequest(document_id="d", content="텍스트", user_id="u1")
        await use_case.execute(req, REQUEST_ID)
        mock_strategy.chunk.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_calls_keyword_extractor_per_chunk(self, use_case, mock_extractor):
        from src.application.chunk_and_index.schemas import ChunkAndIndexRequest
        req = ChunkAndIndexRequest(document_id="d", content="텍스트", user_id="u1")
        await use_case.execute(req, REQUEST_ID)
        assert mock_extractor.extract.call_count == 2  # 2 chunks

    @pytest.mark.asyncio
    async def test_execute_calls_es_bulk_index(self, use_case, mock_es_repo):
        from src.application.chunk_and_index.schemas import ChunkAndIndexRequest
        req = ChunkAndIndexRequest(document_id="d", content="텍스트", user_id="u1")
        await use_case.execute(req, REQUEST_ID)
        mock_es_repo.bulk_index.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_result_contains_indexed_chunks(self, use_case):
        from src.application.chunk_and_index.schemas import ChunkAndIndexRequest
        req = ChunkAndIndexRequest(document_id="d", content="텍스트", user_id="u1")
        result = await use_case.execute(req, REQUEST_ID)
        assert result.total_chunks == 2
        assert len(result.indexed_chunks) == 2

    @pytest.mark.asyncio
    async def test_execute_chunks_contain_keywords(self, use_case):
        from src.application.chunk_and_index.schemas import ChunkAndIndexRequest
        req = ChunkAndIndexRequest(document_id="d", content="텍스트", user_id="u1")
        result = await use_case.execute(req, REQUEST_ID)
        for chunk in result.indexed_chunks:
            assert len(chunk.keywords) > 0

    @pytest.mark.asyncio
    async def test_execute_es_documents_include_keywords_field(self, use_case, mock_es_repo):
        from src.application.chunk_and_index.schemas import ChunkAndIndexRequest
        req = ChunkAndIndexRequest(document_id="d", content="텍스트", user_id="u1")
        await use_case.execute(req, REQUEST_ID)
        call_args = mock_es_repo.bulk_index.call_args
        docs = call_args[0][0]
        for doc in docs:
            assert "keywords" in doc.body
            assert isinstance(doc.body["keywords"], list)

    @pytest.mark.asyncio
    async def test_execute_es_documents_include_content_field(self, use_case, mock_es_repo):
        from src.application.chunk_and_index.schemas import ChunkAndIndexRequest
        req = ChunkAndIndexRequest(document_id="d", content="텍스트", user_id="u1")
        await use_case.execute(req, REQUEST_ID)
        call_args = mock_es_repo.bulk_index.call_args
        docs = call_args[0][0]
        for doc in docs:
            assert "content" in doc.body

    @pytest.mark.asyncio
    async def test_execute_logs_start_and_completion(self, use_case, mock_logger):
        from src.application.chunk_and_index.schemas import ChunkAndIndexRequest
        req = ChunkAndIndexRequest(document_id="d", content="텍스트", user_id="u1")
        await use_case.execute(req, REQUEST_ID)
        assert mock_logger.info.call_count >= 2

    @pytest.mark.asyncio
    async def test_execute_logs_error_and_reraises_on_exception(
        self, use_case, mock_es_repo, mock_logger
    ):
        from src.application.chunk_and_index.schemas import ChunkAndIndexRequest
        mock_es_repo.bulk_index.side_effect = RuntimeError("ES down")
        req = ChunkAndIndexRequest(document_id="d", content="텍스트", user_id="u1")
        with pytest.raises(RuntimeError):
            await use_case.execute(req, REQUEST_ID)
        mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_passes_top_keywords_to_extractor(
        self, use_case, mock_extractor
    ):
        from src.application.chunk_and_index.schemas import ChunkAndIndexRequest
        req = ChunkAndIndexRequest(document_id="d", content="텍스트", user_id="u1", top_keywords=5)
        await use_case.execute(req, REQUEST_ID)
        for call in mock_extractor.extract.call_args_list:
            assert call[1].get("top_n") == 5 or (call[0] and call[0][1] == 5)

    @pytest.mark.asyncio
    async def test_execute_es_docs_include_user_id_and_document_id(
        self, use_case, mock_es_repo
    ):
        from src.application.chunk_and_index.schemas import ChunkAndIndexRequest
        req = ChunkAndIndexRequest(document_id="doc-99", content="텍스트", user_id="user-1")
        await use_case.execute(req, REQUEST_ID)
        docs = mock_es_repo.bulk_index.call_args[0][0]
        for doc in docs:
            assert doc.body.get("document_id") == "doc-99"
            assert doc.body.get("user_id") == "user-1"
