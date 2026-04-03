"""Tests for Elasticsearch domain Value Objects.

Domain tests: mock 금지 (CLAUDE.md Rule 6)
"""
import pytest


class TestESDocument:
    """ESDocument Value Object 테스트."""

    def test_create_with_required_fields(self):
        """id, body, index 필드로 생성 가능하다."""
        from src.domain.elasticsearch.schemas import ESDocument

        doc = ESDocument(id="doc-1", body={"title": "hello"}, index="my-index")

        assert doc.id == "doc-1"
        assert doc.body == {"title": "hello"}
        assert doc.index == "my-index"

    def test_body_accepts_nested_dict(self):
        """body는 중첩 딕셔너리를 허용한다."""
        from src.domain.elasticsearch.schemas import ESDocument

        doc = ESDocument(
            id="doc-2",
            body={"title": "t", "meta": {"author": "alice", "tags": ["a", "b"]}},
            index="idx",
        )

        assert doc.body["meta"]["author"] == "alice"

    def test_id_must_be_string(self):
        """id는 문자열이어야 한다."""
        from src.domain.elasticsearch.schemas import ESDocument

        doc = ESDocument(id="str-id", body={}, index="idx")
        assert isinstance(doc.id, str)


class TestESSearchQuery:
    """ESSearchQuery Value Object 테스트."""

    def test_create_with_required_fields(self):
        """index와 query만으로 생성 가능하다."""
        from src.domain.elasticsearch.schemas import ESSearchQuery

        q = ESSearchQuery(index="my-index", query={"match": {"title": "hello"}})

        assert q.index == "my-index"
        assert q.query == {"match": {"title": "hello"}}

    def test_default_size_is_10(self):
        """기본 size는 10이다."""
        from src.domain.elasticsearch.schemas import ESSearchQuery

        q = ESSearchQuery(index="idx", query={})
        assert q.size == 10

    def test_default_from_is_0(self):
        """기본 from_은 0이다."""
        from src.domain.elasticsearch.schemas import ESSearchQuery

        q = ESSearchQuery(index="idx", query={})
        assert q.from_ == 0

    def test_default_source_fields_is_empty_list(self):
        """기본 source_fields는 빈 리스트이다."""
        from src.domain.elasticsearch.schemas import ESSearchQuery

        q = ESSearchQuery(index="idx", query={})
        assert q.source_fields == []

    def test_custom_size_and_from(self):
        """size와 from_을 커스텀으로 설정할 수 있다."""
        from src.domain.elasticsearch.schemas import ESSearchQuery

        q = ESSearchQuery(index="idx", query={}, size=5, from_=20)
        assert q.size == 5
        assert q.from_ == 20

    def test_source_fields_can_be_specified(self):
        """source_fields를 지정할 수 있다."""
        from src.domain.elasticsearch.schemas import ESSearchQuery

        q = ESSearchQuery(index="idx", query={}, source_fields=["title", "content"])
        assert q.source_fields == ["title", "content"]


class TestESSearchResult:
    """ESSearchResult Value Object 테스트."""

    def test_create_with_all_fields(self):
        """id, score, source, index 필드로 생성 가능하다."""
        from src.domain.elasticsearch.schemas import ESSearchResult

        result = ESSearchResult(
            id="hit-1",
            score=0.95,
            source={"title": "result"},
            index="my-index",
        )

        assert result.id == "hit-1"
        assert result.score == 0.95
        assert result.source == {"title": "result"}
        assert result.index == "my-index"

    def test_score_can_be_zero(self):
        """score는 0.0일 수 있다 (필터 쿼리 결과)."""
        from src.domain.elasticsearch.schemas import ESSearchResult

        result = ESSearchResult(id="x", score=0.0, source={}, index="idx")
        assert result.score == 0.0
