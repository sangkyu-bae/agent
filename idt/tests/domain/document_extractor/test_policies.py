"""document_extractor 도메인 정책 단위 테스트 (Design §2-2).

파일 검증 · 슬롯 규칙 · 토큰 정합 · MAX_REGEN · GB6 공란 판정 — 전부 순수 규칙.
"""
import pytest

from src.domain.document_extractor.exceptions import (
    DocumentTooLargeError,
    InvalidDocumentError,
    InvalidSlotError,
    RegenLimitExceededError,
    TemplateTokenMismatchError,
)
from src.domain.document_extractor.policies import (
    DocumentFilePolicy,
    HtmlSanitizePolicy,
    RegenPolicy,
    SlotPolicy,
    SlotValuePolicy,
    TemplateTokenPolicy,
    UnfilledSlotPolicy,
)
from src.domain.document_extractor.schemas import TemplateSlot


def _slot(key="loan_amount", label="여신금액", slot_type="value", **kwargs):
    return TemplateSlot(key=key, label=label, slot_type=slot_type, **kwargs)


class TestDocumentFilePolicy:
    def test_resolve_format_pdf(self):
        assert DocumentFilePolicy.resolve_format("여신심의서.PDF") == "pdf"

    def test_resolve_format_docx(self):
        assert DocumentFilePolicy.resolve_format("form.docx") == "docx"

    def test_unsupported_extension_rejected(self):
        with pytest.raises(InvalidDocumentError):
            DocumentFilePolicy.resolve_format("scan.hwp")

    def test_no_extension_rejected(self):
        with pytest.raises(InvalidDocumentError):
            DocumentFilePolicy.resolve_format("noext")

    def test_validate_returns_format(self):
        fmt = DocumentFilePolicy.validate("a.pdf", size_bytes=100, max_file_mb=20)
        assert fmt == "pdf"

    def test_empty_file_rejected(self):
        with pytest.raises(InvalidDocumentError):
            DocumentFilePolicy.validate("a.pdf", size_bytes=0, max_file_mb=20)

    def test_oversize_rejected(self):
        with pytest.raises(DocumentTooLargeError):
            DocumentFilePolicy.validate(
                "a.pdf", size_bytes=2 * 1024 * 1024, max_file_mb=1
            )


class TestSlotPolicy:
    def test_valid_slots_pass(self):
        SlotPolicy.validate([_slot(), _slot(key="opinion", slot_type="generated")])

    def test_empty_slots_rejected(self):
        with pytest.raises(InvalidSlotError):
            SlotPolicy.validate([])

    def test_max_slots_exceeded(self):
        slots = [_slot(key=f"k_{i}") for i in range(4)]
        with pytest.raises(InvalidSlotError):
            SlotPolicy.validate(slots, max_slots=3)

    @pytest.mark.parametrize(
        "bad_key", ["Upper", "1starts_digit", "한글키", "has space", "", "a" * 51]
    )
    def test_invalid_key_pattern_rejected(self, bad_key):
        with pytest.raises(InvalidSlotError):
            SlotPolicy.validate([_slot(key=bad_key)])

    def test_duplicate_keys_rejected(self):
        with pytest.raises(InvalidSlotError):
            SlotPolicy.validate([_slot(), _slot()])

    def test_empty_label_rejected(self):
        with pytest.raises(InvalidSlotError):
            SlotPolicy.validate([_slot(label="")])

    def test_invalid_slot_type_rejected(self):
        with pytest.raises(InvalidSlotError):
            SlotPolicy.validate([_slot(slot_type="magic")])


class TestTemplateTokenPolicy:
    def test_valid_skeleton_passes(self):
        html = "<p>금액: {{loan_amount}}</p><p>소견: {{opinion}}</p>"
        slots = [_slot(), _slot(key="opinion", slot_type="generated")]
        TemplateTokenPolicy.validate(html, slots)

    def test_missing_slot_token_rejected(self):
        html = "<p>금액: {{loan_amount}}</p>"
        slots = [_slot(), _slot(key="opinion", slot_type="generated")]
        with pytest.raises(TemplateTokenMismatchError):
            TemplateTokenPolicy.validate(html, slots)

    def test_undefined_token_rejected(self):
        html = "<p>{{loan_amount}} {{ghost}}</p>"
        with pytest.raises(TemplateTokenMismatchError):
            TemplateTokenPolicy.validate(html, [_slot()])

    def test_empty_skeleton_rejected(self):
        with pytest.raises(TemplateTokenMismatchError):
            TemplateTokenPolicy.validate("   ", [_slot()])

    def test_same_token_multiple_occurrences_ok(self):
        html = "<p>{{loan_amount}} / 재확인 {{loan_amount}}</p>"
        TemplateTokenPolicy.validate(html, [_slot()])


class TestRegenPolicy:
    def test_within_limit_passes(self):
        RegenPolicy.validate(regen_count=0, max_regen=10)
        RegenPolicy.validate(regen_count=9, max_regen=10)

    def test_at_limit_rejected(self):
        with pytest.raises(RegenLimitExceededError):
            RegenPolicy.validate(regen_count=10, max_regen=10)

    def test_negative_count_rejected(self):
        with pytest.raises(RegenLimitExceededError):
            RegenPolicy.validate(regen_count=-1, max_regen=10)


class TestUnfilledSlotPolicy:
    """GB6: 미근거 = 공란 판정 + 하이라이트 마크업."""

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_unfilled_values(self, value):
        assert UnfilledSlotPolicy.is_unfilled(value) is True

    def test_filled_value(self):
        assert UnfilledSlotPolicy.is_unfilled("5억 원") is False

    def test_render_unfilled_contains_key_and_label(self):
        markup = UnfilledSlotPolicy.render_unfilled(_slot())
        assert 'data-unfilled="loan_amount"' in markup
        assert "여신금액" in markup
        assert markup.startswith("<mark")

    def test_render_unfilled_contains_text_marker(self):
        """D8: html→docx 변환(htmldocx)이 mark 스타일을 소실해도
        텍스트 표식 [미기재]는 산출물에 생존해야 한다 (PoC 실측)."""
        markup = UnfilledSlotPolicy.render_unfilled(_slot())
        assert "[미기재]" in markup


class TestSlotValuePolicy:
    def test_strips_token_braces(self):
        assert "{{" not in SlotValuePolicy.sanitize("악의적 {{ghost}} 값")
        assert "}}" not in SlotValuePolicy.sanitize("악의적 {{ghost}} 값")

    def test_normal_value_unchanged(self):
        assert SlotValuePolicy.sanitize("500,000,000원") == "500,000,000원"


class TestHtmlSanitizePolicy:
    def test_removes_script_tags(self):
        html = "<p>ok</p><script>alert(1)</script>"
        cleaned = HtmlSanitizePolicy.clean(html)
        assert "<script" not in cleaned.lower()
        assert "<p>ok</p>" in cleaned

    def test_removes_event_handler_attributes(self):
        html = '<img src="x" onerror="alert(1)"><div onclick="x()">t</div>'
        cleaned = HtmlSanitizePolicy.clean(html)
        assert "onerror" not in cleaned.lower()
        assert "onclick" not in cleaned.lower()

    def test_removes_iframe(self):
        cleaned = HtmlSanitizePolicy.clean('<iframe src="evil"></iframe><b>k</b>')
        assert "<iframe" not in cleaned.lower()
        assert "<b>k</b>" in cleaned

    def test_removes_javascript_url(self):
        cleaned = HtmlSanitizePolicy.clean('<a href="javascript:bad()">x</a>')
        assert "javascript:" not in cleaned.lower()
