"""확장자 기반 파서 라우팅 (kb-excel-upload D3).

기존 PDF 파서를 감싸는 additive 위임 구조 — PDF 경로의 동작은 주입된
파서 인스턴스에 그대로 위임되고, 엑셀만 어댑터로 분기한다.
미지원 확장자는 파싱 시도 전에 UnsupportedFileFormatError(→422)로 거부한다.
"""
import os
from typing import List, Optional

from langchain_core.documents import Document

from src.domain.parser.exceptions import UnsupportedFileFormatError
from src.domain.parser.interfaces import PDFParserInterface
from src.domain.parser.supported_formats import (
    FORMAT_EXCEL,
    FORMAT_PDF,
    resolve_format,
)
from src.domain.parser.value_objects import ParserConfig


class ExtensionRoutingParser(PDFParserInterface):
    def __init__(
        self,
        pdf_parser: PDFParserInterface,
        excel_parser: PDFParserInterface,
    ) -> None:
        self._parsers = {
            FORMAT_PDF: pdf_parser,
            FORMAT_EXCEL: excel_parser,
        }
        self._pdf_parser = pdf_parser

    def parse(
        self,
        file_path: str,
        user_id: str,
        config: Optional[ParserConfig] = None,
    ) -> List[Document]:
        parser = self._select(os.path.basename(file_path))
        return parser.parse(file_path, user_id, config)

    def parse_bytes(
        self,
        file_bytes: bytes,
        filename: str,
        user_id: str,
        config: Optional[ParserConfig] = None,
    ) -> List[Document]:
        parser = self._select(filename)
        return parser.parse_bytes(file_bytes, filename, user_id, config)

    def get_parser_name(self) -> str:
        return "extension_routing"

    def supports_ocr(self) -> bool:
        return self._pdf_parser.supports_ocr()

    def _select(self, filename: str) -> PDFParserInterface:
        file_format = resolve_format(filename)
        if file_format is None:
            _, ext = os.path.splitext(filename)
            raise UnsupportedFileFormatError(ext.lower() or filename)
        return self._parsers[file_format]
