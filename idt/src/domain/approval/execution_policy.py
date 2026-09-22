"""승인된 도구 집행의 도메인 규칙 — 실패 문구와 MCP 인자 준비.

Design Ref: approval-gate-phase2-mcp-executor §3.1, §6.1.

도메인 순수성: langchain·mcp SDK·infrastructure 를 참조하지 않는다.
집행기(infrastructure)는 문구와 인자 규칙을 여기서만 가져다 쓴다 — 접두
문자열이 집행기마다 흩어지면 사람이 실패를 구분할 기준이 무너진다.
"""
from typing import Literal

# D-04: 실패를 세 갈래로만 나눈다. 사람이 다음에 할 일이 갈래마다 다르다.
#   blocked    — 호출 0회. 대상 시스템에 아무것도 가지 않았다.
#   unknown    — 호출했으나 결과를 모른다. 집행됐을 수도 있다.
#   tool_error — 도구가 실패라고 답했다.
ExecutionFailureKind = Literal["blocked", "unknown", "tool_error"]

_TRUNCATED_MARK = "… (절단됨)"


class ExecutionFailurePolicy:
    """집행 실패 문구의 단일 생성 지점 (D-04).

    `error_message` 는 영속되어 승인 화면에 그대로 노출된다. 호출측은 reason
    에 예외 문자열(`str(e)`)을 넣지 않는다 — URL 쿼리의 api_key 가 새어 나갈
    수 있다 (D-11). 예외는 타입명만 쓴다.
    """

    _PREFIX: dict[str, str] = {
        "blocked": "[집행 불가]",
        "unknown": "[집행 여부 불명]",
        "tool_error": "[도구 실패]",
    }
    _HINT: dict[str, str] = {
        "blocked": "대상 시스템에는 아무것도 전달되지 않았습니다.",
        # Plan R-1: 불명 상태의 재승인이 이중 집행의 주 경로다.
        "unknown": "대상 시스템에서 실제 집행 여부를 먼저 확인한 뒤 재승인하세요.",
        "tool_error": "",
    }

    @classmethod
    def render(cls, kind: ExecutionFailureKind, reason: str) -> str:
        hint = cls._HINT[kind]
        body = f"{cls._PREFIX[kind]} {reason}"
        return f"{body} — {hint}" if hint else body


class McpArgumentPolicy:
    """승인된 tool_args → MCP 서버에 보낼 arguments.

    집행기가 인자에 가하는 변형은 여기 있는 둘뿐이다 — 래퍼 해제와 멱등키
    주입. 사람이 승인한 값 자체는 건드리지 않는다 (Design §7).
    """

    IDEMPOTENCY_PARAM = "idempotency_key"
    _WRAPPER_KEY = "arguments"

    @classmethod
    def unwrap(cls, tool_args: dict) -> dict:
        """MCPToolInput 래퍼(`{"arguments": {...}}`) 해제 (D-03).

        모든 MCP 도구의 args_schema 가 이 제네릭 래퍼라, 게이트가 기록한
        tool_args 도 같은 모양이다. 키가 정확히 하나이고 값이 dict 일 때만
        래퍼로 본다 — 실제 파라미터 이름이 arguments 인 도구를 망가뜨리지
        않기 위해서다.
        """
        inner = tool_args.get(cls._WRAPPER_KEY)
        if len(tool_args) == 1 and isinstance(inner, dict):
            return dict(inner)
        return dict(tool_args)

    @classmethod
    def with_idempotency_key(
        cls, arguments: dict, input_schema: dict, key: str | None
    ) -> dict:
        """도구 스키마가 멱등키 파라미터를 선언했을 때만 주입한다 (D-05).

        스키마에 없는 인자를 넣으면 서버 검증에서 떨어질 수 있다. 이미 값이
        있으면 덮어쓰지 않는다.
        """
        result = dict(arguments)
        properties = (input_schema or {}).get("properties") or {}
        if not key or cls.IDEMPOTENCY_PARAM not in properties:
            return result
        result.setdefault(cls.IDEMPOTENCY_PARAM, key)
        return result

    @staticmethod
    def truncate(text: str, max_chars: int) -> str:
        """재개 주입·error_message 용 출력 상한."""
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + _TRUNCATED_MARK
