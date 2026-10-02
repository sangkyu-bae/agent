"""승인 대기로 끝난 런의 사용자 답변 — 결정적 템플릿.

Design Ref: approval-gate-run-termination §3.1 (Plan FR-03/FR-04).

승인 대기 런의 답변을 워커·LLM 텍스트로 만들지 않는 이유(실측 2026-09-29):
게이트가 막은 뒤 워커 LLM 이 도구 응답 모양을 흉내 낸 "성공 JSON" 을 출력했고,
그 문자열이 그대로 채팅에 저장돼 실제로는 실행되지 않은 등록이 "완료" 처럼
보였다. 사용자가 보는 상태 = 실제 상태를 보장하려면 입력(approval_pending)만의
함수여야 한다.
"""
from src.domain.approval.edit_policy import ApprovalEditPolicy

_NO_PREVIEW = "(본문은 승인 화면에서 확인하세요)"


class ApprovalPendingNoticePolicy:
    PREVIEW_MAX_CHARS: int = 300

    @classmethod
    def render(cls, *, tool_id: str, tool_args: dict, draft: str) -> str:
        return (
            "요청하신 작업을 담당자 승인함에 올렸습니다. 아직 실행되지 않았습니다.\n"
            "작업함 › 승인 대기에서 내용을 확인·수정한 뒤 승인하면 실제로 실행됩니다.\n\n"
            f"- 작업: {cls._tool_label(tool_id)}\n"
            f"- 초안 미리보기:\n{cls._preview(tool_args, draft)}"
        )

    @staticmethod
    def _tool_label(tool_id: str) -> str:
        """`mcp:<server>:<tool>` → `<tool>`. 접두 없는 내부 도구는 그대로."""
        return (tool_id or "").rsplit(":", 1)[-1]

    @classmethod
    def _preview(cls, tool_args: dict, draft: str) -> str:
        """본문으로 판정되는 초안만 싣는다 — JSON 폴백 초안은 채팅에 노출하지 않는다."""
        if ApprovalEditPolicy.body_key(tool_args or {}, draft) is None:
            return _NO_PREVIEW
        body = draft[: cls.PREVIEW_MAX_CHARS]
        if len(draft) > cls.PREVIEW_MAX_CHARS:
            body += "…"
        return "\n".join(f"> {line}" for line in body.split("\n"))
