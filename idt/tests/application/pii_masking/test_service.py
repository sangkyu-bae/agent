"""application/pii_masking/pii_masking_service 단위 테스트 (mock 금지)."""
import pytest
from src.application.pii_masking.pii_masking_service import (
    MASK_FAILURE_PLACEHOLDER,
    PiiMaskingService,
)
from src.application.pii_masking.schemas import PiiMaskingConfig
from src.domain.pii_masking.schemas import (
    PiiMaskingMode,
    PiiMatch,
    PiiRunScope,
    PiiType,
)
from src.infrastructure.pii_masking.regex_detectors import RegexPiiDetector

ALL_TYPES = "rrn,phone,email,card,account"


class _RaisingDetector:
    """탐지 중 예외를 던지는 테스트 더블(mock 아님, 명시적 fake)."""

    def detect(self, text: str) -> list[PiiMatch]:
        raise RuntimeError("detector boom")


class _RecordingLogger:
    """로그 인자를 모아 원본 PII 기록 여부를 검사한다."""

    def __init__(self) -> None:
        self.records: list[tuple[str, str, dict]] = []

    def _log(self, level: str, message: str, **kwargs) -> None:
        self.records.append((level, message, kwargs))

    def debug(self, message: str, **kwargs) -> None:
        self._log("debug", message, **kwargs)

    def info(self, message: str, **kwargs) -> None:
        self._log("info", message, **kwargs)

    def warning(self, message: str, **kwargs) -> None:
        self._log("warning", message, **kwargs)

    def error(self, message: str, **kwargs) -> None:
        self._log("error", message, **kwargs)

    def critical(self, message: str, **kwargs) -> None:
        self._log("critical", message, **kwargs)

    def dump(self) -> str:
        return repr(self.records)


def _service(
    *,
    mode: str = "on",
    types_csv: str = ALL_TYPES,
    detector=None,
    logger=None,
) -> PiiMaskingService:
    config = PiiMaskingConfig.from_settings(mode=mode, types_csv=types_csv)
    return PiiMaskingService(
        detector=detector or RegexPiiDetector(),
        logger=logger or _RecordingLogger(),
        config=config,
    )


class TestConfig:
    def test_from_settings_unknown_type_raises(self):
        # Design D-02 취지: 오타가 특정 타입 보호를 조용히 끄면 안 된다.
        with pytest.raises(ValueError):
            PiiMaskingConfig.from_settings(mode="on", types_csv="rrn,phon")

    def test_from_settings_empty_types_raises(self):
        with pytest.raises(ValueError):
            PiiMaskingConfig.from_settings(mode="on", types_csv=" , ")

    def test_from_settings_unknown_mode_raises(self):
        with pytest.raises(ValueError):
            PiiMaskingConfig.from_settings(mode="onn", types_csv=ALL_TYPES)


class TestNewScope:
    def test_new_scope_uses_configured_mode(self):
        assert _service(mode="shadow").new_scope().mode is PiiMaskingMode.SHADOW

    def test_new_scope_returns_fresh_vault_each_call(self):
        svc = _service()
        assert svc.new_scope().vault is not svc.new_scope().vault


class TestMaskOn:
    def test_mask_text_pii_replaced_with_placeholders(self):
        svc = _service()
        text = "주민 900101-1234567 전화 010-1234-5678"
        masked = svc.mask_text(text, svc.new_scope())
        assert masked == "주민 [RRN_1] 전화 [PHONE_1]"

    def test_mask_text_particle_attached_keeps_particle(self):
        svc = _service()
        assert svc.mask_text("010-1234-5678로 보내줘", svc.new_scope()) == (
            "[PHONE_1]로 보내줘"
        )

    def test_mask_text_same_value_same_placeholder(self):
        svc = _service()
        masked = svc.mask_text("010-1234-5678 와 010-1234-5678", svc.new_scope())
        assert masked.count("[PHONE_1]") == 2

    def test_mask_text_second_call_same_scope_keeps_placeholder(self):
        svc = _service()
        scope = svc.new_scope()
        svc.mask_text("010-1234-5678", scope)
        assert svc.mask_text("다시 010-1234-5678 확인", scope) == "다시 [PHONE_1] 확인"

    def test_mask_text_different_scope_independent(self):
        svc = _service()
        svc.mask_text("010-1234-5678", svc.new_scope())
        assert svc.mask_text("011-999-8888", svc.new_scope()) == "[PHONE_1]"

    def test_mask_text_disabled_type_not_masked(self):
        svc = _service(types_csv="rrn")
        text = "전화 010-1234-5678"
        assert svc.mask_text(text, svc.new_scope()) == text

    def test_mask_text_no_pii_returns_unchanged(self):
        svc = _service()
        text = "2024년 매출 보고서"
        assert svc.mask_text(text, svc.new_scope()) == text

    def test_mask_text_literal_placeholder_not_collided(self):
        svc = _service()
        scope = svc.new_scope()
        masked = svc.mask_text("양식 [PHONE_1] 칸에 010-1234-5678", scope)
        assert masked == "양식 [PHONE_1] 칸에 [PHONE_2]"
        assert svc.restore_text(masked, scope) == "양식 [PHONE_1] 칸에 010-1234-5678"


class TestRoundTrip:
    def test_restore_text_after_mask_returns_original(self):
        svc = _service()
        scope = svc.new_scope()
        original = "홍길동 900101-1234567 / hong@test.com입니다"
        assert svc.restore_text(svc.mask_text(original, scope), scope) == original


class TestRestoreOrphan:
    def test_restore_text_orphan_placeholder_redacted(self):
        svc = _service()
        assert svc.restore_text("남은 [PHONE_9] 값", svc.new_scope()) == (
            "남은 [REDACTED_PHONE] 값"
        )

    def test_restore_known_text_keeps_orphan_placeholder(self):
        svc = _service()
        scope = svc.new_scope()
        svc.mask_text("010-1234-5678", scope)
        assert svc.restore_known_text("[PHONE_1] [PHONE_9]", scope) == (
            "010-1234-5678 [PHONE_9]"
        )

    def test_restore_known_text_shadow_returns_original(self):
        svc = _service(mode="shadow")
        scope = svc.new_scope()
        svc.mask_text("010-1234-5678", scope)
        assert svc.restore_known_text("[PHONE_1]", scope) == "[PHONE_1]"

    def test_restore_text_unmapped_pii_left_as_is(self):
        # Design D-05: 미매핑 PII redact 제거. 정상 도구 인자를 훼손하지 않는다.
        svc = _service()
        text = "응답에 010-9999-8888 노출"
        assert svc.restore_text(text, svc.new_scope()) == text

    def test_has_orphan_unknown_placeholder_returns_true(self):
        svc = _service()
        assert svc.has_orphan({"to": ["[EMAIL_9]"]}, svc.new_scope()) is True

    def test_has_orphan_plain_args_returns_false(self):
        svc = _service()
        assert svc.has_orphan({"to": "a@b.com", "n": 1}, svc.new_scope()) is False


class TestShadow:
    def test_mask_text_shadow_returns_original(self):
        svc = _service(mode="shadow")
        text = "전화 010-1234-5678"
        assert svc.mask_text(text, svc.new_scope()) == text

    def test_mask_text_shadow_records_unique_counts(self):
        svc = _service(mode="shadow")
        scope = svc.new_scope()
        svc.mask_text("010-1234-5678, 010-1234-5678", scope)
        assert scope.vault.counts() == {PiiType.PHONE: 1}

    def test_restore_text_shadow_returns_original(self):
        svc = _service(mode="shadow")
        text = "남은 [PHONE_9] 값"
        assert svc.restore_text(text, svc.new_scope()) == text

    def test_mask_text_shadow_detection_error_returns_original(self):
        svc = _service(mode="shadow", detector=_RaisingDetector())
        text = "주민 900101-1234567"
        assert svc.mask_text(text, svc.new_scope()) == text


class TestInspect:
    def test_inspect_nested_value_counts_occurrences(self):
        svc = _service()
        value = {"to": ["010-1234-5678", "a@b.com"], "memo": "010-1234-5678로", "n": 3}
        assert svc.inspect(value) == {PiiType.PHONE: 2, PiiType.EMAIL: 1}

    def test_inspect_no_pii_returns_empty(self):
        assert _service().inspect({"q": "규정 알려줘"}) == {}

    def test_inspect_detection_error_returns_empty(self):
        # Design §6.2: 검사가 도구 실행을 막지 않는다.
        assert _service(detector=_RaisingDetector()).inspect("x") == {}


class TestFindOrphanArgument:
    """Check G-3 — 도구 인자 고아 차단은 on 모드에서만 한다."""

    def test_on_mode_returns_placeholder_in_nested_args(self):
        args = {"to": ["[EMAIL_9]"], "body": "b"}
        assert _service().find_orphan_argument(args) == "[EMAIL_9]"

    def test_on_mode_without_placeholder_returns_none(self):
        assert _service().find_orphan_argument({"to": "a@b.com"}) is None

    def test_shadow_mode_never_blocks(self):
        # shadow 는 LLM 이 placeholder 를 받은 적이 없어 지어낼 수 없다.
        # 사용자가 입력한 같은 모양의 문자열은 그대로 도구에 가야 한다.
        args = {"subject": "[EMAIL_1] 회신 요청"}
        assert _service(mode="shadow").find_orphan_argument(args) is None


@pytest.mark.parametrize("text", ["", None])
class TestEmptyInput:
    def test_mask_and_restore_empty_returned_as_is(self, text):
        svc = _service()
        scope = svc.new_scope()
        assert svc.mask_text(text, scope) == text
        assert svc.restore_text(text, scope) == text


class TestDetectionFailureGuard:
    def test_mask_text_on_detection_error_fails_closed(self):
        svc = _service(detector=_RaisingDetector())
        result = svc.mask_text("주민 900101-1234567", svc.new_scope())
        assert result == MASK_FAILURE_PLACEHOLDER


class TestLoggingNoPii:
    def test_logs_never_contain_original_or_placeholder(self):
        logger = _RecordingLogger()
        svc = _service(logger=logger)
        scope: PiiRunScope = svc.new_scope()
        masked = svc.mask_text("주민 900101-1234567, a@b.com", scope)
        svc.restore_text(masked + " [PHONE_9]", scope)
        svc.inspect("010-1234-5678")
        dump = logger.dump()
        assert logger.records
        for value in ("900101-1234567", "a@b.com", "010-1234-5678", "[PHONE_9]"):
            assert value not in dump
