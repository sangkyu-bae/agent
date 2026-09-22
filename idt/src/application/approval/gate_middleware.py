"""ApprovalGateMiddleware — 부작용 도구 호출 차단 + 마커 생성.

Design Ref: §2.1 ①, §9.3.

**순수 미들웨어**다. DB·그래프 상태·네트워크를 만지지 않고, 실도구 handler 를
호출하지 않으며 마커 ToolMessage 만 돌려준다. 적재(approval_request 생성)는
워커 래퍼가 신호를 SupervisorState 로 올린 뒤 RunAgentUseCase 가 수행한다.

이 순수성이 Option C 의 이점이다 — 미들웨어가 repo 를 물지 않으므로
MiddlewareBuilder 의 정적 구조를 깨지 않고, DB 없이 단위 테스트가 된다.

langchain v1 클래스 참조는 본 모듈과 MiddlewareBuilder 에만 존재한다
(builtin-middleware D8 격리 계약).
"""
import json
from typing import Any, Callable

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage

from src.domain.approval.policies import ApprovalSignalPolicy

# 인자에 사람이 검토할 본문이 담기는 관례 키. 없으면 인자 전체를 초안으로 쓴다.
_DRAFT_KEYS = ("draft", "body", "content", "본문")


class ApprovalGateMiddleware(AgentMiddleware):
    """게이트 대상 도구의 실행을 차단하고 승인 요청 신호를 남긴다.

    Args:
        tool_id: 저장 형식 tool_id. `request.tool_call["name"]` 을 쓰지 않는
            이유는 MCP 도구명이 UUID 접두 합성명이라 카탈로그 tool_id 와
            다르기 때문이다 (위키 mcp-runtime-tool-shape).
        worker_id: 재개 시 결과를 주입할 워커. 래퍼가 알지만 마커에도 담아
            신호 경로가 끊겨도 추적이 가능하게 한다.
    """

    def __init__(self, tool_id: str, worker_id: str) -> None:
        super().__init__()
        self._tool_id = tool_id
        self._worker_id = worker_id

    def wrap_tool_call(
        self, request: Any, handler: Callable[[Any], Any]
    ) -> ToolMessage:
        # handler 를 호출하지 않는다 — 이것이 차단의 전부다.
        return self._block(request)

    async def awrap_tool_call(
        self, request: Any, handler: Callable[[Any], Any]
    ) -> ToolMessage:
        """워커는 ainvoke 로 돌므로 이쪽이 실제 경로다.

        동기와 같은 순수 로직을 부르므로 await 할 것이 없다.
        """
        return self._block(request)

    def _block(self, request: Any) -> ToolMessage:
        call = getattr(request, "tool_call", None) or {}
        args = call.get("args") or {}
        call_id = call.get("id") or ""
        content = ApprovalSignalPolicy.render(
            tool_id=self._tool_id,
            tool_args=args,
            draft=_extract_draft(args),
            tool_call_id=call_id,
        )
        # tool_call_id 를 그대로 되돌려야 짝이 맞는다 — 어긋나면 OpenAI 가
        # 고아 tool 메시지로 400 을 낸다 (worker-toolmessage-leak-fix 와 동류).
        return ToolMessage(content=content, tool_call_id=call_id)


def _extract_draft(args: dict) -> str:
    """사람이 검토할 본문을 뽑는다.

    관례 키가 없으면 인자 전체를 읽기 좋게 직렬화한다 — 승인 화면에서
    '무엇을 승인하는지' 를 볼 수 없으면 게이트가 형식만 남는다.
    """
    for key in _DRAFT_KEYS:
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return json.dumps(args, ensure_ascii=False, indent=2, default=str)


class StatelessGate:
    """ApprovalGateInterface 의 현재 구현체 (Check G9).

    handler 미호출 + 마커 ToolMessage 방식. LangGraph checkpointer 를 도입하면
    interrupt() 기반 InterruptGate 를 만들어 WorkflowCompiler.approval_gate 만
    교체하면 된다 — 이전에는 Protocol 만 있고 구현체가 없어 교체 지점이
    형식에 그쳤다.
    """

    def build_for_worker(self, *, tool_id: str, worker_id: str) -> ApprovalGateMiddleware:
        # 워커마다 새 인스턴스 (builtin-middleware D6 — 상태 공유 금지)
        return ApprovalGateMiddleware(tool_id=tool_id, worker_id=worker_id)
