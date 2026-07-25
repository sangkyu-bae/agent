"""_build_qdrant_filter metadata_lenient 변환 테스트 (rag-auth-filter-fix D2)."""
from unittest.mock import AsyncMock, MagicMock

from qdrant_client import models

from src.domain.vector.value_objects import SearchFilter
from src.infrastructure.vector.qdrant_vectorstore import QdrantVectorStore


def _store() -> QdrantVectorStore:
    client = MagicMock()
    client.query_points = AsyncMock(return_value=MagicMock(points=[]))
    embedding = MagicMock()
    return QdrantVectorStore(
        client=client, embedding=embedding, collection_name="test"
    )


class TestBuildQdrantFilterLenient:
    def test_lenient_key_builds_nested_should_with_is_empty(self):
        sf = SearchFilter(metadata_lenient={"visibility": "public"})

        result = _store()._build_qdrant_filter(sf)

        assert len(result.must) == 1
        nested = result.must[0]
        assert isinstance(nested, models.Filter)
        match_cond, empty_cond = nested.should
        assert isinstance(match_cond, models.FieldCondition)
        assert match_cond.key == "visibility"
        assert match_cond.match.value == "public"
        assert isinstance(empty_cond, models.IsEmptyCondition)
        assert empty_cond.is_empty.key == "visibility"

    def test_hard_metadata_unchanged(self):
        sf = SearchFilter(metadata={"category": "policy"})

        result = _store()._build_qdrant_filter(sf)

        cond = result.must[0]
        assert isinstance(cond, models.FieldCondition)
        assert cond.key == "category"

    def test_hard_and_lenient_compose_as_and(self):
        sf = SearchFilter(
            metadata={"category": "policy"},
            metadata_lenient={"visibility": "public"},
        )

        result = _store()._build_qdrant_filter(sf)

        assert len(result.must) == 2

    def test_is_empty_reflects_lenient(self):
        assert SearchFilter().is_empty()
        assert not SearchFilter(metadata_lenient={"visibility": "public"}).is_empty()
