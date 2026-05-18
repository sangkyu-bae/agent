# Multi-Query Rewrite Design Document

> **Summary**: LangGraph StateGraph 기반 Multi-Query Rewrite 워크플로우 상세 설계 — 쿼리 분류 → 다관점 쿼리 생성 → 병렬 검색 → RRF 합산
>
> **Project**: sangplusbot (idt)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-05-14
> **Status**: Draft
> **Planning Doc**: [multi-query-rewrite.plan.md](../../01-plan/features/multi-query-rewrite.plan.md)

---

## 1. Overview

### 1.1 Design Goals

1. **검색 재현율(Recall) 향상**: 1개 쿼리 → N개 다관점 쿼리로 확장하여 금융/정책 문서의 다양한 표현을 커버
2. **기존 아키텍처 통합**: Thin DDD 레이어 규칙을 준수하며, 기존 HybridSearchUseCase와 RRFFusionPolicy를 재사용
3. **확장 가능한 전략 구조**: 현재는 Multi-Query, 향후 HyDE/Step-back 등 전략 추가를 고려한 설계
4. **성능 최적화**: asyncio.gather로 병렬 검색, 단순 쿼리는 fast-path로 지연 최소화

### 1.2 Design Principles

- **Single Responsibility**: 각 LangGraph 노드는 하나의 역할만 수행
- **Domain Purity**: 분류 규칙/합산 정책은 domain layer에서 정의, 외부 의존성 없음
- **Graceful Fallback**: LLM 호출 실패 시 원본 쿼리로 fallback, 검색 실패 시 빈 결과 반환
- **기존 코드 최소 변경**: 새 모듈 추가 중심, 기존 코드는 InternalDocumentSearchTool에 옵션 1개 추가만

---

## 2. Architecture

### 2.1 Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         RAG Agent                                │
│  ┌──────────────┐                                                │
│  │ RAGAgentUseCase │──┐                                          │
│  └──────────────┘   │                                            │
│                     ▼                                            │
│  ┌──────────────────────────────┐                                │
│  │ InternalDocumentSearchTool   │                                │
│  │  use_multi_query=True/False  │                                │
│  └──────────┬───────────────────┘                                │
│             │                                                    │
│   ┌─────────▼──────────┐      ┌──────────────────────┐          │
│   │ use_multi_query=T  │      │ use_multi_query=F    │          │
│   │                    │      │ (기존 동작 유지)       │          │
│   ▼                    │      ▼                      │          │
│ ┌────────────────────┐ │ ┌──────────────────────┐    │          │
│ │ MultiQuerySearch   │ │ │ HybridSearchUseCase  │    │          │
│ │ UseCase            │ │ │ (직접 호출)            │    │          │
│ └────────┬───────────┘ │ └──────────────────────┘    │          │
│          │             │                              │          │
│          ▼             │                              │          │
│ ┌──────────────────────────────────────────┐         │          │
│ │     MultiQueryRewriteWorkflow            │         │          │
│ │     (LangGraph StateGraph)               │         │          │
│ │                                          │         │          │
│ │  classify → generate → search → fuse     │         │          │
│ └──────────────────────────────────────────┘         │          │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

```
User Query
    │
    ▼
┌─────────────────────────────────┐
│ 1. classify_query_node          │  Domain Policy 기반 분류
│    (MultiQueryPolicy 호출)       │  → "simple" | "complex" | "ambiguous"
└─────────────┬───────────────────┘
              │
    ┌─────────┴─────────┐
    │                   │
    ▼                   ▼
simple              complex / ambiguous
    │                   │
    ▼                   ▼
┌────────────┐  ┌─────────────────────┐
│ 2a. simple │  │ 2b. generate        │  LLM (gpt-4o-mini)
│ _rewrite   │  │ _queries_node       │  → 3~5개 변형 쿼리 생성
│ _node      │  │ (QueryGenerator     │
│ (기존      │  │  Adapter 호출)       │
│ Rewriter)  │  └─────────┬───────────┘
└─────┬──────┘            │
      │                   ▼
      │           ┌───────────────────┐
      │           │ 3. parallel       │  asyncio.gather로
      │           │ _search_node      │  N개 쿼리 병렬 검색
      │           │ (HybridSearch     │  (HybridSearchUseCase × N)
      │           │  UseCase × N)     │
      │           └───────┬───────────┘
      │                   │
      ├───────────────────┘
      │
      ▼
┌─────────────────────────┐
│ 4. fuse_results_node    │  Cross-Query RRF 합산
│    (MultiQueryFusion    │  → 중복 제거 + 점수 누적
│     Policy 호출)         │  → top_k 반환
└─────────────┬───────────┘
              │
              ▼
        FusedResults
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| MultiQuerySearchUseCase | MultiQueryRewriteWorkflow | 워크플로우 실행 진입점 |
| MultiQueryRewriteWorkflow | HybridSearchUseCase, QueryGeneratorAdapter, MultiQueryPolicy, MultiQueryFusionPolicy | 그래프 노드 실행 |
| MultiQueryRewriteWorkflow | QueryRewriterUseCase (기존) | simple 경로 리라이트 |
| QueryGeneratorAdapter | ChatOpenAI (gpt-4o-mini) | Multi-Query 생성 |
| InternalDocumentSearchTool | MultiQuerySearchUseCase | RAG Agent 연동 |

---

## 3. Data Model

### 3.1 Domain Schemas (`src/domain/multi_query/schemas.py`)

```python
from dataclasses import dataclass, field
from typing import Optional
from typing_extensions import TypedDict

from src.domain.hybrid_search.schemas import HybridSearchResult


# --- LangGraph State ---

class MultiQueryState(TypedDict):
    """LangGraph 워크플로우 State."""

    # Input
    original_query: str
    request_id: str
    top_k: int

    # Classification
    query_type: str  # "simple" | "complex" | "ambiguous"

    # Query Generation
    generated_queries: list[str]

    # Search Results (쿼리별 HybridSearchResult 리스트)
    per_query_results: list[list[HybridSearchResult]]

    # Fused Output
    fused_results: list[HybridSearchResult]

    # Metadata
    errors: list[str]
    status: str  # "classifying" | "generating" | "searching" | "fusing" | "completed" | "failed"


# --- Value Objects ---

@dataclass(frozen=True)
class QueryVariant:
    """생성된 변형 쿼리."""
    query: str
    perspective: str  # 변형 관점 설명 (예: "유사 용어 확장", "구체화")


@dataclass(frozen=True)
class MultiQueryResult:
    """Multi-Query 검색 최종 결과."""
    original_query: str
    query_type: str
    generated_queries: list[str]
    results: list[HybridSearchResult]
    total_found: int
    request_id: str
```

### 3.2 Domain Policy (`src/domain/multi_query/policy.py`)

```python
from dataclasses import dataclass


class MultiQueryPolicy:
    """Multi-Query 생성 관련 도메인 정책."""

    MAX_GENERATED_QUERIES: int = 5
    MIN_GENERATED_QUERIES: int = 3
    DEFAULT_PER_QUERY_TOP_K: int = 5

    COMPLEX_INDICATORS: list[str] = [
        "비교", "차이", "장단점", "vs", "어떤 것",
        "~와 ~의", "관계", "영향",
    ]

    AMBIGUOUS_INDICATORS: list[str] = [
        "이거", "그거", "저거", "그것", "이것", "저것",
        "뭐야", "뭐", "어떻게", "왜",
    ]

    SHORT_QUERY_THRESHOLD: int = 10

    @classmethod
    def classify(cls, query: str) -> str:
        """쿼리를 simple / complex / ambiguous로 분류.

        Returns:
            "simple" | "complex" | "ambiguous"
        """
        stripped = query.strip()

        for indicator in cls.AMBIGUOUS_INDICATORS:
            if indicator in stripped:
                return "ambiguous"

        for indicator in cls.COMPLEX_INDICATORS:
            if indicator in stripped:
                return "complex"

        if len(stripped) <= cls.SHORT_QUERY_THRESHOLD:
            return "ambiguous"

        return "simple"

    @classmethod
    def calculate_per_query_top_k(
        cls, total_top_k: int, query_count: int
    ) -> int:
        """쿼리 수에 따라 개별 검색 top_k 조정.

        총 top_k=10, 쿼리 5개 → 개별 5개씩 검색 → RRF로 10개 선택
        """
        if query_count <= 0:
            return total_top_k
        per_k = max(total_top_k, total_top_k * 2 // query_count)
        return min(per_k, total_top_k * 2)


class MultiQueryFusionPolicy:
    """Cross-Query RRF 합산 정책.

    N개 쿼리의 검색 결과를 단일 랭킹으로 합산한다.
    기존 RRFFusionPolicy(BM25 vs Vector)와 별개로,
    쿼리 간(inter-query) 합산을 수행한다.
    """

    DEFAULT_K: int = 60

    @classmethod
    def fuse(
        cls,
        per_query_results: list[list["HybridSearchResult"]],
        top_k: int,
        k: int = DEFAULT_K,
    ) -> list["HybridSearchResult"]:
        """N개 쿼리 검색 결과를 RRF로 합산.

        각 쿼리 결과 내에서의 rank를 기준으로 RRF 점수를 누적.
        동일 문서(id 기준)가 여러 쿼리에서 나타나면 점수가 높아진다.

        Args:
            per_query_results: 쿼리별 HybridSearchResult 리스트
            top_k: 최종 반환 문서 수
            k: RRF 상수 (기본 60)

        Returns:
            RRF 점수 내림차순 상위 top_k 결과
        """
        scores: dict[str, float] = {}
        doc_map: dict[str, "HybridSearchResult"] = {}

        for query_results in per_query_results:
            for rank, result in enumerate(query_results, start=1):
                rrf_score = 1.0 / (k + rank)
                scores[result.id] = scores.get(result.id, 0.0) + rrf_score
                if result.id not in doc_map or result.score > doc_map[result.id].score:
                    doc_map[result.id] = result

        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

        fused: list["HybridSearchResult"] = []
        for doc_id in sorted_ids[:top_k]:
            original = doc_map[doc_id]
            fused.append(
                HybridSearchResult(
                    id=original.id,
                    content=original.content,
                    score=scores[doc_id],
                    bm25_rank=original.bm25_rank,
                    bm25_score=original.bm25_score,
                    vector_rank=original.vector_rank,
                    vector_score=original.vector_score,
                    source=original.source,
                    metadata=original.metadata,
                )
            )
        return fused
```

---

## 4. API Specification

### 4.1 외부 API 변경 없음

기존 API 엔드포인트(`/api/v1/rag-agent/query`)는 변경하지 않는다.
내부 워크플로우만 교체되므로 프론트엔드 영향 없음.

### 4.2 Internal Interface

#### `MultiQuerySearchUseCase.execute()`

```python
class MultiQuerySearchUseCase:
    """Multi-Query 검색 진입점 UseCase."""

    async def execute(
        self,
        query: str,
        request_id: str,
        top_k: int = 10,
        collection_name: str | None = None,
        es_index: str | None = None,
        metadata_filter: dict[str, str] | None = None,
    ) -> MultiQueryResult:
        """Multi-Query 워크플로우 실행.

        Args:
            query: 원본 사용자 쿼리
            request_id: 요청 추적 ID
            top_k: 최종 반환 문서 수
            collection_name: Qdrant 컬렉션 (optional)
            es_index: ES 인덱스 (optional)
            metadata_filter: 메타데이터 필터 (optional)

        Returns:
            MultiQueryResult (fused 결과 + 메타데이터)
        """
```

---

## 5. UI/UX Design

N/A — 백엔드 내부 워크플로우 변경. 프론트엔드 변경 없음.

---

## 6. Error Handling

### 6.1 에러 시나리오 및 처리

| 시나리오 | 처리 | 노드 |
|---------|------|------|
| LLM Multi-Query 생성 실패 | 원본 쿼리 1개로 fallback 검색 | generate_queries_node |
| LLM 응답 파싱 실패 (structured output) | 원본 쿼리 1개로 fallback | generate_queries_node |
| 개별 Hybrid Search 실패 | 해당 쿼리 결과만 빈 리스트, 나머지는 계속 | parallel_search_node |
| 모든 검색 실패 | 빈 결과 반환, 에러 로그 기록 | parallel_search_node |
| RRF 합산 입력 없음 | 빈 결과 반환 | fuse_results_node |

### 6.2 Fallback Flow

```
generate_queries_node 실패
    │
    ▼
state.generated_queries = [state.original_query]  # 원본 1개로 fallback
state.errors.append("Multi-query generation failed, using original query")
    │
    ▼
parallel_search_node (원본 쿼리 1개로 검색)
    │
    ▼
fuse_results_node (단일 결과 그대로 반환)
```

---

## 7. Security Considerations

- [x] LLM 입력에 사용자 쿼리만 전달 (시스템 프롬프트 주입 방지)
- [x] 생성된 쿼리 길이 검증 (MAX_QUERY_LENGTH=1000, 기존 정책 재사용)
- [x] 병렬 검색 수 제한 (최대 5개, DoS 방지)
- [ ] Rate Limiting: 기존 API 레벨에서 처리 (추가 불필요)

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit Test | MultiQueryPolicy (classify, calculate_per_query_top_k) | pytest |
| Unit Test | MultiQueryFusionPolicy (fuse) | pytest |
| Unit Test | QueryGeneratorAdapter (mock LLM) | pytest + AsyncMock |
| Unit Test | MultiQueryRewriteWorkflow (mock 의존성) | pytest |
| Integration Test | MultiQuerySearchUseCase → HybridSearchUseCase | pytest |

### 8.2 Test Cases (Key)

**Domain Policy Tests** (`tests/domain/multi_query/`):
- [ ] `test_classify_short_query_as_ambiguous`: 10자 이하 → "ambiguous"
- [ ] `test_classify_complex_indicators`: "비교", "차이" 포함 → "complex"
- [ ] `test_classify_ambiguous_indicators`: "이거", "뭐야" 포함 → "ambiguous"
- [ ] `test_classify_normal_query_as_simple`: 충분히 긴 일반 쿼리 → "simple"
- [ ] `test_fusion_single_query_passthrough`: 1개 쿼리 결과 → 그대로 반환
- [ ] `test_fusion_multi_query_dedup`: 3개 쿼리에서 동일 문서 → 점수 누적, 중복 제거
- [ ] `test_fusion_respects_top_k`: top_k=5이면 5개만 반환
- [ ] `test_fusion_empty_results`: 빈 입력 → 빈 출력

**Infrastructure Tests** (`tests/infrastructure/multi_query/`):
- [ ] `test_generate_queries_returns_3_to_5`: LLM이 3~5개 쿼리 생성
- [ ] `test_generate_queries_preserves_intent`: 원본 의도와 변형 쿼리 관련성
- [ ] `test_generate_queries_fallback_on_error`: LLM 실패 → 원본 쿼리 반환

**Application Tests** (`tests/application/multi_query/`):
- [ ] `test_workflow_simple_query_skips_generation`: simple → rewrite → 검색 → 합산
- [ ] `test_workflow_complex_query_generates_multi`: complex → multi-query 생성 → 병렬 검색
- [ ] `test_workflow_parallel_search_gathers`: N개 쿼리가 동시에 검색되는지
- [ ] `test_workflow_llm_failure_fallback`: LLM 실패 시 원본 쿼리로 정상 검색
- [ ] `test_use_case_end_to_end`: UseCase → Workflow → 결과 반환 통합

---

## 9. Clean Architecture

### 9.1 Layer Structure

| Layer | Responsibility | Location |
|-------|---------------|----------|
| **Domain** | State 정의, 분류 정책, 합산 정책, Value Objects | `src/domain/multi_query/` |
| **Application** | LangGraph 워크플로우, UseCase 오케스트레이션 | `src/application/multi_query/` |
| **Infrastructure** | LLM Multi-Query 생성 어댑터, 프롬프트 | `src/infrastructure/multi_query/` |
| **Interfaces** | 변경 없음 (기존 RAG Agent 라우터 사용) | - |

### 9.2 Dependency Rules

```
┌─────────────────────────────────────────────────────────────┐
│                    Dependency Direction                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   Interfaces ──→ Application ──→ Domain ←── Infrastructure  │
│   (변경 없음)         │                                     │
│                       └──→ Infrastructure                   │
│                                                             │
│   ✅ application/multi_query/ → domain/multi_query/         │
│   ✅ application/multi_query/ → infrastructure/multi_query/ │
│   ✅ application/multi_query/ → application/hybrid_search/  │
│   ✅ application/multi_query/ → application/query_rewrite/  │
│   ✅ infrastructure/multi_query/ → domain/multi_query/      │
│   ❌ domain/multi_query/ → infrastructure (금지)             │
│   ❌ domain/multi_query/ → application (금지)                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 9.3 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| MultiQueryState | Domain | `src/domain/multi_query/schemas.py` |
| MultiQueryPolicy | Domain | `src/domain/multi_query/policy.py` |
| MultiQueryFusionPolicy | Domain | `src/domain/multi_query/policy.py` |
| QueryVariant, MultiQueryResult | Domain | `src/domain/multi_query/schemas.py` |
| MultiQueryRewriteWorkflow | Application | `src/application/multi_query/workflow.py` |
| MultiQuerySearchUseCase | Application | `src/application/multi_query/use_case.py` |
| QueryGeneratorAdapter | Infrastructure | `src/infrastructure/multi_query/query_generator_adapter.py` |
| Multi-Query 프롬프트 | Infrastructure | `src/infrastructure/multi_query/prompts.py` |

---

## 10. Coding Convention Reference

### 10.1 Naming Conventions (Python)

| Target | Rule | Example |
|--------|------|---------|
| Module | snake_case | `multi_query`, `query_generator_adapter` |
| Class | PascalCase | `MultiQueryPolicy`, `MultiQueryRewriteWorkflow` |
| Function | snake_case | `classify`, `fuse` |
| LangGraph 노드 | `_xxx_node` | `_classify_query_node`, `_generate_queries_node` |
| Constants | UPPER_SNAKE_CASE | `MAX_GENERATED_QUERIES`, `DEFAULT_K` |
| TypedDict State | PascalCase + "State" 접미사 | `MultiQueryState` |

### 10.2 LangGraph 패턴 (기존 research_agent 기준)

```python
# 노드 함수: state 입력 → state 부분 반환
async def _classify_query_node(self, state: MultiQueryState) -> MultiQueryState:
    # 1. state에서 필요한 값 추출
    # 2. 비즈니스 로직 실행 (Policy 호출)
    # 3. 변경된 필드만 포함한 dict 반환
    return {**state, "query_type": result, "status": "classifying"}

# 조건부 엣지: state → 다음 노드 이름(str) 반환
def _after_classify(self, state: MultiQueryState) -> str:
    if state["query_type"] == "simple":
        return "simple_rewrite"
    return "generate_queries"
```

### 10.3 This Feature's Conventions

| Item | Convention Applied |
|------|-------------------|
| Logger | `get_logger(__name__)` — 모든 노드에서 request_id 포함 로깅 |
| Error Handling | try-except + logger.error + state["errors"].append |
| State Update | `{**state, "changed_field": value}` 패턴 |
| DI | 생성자 주입, 기존 `main.py` 의존성 팩토리 패턴 따름 |

---

## 11. Implementation Guide

### 11.1 File Structure

```
src/
├── domain/
│   └── multi_query/
│       ├── __init__.py
│       ├── schemas.py              # MultiQueryState, QueryVariant, MultiQueryResult
│       └── policy.py               # MultiQueryPolicy, MultiQueryFusionPolicy
│
├── application/
│   └── multi_query/
│       ├── __init__.py
│       ├── workflow.py             # MultiQueryRewriteWorkflow (LangGraph)
│       └── use_case.py             # MultiQuerySearchUseCase
│
├── infrastructure/
│   └── multi_query/
│       ├── __init__.py
│       ├── query_generator_adapter.py  # LLM Multi-Query 생성
│       ├── prompts.py              # 프롬프트 템플릿
│       └── schemas.py              # MultiQueryGeneratorOutput (structured output)
│
└── application/
    └── rag_agent/
        └── tools.py                # InternalDocumentSearchTool 수정 (옵션 추가)
```

### 11.2 Implementation Order

#### Step 1: Domain Layer (테스트 먼저)
1. [ ] `tests/domain/multi_query/test_policy.py` — 분류/합산 정책 테스트 작성
2. [ ] `src/domain/multi_query/schemas.py` — MultiQueryState, QueryVariant, MultiQueryResult
3. [ ] `src/domain/multi_query/policy.py` — MultiQueryPolicy, MultiQueryFusionPolicy
4. [ ] 테스트 통과 확인

#### Step 2: Infrastructure Layer (테스트 먼저)
5. [ ] `tests/infrastructure/multi_query/test_query_generator_adapter.py` — mock LLM 테스트
6. [ ] `src/infrastructure/multi_query/prompts.py` — 금융 도메인 특화 프롬프트
7. [ ] `src/infrastructure/multi_query/schemas.py` — structured output 스키마
8. [ ] `src/infrastructure/multi_query/query_generator_adapter.py` — LLM 어댑터
9. [ ] 테스트 통과 확인

#### Step 3: Application Layer (테스트 먼저)
10. [ ] `tests/application/multi_query/test_workflow.py` — 워크플로우 테스트
11. [ ] `src/application/multi_query/workflow.py` — LangGraph StateGraph
12. [ ] `tests/application/multi_query/test_use_case.py` — UseCase 테스트
13. [ ] `src/application/multi_query/use_case.py` — UseCase
14. [ ] 테스트 통과 확인

#### Step 4: Integration
15. [ ] `src/application/rag_agent/tools.py` — `use_multi_query` 필드 추가
16. [ ] `src/application/rag_agent/use_case.py` — MultiQuerySearchUseCase DI 주입
17. [ ] 기존 RAG Agent 테스트 회귀 확인

### 11.3 LangGraph Workflow 상세 (`workflow.py`)

```python
class MultiQueryRewriteWorkflow:
    """LangGraph StateGraph 기반 Multi-Query Rewrite 워크플로우."""

    def __init__(
        self,
        query_generator: QueryGeneratorAdapter,
        hybrid_search: HybridSearchUseCase,
        query_rewriter: QueryRewriterUseCase,
        logger: LoggerInterface,
        collection_name: str | None = None,
        es_index: str | None = None,
        metadata_filter: dict[str, str] | None = None,
    ) -> None:
        self._query_generator = query_generator
        self._hybrid_search = hybrid_search
        self._query_rewriter = query_rewriter
        self._logger = logger
        self._collection_name = collection_name
        self._es_index = es_index
        self._metadata_filter = metadata_filter or {}
        self._graph = self._build_graph()

    def _build_graph(self) -> CompiledGraph:
        workflow = StateGraph(MultiQueryState)

        workflow.add_node("classify_query", self._classify_query_node)
        workflow.add_node("simple_rewrite", self._simple_rewrite_node)
        workflow.add_node("generate_queries", self._generate_queries_node)
        workflow.add_node("parallel_search", self._parallel_search_node)
        workflow.add_node("fuse_results", self._fuse_results_node)

        workflow.set_entry_point("classify_query")

        workflow.add_conditional_edges(
            "classify_query",
            self._after_classify,
            {
                "simple_rewrite": "simple_rewrite",
                "generate_queries": "generate_queries",
            },
        )

        workflow.add_edge("simple_rewrite", "parallel_search")
        workflow.add_edge("generate_queries", "parallel_search")
        workflow.add_edge("parallel_search", "fuse_results")
        workflow.add_edge("fuse_results", END)

        return workflow.compile()
```

### 11.4 Multi-Query 생성 프롬프트 (`prompts.py`)

```python
MULTI_QUERY_SYSTEM_PROMPT = """당신은 한국 금융·정책 문서 검색 최적화 전문가입니다.

사용자의 질문을 받아 검색에 효과적인 3~5개의 변형 쿼리를 생성하세요.

각 변형 쿼리는 다른 관점에서 같은 정보를 찾을 수 있도록 해야 합니다:
1. 유사 용어 확장: 동의어, 전문 용어, 약어 등 대체 표현
2. 구체화: 더 구체적인 조건이나 맥락 추가
3. 추상화: 더 넓은 범위의 상위 개념으로 확장
4. 관점 전환: 다른 이해관계자나 시각에서의 질문

예시:
입력: "적금 금리"
출력:
- "저축은행 정기적금 이자율 현황"
- "적금 상품 금리 비교 2024년"
- "예적금 이율 변동 추이"
- "적금 가입 시 우대 금리 조건"

입력: "대출 한도"
출력:
- "여신 한도 산정 기준"
- "개인 신용대출 최대 대출 가능 금액"
- "대출 한도 증액 조건 및 절차"
- "DTI DSR 기반 대출 한도 계산"
"""

MULTI_QUERY_HUMAN_TEMPLATE = """원본 질문: {query}

위 질문에 대해 검색 최적화된 변형 쿼리 {num_queries}개를 생성하세요."""
```

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-14 | Initial draft | 배상규 |
