"""Tests for RoutingPolicy."""

import pytest

from src.domain.research_agent.policy import RoutingPolicy


class TestRoutingPolicy:
    """Tests for RoutingPolicy."""

    class TestConstants:
        """Tests for policy constants."""

        def test_max_retry_count_is_three(self) -> None:
            """MAX_RETRY_COUNT should be 3."""
            assert RoutingPolicy.MAX_RETRY_COUNT == 3

        def test_web_search_keywords_is_list(self) -> None:
            """WEB_SEARCH_KEYWORDS should be a list."""
            assert isinstance(RoutingPolicy.WEB_SEARCH_KEYWORDS, list)

        def test_web_search_keywords_not_empty(self) -> None:
            """WEB_SEARCH_KEYWORDS should not be empty."""
            assert len(RoutingPolicy.WEB_SEARCH_KEYWORDS) > 0

    class TestShouldUseWebSearch:
        """Tests for should_use_web_search method."""

        def test_returns_true_with_latest_keyword(self) -> None:
            """Question with '최신' should return True."""
            result = RoutingPolicy.should_use_web_search("최신 AI 동향은 무엇인가요?")
            assert result is True

        def test_returns_true_with_current_keyword(self) -> None:
            """Question with '현재' should return True."""
            result = RoutingPolicy.should_use_web_search("현재 시장 상황은 어떻습니까?")
            assert result is True

        def test_returns_true_with_today_keyword(self) -> None:
            """Question with '오늘' should return True."""
            result = RoutingPolicy.should_use_web_search("오늘 날씨는 어떻습니까?")
            assert result is True

        def test_returns_true_with_recent_keyword(self) -> None:
            """Question with '최근' should return True."""
            result = RoutingPolicy.should_use_web_search("최근 경제 뉴스가 있나요?")
            assert result is True

        def test_returns_true_with_news_keyword(self) -> None:
            """Question with '뉴스' should return True."""
            result = RoutingPolicy.should_use_web_search("뉴스를 검색해주세요")
            assert result is True

        def test_returns_true_with_real_time_keyword(self) -> None:
            """Question with '실시간' should return True."""
            result = RoutingPolicy.should_use_web_search("실시간 정보가 필요합니다")
            assert result is True

        def test_returns_false_without_keywords(self) -> None:
            """Question without web search keywords should return False."""
            result = RoutingPolicy.should_use_web_search("금융 정책에 대해 설명해주세요")
            assert result is False

        def test_returns_false_with_empty_question(self) -> None:
            """Empty question should return False."""
            result = RoutingPolicy.should_use_web_search("")
            assert result is False

        def test_returns_false_with_none_question(self) -> None:
            """None question should return False."""
            result = RoutingPolicy.should_use_web_search(None)
            assert result is False

        def test_returns_false_with_whitespace_question(self) -> None:
            """Whitespace-only question should return False."""
            result = RoutingPolicy.should_use_web_search("   ")
            assert result is False

    class TestCanRetry:
        """Tests for can_retry method."""

        def test_returns_true_when_retry_count_is_zero(self) -> None:
            """retry_count=0 should return True."""
            result = RoutingPolicy.can_retry(0)
            assert result is True

        def test_returns_true_when_retry_count_is_one(self) -> None:
            """retry_count=1 should return True."""
            result = RoutingPolicy.can_retry(1)
            assert result is True

        def test_returns_true_when_retry_count_is_two(self) -> None:
            """retry_count=2 should return True."""
            result = RoutingPolicy.can_retry(2)
            assert result is True

        def test_returns_false_when_retry_count_equals_max(self) -> None:
            """retry_count=MAX_RETRY_COUNT should return False."""
            result = RoutingPolicy.can_retry(RoutingPolicy.MAX_RETRY_COUNT)
            assert result is False

        def test_returns_false_when_retry_count_exceeds_max(self) -> None:
            """retry_count > MAX_RETRY_COUNT should return False."""
            result = RoutingPolicy.can_retry(RoutingPolicy.MAX_RETRY_COUNT + 1)
            assert result is False

    class TestShouldEnd:
        """Tests for should_end method."""

        def test_returns_true_when_relevant_and_not_hallucinated(self) -> None:
            """Relevant answer without hallucination should end."""
            result = RoutingPolicy.should_end(
                is_relevant=True, is_hallucinated=False, retry_count=0
            )
            assert result is True

        def test_returns_true_when_max_retry_exceeded(self) -> None:
            """Should end when max retry exceeded regardless of quality."""
            result = RoutingPolicy.should_end(
                is_relevant=False,
                is_hallucinated=True,
                retry_count=RoutingPolicy.MAX_RETRY_COUNT,
            )
            assert result is True

        def test_returns_false_when_not_relevant_and_can_retry(self) -> None:
            """Not relevant with retry available should not end."""
            result = RoutingPolicy.should_end(
                is_relevant=False, is_hallucinated=False, retry_count=0
            )
            assert result is False

        def test_returns_false_when_hallucinated_and_can_retry(self) -> None:
            """Hallucinated with retry available should not end."""
            result = RoutingPolicy.should_end(
                is_relevant=True, is_hallucinated=True, retry_count=0
            )
            assert result is False

        def test_returns_false_when_both_issues_and_can_retry(self) -> None:
            """Both issues with retry available should not end."""
            result = RoutingPolicy.should_end(
                is_relevant=False, is_hallucinated=True, retry_count=1
            )
            assert result is False
