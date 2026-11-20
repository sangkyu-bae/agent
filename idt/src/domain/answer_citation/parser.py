"""답변 본문의 인용 표시 `[n]` 해석 (answer-citation-verification §3.2, D-09·D-10).

- 코드 블록(``` 펜스·`인라인`) 안의 `[n]` 은 인용이 아니다.
- `[1, 3]`·`[1,3]` 은 `[1][3]` 으로, `문장.[1]` 은 `문장[1].` 로 정규화한다
  (문장 경계 규칙이 종결 부호 뒤 공백을 요구해, 옮기지 않으면 두 문장이 합쳐진다).
- 문장 경계는 GroundingEditPolicy.sentence_spans — 문장 제거와 같은 단위(D-06).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from src.domain.hallucination.citation_check import CitationPair
from src.domain.hallucination.grounding_edit import GroundingEditPolicy

_FENCE = re.compile(r"```.*?(?:```|\Z)", re.S)
_INLINE = re.compile(r"`[^`\n]*`")
_MARKER = re.compile(r"\[(\d{1,3})\]")
_GROUP = re.compile(r"\[(\d{1,3}(?:\s*,\s*\d{1,3})+)\]")
_AFTER_TERMINATOR = re.compile(r"([.?!。])((?:\[\d{1,3}\])+)")
_WS = re.compile(r"\s+")


@dataclass(frozen=True)
class MarkerHit:
    start: int
    end: int
    marker: int


class CitationMarkerParser:
    @staticmethod
    def normalize(text: str) -> str:
        def _plain(segment: str) -> str:
            segment = _GROUP.sub(
                lambda m: "".join(f"[{n.strip()}]" for n in m.group(1).split(",")),
                segment,
            )
            return _AFTER_TERMINATOR.sub(r"\2\1", segment)

        return _map_plain(text, _plain)

    @staticmethod
    def markers(text: str, known: Iterable[int]) -> list[MarkerHit]:
        """코드 밖, 레지스트리에 있는 번호의 인용 표시 위치."""
        known_set = set(known)
        code = _code_ranges(text)
        return [
            MarkerHit(m.start(), m.end(), int(m.group(1)))
            for m in _MARKER.finditer(text)
            if int(m.group(1)) in known_set and not _inside(code, m.start())
        ]

    @classmethod
    def pairs(cls, text: str, known: Iterable[int]) -> tuple[CitationPair, ...]:
        """문장 × 인용 번호 쌍. 문장에서는 레지스트리 번호 표시만 뺀다."""
        hits = cls.markers(text, known)
        pairs: list[CitationPair] = []
        for start, end in GroundingEditPolicy.sentence_spans(text):
            inside = [h for h in hits if start <= h.start < end]
            if not inside:
                continue
            sentence = _without(text, start, end, inside)
            for marker in dict.fromkeys(h.marker for h in inside):
                pairs.append(CitationPair(f"c{len(pairs) + 1}", marker, sentence))
        return tuple(pairs)

    @staticmethod
    def sentence_key(sentence: str) -> str:
        """판정 문장과 최종 본문 문장을 맞추는 키 — 인용 표시·공백 무시."""
        return _WS.sub("", _MARKER.sub("", sentence))

    @staticmethod
    def strip_all(text: str) -> str:
        """이전 대화 메시지의 인용 표시 제거(D-10). 코드 안은 그대로."""
        return _map_plain(text, lambda segment: _MARKER.sub("", segment))


def _without(text: str, start: int, end: int, hits: list[MarkerHit]) -> str:
    out, cursor = [], start
    for h in hits:
        out.append(text[cursor : h.start])
        cursor = h.end
    out.append(text[cursor:end])
    return "".join(out).strip()


def _code_ranges(text: str) -> list[tuple[int, int]]:
    ranges = [(m.start(), m.end()) for m in _FENCE.finditer(text)]
    ranges += [
        (m.start(), m.end())
        for m in _INLINE.finditer(text)
        if not _inside(ranges, m.start())
    ]
    return sorted(ranges)


def _inside(ranges: list[tuple[int, int]], pos: int) -> bool:
    return any(s <= pos < e for s, e in ranges)


def _map_plain(text: str, fn: Callable[[str], str]) -> str:
    """코드 구간은 그대로 두고 나머지 구간에만 fn 을 적용한다."""
    out, cursor = [], 0
    for start, end in _code_ranges(text):
        out.append(fn(text[cursor:start]))
        out.append(text[start:end])
        cursor = end
    out.append(fn(text[cursor:]))
    return "".join(out)
