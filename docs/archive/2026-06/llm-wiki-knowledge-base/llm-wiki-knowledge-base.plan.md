---
template: plan
version: 1.2
feature: llm-wiki-knowledge-base
date: 2026-06-28
author: 배상규
project: sangplusbot
---

# llm-wiki-knowledge-base Planning Document

> **Summary**: 에이전트 지식베이스를 Pull-only 구조에서 "검색→정제→기억" 환류 루프를 갖춘 Self-Improving RAG(LLM Wiki)로 전환한다.
>
> **Project**: sangplusbot
> **Version**: feature/mcp-server-registry 기반
> **Author**: 배상규
> **Date**: 2026-06-28
> **Status**: Draft
> **Reference**: `docs/llm-wiki-knowledge-base-analysis-2026-06-28.md` (분석 레포트)

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 현재 지식베이스는 추론 중 읽기 전용(Pull-only)이라 대화·웹서치·검색에서 얻은 지식이 어디에도 축적되지 않는다. 시간이 지나도 시스템이 똑똑해지지 않고, 반복 질의마다 동일 비용이 발생한다. |
| **Solution** | 정제 정적층(B) → 거버넌스 게이트(C) → 자가 진화 루프(A)를 단계적으로 결합한 **Self-Improving RAG**. `wiki_knowledge` 컬렉션을 신설하고, 기존 하이브리드 검색·관측 인프라(`ai_retrieval_source`)를 환류 신호로 재활용한다. |
| **Function/UX Effect** | 검색 노이즈↓·답변 일관성↑, 반복 질의 비용↓, 운영자 승인 위키 관리 UI 제공. 금융/정책 도메인의 보수적 동작 원칙을 위반하지 않는 human-in-the-loop 승인 흐름. |
| **Core Value** | "검색을 더 잘하기"가 아니라 "검색한 것을 기억하고 정제해 다음에 더 잘 답하기" — 지속 발전하는 지식베이스. |

---

## 1. Overview

### 1.1 Purpose

에이전트가 RAG·웹서치·대화에서 확보한 지식을 **검증 게이트를 거쳐 위키 형태로 누적·정제·재활용**하도록 만들어, 시간이 지날수록 답변 품질이 향상되는(지속 발전하는) 지식베이스를 구축한다.

### 1.2 Background

- 현재 시스템은 **단방향 읽기(Pull-only)** 구조다. 벡터 스토어는 추론 중 읽기 전용이고, 쓰기는 명시적 인제스트(`idt/src/application/ingest/ingest_use_case.py`)로만 발생한다.
- 대화 요약(`conversation/use_case.py`)은 만들어지지만 **KB로 환류되지 않으며**, 웹서치 결과(`web_search/tavily_tool.py`)는 1회성으로 `ai_retrieval_source`에 감사 로그로만 남는다.
- 결과적으로 시스템이 경험으로부터 학습하지 않아 "지속 발전이 어렵다". 자세한 진단은 분석 레포트(§1~2) 참조.
- 동시에 우리 구조(DDD 레이어 분리, LangGraph 동적 그래프, 하이브리드 검색 RRF 융합, 관측 테이블)는 환류 루프를 받을 토대가 절반 이상 갖춰져 있어 ROI가 높다.

### 1.3 Related Documents

- 분석 레포트: `docs/llm-wiki-knowledge-base-analysis-2026-06-28.md`
- 참조(업계): GraphRAG, Self-RAG, RAPTOR, MemGPT/Letta, HippoRAG, Reflexion
- 기존 핵심 코드: `idt/src/application/hybrid_search/use_case.py`, `idt/src/domain/agent_builder/rag_tool_config.py`, `idt/src/application/agent_builder/workflow_compiler.py`

---

## 2. Scope

### 2.1 In Scope

**Phase 1 — 위키화 정적층(B) [MVP]**
- [ ] `WikiArticle` 도메인 엔티티 + 검증 정책 신설 (`idt/src/domain/wiki/`)
- [ ] `DistillToWikiUseCase`: 원본 청크 군집 → LLM 정제/요약 → 위키 아티클 생성
- [ ] `wiki_knowledge` Qdrant 컬렉션 + ES 인덱스 + 리포지토리 신설
- [ ] `wiki_article` 테이블 마이그레이션 (`db-migration` 스킬)
- [ ] 위키 검색: `RagToolConfig.search_mode`에 위키 우선 + 원본 폴백 경로 추가

**Phase 2 — 거버넌스 게이트(C)**
- [ ] 위키 항목 `status`(draft/approved/deprecated) 라이프사이클
- [ ] `WikiReviewUseCase`: 승인/반려/폐기 워크플로
- [ ] 위키 관리·승인 프론트 UI (`idt_front/src/components/wiki/`)
- [ ] API 계약 동기화 (`api-cotract` 스킬)

**Phase 3 — 자가 진화 루프(A)**
- [ ] LangGraph `wiki_writer` 노드 추가 (`workflow_compiler.py` 확장)
- [ ] `WikiWriteBackUseCase`: "기억할 가치" 판단 → draft 후보 생성
- [ ] `ai_retrieval_source` 기여도 신호 기반 `confidence` 갱신/감쇠
- [ ] 모순 탐지(임베딩 유사도 + LLM 판정) 및 `valid_until` TTL

### 2.2 Out of Scope

- GraphRAG식 엔티티-관계 그래프 인덱싱 (후속 고도화 — MVP 제외)
- 멀티홉 추론용 HippoRAG 스타일 인덱싱 (후속)
- 위키 항목 자동 번역/다국어화
- Excel/Supervisor 경로 통합 (기존 메모리 노트와 동일하게 후속 분리)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `WikiArticle` 도메인 엔티티(title/content/source_type/status/confidence/source_refs/valid_until/version) + 검증 정책 | High | Pending |
| FR-02 | `DistillToWikiUseCase` — 원본 청크 → LLM 정제 → 위키 아티클 생성·임베딩 | High | Pending |
| FR-03 | `wiki_knowledge` 벡터/ES 컬렉션 + 리포지토리 + 마이그레이션 | High | Pending |
| FR-04 | 위키 우선 검색 + 원본 폴백 (RRF 가중치 조정 포함) | High | Pending |
| FR-05 | 위키 라이프사이클(draft→approved→deprecated) + `WikiReviewUseCase` | High | Pending |
| FR-06 | 위키 관리·승인 프론트 UI + API 동기화 | Medium | Pending |
| FR-07 | `wiki_writer` 노드 + `WikiWriteBackUseCase`(기억 가치 판단, draft 생성) | Medium | Pending |
| FR-08 | `confidence` 환류 갱신/감쇠 (`ai_retrieval_source` 신호 기반) | Medium | Pending |
| FR-09 | 모순 탐지 + `valid_until` TTL 만료 재검증 배치 | Low | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | 위키 우선 검색 추가로 인한 응답 지연 < +150ms (p95) | `ai_run_step` 단계별 타이밍 |
| Safety | 자동 생성 지식은 승인 전 검색 비노출 또는 confidence 가중치↓ | 거버넌스 게이트 단위 테스트 |
| Traceability | 모든 위키 항목 `source_refs` 필수(출처 없는 항목 KB 진입 금지) | 도메인 정책 검증 |
| Quality | 신규 모듈 테스트 커버리지 ≥ 80%, TDD Red→Green | pytest / `verify-tdd` 스킬 |
| Architecture | DDD 레이어 의존성 규칙 준수 | `verify-architecture` 스킬 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] Phase별 기능 요구사항(FR) 구현 완료
- [ ] 신규 모듈 단위 테스트 작성 및 통과 (TDD)
- [ ] DDD 레이어/로깅 규칙 검증 통과 (`verify-architecture`, `verify-logging`)
- [ ] 백엔드 ↔ 프론트 API 계약 동기화 (`api-cotract`)
- [ ] 마이그레이션 파일 생성 및 적용 (`db-migration`)

### 4.2 Quality Criteria

- [ ] 테스트 커버리지 ≥ 80% (신규 모듈)
- [ ] lint/타입 에러 0
- [ ] Gap Analysis Match Rate ≥ 90%

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 환각 누적 (잘못된 지식 증폭) | High | Medium | C 게이트(draft 우선) + `source_refs` 필수 + 모순 탐지 (분석 레포트 §4-4) |
| 정제 LLM 토큰 비용 증가 | Medium | High | 변경분만 증분 재합성, 저빈도 배치 |
| 위키 vs 원본 검색 중복/혼란 | Medium | Medium | 위키 우선 + 원본 폴백, RRF 가중치 튜닝 |
| 사람 승인 병목 (C) | Medium | Medium | 고신뢰 자동승인 + 저신뢰만 사람 검토 하이브리드 |
| 금융/정책 도메인 오답 리스크 | High | Low | 보수적 기본값(draft), 감사 로그(기보유), 도메인 정책 강제 |
| 환류 루프 테스트 복잡도 | Medium | Medium | TDD 강제(`idt:tdd`) + `zero-script-qa` 로그 기반 검증 |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | 단순 구조 | 정적 사이트 | ☐ |
| **Dynamic** | 기능 모듈, BaaS | SaaS MVP | ☐ |
| **Enterprise** | 엄격한 레이어 분리, DDD | 복잡 아키텍처 | ☑ |

> 본 프로젝트 백엔드는 DDD 4-레이어(domain/application/infrastructure/api) 구조로 Enterprise 수준에 해당.

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 위키 저장소 | 기존 RAG 컬렉션 재사용 / 전용 컬렉션 신설 | **전용 `wiki_knowledge` 컬렉션** | 원본과 정제층 분리, 검색 가중치 독립 제어 |
| 검색 통합 | 새 툴 신설 / `search_mode` 확장 | **`search_mode` 확장 + 우선/폴백** | 기존 `RagToolConfig` 인터페이스 재사용, 최소 침습 |
| 환류 신호원 | 신규 수집 / 기존 관측 재활용 | **`ai_retrieval_source` 재활용** | 기여도 신호 이미 수집 중 |
| 거버넌스 | 전자동 / human-in-the-loop | **HITL 승인 게이트** | 금융/정책 도메인 보수적 원칙 (CLAUDE.md §1) |
| 정제 단위 | 문서 요약 / 명제(proposition) / RAPTOR 트리 | **Design에서 확정** (MVP는 문서 요약 권장) | 비용 vs 정밀도 트레이드오프 |
| 도입 순서 | 동시 / 단계적 | **B → C → A 단계적** | A는 C 게이트 없이 활성화 금지 |

### 6.3 Clean Architecture Approach

```
Selected Level: Enterprise (DDD)

신규/변경 폴더 (idt/):
┌─────────────────────────────────────────────────────┐
│ domain/wiki/            → WikiArticle, 정책 (신규)    │
│ application/wiki/        → Distill/Review/WriteBack    │
│                           UseCase (신규)              │
│ infrastructure/wiki/     → wiki_knowledge 리포지토리, │
│                           Qdrant/ES 어댑터 (신규)     │
│ domain/agent_builder/rag_tool_config.py → 검색모드확장│
│ application/agent_builder/workflow_compiler.py        │
│                          → wiki_writer 노드 (확장)    │
│ db/migration/V0xx__create_wiki_article.sql (신규)     │
└─────────────────────────────────────────────────────┘
신규 폴더 (idt_front/):
  src/components/wiki/  → 위키 관리·승인 UI
  src/services/, src/hooks/, src/types/ → API 연동
```

---

## 7. Convention Prerequisites

### 7.1 Existing Project Conventions

- [x] `CLAUDE.md` 코딩 컨벤션 존재 (루트 + `idt/` + `idt_front/`)
- [x] DDD 레이어 의존성 규칙 (`verify-architecture` 스킬)
- [x] 로깅 규칙 LOG-001 (`verify-logging` 스킬)
- [x] TDD 강제 (`idt:tdd`, `idt_front:tdd`, `verify-tdd`)
- [x] API 계약 동기화 규칙 (CLAUDE.md §4-1, `api-cotract` 스킬)

### 7.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| 위키 컬렉션 네이밍 | missing | `wiki_knowledge` 컬렉션/ES 인덱스 규칙 | High |
| source_type/status enum | missing | 도메인 enum 정의 | High |
| confidence 산정 규칙 | missing | 환류 신호 → 점수 매핑 | Medium |
| TTL 정책 | missing | 출처별 만료 기준(웹서치 만료 권장) | Medium |

### 7.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| `WIKI_COLLECTION_NAME` | 위키 전용 Qdrant 컬렉션명 | Server | ☑ |
| `WIKI_DISTILL_MODEL` | 정제용 LLM 모델 (기본 claude/openai) | Server | ☑ |
| `WIKI_AUTO_APPROVE_THRESHOLD` | 자동 승인 confidence 임계값 | Server | ☑ |

### 7.4 Pipeline Integration

| Phase | Status | Document Location | Command |
|-------|:------:|-------------------|---------|
| Phase 1 (Schema) | ☐ | Design에서 wiki 스키마 정의 | `/pdca design` |
| Phase 2 (Convention) | ☐ | 위 7.2 항목 확정 | `/pdca design` |

---

## 8. Next Steps

1. [ ] Design 문서 작성 (`/pdca design llm-wiki-knowledge-base`) — 도메인 모델·노드·마이그레이션 상세
2. [ ] **Plan 확정 결정사항**: (a) Phase 1 파일럿 범위 — 전체 컬렉션 vs 특정 에이전트 한정, (b) 정제 단위 — 문서요약/명제/RAPTOR, (c) GraphRAG 포함 여부(권장: MVP 제외)
3. [ ] Design 승인 후 `idt:tdd`로 Phase 1(B)부터 Red→Green 구현

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-06-28 | 분석 레포트 기반 초안 작성 | 배상규 |
