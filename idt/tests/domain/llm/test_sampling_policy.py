"""Anthropic 샘플링 파라미터 허용 정책 테스트.

Claude Opus 4.7 이후 모델(Opus 5.5·Sonnet 5.5·Fable 등)은 temperature를 보내면
400("`temperature` is deprecated for this model")을 반환한다 — 2026-11-19 실호출로 확인.
temperature를 받는 구형 모델에만 보내고, 모르는 이름은 보내지 않는다(안전한 기본값).
"""
import pytest

from src.domain.llm.sampling_policy import anthropic_accepts_temperature


@pytest.mark.parametrize("model_name", [
    "claude-3-5-sonnet-20241022",
    "claude-3-opus-20240229",
    "claude-3-haiku-20240307",
    "claude-opus-4-20250514",
    "claude-sonnet-4-20250514",
    "claude-opus-4-1",
    "claude-opus-4-1-20250805",
    "claude-opus-4-5-20251101",
    "claude-sonnet-4-5-20250929",
    "claude-haiku-4-5-20251001",
    "claude-haiku-4-5",
    "claude-opus-4-6",
    "claude-sonnet-4-6",
])
def test_legacy_models_accept_temperature(model_name):
    assert anthropic_accepts_temperature(model_name) is True


@pytest.mark.parametrize("model_name", [
    "claude-opus-4-7",
    "claude-opus-4-8",
    "claude-opus-5",
    "claude-opus-5-5",
    "claude-sonnet-5",
    "claude-sonnet-5-5",
    "claude-haiku-5-5",
    "claude-fable-5-2",
    "claude-mythos-5-2",
    "anthropic.claude-opus-5-5",
    "unknown-model",
    "",
])
def test_new_or_unknown_models_do_not_get_temperature(model_name):
    assert anthropic_accepts_temperature(model_name) is False
