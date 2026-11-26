"""보조 LLM 재구조화 어댑터 (application.ports.StructuredExtractor 구현).

Design Ref: stock-analysis-agents DD8
— 판단 에이전트 답변의 JSON 파싱이 실패했을 때 1회만 쓴다.
관리자 보조 모델(UtilityLLMProvider, PII 가드 포함)과
`StructuredCaller`(json_schema → json_mode → text 폴백).
보조 모델이 없거나 실패하면 None — 호출자가 skip/hold 로 내린다.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from src.domain.logging.interfaces.logger_interface import LoggerInterface

T = TypeVar("T", bound=BaseModel)

_MAX_TEXT = 20_000
_SYSTEM = (
    "다음 글에서 요청한 스키마의 값을 그대로 옮겨 적는다. "
    "글에 없는 값은 지어내지 않고 비운다."
)


class PlatformStructuredExtractor:
    def __init__(
        self,
        *,
        provider: Any,
        caller_factory: Callable[[Any], Any],
        logger: LoggerInterface,
    ) -> None:
        self._provider = provider
        self._caller_factory = caller_factory
        self._logger = logger

    async def extract(self, *, text: str, schema: type[T], request_id: str) -> T | None:
        llm = await self._provider.get(temperature=0.0)
        if llm is None:
            self._logger.warning(
                "market_analysis structured extract skipped — no utility llm",
                request_id=request_id,
            )
            return None
        messages = [
            SystemMessage(content=_SYSTEM),
            HumanMessage(content=text[:_MAX_TEXT]),
        ]
        try:
            model, _mode, _usage = await self._caller_factory(llm).call(
                messages, schema
            )
        except Exception as e:  # noqa: BLE001 — 실패는 None (호출자가 보수적으로 처리)
            self._logger.warning(
                "market_analysis structured extract failed",
                exception=e,
                request_id=request_id,
                schema=schema.__name__,
            )
            return None
        return model if isinstance(model, schema) else None
