# Multi-Query Rewrite Planning Document

> **Summary**: LangGraph 기반 Multi-Query Rewrite 워크플로우 — 사용자 쿼리를 다각도 변형 후 병렬 검색하여 RAG 검색 품질을 개선한다
>
> **Project**: sangplusbot (idt)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-05-14
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 현재 RAG Agent는 사용자의 원본 쿼리를 그대로 검색에 사용하므로, 짧거나 모호한 질문에 대해 관련 문서를 놓치는 경우가 빈번하다 |
| **Solution** | LangGraph StateGraph로 Multi-Query Rewrite 워크플로우를 구축하여 1개 질문을 3~5개 관점의 쿼리로 확장 → 각각 Hybrid Search → RRF 합산 |
| **Function/UX Effect** | 사용자가 간단하게 질문해도 내부적으로 다각도 검색이 수행되어 더 풍부하고 정확한 문서가 검색된다 |
| **Core Value** | RAG 검색 재현율(Recall) 향상으로 답변 품질 개선, 금융/정책 문서의 다양한 표현을 커버 |

---

## 1. Overview

### 1.1 Purpose

현재 시스템에는 두 가지 문제가 있다:

1. **RAG Agent 경로**: 사용자 쿼리를 그대로 `InternalDocumentSearchTool`에 전달. Query rewrite 없음.
2. **기존 QueryRewriterUseCase**: 단순 1회 LLM 리라이트만 수행. RAG Agent/Hybrid Search에 연결되지 않음.

Multi-Query Rewrite는 이 문제를 해결하기 위해 **1개 쿼리 → N개 변형 쿼리 → 각각 검색 → 결과 합산(RAG-Fusion)** 패턴의 LangGraph 워크플로우를 구축한다.

### 1.2 Background

- **금융/정책 문서 특성**: 동일 개념을 다양한 용어로 표현 (예: "대출 한도" = "여신 한도" = "대출 가능 금액")
- **짧은 질문**: 사용자가 "적금 금리" 같은 2~3단어 질문을 자주 하지만, 문서에는 더 구체적 표현 사용
- **Multi-Query 접근**: 학술적으로 검증된 RAG-Fusion 패턴으로, 다양한 관점의 쿼리를 생성하여 검색 재현율을 크게 개선

### 1.3 Related Documents

- 기존 코드: `src/application/query_rewrite/use_case.py` (단순 리라이트)
- 기존 코드: `src/application/research_agent/workflow.py` (LangGraph 패턴 참조)
- 기존 코드: `src/application/hybrid_search/use_case.py` (검색 실행)
- 기존 코드: `src/domain/hybrid_search/schemas.py` (RRF Fusion 정책)

---

## 2. Scope

### 2.1 In Scope

- [ ] Multi-Query 생성 LangGraph 워크플로우 (StateGraph)
- [ ] 쿼리 분류 노드: 단순/복합/모호 판별
- [ ] Multi-Query 생성 노드: 1개 → 3~5개 변형 쿼리 생성 (LLM)
- [ ] 병렬 검색 노드: 각 변형 쿼리로 Hybrid Search 실행
- [ ] 결과 합산 노드: RRF(Reciprocal Rank Fusion)로 최종 결과 병합
- [ ] 기존 QueryRewriterUseCase를 simple-rewrite 전략으로 포함
- [ ] RAG Agent에서 호출 가능한 인터페이스 제공
- [ ] Domain 정책: Multi-Query 생성 규칙, 최대 쿼리 수 제한

### 2.2 Out of Scope

- HyDE (Hypothetical Document Embedding) — 향후 전략으로 추가 가능
- Step-back Prompting / Query Decomposition — 향후 전략으로 추가 가능
- 기존 API 엔드포인트 변경 (내부 워크플로우만 교체)
- 프론트엔드 변경 (백엔드 내부 개선)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | LangGraph StateGraph로 Multi-Query Rewrite 워크플로우 구성 | High | Pending |
| FR-02 | 쿼리 분류(classify) 노드: 단순(simple) / 복합(complex) / 모호(ambiguous) 판별 | High | Pending |
| FR-03 | Multi-Query 생성 노드: LLM으로 3~5개 다관점 변형 쿼리 생성 | High | Pending |
| FR-04 | 병렬 검색 노드: 각 변형 쿼리로 HybridSearchUseCase 호출 | High | Pending |
| FR-05 | 결과 합산 노드: RRF Fusion으로 중복 제거 + 점수 합산 | High | Pending |
| FR-06 | 기존 QueryRewriterUseCase를 단순 쿼리 경로에서 재사용 | Medium | Pending |
| FR-07 | RAG Agent의 InternalDocumentSearchTool에서 호출 연동 | High | Pending |
| FR-08 | Domain Policy: 최대 쿼리 수, 쿼리 분류 기준 정의 | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | Multi-Query 생성 + 검색 총 응답시간 < 5초 (5개 쿼리 기준) | 로그 타임스탬프 |
| Performance | 병렬 검색으로 순차 대비 지연 최소화 | asyncio.gather 활용 |
| Reliability | LLM 쿼리 생성 실패 시 원본 쿼리로 fallback | 에러 핸들링 테스트 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] LangGraph 워크플로우 3개 핵심 노드 구현 (classify → generate_queries → search_and_fuse)
- [ ] 단위 테스트 작성 및 통과 (TDD)
- [ ] RAG Agent 연동 테스트 통과
- [ ] 기존 기능(Hybrid Search, RAG Agent) 회귀 없음

### 4.2 Quality Criteria

- [ ] 테스트 커버리지 80% 이상
- [ ] mypy 타입 체크 통과
- [ ] 레이어 의존성 규칙 준수 (domain → application → infrastructure)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| LLM 호출 비용 증가 (쿼리당 1회 → 2회) | Medium | High | gpt-4o-mini 사용, 단순 쿼리는 rewrite 건너뛰기 |
| 병렬 검색 시 Qdrant/ES 부하 증가 | Medium | Medium | top_k를 쿼리 수에 반비례 조정 (5개 쿼리 × 4개씩 = 20개) |
| Multi-Query 생성 품질 편차 | Medium | Medium | few-shot 예시로 프롬프트 품질 안정화, 도메인 특화 예시 포함 |
| 응답 지연 증가 | Low | Medium | asyncio.gather로 병렬 검색, classify에서 단순 쿼리는 fast-path |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules, BaaS | Web apps with backend | ☐ |
| **Enterprise** | Strict layer separation, DI | High-traffic systems | ☑ |

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 워크플로우 엔진 | LangGraph StateGraph / LangChain LCEL / 직접 구현 | LangGraph StateGraph | 기존 research_agent와 패턴 통일, 노드 재사용 용이 |
| 쿼리 생성 LLM | gpt-4o / gpt-4o-mini | gpt-4o-mini | 비용 효율, 쿼리 변형은 복잡한 추론 불필요 |
| 검색 병렬화 | asyncio.gather / LangGraph Send API | asyncio.gather | 기존 HybridSearchUseCase가 async, Send API는 과도 |
| 결과 합산 | RRF / 단순 Union | RRF (Reciprocal Rank Fusion) | 기존 RRFFusionPolicy 재사용, 검증된 알고리즘 |
| 기존 코드 관계 | 교체 / 확장 / 공존 | 확장 | 기존 QueryRewriterUseCase를 simple 전략으로 유지 |

### 6.3 Clean Architecture Approach

```
Enterprise (Thin DDD):

src/
├── domain/
│   └── multi_query/
│       ├── schemas.py          # MultiQueryState, QueryVariant, FusedResult
│       └── policy.py           # MultiQueryPolicy (분류 규칙, 최대 쿼리 수)
│
├── application/
│   └── multi_query/
│       ├── workflow.py         # MultiQueryRewriteWorkflow (LangGraph StateGraph)
│       └── use_case.py         # MultiQuerySearchUseCase (진입점)
│
├── infrastructure/
│   └── multi_query/
│       └── query_generator_adapter.py  # LLM 기반 Multi-Query 생성
│
└── api/routes/                 # (기존 API 변경 없음, 내부 호출만)
```

### 6.4 LangGraph Workflow Design

```
                    ┌──────────────┐
                    │   START      │
                    │ (user query) │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │  classify    │  쿼리 유형 분류
                    │  _query      │  (simple / complex / ambiguous)
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
        ┌─────▼─────┐ ┌───▼────┐ ┌────▼──────┐
        │  simple   │ │complex │ │ ambiguous │
        │ rewrite   │ │ multi  │ │  multi    │
        │ (기존)    │ │ query  │ │  query    │
        └─────┬─────┘ └───┬────┘ └────┬──────┘
              │            │            │
              │      ┌─────▼─────┐      │
              │      │ generate  │      │
              │      │ _queries  │◄─────┘
              │      │ (LLM)    │
              │      └─────┬─────┘
              │            │
              │      ┌─────▼─────────┐
              │      │ parallel      │
              │      │ _search       │
              │      │ (N개 쿼리     │
              │      │  각각 검색)   │
              │      └─────┬─────────┘
              │            │
              ├────────────┤
              │            │
        ┌─────▼────────────▼─────┐
        │     fuse_results       │
        │  (RRF 합산 + 중복제거) │
        └────────────┬───────────┘
                     │
              ┌──────▼──────┐
              │    END      │
              │ (fused docs)│
              └─────────────┘
```

**State 정의**:
```python
class MultiQueryState(TypedDict):
    original_query: str           # 원본 쿼리
    request_id: str               # 추적 ID
    query_type: str               # "simple" | "complex" | "ambiguous"
    generated_queries: list[str]  # 생성된 변형 쿼리들
    search_results: list[list]    # 각 쿼리별 검색 결과
    fused_results: list           # RRF 합산 최종 결과
    top_k: int                    # 최종 반환 문서 수
    errors: list[str]             # 에러 목록
    status: str                   # 워크플로우 상태
```

---

## 7. Convention Prerequisites

### 7.1 Existing Project Conventions

- [x] `CLAUDE.md` has coding conventions section
- [x] `docs/rules/` 규칙 파일 존재 (logging, testing, db-session 등)
- [x] Thin DDD 레이어 분리 확립
- [x] pytest TDD 워크플로우 확립

### 7.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| **Naming** | 기존 패턴 확립 | `multi_query` 모듈 네이밍 | High |
| **LangGraph 패턴** | research_agent 참조 | 노드 함수 네이밍 (`_xxx_node`), State 업데이트 패턴 | High |
| **에러 처리** | logger 사용 필수 | LLM 실패 시 fallback 패턴 | Medium |

### 7.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| `OPENAI_API_KEY` | Multi-Query 생성 LLM 호출 | Server | ☑ (기존) |
| (추가 없음) | 기존 환경변수만 사용 | - | - |

---

## 8. Implementation Order

### Phase 1: Domain Layer
1. `src/domain/multi_query/schemas.py` — MultiQueryState, QueryVariant
2. `src/domain/multi_query/policy.py` — MultiQueryPolicy (분류 규칙, 최대 쿼리 수)

### Phase 2: Infrastructure Layer
3. `src/infrastructure/multi_query/query_generator_adapter.py` — LLM Multi-Query 생성
4. `src/infrastructure/multi_query/prompts.py` — 프롬프트 템플릿 (few-shot 포함)

### Phase 3: Application Layer (핵심)
5. `src/application/multi_query/workflow.py` — LangGraph StateGraph 워크플로우
6. `src/application/multi_query/use_case.py` — MultiQuerySearchUseCase (진입점)

### Phase 4: Integration
7. `src/application/rag_agent/tools.py` — InternalDocumentSearchTool에 multi-query 옵션 추가
8. `src/application/rag_agent/use_case.py` — 워크플로우 DI 주입

---

## 9. Next Steps

1. [ ] Design 문서 작성 (`multi-query-rewrite.design.md`)
2. [ ] 코드 리뷰 및 Plan 확정
3. [ ] TDD 사이클로 구현 시작

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-14 | Initial draft | 배상규 |
