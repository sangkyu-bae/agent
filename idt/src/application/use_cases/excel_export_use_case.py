"""Excel 파일 생성 UseCase.

exporter.export()는 sync 함수이므로 asyncio.to_thread()로 래핑한다.
"""
import asyncio

from src.domain.excel_export.interfaces import ExcelExporterInterface
from src.domain.excel_export.schemas import ExcelExportRequest, ExcelExportResult
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class ExcelExportUseCase:
    """ExcelExportRequest를 받아 Excel 파일 bytes를 생성하는 UseCase."""

    def __init__(
        self,
        exporter: ExcelExporterInterface,
        logger: LoggerInterface,
    ) -> None:
        self._exporter = exporter
        self._logger = logger

    async def export(self, request: ExcelExportRequest) -> ExcelExportResult:
        """Excel 파일을 생성한다.

        Args:
            request: 시트 데이터 목록 포함 요청

        Returns:
            ExcelExportResult (excel_bytes, size_bytes, sheet_count 포함)

        Raises:
            RuntimeError: 생성 중 오류 발생 시
        """
        self._logger.info(
            "Excel export started",
            request_id=request.request_id,
            user_id=request.user_id,
            sheet_count=len(request.sheets),
            exporter=self._exporter.get_exporter_name(),
        )

        try:
            result = await asyncio.to_thread(self._exporter.export, request)

            self._logger.info(
                "Excel export completed",
                request_id=request.request_id,
                size_bytes=result.size_bytes,
                sheet_count=result.sheet_count,
            )

            return result

        except Exception as exc:
            self._logger.error(
                "Excel export failed",
                exception=exc,
                request_id=request.request_id,
            )
            raise
