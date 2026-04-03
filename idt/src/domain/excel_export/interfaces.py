"""Domain interface for Excel exporter.

Implementations live in infrastructure layer.
"""
from abc import ABC, abstractmethod

from src.domain.excel_export.schemas import ExcelExportRequest, ExcelExportResult


class ExcelExporterInterface(ABC):
    """Excel 파일 생성기 추상 인터페이스."""

    @abstractmethod
    def export(self, request: ExcelExportRequest) -> ExcelExportResult:
        """ExcelExportRequest를 받아 Excel bytes를 반환한다.

        Args:
            request: 시트 데이터 목록 + 메타데이터 포함

        Returns:
            ExcelExportResult (excel_bytes, size_bytes, sheet_count 포함)

        Raises:
            RuntimeError: Excel 생성 라이브러리 오류 발생 시
        """

    @abstractmethod
    def get_exporter_name(self) -> str:
        """구현체 이름을 반환한다. 예: 'pandas+openpyxl'"""
