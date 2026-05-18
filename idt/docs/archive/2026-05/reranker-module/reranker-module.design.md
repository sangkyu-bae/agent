# reranker-module Design Document

> **Summary**: Lost in the Middle 대응 Reranker 독립 모듈 상세 설계 — 도메인 인터페이스 + PositionalReranker 알고리즘
>
> **Project**: sangplusbot (idt)
> **Author**: 배상규
> **Date**: 2026-05-13
> **Status**: Draft
> **Planning Doc**: [reranker-module.plan.md](../../01-plan/features/reranker-module.plan.md)

---

## 1. Overview

### 1.1 Design Goals

1. `RerankerInterface` ABC로 전략 패턴 정의 — 구현체 교체만으로 reranking 전략 변경
2. `PositionalReranker`를 순수 도메인 정책으로 구현 — 외부 의존성 0, O(n) 성능
3. 기존 `HybridSearchUseCase`, `RAGAgentUseCase` 코드 변경 없이 독립 모듈로 존재
4. `rerank_candidates` 파라미터로 후보군 크기 조절 가능 — 유연한 성능/정확도 트레이드오프

### 1.2 Design Principles

- **Strategy Pattern**: `RerankerInterface` 하나의 계약으로 PositionalReranker(1단계) → CohereReranker(2단계) 무중단 교체
- **Domain Purity**: PositionalReranker는 순수 Python 로직, 외부 라이브러리/API 호출 없음
- **Zero Side Effect**: 기존 파이프라인에 영향 없는 독립 모듈 — 통합은 별도 작업으로 분리

---

## 2. Architecture

### 2.1 모듈 위치 (Thin DDD Layers)

```
src/
├── domain/
│   └── reranker/                     ← 신규 도메인 모듈
│       ├── __init__.py
│       ├── interfaces.py             ← RerankerInterface (ABC)
│       ├── schemas.py                ← RerankableDocument, RerankerRequest, RerankerResponse
│       └── policies.py              ← PositionalReranker (순수 도메인 정책)
│
├── infrastructure/
│   └── reranker/                     ← 2단계 확장점 (이번 스코프: 빈 모듈)
│       └── __init__.py
│
└── application/
    └── (변경 없음 — 통합은 별도 작업)

tests/
└── domain/
    └── reranker/                     ← 신규 테스트
        ├── __init__.py
        ├── test_schemas.py
        └── test_policies.py
```

### 2.2 현행 파이프라인 (변경 없음)

```
Query → BM25(ES) + Vector(Qdrant) → RRF Fusion → top_k → LLM
         ↑ _fetch_bm25()              ↑ RRFFusionPolicy.merge()
         ↑ _fetch_vector()
```

### 2.3 목표 파이프라인 (추후 통합 시)

```
Query → BM25 + Vector → RRF Fusion → Reranker → top_k → LLM
                                       ↑
                              RerankerInterface.rerank()
                              (PositionalReranker 또는 CohereReranker)
```

### 2.4 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `RerankerInterface` | `abc.ABC` | 추상 인터페이스 정의 |
| `PositionalReranker` | `RerankerInterface`, `schemas` | 양끝 배치 알고리즘 구현 |
| `schemas` | `dataclasses` | 순수 도메인 VO (외부 의존성 없음) |

---

## 3. Data Model

### 3.1 RerankableDocument

```python
# src/domain/reranker/schemas.py

@dataclass(frozen=True)
class RerankableDocument:
    """Reranking 대상 문서. HybridSearchResult와 1:1 대응."""

    id: str
    content: str
    score: float
    metadata: dict[str, str] = field(default_factory=dict)
```

**설계 결정**: `HybridSearchResult`를 직접 참조하지 않고 별도 VO를 정의한다.
- Reranker 모듈은 hybrid_search에 의존하면 안 됨 (독립 도메인)
- 추후 다른 검색 소스(vector only, BM25 only)에서도 사용 가능
- 변환은 통합 시점에 application 레이어에서 수행

### 3.2 RerankerRequest

```python
@dataclass(frozen=True)
class RerankerRequest:
    """Reranker 호출 요청."""

    query: str
    documents: list[RerankableDocument]
    top_k: int = 5
    rerank_candidates: int | None = None  # None이면 documents 전체 사용
```

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `query` | str | (필수) | 원본 검색 쿼리 — 2단계 API Reranker에서 query-document relevance 계산에 사용 |
| `documents` | list[RerankableDocument] | (필수) | reranking 대상 문서 목록 (score 순 정렬 기대) |
| `top_k` | int | 5 | 최종 반환할 문서 수 |
| `rerank_candidates` | int \| None | None | reranking에 사용할 최대 후보 수. None이면 전체 사용 |

**`rerank_candidates` 동작**:
```
documents = [d1, d2, d3, d4, d5, d6, d7, d8, d9, d10]  (10개)
rerank_candidates = 6  →  [d1, d2, d3, d4, d5, d6] 만 reranking
top_k = 3  →  reranking 결과에서 상위 3개 반환
```

### 3.3 RerankerResponse

```python
@dataclass(frozen=True)
class RerankerResponse:
    """Reranker 처리 결과."""

    documents: list[RerankableDocument]
    strategy: str  # "positional", "cohere", "jina", "cross_encoder"
    original_count: int
    reranked_count: int
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `documents` | list[RerankableDocument] | 재배치된 문서 목록 (최대 top_k개) |
| `strategy` | str | 사용된 전략 이름 (로깅/디버깅용) |
| `original_count` | int | 입력 문서 총 수 |
| `reranked_count` | int | 실제 reranking 처리된 문서 수 |

---

## 4. Component Specification

### 4.1 RerankerInterface

```python
# src/domain/reranker/interfaces.py

from abc import ABC, abstractmethod
from src.domain.reranker.schemas import RerankerRequest, RerankerResponse


class RerankerInterface(ABC):
    """Reranker 전략 인터페이스.

    구현체:
    - PositionalReranker (domain/policies.py) — 코드 기반 양끝 배치
    - CohereReranker (infrastructure/) — Cohere Rerank API (추후)
    - JinaReranker (infrastructure/) — Jina Reranker API (추후)
    - CrossEncoderReranker (infrastructure/) — 로컬 모델 (추후)
    """

    @abstractmethod
    async def rerank(self, request: RerankerRequest) -> RerankerResponse:
        """문서를 reranking하여 재배치된 결과를 반환한다.

        Args:
            request: 쿼리, 문서 목록, top_k, 후보군 크기

        Returns:
            재배치된 문서 목록 + 메타데이터
        """
        ...
```

**비동기 인터페이스 선택 이유**:
- 1단계 PositionalReranker는 동기 로직이지만 `async`로 정의
- 2단계 API Reranker(Cohere, Jina)는 HTTP 호출 필요 → `async` 필수
- 인터페이스를 `async`로 통일하여 구현체 교체 시 호출부 변경 불필요

### 4.2 PositionalReranker

```python
# src/domain/reranker/policies.py

from src.domain.reranker.interfaces import RerankerInterface
from src.domain.reranker.schemas import (
    RerankableDocument,
    RerankerRequest,
    RerankerResponse,
)


class PositionalReranker(RerankerInterface):
    """양끝 우선 배치(Alternating Ends) 전략으로 문서를 재배치한다.

    Lost in the Middle (Liu et al., 2023) 대응:
    관련도 상위 문서를 LLM이 잘 읽는 시작/끝에 배치하고,
    관련도 하위 문서를 중간에 배치한다.
    """

    STRATEGY_NAME: str = "positional"

    async def rerank(self, request: RerankerRequest) -> RerankerResponse:
        documents = request.documents
        original_count = len(documents)

        if original_count <= 1:
            return RerankerResponse(
                documents=documents[:request.top_k],
                strategy=self.STRATEGY_NAME,
                original_count=original_count,
                reranked_count=original_count,
            )

        candidates = self._select_candidates(documents, request.rerank_candidates)
        reordered = self._alternating_ends(candidates)
        final = reordered[:request.top_k]

        return RerankerResponse(
            documents=final,
            strategy=self.STRATEGY_NAME,
            original_count=original_count,
            reranked_count=len(candidates),
        )

    def _select_candidates(
        self,
        documents: list[RerankableDocument],
        rerank_candidates: int | None,
    ) -> list[RerankableDocument]:
        """rerank_candidates 수만큼 상위 문서를 선택한다."""
        if rerank_candidates is None or rerank_candidates >= len(documents):
            return list(documents)
        return list(documents[:rerank_candidates])

    def _alternating_ends(
        self, documents: list[RerankableDocument],
    ) -> list[RerankableDocument]:
        """양끝 우선 배치 알고리즘.

        입력 (score 순): [1등, 2등, 3등, 4등, 5등]
        출력 (위치 순): [1등, 3등, 5등, 4등, 2등]

        홀수 인덱스(0,2,4,...) → 시작부터 채움
        짝수 인덱스(1,3,5,...) → 끝부터 채움
        """
        n = len(documents)
        result: list[RerankableDocument | None] = [None] * n

        left = 0
        right = n - 1

        for i, doc in enumerate(documents):
            if i % 2 == 0:
                result[left] = doc
                left += 1
            else:
                result[right] = doc
                right -= 1

        return [doc for doc in result if doc is not None]
```

### 4.3 알고리즘 상세: `_alternating_ends`

**입력**: score 기준 내림차순 정렬된 문서 리스트

**배치 규칙**:
```
인덱스 0 (1등, 최고 관련도) → 배열 시작 (left=0)
인덱스 1 (2등)             → 배열 끝 (right=n-1)
인덱스 2 (3등)             → 배열 시작+1 (left=1)
인덱스 3 (4등)             → 배열 끝-1 (right=n-2)
인덱스 4 (5등)             → 배열 시작+2 (left=2)  ← 중간
```

**예시 (5개 문서)**:
```
입력: [A(0.95), B(0.90), C(0.85), D(0.80), E(0.75)]
        1등       2등       3등       4등       5등

Step 0: i=0 (A), left=0  → result[0] = A     [A, _, _, _, _]
Step 1: i=1 (B), right=4 → result[4] = B     [A, _, _, _, B]
Step 2: i=2 (C), left=1  → result[1] = C     [A, C, _, _, B]
Step 3: i=3 (D), right=3 → result[3] = D     [A, C, _, D, B]
Step 4: i=4 (E), left=2  → result[2] = E     [A, C, E, D, B]

출력: [A(0.95), C(0.85), E(0.75), D(0.80), B(0.90)]
       시작(1등)                              끝(2등)
```

**LLM 시선 분포와 매핑**:
```
위치:    [시작]  [시작+1]  [중간]  [끝-1]  [끝]
관련도:   1등     3등      5등     4등     2등
LLM주의:  ★★★    ★★      ★       ★★     ★★★
```

→ 1등, 2등(가장 관련도 높은 문서)이 LLM 주의도가 가장 높은 시작/끝에 배치됨

**예시 (6개 문서)**:
```
입력: [A, B, C, D, E, F]  (score 순)
출력: [A, C, E, F, D, B]

위치:    시작  시작+1  중간-1  중간  끝-1   끝
관련도:  1등    3등    5등    6등   4등    2등
```

### 4.4 Edge Cases 처리

| 케이스 | 입력 | 동작 | 출력 |
|--------|------|------|------|
| 빈 목록 | `documents=[]` | 즉시 반환 | `documents=[], reranked_count=0` |
| 1개 문서 | `documents=[A]` | 재배치 불필요, 그대로 반환 | `documents=[A], reranked_count=1` |
| 2개 문서 | `documents=[A, B]` | A→시작, B→끝 | `documents=[A, B]` (변화 없음, 정상) |
| `top_k > len(documents)` | `top_k=10, documents=5개` | 전체 반환 | `documents=5개 전부` |
| `rerank_candidates < top_k` | `candidates=3, top_k=5` | 3개만 reranking, 3개 반환 | `documents=3개` |
| `rerank_candidates = None` | 전체 문서 대상 | documents 전체 reranking | 정상 동작 |

---

## 5. Error Handling

### 5.1 PositionalReranker 에러

| 상황 | 처리 |
|------|------|
| `documents`가 빈 리스트 | 빈 `RerankerResponse` 반환 (예외 아님) |
| `top_k <= 0` | 빈 결과 반환 (슬라이싱 `[:0]` = 빈 리스트) |
| `rerank_candidates <= 0` | 빈 결과 반환 |
| 문서 score가 동일 | 입력 순서 유지 (stable) — 알고리즘이 인덱스 기반이므로 자연스럽게 안정 정렬 |

### 5.2 2단계 확장 시 에러 (설계 예약)

| 상황 | 처리 |
|------|------|
| API 호출 실패 (Cohere/Jina) | fallback으로 `PositionalReranker` 사용 또는 원본 순서 유지 |
| API 타임아웃 | 설정 가능한 timeout + fallback |
| 모델 로딩 실패 (Cross-Encoder) | 에러 로깅 + 원본 순서 유지 |

---

## 6. Test Plan

### 6.1 Test Scope

| Type | Target | 파일 |
|------|--------|------|
| Unit | `RerankableDocument` 생성 | `tests/domain/reranker/test_schemas.py` |
| Unit | `RerankerRequest` 생성/유효성 | `tests/domain/reranker/test_schemas.py` |
| Unit | `RerankerResponse` 생성 | `tests/domain/reranker/test_schemas.py` |
| Unit | `PositionalReranker.rerank()` 정상 동작 | `tests/domain/reranker/test_policies.py` |
| Unit | `PositionalReranker._alternating_ends()` 알고리즘 | `tests/domain/reranker/test_policies.py` |
| Unit | `PositionalReranker` edge cases | `tests/domain/reranker/test_policies.py` |
| Unit | `RerankerInterface` ABC 준수 | `tests/domain/reranker/test_policies.py` |

### 6.2 Test Cases

#### 스키마 테스트 (`test_schemas.py`)

| ID | 테스트 | 검증 내용 |
|----|--------|----------|
| TC-S01 | `RerankableDocument` 생성 | id, content, score, metadata 설정 정상 |
| TC-S02 | `RerankableDocument` frozen | 불변성 확인 (FrozenInstanceError) |
| TC-S03 | `RerankableDocument` 기본 metadata | `metadata={}` 기본값 |
| TC-S04 | `RerankerRequest` 기본값 | `top_k=5`, `rerank_candidates=None` |
| TC-S05 | `RerankerRequest` 커스텀 파라미터 | `top_k=10`, `rerank_candidates=20` |
| TC-S06 | `RerankerResponse` 생성 | 모든 필드 정상 설정 |

#### 정책 테스트 (`test_policies.py`)

| ID | 테스트 | 입력 | 기대 출력 |
|----|--------|------|----------|
| TC-P01 | 5개 문서 양끝 배치 | `[A, B, C, D, E]` score순 | `[A, C, E, D, B]` |
| TC-P02 | 6개 문서 양끝 배치 | `[A, B, C, D, E, F]` score순 | `[A, C, E, F, D, B]` |
| TC-P03 | 3개 문서 양끝 배치 | `[A, B, C]` | `[A, C, B]` |
| TC-P04 | 빈 목록 | `[]` | `documents=[], reranked_count=0` |
| TC-P05 | 1개 문서 | `[A]` | `documents=[A], reranked_count=1` |
| TC-P06 | 2개 문서 | `[A, B]` | `[A, B]` (순서 유지) |
| TC-P07 | `top_k` 적용 | 5개 입력, `top_k=3` | 3개만 반환 |
| TC-P08 | `rerank_candidates` 적용 | 10개 입력, `candidates=5` | 5개만 reranking |
| TC-P09 | `rerank_candidates > len(docs)` | 3개 입력, `candidates=10` | 3개 전체 reranking |
| TC-P10 | `top_k > len(docs)` | 3개 입력, `top_k=10` | 3개 전체 반환 |
| TC-P11 | `strategy` 필드 값 | 모든 호출 | `"positional"` |
| TC-P12 | 문서 누락/중복 없음 | 임의 N개 입력 | 입력 문서 전부 출력에 포함 (set 비교) |
| TC-P13 | `RerankerInterface` ABC 준수 | `isinstance(PositionalReranker(), RerankerInterface)` | `True` |
| TC-P14 | `original_count`/`reranked_count` 정확성 | 10개 입력, candidates=6 | `original=10, reranked=6` |

---

## 7. Clean Architecture Layer Assignment

### 7.1 Dependency Rules 준수

```
domain/reranker/ (신규)
  └── interfaces.py: RerankerInterface (ABC) — abc 모듈만 사용
  └── schemas.py: RerankableDocument, Request, Response — dataclasses만 사용
  └── policies.py: PositionalReranker — interfaces + schemas만 참조
  ※ 외부 의존성 완전 0 — 순수 Python stdlib만 사용

infrastructure/reranker/ (2단계 예약)
  └── __init__.py: 빈 모듈
  ※ 추후 CohereReranker 등이 domain/reranker/interfaces.py를 import
  ※ infrastructure → domain 참조: 정당한 의존 방향
```

### 7.2 Layer 위반 없음 확인

| 모듈 | Import | From → To | 위반 여부 |
|------|--------|-----------|----------|
| `policies.py` → `interfaces.py` | domain → domain | **정당** |
| `policies.py` → `schemas.py` | domain → domain | **정당** |
| `schemas.py` → (없음) | 자체 완결 | **정당** |
| `interfaces.py` → `schemas.py` | domain → domain | **정당** |

### 7.3 기존 코드 변경 없음 확인

| 기존 모듈 | 변경 | 이유 |
|-----------|------|------|
| `hybrid_search/use_case.py` | 없음 | 통합은 별도 작업 |
| `hybrid_search/policies.py` | 없음 | RRF 로직 유지 |
| `hybrid_search/schemas.py` | 없음 | 별도 VO 사용 |
| `rag_agent/use_case.py` | 없음 | 통합은 별도 작업 |
| `rag_agent/tools.py` | 없음 | 통합은 별도 작업 |

---

## 8. Implementation Order

### Step 1: Domain 스키마 정의 (TDD)

```
Red:   test_schemas.py — TC-S01~S06
Green: schemas.py — RerankableDocument, RerankerRequest, RerankerResponse
```

변경 파일:
- `src/domain/reranker/__init__.py` (신규)
- `src/domain/reranker/schemas.py` (신규)
- `tests/domain/reranker/__init__.py` (신규)
- `tests/domain/reranker/test_schemas.py` (신규)

### Step 2: Domain 인터페이스 정의

```
interfaces.py — RerankerInterface(ABC) 정의
TC-P13에서 ABC 준수 검증 (Step 3에서 함께 테스트)
```

변경 파일:
- `src/domain/reranker/interfaces.py` (신규)

### Step 3: PositionalReranker 구현 (TDD)

```
Red:   test_policies.py — TC-P01~P14
Green: policies.py — PositionalReranker 구현
```

변경 파일:
- `src/domain/reranker/policies.py` (신규)
- `tests/domain/reranker/test_policies.py` (신규)

### Step 4: Infrastructure 확장점 준비

```
infrastructure/reranker/__init__.py — 빈 모듈 생성
```

변경 파일:
- `src/infrastructure/reranker/__init__.py` (신규)

---

## 9. 추후 통합 설계 (참고)

### 9.1 HybridSearchUseCase 통합 방안

```python
# 추후 통합 시 변경 예시 (이번 스코프 아님)

class HybridSearchUseCase:
    def __init__(
        self,
        es_repo: ElasticsearchRepositoryInterface,
        embedding: EmbeddingInterface,
        vector_store: VectorStoreInterface,
        es_index: str,
        logger: LoggerInterface,
        reranker: RerankerInterface | None = None,  # 선택적 주입
    ) -> None:
        ...
        self._reranker = reranker

    async def execute(self, request, request_id) -> HybridSearchResponse:
        ...
        results = self._rrf_policy.merge(bm25_hits, vector_hits, ...)

        if self._reranker:
            rerank_request = RerankerRequest(
                query=request.query,
                documents=[
                    RerankableDocument(
                        id=r.id, content=r.content,
                        score=r.score, metadata=r.metadata,
                    )
                    for r in results
                ],
                top_k=request.top_k,
                rerank_candidates=request.rerank_candidates,
            )
            rerank_response = await self._reranker.rerank(rerank_request)
            # RerankableDocument → HybridSearchResult 변환
            ...

        return HybridSearchResponse(...)
```

### 9.2 2단계 Infrastructure 구현체 예시

```python
# infrastructure/reranker/cohere_reranker.py (추후)

class CohereReranker(RerankerInterface):
    STRATEGY_NAME = "cohere"

    def __init__(self, api_key: str, model: str = "rerank-v3.5"):
        self._client = cohere.AsyncClient(api_key)
        self._model = model

    async def rerank(self, request: RerankerRequest) -> RerankerResponse:
        response = await self._client.rerank(
            model=self._model,
            query=request.query,
            documents=[doc.content for doc in request.documents],
            top_n=request.top_k,
        )
        reranked = [request.documents[r.index] for r in response.results]
        return RerankerResponse(
            documents=reranked,
            strategy=self.STRATEGY_NAME,
            original_count=len(request.documents),
            reranked_count=len(reranked),
        )
```

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-13 | Initial draft | 배상규 |
