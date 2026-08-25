"""FontCatalog (FR-07) — 설치 폰트 스캔·기본 폰트·매핑 제안."""

from pathlib import Path

from src.infrastructure.blueprint.fonts import FontCatalog


def _dir(tmp_path: Path) -> Path:
    for name in (
        "NanumGothic.ttf",
        "NanumGothicBold.ttf",
        "NotoSansKR-Regular.otf",
        "readme.txt",
    ):
        (tmp_path / name).write_bytes(b"x")
    return tmp_path


def test_installed_lists_font_files_sorted_without_extension(tmp_path):
    cat = FontCatalog(font_dir=_dir(tmp_path), default="NanumGothic")
    assert cat.installed() == ("NanumGothic", "NanumGothicBold", "NotoSansKR-Regular")
    assert cat.default_font() == "NanumGothic"


def test_missing_dir_yields_only_default(tmp_path):
    cat = FontCatalog(font_dir=tmp_path / "nope", default="Arial")
    assert cat.installed() == ()
    assert cat.default_font() == "Arial"
    assert cat.suggest("Anything") is None


def test_suggest_exact_normalized_and_bold_variant(tmp_path):
    cat = FontCatalog(font_dir=_dir(tmp_path), default="NanumGothic")
    assert cat.suggest("NanumGothic") == "NanumGothic"
    assert cat.suggest("nanum gothic") == "NanumGothic"
    assert cat.suggest("NanumGothic-Bold") == "NanumGothicBold"
    assert cat.suggest("Helvetica-Bold") is None


def test_suggest_uses_known_aliases(tmp_path):
    cat = FontCatalog(font_dir=_dir(tmp_path), default="NanumGothic")
    assert (
        cat.suggest("맑은 고딕") == "NanumGothic"
    )  # 별칭 표: 한글 고딕 계열 → 설치된 고딕
    assert cat.suggest("Malgun Gothic") == "NanumGothic"


def test_propose_mapping_keeps_unknown_font_as_is(tmp_path):
    """style-fidelity FR-01 (DR-3): 미설치 폰트는 원본명 유지 + 경고."""
    cat = FontCatalog(font_dir=_dir(tmp_path), default="NanumGothic")
    mapping, warnings = cat.propose_mapping(("NanumGothicBold", "HY헤드라인M"))
    assert mapping == {
        "NanumGothicBold": "NanumGothicBold",
        "HY헤드라인M": "HY헤드라인M",
    }
    assert warnings == ("font 'HY헤드라인M' not installed — kept as-is",)


def test_propose_mapping_normalizes_subfamily_without_catalog():
    """pptx-font-fidelity FR-01: 미설치라도 서브패밀리 접미사는 떼어 낸다."""
    cat = FontCatalog(font_dir=None, default="NanumGothic")
    mapping, warnings = cat.propose_mapping(
        ("Malgun Gothic Bold", "Malgun Gothic Regular")
    )
    assert mapping == {
        "Malgun Gothic Bold": "Malgun Gothic",
        "Malgun Gothic Regular": "Malgun Gothic",
    }
    assert warnings == ()  # 정규화에 성공했으므로 경고 없음


def test_propose_mapping_warns_only_when_name_is_unchanged():
    cat = FontCatalog(font_dir=None, default="NanumGothic")
    mapping, warnings = cat.propose_mapping(("HY헤드라인M",))
    assert mapping == {"HY헤드라인M": "HY헤드라인M"}
    assert warnings == ("font 'HY헤드라인M' not installed — kept as-is",)


def test_suggest_matches_installed_font_after_normalization(tmp_path):
    cat = FontCatalog(font_dir=_dir(tmp_path), default="NanumGothic")
    assert cat.suggest("NanumGothic Regular") == "NanumGothic"
    assert cat.suggest("NanumGothicBold") == "NanumGothicBold"  # 설치명 정확 일치 우선


def test_suggest_alias_ignores_weight_and_prefers_regular(tmp_path):
    """굵기는 bold 속성으로 표현하므로 별칭 후보는 항상 regular 계열."""
    cat = FontCatalog(font_dir=_dir(tmp_path), default="NanumGothic")
    assert cat.suggest("Malgun Gothic Bold") == "NanumGothic"


def test_propose_mapping_empty_name_falls_back_to_default():
    cat = FontCatalog(font_dir=None, default="NanumGothic")
    mapping, _ = cat.propose_mapping(("",))
    assert mapping == {"": "NanumGothic"}
