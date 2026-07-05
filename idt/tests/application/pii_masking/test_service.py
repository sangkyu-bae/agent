"""application/pii_masking/pii_masking_service 단위 테스트 (mock 금지)."""
import pytest
from src.application.pii_masking.pii_masking_service import (
    MASK_FAILURE_PLACEHOLDER,
    PiiMaskingService,
)
from src.application.pii_masking.schemas import PiiMaskingConfig
from src.domain.pii_masking.schemas import PiiMatch, TokenVaultRegistry
from src.infrastructure.logging.structured_logger import StructuredLogger
from src.infrastructure.pii_masking.regex_detectors import RegexPiiDetector

ALL_TYPES = "rrn,phone,email,card,account"


class _RaisingDetector:
    """탐지 중 예외를 던지는 테스트 더블(mock 아님, 명시적 fake)."""

    def detect(self, text: str) -> list[PiiMatch]:
        raise RuntimeError("detector boom")


def _service(
    *,
    enabled: bool = True,
    types_csv: str = ALL_TYPES,
    output_redact: bool = True,
    detector=None,
) -> PiiMaskingService:
    config = PiiMaskingConfig.from_settings(
        enabled=enabled, types_csv=types_csv, output_redact=output_redact
    )
    return PiiMaskingService(
        detector=detector or RegexPiiDetector(),
        registry=TokenVaultRegistry(),
        logger=StructuredLogger(name="test-pii"),
        config=config,
    )


class TestMask:
    def test_masks_pii_with_placeholders(self):
        svc = _service()
        masked = svc.mask("주민 900101-1234567 전화 010-1234-5678", "s1")
        assert "900101-1234567" not in masked
        assert "010-1234-5678" not in masked
        assert "[RRN_1]" in masked
        assert "[PHONE_1]" in masked

    def test_same_value_same_placeholder_within_text(self):
        svc = _service()
        masked = svc.mask("010-1234-5678 와 010-1234-5678", "s1")
        assert masked.count("[PHONE_1]") == 2

    def test_disabled_type_not_masked(self):
        svc = _service(types_csv="rrn")  # phone 비활성
        masked = svc.mask("전화 010-1234-5678", "s1")
        assert "010-1234-5678" in masked

    def test_no_pii_returns_unchanged(self):
        svc = _service()
        assert svc.mask("2024년 매출 보고서", "s1") == "2024년 매출 보고서"


class TestRoundTrip:
    def test_mask_then_unmask_restores_original(self):
        svc = _service()
        original = "홍길동 900101-1234567 / hong@test.com"
        masked = svc.mask(original, "s1")
        restored = svc.unmask(masked, "s1")
        assert restored == original

    def test_multiturn_same_session_consistent_placeholder(self):
        svc = _service()
        m1 = svc.mask("내 번호 010-1234-5678", "s1")
        m2 = svc.mask("다시 010-1234-5678 확인", "s1")
        # 동일 session_id → 동일 placeholder 유지.
        assert "[PHONE_1]" in m1
        assert "[PHONE_1]" in m2

    def test_different_session_independent(self):
        svc = _service()
        svc.mask("010-1234-5678", "s1")
        m2 = svc.mask("011-9999-8888", "s2")
        # s2의 첫 전화 → [PHONE_1] (세션별 카운터 독립).
        assert "[PHONE_1]" in m2


class TestUnmaskRedaction:
    def test_unmapped_pii_in_output_redacted(self):
        svc = _service()
        # vault에 없는 신규 전화번호가 응답에 등장.
        out = svc.unmask("응답에 010-9999-8888 노출됨", "s1")
        assert "010-9999-8888" not in out
        assert "[REDACTED_PHONE]" in out

    def test_redaction_off_keeps_text(self):
        svc = _service(output_redact=False)
        out = svc.unmask("응답에 010-9999-8888", "s1")
        assert "010-9999-8888" in out

    def test_known_placeholder_restored_not_redacted(self):
        svc = _service()
        masked = svc.mask("내 번호 010-1234-5678", "s1")
        restored = svc.unmask(masked, "s1")
        assert "010-1234-5678" in restored
        assert "REDACTED" not in restored


class TestDisabled:
    def test_disabled_service_is_noop(self):
        svc = _service(enabled=False)
        text = "주민 900101-1234567"
        assert svc.mask(text, "s1") == text
        assert svc.unmask(text, "s1") == text


@pytest.mark.parametrize("text", ["", None])
class TestEmptyInput:
    def test_empty_or_none_returned_as_is(self, text):
        svc = _service()
        assert svc.mask(text, "s1") == text
        assert svc.unmask(text, "s1") == text


class TestDetectionFailureGuard:
    def test_mask_fails_closed_no_original_leak(self):
        # 탐지 예외 시 원문(PII)을 그대로 통과시키지 않는다.
        svc = _service(detector=_RaisingDetector())
        result = svc.mask("주민 900101-1234567", "s1")
        assert "900101-1234567" not in result
        assert result == MASK_FAILURE_PLACEHOLDER

    def test_unmask_does_not_raise_on_detection_error(self):
        svc = _service(detector=_RaisingDetector())
        # 예외가 호출자로 전파되지 않아야 한다.
        out = svc.unmask("응답 텍스트", "s1")
        assert isinstance(out, str)


class TestOrphanPlaceholder:
    def test_orphan_placeholder_redacted_and_warned(self):
        # vault에 없는 고아 placeholder가 응답에 등장 → [REDACTED_<TYPE>]로 대체.
        svc = _service()
        out = svc.unmask("응답에 [PHONE_9] 가 남음", "s1")
        assert "[PHONE_9]" not in out
        assert "[REDACTED_PHONE]" in out

    def test_known_placeholder_not_treated_as_orphan(self):
        svc = _service()
        masked = svc.mask("번호 010-1234-5678", "s1")
        restored = svc.unmask(masked, "s1")
        assert "010-1234-5678" in restored
        assert "REDACTED" not in restored
