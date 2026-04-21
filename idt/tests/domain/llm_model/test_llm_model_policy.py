"""LlmModelPolicy tests — mock 금지 (domain 규칙)."""
from datetime import datetime, timezone

import pytest

from src.domain.llm_model.entity import LlmModel
from src.domain.llm_model.policies import LlmModelPolicy


def _make_model(
    *,
    model_id: str = "m1",
    provider: str = "openai",
    model_name: str = "gpt-4o",
    is_default: bool = False,
) -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id=model_id,
        provider=provider,
        model_name=model_name,
        display_name="display",
        description=None,
        api_key_env="OPENAI_API_KEY",
        max_tokens=None,
        is_active=True,
        is_default=is_default,
        created_at=now,
        updated_at=now,
    )


class TestLlmModelPolicySingleDefault:
    def test_zero_default_is_allowed(self) -> None:
        LlmModelPolicy.validate_single_default([
            _make_model(model_id="a"),
            _make_model(model_id="b"),
        ])

    def test_single_default_is_allowed(self) -> None:
        LlmModelPolicy.validate_single_default([
            _make_model(model_id="a", is_default=True),
            _make_model(model_id="b"),
        ])

    def test_multiple_defaults_raises(self) -> None:
        with pytest.raises(ValueError, match="기본 모델은 1개"):
            LlmModelPolicy.validate_single_default([
                _make_model(model_id="a", is_default=True),
                _make_model(model_id="b", is_default=True),
            ])


class TestLlmModelPolicyModelNameValidation:
    def test_non_empty_name_is_allowed(self) -> None:
        LlmModelPolicy.validate_model_name_not_empty("gpt-4o")

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError, match="빈 문자열"):
            LlmModelPolicy.validate_model_name_not_empty("")

    def test_whitespace_only_raises(self) -> None:
        with pytest.raises(ValueError, match="빈 문자열"):
            LlmModelPolicy.validate_model_name_not_empty("   ")
