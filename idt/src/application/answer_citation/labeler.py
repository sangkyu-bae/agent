"""검색 결과 머리말 라벨러 (answer-citation-verification §10.2, FR-03).

on: `[출처 {n}: {파일} · {page}쪽]` — 번호는 실행 단위 레지스트리에서 받는다.
실행 컨텍스트가 없거나 실패하면 None → 검색 도구가 기존 `[출처: 파일]` 을 쓴다.
"""

from __future__ import annotations

from typing import Any

from src.application.agent_run.context import get_current_run_context
from src.application.answer_citation.registry import CitationRegistry
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class CitationLabeler:
    def __init__(self, registry: CitationRegistry, logger: LoggerInterface) -> None:
        self._registry = registry
        self._logger = logger

    def label(
        self,
        *,
        source: str,
        chunk_id: str | None,
        document_id: str | None,
        page: Any,
        text: str,
    ) -> str | None:
        ctx = get_current_run_context()
        if ctx is None or ctx.run_id is None:
            return None
        page_no = _page(page)
        try:
            marker = self._registry.assign(
                str(ctx.run_id.value),
                chunk_id=chunk_id,
                document_id=document_id,
                page=page_no,
                text=text,
            )
        except Exception as e:  # noqa: BLE001 — 머리말은 기존 형식으로 내려간다
            self._logger.warning(
                "citation label failed — plain source header used",
                exception=e,
                chunk_id=chunk_id,
            )
            return None
        suffix = f" · {page_no}쪽" if page_no is not None else ""
        return f"[출처 {marker}: {source}{suffix}]"


def _page(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
