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
