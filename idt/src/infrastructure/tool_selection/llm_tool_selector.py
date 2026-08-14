"""LLMToolSelector — Design Ref: §4.1, §6.1.

경량 모델 1콜로 후보 도구를 좁힌다.

이 모듈은 langchain을 import 하지 않는다. LLM 인스턴스는 domain의
LLMFactoryInterface를 통해 받으며, 프레임워크 타입은 어댑터에만 등장한다 (§9.3).

Plan RISK(기능 회귀) 대응: select()는 **어떤 경우에도 예외를 던지지 않는다**.
모든 실패는 fallback=True + reason으로 표현되고 필수 세트는 반드시 살아남는다.
"""
import asyncio
import json
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass

from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm_model.entity import LlmModel
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.tool_selection.interfaces.selection_cache_port import (
    SelectionCachePort,
)
from src.domain.tool_selection.interfaces.tool_selector_port import ToolSelectorPort
from src.domain.tool_selection.policies import (
    DEFAULT_TOP_K,
    SelectionReason,
    build_cache_key,
    merge,
    needs_selection,
    sanitize,
)
from src.domain.tool_selection.schemas import SelectionResult, ToolCandidate
from src.infrastructure.tool_selection.null_cache import NullSelectionCache
from src.infrastructure.tool_selection.prompts import (
    SELECTOR_SYSTEM_PROMPT,
    build_user_prompt,
)

DEFAULT_TIMEOUT_SEC = 3.0

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
_RAW_PREVIEW_LEN = 200


def parse_tool_ids(raw: str) -> list[object]:
    """모델 응답에서 도구 ID 배열을 뽑는다. 실패 시 ValueError.

    파싱은 관대하게 — 코드펜스를 벗기고, ``{"tool_ids": [...]}``와 맨 배열
    ``[...]`` 둘 다 받는다. 검증(화이트리스트 대조)은 호출부가 sanitize로 한다.
    """
    text = _FENCE.sub("", raw or "").strip()
    if not text:
        raise ValueError("empty response")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("tool_ids"), list):
        return list(data["tool_ids"])
    raise ValueError("missing 'tool_ids' array")


@dataclass(frozen=True)
class _Ctx:
    """한 번의 select() 호출에 걸친 불변 문맥."""

    started: float
    required: tuple[str, ...]
    order: tuple[str, ...]
    request_id: str


class LLMToolSelector(ToolSelectorPort):
    """경량 LLM 1콜 기반 도구 선별기."""

    def __init__(
        self,
        llm_factory: LLMFactoryInterface,
        llm_model: LlmModel,
        logger: LoggerInterface,
        cache: SelectionCachePort | None = None,
        top_k: int = DEFAULT_TOP_K,
        timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    ) -> None:
        self._llm_factory = llm_factory
        self._llm_model = llm_model
        self._logger = logger
        self._cache = cache or NullSelectionCache()
        self._top_k = top_k
        self._timeout_sec = timeout_sec

    # ── Public ──────────────────────────────────────────────────────────────

    async def select(
        self,
        query: str,
        candidates: Sequence[ToolCandidate],
        *,
        required_ids: Sequence[str] = (),
        request_id: str = "",
    ) -> SelectionResult:
        """Design §2.2 데이터 흐름을 그대로 따른다."""
        ctx = _Ctx(
            started=time.perf_counter(),
            required=tuple(dict.fromkeys(required_ids)),
            order=tuple(c.tool_id for c in candidates),
            request_id=request_id,
        )

        short = self._short_circuit(candidates, ctx)
        if short is not None:
            return short

        cached = await self._from_cache(query, ctx)
        if cached is not None:
            return cached

        ids, failure = await self._ask_llm(query, candidates, ctx)
        if failure is not None:
            return self._result(ctx, (), reason=failure, fallback=True)

        kept, dropped = sanitize(ids or [], ctx.order)
        kept = kept[: self._top_k]
        if not kept:
            return self._result(
                ctx, (), reason=SelectionReason.EMPTY_SELECTION,
                fallback=True, dropped=dropped,
            )

        await self._store(query, ctx, kept)
        reason = SelectionReason.SANITIZED if dropped else None
        return self._result(ctx, kept, reason=reason, dropped=dropped)

    # ── 조기 반환 (§6.1 #1, #2) ─────────────────────────────────────────────

    def _short_circuit(
        self, candidates: Sequence[ToolCandidate], ctx: _Ctx
    ) -> SelectionResult | None:
        """LLM을 부를 필요가 없는 경우를 먼저 걸러낸다 (FR-08)."""
        if not candidates:
            return self._result(ctx, (), reason=SelectionReason.NO_CANDIDATES)
        if not needs_selection(len(candidates), self._top_k):
            return self._result(
                ctx, ctx.order, reason=SelectionReason.UNDER_THRESHOLD
            )
        return None

    # ── 캐시 (§4.2) ─────────────────────────────────────────────────────────

    async def _from_cache(self, query: str, ctx: _Ctx) -> SelectionResult | None:
        """캐시 히트 시 결과 반환. 캐시 장애는 미스로 강등한다."""
        try:
            cached = await self._cache.get(build_cache_key(query, ctx.order))
        except Exception as exc:
            self._logger.warning(
                "Tool selection cache read failed",
                request_id=ctx.request_id, exception=exc,
            )
            return None
        if not cached:
            return None
        kept, dropped = sanitize(cached, ctx.order)
        if not kept:
            return None
        return self._result(
            ctx, kept[: self._top_k],
            reason=SelectionReason.CACHE_HIT, dropped=dropped,
        )

    async def _store(self, query: str, ctx: _Ctx, kept: Sequence[str]) -> None:
        try:
            await self._cache.set(build_cache_key(query, ctx.order), kept)
        except Exception as exc:
            self._logger.warning(
                "Tool selection cache write failed",
                request_id=ctx.request_id, exception=exc,
            )

    # ── LLM 호출 (§6.1 #3, #4, #5) ──────────────────────────────────────────

    async def _ask_llm(
        self, query: str, candidates: Sequence[ToolCandidate], ctx: _Ctx
    ) -> tuple[list[object] | None, str | None]:
        """``(ids, failure_reason)`` — 실패 시 ids는 None."""
        try:
            raw = await asyncio.wait_for(
                self._invoke(query, candidates), self._timeout_sec
            )
        except TimeoutError:
            self._logger.warning(
                "Tool selection LLM timed out",
                request_id=ctx.request_id, timeout_sec=self._timeout_sec,
            )
            return None, SelectionReason.LLM_TIMEOUT
        except Exception as exc:
            self._logger.warning(
                "Tool selection LLM call failed",
                request_id=ctx.request_id, exception=exc,
            )
            return None, SelectionReason.LLM_ERROR

        try:
            return parse_tool_ids(raw), None
        except ValueError as exc:
            self._logger.warning(
                "Tool selection response parse failed",
                request_id=ctx.request_id, exception=exc,
                raw_preview=raw[:_RAW_PREVIEW_LEN],
            )
            return None, SelectionReason.PARSE_ERROR

    async def _invoke(
        self, query: str, candidates: Sequence[ToolCandidate]
    ) -> str:
        llm = self._llm_factory.create(self._llm_model, temperature=0)
        messages = [
            ("system", SELECTOR_SYSTEM_PROMPT.format(top_k=self._top_k)),
            ("user", build_user_prompt(query, candidates)),
        ]
        response = await llm.ainvoke(messages)
        content = getattr(response, "content", "")
        return content if isinstance(content, str) else str(content)

    # ── 결과 조립 & 관측 (FR-10) ────────────────────────────────────────────

    def _result(
        self,
        ctx: _Ctx,
        selected: Sequence[str],
        *,
        reason: str | None = None,
        fallback: bool = False,
        dropped: Sequence[str] = (),
    ) -> SelectionResult:
        result = SelectionResult(
            selected_ids=tuple(selected),
            required_ids=ctx.required,
            final_ids=merge(ctx.required, selected, ctx.order),
            candidate_count=len(ctx.order),
            elapsed_ms=int((time.perf_counter() - ctx.started) * 1000),
            fallback=fallback,
            reason=reason,
            dropped_ids=tuple(dropped),
        )
        self._log(result, ctx.request_id)
        return result

    def _log(self, result: SelectionResult, request_id: str) -> None:
        payload = {
            "request_id": request_id,
            "candidate_count": result.candidate_count,
            "selected_count": len(result.final_ids),
            "fallback": result.fallback,
            "reason": result.reason,
            "elapsed_ms": result.elapsed_ms,
        }
        if result.fallback or result.dropped_ids:
            self._logger.warning(
                "Tool selection degraded",
                dropped_ids=list(result.dropped_ids), **payload,
            )
            return
        self._logger.info("Tool selection completed", **payload)
