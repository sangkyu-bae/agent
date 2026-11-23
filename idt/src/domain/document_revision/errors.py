"""document-revision 도메인 예외 (Design §6.1). 라우터가 409/422 로 변환한다."""
from __future__ import annotations

from src.domain.document_revision.value_objects import DocumentVersion


class DocumentRevisionError(Exception):
    code: str = "DOCUMENT_REVISION_ERROR"

    def __init__(self, reason: str, message: str | None = None) -> None:
        self.reason = reason
        super().__init__(message or reason)


class DuplicateDocumentError(DocumentRevisionError):
    code = "DUPLICATE_DOCUMENT"

    def __init__(self, existing: DocumentVersion) -> None:
        self.existing = existing
        super().__init__(
            "duplicate",
            f"같은 파일이 이미 있습니다: {existing.filename}",
        )


class RevisionTargetInvalidError(DocumentRevisionError):
    """reason: not_found | other_kb | not_active | not_latest"""

    code = "REVISION_TARGET_INVALID"


class RollbackNotAllowedError(DocumentRevisionError):
    """reason: not_found | not_active | first_version | no_previous"""

    code = "ROLLBACK_NOT_ALLOWED"


class RevisionLinkInvalidError(DocumentRevisionError):
    """reason: not_found | other_kb | not_active | same_document
    | source_has_history | target_not_latest"""

    code = "REVISION_LINK_INVALID"


class RevisionModeNotAvailableError(DocumentRevisionError):
    code = "REVISION_MODE_NOT_AVAILABLE"


class RestorePendingError(DocumentRevisionError):
    """최신 버전 삭제 전 이전 버전 재활성 표식이 끝나지 않음 (Act-1 I2)."""

    code = "RESTORE_PENDING"
