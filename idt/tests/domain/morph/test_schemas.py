"""MorphToken, MorphAnalysisResult domain schema tests.

Domain tests — no mocks.
"""
import pytest

from src.domain.morph.schemas import MorphAnalysisResult, MorphToken

# ─────────────────────────────────────────────
# MorphToken
# ─────────────────────────────────────────────


class TestMorphToken:
    def test_creates_with_all_fields(self):
        token = MorphToken(surface="정책", pos="NNG", start=0, length=2)
        assert token.surface == "정책"
        assert token.pos == "NNG"
        assert token.start == 0
        assert token.length == 2

    def test_is_frozen_immutable(self):
        token = MorphToken(surface="금융", pos="NNG", start=3, length=2)
        with pytest.raises((AttributeError, TypeError)):
            token.surface = "수정"  # type: ignore[misc]

    def test_equality_by_value(self):
        t1 = MorphToken(surface="분석", pos="NNG", start=0, length=2)
        t2 = MorphToken(surface="분석", pos="NNG", start=0, length=2)
        assert t1 == t2

    def test_different_tokens_not_equal(self):
        t1 = MorphToken(surface="분석", pos="NNG", start=0, length=2)
        t2 = MorphToken(surface="분석", pos="VV", start=0, length=2)
        assert t1 != t2


# ─────────────────────────────────────────────
# MorphAnalysisResult
# ─────────────────────────────────────────────


class TestMorphAnalysisResult:
    def _make_tokens(self) -> tuple:
        return (
            MorphToken(surface="금융", pos="NNG", start=0, length=2),
            MorphToken(surface="정책", pos="NNG", start=3, length=2),
            MorphToken(surface="한국", pos="NNP", start=6, length=2),
            MorphToken(surface="것", pos="NNB", start=9, length=1),
            MorphToken(surface="분석하다", pos="VV", start=11, length=4),
            MorphToken(surface="좋다", pos="VA", start=16, length=2),
            MorphToken(surface="매우", pos="MAG", start=19, length=2),
        )

    def test_creates_with_tokens_and_text(self):
        tokens = self._make_tokens()
        result = MorphAnalysisResult(tokens=tokens, text="금융 정책 한국 것 분석하다 좋다 매우")
        assert len(result.tokens) == 7
        assert result.text == "금융 정책 한국 것 분석하다 좋다 매우"

    def test_nouns_returns_nng_nnp_nnb(self):
        result = MorphAnalysisResult(tokens=self._make_tokens(), text="test")
        nouns = result.nouns
        pos_tags = {t.pos for t in nouns}
        assert pos_tags == {"NNG", "NNP", "NNB"}
        assert len(nouns) == 4

    def test_verbs_returns_vv_only(self):
        result = MorphAnalysisResult(tokens=self._make_tokens(), text="test")
        verbs = result.verbs
        assert all(t.pos == "VV" for t in verbs)
        assert len(verbs) == 1
        assert verbs[0].surface == "분석하다"

    def test_adjectives_returns_va_only(self):
        result = MorphAnalysisResult(tokens=self._make_tokens(), text="test")
        adjectives = result.adjectives
        assert all(t.pos == "VA" for t in adjectives)
        assert len(adjectives) == 1
        assert adjectives[0].surface == "좋다"

    def test_noun_surfaces_returns_surface_strings(self):
        result = MorphAnalysisResult(tokens=self._make_tokens(), text="test")
        surfaces = result.noun_surfaces
        assert "금융" in surfaces
        assert "정책" in surfaces
        assert "한국" in surfaces
        assert "것" in surfaces
        assert len(surfaces) == 4

    def test_empty_tokens_all_properties_empty(self):
        result = MorphAnalysisResult(tokens=(), text="")
        assert result.nouns == []
        assert result.verbs == []
        assert result.adjectives == []
        assert result.noun_surfaces == []

    def test_is_frozen_immutable(self):
        result = MorphAnalysisResult(tokens=(), text="test")
        with pytest.raises((AttributeError, TypeError)):
            result.text = "수정"  # type: ignore[misc]

    def test_noun_surfaces_order_preserved(self):
        tokens = (
            MorphToken(surface="이자율", pos="NNG", start=0, length=3),
            MorphToken(surface="금융", pos="NNG", start=4, length=2),
        )
        result = MorphAnalysisResult(tokens=tokens, text="이자율 금융")
        assert result.noun_surfaces == ["이자율", "금융"]
