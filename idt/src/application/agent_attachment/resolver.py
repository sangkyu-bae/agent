"""첨부 참조 해석 + 정리 (Design §4.3).

- resolve: file_id → RunAgentRequest.attachments 항목({type, file_path, user_id})
  + 소유자 검증 (업로더 == 뷰어).
- cleanup: run 종료 시 file_id 일괄 삭제 (실패는 본 흐름 비차단, 경고 로그).
"""
from src.domain.agent_attachment.exceptions import (
    AttachmentAccessDeniedError,
    AttachmentNotFoundError,
)
from src.domain.agent_attachment.interfaces import AttachmentStoreInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class AttachmentResolver:
    """file_id 참조를 분석 노드가 소비할 attachment dict로 해석한다."""

    def __init__(
        self,
        store: AttachmentStoreInterface,
        logger: LoggerInterface,
    ) -> None:
        self._store = store
        self._logger = logger

    def resolve(self, file_id: str, viewer_user_id: str) -> dict:
        """단일 file_id 해석. 소유자 검증 포함.

        Raises:
            AttachmentNotFoundError: 메타/파일 없음 또는 만료
            AttachmentAccessDeniedError: 업로더 != 뷰어
        """
        stored = self._store.load(file_id)
        if stored is None:
            raise AttachmentNotFoundError(file_id)
        if stored.owner_user_id != viewer_user_id:
            raise AttachmentAccessDeniedError(file_id)
        return {
            "type": stored.type.value,
            "file_path": stored.file_path,
            "user_id": stored.owner_user_id,
        }

    def resolve_many(
        self,
        refs: list[dict],
        viewer_user_id: str,
    ) -> list[dict]:
        """refs(list of {type, file_id}) → attachment dict 리스트."""
        return [self.resolve(r["file_id"], viewer_user_id) for r in refs]

    def cleanup(self, file_ids: list[str]) -> None:
        """run 종료 시 호출 — 임시 파일 삭제 (Design §4.3 finally)."""
        for file_id in file_ids:
            try:
                self._store.delete(file_id)
            except Exception as e:  # 정리 실패가 응답 흐름을 막지 않는다
                self._logger.warning(
                    "agent attachment cleanup failed",
                    file_id=file_id,
                    exception=e,
                )
