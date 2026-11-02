"""LlmModel 종류(model_kind) 규칙 — image-generation-tool Design §3.3 / §4.2 / D-05."""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.domain.llm_model.entity import LlmModel
from src.domain.llm_model.policies import LlmModelPolicy, MODEL_KINDS


def _model(kind: str = "chat", **over) -> LlmModel:
    now = datetime.now(timezone.utc)
    base = dict(
        id="m", provider="openai", model_name="x", display_name="X", description=None,
        api_key_env="OPENAI_API_KEY", max_tokens=None, is_active=True, is_default=False,
        created_at=now, updated_at=now, model_kind=kind,
    )
    base.update(over)
    return LlmModel(**base)


class TestEntityDefaults:
    def test_model_kind_defaults_to_chat(self) -> None:
        now = datetime.now(timezone.utc)
        m = LlmModel(
            id="m", provider="openai", model_name="x", display_name="X", description=None,
            api_key_env="K", max_tokens=None, is_active=True, is_default=False,
            created_at=now, updated_at=now,
        )
        assert m.model_kind == "chat"
        assert m.price_per_image_usd is None
        assert m.is_chat_model is True and m.is_image_model is False

    def test_image_model_flags(self) -> None:
        m = _model("image", price_per_image_usd=Decimal("0.04"))
        assert m.is_image_model is True and m.is_chat_model is False


class TestValidateModelKind:
    @pytest.mark.parametrize("kind", list(MODEL_KINDS))
    def test_known_kinds_pass(self, kind: str) -> None:
        LlmModelPolicy.validate_model_kind(kind)

    @pytest.mark.parametrize("kind", ["", "vision", "CHAT", "audio"])
    def test_unknown_kind_raises(self, kind: str) -> None:
        with pytest.raises(ValueError):
            LlmModelPolicy.validate_model_kind(kind)


class TestRequireKind:
    def test_require_chat_model_accepts_chat(self) -> None:
        LlmModelPolicy.require_chat_model(_model("chat"))

    def test_require_chat_model_rejects_image(self) -> None:
        with pytest.raises(ValueError) as ei:
            LlmModelPolicy.require_chat_model(_model("image", display_name="GPT Image"))
        assert "GPT Image" in str(ei.value)
        # Design §4.2 / §6.1: 프론트가 코드로 구분하도록 MODEL_KIND_MISMATCH 접두어
        assert str(ei.value).startswith("MODEL_KIND_MISMATCH: ")

    def test_require_image_model_rejects_chat_and_inactive(self) -> None:
        with pytest.raises(ValueError):
            LlmModelPolicy.require_image_model(_model("chat"))
        with pytest.raises(ValueError):
            LlmModelPolicy.require_image_model(_model("image", is_active=False))
        LlmModelPolicy.require_image_model(_model("image"))

    def test_default_model_must_be_chat(self) -> None:
        with pytest.raises(ValueError):
            LlmModelPolicy.validate_default_is_chat(_model("image", is_default=True))
        LlmModelPolicy.validate_default_is_chat(_model("image", is_default=False))
        LlmModelPolicy.validate_default_is_chat(_model("chat", is_default=True))
