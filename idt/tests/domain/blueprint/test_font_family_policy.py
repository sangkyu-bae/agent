"""FontFamilyPolicy (pptx-font-fidelity §3.2 / FR-01) — 폰트명 정규화."""

import pytest
from src.domain.blueprint.policies import FontFamilyPolicy


@pytest.mark.parametrize(
    "source,family,bold",
    [
        ("Malgun Gothic Regular", "Malgun Gothic", False),
        ("Malgun Gothic Bold", "Malgun Gothic", True),
        ("NanumSquare ExtraBold Italic", "NanumSquare", True),
        ("Pretendard-SemiBold", "Pretendard", True),
        ("Noto Sans KR Light", "Noto Sans KR", False),
        ("맑은 고딕", "맑은 고딕", False),
    ],
)
def test_normalize_strips_subfamily_tokens(source, family, bold):
    assert FontFamilyPolicy.normalize(source) == (family, bold)


def test_normalize_removes_pdf_subset_prefix():
    family, bold = FontFamilyPolicy.normalize("ABCDEF+MalgunGothicBold")
    assert "+" not in family
    assert family == "MalgunGothicBold"  # 무공백 명칭의 토큰 분해는 하지 않는다
    assert bold is False


def test_normalize_keeps_name_made_only_of_tokens():
    """전부 제거되면 원본을 유지한다 (폰트명 자체가 'Black' 인 경우)."""
    assert FontFamilyPolicy.normalize("Black") == ("Black", False)


def test_normalize_handles_empty_and_whitespace():
    assert FontFamilyPolicy.normalize("") == ("", False)
    assert FontFamilyPolicy.normalize("   ") == ("", False)


def test_normalize_is_idempotent():
    once, _ = FontFamilyPolicy.normalize("Malgun Gothic Bold")
    twice, _ = FontFamilyPolicy.normalize(once)
    assert once == twice == "Malgun Gothic"


def test_normalize_strip_key_drops_tokens_without_separator():
    """별칭 매칭용 비교키는 무공백 명칭에서도 접미사를 떼어낸다."""
    assert FontFamilyPolicy.alias_key("MalgunGothicRegular") == "malgungothic"
    assert FontFamilyPolicy.alias_key("Malgun Gothic Bold") == "malgungothic"
    assert FontFamilyPolicy.alias_key("맑은 고딕") == "맑은고딕"


# ── blueprint-font-mapping-migration FR-06 — 보호 패밀리 ────────────────────


@pytest.mark.parametrize(
    "source,family,bold",
    [
        # 마지막 토큰이 서브패밀리 토큰이지만 실존 패밀리명의 일부다
        ("Times New Roman", "Times New Roman", False),
        ("Arial Black", "Arial Black", False),
        # 보호 패밀리 + 진짜 서브패밀리 접미사 → 접미사만 떨어진다 (설계 DR-4)
        ("Arial Black Italic", "Arial Black", False),
        ("Times New Roman Bold", "Times New Roman", True),
        # 서브셋 프리픽스를 벗겨 낸 뒤에도 보호가 적용된다
        ("ABCDEF+Times New Roman", "Times New Roman", False),
        # 회귀: 보호 대상이 아닌 이름은 기존대로 축약된다
        ("Franklin Gothic Book", "Franklin Gothic", False),
        ("Segoe UI Light", "Segoe UI", False),
        ("Malgun Gothic Bold", "Malgun Gothic", True),
    ],
)
def test_normalize_protects_known_families(source, family, bold):
    assert FontFamilyPolicy.normalize(source) == (family, bold)


def test_protected_family_normalization_is_idempotent():
    once, _ = FontFamilyPolicy.normalize("Times New Roman")
    twice, _ = FontFamilyPolicy.normalize(once)
    assert once == twice == "Times New Roman"
