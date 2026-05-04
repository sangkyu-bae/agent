from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.doc_browse.schemas import DocumentMetadata


class DocumentDeletePolicy:

    @staticmethod
    def can_delete(
        user_id: str,
        user_role: str,
        document_metadata: DocumentMetadata,
        collection_owner_id: int | None,
    ) -> bool:
        if user_role == "admin":
            return True
        if document_metadata.user_id == user_id:
            return True
        if collection_owner_id is not None:
            try:
                if collection_owner_id == int(user_id):
                    return True
            except (ValueError, TypeError):
                pass
        return False
