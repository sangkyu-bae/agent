"""Tests for WebSearchDecision schema."""

import pytest
from pydantic import ValidationError

from src.domain.search_decision.schemas import WebSearchDecision


class TestWebSearchDecision:
    def test_requires_needs_web_search(self):
        with pytest.raises(ValidationError):
            WebSearchDecision()  # type: ignore[call-arg]

    def test_reason_defaults_to_empty(self):
        decision = WebSearchDecision(needs_web_search=True)
        assert decision.needs_web_search is True
        assert decision.reason == ""

    def test_full_construction(self):
        decision = WebSearchDecision(
            needs_web_search=False, reason="엑셀 데이터만으로 충분"
        )
        assert decision.needs_web_search is False
        assert decision.reason == "엑셀 데이터만으로 충분"
