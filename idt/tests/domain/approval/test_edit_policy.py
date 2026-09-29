"""담당자 수정 후 승인 — 도메인 규칙 단위 테스트.

Design Ref: approval-edit-before-approve §3.2, §3.3 (D-01, D-02, D-03).
도메인 순수 규칙이라 mock 이 필요 없다.
"""
import json

import pytest

from src.domain.approval.edit_policy import ApprovalEditError, ApprovalEditPolicy
from src.domain.approval.entity import ApprovalEdit
from src.domain.approval.execution_policy import McpArgumentPolicy
from src.domain.approval.policies import ApprovalOutcomePolicy

MAX = 1000


def _wrapped(inner: dict) -> dict:
    return {"arguments": inner}


class TestBodyKey:
    def test_action_경로_사용자_지정_키를_draft_값으로_찾는다(self):
        """B1 — draft_arg_key 가 관례 키가 아니어도(`message`) 판정된다."""
        args = {"to": "a@x.com", "message": "안녕하세요"}
        assert ApprovalEditPolicy.body_key(args, "안녕하세요") == "message"

    def test_react_경로_래퍼_안의_본문_키를_찾는다(self):
        """B2 — MCPToolInput 래퍼를 벗겨서 본다."""
        args = _wrapped({"to": "a@x.com", "body": "본문"})
        assert ApprovalEditPolicy.body_key(args, "본문") == "body"

    def test_json_폴백_초안이면_None(self):
        """B3 — 인자 전체 JSON 이 초안이면 일치 키가 없다."""
        args = {"to": "a@x.com", "count": 3}
        draft = json.dumps(args, ensure_ascii=False, indent=2)
        assert ApprovalEditPolicy.body_key(args, draft) is None

    def test_같은_값이_여러_키면_관례_키가_우선한다(self):
        args = {"subject": "같음", "body": "같음"}
        assert ApprovalEditPolicy.body_key(args, "같음") == "body"

    def test_공백_draft_는_None(self):
        assert ApprovalEditPolicy.body_key({"body": "  "}, "  ") is None


class TestEditableKeys:
    def test_문자열_키만_멱등키는_제외한다(self):
        """B4"""
        args = {
            "to": "a@x.com", "body": "본문", "priority": 1,
            "cc": ["b@x.com"], McpArgumentPolicy.IDEMPOTENCY_PARAM: "k",
        }
        assert ApprovalEditPolicy.editable_keys(args, "본문") == ["to", "body"]

    def test_본문_키가_없으면_빈_목록(self):
        assert ApprovalEditPolicy.editable_keys({"to": "a"}, "{}") == []

    def test_래퍼_건은_안쪽_키를_돌려준다(self):
        args = _wrapped({"to": "a", "body": "본문"})
        assert ApprovalEditPolicy.editable_keys(args, "본문") == ["to", "body"]


class TestApply:
    def test_평탄_인자_수정본을_병합한다(self):
        args = {"to": "a@x.com", "body": "원본", "priority": 1}
        edit = ApprovalEditPolicy.apply(
            args, "원본", {"body": "수정본"}, max_chars=MAX
        )
        assert edit == ApprovalEdit(
            tool_args={"to": "a@x.com", "body": "수정본", "priority": 1},
            draft="수정본",
            changed_keys=("body",),
        )

    def test_래퍼_건은_래퍼_모양을_유지한다(self):
        """B5 — 집행기 unwrap 계약이 깨지지 않게 재포장한다."""
        args = _wrapped({"to": "a", "body": "원본"})
        edit = ApprovalEditPolicy.apply(
            args, "원본", {"to": "b", "body": "수정"}, max_chars=MAX
        )
        assert edit.tool_args == _wrapped({"to": "b", "body": "수정"})
        assert edit.draft == "수정"
        assert edit.changed_keys == ("to", "body")

    def test_본문_외_필드만_바꾸면_draft_는_그대로(self):
        edit = ApprovalEditPolicy.apply(
            {"to": "a", "body": "본문"}, "본문", {"to": "b"}, max_chars=MAX
        )
        assert edit.draft == "본문"
        assert edit.changed_keys == ("to",)

    def test_원본을_변형하지_않는다(self):
        inner = {"to": "a", "body": "원본"}
        args = _wrapped(inner)
        ApprovalEditPolicy.apply(args, "원본", {"body": "수정"}, max_chars=MAX)
        assert args == _wrapped({"to": "a", "body": "원본"})

    @pytest.mark.parametrize("edits", [None, {}, {"body": "원본", "to": "a"}])
    def test_변경이_없으면_None(self, edits):
        """B6 — 일반 승인과 동일하게 취급한다."""
        assert ApprovalEditPolicy.apply(
            {"to": "a", "body": "원본"}, "원본", edits, max_chars=MAX
        ) is None

    def test_변경_없음은_편집_불가_건에서도_None(self):
        """바디 없는 기존 호출이 편집 불가 건에서 실패하면 안 된다."""
        assert ApprovalEditPolicy.apply({"n": 1}, "{}", {}, max_chars=MAX) is None

    @pytest.mark.parametrize(
        "edits",
        [
            {"unknown": "x"},  # 키 추가
            {"priority": "2"},  # 비문자열 원본 키
            {"body": 3},  # 비문자열 값
            {"body": "   "},  # 본문 공백
            {"body": "x" * (MAX + 1)},  # 길이 초과
            {McpArgumentPolicy.IDEMPOTENCY_PARAM: "other"},  # 멱등키
        ],
    )
    def test_검증_실패는_invalid(self, edits):
        """B7"""
        args = {
            "to": "a", "body": "원본", "priority": 1,
            McpArgumentPolicy.IDEMPOTENCY_PARAM: "k",
        }
        with pytest.raises(ApprovalEditError) as exc:
            ApprovalEditPolicy.apply(args, "원본", edits, max_chars=MAX)
        assert exc.value.reason == "invalid"

    def test_본문_키가_없으면_not_editable(self):
        """B8"""
        args = {"to": "a", "n": 1}
        draft = json.dumps(args)
        with pytest.raises(ApprovalEditError) as exc:
            ApprovalEditPolicy.apply(args, draft, {"to": "b"}, max_chars=MAX)
        assert exc.value.reason == "not_editable"


class TestExtractDraft:
    def test_평탄_관례_키(self):
        assert ApprovalEditPolicy.extract_draft({"to": "a", "body": "본문"}) == "본문"

    def test_래퍼_안의_관례_키를_찾는다(self):
        """B9 / D-02 — react 경로 MCP 초안이 JSON 으로 저장되던 문제."""
        args = _wrapped({"to": "a", "content": "본문"})
        assert ApprovalEditPolicy.extract_draft(args) == "본문"

    def test_관례_키_순서를_따른다(self):
        args = {"body": "b", "draft": "d"}
        assert ApprovalEditPolicy.extract_draft(args) == "d"

    def test_관례_키가_없으면_원본_전체_JSON(self):
        args = _wrapped({"to": "a"})
        assert ApprovalEditPolicy.extract_draft(args) == json.dumps(
            args, ensure_ascii=False, indent=2, default=str
        )

    def test_display_args_는_래퍼를_벗긴다(self):
        assert ApprovalEditPolicy.display_args(_wrapped({"a": "1"})) == {"a": "1"}


class TestMcpArgumentWrap:
    def test_is_wrapped(self):
        assert McpArgumentPolicy.is_wrapped(_wrapped({"a": 1}))
        assert not McpArgumentPolicy.is_wrapped({"arguments": "x"})
        assert not McpArgumentPolicy.is_wrapped({"arguments": {}, "b": 1})

    def test_rewrap_은_원래_모양으로_되돌린다(self):
        assert McpArgumentPolicy.rewrap(_wrapped({"a": 1}), {"a": 2}) == _wrapped({"a": 2})
        assert McpArgumentPolicy.rewrap({"a": 1}, {"a": 2}) == {"a": 2}


class TestOutcomeCompose:
    def test_무수정이면_output_그대로(self):
        """B10 — 기존 재개 입력과 바이트 동일."""
        assert ApprovalOutcomePolicy.compose("ok", edited=False, draft="x") == "ok"

    def test_수정건은_안내와_최종_본문을_앞에_붙인다(self):
        """B11"""
        long_draft = "가" * (ApprovalOutcomePolicy.DRAFT_MAX_CHARS + 10)
        out = ApprovalOutcomePolicy.compose("sent", edited=True, draft=long_draft)
        assert out.startswith("[담당자가 초안을 수정해 집행했습니다")
        assert "가" * ApprovalOutcomePolicy.DRAFT_MAX_CHARS in out
        assert "가" * (ApprovalOutcomePolicy.DRAFT_MAX_CHARS + 1) not in out
        assert out.endswith("도구 결과:\nsent")
