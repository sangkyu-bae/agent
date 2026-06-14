"""AttachmentPolicy 검증 규칙 테스트 (Design §8.2)."""
import pytest

from src.domain.agent_attachment.exceptions import (
    AttachmentTooLargeError,
    InvalidAttachmentError,
)
from src.domain.agent_attachment.policies import AttachmentPolicy
from src.domain.agent_attachment.value_objects import AttachmentType

MAX = 10 * 1024 * 1024


class TestResolveType:
    @pytest.mark.parametrize("name", ["sales.xlsx", "REPORT.XLS", "a.b.xlsx"])
    def test_excel_extensions_resolve_to_excel(self, name: str) -> None:
        assert AttachmentPolicy.resolve_type(name) == AttachmentType.EXCEL

    @pytest.mark.parametrize("name", ["data.csv", "image.png", "noext", "x.pdf"])
    def test_unsupported_extension_raises(self, name: str) -> None:
        with pytest.raises(InvalidAttachmentError):
            AttachmentPolicy.resolve_type(name)


class TestValidate:
    def test_valid_excel_returns_type(self) -> None:
        assert AttachmentPolicy.validate("a.xlsx", 1024, MAX) == AttachmentType.EXCEL

    def test_empty_file_raises_invalid(self) -> None:
        with pytest.raises(InvalidAttachmentError):
            AttachmentPolicy.validate("a.xlsx", 0, MAX)

    def test_oversize_raises_too_large(self) -> None:
        with pytest.raises(AttachmentTooLargeError):
            AttachmentPolicy.validate("a.xlsx", MAX + 1, MAX)

    def test_unsupported_ext_raises_before_size_check(self) -> None:
        with pytest.raises(InvalidAttachmentError):
            AttachmentPolicy.validate("a.csv", MAX + 1, MAX)
