from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from qdrant_client import models

from src.domain.collection.schemas import ActionType
from src.domain.doc_browse.policies import DocumentDeletePolicy
from src.domain.doc_browse.schemas import DeleteDocumentResult

if TYPE_CHECKING:
    from qdrant_client import AsyncQdrantClient

    from src.application.collection.activity_log_service import ActivityLogService
    from src.application.collection.permission_service import (
        CollectionPermissionService,
    )
    from src.domain.doc_browse.interfaces import (
        DocumentMetadataRepositoryInterface,
    )
    from src.domain.elasticsearch.interfaces import (
        ElasticsearchRepositoryInterface,
    )
    from src.domain.logging.interfaces.logger_interface import LoggerInterface


class DeleteDocumentUseCase:

    class DocumentNotFoundError(Exception):
        pass

    class PermissionDeniedError(Exception):
        pass

    def __init__(
        self,
        document_metadata_repo: DocumentMetadataRepositoryInterface,
        qdrant_client: AsyncQdrantClient,
        es_repo: ElasticsearchRepositoryInterface,
        es_index: str,
        permission_service: CollectionPermissionService,
        activity_log_service: ActivityLogService,
        policy: DocumentDeletePolicy,
        logger: LoggerInterface,
    ) -> None:
        self._metadata_repo = document_metadata_repo
        self._qdrant_client = qdrant_client
        self._es_repo = es_repo
        self._es_index = es_index
        self._permission_service = permission_service
        self._activity_log_service = activity_log_service
        self._policy = policy
        self._logger = logger

    async def execute_single(
        self,
        collection_name: str,
        document_id: str,
        user_id: str,
        user_role: str = "user",
    ) -> DeleteDocumentResult:
        request_id = str(uuid.uuid4())
        self._logger.info(
            "Delete document started",
            request_id=request_id,
            collection=collection_name,
            document_id=document_id,
            user_id=user_id,
        )

        metadata = await self._metadata_repo.find_by_document_id(
            document_id, request_id
        )
        if metadata is None:
            raise self.DocumentNotFoundError(
                f"Document not found: {document_id}"
            )

        await self._check_permission(
            collection_name, user_id, user_role, metadata, request_id
        )

        deleted_qdrant = await self._delete_qdrant_chunks(
            collection_name, document_id
        )

        deleted_es = await self._delete_es_chunks(document_id, request_id)

        await self._metadata_repo.delete_by_document_id(
            document_id, request_id
        )

        await self._log_activity(
            collection_name, document_id, metadata.filename,
            deleted_qdrant, user_id, request_id,
        )

        self._logger.info(
            "Delete document completed",
            request_id=request_id,
            document_id=document_id,
            deleted_qdrant=deleted_qdrant,
            deleted_es=deleted_es,
        )

        return DeleteDocumentResult(
            document_id=document_id,
            collection_name=collection_name,
            filename=metadata.filename,
            deleted_qdrant_chunks=deleted_qdrant,
            deleted_es_chunks=deleted_es,
            status="deleted",
        )

    async def execute_batch(
        self,
        collection_name: str,
        document_ids: list[str],
        user_id: str,
        user_role: str = "user",
    ) -> dict[str, Any]:
        request_id = str(uuid.uuid4())
        self._logger.info(
            "Batch delete started",
            request_id=request_id,
            collection=collection_name,
            count=len(document_ids),
        )

        await self._pre_validate_permissions(
            collection_name, document_ids, user_id, user_role, request_id
        )

        results: list[dict[str, Any]] = []
        success_count = 0
        failure_count = 0

        for doc_id in document_ids:
            try:
                result = await self.execute_single(
                    collection_name, doc_id, user_id, user_role
                )
                results.append({
                    "document_id": result.document_id,
                    "status": "deleted",
                    "deleted_qdrant_chunks": result.deleted_qdrant_chunks,
                    "deleted_es_chunks": result.deleted_es_chunks,
                    "filename": result.filename,
                    "error": None,
                })
                success_count += 1
            except Exception as e:
                self._logger.warning(
                    "Batch delete item failed",
                    document_id=doc_id,
                    exception=e,
                )
                results.append({
                    "document_id": doc_id,
                    "status": "failed",
                    "deleted_qdrant_chunks": 0,
                    "deleted_es_chunks": 0,
                    "filename": "",
                    "error": str(e),
                })
                failure_count += 1

        return {
            "total": len(document_ids),
            "success_count": success_count,
            "failure_count": failure_count,
            "results": results,
        }

    async def _check_permission(
        self,
        collection_name: str,
        user_id: str,
        user_role: str,
        metadata: Any,
        request_id: str,
    ) -> None:
        perm = await self._permission_service.find_permission(
            collection_name, request_id
        )
        owner_id = perm.owner_id if perm else None

        if not self._policy.can_delete(
            user_id=user_id,
            user_role=user_role,
            document_metadata=metadata,
            collection_owner_id=owner_id,
        ):
            raise self.PermissionDeniedError(
                "No permission to delete document"
            )

    async def _pre_validate_permissions(
        self,
        collection_name: str,
        document_ids: list[str],
        user_id: str,
        user_role: str,
        request_id: str,
    ) -> None:
        perm = await self._permission_service.find_permission(
            collection_name, request_id
        )
        owner_id = perm.owner_id if perm else None

        for doc_id in document_ids:
            metadata = await self._metadata_repo.find_by_document_id(
                doc_id, request_id
            )
            if metadata is None:
                continue
            if not self._policy.can_delete(
                user_id=user_id,
                user_role=user_role,
                document_metadata=metadata,
                collection_owner_id=owner_id,
            ):
                raise self.PermissionDeniedError(
                    f"No permission to delete document: {doc_id}"
                )

    async def _delete_qdrant_chunks(
        self, collection_name: str, document_id: str
    ) -> int:
        qdrant_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="document_id",
                    match=models.MatchValue(value=document_id),
                )
            ]
        )
        count_result = await self._qdrant_client.count(
            collection_name=collection_name,
            count_filter=qdrant_filter,
            exact=True,
        )
        deleted_count = count_result.count

        await self._qdrant_client.delete(
            collection_name=collection_name,
            points_selector=models.FilterSelector(filter=qdrant_filter),
        )
        return deleted_count

    async def _delete_es_chunks(
        self, document_id: str, request_id: str
    ) -> int:
        try:
            query = {"match": {"document_id": document_id}}
            return await self._es_repo.delete_by_query(
                self._es_index, query, request_id
            )
        except Exception as e:
            self._logger.warning(
                "ES delete failed, continuing",
                exception=e,
                document_id=document_id,
            )
            return 0

    async def _log_activity(
        self,
        collection_name: str,
        document_id: str,
        filename: str,
        deleted_chunks: int,
        user_id: str,
        request_id: str,
    ) -> None:
        try:
            await self._activity_log_service.log(
                collection_name=collection_name,
                action=ActionType.DELETE_DOCUMENT,
                request_id=request_id,
                user_id=user_id,
                detail={
                    "document_id": document_id,
                    "filename": filename,
                    "deleted_chunks_count": deleted_chunks,
                },
            )
        except Exception as e:
            self._logger.warning(
                "Activity log failed, continuing",
                exception=e,
                document_id=document_id,
            )
