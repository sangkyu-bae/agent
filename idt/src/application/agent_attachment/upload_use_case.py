"""첨부 업로드 유스케이스 (Design §4.2).

검증(domain 정책) → 저장(store) → file_id 발급.
비즈니스 규칙은 AttachmentPolicy에 위임 — UseCase는 흐름만 제어한다.

chat-image-attachment Design §2.2: 이미지는 확장자·크기 검증 뒤 매직 넘버를
확인하고, ImageNormalizerPort 로 정규화(리사이즈·EXIF·메타 제거)한 바이트를 저장한다.
"""
from src.domain.agent_attachment.interfaces import (
    AttachmentStoreInterface,
    ImageNormalizerPort,
)
from src.domain.agent_attachment.policies import AttachmentPolicy
from src.domain.agent_attachment.value_objects import (
    AttachmentType,
    ImageDimensions,
    StoredAttachment,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface

_MAGIC_HEAD_BYTES = 16


class UploadAttachmentUseCase:
    """엑셀·이미지 등 첨부 파일을 검증 후 저장하고 참조를 반환한다."""

    def __init__(
        self,
        store: AttachmentStoreInterface,
        max_bytes: int,
        logger: LoggerInterface,
        *,
        image_normalizer: ImageNormalizerPort | None = None,
        image_max_edge_px: int = 1568,
        image_jpeg_quality: int = 90,
    ) -> None:
        self._store = store
        self._max_bytes = max_bytes
        self._logger = logger
        self._image_normalizer = image_normalizer
        self._image_max_edge_px = image_max_edge_px
        self._image_jpeg_quality = image_jpeg_quality

    def execute(
        self,
        *,
        file_bytes: bytes,
        filename: str,
        owner_user_id: str,
    ) -> StoredAttachment:
        attachment_type = AttachmentPolicy.validate(
            filename, len(file_bytes), self._max_bytes
        )
        dims: ImageDimensions | None = None
        if attachment_type == AttachmentType.IMAGE:
            file_bytes, dims = self._prepare_image(file_bytes, filename)
        stored = self._store.save(
            file_bytes=file_bytes,
            filename=filename,
            attachment_type=attachment_type,
            owner_user_id=owner_user_id,
            width=dims.width if dims else None,
            height=dims.height if dims else None,
        )
        self._logger.info(
            "agent attachment uploaded",
            file_id=stored.file_id,
            type=attachment_type.value,
            size=stored.size,
            owner_user_id=owner_user_id,
            mime=dims.mime if dims else None,
            width=stored.width,
            height=stored.height,
        )
        return stored

    def _prepare_image(
        self, file_bytes: bytes, filename: str
    ) -> tuple[bytes, ImageDimensions | None]:
        # Design §7: 확장자↔매직 넘버 삼중 검증 (위장 파일 차단) — normalizer 호출 전
        AttachmentPolicy.validate_image_bytes(filename, file_bytes[:_MAGIC_HEAD_BYTES])
        if self._image_normalizer is None:
            return file_bytes, None
        return self._image_normalizer.normalize(
            file_bytes,
            max_edge_px=self._image_max_edge_px,
            jpeg_quality=self._image_jpeg_quality,
        )
