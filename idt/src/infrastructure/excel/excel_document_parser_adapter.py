"""ExcelData→List[Document] 어댑터 (kb-excel-upload D4/D6).

PandasExcelParser를 PDFParserInterface 모양으로 감싸 UnifiedUploadUseCase에
끼울 수 있게 한다. 시트 1개 = Document 1개, metadata는 PDF 파서와 동일한
DocumentMetadata 계약(page/total_pages/parser/document_id)을 따른다 —
청킹·ES 색인·콘텐츠 브라우저가 이 키에 의존한다.
"""
from typing import List, Optional

from langchain_core.documents import Document

from src.domain.excel.entities.excel_data import ExcelData
from src.domain.excel.entities.sheet_data import SheetData
from src.domain.excel.interfaces.excel_parser_interface import (
    ExcelParserInterface,
)
from src.domain.excel.services.sheet_text_serializer import sheet_to_text
from src.domain.parser.interfaces import PDFParserInterface
from src.domain.parser.value_objects import (
    DocumentMetadata,
    ParserConfig,
    generate_document_id,
)
from src.infrastructure.logging import get_logger

logger = get_logger(__name__)


class ExcelDocumentParserAdapter(PDFParserInterface):
    def __init__(
        self,
        excel_parser: ExcelParserInterface,
        max_rows_per_sheet: int,
    ) -> None:
        self._excel_parser = excel_parser
        self._max_rows_per_sheet = max_rows_per_sheet

    def parse(
        self,
        file_path: str,
        user_id: str,
        config: Optional[ParserConfig] = None,
    ) -> List[Document]:
        excel_data = self._excel_parser.parse(file_path, user_id)
        return self._to_documents(excel_data, user_id)

    def parse_bytes(
        self,
        file_bytes: bytes,
        filename: str,
        user_id: str,
        config: Optional[ParserConfig] = None,
    ) -> List[Document]:
        try:
            excel_data = self._excel_parser.parse_bytes(
                file_bytes, filename, user_id
            )
        except ValueError:
            raise
        except Exception as e:
            logger.error(
                "Excel parsing failed", exception=e, file_name=filename
            )
            raise ValueError(f"Excel parsing failed: {e}") from e
        return self._to_documents(excel_data, user_id)

    def get_parser_name(self) -> str:
        return "pandas_excel"

    def supports_ocr(self) -> bool:
        return False

    def _to_documents(
        self, excel_data: ExcelData, user_id: str
    ) -> List[Document]:
        sheets = [s for s in excel_data.sheets.values() if not s.is_empty]
        if not sheets:
            raise ValueError(
                f"No parsable sheet in excel file '{excel_data.filename}'"
            )
        self._validate_row_limits(excel_data.filename, sheets)

        document_id = generate_document_id(excel_data.filename)
        documents: List[Document] = []
        for order, sheet in enumerate(sheets, start=1):
            metadata = DocumentMetadata(
                filename=excel_data.filename,
                user_id=user_id,
                page=order,
                total_pages=len(sheets),
                parser=self.get_parser_name(),
                document_id=document_id,
            )
            meta_dict = metadata.to_dict()
            meta_dict["sheet_name"] = sheet.sheet_name
            meta_dict["row_count"] = sheet.row_count
            documents.append(
                Document(page_content=sheet_to_text(sheet), metadata=meta_dict)
            )
        return documents

    def _validate_row_limits(
        self, filename: str, sheets: List[SheetData]
    ) -> None:
        for sheet in sheets:
            if sheet.row_count > self._max_rows_per_sheet:
                raise ValueError(
                    f"Sheet '{sheet.sheet_name}' in '{filename}' has "
                    f"{sheet.row_count} rows, exceeds limit "
                    f"{self._max_rows_per_sheet}. Split the file and retry"
                )
