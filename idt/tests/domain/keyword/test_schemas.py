"""Tests for keyword domain schemas. Domain: mock 금지."""


class TestKeywordExtractionResult:
    def test_create_with_keywords_and_frequencies(self):
        from src.domain.keyword.schemas import KeywordExtractionResult
        r = KeywordExtractionResult(
            keywords=["금융", "정책"],
            keyword_frequencies={"금융": 3, "정책": 2},
        )
        assert r.keywords == ["금융", "정책"]
        assert r.keyword_frequencies["금융"] == 3

    def test_empty_result(self):
        from src.domain.keyword.schemas import KeywordExtractionResult
        r = KeywordExtractionResult(keywords=[], keyword_frequencies={})
        assert r.keywords == []
