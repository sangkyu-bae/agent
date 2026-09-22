"""집행 실패 문구·MCP 인자 규칙 단위 테스트.

Design Ref: approval-gate-phase2-mcp-executor §3.1, §6.1 (D-03, D-04, D-05).
도메인 순수 규칙이라 mock 이 필요 없다.
"""
import pytest

from src.domain.approval.execution_policy import (
    ExecutionFailurePolicy,
    McpArgumentPolicy,
)


class TestExecutionFailurePolicyRender:
    @pytest.mark.parametrize(
        ("kind", "prefix"),
        [
            ("blocked", "[집행 불가]"),
            ("unknown", "[집행 여부 불명]"),
            ("tool_error", "[도구 실패]"),
        ],
    )
    def test_kind별_접두로_시작한다(self, kind, prefix):
        message = ExecutionFailurePolicy.render(kind, "사유")
        assert message.startswith(prefix)
        assert "사유" in message

    def test_불명은_확인_후_재승인_안내를_담는다(self):
        """Plan SC-7 — 사람이 대상 시스템을 먼저 확인하게 유도한다 (R-1)."""
        message = ExecutionFailurePolicy.render("unknown", "호출 중 오류")
        assert "확인" in message
        assert "재승인" in message

    def test_불가는_미전달을_명시한다(self):
        message = ExecutionFailurePolicy.render("blocked", "서버 비활성")
        assert "전달되지 않았습니다" in message

    def test_도구_실패는_안내_문구를_덧붙이지_않는다(self):
        message = ExecutionFailurePolicy.render("tool_error", "quota exceeded")
        assert message == "[도구 실패] quota exceeded"


class TestMcpArgumentPolicyUnwrap:
    def test_래퍼를_해제한다(self):
        assert McpArgumentPolicy.unwrap({"arguments": {"to": "a"}}) == {"to": "a"}

    def test_래퍼가_아니면_그대로_둔다(self):
        assert McpArgumentPolicy.unwrap({"to": "a"}) == {"to": "a"}

    def test_arguments가_dict가_아니면_그대로_둔다(self):
        args = {"arguments": "raw"}
        assert McpArgumentPolicy.unwrap(args) == args

    def test_키가_둘_이상이면_그대로_둔다(self):
        """도구의 실제 파라미터 이름이 arguments 일 가능성을 배제하지 않는다."""
        args = {"arguments": {"a": 1}, "to": "b"}
        assert McpArgumentPolicy.unwrap(args) == args

    def test_빈_인자는_빈_dict(self):
        assert McpArgumentPolicy.unwrap({}) == {}


class TestMcpArgumentPolicyIdempotencyKey:
    _SCHEMA = {"type": "object", "properties": {"to": {}, "idempotency_key": {}}}

    def test_스키마에_있으면_주입한다(self):
        result = McpArgumentPolicy.with_idempotency_key(
            {"to": "a"}, self._SCHEMA, "key-1"
        )
        assert result == {"to": "a", "idempotency_key": "key-1"}

    @pytest.mark.parametrize(
        "schema",
        [{}, {"properties": {"to": {}}}, {"properties": None}],
    )
    def test_스키마에_없으면_주입하지_않는다(self, schema):
        result = McpArgumentPolicy.with_idempotency_key({"to": "a"}, schema, "key-1")
        assert result == {"to": "a"}

    def test_key가_없으면_주입하지_않는다(self):
        result = McpArgumentPolicy.with_idempotency_key({"to": "a"}, self._SCHEMA, None)
        assert result == {"to": "a"}

    def test_이미_있는_값은_덮어쓰지_않는다(self):
        """사람이 승인한 인자 값은 그대로 간다 (Design §7)."""
        result = McpArgumentPolicy.with_idempotency_key(
            {"idempotency_key": "approved"}, self._SCHEMA, "key-1"
        )
        assert result["idempotency_key"] == "approved"

    def test_입력_dict를_변경하지_않는다(self):
        arguments = {"to": "a"}
        McpArgumentPolicy.with_idempotency_key(arguments, self._SCHEMA, "key-1")
        assert arguments == {"to": "a"}


class TestMcpArgumentPolicyTruncate:
    def test_상한_이하는_그대로(self):
        assert McpArgumentPolicy.truncate("abc", 10) == "abc"

    def test_상한_초과는_절단하고_표식을_붙인다(self):
        result = McpArgumentPolicy.truncate("a" * 50, 10)
        assert result.startswith("a" * 10)
        assert len(result) < 50
        assert "절단" in result
