"""PiiMaskingMiddleware — create_agent 경로의 외부 LLM 경계.

Design Ref: pii-masking-integration §4.3 (FR-01, FR-02, FR-03)
- awrap_model_call: 요청(system 포함)만 마스킹해 호출하고 응답을 원복한다.
  `request.override`는 그래프 상태를 바꾸지 않으므로 상태·도구·승인 초안에는
  원본이 남는다 (2026-11-02 스파이크로 확인).
- awrap_tool_call: 원복 후에도 인자에 placeholder가 남으면 LLM이 지어낸 값이다.
  도구를 실행하지 않고 교정 지시를 돌려준다.
- 체인 맨 앞에 둔다. 재시도·폴백이 안쪽에서 돌아 fallback 모델도 마스킹된 요청을
  받고, 승인 게이트는 원복된 인자를 본다.

langchain v1 클래스 참조는 이 모듈과 MiddlewareBuilder에 둔다 (builtin-middleware D8,
gate_middleware.py 선례). 워커마다 새 인스턴스, scope는 런 단위로 공유한다.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ExtendedModelResponse, ModelResponse
from langchain_core.messages import AIMessage, ToolMessage

from src.application.pii_masking.message_masker import PiiMessageMasker
from src.domain.pii_masking.policies import PII_ORPHAN_TOOL_ARG_NOTICE
from src.domain.pii_masking.schemas import PiiRunScope

# 안내 문구는 MCP 어댑터·집행기와 같은 도메인 상수를 쓴다 (단일 출처).
ORPHAN_TOOL_ARG_NOTICE = PII_ORPHAN_TOOL_ARG_NOTICE


class PiiMaskingMiddleware(AgentMiddleware):
    def __init__(self, masker: PiiMessageMasker, scope: PiiRunScope) -> None:
        super().__init__()
        self._masker = masker
        self._scope = scope

    @property
    def scope(self) -> PiiRunScope:
        return self._scope

    def wrap_model_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        return self._restore(handler(self._mask(request)))

    async def awrap_model_call(
        self, request: Any, handler: Callable[[Any], Any]
    ) -> Any:
        return self._restore(await handler(self._mask(request)))

    def wrap_tool_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        blocked = self._block_orphan(request)
        return blocked if blocked is not None else handler(request)

    async def awrap_tool_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        blocked = self._block_orphan(request)
        return blocked if blocked is not None else await handler(request)

    def _mask(self, request: Any) -> Any:
        messages, system = self._masker.mask_request(
            list(request.messages), self._scope, system=request.system_message
        )
        return request.override(messages=messages, system_message=system)

    def _restore(self, result: Any) -> Any:
        """handler 반환 3형태(AIMessage, ModelResponse, ExtendedModelResponse) 원복."""
        if isinstance(result, ExtendedModelResponse):
            return ExtendedModelResponse(
                model_response=self._restore_response(result.model_response),
                command=result.command,
            )
        if isinstance(result, ModelResponse):
            return self._restore_response(result)
        if isinstance(result, AIMessage):
            return self._masker.restore_message(result, self._scope)
        return result

    def _restore_response(self, response: ModelResponse) -> ModelResponse:
        return ModelResponse(
            result=[
                self._masker.restore_message(m, self._scope) for m in response.result
            ],
            structured_response=self._masker.restore_output(
                response.structured_response, self._scope
            ),
        )

    def _block_orphan(self, request: Any) -> ToolMessage | None:
        call = getattr(request, "tool_call", None) or {}
        if not self._masker.has_orphan(call.get("args") or {}, self._scope):
            return None
        # tool_call_id를 그대로 돌려야 짝이 맞는다 (gate_middleware와 같은 이유).
        return ToolMessage(
            content=ORPHAN_TOOL_ARG_NOTICE,
            tool_call_id=call.get("id") or "",
            status="error",
        )
