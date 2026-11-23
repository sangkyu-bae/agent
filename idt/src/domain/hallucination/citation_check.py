"""인용 검증 VO — 근거 판정 포트가 쓰는 입력·출력.

Design Ref: answer-citation-verification §3.1 — 판정 포트(domain/hallucination)는
인용 모듈(answer_citation)을 모른다. 인용 모듈을 떼어도 판정기는 그대로 컴파일된다.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CitationPair:
    """답변 문장 1개 × 인용 번호 1개."""

    pair_id: str  # "c1", "c2" …
    marker: int  # 실행 단위 레지스트리 번호
    sentence: str  # 인용 표시를 뺀 답변 문장


@dataclass(frozen=True)
class CitationCheckRequest:
    pairs: tuple[CitationPair, ...]
    # 번호 → 청크 본문(답변 모델이 본 그대로). 인용된 청크만 싣는다(Design D-03).
    cited_sources: Mapping[int, str] = field(default_factory=dict)

    @property
    def empty(self) -> bool:
        return not self.pairs


@dataclass(frozen=True)
class CitationCheck:
    pair_id: str
    supported: bool
    evidence: str = ""  # 판정기가 청크에서 그대로 복사한 근거 문장
