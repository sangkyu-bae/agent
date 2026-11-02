"""첨부 저장소 Protocol (domain) — infrastructure가 구현, application이 의존."""
from typing import Optional, Protocol

from src.domain.agent_attachment.value_objects import (
    AttachmentType,
    ImageDimensions,
    StoredAttachment,
)


class AttachmentStoreInterface(Protocol):
    """첨부 파일 저장/조회/삭제 추상화.

    구현체는 infrastructure 레이어 (예: 로컬 임시 디렉토리 + 사이드카 메타).
    """

    def save(
        self,
        *,
        file_bytes: bytes,
        filename: str,
        attachment_type: AttachmentType,
        owner_user_id: str,
        width: int | None = None,
        height: int | None = None,
    ) -> StoredAttachment:
        """파일을 저장하고 file_id를 발급한다. width/height 는 이미지일 때만."""
        ...

    def load(self, file_id: str) -> Optional[StoredAttachment]:
        """file_id로 저장된 첨부를 조회한다 (없으면 None)."""
        ...

    def delete(self, file_id: str) -> None:
        """file_id에 해당하는 파일/메타를 삭제한다 (없어도 예외 금지)."""
        ...


class ImageNormalizerPort(Protocol):
    """이미지 바이트 정규화(리사이즈·EXIF 방향·메타 제거) — chat-image-attachment Design §3.1.

    구현체는 infrastructure(PIL). domain/application 은 PIL 을 모른다.
    """

    def normalize(
        self, data: bytes, *, max_edge_px: int, jpeg_quality: int
    ) -> tuple[bytes, ImageDimensions]:
        """정규화된 바이트와 (width, height, mime). 손상·폭탄은 InvalidAttachmentError."""
        ...


class ImageBlockBuilderPort(Protocol):
    """LLM provider 별 이미지 content block 생성 — chat-image-attachment Design §3.3 / D-08."""

    def supports(self, provider: str) -> bool:
        ...

    def build(self, provider: str, *, mime: str, data: bytes, detail: str) -> dict:
        """미지원 provider 는 ValueError."""
        ...

    def build_from_path(
        self, provider: str, *, mime: str, path: str, detail: str
    ) -> dict:
        """저장된 첨부 파일을 읽어 블록 생성 (파일 I/O 는 infrastructure 가 맡는다)."""
        ...
