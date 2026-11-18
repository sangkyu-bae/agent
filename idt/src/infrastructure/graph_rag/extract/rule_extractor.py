"""규칙 추출기 — 조문 제목·조문 참조(제N조(의M)·별표 N·부칙)를 LLM 없이 추출한다.

Design Ref: graph-rag-foundation §7.2 D2 / Plan FR-05 / §11.7.1 개선(2026-11-17).
- 줄 첫머리의 `제N조(제목)`을 조문 머리로 본다. 청크가 "규정 (발췌)" 같은 제목
  줄로 시작해도 모든 조문 머리를 찾는다. 줄 중간의 `제3조(정의)에 따른`은 참조다.
- 조문 머리마다 `조문 -[정의]-> 제목 개념` 관계를 만든다(근거 = 조문 머리 문자열).
  제목 개념은 LLM 이 같은 이름으로 뽑았으면 그 엔티티에 연결된다(유스케이스가
  LLM 언급을 먼저 판정한다).
- 본문 속 참조는 그 위치를 포함하는 조문(직전 조문 머리)에서 나가는 REFERS_TO.
- 조문 엔티티 키는 문서 단위("{document_id}::제5조")라 다른 문서와 섞이지 않는다.
"""

from __future__ import annotations

import re

from src.domain.graph_rag.extraction import (
    REL_REFERS_TO,
    REL_RELATES,
    ChunkUnit,
    ExtractionContext,
    ExtractionResult,
    Mention,
    RelationDraft,
)
from src.domain.graph_rag.interfaces import GraphExtractorPort

CLAUSE_TYPE = "조문"
TITLE_TYPE = "용어"
REFERS_TYPE = "참조"
TITLE_RELATION_TYPE = "정의"

_ARTICLE = r"제\s*(\d+)\s*조(?:\s*의\s*(\d+))?"
_REF = re.compile(rf"{_ARTICLE}|별표\s*(\d+)|(부칙)")
# 줄 첫머리 조문 머리. 제목(괄호)은 선택 — 없으면 참조 소유만 한다.
_HEADING = re.compile(rf"(?m)^[ \t]*{_ARTICLE}(?:[ \t]*\(([^()\n]{{1,40}})\))?")
_EVIDENCE_PAD = 20


def _article(article: str, sub: str | None) -> str:
    return f"제{article}조" + (f"의{sub}" if sub else "")


def _ref_name(m: re.Match) -> str:
    article, sub, appendix, supplementary = m.groups()
    if article:
        return _article(article, sub)
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
        text, doc = unit.content, unit.document_id
        headings = list(_HEADING.finditer(text))
        clauses: dict[str, str] = {}  # 표시 이름 → 키
        mentions: list[Mention] = []
        relations: list[RelationDraft] = []
        for h in headings:
            name = _article(h.group(1), h.group(2))
            clauses.setdefault(name, f"{doc}::{name}")
            title = (h.group(3) or "").strip()
            if title:
                mentions.append(Mention(title, TITLE_TYPE, "", unit.chunk_id))
                relations.append(
                    RelationDraft(
                        source=clauses[name],
                        target=title,
                        type=TITLE_RELATION_TYPE,
                        evidence=h.group(0).strip(),
                        chunk_id=unit.chunk_id,
                        kind=REL_RELATES,
                    )
                )
        relations += self._references(text, unit, headings, clauses)
        mentions = [
            Mention(n, CLAUSE_TYPE, "", unit.chunk_id, key=k)
            for n, k in clauses.items()
        ] + mentions
        return ExtractionResult(mentions=tuple(mentions), relations=tuple(relations))

    @staticmethod
    def _references(
        text: str, unit: ChunkUnit, headings: list[re.Match], clauses: dict[str, str]
    ) -> list[RelationDraft]:
        out: dict[tuple[str, str], RelationDraft] = {}
        for m in _REF.finditer(text):
            name = _ref_name(m)
            clauses.setdefault(name, f"{unit.document_id}::{name}")
            # 조문 번호 위치끼리 비교한다(머리 자신의 매치도 그 조문이 소유).
            pos = m.start(1) if m.group(1) else m.start()
            owner = next((h for h in reversed(headings) if h.start(1) <= pos), None)
            if owner is None:
                continue
            owner_key = clauses[_article(owner.group(1), owner.group(2))]
            target = clauses[name]
            if target == owner_key or (owner_key, target) in out:
                continue
            out[(owner_key, target)] = RelationDraft(
                source=owner_key,
                target=target,
                type=REFERS_TYPE,
                evidence=_evidence(text, m),
                chunk_id=unit.chunk_id,
                kind=REL_REFERS_TO,
            )
        return list(out.values())
