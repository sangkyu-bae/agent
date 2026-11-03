from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.doc_browse.delete_document_use_case import (
    DeleteDocumentUseCase,
)
from src.domain.collection.permission_schemas import (
    CollectionPermission,
    CollectionScope,
)
from src.domain.doc_browse.policies import DocumentDeletePolicy
from src.domain.doc_browse.schemas import DocumentMetadata


def _make_metadata(
    document_id: str = "doc-123",
    user_id: str = "42",
    collection_name: str = "test-col",
    filename: str = "test.pdf",
) -> DocumentMetadata:
    return DocumentMetadata(
        document_id=document_id,
        collection_name=collection_name,
        filename=filename,
        category="general",
        user_id=user_id,
        chunk_count=10,
        chunk_strategy="parent_child",
    )


def _make_permission(owner_id: int = 42) -> CollectionPermission:
    return CollectionPermission(
        collection_name="test-col",
        owner_id=owner_id,
        scope=CollectionScope.PERSONAL,
    )


def _make_count_result(count: int):
    result = MagicMock()
    result.count = count
    return result


@pytest.fixture
def deps():
    metadata_repo = AsyncMock()
    qdrant_client = AsyncMock()
    es_repo = AsyncMock()
    permission_service = AsyncMock()
    activity_log_service = AsyncMock()
    logger = MagicMock()

    uc = DeleteDocumentUseCase(
        document_metadata_repo=metadata_repo,
        qdrant_client=qdrant_client,
        es_repo=es_repo,
        es_index="documents",
        permission_service=permission_service,
        activity_log_service=activity_log_service,
        policy=DocumentDeletePolicy(),
        logger=logger,
    )
    return {
        "uc": uc,
        "metadata_repo": metadata_repo,
        "qdrant_client": qdrant_client,
        "es_repo": es_repo,
        "permission_service": permission_service,
        "activity_log_service": activity_log_service,
        "logger": logger,
    }


class TestDeleteVerified:
    """kb-document-management Design §6.2 — 저장소 실패 시 메타데이터 유지."""

    @pytest.mark.asyncio
    async def test_deletes_stores_metadata_and_logs(self, deps):
        deps["qdrant_client"].count.return_value = _make_count_result(10)
        deps["es_repo"].delete_by_query.return_value = 8

        result = await deps["uc"].delete_verified(
            "test-col", "doc-123", "a.pdf", "42", "req-1",
            extra_detail={"kb_id": "kb-1"},
        )

        assert result.document_id == "doc-123"
        assert result.collection_name == "test-col"
        assert result.filename == "a.pdf"
        assert result.deleted_qdrant_chunks == 10
        assert result.deleted_es_chunks == 8
        assert result.status == "deleted"
        deps["qdrant_client"].delete.assert_awaited_once()
        deps["metadata_repo"].delete_by_document_id.assert_awaited_once_with(
            "doc-123", "req-1"
        )
        detail = deps["activity_log_service"].log.call_args.kwargs["detail"]
        assert detail["kb_id"] == "kb-1"
        assert detail["document_id"] == "doc-123"
        assert detail["deleted_chunks_count"] == 10

    @pytest.mark.asyncio
    async def test_does_not_check_permission(self, deps):
        deps["qdrant_client"].count.return_value = _make_count_result(1)
        deps["es_repo"].delete_by_query.return_value = 1

        await deps["uc"].delete_verified(
            "test-col", "doc-123", "a.pdf", "42", "req-1"
        )

        deps["permission_service"].find_permission.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_es_failure_keeps_metadata(self, deps):
        deps["qdrant_client"].count.return_value = _make_count_result(10)
        deps["es_repo"].delete_by_query.side_effect = RuntimeError("es down")

        with pytest.raises(DeleteDocumentUseCase.StoreDeleteFailedError):
            await deps["uc"].delete_verified(
                "test-col", "doc-123", "a.pdf", "42", "req-1"
            )

        deps["metadata_repo"].delete_by_document_id.assert_not_awaited()
        deps["activity_log_service"].log.assert_not_awaited()
        deps["logger"].error.assert_called_once()
        assert isinstance(
            deps["logger"].error.call_args.kwargs["exception"], RuntimeError
        )

    @pytest.mark.asyncio
    async def test_qdrant_failure_skips_es_and_keeps_metadata(self, deps):
        deps["qdrant_client"].count.side_effect = RuntimeError("qdrant down")

        with pytest.raises(DeleteDocumentUseCase.StoreDeleteFailedError):
            await deps["uc"].delete_verified(
                "test-col", "doc-123", "a.pdf", "42", "req-1"
            )

        deps["es_repo"].delete_by_query.assert_not_awaited()
        deps["metadata_repo"].delete_by_document_id.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_activity_log_failure_is_ignored(self, deps):
        deps["qdrant_client"].count.return_value = _make_count_result(1)
        deps["es_repo"].delete_by_query.return_value = 1
        deps["activity_log_service"].log.side_effect = RuntimeError("log down")

        result = await deps["uc"].delete_verified(
            "test-col", "doc-123", "a.pdf", "42", "req-1"
        )

        assert result.status == "deleted"


class TestExecuteSingle:

    @pytest.mark.asyncio
    async def test_success_uploader_deletes_own_document(self, deps):
        uc = deps["uc"]
        deps["metadata_repo"].find_by_document_id.return_value = _make_metadata()
        deps["permission_service"].find_permission.return_value = _make_permission(
            owner_id=999
        )
        deps["qdrant_client"].count.return_value = _make_count_result(10)
        deps["es_repo"].delete_by_query.return_value = 10

        result = await uc.execute_single("test-col", "doc-123", "42")

        assert result.status == "deleted"
        assert result.document_id == "doc-123"
        assert result.deleted_qdrant_chunks == 10
        assert result.deleted_es_chunks == 10
        deps["qdrant_client"].delete.assert_awaited_once()
        deps["metadata_repo"].delete_by_document_id.assert_awaited_once()
        deps["activity_log_service"].log.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_document_not_found_raises_404(self, deps):
        uc = deps["uc"]
        deps["metadata_repo"].find_by_document_id.return_value = None

        with pytest.raises(uc.DocumentNotFoundError):
            await uc.execute_single("test-col", "doc-missing", "42")

    @pytest.mark.asyncio
    async def test_permission_denied_raises_403(self, deps):
        uc = deps["uc"]
        deps["metadata_repo"].find_by_document_id.return_value = _make_metadata(
            user_id="42"
        )
        deps["permission_service"].find_permission.return_value = _make_permission(
            owner_id=999
        )

        with pytest.raises(uc.PermissionDeniedError):
            await uc.execute_single("test-col", "doc-123", "888")

    @pytest.mark.asyncio
    async def test_es_failure_continues(self, deps):
        uc = deps["uc"]
        deps["metadata_repo"].find_by_document_id.return_value = _make_metadata()
        deps["permission_service"].find_permission.return_value = _make_permission()
        deps["qdrant_client"].count.return_value = _make_count_result(5)
        deps["es_repo"].delete_by_query.side_effect = Exception("ES down")

        result = await uc.execute_single("test-col", "doc-123", "42")

        assert result.status == "deleted"
        assert result.deleted_es_chunks == 0
        deps["metadata_repo"].delete_by_document_id.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_collection_owner_can_delete(self, deps):
        uc = deps["uc"]
        deps["metadata_repo"].find_by_document_id.return_value = _make_metadata(
            user_id="other-user"
        )
        deps["permission_service"].find_permission.return_value = _make_permission(
            owner_id=100
        )
        deps["qdrant_client"].count.return_value = _make_count_result(3)
        deps["es_repo"].delete_by_query.return_value = 3

        result = await uc.execute_single("test-col", "doc-123", "100")

        assert result.status == "deleted"

    @pytest.mark.asyncio
    async def test_admin_can_delete_any_document(self, deps):
        uc = deps["uc"]
        deps["metadata_repo"].find_by_document_id.return_value = _make_metadata(
            user_id="other-user"
        )
        deps["permission_service"].find_permission.return_value = _make_permission(
            owner_id=999
        )
        deps["qdrant_client"].count.return_value = _make_count_result(3)
        deps["es_repo"].delete_by_query.return_value = 3

        result = await uc.execute_single(
            "test-col", "doc-123", "777", user_role="admin"
        )

        assert result.status == "deleted"


class TestExecuteBatch:

    @pytest.mark.asyncio
    async def test_batch_all_success(self, deps):
        uc = deps["uc"]
        meta1 = _make_metadata(document_id="doc-1", user_id="42")
        meta2 = _make_metadata(document_id="doc-2", user_id="42")
        deps["metadata_repo"].find_by_document_id.side_effect = [
            meta1, meta2, meta1, meta2,
        ]
        deps["permission_service"].find_permission.return_value = _make_permission()
        deps["qdrant_client"].count.return_value = _make_count_result(5)
        deps["es_repo"].delete_by_query.return_value = 5

        result = await uc.execute_batch("test-col", ["doc-1", "doc-2"], "42")

        assert result["total"] == 2
        assert result["success_count"] == 2
        assert result["failure_count"] == 0

    @pytest.mark.asyncio
    async def test_batch_partial_failure(self, deps):
        uc = deps["uc"]
        meta1 = _make_metadata(document_id="doc-1", user_id="42")
        meta2 = _make_metadata(document_id="doc-2", user_id="42")
        deps["metadata_repo"].find_by_document_id.side_effect = [
            meta1, meta2,  # pre-validation
            meta1,         # execute_single for doc-1
            meta2,         # execute_single for doc-2
        ]
        deps["permission_service"].find_permission.return_value = _make_permission()
        deps["qdrant_client"].count.side_effect = [
            _make_count_result(5),
            Exception("Qdrant connection lost"),
        ]
        deps["es_repo"].delete_by_query.return_value = 5

        result = await uc.execute_batch("test-col", ["doc-1", "doc-2"], "42")

        assert result["total"] == 2
        assert result["success_count"] == 1
        assert result["failure_count"] == 1
        assert result["results"][0]["status"] == "deleted"
        assert result["results"][1]["status"] == "failed"
        assert result["results"][1]["error"] is not None

    @pytest.mark.asyncio
    async def test_batch_permission_denied_fails_all(self, deps):
        uc = deps["uc"]
        meta = _make_metadata(user_id="other-user")
        deps["metadata_repo"].find_by_document_id.return_value = meta
        deps["permission_service"].find_permission.return_value = _make_permission(
            owner_id=999
        )

        with pytest.raises(uc.PermissionDeniedError):
            await uc.execute_batch("test-col", ["doc-1"], "888")
