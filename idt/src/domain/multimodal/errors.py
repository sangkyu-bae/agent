"""multimodal-extractor 도메인 예외.

Design Ref: multimodal-extractor §6.1 / §6.3
— 설정 오류·입력 무효만 예외, 건별 비전 실패는 예외가 아니라 status.
"""


class MultimodalError(Exception):
    """모듈 공통 베이스."""


class MultimodalDisabledError(MultimodalError):
    """enabled=False — 호출자는 '노드 미존재'로 취급해 스킵한다(탈착형 이음매)."""


class MultimodalNotConfiguredError(MultimodalError):
    """vision_model_id 미설정·모델 없음·비활성·supports_vision=0·API 키 env 없음.

    Plan FR-10.
    """


class UnsupportedFormatError(MultimodalError):
    """확장자/MIME 에 등록된 추출기가 없음 (Plan FR-17)."""

    def __init__(self, extension: str, supported: tuple[str, ...]) -> None:
        self.extension = extension
        self.supported = supported
        super().__init__(
            f"unsupported format '{extension}' (supported: {', '.join(supported)})"
        )


class UnsupportedVisionProviderError(MultimodalError):
    """provider 키에 등록된 비전 어댑터가 없음 (Plan FR-17)."""

    def __init__(self, provider: str, supported: tuple[str, ...]) -> None:
        self.provider = provider
        self.supported = supported
        super().__init__(
            f"unsupported vision provider '{provider}' "
            f"(supported: {', '.join(supported)})"
        )


class ExtractionError(MultimodalError):
    """입력 파일 자체를 열 수 없음(손상 등)."""
