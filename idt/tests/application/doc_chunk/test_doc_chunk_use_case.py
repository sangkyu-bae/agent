"""Tests for DocChunkUseCase — TDD first."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.documents import Document as LangchainDocument

from src.domain.doc_chunk.schemas import DocChunkRequest, DocChunkResult


def _make_request(
    filename: str = "test.txt",
    strategy_type: str = "full_token",
    content: bytes = b"Hello world. This is a test document for chunking.",
) -> DocChunkRequest:
    return DocChunkRequest(
        filename=filename,
        user_id="user_001",
        request_id="req_001",
        file_bytes=content,
        strategy_type=strategy_type,
        chunk_size=100,
        chunk_overlap=10,
    )


def _make_logger() -> MagicMock:
    logger = MagicMock()
    logger.info = MagicMock()
    logger.error = MagicMock()
    return logger


def _make_pdf_parser(docs=None) -> MagicMock:
    parser = MagicMock()
    parser.get_parser_name.return_value = "pymupdf"
    if docs is None:
        docs = [LangchainDocument(page_content="PDF content here.", metadata={})]
    parser.parse_bytes.return_value = docs
    return parser


def _make_excel_parser(sheets=None) -> MagicMock:
    from src.domain.excel.entities.excel_data import ExcelData
    from src.domain.excel.entities.sheet_data import SheetData
    from src.domain.excel.value_objects.excel_metadata import ExcelMetadata

    if sheets is None:
        sheet = SheetData(
            sheet_name="Sheet1",
            data=[{"col_a": "value1", "col_b": 100}],
            columns=["col_a", "col_b"],
            dtypes={"col_a": "object", "col_b": "int64"},
        )
        sheets = {"Sheet1": sheet}

    excel_data = ExcelData(
        file_id="excel_001",
        filename="test.xlsx",
        sheets=sheets,
        metadata=ExcelMetadata(
            file_id="excel_001",
            filename="test.xlsx",
            sheet_names=list(sheets.keys()),
            total_rows=1,
            user_id="user_001",
        ),
    )
    parser = MagicMock()
    parser.get_parser_name.return_value = "pandas"
    parser.parse_bytes.return_value = excel_data
    return parser


# ──────────────────────────────────────────────────────
# TXT 파일 청킹
# ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chunk_txt_file_returns_chunks():
    from src.application.doc_chunk.use_case import DocChunkUseCase

    use_case = DocChunkUseCase(
        pdf_parser=_make_pdf_parser(),
        excel_parser=_make_excel_parser(),
        logger=_make_logger(),
    )
    request = _make_request(filename="doc.txt", content=b"Hello world. Test document.")
    result = await use_case.execute(request)

    assert isinstance(result, DocChunkResult)
    assert result.total_chunks >= 1
    assert result.filename == "doc.txt"
    assert result.user_id == "user_001"
    assert len(result.chunks) == result.total_chunks


@pytest.mark.asyncio
async def test_chunk_md_file_returns_chunks():
    from src.application.doc_chunk.use_case import DocChunkUseCase

    use_case = DocChunkUseCase(
        pdf_parser=_make_pdf_parser(),
        excel_parser=_make_excel_parser(),
        logger=_make_logger(),
    )
    request = _make_request(filename="README.md", content=b"# Title\n\nSome content here.")
    result = await use_case.execute(request)

    assert result.total_chunks >= 1
    assert result.filename == "README.md"


# ──────────────────────────────────────────────────────
# PDF 파일 청킹
# ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chunk_pdf_file_calls_pdf_parser():
    from src.application.doc_chunk.use_case import DocChunkUseCase

    pdf_parser = _make_pdf_parser(
        docs=[LangchainDocument(page_content="PDF page content.", metadata={})]
    )
    use_case = DocChunkUseCase(
        pdf_parser=pdf_parser,
        excel_parser=_make_excel_parser(),
        logger=_make_logger(),
    )
    request = _make_request(filename="report.pdf", content=b"%PDF-1.4 fake")
    result = await use_case.execute(request)

    pdf_parser.parse_bytes.assert_called_once()
    assert result.total_chunks >= 1


@pytest.mark.asyncio
async def test_chunk_pdf_returns_chunks_from_parser():
    from src.application.doc_chunk.use_case import DocChunkUseCase

    pages = [
        LangchainDocument(page_content="Page one content.", metadata={"page": "1"}),
        LangchainDocument(page_content="Page two content.", metadata={"page": "2"}),
    ]
    use_case = DocChunkUseCase(
        pdf_parser=_make_pdf_parser(docs=pages),
        excel_parser=_make_excel_parser(),
        logger=_make_logger(),
    )
    request = _make_request(filename="multi.pdf", content=b"%PDF fake")
    result = await use_case.execute(request)

    assert result.total_chunks >= 1
    assert all(c.content for c in result.chunks)


# ──────────────────────────────────────────────────────
# Excel 파일 청킹
# ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chunk_excel_file_calls_excel_parser():
    from src.application.doc_chunk.use_case import DocChunkUseCase

    excel_parser = _make_excel_parser()
    use_case = DocChunkUseCase(
        pdf_parser=_make_pdf_parser(),
        excel_parser=excel_parser,
        logger=_make_logger(),
    )
    request = _make_request(filename="data.xlsx", content=b"fake xlsx bytes")
    result = await use_case.execute(request)

    excel_parser.parse_bytes.assert_called_once()
    assert result.total_chunks >= 1


@pytest.mark.asyncio
async def test_chunk_xls_file_calls_excel_parser():
    from src.application.doc_chunk.use_case import DocChunkUseCase

    excel_parser = _make_excel_parser()
    use_case = DocChunkUseCase(
        pdf_parser=_make_pdf_parser(),
        excel_parser=excel_parser,
        logger=_make_logger(),
    )
    request = _make_request(filename="data.xls", content=b"fake xls bytes")
    await use_case.execute(request)

    excel_parser.parse_bytes.assert_called_once()


# ──────────────────────────────────────────────────────
# 지원하지 않는 파일 형식
# ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unsupported_extension_raises_value_error():
    from src.application.doc_chunk.use_case import DocChunkUseCase

    use_case = DocChunkUseCase(
        pdf_parser=_make_pdf_parser(),
        excel_parser=_make_excel_parser(),
        logger=_make_logger(),
    )
    request = _make_request(filename="archive.zip", content=b"fake zip")
    with pytest.raises(ValueError, match="Unsupported file type"):
        await use_case.execute(request)


@pytest.mark.asyncio
async def test_docx_extension_raises_value_error():
    from src.application.doc_chunk.use_case import DocChunkUseCase

    use_case = DocChunkUseCase(
        pdf_parser=_make_pdf_parser(),
        excel_parser=_make_excel_parser(),
        logger=_make_logger(),
    )
    request = _make_request(filename="word.docx", content=b"fake docx")
    with pytest.raises(ValueError, match="Unsupported file type"):
        await use_case.execute(request)


# ──────────────────────────────────────────────────────
# 전략 타입
# ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_strategy_type_reflected_in_result():
    from src.application.doc_chunk.use_case import DocChunkUseCase

    use_case = DocChunkUseCase(
        pdf_parser=_make_pdf_parser(),
        excel_parser=_make_excel_parser(),
        logger=_make_logger(),
    )
    request = _make_request(filename="doc.txt", strategy_type="full_token")
    result = await use_case.execute(request)

    assert result.strategy_used == "full_token"


@pytest.mark.asyncio
async def test_parent_child_strategy_returns_chunks():
    from src.application.doc_chunk.use_case import DocChunkUseCase

    use_case = DocChunkUseCase(
        pdf_parser=_make_pdf_parser(),
        excel_parser=_make_excel_parser(),
        logger=_make_logger(),
    )
    # parent_child needs bigger content to actually split
    content = ("sentence number one. " * 100).encode()
    request = _make_request(
        filename="doc.txt",
        strategy_type="parent_child",
        content=content,
    )
    result = await use_case.execute(request)

    assert result.total_chunks >= 1


# ──────────────────────────────────────────────────────
# LOG-001 준수
# ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_logs_info_on_start_and_complete():
    from src.application.doc_chunk.use_case import DocChunkUseCase

    logger = _make_logger()
    use_case = DocChunkUseCase(
        pdf_parser=_make_pdf_parser(),
        excel_parser=_make_excel_parser(),
        logger=logger,
    )
    await use_case.execute(_make_request(filename="doc.txt"))

    assert logger.info.call_count >= 2


@pytest.mark.asyncio
async def test_logs_error_and_reraises_on_pdf_failure():
    from src.application.doc_chunk.use_case import DocChunkUseCase

    pdf_parser = MagicMock()
    pdf_parser.get_parser_name.return_value = "pymupdf"
    pdf_parser.parse_bytes.side_effect = RuntimeError("parse error")

    logger = _make_logger()
    use_case = DocChunkUseCase(
        pdf_parser=pdf_parser,
        excel_parser=_make_excel_parser(),
        logger=logger,
    )
    request = _make_request(filename="bad.pdf", content=b"bad bytes")

    with pytest.raises(RuntimeError, match="parse error"):
        await use_case.execute(request)

    assert logger.error.call_count >= 1
    call_kwargs = logger.error.call_args.kwargs
    assert "exception" in call_kwargs


# ──────────────────────────────────────────────────────
# 청크 결과 구조
# ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chunk_items_have_required_fields():
    from src.application.doc_chunk.use_case import DocChunkUseCase

    use_case = DocChunkUseCase(
        pdf_parser=_make_pdf_parser(),
        excel_parser=_make_excel_parser(),
        logger=_make_logger(),
    )
    result = await use_case.execute(_make_request(filename="doc.txt"))

    for chunk in result.chunks:
        assert chunk.chunk_id
        assert chunk.content
        assert chunk.chunk_type in {"full", "parent", "child", "semantic"}
        assert chunk.chunk_index >= 0
