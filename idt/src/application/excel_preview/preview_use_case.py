"""PreviewExcelUseCase (excel-preview Design §4.3).

검증 순서: store.load(404) → owner(403) → 확장자(415) → to_thread(파싱, 422)
— 다운로드 라우트와 동일한 저장소·검증 공유 (FR-01).
"""
import asyncio
import time

from src.application.excel_preview.schemas import (
    ExcelPreviewResponse,
    ExcelPreviewSheet,
)
from src.domain.excel_preview.exceptions import (
    PreviewFileNotFoundError,
    PreviewForbiddenError,
    PreviewUnsupportedError,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class PreviewExcelUseCase:
    def __init__(
        self,
        store,
        reader,
        max_rows: int,
        max_cols: int,
        logger: LoggerInterface,
    ) -> None:
        self._store = store      # AgentAttachmentStore (다운로드와 동일 인스턴스)
        self._reader = reader    # ExcelPreviewReader (duck-typing 주입, Design §4.3)
        self._max_rows = max_rows
        self._max_cols = max_cols
        self._logger = logger

    async def execute(
        self, file_id: str, owner_user_id: str, request_id: str
    ) -> ExcelPreviewResponse:
        self._logger.info(
            "PreviewExcelUseCase start", request_id=request_id, file_id=file_id
        )
        stored = self._store.load(file_id)
        if stored is None:
            self._warn("file not found or expired", request_id, file_id)
            raise PreviewFileNotFoundError("파일을 찾을 수 없거나 만료되었습니다.")
        if stored.owner_user_id != owner_user_id:
            self._warn("owner mismatch", request_id, file_id)
            raise PreviewForbiddenError("본인이 생성한 파일만 미리볼 수 있습니다.")
        if not stored.filename.lower().endswith(".xlsx"):
            self._warn("unsupported extension", request_id, file_id)
            raise PreviewUnsupportedError("미리보기는 .xlsx 파일만 지원합니다.")

        started = time.perf_counter()
        # (LOG-001: 비즈니스 오류는 WARNING, 시스템 오류는 ERROR+스택)
        try:
            sheets = await asyncio.to_thread(
                self._reader.read, stored.file_path, self._max_rows, self._max_cols
            )
        except Exception as e:
            self._logger.error(
                "PreviewExcelUseCase parse failed",
                exception=e, request_id=request_id, file_id=file_id,
            )
            raise

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        self._logger.info(
            "PreviewExcelUseCase done",
            request_id=request_id, file_id=file_id,
            sheet_count=len(sheets), elapsed_ms=elapsed_ms,
        )
        return ExcelPreviewResponse(
            file_id=file_id,
            filename=stored.filename,
            max_rows=self._max_rows,
            max_cols=self._max_cols,
            sheets=[ExcelPreviewSheet.from_domain(s) for s in sheets],
        )

    def _warn(self, reason: str, request_id: str, file_id: str) -> None:
        self._logger.warning(
            f"PreviewExcelUseCase rejected: {reason}",
            request_id=request_id, file_id=file_id,
        )
