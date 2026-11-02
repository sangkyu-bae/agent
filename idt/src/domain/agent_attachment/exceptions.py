"""Agent 첨부 도메인 예외 (ws-agent-excel-attachment Design §6.1)."""


class AttachmentError(Exception):
    """첨부 도메인 기반 예외."""


class InvalidAttachmentError(AttachmentError):
    """허용되지 않는 확장자/타입 또는 빈 파일."""


class AttachmentTooLargeError(AttachmentError):
    """최대 허용 크기 초과."""


class AttachmentNotFoundError(AttachmentError):
    """file_id에 해당하는 첨부 없음/만료."""


class AttachmentAccessDeniedError(AttachmentError):
    """업로더가 아닌 사용자의 접근 (소유자 불일치)."""


class TooManyImagesError(AttachmentError):
    """턴당 이미지 장수 상한 초과 (chat-image-attachment Design §6.1)."""


class VisionNotSupportedError(AttachmentError):
    """에이전트 실효 모델이 이미지 입력을 지원하지 않음 (chat-image-attachment D-05)."""

    def __init__(self, model_display_name: str) -> None:
        self.model_display_name = model_display_name
        super().__init__(
            f"'{model_display_name}' 모델은 이미지 입력을 지원하지 않습니다. "
            "관리자 > LLM 모델에서 비전 지원을 켜거나 다른 모델의 에이전트를 사용하세요."
        )
