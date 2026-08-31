"""BaseVisionAdapter — 비전 어댑터 공통 골격.

Design Ref: multimodal-extractor §9.5
— LLMFactory 재사용(클라이언트·API 키·base_url 경로 통일),
  출력 모드 폴백 strict→json→text,
  서브클래스는 build_image_block() 만 구현한다(벤더별 유일한 차이).
Design §6.3: 폴백으로 성공하면 degraded_output_mode=True (결과는 있으나 품질 표기).
Plan FR-05, FR-20(usage 전달: 응답 usage_metadata → DescribeOutcome.usage,
callbacks 주입 가능).
"""

import json
import re
from abc import ABC, abstractmethod
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from pydantic import BaseModel, ValidationError

from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm_model.entity import LlmModel
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.multimodal.interfaces import (
    DescribeOptions,
    DescribeOutcome,
    VisionDescriberPort,
)
from src.domain.multimodal.schemas import DescriptionDraft
from src.domain.multimodal.value_objects import ElementType, ImageCandidate
from src.infrastructure.multimodal.prompts import build_messages

_TRANSIENT_STATUS = {408, 429, 500, 502, 503, 504}
_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


class VisionCallError(Exception):
    """모든 출력 모드가 실패 — UseCase 가 건별 failed 로 기록한다."""


class BaseVisionAdapter(VisionDescriberPort, ABC):
    provider: str = ""
    output_modes: tuple[str, ...] = ("strict", "json", "text")

    def __init__(
        self,
        llm_factory: LLMFactoryInterface,
        llm_model: LlmModel,
        logger: LoggerInterface,
        callbacks: list[Any] | None = None,
    ) -> None:
        self._model = llm_model
        self._logger = logger
        self._callbacks = list(callbacks or [])
        self._llm: BaseChatModel = llm_factory.create(llm_model, temperature=0.0)
        # 불변 — asyncio.gather 로 동시 호출돼도 공유 가변 상태가 없다
        self._config: dict[str, Any] | None = (
            {"callbacks": self._callbacks} if self._callbacks else None
        )

    @abstractmethod
    def build_image_block(
        self, image: ImageCandidate, options: DescribeOptions
    ) -> dict:
        """벤더별 이미지 content block."""

    async def describe(
        self,
        image: ImageCandidate,
        element_type: ElementType,
        options: DescribeOptions,
    ) -> DescribeOutcome:
        messages = build_messages(
            element_type, options, self.build_image_block(image, options)
        )
        return await self.describe_with(messages, DescriptionDraft)

    async def describe_with(
        self, messages: list, schema: type[BaseModel]
    ) -> DescribeOutcome:
        """임의 strict 스키마로 비전 호출 (golden-sample-blueprint D8).

        모드 폴백·transient 전파·degraded 표기는 describe() 와 동일.
        draft 는 `schema` 인스턴스.
        """
        last_error: Exception | None = None
        for mode in self.output_modes:
            try:
                draft, usage = await self._call(mode, messages, schema)
            except Exception as e:  # noqa: BLE001 — 모드별 폴백 판단을 위해 전부 받는다
                if _is_transient(e):
                    raise
                last_error = e
                self._logger.warning(
                    "vision.describe mode failed — falling back",
                    provider=self.provider,
                    model=self._model.model_name,
                    mode=mode,
                    schema=schema.__name__,
                    exception=e,
                )
                continue
            return DescribeOutcome(
                draft=draft,  # type: ignore[arg-type]
                degraded_output_mode=(mode != "strict"),
                output_mode=mode,
                usage=usage,
            )
        raise VisionCallError(
            f"all output modes failed ({', '.join(self.output_modes)}): {last_error}"
        ) from last_error

    async def _call(
        self, mode: str, messages: list, schema: type[BaseModel] = DescriptionDraft
    ) -> tuple[BaseModel, dict | None]:
        if mode == "text":
            msg = await self._llm.ainvoke(messages, config=self._config)
            return _parse_text(msg, schema), _usage_of(msg)
        structured = self._llm.with_structured_output(
            schema,
            method="json_schema" if mode == "strict" else "json_mode",
            strict=(mode == "strict"),
            # Plan FR-20: raw AIMessage 의 usage_metadata 를 함께 받는다
            include_raw=True,
        )
        result = await structured.ainvoke(messages, config=self._config)
        return _unpack_structured(result, schema)


def _unpack_structured(
    result: Any, schema: type[BaseModel] = DescriptionDraft
) -> tuple[BaseModel, dict | None]:
    """include_raw=True 응답({"raw","parsed","parsing_error"}) 또는
    Draft 직접 반환 모두 수용.
    """
    if isinstance(result, dict) and "parsed" in result:
        if result.get("parsing_error") is not None:
            raise ValueError(f"structured parsing failed: {result['parsing_error']}")
        parsed, raw = result["parsed"], result.get("raw")
        usage = _usage_of(raw)
    else:
        parsed, usage = result, None
    if parsed is None:
        raise ValueError("structured output returned no parsed object")
    if not isinstance(parsed, schema):
        parsed = schema.model_validate(parsed)
    return parsed, usage


def _is_transient(e: Exception) -> bool:
    status = getattr(e, "status_code", None) or getattr(e, "status", None)
    if isinstance(status, int) and status in _TRANSIENT_STATUS:
        return True
    return isinstance(e, TimeoutError)


def _usage_of(msg: Any) -> dict | None:
    usage = getattr(msg, "usage_metadata", None)
    return dict(usage) if usage else None


def _parse_text(
    msg: AIMessage, schema: type[BaseModel] = DescriptionDraft
) -> BaseModel:
    content = msg.content if isinstance(msg.content, str) else json.dumps(msg.content)
    m = _FENCE.search(content)
    raw = m.group(1) if m else content[content.find("{") : content.rfind("}") + 1]
    try:
        return schema.model_validate_json(raw)
    except (ValidationError, ValueError) as e:
        raise ValueError(
            f"text mode: response is not a {schema.__name__} JSON: {e}"
        ) from e
