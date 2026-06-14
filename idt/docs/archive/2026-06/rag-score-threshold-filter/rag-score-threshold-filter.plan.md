# RAG Score Threshold Filter Planning Document

> **Summary**: 하이브리드 검색의 벡터 코사인 유사도가 임계값 미만인 문서를 검색 결과에서 제외하여 "터무니없는 문서" 혼입을 차단한다. 전역 기본값 + 에이전트별 주입으로 운영 중 조정 가능하게 한다.
>
> **Project**: sangplusbot (idt)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-06-03
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 현재 Agent RAG 경로(`InternalDocumentSearchTool` → `HybridSearchUseCase` → RRF)는 점수 하한 없이 상위 `top_k`를 무조건 반환한다. 벡터 코사인 유사도가 낮은(질문과 무관한) 문서도 RRF top_k에 끼어들어 답변 품질을 떨어뜨린다 |
| **Solution** | RRF 병합 **이전** 벡터 검색 단계에서 코사인 유사도(0~1)가 임계값 미만인 hit을 제거한다. 임계값은 `config.py` 전역 기본값 + `RagToolConfig` 에이전트별 주입(오버라이드)으로 관리한다 |
| **Function/UX Effect** | 명백히 무관한 문서가 출처에서 사라져 답변 정확도와 신뢰도가 올라간다. 운영 중 코드 변경 없이 에이전트별로 임계값을 조정할 수 있다 |
| **Core Value** | 금융/정책 문서에 요구되는 보수적 검색 동작 확보 — "모르면 답하지 않음"을 위한 검색 단계 품질 게이트 |

---

## 1. Overview

### 1.1 Purpose

Agent RAG 검색에서 질문과 무관한 저품질 문서가 결과에 섞이는 문제를 해결한다.
벡터 코사인 유사도를 기준으로 임계값 미만 문서를 검색 단계에서 컷오프하고,
그 임계값을 **전역 기본값**으로 두되 **에이전트별로 주입/변경** 가능하게 한다.

### 1.2 Background

현재 실제 사용자 경로의 검색 흐름:

```
InternalDocumentSearchTool._single_query_search
  → HybridSearchUseCase.execute
    → _fetch_bm25 + _fetch_vector  (각각 top_k*2 수집)
    → RRFFusionPolicy.merge        (RRF 점수 내림차순, 상위 top_k 반환)
```

문제점:

1. **점수 하한 부재**: `RRFFusionPolicy.merge`는 `results[:top_k]`로 무조건 상위 N개를 반환한다. 관련 문서가 부족해도 빈자리를 저품질 문서로 채운다.
2. **RRF 점수는 임계 기준 부적합**: 최종 RRF 점수는 `0.5 × 1/(60+rank)` 형태로 0.008 같은 작은 값이라 직관적인 임계값을 잡기 어렵다.
3. **기존 자산 미활용**: `QdrantRetriever`에는 이미 `score_threshold`(코사인 0~1) 필드가 있으나 **하이브리드 경로(`QdrantVectorStore.search_by_vector`)는 이를 거치지 않는다**.

→ 따라서 **벡터 검색 hit의 코사인 raw_score(0~1)** 를 RRF 병합 전에 필터링하는 것이 가장 직관적이고 효과적이다.

### 1.3 Related Documents

- 기존 코드: `src/application/rag_agent/tools.py` (`InternalDocumentSearchTool`)
- 기존 코드: `src/application/hybrid_search/use_case.py` (`_fetch_vector`)
- 기존 코드: `src/domain/hybrid_search/schemas.py` (`HybridSearchRequest`, `SearchHit`)
- 기존 코드: `src/domain/agent_builder/rag_tool_config.py` (`RagToolConfig`)
- 기존 코드: `src/infrastructure/agent_builder/tool_factory.py` (`ToolFactory`)
- 기존 코드: `src/config.py` (`Settings`)
- 참고: `src/infrastructure/retriever/qdrant_retriever.py` (`score_threshold` 선행 사례)

---

## 2. Scope

### 2.1 In Scope

- [ ] `config.py`에 전역 기본 임계값 `rag_vector_score_threshold: float = 0.0` 추가 (env: `RAG_VECTOR_SCORE_THRESHOLD`)
- [ ] `RagToolConfig`에 `score_threshold: float | None = None` 필드 + 검증(0.0~1.0) 추가
- [ ] `HybridSearchRequest`에 `vector_score_threshold: float = 0.0` 필드 추가
- [ ] `HybridSearchUseCase._fetch_vector`에서 코사인 `raw_score < threshold` hit 제거
- [ ] `InternalDocumentSearchTool`에 `score_threshold` 필드 추가 → `HybridSearchRequest`로 전달 (단일 쿼리 경로)
- [ ] `ToolFactory.create`에서 `RagToolConfig.score_threshold` 우선, `None`이면 `settings.rag_vector_score_threshold` 전역 기본값 적용
- [ ] 전 결과가 임계값에 걸려 비면 기존 "관련 내부 문서를 찾지 못했습니다" 메시지로 자연스럽게 동작
- [ ] 각 레이어 단위 테스트 (TDD: 정책/스키마 → UseCase 필터링 → Tool 주입 → Factory fallback)

### 2.2 Out of Scope

- **Multi-Query 경로**(`_multi_query_search` → `MultiQuerySearchUseCase`)의 임계값 전파 — 후속 작업 (FR로 별도 추적, 본 작업은 단일 쿼리 하이브리드 경로 집중)
- **BM25(ES) 점수 임계값** — ES score는 비정규화·무한대 범위라 직관적 임계 불가, 본 작업 제외
- **RRF 최종 점수 임계값** — 직관성 낮아 제외 (질문 응답에서 결정됨)
- **다른 검색 경로**: `retrieval_use_case`, `collection_search`, `QdrantRetriever` 직접 호출 경로 — 적용 범위에서 제외
- 프론트엔드 변경 (백엔드 내부 검색 품질 개선, API 계약 불변)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 벡터 검색 hit 중 코사인 유사도가 임계값 미만이면 RRF 병합 전 제거 | High | Pending |
| FR-02 | `config.py`에 전역 기본 임계값(env 주입) 정의, 기본값 0.0(비활성) | High | Pending |
| FR-03 | `RagToolConfig`에 에이전트별 `score_threshold` 필드 + 0.0~1.0 검증 | High | Pending |
| FR-04 | `ToolFactory`에서 에이전트값 우선·전역 기본값 fallback 적용 | High | Pending |
| FR-05 | `HybridSearchRequest`/`HybridSearchUseCase`에 임계값 파라미터 전파 | High | Pending |
| FR-06 | 모든 결과가 컷오프되면 "관련 내부 문서를 찾지 못했습니다" 반환 | Medium | Pending |
| FR-07 | 임계값=0.0이면 기존 동작과 100% 동일 (회귀 없음) | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | 필터링은 메모리 내 리스트 연산, 추가 I/O 없음 (오버헤드 무시 가능) | 코드 리뷰 |
| Compatibility | 기본값 0.0으로 기존 에이전트 동작 불변 | 회귀 테스트 |
| Observability | 컷오프된 hit 수를 디버그 로그로 남김 (선택) | 로그 확인 |
| Maintainability | Thin DDD 레이어 의존성 규칙 준수 | `/verify-architecture` |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] 모든 기능 요구사항(FR-01~07) 구현
- [ ] 단위 테스트 작성 및 통과 (TDD Red→Green→Refactor)
- [ ] 임계값 0.0 기본값에서 기존 동작 회귀 없음 검증
- [ ] 임계값 0.3/0.5 주입 시 저점수 문서 제외 검증
- [ ] 레이어 의존성 규칙 준수 확인

### 4.2 Quality Criteria

- [ ] 테스트 커버리지 80% 이상 (변경 모듈 기준)
- [ ] mypy 타입 체크 통과
- [ ] `print()` 미사용, logger 사용 (LOG-001)
- [ ] config 하드코딩 없음 (env 주입)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 임계값을 너무 높게 잡아 정상 문서까지 컷오프 → Recall 하락 | High | Medium | 기본값 0.0(비활성)로 시작, 에이전트별 점진 튜닝, 컷오프 로그로 모니터링 |
| 임베딩 모델/거리 함수에 따라 코사인 분포 상이 (COSINE 사용 확인됨) | Medium | Low | `QdrantVectorStore`가 `Distance.COSINE` 사용 확인 — score는 0~1 코사인 유사도 |
| BM25 단독 hit은 필터 미적용이라 여전히 저품질 가능 | Low | Medium | 본 작업 범위는 벡터 코사인 컷오프. BM25 임계는 Out of Scope로 명시 |
| Multi-Query 경로에 임계값 미전파로 동작 불일치 | Medium | Medium | Out of Scope 명시 + 후속 FR로 추적, 단일 쿼리 경로 먼저 안정화 |
| `raw_score`가 0.0으로 들어오는 fallback(예외 시) hit이 컷오프됨 | Low | Low | 임계값 0.0 기본에서는 영향 없음. 예외 fallback은 빈 리스트 반환이므로 무관 |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules, BaaS | Web apps with backend | ☐ |
| **Enterprise** | Strict layer separation, DI | High-traffic systems | ☑ |

> 기존 Thin DDD(Domain → Application → Infrastructure) 구조 유지. 신규 레이어/모듈 없이 기존 파일 확장.

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 필터 기준 점수 | 벡터 코사인(0~1) / RRF 최종 / 둘 다 | **벡터 코사인(0~1)** | 직관적 임계, "터무니없는 문서" 직접 원인, RRF 점수는 비직관적 |
| 필터 적용 위치 | 벡터 fetch 단계 / RRF 병합 후 | **벡터 fetch 단계 (`_fetch_vector`)** | 병합 전 제거가 가장 단순·정확, BM25와 분리 |
| 설정 위치 | 전역 config만 / RagToolConfig만 / 둘 다 | **RagToolConfig + 전역 기본값** | 운영 중 에이전트별 주입·변경, 기존 top_k/search_mode와 동일 패턴 |
| 기본 임계값 | 0.0(비활성) / 0.3 / 0.5 | **0.0 (opt-in)** | 회귀 위험 0, 기존 동작 보존 후 에이전트별 점진 적용 |
| 적용 범위 | 하이브리드만 / 전체 경로 | **Agent 하이브리드 단일쿼리 경로** | 실제 사용자 영향 큰 핵심 경로 집중, 검증 부담 최소화 |
| 기존 코드 관계 | 교체 / 확장 | **확장** | 기존 필드(top_k 등) 옆에 score_threshold 추가, 하위 호환 |

### 6.3 Clean Architecture Approach

```
Enterprise (Thin DDD) — 기존 파일 확장, 신규 모듈 없음

src/
├── config.py                                    # [확장] rag_vector_score_threshold 전역 기본값
│
├── domain/
│   ├── agent_builder/rag_tool_config.py         # [확장] score_threshold 필드 + 0~1 검증
│   └── hybrid_search/schemas.py                 # [확장] HybridSearchRequest.vector_score_threshold
│
├── application/
│   ├── hybrid_search/use_case.py                # [핵심] _fetch_vector 코사인 컷오프
│   └── rag_agent/tools.py                        # [확장] InternalDocumentSearchTool.score_threshold 전달
│
└── infrastructure/
    └── agent_builder/tool_factory.py            # [확장] 에이전트값 우선 + 전역 fallback 주입
```

### 6.4 Data Flow Design

```
[설정 주입]
  config.py (전역 기본값 0.0)
        │ settings.rag_vector_score_threshold
        ▼
  ToolFactory.create
        │  rag_config.score_threshold ?? settings.rag_vector_score_threshold
        ▼
  InternalDocumentSearchTool(score_threshold=…)
        │
        ▼
  HybridSearchRequest(vector_score_threshold=…)
        │
        ▼
[검색 실행 — 핵심 필터 지점]
  HybridSearchUseCase._fetch_vector
        │  vector_docs = search_by_vector(...)        # 코사인 score 포함
        │  ── 필터: [d for d in docs if d.score >= threshold]   ◄── 컷오프
        ▼
  RRFFusionPolicy.merge(bm25_hits, filtered_vector_hits, top_k)
        ▼
  상위 top_k 반환 (저품질 벡터 hit 이미 제거됨)
```

**핵심 변경 (`_fetch_vector`)**:
```python
threshold = request.vector_score_threshold  # 기본 0.0
return [
    SearchHit(id=…, content=doc.content, metadata=doc.metadata, raw_score=doc.score or 0.0)
    for doc in vector_docs
    if (doc.score or 0.0) >= threshold        # ◄── 추가
]
```

> 임계값 0.0이면 `score >= 0.0`은 항상 참 → 기존 동작과 동일(회귀 없음, FR-07).

---

## 7. Convention Prerequisites

### 7.1 Existing Project Conventions

- [x] `CLAUDE.md` 코딩 컨벤션 섹션 존재
- [x] `docs/rules/` 규칙 파일 존재 (logging, testing, db-session 등)
- [x] Thin DDD 레이어 분리 확립
- [x] pytest TDD 워크플로우 확립
- [x] `RagToolConfig` frozen dataclass + `__post_init__` 검증 패턴 확립

### 7.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| **검증 규칙** | `RagToolConfig.__post_init__` 패턴 존재 | `score_threshold` 0.0~1.0 범위 검증 추가 | High |
| **설정 네이밍** | `settings.*` snake_case | `rag_vector_score_threshold` / env `RAG_VECTOR_SCORE_THRESHOLD` | High |
| **fallback 패턴** | `_parse_rag_config` None→기본값 | `None`이면 전역 기본값 주입 패턴 | Medium |

### 7.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| `RAG_VECTOR_SCORE_THRESHOLD` | 벡터 코사인 컷오프 전역 기본값 (기본 0.0) | Server | ☑ |

---

## 8. Implementation Order

### Phase 1: Domain Layer (TDD)
1. `src/domain/agent_builder/rag_tool_config.py` — `score_threshold: float | None = None` + `__post_init__`에 0.0~1.0 검증
2. `src/domain/hybrid_search/schemas.py` — `HybridSearchRequest.vector_score_threshold: float = 0.0`

### Phase 2: Application Layer (핵심)
3. `src/application/hybrid_search/use_case.py` — `_fetch_vector`에서 `raw_score >= threshold` 필터링 (+ 컷오프 수 debug 로그 선택)
4. `src/application/rag_agent/tools.py` — `InternalDocumentSearchTool.score_threshold` 필드 추가, `_single_query_search`에서 `HybridSearchRequest`로 전달

### Phase 3: Infrastructure Layer (주입)
5. `src/config.py` — `rag_vector_score_threshold: float = 0.0`
6. `src/infrastructure/agent_builder/tool_factory.py` — `create`에서 `rag_config.score_threshold`가 `None`이면 `settings.rag_vector_score_threshold` 적용 후 Tool에 주입

### Phase 4: Verification
7. 회귀 테스트: 임계값 0.0에서 기존 결과 동일
8. 동작 테스트: 임계값 0.3/0.5 주입 시 저점수 벡터 hit 제외 확인
9. `/verify-architecture`, `/verify-logging`, `/verify-tdd` 실행

---

## 9. Open Questions / Follow-ups

- [ ] Multi-Query 경로 임계값 전파 (후속 FR) — `MultiQuerySearchUseCase.execute` 시그니처에 임계값 추가 필요
- [ ] 운영 데이터 기반 권장 기본 임계값 산정 (현 0.0 → 추후 0.2~0.4 검토, 임베딩 분포 측정 후)
- [ ] 컷오프 통계를 `ai_retrieval_source`/관측 로그에 남길지 여부

---

## 10. Next Steps

1. [ ] Design 문서 작성 (`/pdca design rag-score-threshold-filter`)
2. [ ] 코드 리뷰 및 Plan 확정
3. [ ] TDD 사이클로 구현 시작 (`/pdca do rag-score-threshold-filter`)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-06-03 | Initial draft | 배상규 |
