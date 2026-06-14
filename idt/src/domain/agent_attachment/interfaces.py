"""첨부 저장소 Protocol (domain) — infrastructure가 구현, application이 의존."""
from typing import Optional, Protocol

from src.domain.agent_attachment.value_objects import (
    AttachmentType,
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
    ) -> StoredAttachment:
        """파일을 저장하고 file_id를 발급한다."""
        ...

    def load(self, file_id: str) -> Optional[StoredAttachment]:
        """file_id로 저장된 첨부를 조회한다 (없으면 None)."""
        ...

    def delete(self, file_id: str) -> None:
        """file_id에 해당하는 파일/메타를 삭제한다 (없어도 예외 금지)."""
        ...
