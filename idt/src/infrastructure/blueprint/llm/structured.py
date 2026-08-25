"""StructuredCaller — 워커 LLM(BaseChatModel) 구조화 호출 strict→json→text 폴백.

Design Ref: golden-sample-blueprint §2.3 (planner/writer: 워커 LLM 사용)
- 비전 어댑터(BaseVisionAdapter)와 동일 규칙: transient(408/429/5xx/timeout)는 전파,
  그 외는 다음 모드로 폴백, 전부 실패 시 StructuredCallError.
- 파싱/언팩 헬퍼는 multimodal 어댑터 모듈의 것을 재사용한다(복제 금지).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.multimodal.vision.base_vision_adapter import (
    _is_transient,
    _parse_text,
    _unpack_structured,
    _usage_of,
)

_MODES = ("strict", "json", "text")


class StructuredCallError(Exception):
    """모든 출력 모드 실패."""


class StructuredCaller:
    def __init__(
        self, llm, logger: LoggerInterface, callbacks: list[Any] | None = None
    ) -> None:
        self._llm = llm
        self._logger = logger
        self._config = {"callbacks": list(callbacks)} if callbacks else None

    async def call(
        self, messages: list, schema: type[BaseModel]
    ) -> tuple[BaseModel, str, dict | None]:
        last: Exception | None = None
        for mode in _MODES:
            try:
                draft, usage = await self._once(mode, messages, schema)
            except Exception as e:  # noqa: BLE001 — 모드별 폴백 판단
                if _is_transient(e):
                    raise
                last = e
                self._logger.warning(
                    "blueprint.structured mode failed — falling back",
                    mode=mode,
                    schema=schema.__name__,
                    exception=e,
                )
                continue
            return draft, mode, usage
        raise StructuredCallError(f"all output modes failed: {last}") from last

    async def _once(self, mode: str, messages: list, schema: type[BaseModel]):
        if mode == "text":
            msg = await self._llm.ainvoke(messages, config=self._config)
            return _parse_text(msg, schema), _usage_of(msg)
        structured = self._llm.with_structured_output(
            schema,
            method="json_schema" if mode == "strict" else "json_mode",
            strict=(mode == "strict"),
            include_raw=True,
        )
        return _unpack_structured(
            await structured.ainvoke(messages, config=self._config), schema
        )
