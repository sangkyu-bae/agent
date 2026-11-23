"""파일명 정규화 — document-revision Design §10.4 (부서 특화 단어 없이 일반 패턴만)."""

import pytest
from src.domain.document_revision.filename_normalizer import (
    filename_similarity,
    normalize_filename,
)


@pytest.mark.parametrize(
    "filename",
    [
        "여신심사기준.pdf",
        "여신심사기준_v2_2026.pdf",
        "여신심사기준(개정).pdf",
        "여신심사기준 [최종] 2026.11.21.hwp",
        "여신심사기준_20261121.PDF",
        "여신심사기준개정.pdf",
        "여신심사기준 (2).pdf",
        "여신심사기준_제3차.pdf",
        "여신심사기준（개정본）.pdf",
        "여신심사기준-ver3.1.pdf",
        "여신심사기준v2.pdf",
        "여신심사기준_2026-11_수정본.hwpx",
    ],
)
def test_revision_noise_is_removed(filename: str) -> None:
    assert normalize_filename(filename) == "여신심사기준"


def test_english_keywords_and_versions_are_removed() -> None:
    assert normalize_filename("Loan Policy rev3 FINAL.docx") == "loan policy"
    assert normalize_filename("loan_policy_v1.2_draft.pdf") == "loan policy"


def test_meaningful_bracket_content_is_kept() -> None:
    assert normalize_filename("(별표1) 수수료표.pdf") == "별표 수수료표"


def test_only_noise_falls_back_to_base_name() -> None:
    assert normalize_filename("최종.pdf") == "최종"
    assert normalize_filename("2026.pdf") == "2026"


def test_name_without_extension() -> None:
    assert normalize_filename("여신심사기준 v3") == "여신심사기준"


def test_similarity_is_one_for_same_normalized_name() -> None:
    assert filename_similarity("여신심사기준_v1.pdf", "여신심사기준(개정).pdf") == 1.0


def test_similarity_is_low_for_unrelated_names() -> None:
    assert filename_similarity("여신심사기준.pdf", "대출금리표.xlsx") < 0.4


def test_similarity_is_partial_for_close_names() -> None:
    score = filename_similarity("여신심사기준.pdf", "여신심사기준 세칙.pdf")
    assert 0.6 <= score < 1.0


def test_similarity_with_empty_name_is_zero() -> None:
    assert filename_similarity("", "a.pdf") == 0.0
