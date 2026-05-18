# reranker-module Planning Document

> **Summary**: Lost in the Middle 현상 대응을 위한 Reranker 모듈 — 코드 기반 위치 재배치(1단계) + API/모델 기반 확장 설계
>
> **Project**: sangplusbot (idt)
> **Author**: 배상규
> **Date**: 2026-05-13
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | LLM은 긴 컨텍스트의 중간에 위치한 문서를 잘 활용하지 못함 (Lost in the Middle, Liu et al. 2023). 현재 RRF 병합 후 순위대로 전달하므로 중간 순위 문서의 정보 손실 발생 |
| **Solution** | 독립 Reranker 모듈을 도메인 인터페이스로 정의하고, 1단계로 코드 기반 위치 재배치(양끝 우선 배치) 구현. 추후 Cohere/Jina/Cross-Encoder로 교체 가능한 전략 패턴 설계 |
| **Function/UX Effect** | 검색 결과 중 관련도 높은 문서가 LLM 컨텍스트의 시작과 끝에 배치되어 답변 품질 향상. 사용자 체감: 동일 질문에 더 정확하고 완전한 답변 |
| **Core Value** | 외부 API 비용 없이 즉시 적용 가능한 검색 품질 개선 + 인터페이스 설계로 향후 고급 Reranker 전략 무중단 교체 가능 |

---

## 1. Overview

### 1.1 Purpose

Hybrid Search(BM25 + Vector → RRF) 결과를 LLM에 전달하기 전에 문서 순서를 재배치하여 Lost in the Middle 현상을 완화하는 독립 Reranker 모듈을 구현한다.

### 1.2 Background

**Lost in the Middle 현상 (Liu et al., 2023)**

Stanford 연구에서 입증된 LLM의 긴 컨텍스트 처리 특성:
- LLM은 컨텍스트 **시작 부분**과 **끝 부분**에 위치한 정보를 가장 잘 활용
- **중간에 위치한 정보**는 관련도가 높아도 무시되거나 활용도가 낮음
- 이 현상은 GPT-4, Claude 등 주요 모델에서 공통적으로 관찰됨

**현재 파이프라인의 한계**:
```
Query → BM25(ES) + Vector(Qdrant) → RRF Fusion (순위 기반 병합) → top_k → LLM
```
- RRF는 관련도 순으로 정렬하지만, 중간 순위 문서가 LLM 컨텍스트 중간에 위치
- 3번째, 4번째 문서가 1번째만큼 관련도 높을 수 있으나 LLM이 제대로 읽지 못함

**목표 파이프라인**:
```
Query → BM25 + Vector → RRF Fusion → Reranker Module → top_k → LLM
```

### 1.3 설계 전략: 2단계 접근

| 단계 | 방식 | 설명 |
|------|------|------|
| **1단계 (이번 스코프)** | `PositionalReranker` | 코드 기반 위치 재배치. 관련도 상위 문서를 양끝에 배치하여 LLM 활용도 극대화 |
| **2단계 (추후 확장)** | `CohereReranker` / `JinaReranker` / `CrossEncoderReranker` | 동일 인터페이스(`RerankerInterface`) 구현체 교체만으로 전환 |

### 1.4 Related Documents

- 현행 Hybrid Search: `src/application/hybrid_search/use_case.py`
- RRF 정책: `src/domain/hybrid_search/policies.py`
- RAG Agent 도구: `src/application/rag_agent/tools.py`
- RAG Agent UseCase: `src/application/rag_agent/use_case.py`
- Hybrid Search 스키마: `src/domain/hybrid_search/schemas.py`

---

## 2. Scope

### 2.1 In Scope

- [ ] `RerankerInterface` 도메인 인터페이스 정의 (전략 패턴)
- [ ] `RerankerRequest` / `RerankerResponse` 도메인 스키마 정의
- [ ] `PositionalReranker` 구현 (코드 기반 양끝 우선 배치)
- [ ] `rerank_candidates` 파라미터화 (후보군 크기 설정 가능)
- [ ] 독립 모듈로 구현 (기존 파이프라인 변경 없음)
- [ ] 단위 테스트: 위치 재배치 로직 검증
- [ ] 통합 준비: HybridSearchUseCase에 주입 가능한 구조

### 2.2 Out of Scope

- Cohere / Jina / Cross-Encoder 등 외부 모델 연동 — 추후 별도 기능
- HybridSearchUseCase 파이프라인 통합 — 테스트 후 별도 작업으로 통합
- 프론트엔드 UI 변경 — 백엔드 내부 모듈
- DB 스키마 변경 — 코드 레벨 모듈
- 검색 쿼리 리라이팅 (Query Rewriting) — 별도 기능

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `RerankerInterface` 정의: `rerank(request) -> response` 비동기 메서드 | High | Pending |
| FR-02 | `RerankerRequest` 스키마: query, documents(list), top_k, rerank_candidates(파라미터) | High | Pending |
| FR-03 | `RerankerResponse` 스키마: reranked_documents(list), strategy_used(str) | High | Pending |
| FR-04 | `PositionalReranker` 구현: 관련도 상위 문서를 양끝(시작, 끝)에 교대 배치 | High | Pending |
| FR-05 | `rerank_candidates` 파라미터로 Reranking 대상 문서 수 조절 가능 | High | Pending |
| FR-06 | Reranker 비활성화 옵션 (`enabled: bool`) — 비교 테스트용 | Medium | Pending |
| FR-07 | 입력 문서가 0~1개일 때 재배치 없이 그대로 반환 (edge case) | Medium | Pending |
| FR-08 | 재배치 전후 문서 누락/중복 없음 보장 | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 확장성 | `RerankerInterface` 구현체 교체만으로 전략 변경 가능 | 코드 리뷰: 새 구현체 추가 시 기존 코드 변경 없음 |
| 성능 | `PositionalReranker`의 추가 latency < 1ms (O(n) 재배치) | 벤치마크 테스트 |
| 테스트 | 단위 테스트 커버리지 90% 이상 | pytest --cov |
| 독립성 | 기존 HybridSearch/RAGAgent 코드 변경 없이 모듈 존재 가능 | 기존 테스트 전체 통과 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] `RerankerInterface` 도메인 인터페이스 정의 완료
- [ ] `PositionalReranker` 구현 및 양끝 배치 로직 동작 확인
- [ ] `rerank_candidates` 파라미터로 후보군 크기 조절 가능
- [ ] edge case 처리 (빈 목록, 1개 문서, top_k > 문서 수)
- [ ] 단위 테스트 통과 (재배치 정확성, 문서 누락/중복 없음)
- [ ] 기존 테스트 전체 통과 (회귀 없음)
- [ ] DDD 레이어 규칙 준수

### 4.2 Quality Criteria

- [ ] 테스트 커버리지 90% 이상
- [ ] Zero lint errors
- [ ] domain 레이어에 외부 의존성 없음
- [ ] 함수 길이 40줄 이하

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 위치 재배치만으로 실제 답변 품질 개선 효과 미미 | Medium | Medium | A/B 비교 로깅 추가하여 효과 측정 후 2단계(모델 기반) 전환 판단 |
| 추후 API 기반 Reranker 전환 시 인터페이스 불일치 | Medium | Low | 인터페이스를 충분히 추상화 (query + documents → reranked documents) |
| Reranker 모듈 통합 시 기존 파이프라인 깨짐 | High | Low | 독립 모듈로 먼저 검증, 통합은 별도 Plan으로 관리 |
| rerank_candidates가 너무 크면 API Reranker 비용 증가 | Medium | Medium | 파라미터 상한값 설정 + 기본값 적정 수준 유지 |

---

## 6. Architecture Considerations

### 6.1 Project Level

| Level | Selected |
|-------|:--------:|
| **Enterprise** | **O** |

기존 Thin DDD 아키텍처(domain → application → infrastructure) 유지.

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 인터페이스 위치 | A) domain/ B) application/ | **A (domain)** | Reranker 전략은 도메인 정책. 외부 의존성 없는 인터페이스만 domain에 배치 |
| 1단계 구현 위치 | A) domain/policies B) infrastructure/ | **A (domain)** | PositionalReranker는 순수 로직, 외부 의존성 없음 → domain policy |
| 2단계 구현 위치 | A) domain/ B) infrastructure/ | **B (infrastructure)** | Cohere/Jina API 호출은 외부 의존성 → infrastructure adapter |
| 파이프라인 통합 방식 | A) HybridSearchUseCase 내부 B) 별도 UseCase | **B (별도)** | 독립 모듈로 먼저 검증, 통합은 추후 별도 작업 |
| 스키마 위치 | A) hybrid_search/schemas B) reranker/schemas | **B (별도)** | Reranker는 독립 도메인 개념, 별도 모듈로 분리 |

### 6.3 PositionalReranker 알고리즘

**양끝 우선 배치 (Alternating Ends Placement)**:

입력: 관련도 순 정렬된 문서 [1등, 2등, 3등, 4등, 5등]

```
배치 규칙:
- 1등 → 위치 0 (시작)
- 2등 → 위치 -1 (끝)
- 3등 → 위치 1 (시작 다음)
- 4등 → 위치 -2 (끝 앞)
- 5등 → 위치 2 (중간)

결과: [1등, 3등, 5등, 4등, 2등]
```

LLM이 가장 잘 읽는 시작/끝에 관련도 높은 문서 배치 → 중간은 관련도가 상대적으로 낮은 문서.

### 6.4 변경 대상 파일

```
변경 범위:
┌─────────────────────────────────────────────────────────────┐
│ domain/reranker/ (신규 모듈)                                  │
│   __init__.py                                                │
│   interfaces.py    — RerankerInterface (ABC)                 │
│   schemas.py       — RerankerRequest, RerankerResponse       │
│   policies.py      — PositionalReranker (순수 도메인 로직)     │
├─────────────────────────────────────────────────────────────┤
│ infrastructure/reranker/ (2단계 예약, 이번엔 빈 모듈)          │
│   __init__.py      — 추후 CohereReranker, JinaReranker 배치  │
├─────────────────────────────────────────────────────────────┤
│ 기존 코드 변경 없음                                            │
│   hybrid_search/   — 변경 없음 (통합은 별도 작업)              │
│   rag_agent/       — 변경 없음 (통합은 별도 작업)              │
├─────────────────────────────────────────────────────────────┤
│ tests/domain/reranker/ (신규)                                 │
│   __init__.py                                                │
│   test_policies.py — PositionalReranker 단위 테스트            │
│   test_schemas.py  — 스키마 유효성 테스트                      │
└─────────────────────────────────────────────────────────────┘
```

---

## 7. Implementation Order

### Phase 1: Domain 스키마 정의

1. `domain/reranker/schemas.py` — `RerankerRequest`, `RerankerResponse`, `RerankableDocument`
2. 테스트: 스키마 생성 및 유효성 검증

### Phase 2: Domain 인터페이스 정의

1. `domain/reranker/interfaces.py` — `RerankerInterface(ABC)` with `async rerank(request) -> response`
2. 테스트: 인터페이스 준수 검증 (ABC 상속 체크)

### Phase 3: PositionalReranker 구현

1. `domain/reranker/policies.py` — 양끝 우선 배치 알고리즘
2. 테스트: 다양한 케이스 (정상, edge case, 파라미터 변형)

### Phase 4: Infrastructure 확장점 준비

1. `infrastructure/reranker/__init__.py` — 빈 모듈 (추후 확장점 표시)
2. 향후 구현 가이드 주석

---

## 8. 향후 확장 로드맵

### 8.1 2단계: API/모델 기반 Reranker

| 구현체 | 위치 | 특징 |
|--------|------|------|
| `CohereReranker` | infrastructure/reranker/ | Cohere Rerank API, 정확도 높음, 호출당 과금 |
| `JinaReranker` | infrastructure/reranker/ | Jina Reranker API, 한국어 우수, 가격 경쟁력 |
| `CrossEncoderReranker` | infrastructure/reranker/ | bge-reranker-v2 로컬 모델, GPU 필요, 호출 비용 없음 |

### 8.2 3단계: 파이프라인 통합

```
HybridSearchUseCase에 RerankerInterface 주입:
  __init__(self, ..., reranker: RerankerInterface | None = None)
  
execute() 내부:
  results = self._rrf_policy.merge(...)
  if self._reranker:
      results = await self._reranker.rerank(results)
  return results
```

---

## 9. Convention Prerequisites

### 9.1 Existing Project Conventions

- [x] `CLAUDE.md` has coding conventions section
- [x] `docs/rules/testing.md` exists
- [x] DDD 레이어 규칙 적용 중
- [x] pytest 기반 TDD 워크플로우

### 9.2 Environment Variables

| Variable | Phase | Description |
|----------|-------|-------------|
| `COHERE_API_KEY` | 2단계 | Cohere Rerank API 키 (추후) |
| `JINA_API_KEY` | 2단계 | Jina Reranker API 키 (추후) |

1단계(PositionalReranker)는 환경변수 불필요.

---

## 10. Next Steps

1. [ ] Design 문서 작성 (`reranker-module.design.md`)
2. [ ] TDD 사이클로 구현 시작 (Phase 1: 스키마부터)
3. [ ] 독립 모듈 테스트 완료 후 통합 Plan 별도 작성
4. [ ] A/B 비교 로깅으로 효과 측정

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-13 | Initial draft | 배상규 |
