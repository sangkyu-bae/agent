"""pandas + openpyxl 기반 Excel 파일 생성기 구현체."""
import io

import pandas as pd

from src.domain.excel_export.interfaces import ExcelExporterInterface
from src.domain.excel_export.schemas import ExcelExportRequest, ExcelExportResult


class PandasExcelExporter(ExcelExporterInterface):
    """pandas + openpyxl을 사용하는 Excel 파일 생성기."""

    def export(self, request: ExcelExportRequest) -> ExcelExportResult:
        try:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                for sheet in request.sheets:
                    df = pd.DataFrame(sheet.rows, columns=sheet.columns)
                    df.to_excel(writer, sheet_name=sheet.sheet_name, index=False)

            excel_bytes = output.getvalue()
            return ExcelExportResult(
                filename=request.filename,
                user_id=request.user_id,
                request_id=request.request_id,
                excel_bytes=excel_bytes,
                size_bytes=len(excel_bytes),
                sheet_count=len(request.sheets),
                exporter_used=self.get_exporter_name(),
            )
        except Exception as exc:
            raise RuntimeError(f"Excel 생성 중 오류가 발생했습니다: {exc}") from exc

    def get_exporter_name(self) -> str:
        return "pandas+openpyxl"
