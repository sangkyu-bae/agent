"""Tests for ExcelUploadUseCase."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from langchain_core.documents import Document

from src.application.use_cases.excel_upload_use_case import ExcelUploadUseCase
from src.domain.excel.entities.excel_data import ExcelData
from src.domain.excel.entities.sheet_data import SheetData
from src.domain.excel.value_objects.excel_metadata import ExcelMetadata
from src.domain.vector.value_objects import DocumentId


def _make_excel_data(file_id: str = "file-abc", filename: str = "test.xlsx") -> ExcelData:
    sheet = SheetData(
        sheet_name="Sheet1",
        data=[
            {"이름": "홍길동", "나이": 30, "부서": "개발"},
            {"이름": "김철수", "나이": 25, "부서": "기획"},
        ],
        columns=["이름", "나이", "부서"],
    )
    metadata = ExcelMetadata(
        file_id=file_id,
        filename=filename,
        sheet_names=["Sheet1"],
        total_rows=2,
        user_id="user-001",
    )
    return ExcelData(
        file_id=file_id,
        filename=filename,
        sheets={"Sheet1": sheet},
        metadata=metadata,
    )


class TestExcelUploadUseCase:
    def setup_method(self):
        self.excel_parser = MagicMock()
        self.chunking_strategy = MagicMock()
        self.vectorstore = MagicMock()
        self.embedding = MagicMock()
        self.logger = MagicMock()

        self.use_case = ExcelUploadUseCase(
            excel_parser=self.excel_parser,
            chunking_strategy=self.chunking_strategy,
            vectorstore=self.vectorstore,
            embedding=self.embedding,
            logger=self.logger,
        )

    @pytest.mark.asyncio
    async def test_execute_returns_completed_status(self):
        excel_data = _make_excel_data()
        self.excel_parser.parse_bytes.return_value = excel_data

        chunk_doc = Document(
            page_content="이름: 홍길동 | 나이: 30",
            metadata={"chunk_type": "full", "chunk_index": 0},
        )
        self.chunking_strategy.chunk.return_value = [chunk_doc]
        self.embedding.embed_documents = AsyncMock(return_value=[[0.1] * 5])
        self.vectorstore.add_documents = AsyncMock(
            return_value=[DocumentId("stored-id-1")]
        )

        result = await self.use_case.execute(
            file_bytes=b"fake-bytes",
            filename="test.xlsx",
            user_id="user-001",
            request_id="req-001",
        )

        assert result.status == "completed"
        assert result.filename == "test.xlsx"
        assert result.sheet_count == 1
        assert result.chunk_count == 1
        assert result.stored_ids == ["stored-id-1"]
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_execute_calls_parser_with_file_bytes(self):
        excel_data = _make_excel_data()
        self.excel_parser.parse_bytes.return_value = excel_data
        self.chunking_strategy.chunk.return_value = []
        self.embedding.embed_documents = AsyncMock(return_value=[])
        self.vectorstore.add_documents = AsyncMock(return_value=[])

        await self.use_case.execute(
            file_bytes=b"some-bytes",
            filename="data.xlsx",
            user_id="user-002",
            request_id="req-002",
        )

        self.excel_parser.parse_bytes.assert_called_once_with(
            b"some-bytes", "data.xlsx", "user-002"
        )

    @pytest.mark.asyncio
    async def test_execute_converts_sheets_to_documents(self):
        excel_data = _make_excel_data()
        self.excel_parser.parse_bytes.return_value = excel_data

        captured_docs = []

        def capture_chunk(docs):
            captured_docs.extend(docs)
            return []

        self.chunking_strategy.chunk.side_effect = capture_chunk
        self.embedding.embed_documents = AsyncMock(return_value=[])
        self.vectorstore.add_documents = AsyncMock(return_value=[])

        await self.use_case.execute(
            file_bytes=b"bytes",
            filename="test.xlsx",
            user_id="user-001",
            request_id="req-003",
        )

        assert len(captured_docs) == 1
        doc = captured_docs[0]
        assert isinstance(doc, Document)
        assert "홍길동" in doc.page_content
        assert doc.metadata["sheet_name"] == "Sheet1"
        assert doc.metadata["user_id"] == "user-001"

    @pytest.mark.asyncio
    async def test_execute_returns_failed_on_parse_error(self):
        self.excel_parser.parse_bytes.side_effect = ValueError("Invalid Excel format")

        result = await self.use_case.execute(
            file_bytes=b"bad-bytes",
            filename="bad.xlsx",
            user_id="user-001",
            request_id="req-004",
        )

        assert result.status == "failed"
        assert len(result.errors) > 0
        assert "Invalid Excel format" in result.errors[0]

    @pytest.mark.asyncio
    async def test_execute_logs_info_on_start_and_complete(self):
        excel_data = _make_excel_data()
        self.excel_parser.parse_bytes.return_value = excel_data
        self.chunking_strategy.chunk.return_value = []
        self.embedding.embed_documents = AsyncMock(return_value=[])
        self.vectorstore.add_documents = AsyncMock(return_value=[])

        await self.use_case.execute(
            file_bytes=b"bytes",
            filename="report.xlsx",
            user_id="user-001",
            request_id="req-005",
        )

        assert self.logger.info.call_count >= 2

    @pytest.mark.asyncio
    async def test_execute_logs_error_on_exception(self):
        self.excel_parser.parse_bytes.side_effect = RuntimeError("Unexpected error")

        await self.use_case.execute(
            file_bytes=b"bytes",
            filename="err.xlsx",
            user_id="user-001",
            request_id="req-006",
        )

        self.logger.error.assert_called_once()
        call_kwargs = self.logger.error.call_args
        assert call_kwargs.kwargs.get("exception") is not None

    @pytest.mark.asyncio
    async def test_execute_multiple_sheets(self):
        sheet1 = SheetData(
            sheet_name="시트1",
            data=[{"A": 1}],
            columns=["A"],
        )
        sheet2 = SheetData(
            sheet_name="시트2",
            data=[{"B": 2}, {"B": 3}],
            columns=["B"],
        )
        metadata = ExcelMetadata(
            file_id="multi-id",
            filename="multi.xlsx",
            sheet_names=["시트1", "시트2"],
            total_rows=3,
            user_id="user-001",
        )
        excel_data = ExcelData(
            file_id="multi-id",
            filename="multi.xlsx",
            sheets={"시트1": sheet1, "시트2": sheet2},
            metadata=metadata,
        )
        self.excel_parser.parse_bytes.return_value = excel_data

        captured_docs = []

        def capture_chunk(docs):
            captured_docs.extend(docs)
            return docs

        self.chunking_strategy.chunk.side_effect = capture_chunk
        self.embedding.embed_documents = AsyncMock(return_value=[[0.1] * 5, [0.2] * 5])
        self.vectorstore.add_documents = AsyncMock(
            return_value=[DocumentId("id1"), DocumentId("id2")]
        )

        result = await self.use_case.execute(
            file_bytes=b"bytes",
            filename="multi.xlsx",
            user_id="user-001",
            request_id="req-007",
        )

        assert result.sheet_count == 2
        assert len(captured_docs) == 2
