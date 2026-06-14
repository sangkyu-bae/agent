"""첨부 검증 정책 (순수 규칙, 외부 의존 0) — Design §3.1."""
from pathlib import PurePath

from src.domain.agent_attachment.exceptions import (
    AttachmentTooLargeError,
    InvalidAttachmentError,
)
from src.domain.agent_attachment.value_objects import AttachmentType


class AttachmentPolicy:
    """타입별 허용 확장자/크기 규칙.

    확장: 신규 타입은 ALLOWED_EXT에 매핑만 추가 (OCP).
    """

    ALLOWED_EXT: dict[AttachmentType, frozenset[str]] = {
        AttachmentType.EXCEL: frozenset({".xlsx", ".xls"}),
    }

    @classmethod
    def resolve_type(cls, filename: str) -> AttachmentType:
        """확장자로 첨부 타입을 판별. 미허용 시 InvalidAttachmentError."""
        ext = cls._ext(filename)
        for attachment_type, exts in cls.ALLOWED_EXT.items():
            if ext in exts:
                return attachment_type
        raise InvalidAttachmentError(
            f"지원하지 않는 첨부 형식입니다: {ext or '(확장자 없음)'}"
        )

    @classmethod
    def validate(cls, filename: str, size: int, max_size: int) -> AttachmentType:
        """확장자/크기 검증 후 판별된 타입 반환.

        Raises:
            InvalidAttachmentError: 미허용 확장자 또는 빈 파일
            AttachmentTooLargeError: max_size 초과
        """
        attachment_type = cls.resolve_type(filename)
        if size <= 0:
            raise InvalidAttachmentError("빈 파일은 업로드할 수 없습니다")
        if size > max_size:
            raise AttachmentTooLargeError(
                f"파일이 너무 큽니다: {size} > {max_size} bytes"
            )
        return attachment_type

    @staticmethod
    def _ext(filename: str) -> str:
        return PurePath(filename).suffix.lower()
