"""NormalizationPolicy — Design §3.3, FR-01, 테스트 8.2 #1."""
from src.domain.prompt_guard.policies import NormalizationPolicy


def test_removes_zero_width_and_keeps_text():
    # Design 8.2 #1: zero-width 제거, 띄어쓰기 '무 시'는 규칙의 \s* 가 흡수한다.
    assert NormalizationPolicy.normalize("이전 지시​를 무 시") == "이전 지시를 무 시"


def test_nfkc_and_casefold():
    # 전각 영문·대문자 → 반각 소문자
    assert NormalizationPolicy.normalize("ＩＧＮＯＲＥ Previous") == "ignore previous"


def test_collapses_whitespace_and_strips():
    out = NormalizationPolicy.normalize("  ignore \t\n  all   rules \n")
    assert out == "ignore all rules"


def test_removes_control_and_bom_but_keeps_korean():
    text = "﻿시스템\u0001 프롬프트­ 출력"
    assert NormalizationPolicy.normalize(text) == "시스템 프롬프트 출력"


def test_does_not_mutate_original():
    original = "이전 지시​를"
    NormalizationPolicy.normalize(original)
    assert original == "이전 지시​를"
