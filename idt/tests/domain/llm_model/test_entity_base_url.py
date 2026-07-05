"""LLM-MODEL-REG-002: LlmModel base_url 필드 검증."""
from datetime import datetime, timezone

from src.domain.llm_model.entity import LlmModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


def test_base_url_stored() -> None:
    model = LlmModel(
        id="m1",
        provider="openai",
        model_name="Qwen2.5",
        display_name="Qwen",
        description=None,
        api_key_env="QWEN_API_KEY",
        max_tokens=None,
        is_active=True,
        is_default=False,
        created_at=_now(),
        updated_at=_now(),
        base_url="http://10.0.0.5:8000/v1",
    )
    assert model.base_url == "http://10.0.0.5:8000/v1"


def test_base_url_defaults_none() -> None:
    model = LlmModel(
        id="m2",
        provider="openai",
        model_name="gpt-4o",
        display_name="GPT-4o",
        description=None,
        api_key_env="OPENAI_API_KEY",
        max_tokens=None,
        is_active=True,
        is_default=False,
        created_at=_now(),
        updated_at=_now(),
    )
    assert model.base_url is None
