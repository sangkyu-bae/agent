"""첨부 검증 정책 (순수 규칙, 외부 의존 0) — Design §3.1.

chat-image-attachment Design §3.1: IMAGE 타입(확장자·매직 넘버·MIME)과
턴 단위 규칙(장수 상한·대화 기록 마커)을 추가. PIL·LangChain·파일 I/O 금지.
"""
from pathlib import PurePath

from src.domain.agent_attachment.exceptions import (
    AttachmentTooLargeError,
    InvalidAttachmentError,
    TooManyImagesError,
)
from src.domain.agent_attachment.value_objects import AttachmentType

# 확장자 → MIME (IMAGE 전용). ALLOWED_EXT[IMAGE] 와 키 집합이 같아야 한다.
_IMAGE_MIME_BY_EXT: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


class AttachmentPolicy:
    """타입별 허용 확장자/크기 규칙.

    확장: 신규 타입은 ALLOWED_EXT에 매핑만 추가 (OCP).
    """

    ALLOWED_EXT: dict[AttachmentType, frozenset[str]] = {
        AttachmentType.EXCEL: frozenset({".xlsx", ".xls"}),
        AttachmentType.IMAGE: frozenset(_IMAGE_MIME_BY_EXT),
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
    def sniff_image_mime(head: bytes) -> str | None:
        """선두 바이트(매직 넘버)로 이미지 MIME 판별. 모르면 None."""
        if head.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if head.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
            return "image/webp"
        return None

    @classmethod
    def validate_image_bytes(cls, filename: str, head: bytes) -> str:
        """확장자와 매직 넘버가 같은 MIME을 가리켜야 한다. 통과 시 MIME 반환.

        Design §7: 위장 파일(확장자만 png) 차단.
        """
        expected = _IMAGE_MIME_BY_EXT.get(cls._ext(filename))
        actual = cls.sniff_image_mime(head)
        if expected is None or actual is None or expected != actual:
            raise InvalidAttachmentError(
                "이미지 내용이 확장자와 일치하지 않습니다 (png/jpg/webp)"
            )
        return actual

    @staticmethod
    def _ext(filename: str) -> str:
        return PurePath(filename).suffix.lower()


class ImageAttachmentPolicy:
    """턴 단위 이미지 규칙 — chat-image-attachment Design §3.1."""

    @staticmethod
    def validate_count(count: int, *, max_count: int) -> None:
        if count > max_count:
            raise TooManyImagesError(
                f"이미지는 최대 {max_count}장까지 첨부할 수 있습니다"
            )

    @staticmethod
    def marker(file_names: list[str]) -> str:
        """대화 기록(DB)에 남기는 텍스트 마커. 이미지가 없으면 빈 문자열."""
        if not file_names:
            return ""
        return f"[이미지 첨부: {', '.join(file_names)}]"

    @staticmethod
    def unsupported_marker(file_names: list[str]) -> str:
        """비전 미지원 서브에이전트 입력에 넣는 마커 (Design FR-07)."""
        if not file_names:
            return ""
        return (
            f"[이미지 첨부: {', '.join(file_names)} "
            "(이 모델은 이미지를 볼 수 없음)]"
        )

    @staticmethod
    def mime_for(filename: str) -> str:
        """확장자 기준 MIME. 저장된 이미지는 업로드 시 매직 넘버 검증을 거쳤다."""
        mime = _IMAGE_MIME_BY_EXT.get(PurePath(filename).suffix.lower())
        if mime is None:
            raise InvalidAttachmentError(f"이미지 확장자가 아닙니다: {filename}")
        return mime
