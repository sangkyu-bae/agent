"""규칙 추출기 — 조문 참조(제N조(의M)·별표 N·부칙)를 LLM 없이 추출한다.

Design Ref: graph-rag-foundation §7.2 D2 / Plan FR-05.
- 청크 첫머리의 '제N조'를 이 청크 자신의 조문으로 본다(조항 청킹 결과 기준).
- 조문 엔티티 키는 문서 단위("{document_id}::제5조") — 다른 문서의 같은 번호와
  섞이지 않게 한다. 자기 조문이 없으면 언급만 만들고 관계는 만들지 않는다.
"""

from __future__ import annotations

import re

from src.domain.graph_rag.extraction import (
    REL_REFERS_TO,
    ChunkUnit,
    ExtractionContext,
    ExtractionResult,
    Mention,
    RelationDraft,
)
from src.domain.graph_rag.interfaces import GraphExtractorPort

CLAUSE_TYPE = "조문"
REFERS_TYPE = "참조"

_ARTICLE = r"제\s*(\d+)\s*조(?:\s*의\s*(\d+))?"
_REF = re.compile(rf"{_ARTICLE}|별표\s*(\d+)|(부칙)")
_OWN = re.compile(rf"^\s*{_ARTICLE}")
_EVIDENCE_PAD = 20


def _name(m: re.Match) -> str:
    # _OWN 은 그룹이 2개, _REF 는 4개 — 모자란 그룹은 None 으로 채운다
    article, sub, appendix, supplementary = (m.groups() + (None,) * 4)[:4]
    if article:
        return f"제{article}조" + (f"의{sub}" if sub else "")
    if appendix:
        return f"별표 {appendix}"
    return supplementary


def _evidence(text: str, m: re.Match) -> str:
    start = max(0, m.start() - _EVIDENCE_PAD)
    return text[start : m.end() + _EVIDENCE_PAD].strip()


class RuleGraphExtractor(GraphExtractorPort):
    async def extract(
        self, unit: ChunkUnit, context: ExtractionContext
    ) -> ExtractionResult:
        text = unit.content
        own_match = _OWN.match(text)
        own = _name(own_match) if own_match else None
        names: dict[str, str] = {}
        relations: list[RelationDraft] = []
        for m in _REF.finditer(text):
            name = _name(m)
            names.setdefault(name, f"{unit.document_id}::{name}")
            if (
                own is None
                or name == own
                or names[name] in {r.target for r in relations}
            ):
                continue
            relations.append(
                RelationDraft(
                    source=f"{unit.document_id}::{own}",
                    target=names[name],
                    type=REFERS_TYPE,
                    evidence=_evidence(text, m),
                    chunk_id=unit.chunk_id,
                    kind=REL_REFERS_TO,
                )
            )
        mentions = tuple(
            Mention(
                name=n, type=CLAUSE_TYPE, description="", chunk_id=unit.chunk_id, key=k
            )
            for n, k in names.items()
        )
        return ExtractionResult(mentions=mentions, relations=tuple(relations))
