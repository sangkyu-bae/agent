"""PreviewExcelUseCase 테스트 (excel-preview Design §4.3, §8.2 #6~7).

검증 순서: store.load(404) → owner(403) → 확장자(415) → to_thread(파싱).
"""
from unittest.mock import MagicMock

import pytest

from src.application.excel_preview.preview_use_case import PreviewExcelUseCase
from src.application.excel_preview.schemas import ExcelPreviewResponse
from src.domain.agent_attachment.value_objects import (
    AttachmentType,
    StoredAttachment,
)
from src.domain.excel_preview.exceptions import (
    PreviewFileNotFoundError,
    PreviewForbiddenError,
    PreviewUnsupportedError,
)
from src.domain.excel_preview.value_objects import ExcelSheetData

FILE_ID = "a" * 32


def _stored(filename: str = "result.xlsx", owner: str = "7") -> StoredAttachment:
    return StoredAttachment(
        file_id=FILE_ID, type=AttachmentType.EXCEL, filename=filename,
        size=10, owner_user_id=owner, file_path=f"/tmp/{FILE_ID}.xlsx",
    )


def _sheet() -> ExcelSheetData:
    return ExcelSheetData(
        name="Sheet1", columns=["a"], rows=[["1"]],
        total_rows=2, total_cols=1, truncated=False,
    )


def _use_case(store, reader) -> PreviewExcelUseCase:
    return PreviewExcelUseCase(
        store=store, reader=reader, max_rows=100, max_cols=50,
        logger=MagicMock(),
    )


class TestPreviewExcelUseCase:
    @pytest.mark.asyncio
    async def test_success_builds_response(self):
        store = MagicMock()
        store.load.return_value = _stored()
        reader = MagicMock()
        reader.read.return_value = [_sheet()]

        res = await _use_case(store, reader).execute(
            file_id=FILE_ID, owner_user_id="7", request_id="rq1"
        )

        assert isinstance(res, ExcelPreviewResponse)
        assert res.file_id == FILE_ID
        assert res.filename == "result.xlsx"
        assert res.max_rows == 100
        assert res.max_cols == 50
        assert res.sheets[0].name == "Sheet1"
        assert res.sheets[0].rows == [["1"]]
        # 리더는 저장 경로·상한으로 호출된다
        reader.read.assert_called_once_with(f"/tmp/{FILE_ID}.xlsx", 100, 50)

    @pytest.mark.asyncio
    async def test_not_found(self):
        store = MagicMock()
        store.load.return_value = None
        reader = MagicMock()

        with pytest.raises(PreviewFileNotFoundError):
            await _use_case(store, reader).execute(
                file_id=FILE_ID, owner_user_id="7", request_id="rq1"
            )
        reader.read.assert_not_called()

    @pytest.mark.asyncio
    async def test_other_owner_forbidden(self):
        store = MagicMock()
        store.load.return_value = _stored(owner="999")
        reader = MagicMock()

        with pytest.raises(PreviewForbiddenError):
            await _use_case(store, reader).execute(
                file_id=FILE_ID, owner_user_id="7", request_id="rq1"
            )
        reader.read.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("filename", ["report.docx", "slide.pptx", "noext"])
    async def test_non_xlsx_unsupported(self, filename):
        store = MagicMock()
        store.load.return_value = _stored(filename=filename)
        reader = MagicMock()

        with pytest.raises(PreviewUnsupportedError):
            await _use_case(store, reader).execute(
                file_id=FILE_ID, owner_user_id="7", request_id="rq1"
            )
        reader.read.assert_not_called()

    @pytest.mark.asyncio
    async def test_xlsx_extension_case_insensitive(self):
        store = MagicMock()
        store.load.return_value = _stored(filename="RESULT.XLSX")
        reader = MagicMock()
        reader.read.return_value = [_sheet()]

        res = await _use_case(store, reader).execute(
            file_id=FILE_ID, owner_user_id="7", request_id="rq1"
        )
        assert res.filename == "RESULT.XLSX"

    @pytest.mark.asyncio
    async def test_validation_order_load_owner_reader(self):
        """검증 순서 고정: store.load → (owner/확장자) → reader.read (Design §4.2)."""
        parent = MagicMock()
        parent.store.load.return_value = _stored()
        parent.reader.read.return_value = [_sheet()]

        uc = PreviewExcelUseCase(
            store=parent.store, reader=parent.reader,
            max_rows=100, max_cols=50, logger=MagicMock(),
        )
        await uc.execute(file_id=FILE_ID, owner_user_id="7", request_id="rq1")

        call_names = [c[0] for c in parent.mock_calls]
        assert call_names.index("store.load") < call_names.index("reader.read")

    @pytest.mark.asyncio
    async def test_parse_failure_logs_error_with_exception_and_reraises(self):
        """파싱 실패: logger.error(exception=)로 스택 기록 후 재전파 (LOG-001)."""
        store = MagicMock()
        store.load.return_value = _stored()
        reader = MagicMock()
        boom = RuntimeError("corrupt")
        reader.read.side_effect = boom
        logger = MagicMock()

        uc = PreviewExcelUseCase(
            store=store, reader=reader, max_rows=100, max_cols=50, logger=logger,
        )
        with pytest.raises(RuntimeError):
            await uc.execute(file_id=FILE_ID, owner_user_id="7", request_id="rq1")

        assert logger.error.called
        assert logger.error.call_args.kwargs["exception"] is boom

    @pytest.mark.asyncio
    async def test_parse_runs_in_thread(self, monkeypatch):
        """FR-07: 파싱은 asyncio.to_thread로 실행해 이벤트 루프를 막지 않는다."""
        import src.application.excel_preview.preview_use_case as module

        store = MagicMock()
        store.load.return_value = _stored()
        reader = MagicMock()
        reader.read.return_value = [_sheet()]

        called = {}

        async def fake_to_thread(fn, *args):
            called["fn"] = fn
            called["args"] = args
            return fn(*args)

        monkeypatch.setattr(module.asyncio, "to_thread", fake_to_thread)
        await _use_case(store, reader).execute(
            file_id=FILE_ID, owner_user_id="7", request_id="rq1"
        )
        assert called["fn"] is reader.read
