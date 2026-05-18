"""Tests for Multi-Query domain schemas."""
import pytest


class TestMultiQueryState:
    """MultiQueryState TypedDict 테스트."""

    def test_state_creation_with_all_fields(self) -> None:
        """모든 필드를 가진 State 생성."""
        from src.domain.multi_query.schemas import MultiQueryState

        state: MultiQueryState = {
            "original_query": "적금 금리",
            "request_id": "req-001",
            "top_k": 10,
            "query_type": "ambiguous",
            "generated_queries": ["적금 금리 현황", "정기적금 이자율"],
            "per_query_results": [],
            "fused_results": [],
            "errors": [],
            "status": "classifying",
        }
        assert state["original_query"] == "적금 금리"
        assert state["query_type"] == "ambiguous"


class TestQueryVariant:
    """QueryVariant Value Object 테스트."""

    def test_query_variant_creation(self) -> None:
        """QueryVariant 생성."""
        from src.domain.multi_query.schemas import QueryVariant

        variant = QueryVariant(query="정기적금 이자율 현황", perspective="유사 용어 확장")
        assert variant.query == "정기적금 이자율 현황"
        assert variant.perspective == "유사 용어 확장"

    def test_query_variant_is_frozen(self) -> None:
        """QueryVariant는 immutable."""
        from src.domain.multi_query.schemas import QueryVariant

        variant = QueryVariant(query="test", perspective="test")
        with pytest.raises(AttributeError):
            variant.query = "changed"


class TestMultiQueryResult:
    """MultiQueryResult Value Object 테스트."""

    def test_result_creation(self) -> None:
        """MultiQueryResult 생성."""
        from src.domain.multi_query.schemas import MultiQueryResult

        result = MultiQueryResult(
            original_query="적금 금리",
            query_type="ambiguous",
            generated_queries=["적금 금리 현황", "정기적금 이자율"],
            results=[],
            total_found=0,
            request_id="req-001",
        )
        assert result.original_query == "적금 금리"
        assert result.total_found == 0

    def test_result_is_frozen(self) -> None:
        """MultiQueryResult는 immutable."""
        from src.domain.multi_query.schemas import MultiQueryResult

        result = MultiQueryResult(
            original_query="test",
            query_type="simple",
            generated_queries=[],
            results=[],
            total_found=0,
            request_id="req-001",
        )
        with pytest.raises(AttributeError):
            result.original_query = "changed"
