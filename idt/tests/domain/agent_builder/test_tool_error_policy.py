"""ToolErrorPolicy — react 워커 트레이스의 도구 오류 결정적 감지 (wiki-guided-routing D4).

외부 의존 0. LangChain 메시지 타입을 import하지 않고 duck typing(type/status/content)만
쓰므로 domain 레이어 규칙을 지킨다. 여기서는 SimpleNamespace로 흉내 낸다.
"""
from types import SimpleNamespace

from src.domain.agent_builder.policies import ToolErrorPolicy


def _tool(content: str, status: str | None = None):
    ns = SimpleNamespace(type="tool", content=content)
    if status is not None:
        ns.status = status
    return ns


def _ai(content: str = "답변"):
    return SimpleNamespace(type="ai", content=content)


class TestSummarize:
    def test_error_status_detected(self):
        msgs = [_ai(""), _tool("boom", status="error"), _ai("실패했습니다")]
        assert ToolErrorPolicy.summarize(msgs) == "boom"

    def test_mcp_error_prefix_detected(self):
        msgs = [_tool(
            "Error executing tool scrape_url: Connection error fetching "
            "https://fpb.fss.or.kr/x: [Errno -2] Name or service not known"
        )]
        out = ToolErrorPolicy.summarize(msgs)
        assert out.startswith("Error executing tool scrape_url")

    def test_success_tool_message_is_not_error(self):
        msgs = [_tool('{"session_id": "abc", "status_code": 200}', status="success")]
        assert ToolErrorPolicy.summarize(msgs) == ""

    def test_non_tool_messages_ignored_even_if_error_like(self):
        msgs = [_ai("Error executing tool 처럼 보이는 LLM 문장")]
        assert ToolErrorPolicy.summarize(msgs) == ""

    def test_first_error_wins(self):
        msgs = [_tool("첫 오류", status="error"), _tool("둘째 오류", status="error")]
        assert ToolErrorPolicy.summarize(msgs) == "첫 오류"

    def test_truncated_to_max_chars_first_line_only(self):
        long = "Error executing tool x: " + "가" * 500 + "\n  Traceback (most recent call last)"
        out = ToolErrorPolicy.summarize([_tool(long)])
        assert len(out) <= ToolErrorPolicy.MAX_SUMMARY_CHARS
        assert "Traceback" not in out

    def test_objects_without_attributes_are_skipped(self):
        msgs = [object(), {"role": "tool", "content": "Error executing tool y"}, None]
        assert ToolErrorPolicy.summarize(msgs) == ""

    def test_empty_list(self):
        assert ToolErrorPolicy.summarize([]) == ""

    def test_non_string_content_is_stringified(self):
        msgs = [_tool(["Error executing tool z: bad"], status="error")]
        assert "Error executing tool z" in ToolErrorPolicy.summarize(msgs)
