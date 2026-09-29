"""담당자 수정 후 승인의 도메인 규칙 — 본문 키 판정·편집 검증·병합.

Design Ref: approval-edit-before-approve §3.2 (D-01, D-02, D-03).

집행의 진실은 `draft` 가 아니라 `tool_args` 다. 그래서 수정은 언제나
`tool_args` 에 가해지고, `draft` 는 본문 키의 값에서 다시 얻는다.

본문 키를 "관례 키 존재" 가 아니라 **"값이 저장된 draft 와 같은 문자열 키"**
로 판정하는 이유(D-01): action 워커는 사용자가 지정한 `draft_arg_key`
(관례 키가 아닐 수 있다)로 본문을 넣고, react 경로 MCP 도구는 인자가
`{"arguments": {...}}` 래퍼에 싸여 있다. 값 일치 판정은 두 경로를 새 컬럼
없이 모두 덮는다.

도메인 순수성: langchain·DB·env 를 모른다.
"""
import json

from src.domain.approval.entity import ApprovalEdit
from src.domain.approval.execution_policy import McpArgumentPolicy


class ApprovalEditError(ValueError):
    """편집 거부. reason 으로 application 오류를 고른다.

    - not_editable: 본문 키를 판정할 수 없는 건 (승인/거절만 가능)
    - invalid: 불허 키·비문자열·본문 공백·길이 초과
    """

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class ApprovalEditPolicy:
    # 인자에 사람이 검토할 본문이 담기는 관례 키 — 순서가 우선순위다.
    # ActionArgumentPolicy.DRAFT_KEY_CANDIDATES 가 이 값을 참조한다.
    DRAFT_KEYS: tuple[str, ...] = ("draft", "body", "content", "본문")
    # 주입이 없을 때의 필드 길이 상한. 운영값은 settings.approval_edit_max_field_chars.
    DEFAULT_MAX_FIELD_CHARS: int = 20000

    @classmethod
    def extract_draft(cls, tool_args: dict) -> str:
        """게이트 적재 시 사람이 검토할 본문 (D-02: 래퍼를 먼저 벗긴다).

        관례 키가 없으면 원본 인자 전체를 읽기 좋게 직렬화한다 — 승인 화면에서
        '무엇을 승인하는지' 를 볼 수 없으면 게이트가 형식만 남는다.
        """
        inner = McpArgumentPolicy.unwrap(tool_args)
        for key in cls.DRAFT_KEYS:
            value = inner.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return json.dumps(tool_args, ensure_ascii=False, indent=2, default=str)

    @staticmethod
    def display_args(tool_args: dict) -> dict:
        """화면 표시·편집 기준이 되는 인자 (래퍼 해제)."""
        return McpArgumentPolicy.unwrap(tool_args)

    @classmethod
    def body_key(cls, tool_args: dict, draft: str) -> str | None:
        """D-01: 값이 draft 와 같은 문자열 키. 관례 키가 우선, 그다음 인자 순서."""
        if not (draft or "").strip():
            return None
        inner = McpArgumentPolicy.unwrap(tool_args)
        ordered = [k for k in cls.DRAFT_KEYS if k in inner]
        ordered += [k for k in inner if k not in cls.DRAFT_KEYS]
        for key in ordered:
            if inner[key] == draft and isinstance(inner[key], str):
                return key
        return None

    @classmethod
    def editable_keys(cls, tool_args: dict, draft: str) -> list[str]:
        """본문 키가 있을 때만 문자열 값 키 전체. 멱등키는 편집 대상이 아니다."""
        if cls.body_key(tool_args, draft) is None:
            return []
        inner = McpArgumentPolicy.unwrap(tool_args)
        return [
            k for k, v in inner.items()
            if isinstance(v, str) and k != McpArgumentPolicy.IDEMPOTENCY_PARAM
        ]

    @classmethod
    def apply(
        cls, tool_args: dict, draft: str, edits: dict | None, *, max_chars: int
    ) -> ApprovalEdit | None:
        """검증 → 병합 → 재포장. 변경이 없으면 None (일반 승인과 동일)."""
        if not edits:
            return None
        key = cls.body_key(tool_args, draft)
        if key is None:
            raise ApprovalEditError(
                "not_editable", "본문 필드를 찾을 수 없어 수정할 수 없습니다"
            )
        cls._validate(edits, cls.editable_keys(tool_args, draft), max_chars)
        inner = McpArgumentPolicy.unwrap(tool_args)
        changed = {k: v for k, v in edits.items() if inner[k] != v}
        if not changed:
            return None
        merged = {**inner, **changed}
        if not merged[key].strip():
            raise ApprovalEditError("invalid", f"본문({key})은 비울 수 없습니다")
        return ApprovalEdit(
            tool_args=McpArgumentPolicy.rewrap(tool_args, merged),
            draft=merged[key],
            changed_keys=tuple(changed),
        )

    @staticmethod
    def _validate(edits: dict, allowed: list[str], max_chars: int) -> None:
        """키 추가·타입 변경·길이 초과 차단. 값은 메시지에 싣지 않는다."""
        for key, value in edits.items():
            if key not in allowed:
                raise ApprovalEditError("invalid", f"수정할 수 없는 필드입니다: {key}")
            if not isinstance(value, str):
                raise ApprovalEditError("invalid", f"문자열만 입력할 수 있습니다: {key}")
            if len(value) > max_chars:
                raise ApprovalEditError(
                    "invalid", f"{key} 길이가 상한({max_chars}자)을 넘었습니다"
                )
