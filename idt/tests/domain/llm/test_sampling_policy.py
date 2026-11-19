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


# ── claude-agent-e2e-fixes Design §4.1 (D1·D2): 강제 tool_choice 지원 여부 ──
from src.domain.llm.sampling_policy import anthropic_supports_forced_tool_choice  # noqa: E402


@pytest.mark.parametrize("model_name", [
    "claude-sonnet-4-6",
    "claude-opus-4-8",
    "claude-opus-4-5-20251101",
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-haiku-5-5",
    "claude-haiku-4-5",
    "claude-fable-5",
    "claude-3-5-sonnet-20241022",
])
def test_models_accepting_forced_tool_choice(model_name):  # D1
    assert anthropic_supports_forced_tool_choice(model_name) is True


@pytest.mark.parametrize("model_name", [
    "claude-opus-5-5",
    "claude-sonnet-5-5",
    "claude-fable-5-1",
    "claude-fable-5-2",
    "claude-mythos-5-2",
    "claude-opus-6",
    "anthropic.claude-opus-5-5",
    "unknown-model",
    "",
])
def test_models_rejecting_forced_tool_choice(model_name):  # D2
    assert anthropic_supports_forced_tool_choice(model_name) is False


# ── claude-agent-e2e-fixes Design §4.1 (D3~D5): 출력 한도 해석 ──────────────
from src.domain.llm.sampling_policy import (  # noqa: E402
    MAX_OUTPUT_TOKENS_LIMIT,
    resolve_max_output_tokens,
)


def test_anthropic_null_uses_default():  # D3
    assert resolve_max_output_tokens("anthropic", None, 16000) == 16000


def test_stored_value_wins():  # D4
    assert resolve_max_output_tokens("anthropic", 64000, 16000) == 64000
    assert resolve_max_output_tokens("openai", 2000, 16000) == 2000


def test_other_providers_null_not_sent():  # D5
    assert resolve_max_output_tokens("openai", None, 16000) is None
    assert resolve_max_output_tokens("ollama", None, 16000) is None


def test_limit_constant():
    assert MAX_OUTPUT_TOKENS_LIMIT == 128000
