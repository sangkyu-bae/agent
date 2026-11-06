"""PiiRunSummaryPolicy 단위 테스트 (mock 금지) — FR-13."""

from src.domain.pii_masking.policies import PiiRunSummaryPolicy
from src.domain.pii_masking.schemas import PiiMaskingMode, PiiRunScope, PiiType


def test_render_counts_in_detection_order():
    scope = PiiRunScope(mode=PiiMaskingMode.ON)
    scope.vault.get_or_create_placeholder(PiiType.EMAIL, "a@b.com")
    scope.vault.get_or_create_placeholder(PiiType.PHONE, "010-1111-2222")
    scope.vault.get_or_create_placeholder(PiiType.PHONE, "010-3333-4444")
    assert PiiRunSummaryPolicy.render(scope) == "mode=on phone=2 email=1"


def test_render_no_detection_reports_none():
    scope = PiiRunScope(mode=PiiMaskingMode.SHADOW)
    assert PiiRunSummaryPolicy.render(scope) == "mode=shadow none"


def test_render_never_contains_values_or_placeholders():
    scope = PiiRunScope(mode=PiiMaskingMode.ON)
    scope.vault.get_or_create_placeholder(PiiType.RRN, "900101-1234567")
    rendered = PiiRunSummaryPolicy.render(scope)
    assert "900101" not in rendered
    assert "[" not in rendered
