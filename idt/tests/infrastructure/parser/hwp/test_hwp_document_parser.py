"""HwpDocumentParser — 섹션 텍스트 → Document 어댑터.

hwp-parser Design §2.2, §6, §8 U-10~U-12.
"""
import zlib
from unittest.mock import MagicMock, patch

import pytest
from src.domain.parser.exceptions import (
    HwpEncryptedError,
    HwpParseError,
    UnsupportedFileFormatError,
)
from src.domain.parser.interfaces import PDFParserInterface
from src.infrastructure.parser.hwp.hwp_document_parser import HwpDocumentParser


def _reader(sections=None, error=None) -> MagicMock:
    reader = MagicMock()
    if error is not None:
        reader.read_sections.side_effect = error
    else:
        reader.read_sections.return_value = sections
    return reader


def _parser(hwp=None, hwpx=None) -> HwpDocumentParser:
    return HwpDocumentParser(
        max_decompressed_mb=1,
        hwp5_reader=hwp or _reader(["hwp"]),
        hwpx_reader=hwpx or _reader(["hwpx"]),
    )


class TestContract:
    def test_is_pdf_parser_interface(self):
        assert isinstance(_parser(), PDFParserInterface)

    def test_name_and_ocr(self):
        parser = _parser()
        assert parser.get_parser_name() == "hwp"
        assert parser.supports_ocr() is False


class TestReaderSelection:
    def test_hwp_uses_hwp5_reader(self):
        hwp, hwpx = _reader(["a"]), _reader(["b"])
        docs = _parser(hwp, hwpx).parse_bytes(b"x", "공문.HWP", "u1")
        assert docs[0].page_content == "a"
        hwp.read_sections.assert_called_once_with(b"x")
        hwpx.read_sections.assert_not_called()

    def test_hwpx_uses_hwpx_reader(self):
        docs = _parser(hwpx=_reader(["b"])).parse_bytes(b"x", "공문.hwpx", "u1")
        assert docs[0].page_content == "b"
        assert docs[0].metadata["parser"] == "hwpx"

    def test_other_extension_rejected(self):
        with pytest.raises(UnsupportedFileFormatError):
            _parser().parse_bytes(b"x", "a.pdf", "u1")


class TestDocuments:
    def test_empty_sections_dropped_and_metadata(self):
        # U-10
        docs = _parser(_reader(["a", "  ", "b"])).parse_bytes(b"x", "공문.hwp", "u1")
        assert [d.page_content for d in docs] == ["a", "b"]
        meta = [d.metadata for d in docs]
        assert [m["page"] for m in meta] == [1, 2]
        assert {m["total_pages"] for m in meta} == {2}
        assert {m["parser"] for m in meta} == {"hwp"}
        assert {m["filename"] for m in meta} == {"공문.hwp"}
        assert {m["user_id"] for m in meta} == {"u1"}
        # 한 파일의 섹션은 같은 document_id를 공유한다
        assert len({m["document_id"] for m in meta}) == 1

    def test_all_empty_raises(self):
        # U-11
        with pytest.raises(ValueError, match="추출할 텍스트가 없습니다"):
            _parser(_reader(["", "\n"])).parse_bytes(b"x", "빈.hwp", "u1")


class TestErrors:
    def test_parse_error_passes_through(self):
        with pytest.raises(HwpEncryptedError):
            _parser(_reader(error=HwpEncryptedError())).parse_bytes(b"x", "a.hwp", "u1")

    def test_unexpected_error_wrapped_and_logged(self):
        # U-12
        parser = _parser(_reader(error=zlib.error("bad")))
        target = "src.infrastructure.parser.hwp.hwp_document_parser.logger"
        with patch(target) as logger, pytest.raises(HwpParseError) as exc_info:
            parser.parse_bytes(b"x", "a.hwp", "u1")
        assert isinstance(exc_info.value.__cause__, zlib.error)
        logger.error.assert_called_once()
        assert isinstance(logger.error.call_args.kwargs["exception"], zlib.error)

    def test_wrapped_parse_error_logs_cause_as_warning(self):
        # 분석 I-1 / Plan FR-07: 리더가 감싼 손상 오류는 원인 예외를 로그로 남긴다
        try:
            raise zlib.error("corrupt")
        except zlib.error as cause:
            wrapped = HwpParseError("HWP 본문 압축을 풀 수 없습니다")
            wrapped.__cause__ = cause
        parser = _parser(_reader(error=wrapped))
        target = "src.infrastructure.parser.hwp.hwp_document_parser.logger"
        with patch(target) as logger, pytest.raises(HwpParseError):
            parser.parse_bytes(b"x", "a.hwp", "u1")
        logger.warning.assert_called_once()
        kwargs = logger.warning.call_args.kwargs
        assert isinstance(kwargs["exception"], zlib.error)
        assert kwargs["file_name"] == "a.hwp"

    def test_expected_rejection_without_cause_not_logged(self):
        # 암호 문서처럼 원인 예외가 없는 정상 거부는 로그 소음을 만들지 않는다
        parser = _parser(_reader(error=HwpEncryptedError()))
        target = "src.infrastructure.parser.hwp.hwp_document_parser.logger"
        with patch(target) as logger, pytest.raises(HwpEncryptedError):
            parser.parse_bytes(b"x", "a.hwp", "u1")
        logger.warning.assert_not_called()
        logger.error.assert_not_called()


class TestParseFromPath:
    def test_reads_file_and_uses_basename(self, tmp_path):
        path = tmp_path / "문서.hwp"
        path.write_bytes(b"raw")
        hwp = _reader(["본문"])
        docs = _parser(hwp).parse(str(path), "u1")
        hwp.read_sections.assert_called_once_with(b"raw")
        assert docs[0].metadata["filename"] == "문서.hwp"


class TestDefaultReaders:
    def test_limit_passed_to_real_readers(self):
        # 설정 소비 지점: MB → 바이트로 바꿔 두 리더에 전달 (Design §10.3)
        parser = HwpDocumentParser(max_decompressed_mb=3)
        with pytest.raises(HwpParseError):
            parser.parse_bytes(b"not a real file", "a.hwpx", "u1")
        assert parser._readers[".hwp"]._max_bytes == 3 * 1024 * 1024
        assert parser._readers[".hwpx"]._max_bytes == 3 * 1024 * 1024
