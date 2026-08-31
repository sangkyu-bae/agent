"""deep-search-pipeline 테스트용 더블 — 실 LLM·네트워크 없이 노드/그래프를 구동한다.

Design §8.5: 모든 테스트는 Fake LLM / Fake Tool 주입으로 수행하며
실제 API 키나 네트워크를 요구하지 않는다.
"""
from __future__ import annotations

from typing import Any

from src.application.deep_search.llm_schemas import (
    CoverageVerdictOut,
    EvidenceExtractOut,
    SearchPlanOut,
)

_MODEL_SLOT = {
    SearchPlanOut.__name__: "plan",
    EvidenceExtractOut.__name__: "extract",
    CoverageVerdictOut.__name__: "evaluate",
}


class FakeStructuredLLM:
    """`with_structured_output(Model).ainvoke(messages)` 만 지원하는 최소 더블."""

    def __init__(self, parent: FakeLLM, slot: str) -> None:
        self._parent = parent
        self._slot = slot

    async def ainvoke(self, messages: list[dict]) -> Any:
        self._parent.calls.append((self._slot, messages))
        queue = self._parent.scripts.get(self._slot) or []
        if not queue:
            raise AssertionError(f"FakeLLM: '{self._slot}' 응답이 소진되었습니다")
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        return item


class FakeLLM:
    """슬롯(plan/extract/evaluate)별 응답 스크립트를 재생한다.

    각 슬롯의 리스트는 호출 순서대로 소비되며, 마지막 항목은 반복 재사용된다.
    항목이 Exception이면 raise 한다 (실패 폴백 테스트용).
    """

    def __init__(
        self,
        plan: list[Any] | None = None,
        extract: list[Any] | None = None,
        evaluate: list[Any] | None = None,
    ) -> None:
        self.scripts: dict[str, list[Any]] = {
            "plan": list(plan or []),
            "extract": list(extract or []),
            "evaluate": list(evaluate or []),
        }
        self.calls: list[tuple[str, list[dict]]] = []

    def with_structured_output(self, model: type) -> FakeStructuredLLM:
        slot = _MODEL_SLOT.get(model.__name__)
        if slot is None:
            raise AssertionError(f"FakeLLM: 알 수 없는 스키마 {model.__name__}")
        return FakeStructuredLLM(self, slot)

    def count(self, slot: str) -> int:
        return sum(1 for s, _ in self.calls if s == slot)

    @property
    def total_calls(self) -> int:
        return len(self.calls)

    def prompt_text(self, slot: str, index: int = -1) -> str:
        messages = [m for s, m in self.calls if s == slot][index]
        return "\n".join(str(m.get("content", "")) for m in messages)


class FakeTool:
    """`ainvoke(payload)` 만 지원하는 검색 도구 더블."""

    def __init__(
        self,
        responses: dict[str, str] | None = None,
        default: str = "<result>기본 검색 결과</result>",
        fail: set[str] | None = None,
        fail_all: bool = False,
        accepts_max_results: bool = True,
    ) -> None:
        self._responses = responses or {}
        self._default = default
        self._fail = fail or set()
        self._fail_all = fail_all
        self._accepts_max_results = accepts_max_results
        self.queries: list[str] = []
        self.payloads: list[dict] = []

    async def ainvoke(self, payload: dict) -> str:
        if not self._accepts_max_results and "max_results" in payload:
            raise TypeError("unexpected keyword argument 'max_results'")
        query = payload["query"]
        self.queries.append(query)
        self.payloads.append(dict(payload))
        if self._fail_all or query in self._fail:
            raise RuntimeError(f"검색 실패: {query}")
        return self._responses.get(query, self._default)


class FakeLogger:
    """구조화 로거 더블 — 레벨별 (message, kwargs) 를 기록한다."""

    def __init__(self) -> None:
        self.records: list[tuple[str, str, dict]] = []

    def _log(self, level: str, message: str, **kwargs: Any) -> None:
        self.records.append((level, message, kwargs))

    def debug(self, message: str, **kwargs: Any) -> None:
        self._log("debug", message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        self._log("info", message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        self._log("warning", message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        self._log("error", message, **kwargs)

    def messages(self, level: str) -> list[str]:
        return [m for lv, m, _ in self.records if lv == level]

    def has(self, level: str, needle: str) -> bool:
        return any(needle in m for m in self.messages(level))
