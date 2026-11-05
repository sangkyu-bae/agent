"""KbDefaultSetting 도메인 — agent-kb-quick-setup Design §3.1."""

from datetime import UTC, datetime

from src.domain.kb_default_setting.entities import KbDefaultSetting
from src.domain.kb_default_setting.errors import (
    EmbeddingModelInactiveError,
    EmbeddingModelNotFoundError,
    KbDefaultSettingError,
    KbDefaultsNotConfiguredError,
)


def test_configured_false_when_model_id_missing():
    s = KbDefaultSetting(default_embedding_model_id=None, updated_at=None)
    assert s.configured is False


def test_configured_true_when_model_id_set():
    s = KbDefaultSetting(
        default_embedding_model_id=3, updated_at=datetime(2026, 11, 5, tzinfo=UTC)
    )
    assert s.configured is True


def test_errors_are_value_errors_with_codes():
    """라우터가 ValueError 계열로 잡되 code 로 분기한다 (Design §6.1)."""
    for cls, code in (
        (KbDefaultsNotConfiguredError, "KB_DEFAULTS_NOT_CONFIGURED"),
        (EmbeddingModelNotFoundError, "EMBEDDING_MODEL_NOT_FOUND"),
        (EmbeddingModelInactiveError, "EMBEDDING_MODEL_INACTIVE"),
    ):
        err = cls()
        assert isinstance(err, ValueError)
        assert isinstance(err, KbDefaultSettingError)
        assert err.code == code
        assert str(err)


def test_not_configured_default_message_is_user_facing():
    assert "기본 임베딩 모델" in str(KbDefaultsNotConfiguredError())
