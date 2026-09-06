"""ToolArgumentPolicy 테스트 - Mock 금지 (순수 도메인 규칙).

Design Ref: worker-context-injection §3.2 / §8.2 L1 #1~7
"""
import pytest


class TestIsPlaceholderUrl:

    @pytest.mark.parametrize("url", [
        "https://www.example.com/financial-market-2026-09-03",
        "http://example.com",
        "https://example.org/a/b?c=d",
        "https://EXAMPLE.NET/path",
        "https://sub.deep.example.edu/x",
        "https://your-domain.com/report",
        "https://test.com",
    ])
    def test_returns_true_for_reserved_hosts(self, url):
        from src.domain.mcp.tool_argument_policy import ToolArgumentPolicy
        assert ToolArgumentPolicy.is_placeholder_url(url) is True

    @pytest.mark.parametrize("url", [
        "https://finance.naver.com/marketindex",
        "https://www.bok.or.kr/portal/main",
        "https://data.go.kr/dataset/1",
    ])
    def test_returns_false_for_real_hosts(self, url):
        from src.domain.mcp.tool_argument_policy import ToolArgumentPolicy
        assert ToolArgumentPolicy.is_placeholder_url(url) is False

    @pytest.mark.parametrize("url", [
        "https://myexample.com/a",
        "https://example.com.evil.co.kr/a",
        "https://notexample.org/a",
    ])
    def test_returns_false_for_partial_host_matches(self, url):
        """부분 문자열 일치는 오탐 — 정확 일치 또는 서브도메인만 차단한다."""
        from src.domain.mcp.tool_argument_policy import ToolArgumentPolicy
        assert ToolArgumentPolicy.is_placeholder_url(url) is False

    @pytest.mark.parametrize("url", [
        "http://localhost:8080/scrape",
        "http://127.0.0.1:9000/x",
    ])
    def test_returns_false_for_localhost(self, url):
        """§3.2 — 사내 로컬 대상 스크래핑 오탐 방지를 위해 의도적으로 제외."""
        from src.domain.mcp.tool_argument_policy import ToolArgumentPolicy
        assert ToolArgumentPolicy.is_placeholder_url(url) is False

    @pytest.mark.parametrize("value", [
        "example.com 관련 뉴스를 찾아줘",
        "2026년 3분기 실적",
        "",
        "   ",
        "not a url at all",
    ])
    def test_returns_false_for_non_url_strings(self, value):
        from src.domain.mcp.tool_argument_policy import ToolArgumentPolicy
        assert ToolArgumentPolicy.is_placeholder_url(value) is False


class TestFindPlaceholder:

    def test_finds_placeholder_in_flat_dict(self):
        from src.domain.mcp.tool_argument_policy import ToolArgumentPolicy
        args = {"url": "https://www.example.com/financial-market-2026-09-03"}
        assert ToolArgumentPolicy.find_placeholder(args) == args["url"]

    def test_finds_placeholder_in_nested_structure(self):
        from src.domain.mcp.tool_argument_policy import ToolArgumentPolicy
        args = {"arguments": {"targets": ["https://example.org/a"]}}
        assert ToolArgumentPolicy.find_placeholder(args) == "https://example.org/a"

    def test_returns_none_for_real_urls(self):
        from src.domain.mcp.tool_argument_policy import ToolArgumentPolicy
        args = {"url": "https://finance.naver.com/x", "depth": 2}
        assert ToolArgumentPolicy.find_placeholder(args) is None

    def test_returns_none_when_placeholder_is_not_a_url_value(self):
        from src.domain.mcp.tool_argument_policy import ToolArgumentPolicy
        args = {"query": "example.com 관련 뉴스"}
        assert ToolArgumentPolicy.find_placeholder(args) is None

    @pytest.mark.parametrize("args", [{}, None])
    def test_returns_none_for_empty_arguments(self, args):
        from src.domain.mcp.tool_argument_policy import ToolArgumentPolicy
        assert ToolArgumentPolicy.find_placeholder(args) is None

    def test_does_not_raise_on_deeply_nested_structure(self):
        """MAX_SCAN_DEPTH 초과분은 조용히 무시 — 예외를 던지지 않는다."""
        from src.domain.mcp.tool_argument_policy import ToolArgumentPolicy
        deep = {"a": {"b": {"c": {"d": {"e": {"f": "https://example.com/x"}}}}}}
        assert ToolArgumentPolicy.find_placeholder(deep) is None

    def test_handles_non_string_scalar_values(self):
        from src.domain.mcp.tool_argument_policy import ToolArgumentPolicy
        args = {"count": 3, "flag": True, "ratio": 1.5, "none": None}
        assert ToolArgumentPolicy.find_placeholder(args) is None

    def test_returns_first_placeholder_when_multiple_exist(self):
        from src.domain.mcp.tool_argument_policy import ToolArgumentPolicy
        args = {"a": "https://example.com/1", "b": "https://example.org/2"}
        assert ToolArgumentPolicy.find_placeholder(args) in (
            "https://example.com/1", "https://example.org/2",
        )


class TestBuildBlockedMessage:

    def test_message_contains_blocked_value_and_guidance(self):
        from src.domain.mcp.tool_argument_policy import ToolArgumentPolicy
        msg = ToolArgumentPolicy.build_blocked_message("https://example.com/x")
        assert "https://example.com/x" in msg
        assert "차단" in msg

    def test_message_instructs_not_to_retry_with_guessed_url(self):
        from src.domain.mcp.tool_argument_policy import ToolArgumentPolicy
        msg = ToolArgumentPolicy.build_blocked_message("https://example.com/x")
        assert "추측" in msg


class TestIsBlockedMessage:
    """GAP-02 — 차단 응답을 상위 레이어가 식별할 수 있어야 run step에 반영된다."""

    def test_recognizes_own_blocked_message(self):
        from src.domain.mcp.tool_argument_policy import ToolArgumentPolicy
        msg = ToolArgumentPolicy.build_blocked_message("https://example.com/x")
        assert ToolArgumentPolicy.is_blocked_message(msg) is True

    @pytest.mark.parametrize("text", [
        "정상 도구 응답입니다",
        "",
        "차단",
    ])
    def test_rejects_other_text(self, text):
        from src.domain.mcp.tool_argument_policy import ToolArgumentPolicy
        assert ToolArgumentPolicy.is_blocked_message(text) is False

    def test_handles_non_string(self):
        from src.domain.mcp.tool_argument_policy import ToolArgumentPolicy
        assert ToolArgumentPolicy.is_blocked_message(None) is False
        assert ToolArgumentPolicy.is_blocked_message(123) is False

    def test_prefix_is_exposed_as_constant(self):
        from src.domain.mcp.tool_argument_policy import ToolArgumentPolicy
        msg = ToolArgumentPolicy.build_blocked_message("https://example.com/x")
        assert msg.startswith(ToolArgumentPolicy.BLOCKED_PREFIX)
