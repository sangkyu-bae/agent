"""인용 정리 정책 (answer-citation-verification §3.2, D-06~D-08).

판정 결과를 최종 본문에 적용한다: 통과한 인용만 남기고 등장 순서대로 1부터
다시 번호를 매긴다. 레지스트리에 없는 번호의 `[n]` 글자는 건드리지 않는다.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping, Sequence

from src.domain.answer_citation.models import (
    AnswerCitation,
    CitationOutcome,
    NoneReason,
    RegisteredChunk,
)
from src.domain.answer_citation.parser import CitationMarkerParser, MarkerHit
from src.domain.hallucination.citation_check import CitationCheck, CitationPair
from src.domain.hallucination.grounding_edit import GroundingEditPolicy

_DROP_SPACE_BEFORE = set(".?!。,;:)\n")
Verdicts = dict[tuple[str, int], str]


class EvidenceLocator:
    @staticmethod
    def find(evidence: str, chunk_text: str) -> bool:
        """근거 문장이 청크에 실제로 있는가.

        공백·U+FFFD 무시, NFKC — 원문 뷰어 매칭과 같은 기준.
        """
        needle = _squash(evidence)
        return bool(needle) and needle in _squash(chunk_text)


class CitationFinalizePolicy:
    @classmethod
    def finalize(
        cls,
        text: str,
        *,
        chunks: Mapping[int, RegisteredChunk],
        pairs: Sequence[CitationPair],
        checks: Sequence[CitationCheck],
        judged: bool,
    ) -> CitationOutcome:
        text = CitationMarkerParser.normalize(text)
        hits = CitationMarkerParser.markers(text, chunks)
        if not hits:
            return _none(text, "no_markers")
        if not judged:
            return _none(_rebuild(text, hits, {}), "judge_failed")
        verdicts = _verdicts(pairs, checks, chunks)
        kept = cls._kept(text, hits, verdicts, chunks)
        if not kept:
            return _none(_rebuild(text, hits, {}), "all_rejected")
        numbers = _renumber(hits, kept)
        citations = cls._citations(text, hits, kept, numbers, verdicts, chunks)
        replacements = {i: f"[{numbers[hits[i].marker]}]" for i in kept}
        return CitationOutcome(
            text=_rebuild(text, hits, replacements),
            status="verified",
            citations=citations,
        )

    @staticmethod
    def _kept(
        text: str,
        hits: list[MarkerHit],
        verdicts: Verdicts,
        chunks: Mapping[int, RegisteredChunk],
    ) -> dict[int, str]:
        """남길 인용 표시 index → 그 문장 원문.

        Analysis G-10: 한 문장 안에서 같은 문서의 같은 근거 문장을 가리키는
        인용(parent·child 청크 중복)은 첫 번째만 남긴다.
        """
        kept: dict[int, str] = {}
        seen: set[tuple[tuple[int, int], str | None, str]] = set()
        spans = GroundingEditPolicy.sentence_spans(text)
        for i, hit in enumerate(hits):
            span = next((s for s in spans if s[0] <= hit.start < s[1]), None)
            if span is None:
                continue
            sentence = text[span[0] : span[1]]
            key = CitationMarkerParser.sentence_key(sentence)
            if (key, hit.marker) not in verdicts:
                continue
            evidence = _squash(verdicts[(key, hit.marker)])
            if evidence:
                same = (span, chunks[hit.marker].document_id, evidence)
                if same in seen:
                    continue
                seen.add(same)
            kept[i] = sentence
        return kept

    @staticmethod
    def _citations(
        text: str,
        hits: list[MarkerHit],
        kept: dict[int, str],
        numbers: dict[int, int],
        verdicts: Verdicts,
        chunks: Mapping[int, RegisteredChunk],
    ) -> tuple[AnswerCitation, ...]:
        seen: set[tuple[int, str]] = set()
        out: list[AnswerCitation] = []
        for i, sentence in kept.items():
            marker = hits[i].marker
            key = CitationMarkerParser.sentence_key(sentence)
            if (marker, key) in seen:
                continue
            seen.add((marker, key))
            chunk = chunks[marker]
            evidence = verdicts[(key, marker)]
            out.append(
                AnswerCitation(
                    no=numbers[marker],
                    marker=marker,
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    page=chunk.page,
                    evidence=evidence
                    if EvidenceLocator.find(evidence, chunk.text)
                    else None,
                    sentence=CitationMarkerParser.strip_all(sentence).strip(),
                )
            )
        return tuple(out)


def _verdicts(
    pairs: Sequence[CitationPair],
    checks: Sequence[CitationCheck],
    chunks: Mapping[int, RegisteredChunk],
) -> Verdicts:
    by_id = {c.pair_id: c for c in checks}
    verdicts: Verdicts = {}
    for p in pairs:
        check = by_id.get(p.pair_id)
        if check is None or not check.supported or p.marker not in chunks:
            continue
        if _evidence_from_other_chunk(check.evidence, p.marker, chunks):
            continue  # 번호가 틀린 인용 — 다른 청크 문장을 근거로 댔다(D-07 보강)
        key = CitationMarkerParser.sentence_key(p.sentence)
        verdicts[(key, p.marker)] = check.evidence
    return verdicts


def _evidence_from_other_chunk(
    evidence: str, marker: int, chunks: Mapping[int, RegisteredChunk]
) -> bool:
    """근거 문장이 지정 청크엔 없고 다른 청크에만 있는가.

    벤치(2026-11-21): 판정기가 틀린 번호의 인용에 실제 근거 청크 문장을 대며
    supported 로 답했다. 어느 청크에도 없으면(복사 오류) 탈락시키지 않는다.
    """
    if not evidence or EvidenceLocator.find(evidence, chunks[marker].text):
        return False
    return any(
        EvidenceLocator.find(evidence, c.text) for n, c in chunks.items() if n != marker
    )


def _renumber(hits: list[MarkerHit], kept: dict[int, str]) -> dict[int, int]:
    numbers: dict[int, int] = {}
    for i in sorted(kept):
        numbers.setdefault(hits[i].marker, len(numbers) + 1)
    return numbers


def _rebuild(text: str, hits: list[MarkerHit], replacements: dict[int, str]) -> str:
    """kept 는 새 번호로 바꾸고 나머지 인용 표시는 지운다. 지운 표시 앞 공백도 정리."""
    out: list[str] = []
    cursor = 0
    for i, hit in enumerate(hits):
        out.append(text[cursor : hit.start])
        cursor = hit.end
        if i in replacements:
            out.append(replacements[i])
            continue
        following = _next_char(text, hits, i)
        if following in _DROP_SPACE_BEFORE and out and out[-1].endswith(" "):
            out[-1] = out[-1].rstrip(" ")
    out.append(text[cursor:])
    return "".join(out)


def _next_char(text: str, hits: list[MarkerHit], i: int) -> str:
    """지운 표시 뒤의 첫 글자(바로 붙은 다른 인용 표시는 건너뜀). 끝이면 '\\n'."""
    pos = hits[i].end
    j = i + 1
    while j < len(hits) and hits[j].start == pos:
        pos = hits[j].end
        j += 1
    return text[pos] if pos < len(text) else "\n"


def _none(text: str, reason: NoneReason) -> CitationOutcome:
    return CitationOutcome(text=text, status="none", citations=(), none_reason=reason)


def _squash(value: str) -> str:
    return "".join(unicodedata.normalize("NFKC", value or "").replace("�", "").split())
