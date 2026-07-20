"""Tests for KbSearchUseCase (kb-retrieval-test Design D1–D5)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.hybrid_search.schemas import HybridSearchResponse
from src.domain.knowledge_base.search_schemas import KbSearchRequest


def _make_user(user_id: int = 1) -> User:
    return User(
        email="test@example.com",
        password_hash="hash",
        role=UserRole.USER,
        status=UserStatus.APPROVED,
        id=user_id,
    )


def _make_kb(kb_id: str = "kb-1", collection_name: str = "col-a"):
    kb = MagicMock()
    kb.id = kb_id
    kb.name = "테스트 KB"
    kb.collection_name = collection_name
    return kb


def _make_embedding_model():
    model = MagicMock()
    model.provider = "openai"
    model.model_name = "text-embedding-3-small"
    return model


def _make_activity_log():
    log = MagicMock()
    log.detail = {"embedding_model": "text-embedding-3-small"}
    return log


def _make_hybrid_response() -> HybridSearchResponse:
    return HybridSearchResponse(
        query="q", results=[], total_found=0, request_id="req-1"
    )


@pytest.fixture
def deps():
    kb_use_case = AsyncMock()
    kb_use_case.get = AsyncMock(return_value=_make_kb())
    activity_log_repo = AsyncMock()
    activity_log_repo.find_all = AsyncMock(return_value=[_make_activity_log()])
    embedding_model_repo = AsyncMock()
    embedding_model_repo.find_by_model_name = AsyncMock(
        return_value=_make_embedding_model()
    )
    return {
        "kb_use_case": kb_use_case,
        "document_guard": AsyncMock(),
        "activity_log_repo": activity_log_repo,
        "embedding_model_repo": embedding_model_repo,
        "embedding_factory": MagicMock(),
        "qdrant_client": AsyncMock(),
        "es_repo": AsyncMock(),
        "es_index": "test-index",
        "search_history_repo": AsyncMock(),
        "logger": MagicMock(),
    }


def _create_use_case(deps):
    from src.application.knowledge_base.search_use_case import KbSearchUseCase

    return KbSearchUseCase(**deps)


def _patch_hybrid():
    return patch(
        "src.application.knowledge_base.search_use_case.HybridSearchUseCase"
    )


class TestKbSearchUseCaseExecute:
    @pytest.mark.asyncio
    async def test_metadata_filter_includes_kb_id_and_collection(self, deps):
        uc = _create_use_case(deps)
        request = KbSearchRequest(query="hello")

        with _patch_hybrid() as MockHybridUC:
            mock_instance = AsyncMock()
            mock_instance.execute = AsyncMock(
                return_value=_make_hybrid_response()
            )
            MockHybridUC.return_value = mock_instance

            result = await uc.execute(
                "kb-1", request, _make_user(), "req-1"
            )

            hybrid_req = mock_instance.execute.call_args[0][0]
            assert hybrid_req.metadata_filter == {
                "collection_name": "col-a",
                "kb_id": "kb-1",
            }

        assert result.kb_id == "kb-1"
        assert result.kb_name == "테스트 KB"
        assert result.collection_name == "col-a"

    @pytest.mark.asyncio
    async def test_document_scope_calls_guard_and_filters(self, deps):
        uc = _create_use_case(deps)
        request = KbSearchRequest(query="q", document_id="doc-9")

        with _patch_hybrid() as MockHybridUC:
            mock_instance = AsyncMock()
            mock_instance.execute = AsyncMock(
                return_value=_make_hybrid_response()
            )
            MockHybridUC.return_value = mock_instance

            result = await uc.execute(
                "kb-1", request, _make_user(), "req-1"
            )

            hybrid_req = mock_instance.execute.call_args[0][0]
            assert hybrid_req.metadata_filter["document_id"] == "doc-9"

        deps["document_guard"].ensure.assert_awaited_once()
        assert result.document_id == "doc-9"

    @pytest.mark.asyncio
    async def test_guard_rejection_propagates(self, deps):
        deps["document_guard"].ensure = AsyncMock(
            side_effect=ValueError("Document 'doc-9' not found in knowledge base")
        )
        uc = _create_use_case(deps)
        request = KbSearchRequest(query="q", document_id="doc-9")

        with pytest.raises(ValueError, match="not found"):
            await uc.execute("kb-1", request, _make_user(), "req-1")

    @pytest.mark.asyncio
    async def test_no_guard_call_without_document_id(self, deps):
        uc = _create_use_case(deps)

        with _patch_hybrid() as MockHybridUC:
            mock_instance = AsyncMock()
            mock_instance.execute = AsyncMock(
                return_value=_make_hybrid_response()
            )
            MockHybridUC.return_value = mock_instance

            await uc.execute(
                "kb-1", KbSearchRequest(query="q"), _make_user(), "req-1"
            )

        deps["document_guard"].ensure.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_kb_permission_error_propagates(self, deps):
        deps["kb_use_case"].get = AsyncMock(
            side_effect=PermissionError("No read access")
        )
        uc = _create_use_case(deps)

        with pytest.raises(PermissionError):
            await uc.execute(
                "kb-1", KbSearchRequest(query="q"), _make_user(), "req-1"
            )

    @pytest.mark.asyncio
    async def test_kb_not_found_propagates(self, deps):
        deps["kb_use_case"].get = AsyncMock(
            side_effect=ValueError("Knowledge base 'kb-x' not found")
        )
        uc = _create_use_case(deps)

        with pytest.raises(ValueError, match="not found"):
            await uc.execute(
                "kb-x", KbSearchRequest(query="q"), _make_user(), "req-1"
            )

    @pytest.mark.asyncio
    async def test_history_saved_with_kb_id(self, deps):
        uc = _create_use_case(deps)

        with _patch_hybrid() as MockHybridUC:
            mock_instance = AsyncMock()
            mock_instance.execute = AsyncMock(
                return_value=_make_hybrid_response()
            )
            MockHybridUC.return_value = mock_instance

            await uc.execute(
                "kb-1", KbSearchRequest(query="q"), _make_user(), "req-1"
            )

        save_kwargs = deps["search_history_repo"].save.call_args.kwargs
        assert save_kwargs["kb_id"] == "kb-1"
        assert save_kwargs["collection_name"] == "col-a"

    @pytest.mark.asyncio
    async def test_history_save_failure_does_not_break_search(self, deps):
        deps["search_history_repo"].save = AsyncMock(
            side_effect=RuntimeError("DB error")
        )
        uc = _create_use_case(deps)

        with _patch_hybrid() as MockHybridUC:
            mock_instance = AsyncMock()
            mock_instance.execute = AsyncMock(
                return_value=_make_hybrid_response()
            )
            MockHybridUC.return_value = mock_instance

            result = await uc.execute(
                "kb-1", KbSearchRequest(query="q"), _make_user(), "req-1"
            )

        assert result.total_found == 0

    @pytest.mark.asyncio
    async def test_weights_passed_to_hybrid_request(self, deps):
        uc = _create_use_case(deps)
        request = KbSearchRequest(
            query="q", bm25_weight=0.8, vector_weight=0.2, top_k=7
        )

        with _patch_hybrid() as MockHybridUC:
            mock_instance = AsyncMock()
            mock_instance.execute = AsyncMock(
                return_value=_make_hybrid_response()
            )
            MockHybridUC.return_value = mock_instance

            await uc.execute("kb-1", request, _make_user(), "req-1")

            hybrid_req = mock_instance.execute.call_args[0][0]
            assert hybrid_req.bm25_weight == 0.8
            assert hybrid_req.vector_weight == 0.2
            assert hybrid_req.top_k == 7


class TestKbSearchRequestValidation:
    def test_empty_query_rejected(self):
        with pytest.raises(ValueError, match="query"):
            KbSearchRequest(query="   ")

    def test_invalid_weight_rejected(self):
        with pytest.raises(ValueError, match="bm25_weight"):
            KbSearchRequest(query="q", bm25_weight=1.5)
