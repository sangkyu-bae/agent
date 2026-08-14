"""ToolSelectionMiddleware — Design Ref: §4.3 (선택 어댑터).

LangChain의 ``awrap_model_call``에서 ``request.override(tools=...)``로 도구를
좁힌다. 모델 호출 직전에 끼므로 호출부 코드를 전혀 건드리지 않는다.

**현재 미배선이다.** 결선 스타일(함수형 필터 vs 미들웨어)은 module-4에서 고른다.
DB 카탈로그(MiddlewareType enum + middleware_catalog 테이블)에 등록하지 않고
코드에서 직접 인스턴스화해 middleware 리스트에 넣는 방식이라 DDL이 필요 없다
— Design §2.0에서 Option B를 탈락시킨 이유가 이것이다.
"""
from collections.abc import Sequence
from typing import Any

from langchain.agents.middleware import AgentMiddleware

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.tool_selection.interfaces.tool_selector_port import ToolSelectorPort
from src.infrastructure.tool_selection.adapters.langchain_filter import (
    LangChainToolFilter,
    ToolIdResolver,
)


def extract_latest_user_text(messages: Sequence[Any]) -> str:
    """마지막 사람 메시지의 텍스트. 없으면 빈 문자열.

    Plan 결정: 입력 컨텍스트는 **현재 유저 메시지만** — 대화 이력은 넣지 않는다.
    """
    for message in reversed(list(messages or [])):
        if getattr(message, "type", None) != "human":
            continue
        content = getattr(message, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return " ".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict)
            ).strip()
    return ""


class ToolSelectionMiddleware(AgentMiddleware):
    """모델 호출 직전에 도구 목록을 좁히는 미들웨어."""

    def __init__(
        self,
        selector: ToolSelectorPort,
        logger: LoggerInterface,
        resolver: ToolIdResolver | None = None,
        required_ids: Sequence[str] = (),
    ) -> None:
        super().__init__()
        self._filter = LangChainToolFilter(selector, logger, resolver)
        self._logger = logger
        self._required_ids = tuple(required_ids)

    async def awrap_model_call(self, request, handler):
        """도구를 좁힌 request로 다음 핸들러를 호출한다.

        좁히지 못하면 원본 request를 그대로 넘긴다 — 미들웨어가 실행을
        막는 일은 없다.
        """
        tools = list(getattr(request, "tools", None) or [])
        query = extract_latest_user_text(getattr(request, "messages", []))
        if not tools or not query:
            return await handler(request)

        selected = await self._filter.filter(
            tools, query, required_ids=self._required_ids,
        )
        if len(selected) == len(tools):
            return await handler(request)
        return await handler(request.override(tools=selected))
