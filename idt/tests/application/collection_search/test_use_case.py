"""Tests for CollectionSearchUseCase."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.collection_search.schemas import (
    CollectionSearchRequest,
)
from src.domain.hybrid_search.schemas import HybridSearchResponse


def _make_user(user_id: int = 1) -> User:
    return User(
        email="test@example.com",
        password_hash="hash",
        role=UserRole.USER,
        status=UserStatus.APPROVED,
        id=user_id,
    )


def _make_embedding_model():
    model = MagicMock()
    model.provider = "openai"
    model.model_name = "text-embedding-3-small"
    return model


def _make_activity_log(embedding_model: str = "text-embedding-3-small"):
    log = MagicMock()
    log.detail = {"embedding_model": embedding_model}
    return log


def _make_hybrid_response() -> HybridSearchResponse:
    return HybridSearchResponse(
        query="q",
        results=[],
        total_found=0,
        request_id="req-1",
    )


@pytest.fixture
def deps():
    """Create mocked dependencies for CollectionSearchUseCase."""
    return {
        "collection_repo": AsyncMock(),
        "permission_service": AsyncMock(),
        "activity_log_repo": AsyncMock(),
        "embedding_model_repo": AsyncMock(),
        "embedding_factory": MagicMock(),
        "qdrant_client": AsyncMock(),
        "es_repo": AsyncMock(),
        "es_index": "test-index",
        "search_history_repo": AsyncMock(),
        "logger": MagicMock(),
    }


def _create_use_case(deps):
    from src.application.collection_search.use_case import CollectionSearchUseCase

    return CollectionSearchUseCase(**deps)


class TestCollectionSearchUseCaseExecute:
    @pytest.mark.asyncio
    async def test_normal_search_returns_response(self, deps):
        deps["collection_repo"].collection_exists = AsyncMock(return_value=True)
        deps["activity_log_repo"].find_all = AsyncMock(
            return_value=[_make_activity_log()]
        )
        deps["embedding_model_repo"].find_by_model_name = AsyncMock(
            return_value=_make_embedding_model()
        )

        uc = _create_use_case(deps)
        request = CollectionSearchRequest(collection_name="test-col", query="hello")

        with patch(
            "src.application.collection_search.use_case.HybridSearchUseCase"
        ) as MockHybridUC:
            mock_instance = AsyncMock()
            mock_instance.execute = AsyncMock(return_value=_make_hybrid_response())
            MockHybridUC.return_value = mock_instance

            result = await uc.execute(request, _make_user(), "req-1")

        assert result.collection_name == "test-col"
        assert result.query == "q"

    @pytest.mark.asyncio
    async def test_permission_error_propagates(self, deps):
        deps["permission_service"].check_read_access = AsyncMock(
            side_effect=PermissionError("No read access")
        )

        uc = _create_use_case(deps)
        request = CollectionSearchRequest(collection_name="c", query="q")

        with pytest.raises(PermissionError):
            await uc.execute(request, _make_user(), "req-1")

    @pytest.mark.asyncio
    async def test_collection_not_found_raises(self, deps):
        from src.application.collection_search.use_case import (
            CollectionNotFoundError,
        )

        deps["collection_repo"].collection_exists = AsyncMock(return_value=False)

        uc = _create_use_case(deps)
        request = CollectionSearchRequest(collection_name="missing", query="q")

        with pytest.raises(CollectionNotFoundError):
            await uc.execute(request, _make_user(), "req-1")

    @pytest.mark.asyncio
    async def test_embedding_model_not_found_raises(self, deps):
        deps["collection_repo"].collection_exists = AsyncMock(return_value=True)
        deps["activity_log_repo"].find_all = AsyncMock(return_value=[])

        uc = _create_use_case(deps)
        request = CollectionSearchRequest(collection_name="c", query="q")

        with pytest.raises(ValueError, match="Cannot determine"):
            await uc.execute(request, _make_user(), "req-1")

    @pytest.mark.asyncio
    async def test_document_scoped_search_passes_document_id(self, deps):
        deps["collection_repo"].collection_exists = AsyncMock(return_value=True)
        deps["activity_log_repo"].find_all = AsyncMock(
            return_value=[_make_activity_log()]
        )
        deps["embedding_model_repo"].find_by_model_name = AsyncMock(
            return_value=_make_embedding_model()
        )

        uc = _create_use_case(deps)
        request = CollectionSearchRequest(
            collection_name="c", query="q", document_id="doc-123"
        )

        with patch(
            "src.application.collection_search.use_case.HybridSearchUseCase"
        ) as MockHybridUC:
            mock_instance = AsyncMock()
            mock_instance.execute = AsyncMock(return_value=_make_hybrid_response())
            MockHybridUC.return_value = mock_instance

            result = await uc.execute(request, _make_user(), "req-1")

        assert result.document_id == "doc-123"

    @pytest.mark.asyncio
    async def test_history_save_failure_does_not_break_search(self, deps):
        deps["collection_repo"].collection_exists = AsyncMock(return_value=True)
        deps["activity_log_repo"].find_all = AsyncMock(
            return_value=[_make_activity_log()]
        )
        deps["embedding_model_repo"].find_by_model_name = AsyncMock(
            return_value=_make_embedding_model()
        )
        deps["search_history_repo"].save = AsyncMock(
            side_effect=RuntimeError("DB error")
        )

        uc = _create_use_case(deps)
        request = CollectionSearchRequest(collection_name="c", query="q")

        with patch(
            "src.application.collection_search.use_case.HybridSearchUseCase"
        ) as MockHybridUC:
            mock_instance = AsyncMock()
            mock_instance.execute = AsyncMock(return_value=_make_hybrid_response())
            MockHybridUC.return_value = mock_instance

            result = await uc.execute(request, _make_user(), "req-1")

        assert result.total_found == 0

    @pytest.mark.asyncio
    async def test_weights_passed_to_hybrid_request(self, deps):
        deps["collection_repo"].collection_exists = AsyncMock(return_value=True)
        deps["activity_log_repo"].find_all = AsyncMock(
            return_value=[_make_activity_log()]
        )
        deps["embedding_model_repo"].find_by_model_name = AsyncMock(
            return_value=_make_embedding_model()
        )

        uc = _create_use_case(deps)
        request = CollectionSearchRequest(
            collection_name="c", query="q", bm25_weight=0.8, vector_weight=0.2
        )

        with patch(
            "src.application.collection_search.use_case.HybridSearchUseCase"
        ) as MockHybridUC:
            mock_instance = AsyncMock()
            mock_instance.execute = AsyncMock(return_value=_make_hybrid_response())
            MockHybridUC.return_value = mock_instance

            await uc.execute(request, _make_user(), "req-1")

            call_args = mock_instance.execute.call_args
            hybrid_req = call_args[0][0]
            assert hybrid_req.bm25_weight == 0.8
            assert hybrid_req.vector_weight == 0.2
