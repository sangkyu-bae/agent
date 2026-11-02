"""image_generation 예외 — image-generation-tool Design §3.1 / §6."""


class ImageGenerationError(Exception):
    """기반 예외. 노드는 이 계열을 안내 AIMessage 로 바꾼다 (그래프 비중단)."""

    user_message: str = "이미지 생성에 실패했습니다."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.user_message)
        if message:
            self.user_message = message


class InvalidImageRequestError(ImageGenerationError):
    user_message = "이미지 생성 요청이 올바르지 않습니다."


class ImageTurnCapExceededError(ImageGenerationError):
    def __init__(self, max_per_turn: int) -> None:
        self.max_per_turn = max_per_turn
        super().__init__(
            f"이번 대화 턴의 이미지 생성 상한({max_per_turn}장)에 도달했습니다. "
            "새 메시지에서 다시 요청해 주세요."
        )


class UnsupportedImageProviderError(ImageGenerationError):
    def __init__(self, provider: str, supported: tuple[str, ...]) -> None:
        self.provider = provider
        super().__init__(
            f"이미지 생성을 지원하지 않는 provider 입니다: {provider!r} "
            f"(지원: {', '.join(supported) or '없음'})"
        )


class ImageModelNotConfiguredError(ImageGenerationError):
    user_message = (
        "이미지 생성 모델이 설정되지 않았거나 사용할 수 없습니다. "
        "에이전트 편집에서 이미지 모델을 다시 선택해 주세요."
    )


class ImageProviderError(ImageGenerationError):
    """provider 호출 실패. retryable=False 는 정책 위반 등 재시도 무의미."""

    def __init__(self, user_message: str, *, retryable: bool) -> None:
        self.retryable = retryable
        super().__init__(user_message)
