"""UnsupportedFileFormatError — 미지원 확장자 예외 (kb-excel-upload D2)."""
import pytest

from src.domain.parser.exceptions import UnsupportedFileFormatError


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
