"""UnsupportedFileFormatError — 미지원 확장자 예외 (kb-excel-upload D2)."""
import pytest

from src.domain.parser.exceptions import (
    HwpEncryptedError,
    HwpParseError,
    UnsupportedFileFormatError,
)


class TestUnsupportedFileFormatError:
    def test_is_value_error_for_router_422_mapping(self):
        # ValueError 서브클래스여야 기존 라우터 매핑(422)에 무수정 편승한다
        assert issubclass(UnsupportedFileFormatError, ValueError)

    def test_message_contains_extension_and_supported_list(self):
        with pytest.raises(UnsupportedFileFormatError) as exc_info:
            raise UnsupportedFileFormatError(".docx")
        msg = str(exc_info.value)
        assert ".docx" in msg
        assert "pdf" in msg
        assert "xlsx" in msg


class TestHwpParseErrors:
    # hwp-parser Design §6.1 — ValueError 계열이어야 기존 422 매핑을 탄다
    def test_parse_error_is_value_error(self):
        assert issubclass(HwpParseError, ValueError)

    def test_encrypted_error_is_parse_error(self):
        assert issubclass(HwpEncryptedError, HwpParseError)

    def test_encrypted_error_default_message(self):
        assert "암호" in str(HwpEncryptedError())
