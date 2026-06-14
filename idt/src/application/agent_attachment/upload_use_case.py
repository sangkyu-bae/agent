"""첨부 업로드 유스케이스 (Design §4.2).

검증(domain 정책) → 저장(store) → file_id 발급.
비즈니스 규칙은 AttachmentPolicy에 위임 — UseCase는 흐름만 제어한다.
"""
from src.domain.agent_attachment.interfaces import AttachmentStoreInterface
from src.domain.agent_attachment.policies import AttachmentPolicy
from src.domain.agent_attachment.value_objects import StoredAttachment
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class UploadAttachmentUseCase:
    """엑셀 등 첨부 파일을 검증 후 저장하고 참조를 반환한다."""

    def __init__(
        self,
        store: AttachmentStoreInterface,
        max_bytes: int,
        logger: LoggerInterface,
    ) -> None:
        self._store = store
        self._max_bytes = max_bytes
        self._logger = logger

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
        stored = self._store.save(
            file_bytes=file_bytes,
            filename=filename,
            attachment_type=attachment_type,
            owner_user_id=owner_user_id,
        )
        self._logger.info(
            "agent attachment uploaded",
            file_id=stored.file_id,
            type=attachment_type.value,
            size=stored.size,
            owner_user_id=owner_user_id,
        )
        return stored
