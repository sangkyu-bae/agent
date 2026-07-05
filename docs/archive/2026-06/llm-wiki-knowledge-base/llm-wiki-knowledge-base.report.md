---
template: report
version: 1.1
feature: llm-wiki-knowledge-base
date: 2026-06-30
author: 배상규
project: sangplusbot
---

# llm-wiki-knowledge-base Completion Report

> **Status**: Complete (Phase 1+2 풀스택) / Phase 3 차기 사이클
>
> **Project**: sangplusbot
> **Author**: 배상규
> **Completion Date**: 2026-06-30
> **PDCA Cycle**: #1 (Plan→Design→Do→Check×3→Act)

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | llm-wiki-knowledge-base (Self-Improving RAG / LLM Wiki) |
| Start Date | 2026-06-28 |
| End Date | 2026-06-30 |
| Duration | 3일 (Plan→Report) |
| Scope | Phase 1(B 정제) + Phase 2(C 거버넌스) 풀스택 + Step6 런타임 검색 와이어링 |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────────────────┐
│  Scoped Completion (Phase 1+2 풀스택):  ~98%  ✅          │
│  Overall (전체 설계, Phase 3 포함):     ~78%  (A 차기)    │
├─────────────────────────────────────────────────────────┤
│  ✅ 완료: 구현 13스텝(domain~UI~상세편집) + 와이어링 + 계약 │
│  ⏳ 차기: Phase 3(A 자가진화) 4항목 + ES BM25 색인         │
│  테스트: 백엔드 105건 + 프론트 15건 (격리 실행 전부 통과)  │
└─────────────────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 지식베이스가 Pull-only라 대화·웹서치·검색에서 얻은 지식이 휘발 → 시간이 지나도 시스템이 똑똑해지지 않음("지속 발전 불가"). |
| **Solution** | "검색→정제→기억" 환류의 토대 구축: 원본 청크를 LLM이 위키로 정제(B), 승인 게이트로 검증(C), 승인 위키를 에이전트 검색에 우선 노출(Step6). DDD 4-layer + LangGraph tool 무수정 래핑으로 최소 침습. |
| **Function/UX Effect** | `wiki_knowledge` 컬렉션 신설 + 8개 REST 엔드포인트 + `/admin/wiki` 관리 UI(목록·상세·편집·승인/반려/폐기/복구) + 에이전트 빌더 "위키 우선 검색" 토글. 출처 불변식·보수적 기본값(draft)·만료(TTL)로 환각 누적 방어. 백엔드 105 + 프론트 15 테스트. |
| **Core Value** | "검색을 더 잘하기"가 아니라 "검색한 것을 기억하고 정제해 다음에 더 잘 답하기" — 금융/정책 도메인에 맞춘 human-in-the-loop 거버넌스로 신뢰성 있는 자가 개선 RAG의 B+C 구간 완성. |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| 분석 | [분석 레포트](../llm-wiki-knowledge-base-analysis-2026-06-28.md) | ✅ |
| Plan | [plan](../01-plan/features/llm-wiki-knowledge-base.plan.md) | ✅ |
| Design | [design](../02-design/features/llm-wiki-knowledge-base.design.md) | ✅ |
| Do | [do](../02-design/features/llm-wiki-knowledge-base.do.md) | ✅ |
| Check | [analysis v0.4](../03-analysis/llm-wiki-knowledge-base.analysis.md) | ✅ |
| Act | 현재 문서 | ✅ |

---

## 3. Completed Items

### 3.1 Functional Requirements (Plan FR 대비)

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| FR-01 | WikiArticle 도메인 엔티티 + 정책 | ✅ | 출처 불변식·상태전이 화이트리스트 |
| FR-02 | DistillToWikiUseCase (정제) | ✅ | + WikiDistiller/SourceProvider 어댑터 |
| FR-03 | wiki_knowledge 컬렉션 + repo + 마이그레이션 | ✅ | MySQL(SoT)+Qdrant, V036 |
| FR-04 | 위키 우선 검색 + 폴백 | ✅ | WikiFirstSearch + RunScopedWikiSearch 런타임 연결 |
| FR-05 | 라이프사이클 + WikiReviewUseCase | ✅ | approve/reject/deprecate/restore/edit |
| FR-06 | 위키 관리 프론트 UI + API 동기화 | ✅ | 목록·상세·편집, api-cotract |
| FR-07~09 | Phase 3(A) wiki_writer·WriteBack·confidence·TTL | ⏳ 차기 | 자가진화 별도 사이클 |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|--------|
| DDD 레이어 의존성 | domain 외부의존 0 | 0 | ✅ |
| 테스트(신규 모듈) | TDD Red→Green | 백엔드 105 + 프론트 15 | ✅ |
| 보안/거버넌스 | 자동생성 승인 전 비노출 + Admin RBAC | draft 게이트 + require_role | ✅ |
| 출처 추적 | source_refs 필수 | 도메인 + DB JSON NOT NULL 이중 | ✅ |

### 3.3 Deliverables

| Deliverable | Location | Status |
|-------------|----------|--------|
| 도메인 | `idt/src/domain/wiki/` | ✅ |
| 애플리케이션 | `idt/src/application/wiki/` (distill/review/query/search/run-scoped) | ✅ |
| 인프라 | `idt/src/infrastructure/wiki/` (repo/distiller/source_provider) | ✅ |
| API | `idt/src/api/routes/wiki_router.py` + main.py DI | ✅ |
| 마이그레이션 | `idt/db/migration/V036__create_wiki_article.sql` | ✅ |
| 프론트 | `idt_front/src/{types,services,hooks}/wiki*` + `pages/WikiPage/` | ✅ |

---

## 4. Incomplete Items

### 4.1 Carried Over to Next Cycle

| Item | Reason | Priority |
|------|--------|----------|
| Phase 3(A): wiki_writer 노드 + WikiWriteBackUseCase | "진짜 자가진화"는 별도 마일스톤 | High |
| confidence 환류 (ai_retrieval_source 기여 신호) | Phase 3 의존 | Medium |
| valid_until TTL 만료 재검증 배치 | Phase 3 의존 | Medium |
| 위키 본문 ES BM25 색인 | 현재 검색 경로는 벡터(search_similar) | Low |
| 설계 문서 싱크 5건 | 코드 영향 없음(표기 정정) | Low |

---

## 5. Quality Metrics

### 5.1 Final Analysis Results (Check 추이)

| Metric | Target | Final | 추이 |
|--------|--------|-------|------|
| Scoped Match Rate | 90% | **98%** | 95(v0.1)→92(v0.2)→94(v0.3)→98(v0.4) |
| Architecture/DDD | 준수 | ~97% | domain 순수성 검증 |
| API-Contract(BE↔FE) | 일치 | ~99% | 8 엔드포인트·필드 완전 일치 |
| Critical 결함 | 0 | 0 | ✅ |

### 5.2 Resolved Issues (Check에서 발견 → 수정)

| Issue | Resolution | Result |
|-------|------------|--------|
| 🔴 update() 중복키 INSERT (거버넌스 쓰기 전부 깨짐) | load-then-mutate로 변경 + 실세션 통합테스트 | ✅ |
| 🟠 거버넌스 엔드포인트 RBAC 부재 | require_role("admin") + 403 테스트 | ✅ |
| 🔵 죽어있던 useUpdateArticle (편집 UI 없음) | WikiDetailPanel 구현 + 연결 | ✅ |
| 🟡 reviewer/editor 빈값 가드 / 상태 라벨 | 버튼 비활성 + 한글 라벨 | ✅ |

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- **분석 레포트 선행** → Plan/Design 품질↑, "B→C→A 단계적 도입" 전략이 끝까지 일관.
- **TDD 철저** → update() 영속 버그를 실세션 통합테스트가 잡음(유닛 모킹이 가린 결함). gap-detector가 HIGH 결함을 조기 포착.
- **무수정 래핑 설계** → RunScopedWikiSearch가 tool/HybridSearch를 안 건드리고 통합 → 회귀 0.

### 6.2 What Needs Improvement (Problem)

- 1차 분석이 6스텝만 봐서 95%로 과대평가 → 범위 확장 후 83%로 드러남. **스코프를 처음부터 명시**해야 함.
- 모킹 위주 유닛테스트가 실DB 영속 버그를 가림 → **리포지토리는 실세션 통합테스트 병행** 필요.
- 설계 문서와 구현 간 표기 드리프트(프리픽스/계약) 누적 → 문서 싱크를 즉시 반영하는 습관 필요.

### 6.3 What to Try Next (Try)

- Phase 3 자가진화는 환각 누적 위험이 크므로 **C 게이트 통과 후에만** 활성화(설계 원칙 유지).
- 프론트 테스트 Windows flakiness → `--pool=threads --no-file-parallelism` 표준화(메모리 반영 완료).

---

## 8. Next Steps

### 8.1 Immediate

- [ ] 설계 문서 싱크 5건 반영 (`/api/v1/wiki` 프리픽스, restore/8엔드포인트, distill 동기계약, 에러 envelope, VARCHAR(36))
- [ ] 로컬 통합 검증: flyway migrate(V036) + 실제 distill→approve→검색 E2E

### 8.2 Next PDCA Cycle

| Item | Priority |
|------|----------|
| Phase 3(A) 자가진화: wiki_writer·WriteBack·confidence 환류·TTL 배치 | High |
| 위키 본문 ES BM25 색인 (BM25까지 위키 우선) | Low |

---

## 9. Changelog

### v1.0.0 (2026-06-30)

**Added:**
- LLM Wiki 도메인/정제/거버넌스/검색 풀스택 (Phase 1+2)
- `wiki_article` 테이블(V036), `wiki_knowledge` 벡터 컬렉션
- 8개 REST 엔드포인트 + `/admin/wiki` 관리 UI(목록·상세·편집)
- 에이전트 빌더 `use_wiki_first` 토글 + 런타임 위키 우선 검색

**Fixed:**
- update() 중복키 INSERT (load-then-mutate)
- 거버넌스 엔드포인트 Admin RBAC

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-06-30 | Phase 1+2 풀스택 완료 보고서 | 배상규 |
