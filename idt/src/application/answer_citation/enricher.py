"""근거 칩에 저장된 인용을 붙인다 (answer-citation-verification §4.2, D-12~D-14).

RunSourcesService 가 duck typing 으로 부른다:
  stored = await enricher.load(run_ids, request_id)   # 실행 묶음당 1회
  items = enricher.apply(items, stored.get(run_id), evidence)
- 저장 행이 없으면(not_applicable) 칩 그대로 — 키를 싣지 않는다.
- 문서 칩마다 {status, entries}. 인용되지 않은 문서는 entries=[] (미사용 구절).
- 인용된 문서가 칩 상한으로 빠졌으면 검색 기록으로 문서 칩을 보충한다(D-14).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable

from src.domain.agent_run.entities import RetrievalSource
from src.domain.agent_run.source_policy import RunEvidence, RunSourceItem, SourceKind
from src.domain.answer_citation.models import AnswerCitation
from src.domain.answer_citation.ports import (
    AnswerCitationRepositoryPort,
    StoredRunCitations,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class CitationEnricher:
    def __init__(
        self, repo: AnswerCitationRepositoryPort, logger: LoggerInterface
    ) -> None:
        self._repo = repo
        self._logger = logger

    async def load(
        self, run_ids: list[str], request_id: str
    ) -> dict[str, StoredRunCitations]:
        return await self._repo.find_by_runs(run_ids, request_id)

    def apply(
        self,
        items: list[RunSourceItem],
        stored: StoredRunCitations | None,
        evidence: RunEvidence,
    ) -> list[RunSourceItem]:
        if stored is None:
            return items
        by_doc = _entries_by_document(stored.citations, evidence.retrievals)
        out = [
            dataclasses.replace(item, citation=_payload(stored, by_doc.get(item.key)))
            if item.kind == SourceKind.DOCUMENT
            else item
            for item in items
        ]
        present = {i.key for i in items if i.kind == SourceKind.DOCUMENT}
        missing = [
            _document_item(doc, entries, stored, evidence)
            for doc, entries in by_doc.items()
            if doc not in present
        ]
        return _insert_after_documents(out, missing)


def _entries_by_document(
    citations: Iterable[AnswerCitation], retrievals: list[RetrievalSource]
) -> dict[str, list[dict]]:
    """문서별 인용 항목 — 같은 번호·같은 청크는 한 번, 번호 순."""
    by_doc: dict[str, dict[tuple, dict]] = {}
    for c in citations:
        if not c.document_id:
            continue
        key = (c.no, c.chunk_id)
        by_doc.setdefault(c.document_id, {}).setdefault(
            key,
            {
                "no": c.no,
                "chunk_id": c.chunk_id,
                "page": c.page
                if c.page is not None
                else _page_of(c.chunk_id, retrievals),
                "evidence": c.evidence,
            },
        )
    return {
        doc: sorted(entries.values(), key=lambda e: e["no"])
        for doc, entries in by_doc.items()
    }


def _payload(stored: StoredRunCitations, entries: list[dict] | None) -> dict:
    return {"status": stored.status, "entries": list(entries or [])}


def _document_item(
    document_id: str,
    entries: list[dict],
    stored: StoredRunCitations,
    evidence: RunEvidence,
) -> RunSourceItem:
    return RunSourceItem(
        kind=SourceKind.DOCUMENT,
        label=_filename(document_id, evidence) or document_id,
        excerpt=next((e["evidence"] for e in entries if e["evidence"]), ""),
        key=document_id,
        citation=_payload(stored, entries),
    )


def _insert_after_documents(
    items: list[RunSourceItem], extra: list[RunSourceItem]
) -> list[RunSourceItem]:
    if not extra:
        return items
    last_doc = max(
        (i for i, item in enumerate(items) if item.kind == SourceKind.DOCUMENT),
        default=-1,
    )
    return items[: last_doc + 1] + extra + items[last_doc + 1 :]


def _page_of(chunk_id: str | None, retrievals: list[RetrievalSource]) -> int | None:
    for r in retrievals:
        if r.chunk_id == chunk_id:
            try:
                return int((r.metadata_json or {}).get("page"))
            except (TypeError, ValueError):
                return None
    return None


def _filename(document_id: str, evidence: RunEvidence) -> str:
    for r in evidence.retrievals:
        name = (r.metadata_json or {}).get("filename")
        if r.document_id == document_id and name:
            return str(name)
    return evidence.filenames.get(document_id, "")
