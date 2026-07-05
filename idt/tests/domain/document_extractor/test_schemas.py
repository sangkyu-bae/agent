"""TemplateSlot / DocumentTemplate 도메인 스키마 단위 테스트."""
import pytest

from src.domain.document_extractor.schemas import TemplateSlot


def _slot(**kwargs) -> TemplateSlot:
    base = dict(key="loan_amount", label="여신금액", slot_type="value")
    base.update(kwargs)
    return TemplateSlot(**base)


class TestTemplateSlot:
    def test_anchor_is_double_brace_token(self):
        assert _slot(key="loan_amount").anchor == "{{loan_amount}}"

    def test_slot_is_frozen(self):
        slot = _slot()
        with pytest.raises(AttributeError):
            slot.key = "other"

    def test_optional_fields_default_empty(self):
        slot = _slot()
        assert slot.description == ""
        assert slot.fill_hint == ""
        assert slot.sample_value == ""
