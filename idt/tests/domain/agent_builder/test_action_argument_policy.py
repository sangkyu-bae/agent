"""ActionArgumentPolicy 단위 테스트.

Design Ref: action-category-compose-node §3.1 / D-04
  - resolve_draft_key: 설정 키는 스키마에 있어야 한다. 빈 설정이면 관례 키 탐색.
    둘 다 실패 → ValueError (compile 시 워커 격리 사유, D-09)
  - merge: 본문 키는 초안 원문으로 마지막에 덮어쓴다 — "초안이 이긴다"
  - summarize_keys: 로그·스텝 요약용 키 목록(값 없음, Plan FR-24/25)
"""
import pytest

from src.domain.agent_builder.policies import ActionArgumentPolicy

_SCHEMA_BODY = {"type": "object", "properties": {"to": {}, "subject": {}, "body": {}}}
_SCHEMA_CONTENT = {"type": "object", "properties": {"channel": {}, "content": {}}}
_SCHEMA_KO = {"type": "object", "properties": {"수신자": {}, "본문": {}}}
_SCHEMA_TEXT = {"type": "object", "properties": {"text": {}}}


class TestResolveDraftKey:
    def test_configured_key_present_in_schema(self):
        assert ActionArgumentPolicy.resolve_draft_key("body", _SCHEMA_BODY) == "body"

    def test_configured_key_missing_in_schema_raises(self):
        with pytest.raises(ValueError) as exc:
            ActionArgumentPolicy.resolve_draft_key("body", _SCHEMA_TEXT)
        assert "body" in str(exc.value)

    def test_empty_config_falls_back_to_first_candidate_in_schema(self):
        assert ActionArgumentPolicy.resolve_draft_key("", _SCHEMA_CONTENT) == "content"

    def test_candidate_order_is_draft_body_content_korean(self):
        """gate_middleware._DRAFT_KEYS 와 같은 순서 — 승인 화면 추출과 일치."""
        assert ActionArgumentPolicy.DRAFT_KEY_CANDIDATES == (
            "draft", "body", "content", "본문",
        )
        both = {"properties": {"content": {}, "body": {}}}
        assert ActionArgumentPolicy.resolve_draft_key("", both) == "body"

    def test_korean_candidate(self):
        assert ActionArgumentPolicy.resolve_draft_key("", _SCHEMA_KO) == "본문"

    def test_empty_config_and_no_candidate_raises(self):
        with pytest.raises(ValueError):
            ActionArgumentPolicy.resolve_draft_key("", _SCHEMA_TEXT)

    def test_schema_without_properties_raises(self):
        """스키마를 모르면 키 이름을 추측하게 된다 — 호출하지 않는다 (collect §6.1 #4)."""
        with pytest.raises(ValueError):
            ActionArgumentPolicy.resolve_draft_key("body", {})
        with pytest.raises(ValueError):
            ActionArgumentPolicy.resolve_draft_key("", {})

    def test_whitespace_config_is_treated_as_empty(self):
        assert ActionArgumentPolicy.resolve_draft_key("  ", _SCHEMA_BODY) == "body"


class TestMerge:
    def test_overwrites_llm_body_with_draft(self):
        """D-04: LLM이 본문 키를 채워도 초안이 이긴다."""
        args = {"to": "a@b.c", "body": "LLM이 지어낸 문장"}
        merged = ActionArgumentPolicy.merge(args, "body", "승인된 초안")
        assert merged["body"] == "승인된 초안"
        assert merged["to"] == "a@b.c"

    def test_adds_key_when_absent(self):
        merged = ActionArgumentPolicy.merge({"to": "x"}, "body", "초안")
        assert merged == {"to": "x", "body": "초안"}

    def test_does_not_mutate_input(self):
        args = {"body": "원래"}
        ActionArgumentPolicy.merge(args, "body", "초안")
        assert args == {"body": "원래"}

    def test_none_arguments_treated_as_empty(self):
        assert ActionArgumentPolicy.merge(None, "body", "초안") == {"body": "초안"}


class TestSummarizeKeys:
    def test_returns_sorted_keys_only(self):
        keys = ActionArgumentPolicy.summarize_keys({"to": "x@y", "body": "비밀", "subject": "s"})
        assert keys == ["body", "subject", "to"]

    def test_empty_or_none(self):
        assert ActionArgumentPolicy.summarize_keys({}) == []
        assert ActionArgumentPolicy.summarize_keys(None) == []
