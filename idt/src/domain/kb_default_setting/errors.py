"""agent-kb-quick-setup 도메인 예외 (Design §6.1).

전부 ValueError 계열 — 기존 라우터의 `except ValueError` 경로를 깨지 않고,
`code` 로 프론트가 분기한다.
"""


class KbDefaultSettingError(ValueError):
    code = "KB_DEFAULT_SETTING_ERROR"
    default_message = "지식베이스 기본값 오류"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.default_message)


class KbDefaultsNotConfiguredError(KbDefaultSettingError):
    """기본 임베딩 모델 미설정·삭제·비활성 — 자동 컬렉션 생성 불가 (Plan FR-03)."""

    code = "KB_DEFAULTS_NOT_CONFIGURED"
    default_message = "관리자가 기본 임베딩 모델을 설정해야 합니다"


class EmbeddingModelNotFoundError(KbDefaultSettingError):
    code = "EMBEDDING_MODEL_NOT_FOUND"
    default_message = "임베딩 모델을 찾을 수 없습니다"


class EmbeddingModelInactiveError(KbDefaultSettingError):
    code = "EMBEDDING_MODEL_INACTIVE"
    default_message = "비활성 모델은 기본값으로 지정할 수 없습니다"
