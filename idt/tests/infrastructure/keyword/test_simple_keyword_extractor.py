"""Tests for SimpleKeywordExtractor. Infrastructure: mock 허용."""
import pytest


class TestSimpleKeywordExtractor:
    """SimpleKeywordExtractor 단위 테스트."""

    @pytest.fixture
    def extractor(self):
        from src.infrastructure.keyword.simple_keyword_extractor import SimpleKeywordExtractor
        return SimpleKeywordExtractor()

    def test_extracts_top_korean_keywords_by_frequency(self, extractor):
        """가장 빈번한 한국어 단어가 첫 번째로 반환된다."""
        text = "금융 정책 금융 이자율 정책 금융"
        result = extractor.extract(text, top_n=5)
        assert result.keywords[0] == "금융"

    def test_extracts_top_english_keywords_by_frequency(self, extractor):
        """가장 빈번한 영어 단어가 첫 번째로 반환된다."""
        text = "machine learning deep learning machine learning"
        result = extractor.extract(text, top_n=5)
        assert result.keywords[0] == "learning"

    def test_single_char_korean_tokens_filtered(self, extractor):
        """1글자 한국어 토큰은 결과에서 제외된다."""
        text = "이 가 그 것 나 우리는 정책"
        result = extractor.extract(text, top_n=10)
        for kw in result.keywords:
            assert len(kw) >= 2

    def test_top_n_limits_output(self, extractor):
        """top_n 개수를 초과하지 않는다."""
        text = " ".join([f"단어{i}" for i in range(20)])
        result = extractor.extract(text, top_n=3)
        assert len(result.keywords) <= 3

    def test_empty_text_returns_empty(self, extractor):
        """빈 텍스트는 빈 결과를 반환한다."""
        result = extractor.extract("", top_n=10)
        assert result.keywords == []
        assert result.keyword_frequencies == {}

    def test_frequency_map_included_in_result(self, extractor):
        """keyword_frequencies에 빈도수가 포함된다."""
        text = "금융 금융 정책"
        result = extractor.extract(text, top_n=5)
        assert result.keyword_frequencies.get("금융") == 2
        assert result.keyword_frequencies.get("정책") == 1

    def test_keywords_sorted_by_frequency_descending(self, extractor):
        """키워드는 빈도 내림차순으로 정렬된다."""
        text = "정책 금융 금융 금융 정책"
        result = extractor.extract(text, top_n=5)
        if len(result.keywords) >= 2:
            first_freq = result.keyword_frequencies[result.keywords[0]]
            second_freq = result.keyword_frequencies[result.keywords[1]]
            assert first_freq >= second_freq

    def test_mixed_korean_english_text(self, extractor):
        """한국어와 영어 혼합 텍스트에서 모두 추출된다."""
        text = "금융 finance 금융 finance policy 정책"
        result = extractor.extract(text, top_n=10)
        assert "금융" in result.keywords
        assert "finance" in result.keywords

    def test_punctuation_does_not_appear_in_keywords(self, extractor):
        """구두점이 키워드에 포함되지 않는다."""
        text = "금융, 정책. 이자율! 금융?"
        result = extractor.extract(text, top_n=10)
        for kw in result.keywords:
            assert not any(p in kw for p in [",", ".", "!", "?"])

    def test_default_top_n_is_10(self, extractor):
        """top_n 기본값은 10이다."""
        text = " ".join([f"단어{i}단어{i}" for i in range(20)])
        result = extractor.extract(text)
        assert len(result.keywords) <= 10
