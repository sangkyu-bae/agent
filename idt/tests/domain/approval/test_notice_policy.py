"""승인 대기 런 종료 — 도메인 규칙 단위 테스트.

Design Ref: approval-gate-run-termination §3.1, §3.2, §3.4 (B1–B6, B9).
"""
import json

from src.domain.approval.edit_policy import ApprovalEditPolicy
from src.domain.approval.entity import GateSettings
from src.domain.approval.notice_policy import ApprovalPendingNoticePolicy
from src.domain.approval.policies import ApprovalPolicy

_TOOL = "mcp:6ea2f615-515e-4f65-aabe-388970dbafbe:submit_reply"


def _wrapped(**inner) -> dict:
    return {"arguments": inner}


class TestNoticeRender:
    def test_본문이_있으면_인용_미리보기를_싣는다(self):
        """B1"""
        args = _wrapped(board="customer", reply_content="안녕하세요\n답변입니다")
        text = ApprovalPendingNoticePolicy.render(
            tool_id=_TOOL, tool_args=args, draft="안녕하세요\n답변입니다"
        )
        assert text.startswith("요청하신 작업을 담당자 승인함에 올렸습니다. 아직 실행되지 않았습니다.")
        assert "작업함 › 승인 대기" in text
        assert "> 안녕하세요\n> 답변입니다" in text

    def test_미리보기는_상한에서_자른다(self):
        long = "가" * (ApprovalPendingNoticePolicy.PREVIEW_MAX_CHARS + 50)
        text = ApprovalPendingNoticePolicy.render(
            tool_id=_TOOL, tool_args={"body": long}, draft=long
        )
        assert "가" * ApprovalPendingNoticePolicy.PREVIEW_MAX_CHARS + "…" in text
        assert "가" * (ApprovalPendingNoticePolicy.PREVIEW_MAX_CHARS + 1) not in text

    def test_JSON_폴백_초안은_원문을_싣지_않는다(self):
        """B2 — 채팅에 인자 JSON 을 노출하지 않는다."""
        args = _wrapped(board="customer", board_seq=63116)
        draft = json.dumps(args, ensure_ascii=False, indent=2)
        text = ApprovalPendingNoticePolicy.render(tool_id=_TOOL, tool_args=args, draft=draft)
        assert "(본문은 승인 화면에서 확인하세요)" in text
        assert "board_seq" not in text

    def test_도구_표시명은_마지막_세그먼트(self):
        """B3"""
        text = ApprovalPendingNoticePolicy.render(
            tool_id=_TOOL, tool_args={"body": "x"}, draft="x"
        )
        assert "- 작업: submit_reply" in text
        plain = ApprovalPendingNoticePolicy.render(
            tool_id="email_send", tool_args={"body": "x"}, draft="x"
        )
        assert "- 작업: email_send" in plain

    def test_입력만의_함수다(self):
        kwargs = dict(tool_id=_TOOL, tool_args={"body": "x"}, draft="x")
        assert ApprovalPendingNoticePolicy.render(**kwargs) == ApprovalPendingNoticePolicy.render(**kwargs)


class TestEffectiveGate:
    def test_미적용이고_승인필요_워커가_있으면_도메인_기본_게이트(self):
        """B4 / D-01 — 승인 측 from_config({}) 해석과 같다."""
        gate = ApprovalPolicy.effective_gate(None, has_gated_workers=True)
        assert gate == GateSettings.from_config({}, is_enforced=False)
        assert ApprovalPolicy.should_gate(tool_requires_approval=True, gate=gate)

    def test_명시_off_는_그대로_둔다(self):
        """B5 — 에이전트 소유자의 명시적 결정 존중."""
        off = GateSettings.from_config({"mode": "off"}, is_enforced=False)
        gate = ApprovalPolicy.effective_gate(off, has_gated_workers=True)
        assert gate is off
        assert not ApprovalPolicy.should_gate(tool_requires_approval=True, gate=gate)

    def test_승인필요_워커가_없으면_None(self):
        """B6 — 비게이트 에이전트 불변."""
        assert ApprovalPolicy.effective_gate(None, has_gated_workers=False) is None


class TestExtractDraftWithKey:
    def test_지정_키를_래퍼_안에서_우선_사용한다(self):
        """B9 / D-04"""
        args = _wrapped(board="customer", reply_content="본문", content="다른 값")
        assert ApprovalEditPolicy.extract_draft(args, draft_key="reply_content") == "본문"

    def test_지정_키가_비어있으면_관례_키로_돌아간다(self):
        args = {"reply_content": "  ", "body": "관례 본문"}
        assert ApprovalEditPolicy.extract_draft(args, draft_key="reply_content") == "관례 본문"

    def test_지정_키로_뽑은_초안은_편집_가능하다(self):
        args = _wrapped(board="customer", reply_content="본문")
        draft = ApprovalEditPolicy.extract_draft(args, draft_key="reply_content")
        assert ApprovalEditPolicy.body_key(args, draft) == "reply_content"
