"""domain/blueprint 예외.

Design §6.1 / §6.3 — 설정 오류는 예외, 건별 실패는 degraded.
"""


class BlueprintError(Exception):
    """blueprint 도메인 공통 예외."""


class UnsupportedSampleFormatError(BlueprintError):
    """Golden Sample 확장자 미지원 (→ 415)."""

    def __init__(self, extension: str, supported: tuple[str, ...]) -> None:
        self.extension = extension
        self.supported = supported
        super().__init__(
            f"unsupported sample format '{extension}' "
            f"(supported: {', '.join(supported)})"
        )


class SampleExtractionError(BlueprintError):
    """파일 손상·파싱 실패 (→ 415)."""


class BlueprintNotFoundError(BlueprintError):
    """blueprint id 없음 (→ 404)."""


class BlueprintNotConfiguredError(BlueprintError):
    """워커에 blueprint 미설정·inactive (그래프 내 안내 노옵)."""


class BlueprintValidationError(BlueprintError):
    """저장 전 정책 검증 실패 (→ 400)."""


class PresentationGenerateError(BlueprintError):
    """LLM 응답 공백·렌더 실패 (워커 실패 메시지)."""
