"""OpenerPolicy 단위 테스트 — agent-opener Design §3.1.

domain 테스트는 mock 금지(docs/rules/testing.md). 순수 함수만 검증한다.
"""
import pytest

from src.domain.agent_opener.policies import OpenerPolicy


class TestNormalize:
    def test_strips_and_preserves_order(self):
        assert OpenerPolicy.normalize(["  b ", "a"]) == ["b", "a"]

    def test_empty_list_is_allowed(self):
        assert OpenerPolicy.normalize([]) == []

    def test_blank_item_rejected(self):
        with pytest.raises(ValueError, match="비어 있습니다"):
            OpenerPolicy.normalize(["a", "   "])

    def test_duplicate_after_strip_rejected(self):
        with pytest.raises(ValueError, match="중복"):
            OpenerPolicy.normalize([" a ", "a"])

    def test_too_long_rejected(self):
        with pytest.raises(ValueError, match="200자"):
            OpenerPolicy.normalize(["x" * (OpenerPolicy.MAX_LENGTH + 1)])

    def test_exact_max_length_allowed(self):
        text = "x" * OpenerPolicy.MAX_LENGTH
        assert OpenerPolicy.normalize([text]) == [text]

    def test_too_many_rejected(self):
        items = [f"q{i}" for i in range(OpenerPolicy.MAX_COUNT + 1)]
        with pytest.raises(ValueError, match="12개"):
            OpenerPolicy.normalize(items)

    def test_exact_max_count_allowed(self):
        items = [f"q{i}" for i in range(OpenerPolicy.MAX_COUNT)]
        assert OpenerPolicy.normalize(items) == items


class TestErrorMessageRouterSafety:
    """Design §6.3: 라우터 ValueError 매퍼가 메시지 문자열로 409/404를 만든다.

    정책 메시지에 그 트리거 단어가 들어가면 422 대신 409/404가 나간다.
    """

    FORBIDDEN = ("최대", "이미", "찾을 수 없")

    @pytest.mark.parametrize(
        "items",
        [
            ["a", " "],
            ["a", "a"],
            ["x" * 201],
            [f"q{i}" for i in range(13)],
            # Check G1: 사용자 텍스트가 트리거 단어를 품고 있어도 메시지에 새지 않는다
            ["최대 한도 알려줘", "최대 한도 알려줘"],
            ["찾을 수 없는 자료", " 찾을 수 없는 자료 "],
            ["이미 부착된 건", "이미 부착된 건"],
            ["최대", " "],
        ],
    )
    def test_messages_avoid_router_trigger_words(self, items):
        with pytest.raises(ValueError) as exc:
            OpenerPolicy.normalize(items)
        msg = str(exc.value)
        for word in self.FORBIDDEN:
            assert word not in msg, f"'{word}' in policy message: {msg}"
