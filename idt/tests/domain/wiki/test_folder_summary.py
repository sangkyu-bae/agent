"""Domain 테스트: WikiFolderSummary 엔티티 + 조상 경로 확장 (wiki-folder-summaries D1/D2)."""
from datetime import datetime

import pytest

from src.domain.wiki.entity import WikiFolderSummary
from src.domain.wiki.policies import WikiPolicy


class TestWikiFolderSummaryEntity:

    def test_creates_with_fields(self):
        s = WikiFolderSummary(
            id="f1", agent_id="a1", path="여신/한도",
            summary="한도 관련 지식", article_count=3,
            updated_at=datetime(2026, 7, 25),
        )
        assert s.path == "여신/한도"
        assert s.article_count == 3

    def test_article_count_defaults_to_zero(self):
        s = WikiFolderSummary(id="f1", agent_id="a1", path="여신", summary="s")
        assert s.article_count == 0
        assert s.updated_at is None


class TestExpandAncestors:
    """path 자신+조상 확장 — 재증류 대상 집합 (D2, 깊이<=3이라 최대 3개)."""

    def test_depth3_returns_self_and_ancestors_bottom_up(self):
        assert WikiPolicy.expand_ancestors("여신/한도/개인") == [
            "여신/한도/개인", "여신/한도", "여신",
        ]

    def test_depth1_returns_self_only(self):
        assert WikiPolicy.expand_ancestors("여신") == ["여신"]

    def test_none_returns_empty(self):
        assert WikiPolicy.expand_ancestors(None) == []
