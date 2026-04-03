"""Tests for PDFParseUseCase — Application layer PDF parsing common service."""
import pytest
from unittest.mock import MagicMock, patch
from langchain_core.documents import Document

from src.domain.parser.schemas import ParseDocumentRequest, ParseDocumentResult


# ───────────────────────────────────────────────
# Fixtures
# ───────────────────────────────────────────────

@pytest.fixture
def mock_parser():
    parser = MagicMock()
    parser.get_parser_name.return_value = "llamaparser"
    parser.parse_bytes.return_value = [
        Document(page_content="페이지 1 내용", metadata={"document_id": "abc_test", "page": 1, "total_pages": 2}),
        Document(page_content="페이지 2 내용", metadata={"document_id": "abc_test", "page": 2, "total_pages": 2}),
    ]
    parser.parse.return_value = [
        Document(page_content="파일 1 내용", metadata={"document_id": "xyz_test", "page": 1, "total_pages": 1}),
    ]
    return parser


@pytest.fixture
def mock_logger():
    logger = MagicMock()
    return logger


@pytest.fixture
def use_case(mock_parser, mock_logger):
    from src.application.use_cases.pdf_parse_use_case import PDFParseUseCase
    return PDFParseUseCase(parser=mock_parser, logger=mock_logger)


@pytest.fixture
def bytes_request():
    return ParseDocumentRequest(
        filename="test.pdf",
        user_id="user_123",
        request_id="req_001",
        file_bytes=b"%PDF-1.4 fake content",
    )


@pytest.fixture
def path_request():
    return ParseDocumentRequest(
        filename="test.pdf",
        user_id="user_123",
        request_id="req_001",
        file_path="/tmp/test.pdf",
    )


# ───────────────────────────────────────────────
# parse_from_bytes
# ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_parse_from_bytes_success_returns_result(use_case, mock_parser, bytes_request):
    result = await use_case.parse_from_bytes(bytes_request)

    assert isinstance(result, ParseDocumentResult)
    assert result.filename == "test.pdf"
    assert result.user_id == "user_123"
    assert result.request_id == "req_001"
    assert result.total_pages == 2
    assert result.parser_used == "llamaparser"
    assert len(result.documents) == 2


@pytest.mark.asyncio
async def test_parse_from_bytes_calls_parser_with_correct_args(use_case, mock_parser, bytes_request):
    await use_case.parse_from_bytes(bytes_request)

    mock_parser.parse_bytes.assert_called_once_with(
        file_bytes=bytes_request.file_bytes,
        filename="test.pdf",
        user_id="user_123",
    )


@pytest.mark.asyncio
async def test_parse_from_bytes_raises_value_error_when_no_bytes(use_case):
    request = ParseDocumentRequest(
        filename="test.pdf",
        user_id="user_123",
        request_id="req_001",
        file_bytes=None,
    )
    with pytest.raises(ValueError, match="file_bytes"):
        await use_case.parse_from_bytes(request)


@pytest.mark.asyncio
async def test_parse_from_bytes_logs_info_on_start_and_complete(use_case, mock_logger, bytes_request):
    await use_case.parse_from_bytes(bytes_request)

    assert mock_logger.info.call_count >= 2


@pytest.mark.asyncio
async def test_parse_from_bytes_logs_error_and_reraises_on_exception(use_case, mock_parser, mock_logger, bytes_request):
    mock_parser.parse_bytes.side_effect = RuntimeError("LlamaParse API 실패")

    with pytest.raises(RuntimeError, match="LlamaParse API 실패"):
        await use_case.parse_from_bytes(bytes_request)

    mock_logger.error.assert_called_once()
    call_kwargs = mock_logger.error.call_args
    assert call_kwargs.kwargs.get("exception") is not None or (
        len(call_kwargs.args) > 0
    )


# ───────────────────────────────────────────────
# parse_from_path
# ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_parse_from_path_success_returns_result(use_case, mock_parser, path_request):
    result = await use_case.parse_from_path(path_request)

    assert isinstance(result, ParseDocumentResult)
    assert result.filename == "test.pdf"
    assert result.user_id == "user_123"
    assert result.total_pages == 1
    assert result.parser_used == "llamaparser"
    assert len(result.documents) == 1


@pytest.mark.asyncio
async def test_parse_from_path_calls_parser_with_correct_args(use_case, mock_parser, path_request):
    await use_case.parse_from_path(path_request)

    mock_parser.parse.assert_called_once_with(
        file_path="/tmp/test.pdf",
        user_id="user_123",
    )


@pytest.mark.asyncio
async def test_parse_from_path_raises_value_error_when_no_path(use_case):
    request = ParseDocumentRequest(
        filename="test.pdf",
        user_id="user_123",
        request_id="req_001",
        file_path=None,
    )
    with pytest.raises(ValueError, match="file_path"):
        await use_case.parse_from_path(request)


@pytest.mark.asyncio
async def test_parse_from_path_logs_info_on_start_and_complete(use_case, mock_logger, path_request):
    await use_case.parse_from_path(path_request)

    assert mock_logger.info.call_count >= 2


@pytest.mark.asyncio
async def test_parse_from_path_logs_error_and_reraises_on_exception(use_case, mock_parser, mock_logger, path_request):
    mock_parser.parse.side_effect = RuntimeError("파일 없음")

    with pytest.raises(RuntimeError, match="파일 없음"):
        await use_case.parse_from_path(path_request)

    mock_logger.error.assert_called_once()


# ───────────────────────────────────────────────
# ParseDocumentRequest schema
# ───────────────────────────────────────────────

def test_parse_document_request_requires_filename():
    with pytest.raises(Exception):
        ParseDocumentRequest(filename="", user_id="u", request_id="r")


def test_parse_document_request_accepts_both_none_bytes_and_path():
    req = ParseDocumentRequest(filename="a.pdf", user_id="u", request_id="r")
    assert req.file_bytes is None
    assert req.file_path is None
