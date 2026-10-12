"""섹션 텍스트 → List[Document] 어댑터.

Design Ref: §2.2 — 확장자로 리더를 고르고, 섹션 1개 = Document 1개로 만든다.
metadata는 엑셀 어댑터와 같은 DocumentMetadata 계약을 따른다 (청킹·ES·콘텐츠
브라우저가 page/total_pages/parser/document_id 키에 의존).
Design Ref: §6.1 — HwpParseError는 그대로 통과, 예상 밖 예외는 로그 후 감싼다.
"""
import os
from pathlib import PurePosixPath, PureWindowsPath

from langchain_core.documents import Document

from src.domain.parser.exceptions import HwpParseError, UnsupportedFileFormatError
from src.domain.parser.interfaces import PDFParserInterface
from src.domain.parser.value_objects import (
    DocumentMetadata,
    ParserConfig,
    generate_document_id,
)
from src.infrastructure.logging import get_logger
from src.infrastructure.parser.hwp._types import HwpSectionReader
from src.infrastructure.parser.hwp.hwp5_reader import Hwp5Reader
from src.infrastructure.parser.hwp.hwpx_reader import HwpxReader

logger = get_logger(__name__)


class HwpDocumentParser(PDFParserInterface):
    def __init__(
        self,
        max_decompressed_mb: int,
        hwp5_reader: HwpSectionReader | None = None,
        hwpx_reader: HwpSectionReader | None = None,
    ) -> None:
        """max_decompressed_mb: settings.kb_hwp_max_decompressed_mb (Design §10.3)."""
        limit = max_decompressed_mb * 1024 * 1024
        self._readers: dict[str, HwpSectionReader] = {
            ".hwp": hwp5_reader or Hwp5Reader(max_decompressed_bytes=limit),
            ".hwpx": hwpx_reader or HwpxReader(max_decompressed_bytes=limit),
        }

    def parse(
        self,
        file_path: str,
        user_id: str,
        config: ParserConfig | None = None,
    ) -> list[Document]:
        with open(file_path, "rb") as f:
            data = f.read()
        return self.parse_bytes(data, os.path.basename(file_path), user_id, config)

    def parse_bytes(
        self,
        file_bytes: bytes,
        filename: str,
        user_id: str,
        config: ParserConfig | None = None,
    ) -> list[Document]:
        suffix = _suffix_of(filename)
        reader = self._readers.get(suffix)
        if reader is None:
            raise UnsupportedFileFormatError(suffix or filename)
        sections = self._read(reader, file_bytes, filename)
        documents = self._to_documents(sections, filename, user_id, suffix)
        logger.info(
            "HWP parsed", file_name=filename, section_count=len(documents)
        )
        return documents

    def get_parser_name(self) -> str:
        return "hwp"

    def supports_ocr(self) -> bool:
        return False

    @staticmethod
    def _read(reader: HwpSectionReader, data: bytes, filename: str) -> list[str]:
        try:
            return reader.read_sections(data)
        except HwpParseError as e:
            # Plan FR-07: 리더가 감싼 손상 오류는 원인 예외를 남긴다.
            # 암호 문서처럼 원인 예외가 없는 정상 거부는 남기지 않는다.
            if e.__cause__ is not None:
                logger.warning(
                    "HWP parse rejected",
                    exception=e.__cause__,
                    file_name=filename,
                    reason=str(e),
                )
            raise
        except Exception as e:
            logger.error("HWP parsing failed", exception=e, file_name=filename)
            raise HwpParseError(f"한글 문서를 읽을 수 없습니다: {filename}") from e

    @staticmethod
    def _to_documents(
        sections: list[str], filename: str, user_id: str, suffix: str
    ) -> list[Document]:
        texts = [s for s in sections if s.strip()]
        if not texts:
            raise ValueError(f"'{filename}'에서 추출할 텍스트가 없습니다")
        document_id = generate_document_id(filename)
        documents: list[Document] = []
        for page, text in enumerate(texts, start=1):
            metadata = DocumentMetadata(
                filename=filename,
                user_id=user_id,
                page=page,
                total_pages=len(texts),
                parser=suffix.lstrip("."),
                document_id=document_id,
            )
            documents.append(Document(page_content=text, metadata=metadata.to_dict()))
        return documents


def _suffix_of(filename: str) -> str:
    # supported_formats와 같은 규칙 — 경로 구분자가 섞여도 basename 확장자만 본다
    return PurePosixPath(PureWindowsPath(filename).name).suffix.lower()
