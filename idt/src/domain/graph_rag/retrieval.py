"""그래프 검색 도메인 — 연결·탐색 결과 VO 와 점수 정책.

Design Ref: graph-rag-foundation §2.2(검색)·§11.9(주제 범위), Plan FR-12~14·FR-29.
흐름: 질문 주제(범위) → 엔티티 연결(Kiwi 명사 묶음 정확·별칭 일치 + 질문 벡터)
 → 최대 N단계 탐색(허브 노드는 지나가지 않음) → 근거 청크 점수 → ES 권한 재조회.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.domain.graph_rag.extraction import NameNormalizer

MAX_SEEDS = 5
MAX_GRAPH_CHUNKS = 50
MAX_PATHS = 200
MAX_HOPS_LIMIT = 3
# 이보다 관계가 많은 엔티티는 경유하지 않는다
# (문서 제목 엔티티가 문서 전체로 퍼지는 것 방지).
HUB_DEGREE_LIMIT = 15
MAX_PHRASE_TOKENS = 3
SEED_MENTION_SCORE = 1.0


@dataclass(frozen=True)
class LinkedEntity:
    id: str
    name: str
    type: str
    via: str  # exact | alias | vector
    score: float


@dataclass(frozen=True)
class PathHit:
    """씨앗에서 시작한 경로 하나 — 관계마다 근거 청크가 있다."""

    names: tuple[str, ...]
    rel_types: tuple[str, ...]
    evidence_chunk_ids: tuple[str, ...]

    @property
    def hops(self) -> int:
        return len(self.rel_types)

    def label(self) -> list[str]:
        out = [self.names[0]]
        for rel, name in zip(self.rel_types, self.names[1:], strict=False):
            out += [f"{rel}→", name]
        return out


@dataclass(frozen=True)
class QueryScope:
    """질문 주제 판정 결과 — topic_ids 가 None 이면 범위를 좁히지 않는다."""

    topic_ids: tuple[str, ...] | None = None
    topic_names: tuple[str, ...] = ()
    decided_by: str = "none"  # jev | llm | cache | none
    reason: str | None = None


@dataclass
class GraphSearchTrace:
    """검색 한 번의 과정 — 관리자 검색 테스트 화면에 그대로 보여 준다."""

    scope: QueryScope = field(default_factory=QueryScope)
    linked: list[LinkedEntity] = field(default_factory=list)
    paths: list[PathHit] = field(default_factory=list)
    chunk_scores: list[tuple[str, float]] = field(default_factory=list)
    hits: list = field(default_factory=list)  # HybridSearchResult
    filtered_out: int = 0
    timings_ms: dict[str, int] = field(default_factory=dict)
    skip_reason: str | None = None


class RetrievalPolicy:
    @staticmethod
    def phrases(nouns: list[str]) -> list[str]:
        """연속 명사 1~3개 묶음 — 붙여 쓴 형태와 띄어 쓴 형태 모두(정규화)."""
        tokens = [n.strip() for n in nouns if n and n.strip()]
        out: list[str] = []
        for size in range(MAX_PHRASE_TOKENS, 0, -1):
            for i in range(len(tokens) - size + 1):
                part = tokens[i : i + size]
                if size == 1 and len(part[0]) < 2:
                    continue
                for text in ("".join(part), " ".join(part)):
                    key = NameNormalizer.normalize(text)
                    if key and key not in out:
                        out.append(key)
        return out

    @staticmethod
    def hops(value: int) -> int:
        if not 1 <= int(value) <= MAX_HOPS_LIMIT:
            raise ValueError(f"max_hops must be 1..{MAX_HOPS_LIMIT}")
        return int(value)

    @staticmethod
    def chunk_scores(
        seed_mentions: dict[str, int], paths: list[PathHit]
    ) -> dict[str, float]:
        """씨앗 언급 청크 1.0, 깊이 d 관계의 근거 청크 1/(1+d) 를 더한다."""
        scores: dict[str, float] = {cid: SEED_MENTION_SCORE for cid in seed_mentions}
        for p in paths:
            for depth, cid in enumerate(p.evidence_chunk_ids, start=1):
                if cid:
                    scores[cid] = scores.get(cid, 0.0) + 1.0 / (1 + depth)
        return scores

    @staticmethod
    def ranked(scores: dict[str, float]) -> list[tuple[str, float]]:
        return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:MAX_GRAPH_CHUNKS]
