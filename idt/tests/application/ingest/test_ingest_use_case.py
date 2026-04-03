"""Tests for IngestDocumentUseCase — parse + chunk + embed + store."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.documents import Document as LangchainDoc

from src.domain.ingest.schemas import IngestRequest, IngestResult
from src.domain.vector.value_objects import DocumentId


# ───────────────────────────────────────────────
# Fixtures
# ───────────────────────────────────────────────

def _make_lc_doc(content: str, doc_id: str = "abc_test") -> LangchainDoc:
    return LangchainDoc(
        page_content=content,
        metadata={"document_id": doc_id, "page": 1, "total_pages": 2},
    )


@pytest.fixture
def mock_pymupdf_parser():
    p = MagicMock()
    p.get_parser_name.return_value = "pymupdf"
    p.parse_bytes.return_value = [
        _make_lc_doc("페이지 1"),
        _make_lc_doc("페이지 2"),
    ]
    return p


@pytest.fixture
def mock_llama_parser():
    p = MagicMock()
    p.get_parser_name.return_value = "llamaparser"
    p.parse_bytes.return_value = [_make_lc_doc("llama 내용")]
    return p


@pytest.fixture
def mock_embedding():
    emb = AsyncMock()
    emb.embed_documents.return_value = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    return emb


@pytest.fixture
def mock_vectorstore():
    vs = AsyncMock()
    vs.add_documents.return_value = [DocumentId("id-1"), DocumentId("id-2")]
    return vs


@pytest.fixture
def mock_logger():
    return MagicMock()


@pytest.fixture
def use_case(mock_pymupdf_parser, mock_llama_parser, mock_embedding, mock_vectorstore, mock_logger):
    from src.application.ingest.ingest_use_case import IngestDocumentUseCase
    return IngestDocumentUseCase(
        parsers={"pymupdf": mock_pymupdf_parser, "llamaparser": mock_llama_parser},
        embedding=mock_embedding,
        vectorstore=mock_vectorstore,
        logger=mock_logger,
    )


@pytest.fixture
def base_request():
    return IngestRequest(
        filename="test.pdf",
        user_id="user_123",
        request_id="req_001",
        file_bytes=b"%PDF fake",
        parser_type="pymupdf",
        chunking_strategy="full_token",
        chunk_size=500,
        chunk_overlap=50,
    )


# ───────────────────────────────────────────────
# Success cases
# ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ingest_success_returns_result(use_case, base_request):
    result = await use_case.ingest(base_request)

    assert isinstance(result, IngestResult)
    assert result.filename == "test.pdf"
    assert result.user_id == "user_123"
    assert result.request_id == "req_001"
    assert result.parser_used == "pymupdf"
    assert result.chunking_strategy == "full_token"
    assert result.chunk_count > 0
    assert len(result.stored_ids) > 0


@pytest.mark.asyncio
async def test_ingest_calls_pymupdf_parser_by_default(use_case, mock_pymupdf_parser, base_request):
    await use_case.ingest(base_request)
    mock_pymupdf_parser.parse_bytes.assert_called_once()


@pytest.mark.asyncio
async def test_ingest_llamaparser_selected_when_requested(use_case, mock_llama_parser, mock_embedding):
    mock_embedding.embed_documents.return_value = [[0.1, 0.2, 0.3]]
    request = IngestRequest(
        filename="test.pdf",
        user_id="user_1",
        request_id="req_1",
        file_bytes=b"pdf",
        parser_type="llamaparser",
    )
    result = await use_case.ingest(request)

    mock_llama_parser.parse_bytes.assert_called_once()
    assert result.parser_used == "llamaparser"


@pytest.mark.asyncio
async def test_ingest_chunks_are_embedded_and_stored(use_case, mock_embedding, mock_vectorstore, base_request):
    await use_case.ingest(base_request)

    mock_embedding.embed_documents.assert_called_once()
    mock_vectorstore.add_documents.assert_called_once()


@pytest.mark.asyncio
async def test_ingest_stored_ids_match_vectorstore_return(use_case, mock_vectorstore, base_request):
    mock_vectorstore.add_documents.return_value = [DocumentId("x-1"), DocumentId("x-2")]

    result = await use_case.ingest(base_request)

    assert "x-1" in result.stored_ids
    assert "x-2" in result.stored_ids


# ───────────────────────────────────────────────
# Error cases
# ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ingest_unknown_parser_raises_value_error(use_case):
    request = IngestRequest(
        filename="test.pdf",
        user_id="u",
        request_id="r",
        file_bytes=b"x",
        parser_type="unknown_parser",
    )
    with pytest.raises(ValueError, match="unknown_parser"):
        await use_case.ingest(request)


@pytest.mark.asyncio
async def test_ingest_logs_info_on_start_and_complete(use_case, mock_logger, base_request):
    await use_case.ingest(base_request)
    assert mock_logger.info.call_count >= 2


@pytest.mark.asyncio
async def test_ingest_logs_error_on_exception(use_case, mock_pymupdf_parser, mock_logger, base_request):
    mock_pymupdf_parser.parse_bytes.side_effect = RuntimeError("파싱 실패")

    with pytest.raises(RuntimeError):
        await use_case.ingest(base_request)

    assert mock_logger.error.call_count >= 1
    # 최소 하나의 error 로그에 exception= 인자 포함 확인
    error_calls = mock_logger.error.call_args_list
    assert any(call.kwargs.get("exception") is not None for call in error_calls)
