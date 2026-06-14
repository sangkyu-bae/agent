# RAG Score Threshold Filter Design Document

> **Summary**: 하이브리드 검색의 벡터 코사인 유사도(0~1)가 임계값 미만인 hit을 RRF 병합 전에 컷오프한다. 임계값은 `config.py` 전역 기본값 + `RagToolConfig` 에이전트별 주입으로 관리한다.
>
> **Project**: sangplusbot (idt)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-06-03
> **Status**: Draft
> **Planning Doc**: [rag-score-threshold-filter.plan.md](../../01-plan/features/rag-score-threshold-filter.plan.md)

### Pipeline References (if applicable)

| Phase | Document | Status |
|-------|----------|--------|
| Phase 1 | Schema Definition | N/A (기존 스키마 확장) |
| Phase 2 | Coding Conventions | ✅ (CLAUDE.md + docs/rules/) |
| Phase 3 | Mockup | N/A (백엔드 내부) |
| Phase 4 | API Spec | N/A (외부 API 불변) |

---

## 1. Overview

### 1.1 Design Goals

1. **검색 품질 게이트**: 벡터 코사인 유사도가 낮은(질문과 무관한) 문서를 RRF 병합 **이전**에 제거하여 "터무니없는 문서" 혼입을 차단한다.
2. **운영 중 조정 가능성**: 임계값을 코드 변경 없이 전역 env + 에이전트별 `tool_config`로 주입/변경할 수 있게 한다.
3. **무회귀 기본값**: 기본 임계값 `0.0`(비활성)으로 기존 모든 에이전트 동작을 100% 보존한다.
4. **최소 변경**: 신규 모듈/레이어 없이 기존 6개 파일만 확장하여 Thin DDD 구조를 유지한다.

### 1.2 Design Principles

- **Domain Purity**: 임계값 검증 규칙은 domain(`RagToolConfig`)에, 필터 파라미터는 domain 스키마(`HybridSearchRequest`)에 둔다. 외부 의존성 없음.
- **Single Filter Point**: 컷오프는 `HybridSearchUseCase._fetch_vector` 한 곳에서만 수행한다 (BM25 미적용, RRF 후 미적용).
- **Backward Compatible**: 모든 신규 필드는 기본값(`None`/`0.0`)을 가지며, 미주입 시 기존 흐름과 동일.
- **Defense by Default**: 잘못된 임계값(범위 밖)은 `RagToolConfig.__post_init__`에서 생성 시점에 차단.

---

## 2. Architecture

### 2.1 Component Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│  [설정 주입 경로]                                                       │
│                                                                        │
│  config.py (Settings)                                                  │
│    rag_vector_score_threshold: float = 0.0  ◄── env RAG_VECTOR_SCORE_THRESHOLD │
│         │                                                              │
│         ▼                                                              │
│  ToolFactory.create(tool_id, tool_config)                             │
│    rag_config = _parse_rag_config(tool_config)                        │
│    threshold = rag_config.score_threshold                             │
│                if rag_config.score_threshold is not None              │
│                else settings.rag_vector_score_threshold   ◄── fallback│
│         │                                                              │
│         ▼                                                              │
│  InternalDocumentSearchTool(score_threshold=threshold)                │
└──────────────────────────────────────────────────────────────────────┘
                          │
                          ▼  (검색 실행)
┌──────────────────────────────────────────────────────────────────────┐
│  [검색 실행 경로]                                                       │
│                                                                        │
│  InternalDocumentSearchTool._single_query_search                      │
│    HybridSearchRequest(..., vector_score_threshold=self.score_threshold) │
│         │                                                              │
│         ▼                                                              │
│  HybridSearchUseCase.execute                                           │
│    ├─ _fetch_bm25  ────────────────► bm25_hits (필터 미적용)           │
│    └─ _fetch_vector                                                    │
│         vector_docs = search_by_vector(...)   # 코사인 score 포함       │
│         ── [d for d in docs if (d.score or 0.0) >= threshold] ◄── 컷오프│
│              │                                                         │
│              ▼                                                         │
│    RRFFusionPolicy.merge(bm25_hits, filtered_vector_hits, top_k)      │
│         │                                                              │
│         ▼  상위 top_k (저품질 벡터 hit 이미 제거)                       │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

```
RagToolConfig.score_threshold (에이전트별, None=미설정)
        │  None이면 ↓
settings.rag_vector_score_threshold (전역, 기본 0.0)
        │
        ▼
InternalDocumentSearchTool.score_threshold (float)
        │
        ▼
HybridSearchRequest.vector_score_threshold (float)
        │
        ▼
HybridSearchUseCase._fetch_vector
        │  raw_score(코사인 0~1) >= threshold 인 hit만 통과
        ▼
RRFFusionPolicy.merge → 상위 top_k
        │
        ▼
결과 0건이면 "관련 내부 문서를 찾지 못했습니다"
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| ToolFactory | RagToolConfig, settings | 에이전트값 우선 + 전역 fallback 주입 |
| InternalDocumentSearchTool | HybridSearchRequest | 임계값 전달 |
| HybridSearchUseCase | HybridSearchRequest, VectorStoreInterface | 벡터 hit 컷오프 |
| RagToolConfig | (없음, 순수 domain) | 임계값 보관 + 검증 |
| HybridSearchRequest | (없음, 순수 domain) | 임계값 파라미터 |

---

## 3. Data Model

### 3.1 RagToolConfig 확장 (`src/domain/agent_builder/rag_tool_config.py`)

```python
@dataclass(frozen=True)
class RagToolConfig:
    """에이전트별 RAG 도구 설정 Value Object."""

    collection_name: str | None = None
    es_index: str | None = None
    metadata_filter: dict[str, str] = field(default_factory=dict)
    top_k: int = 5
    search_mode: SearchMode = "hybrid"
    rrf_k: int = 60
    tool_name: str = "internal_document_search"
    tool_description: str = (
        "내부 문서에서 관련 정보를 검색합니다. "
        "질문에 대한 내부 문서 정보가 필요할 때 사용하세요."
    )
    # ── 신규: 벡터 코사인 유사도 컷오프 임계값 ──────────────────────
    # None  = 미설정 → ToolFactory가 전역 기본값(settings) 적용
    # 0.0   = 비활성 (모든 hit 통과, 기존 동작)
    # 0~1   = 코사인 유사도 하한
    score_threshold: float | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.top_k <= 20:
            raise ValueError(f"top_k must be 1~20, got {self.top_k}")
        if self.search_mode not in _VALID_SEARCH_MODES:
            raise ValueError(f"Invalid search_mode: {self.search_mode}")
        if self.rrf_k < 1:
            raise ValueError(f"rrf_k must be >= 1, got {self.rrf_k}")
        # ── 신규 검증: 범위 0.0~1.0 (None은 미설정 허용) ──
        if self.score_threshold is not None and not (
            0.0 <= self.score_threshold <= 1.0
        ):
            raise ValueError(
                f"score_threshold must be 0.0~1.0, got {self.score_threshold}"
            )
```

> **설계 결정**: `score_threshold`의 기본값을 `0.0`이 아닌 `None`으로 둔다.
> `None`은 "에이전트가 명시하지 않음 → 전역 기본값 사용", `0.0`은 "명시적 비활성"을 의미하여
> 전역값 오버라이드와 비활성을 구분한다.

### 3.2 HybridSearchRequest 확장 (`src/domain/hybrid_search/schemas.py`)

```python
@dataclass(frozen=True)
class HybridSearchRequest:
    """BM25 + 벡터 하이브리드 검색 요청."""

    query: str
    top_k: int = 10
    bm25_top_k: int = 20
    vector_top_k: int = 20
    rrf_k: int = 60
    metadata_filter: dict[str, str] = field(default_factory=dict)
    bm25_weight: float = 0.5
    vector_weight: float = 0.5
    collection_name: str | None = None
    es_index: str | None = None
    # ── 신규: 벡터 코사인 컷오프 (0.0 = 비활성) ──
    vector_score_threshold: float = 0.0
```

> `HybridSearchRequest`는 항상 `float`(기본 0.0)로 받는다. `None` 처리는 ToolFactory에서 완료되어
> UseCase 레이어로는 항상 확정된 `float`가 전달된다.

### 3.3 Settings 확장 (`src/config.py`)

```python
class Settings(BaseSettings):
    ...
    # RAG Retrieval
    # 벡터 코사인 유사도 컷오프 전역 기본값 (0.0 = 비활성)
    # 에이전트별 RagToolConfig.score_threshold가 None일 때 사용된다.
    rag_vector_score_threshold: float = 0.0
```

### 3.4 값 의미 정리표

| score_threshold 값 | 의미 | 동작 |
|--------------------|------|------|
| `RagToolConfig.score_threshold = None` | 에이전트 미설정 | 전역 `settings.rag_vector_score_threshold` 적용 |
| `RagToolConfig.score_threshold = 0.0` | 명시적 비활성 | 모든 벡터 hit 통과 (기존 동작) |
| `RagToolConfig.score_threshold = 0.3` | 느슨한 컷오프 | 코사인 < 0.3 벡터 hit 제거 |
| `settings.rag_vector_score_threshold = 0.0` | 전역 기본(초기값) | 회귀 없음 |

---

## 4. API Specification

### 4.1 외부 API 변경 없음

기존 RAG Agent / 에이전트 빌더 API 엔드포인트는 변경하지 않는다.
단, 에이전트 생성/수정 시 전달하는 `tool_config` JSON에 선택적 키 `score_threshold`가 추가된다.

### 4.2 tool_config 페이로드 확장 (선택 키)

```json
{
  "tool_id": "internal_document_search",
  "tool_config": {
    "collection_name": "policy_docs",
    "top_k": 5,
    "search_mode": "hybrid",
    "score_threshold": 0.3
  }
}
```

| 키 | 타입 | 필수 | 기본 | 설명 |
|----|------|------|------|------|
| `score_threshold` | float \| null | 아니오 | null | 벡터 코사인 하한(0.0~1.0). null이면 전역 기본값 |

> 기존 `tool_config`에 키가 없으면 `RagToolConfig(**tool_config)`가 `score_threshold=None`으로 생성되어
> 전역 기본값(0.0)을 따른다 → 기존 에이전트 무영향.

---

## 5. UI/UX Design

N/A — 백엔드 내부 검색 품질 개선. 프론트엔드 변경 없음.

> (향후) 에이전트 빌더 UI에서 `score_threshold` 슬라이더를 노출하면 운영자가 직접 조정 가능.
> 본 작업 Out of Scope.

---

## 6. Error Handling

### 6.1 에러 시나리오 및 처리

| 시나리오 | 처리 | 위치 |
|---------|------|------|
| `score_threshold`가 0.0~1.0 범위 밖 | `ValueError` 즉시 발생 (에이전트 생성 차단) | `RagToolConfig.__post_init__` |
| 벡터 검색 자체 실패 (Qdrant 예외) | 기존 동작: warning 로그 + 빈 리스트 반환 → 컷오프 무관 | `_fetch_vector` except |
| 모든 벡터 hit이 컷오프됨 | BM25 결과만으로 RRF 병합 진행 | `RRFFusionPolicy.merge` |
| 전 결과가 컷오프/없음 | "관련 내부 문서를 찾지 못했습니다" 반환 (기존 메시지) | `_single_query_search` |
| `doc.score`가 None (예외적) | `(doc.score or 0.0)`로 0.0 처리 → 임계값>0이면 제거 | `_fetch_vector` |

### 6.2 컷오프 관측 (선택)

```python
# _fetch_vector 내부 — 컷오프 발생 시 debug 로그
filtered = [d for d in vector_docs if (d.score or 0.0) >= threshold]
if threshold > 0.0 and len(filtered) < len(vector_docs):
    self._logger.debug(
        "Vector hits filtered by score_threshold",
        request_id=request_id,
        threshold=threshold,
        before=len(vector_docs),
        after=len(filtered),
    )
```

---

## 7. Security Considerations

- [x] 입력 검증: `score_threshold` 범위(0.0~1.0)를 domain 생성 시점에 강제
- [x] 권한 무관: 본 변경은 검색 점수 필터링만 수행, 기존 AuthContext/visibility 필터(`_apply_auth_filter`) 흐름 불변
- [x] DoS 무관: 추가 I/O 없는 메모리 내 리스트 필터링
- [x] 정보 노출 없음: 컷오프 로그는 debug 레벨, 문서 내용 미포함

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit Test | `RagToolConfig` score_threshold 검증 | pytest |
| Unit Test | `HybridSearchRequest` 기본값 | pytest |
| Unit Test | `HybridSearchUseCase._fetch_vector` 컷오프 | pytest + AsyncMock |
| Unit Test | `ToolFactory` 전역 fallback 주입 | pytest |
| Integration Test | Tool → UseCase 임계값 전파 | pytest |
| Regression Test | 임계값 0.0에서 기존 결과 동일 | pytest |

### 8.2 Test Cases (Key)

**Domain Tests** (`tests/domain/agent_builder/test_rag_tool_config.py`):
- [ ] `test_score_threshold_default_is_none`: 미지정 시 None
- [ ] `test_score_threshold_valid_range`: 0.0, 0.5, 1.0 허용
- [ ] `test_score_threshold_below_zero_raises`: -0.1 → ValueError
- [ ] `test_score_threshold_above_one_raises`: 1.1 → ValueError
- [ ] `test_score_threshold_none_allowed`: None 명시 허용

**Domain Tests** (`tests/domain/hybrid_search/test_schemas.py`):
- [ ] `test_hybrid_request_default_threshold_is_zero`: 기본 0.0

**Application Tests** (`tests/application/hybrid_search/test_use_case.py`):
- [ ] `test_fetch_vector_filters_below_threshold`: 코사인 0.2 hit이 threshold 0.3에서 제거
- [ ] `test_fetch_vector_keeps_at_or_above_threshold`: 코사인 0.3 hit이 threshold 0.3에서 통과(경계 포함)
- [ ] `test_threshold_zero_keeps_all_hits`: threshold 0.0이면 전부 통과 (회귀)
- [ ] `test_all_vector_filtered_falls_back_to_bm25`: 벡터 전부 제거돼도 BM25로 RRF 진행
- [ ] `test_none_score_treated_as_zero`: score=None hit은 0.0 취급

**Infrastructure Tests** (`tests/infrastructure/agent_builder/test_tool_factory.py`):
- [ ] `test_uses_agent_threshold_when_set`: RagToolConfig.score_threshold=0.4 → Tool에 0.4 주입
- [ ] `test_falls_back_to_global_when_none`: score_threshold=None → settings 전역값 주입
- [ ] `test_explicit_zero_overrides_global`: score_threshold=0.0 → 전역값 무시, 0.0 주입

**Regression**:
- [ ] `test_internal_search_tool_default_behavior_unchanged`: 기본 설정 시 기존 결과 동일

---

## 9. Clean Architecture

### 9.1 Layer Structure

| Layer | Responsibility | Location |
|-------|---------------|----------|
| **Domain** | 임계값 보관·검증(RagToolConfig), 요청 파라미터(HybridSearchRequest) | `src/domain/agent_builder/`, `src/domain/hybrid_search/` |
| **Application** | 벡터 hit 컷오프 실행, Tool 임계값 전달 | `src/application/hybrid_search/`, `src/application/rag_agent/` |
| **Infrastructure** | 전역 fallback 주입(ToolFactory), 설정 보관(config) | `src/infrastructure/agent_builder/`, `src/config.py` |
| **Interfaces** | 변경 없음 | - |

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
│   ✅ application/hybrid_search → domain/hybrid_search        │
│   ✅ application/rag_agent → domain/hybrid_search            │
│   ✅ infrastructure/agent_builder → domain/agent_builder    │
│   ✅ infrastructure/agent_builder → src.config (settings)   │
│   ❌ domain/* → infrastructure / application (금지)          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

> **검토 포인트**: `ToolFactory`(infrastructure)가 `settings`를 읽어 주입한다.
> domain(`RagToolConfig`)은 settings를 모른다 → 의존성 규칙 준수.

### 9.3 This Feature's Layer Assignment

| Component | Layer | Location | 변경 유형 |
|-----------|-------|----------|----------|
| `RagToolConfig.score_threshold` | Domain | `src/domain/agent_builder/rag_tool_config.py` | 필드+검증 추가 |
| `HybridSearchRequest.vector_score_threshold` | Domain | `src/domain/hybrid_search/schemas.py` | 필드 추가 |
| `HybridSearchUseCase._fetch_vector` | Application | `src/application/hybrid_search/use_case.py` | 필터 로직 추가 |
| `InternalDocumentSearchTool.score_threshold` | Application | `src/application/rag_agent/tools.py` | 필드+전달 추가 |
| `Settings.rag_vector_score_threshold` | Infrastructure | `src/config.py` | 설정 추가 |
| `ToolFactory.create` | Infrastructure | `src/infrastructure/agent_builder/tool_factory.py` | fallback 주입 추가 |

---

## 10. Coding Convention Reference

### 10.1 Naming Conventions (Python)

| Target | Rule | Example |
|--------|------|---------|
| Field (config) | snake_case | `score_threshold`, `vector_score_threshold` |
| Settings field | snake_case | `rag_vector_score_threshold` |
| Env Variable | UPPER_SNAKE_CASE | `RAG_VECTOR_SCORE_THRESHOLD` |
| Test function | `test_xxx` | `test_score_threshold_above_one_raises` |

### 10.2 Conventions Applied

| Item | Convention Applied |
|------|-------------------|
| 검증 | `__post_init__` 패턴 (기존 RagToolConfig 동일) |
| 기본값 | frozen dataclass 필드 기본값 |
| 로깅 | `self._logger.debug(...)` 구조화 로깅, request_id 포함 (LOG-001) |
| 하위 호환 | 모든 신규 필드 기본값 제공, 미주입 시 무영향 |
| config | env 주입 (`pydantic_settings`), 하드코딩 금지 |

### 10.3 Environment Variables

| Variable | Purpose | Scope | Default |
|----------|---------|-------|---------|
| `RAG_VECTOR_SCORE_THRESHOLD` | 벡터 코사인 컷오프 전역 기본값 | Server | `0.0` |

---

## 11. Implementation Guide

### 11.1 File Structure (변경 파일만)

```
src/
├── config.py                                    # [수정] rag_vector_score_threshold
├── domain/
│   ├── agent_builder/rag_tool_config.py         # [수정] score_threshold 필드+검증
│   └── hybrid_search/schemas.py                 # [수정] vector_score_threshold
├── application/
│   ├── hybrid_search/use_case.py                # [수정] _fetch_vector 컷오프
│   └── rag_agent/tools.py                        # [수정] InternalDocumentSearchTool
└── infrastructure/
    └── agent_builder/tool_factory.py            # [수정] 전역 fallback 주입

tests/
├── domain/agent_builder/test_rag_tool_config.py # [추가/수정]
├── domain/hybrid_search/test_schemas.py         # [추가/수정]
├── application/hybrid_search/test_use_case.py   # [추가/수정]
└── infrastructure/agent_builder/test_tool_factory.py # [추가/수정]
```

### 11.2 Implementation Order (TDD: Red → Green → Refactor)

#### Step 1: Domain Layer (테스트 먼저)
1. [ ] `tests/domain/agent_builder/test_rag_tool_config.py` — score_threshold 검증 테스트 작성 (실패 확인)
2. [ ] `src/domain/agent_builder/rag_tool_config.py` — `score_threshold: float | None = None` + `__post_init__` 범위 검증
3. [ ] `tests/domain/hybrid_search/test_schemas.py` — 기본값 테스트
4. [ ] `src/domain/hybrid_search/schemas.py` — `vector_score_threshold: float = 0.0`
5. [ ] 테스트 통과 확인

#### Step 2: Application Layer (핵심, 테스트 먼저)
6. [ ] `tests/application/hybrid_search/test_use_case.py` — `_fetch_vector` 컷오프 테스트 작성 (AsyncMock vector_store)
7. [ ] `src/application/hybrid_search/use_case.py` — `_fetch_vector`에 `>= threshold` 필터 + debug 로그
8. [ ] `src/application/rag_agent/tools.py` — `score_threshold: float = 0.0` 필드 추가, `_single_query_search`의 `HybridSearchRequest`에 `vector_score_threshold=self.score_threshold` 전달
9. [ ] 테스트 통과 확인

#### Step 3: Infrastructure Layer (주입, 테스트 먼저)
10. [ ] `tests/infrastructure/agent_builder/test_tool_factory.py` — fallback 주입 테스트 작성
11. [ ] `src/config.py` — `rag_vector_score_threshold: float = 0.0`
12. [ ] `src/infrastructure/agent_builder/tool_factory.py` — `create`에서 threshold 결정 로직 + Tool 주입
13. [ ] 테스트 통과 확인

#### Step 4: Verification
14. [ ] 회귀 테스트: 기본 설정에서 기존 결과 동일
15. [ ] `/verify-architecture`, `/verify-logging`, `/verify-tdd` 실행
16. [ ] `.env.example`에 `RAG_VECTOR_SCORE_THRESHOLD=0.0` 문서화

### 11.3 핵심 변경 코드

#### `HybridSearchUseCase._fetch_vector` (변경 핵심)

```python
async def _fetch_vector(
    self, request: HybridSearchRequest, request_id: str
) -> list[SearchHit]:
    try:
        query_vector = await self._embedding.embed_text(request.query)
        vector_filter = None
        if request.metadata_filter:
            from src.domain.vector.value_objects import SearchFilter
            vector_filter = SearchFilter(metadata=request.metadata_filter)
        vector_docs = await self._vector_store.search_by_vector(
            vector=query_vector,
            top_k=request.vector_top_k,
            filter=vector_filter,
            collection_name=request.collection_name,
        )

        threshold = request.vector_score_threshold
        hits = [
            SearchHit(
                id=doc.id.value if hasattr(doc.id, "value") else str(doc.id),
                content=doc.content,
                metadata=doc.metadata,
                raw_score=doc.score or 0.0,
            )
            for doc in vector_docs
            if (doc.score or 0.0) >= threshold        # ◄── 컷오프
        ]

        if threshold > 0.0 and len(hits) < len(vector_docs):
            self._logger.debug(
                "Vector hits filtered by score_threshold",
                request_id=request_id,
                threshold=threshold,
                before=len(vector_docs),
                after=len(hits),
            )
        return hits
    except Exception as e:
        self._logger.warning(
            "Vector search failed, falling back to empty",
            exception=e,
            request_id=request_id,
        )
        return []
```

#### `ToolFactory.create` (threshold 결정)

```python
case "internal_document_search":
    from src.application.rag_agent.tools import InternalDocumentSearchTool
    from src.config import settings

    rag_config = self._parse_rag_config(tool_config)
    effective_threshold = (
        rag_config.score_threshold
        if rag_config.score_threshold is not None
        else settings.rag_vector_score_threshold
    )
    return InternalDocumentSearchTool(
        hybrid_search_use_case=self._get_hybrid_search(),
        request_id=request_id,
        top_k=rag_config.top_k,
        search_mode=rag_config.search_mode,
        rrf_k=rag_config.rrf_k,
        metadata_filter=rag_config.metadata_filter,
        collection_name=rag_config.collection_name,
        es_index=rag_config.es_index,
        name=sanitize_tool_name(rag_config.tool_name),
        description=rag_config.tool_description,
        score_threshold=effective_threshold,   # ◄── 신규 주입
        tracker=self._tracker,
        logger=self._logger,
        config=self._obs_config,
        auth_ctx=self._auth_ctx,
    )
```

#### `InternalDocumentSearchTool._single_query_search` (전달)

```python
request = HybridSearchRequest(
    query=query,
    top_k=self.top_k,
    bm25_top_k=bm25_top_k,
    vector_top_k=vector_top_k,
    rrf_k=self.rrf_k,
    metadata_filter=self._get_effective_filter(),
    collection_name=self.collection_name,
    es_index=self.es_index,
    vector_score_threshold=self.score_threshold,   # ◄── 신규 전달
)
```

### 11.4 주의사항 (Implementation Notes)

- **Multi-Query 경로**: `_multi_query_search` → `MultiQuerySearchUseCase.execute`는 본 작업에서 임계값을 전달하지 않는다(Out of Scope). 단일 쿼리 경로만 적용. 후속 작업 시 `MultiQuerySearchUseCase` 시그니처 확장 필요.
- **search_mode 상호작용**: `bm25_only` 모드에서는 벡터 hit이 0개라 임계값 무영향. `vector_only`/`hybrid`에서만 실효.
- **import 위치**: `ToolFactory`에서 `from src.config import settings`는 기존 `_parse_rag_config`와 동일하게 함수 내부 또는 모듈 상단 — 순환 import 없음 확인 필요.
- **경계값**: `>=` 사용 → 임계값과 정확히 같은 점수는 **통과**.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-06-03 | Initial draft | 배상규 |
