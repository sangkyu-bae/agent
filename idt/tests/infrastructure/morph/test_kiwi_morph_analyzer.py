"""KiwiMorphAnalyzer infrastructure tests.

kiwipiepy.Kiwi is mocked to avoid external dependency in CI.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.domain.morph.interfaces import MorphAnalyzerInterface
from src.domain.morph.schemas import MorphAnalysisResult, MorphToken
from src.infrastructure.morph.kiwi_morph_analyzer import KiwiMorphAnalyzer


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────


def _make_kiwi_token(form: str, tag_name: str, start: int, length: int):
    """kiwipiepy Token과 동일한 인터페이스의 mock 객체."""
    tag = SimpleNamespace(name=tag_name)
    return SimpleNamespace(form=form, tag=tag, start=start, len=length)


# ─────────────────────────────────────────────
# KiwiMorphAnalyzer
# ─────────────────────────────────────────────


class TestKiwiMorphAnalyzer:
    @pytest.fixture
    def mock_kiwi_cls(self):
        """Kiwi 클래스를 패치하고 tokenize 반환값을 제어한다."""
        with patch("src.infrastructure.morph.kiwi_morph_analyzer.Kiwi") as mock_cls:
            yield mock_cls

    @pytest.fixture
    def analyzer(self, mock_kiwi_cls):
        mock_kiwi_cls.return_value.tokenize.return_value = []
        return KiwiMorphAnalyzer()

    def test_is_morph_analyzer_interface(self, analyzer):
        assert isinstance(analyzer, MorphAnalyzerInterface)

    def test_analyze_returns_morph_analysis_result(self, mock_kiwi_cls):
        mock_kiwi_cls.return_value.tokenize.return_value = []
        analyzer = KiwiMorphAnalyzer()
        result = analyzer.analyze("테스트")
        assert isinstance(result, MorphAnalysisResult)

    def test_analyze_maps_nng_noun_token(self, mock_kiwi_cls):
        mock_kiwi_cls.return_value.tokenize.return_value = [
            _make_kiwi_token("금융", "NNG", 0, 2),
        ]
        analyzer = KiwiMorphAnalyzer()
        result = analyzer.analyze("금융")
        assert len(result.tokens) == 1
        assert result.tokens[0] == MorphToken(surface="금융", pos="NNG", start=0, length=2)

    def test_analyze_maps_nnp_proper_noun(self, mock_kiwi_cls):
        mock_kiwi_cls.return_value.tokenize.return_value = [
            _make_kiwi_token("한국", "NNP", 0, 2),
        ]
        analyzer = KiwiMorphAnalyzer()
        result = analyzer.analyze("한국")
        assert result.tokens[0].pos == "NNP"

    def test_analyze_maps_vv_verb_token(self, mock_kiwi_cls):
        mock_kiwi_cls.return_value.tokenize.return_value = [
            _make_kiwi_token("분석하", "VV", 0, 3),
        ]
        analyzer = KiwiMorphAnalyzer()
        result = analyzer.analyze("분석하다")
        assert result.tokens[0].pos == "VV"

    def test_analyze_maps_va_adjective_token(self, mock_kiwi_cls):
        mock_kiwi_cls.return_value.tokenize.return_value = [
            _make_kiwi_token("좋", "VA", 0, 1),
        ]
        analyzer = KiwiMorphAnalyzer()
        result = analyzer.analyze("좋다")
        assert result.tokens[0].pos == "VA"

    def test_analyze_empty_text_returns_empty_result(self, mock_kiwi_cls):
        mock_kiwi_cls.return_value.tokenize.return_value = []
        analyzer = KiwiMorphAnalyzer()
        result = analyzer.analyze("")
        assert result.tokens == ()
        assert result.nouns == []

    def test_analyze_preserves_original_text(self, mock_kiwi_cls):
        mock_kiwi_cls.return_value.tokenize.return_value = []
        analyzer = KiwiMorphAnalyzer()
        text = "금융 정책 분석"
        result = analyzer.analyze(text)
        assert result.text == text

    def test_analyze_multiple_tokens(self, mock_kiwi_cls):
        mock_kiwi_cls.return_value.tokenize.return_value = [
            _make_kiwi_token("금융", "NNG", 0, 2),
            MagicMock(form="은", tag=SimpleNamespace(name="JX"), start=2, len=1),
            _make_kiwi_token("정책", "NNG", 4, 2),
        ]
        analyzer = KiwiMorphAnalyzer()
        result = analyzer.analyze("금융은 정책")
        assert len(result.tokens) == 3
        assert result.noun_surfaces == ["금융", "정책"]

    def test_extract_nouns_convenience_method(self, mock_kiwi_cls):
        mock_kiwi_cls.return_value.tokenize.return_value = [
            _make_kiwi_token("이자율", "NNG", 0, 3),
            _make_kiwi_token("정책", "NNG", 4, 2),
        ]
        analyzer = KiwiMorphAnalyzer()
        nouns = analyzer.extract_nouns("이자율 정책")
        assert nouns == ["이자율", "정책"]

    def test_kiwi_instance_reused_across_calls(self, mock_kiwi_cls):
        mock_kiwi_cls.return_value.tokenize.return_value = []
        analyzer = KiwiMorphAnalyzer()
        analyzer.analyze("첫 번째")
        analyzer.analyze("두 번째")
        # Kiwi() 생성자는 1회만 호출되어야 한다
        mock_kiwi_cls.assert_called_once()
