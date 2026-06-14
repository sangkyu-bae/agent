# RAG Score Threshold Filter Completion Report

> **Status**: Complete
>
> **Project**: sangplusbot (idt)
> **Version**: 0.1
> **Author**: 배상규
> **Completion Date**: 2026-06-04
> **PDCA Cycle**: #1

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | rag-score-threshold-filter |
| Start Date | 2026-06-03 |
| End Date | 2026-06-04 |
| Duration | 2일 (Plan→Design→Do→Check→Report) |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Match Rate: 100%                            │
├─────────────────────────────────────────────┤
│  ✅ Complete:     7 / 7 기능 요구사항         │
│  ⏳ In Progress:  0 / 7                       │
│  ❌ Cancelled:    0 / 7                       │
├─────────────────────────────────────────────┤
│  구현 파일:  6 + .env.example                 │
│  테스트:     4개 파일, 16개 신규 케이스 추가   │
│  반복(iterate): 0회 (첫 시도 100% 달성)        │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | Agent RAG 경로가 점수 하한 없이 RRF 상위 `top_k`를 무조건 반환 → 벡터 유사도가 낮은(질문과 무관한) "터무니없는 문서"가 출처에 혼입 |
| **Solution** | RRF 병합 **이전** `_fetch_vector`에서 코사인 유사도(0~1) `>= threshold` hit만 통과. 임계값은 전역 env(`RAG_VECTOR_SCORE_THRESHOLD`) + 에이전트별 `tool_config.score_threshold` 오버라이드 |
| **Function/UX Effect** | 임계값 주입 시 저점수 벡터 문서가 검색 단계에서 컷오프됨을 단위 테스트로 검증(0.2 hit이 threshold 0.3에서 제거, 0.3 경계는 포함). 기본값 0.0으로 기존 동작 100% 보존(회귀 0) |
| **Core Value** | 금융/정책 문서에 요구되는 보수적 검색 동작 — 운영 중 코드 변경 없이 에이전트별로 검색 품질 게이트를 조정 가능 |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [rag-score-threshold-filter.plan.md](../01-plan/features/rag-score-threshold-filter.plan.md) | ✅ Finalized |
| Design | [rag-score-threshold-filter.design.md](../02-design/features/rag-score-threshold-filter.design.md) | ✅ Finalized |
| Check | [rag-score-threshold-filter.analysis.md](../03-analysis/rag-score-threshold-filter.analysis.md) | ✅ Complete (100%) |
| Act | Current document | ✅ Complete |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | Requirement | Status | Evidence |
|----|-------------|--------|----------|
| FR-01 | 벡터 hit 코사인 < 임계값이면 RRF 병합 전 제거 | ✅ Complete | `application/hybrid_search/use_case.py:151-161` |
| FR-02 | `config.py` 전역 기본 임계값(env), 기본 0.0 | ✅ Complete | `config.py:33-36` |
| FR-03 | `RagToolConfig.score_threshold` + 0.0~1.0 검증 | ✅ Complete | `domain/agent_builder/rag_tool_config.py:40,49-54` |
| FR-04 | `ToolFactory` 에이전트값 우선·전역 fallback | ✅ Complete | `tool_factory.py:144-154` |
| FR-05 | `HybridSearchRequest`/UseCase 임계값 전파 | ✅ Complete | `domain/hybrid_search/schemas.py:24`, `rag_agent/tools.py:60,173` |
| FR-06 | 전 결과 컷오프 시 "관련 문서 없음" 반환 | ✅ Complete | `rag_agent/tools.py` `_single_query_search` 기존 분기 재사용 |
| FR-07 | 임계값 0.0이면 기존 동작 100% 동일 (무회귀) | ✅ Complete | `test_threshold_zero_keeps_all_hits` |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|--------|
| 성능 | 추가 I/O 없음 (메모리 내 필터) | 리스트 컴프리헨션 1회 | ✅ |
| 호환성 | 기본값 0.0 무회귀 | 회귀 테스트 통과 | ✅ |
| 아키텍처 | Thin DDD 의존성 준수 | domain→infra 참조 0, settings는 infra에서만 | ✅ |
| 로깅 | print 금지, 구조화 로깅 | `logger.debug` 컷오프 관측 | ✅ |

### 3.3 Deliverables

| Deliverable | Location | Status |
|-------------|----------|--------|
| Domain (config VO) | `domain/agent_builder/rag_tool_config.py` | ✅ |
| Domain (request schema) | `domain/hybrid_search/schemas.py` | ✅ |
| Application (cutoff) | `application/hybrid_search/use_case.py` | ✅ |
| Application (tool passthrough) | `application/rag_agent/tools.py` | ✅ |
| Infrastructure (global default) | `config.py` | ✅ |
| Infrastructure (DI resolution) | `infrastructure/agent_builder/tool_factory.py` | ✅ |
| Env 문서화 | `.env.example` | ✅ |
| Tests | `tests/{domain,application,infrastructure}/...` (4 files) | ✅ |
| PDCA 문서 | `docs/01~04` | ✅ |

---

## 4. Incomplete Items

### 4.1 Carried Over to Next Cycle

| Item | Reason | Priority | Est. |
|------|--------|----------|------|
| Multi-Query 경로 임계값 전파 | 설계상 Out of Scope (단일 쿼리 경로 우선 안정화) | Medium | 0.5일 |
| 운영 데이터 기반 권장 기본값 산정 (0.0 → 0.2~0.4) | 임베딩 분포 측정 필요 | Medium | 측정 후 |
| 컷오프 통계 관측(`ai_retrieval_source`) | 선택 사항 | Low | 0.5일 |

### 4.2 Cancelled/On Hold Items

| Item | Reason | Alternative |
|------|--------|-------------|
| BM25 점수 임계값 | ES score 비정규화·무한대 범위로 직관적 임계 불가 | 벡터 코사인 컷오프로 대체 |
| RRF 최종 점수 임계값 | RRF 점수(0.008 등) 비직관적 | 벡터 단계 컷오프로 대체 |

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Value |
|--------|-------|
| Design Match Rate | **100%** |
| Architecture Compliance | 100% |
| Convention Compliance | 100% |
| Out-of-Scope 누수 | 0건 (Multi-Query/BM25/RRF 정상 미구현 확인) |
| 반복 횟수 | 0회 (첫 구현에서 90% 임계 즉시 통과) |

### 5.2 Test Results

| Test Suite | 신규 케이스 | 결과 |
|------------|:-----------:|------|
| `test_rag_tool_config.py` | 6 | ✅ Pass |
| `test_schemas.py` (hybrid) | 2 | ✅ Pass |
| `test_hybrid_search_use_case.py` | 5 | ✅ Pass |
| `test_tool_factory.py` | 4 (3 설계 + 1 추가) | ✅ Pass |

> 교차 실행 시 나타나는 `ProactorEventLoop _ssock` teardown 에러는 단언 실패가 아닌 Windows asyncio GC 노이즈(문서화된 기존 플래키니스). 단일 격리 실행 시 0 에러로 검증 완료.

---

## 6. Lessons Learned

### 6.1 잘된 점 (Keep)

- **`None` vs `0.0` 의미 분리**가 "전역 기본 + 에이전트별 오버라이드 + 명시적 비활성" 3가지 상태를 깔끔하게 표현 → 설계 시 의도적으로 분리한 것이 구현·테스트를 단순하게 만듦.
- **단일 필터 지점**(`_fetch_vector`에만 적용) 원칙으로 BM25/RRF/Multi-Query 영향 차단 → Out-of-Scope 누수 0건.
- 기본값 0.0 opt-in 전략으로 **회귀 위험 0** 상태에서 안전하게 머지 가능.

### 6.2 개선점 (Problem / Try)

- RRF 최종 점수가 코사인이 아닌 비직관적 값임을 **Plan 질문 단계에서 미리 파악**해 필터 기준을 벡터 코사인으로 확정한 것이 핵심 — 코드 탐색 선행이 결정 품질을 높였다.
- 권장 임계값은 실데이터 임베딩 분포 측정 없이 단정할 수 없어 0.0으로 출발 → 향후 운영 로그(`logger.debug` 컷오프 통계)로 튜닝 근거 확보 필요.

### 6.3 재사용 가능한 패턴

- ToolFactory의 `_resolve_xxx`(에이전트값 ?? 전역 settings) 해석 패턴은 향후 다른 RAG 파라미터(rrf_k, top_k 등)의 전역 기본값화에 그대로 재사용 가능.

---

## 7. Next Steps

1. [ ] (선택) `/pdca archive rag-score-threshold-filter --summary` 로 문서 아카이브 + 메트릭 보존
2. [ ] 운영 배포 시 에이전트별 `score_threshold` 점진 적용 (예: 정책 문서 에이전트 0.3부터)
3. [ ] `logger.debug` 컷오프 통계로 임베딩 분포 측정 → 권장 전역 기본값 재산정
4. [ ] (후속 FR) Multi-Query 경로 임계값 전파

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-06-04 | 완료 보고서 작성 (Match Rate 100%) | 배상규 |
