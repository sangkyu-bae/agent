---
template: do
version: 1.0
feature: llm-wiki-knowledge-base
date: 2026-06-28
author: 배상규
project: sangplusbot
---

# llm-wiki-knowledge-base Implementation Guide

> **Summary**: Self-Improving RAG(LLM Wiki) Phase 1(B, 단일 에이전트 한정 문서/섹션 요약 정제층)부터 TDD로 구현하기 위한 Do 가이드.
>
> **Project**: sangplusbot
> **Author**: 배상규
> **Date**: 2026-06-28
> **Status**: In Progress
> **Design Doc**: [llm-wiki-knowledge-base.design.md](./llm-wiki-knowledge-base.design.md)
> **Plan Doc**: [llm-wiki-knowledge-base.plan.md](../../01-plan/features/llm-wiki-knowledge-base.plan.md)

---

## 1. Pre-Implementation Checklist

### 1.1 Documents Verified

- [x] Plan 검토: `docs/01-plan/features/llm-wiki-knowledge-base.plan.md`
- [x] Design 검토: `docs/02-design/features/llm-wiki-knowledge-base.design.md`
- [x] 컨벤션 숙지: 루트 `CLAUDE.md` + `idt/CLAUDE.md` + `idt_front/CLAUDE.md`

### 1.2 Environment Ready

- [ ] `idt/` 백엔드 의존성 설치 (기존 가상환경 활용)
- [ ] `idt_front/` `npm install --legacy-peer-deps` (메모리: peer-deps 필요)
- [ ] Qdrant / Elasticsearch / MySQL 로컬 기동 (기존 RAG 인프라 재사용)
- [ ] `.env` 신규 변수: `WIKI_COLLECTION_NAME`, `WIKI_DISTILL_MODEL`, `WIKI_AUTO_APPROVE_THRESHOLD`

---

## 2. Implementation Order

> Design §11.2 순서를 따른다. **TDD 강제**: 각 단계는 Red(실패 테스트) → Green(구현) → Refactor.

### 2.1 Phase 1 (B) — 정제 정적층 [MVP, 우선]

| # | Task | File/Location | TDD | Status |
|:--:|------|---------------|:---:|:------:|
| 1 | 도메인 엔티티·enum·정책 | `idt/src/domain/wiki/entity.py`, `policies.py` | `idt:tdd` | ☐ |
| 2 | repo 인터페이스 | `idt/src/application/repositories/wiki_repository.py` | - | ☐ |
| 3 | DB 마이그레이션 | `idt/db/migration/V0xx__create_wiki_article.sql` | `db-migration` | ☐ |
| 4 | repo 구현(Qdrant+ES+MySQL) + SQLAlchemy 모델 | `idt/src/infrastructure/wiki/` | `idt:tdd` | ☐ |
| 5 | `DistillToWikiUseCase` | `idt/src/application/wiki/distill_use_case.py` | `idt:tdd` | ☐ |
| 6 | 검색 확장(위키 우선+폴백) | `idt/src/application/hybrid_search/use_case.py` | `idt:tdd` | ☐ |
| 7 | `wiki_router`(distill/목록/상세) | `idt/src/api/routes/wiki_router.py` | `idt:tdd` | ☐ |
| 8 | 프론트 목록/상세 UI + 타입/서비스/훅 | `idt_front/src/components/wiki/` 등 | `idt_front:tdd` | ☐ |
| 9 | API 계약 동기화 | `api-cotract` 스킬 | - | ☐ |

### 2.2 Phase 2 (C) — 거버넌스 게이트

| # | Task | File/Location | Status |
|:--:|------|---------------|:------:|
| 10 | `WikiReviewUseCase` + 상태전이 검증 | `idt/src/application/wiki/review_use_case.py` | ☐ |
| 11 | approve/reject/deprecate/edit 엔드포인트 | `wiki_router.py` | ☐ |
| 12 | 승인 패널 UI + Admin RBAC 가드 | `idt_front/src/components/wiki/` | ☐ |

### 2.3 Phase 3 (A) — 자가 진화

| # | Task | File/Location | Status |
|:--:|------|---------------|:------:|
| 13 | `wiki_writer` 노드 | `idt/src/application/agent_builder/workflow_compiler.py` | ☐ |
| 14 | `WikiWriteBackUseCase` | `idt/src/application/wiki/write_back_use_case.py` | ☐ |
| 15 | confidence 환류 + TTL 만료 배치 | `application/wiki/` | ☐ |

---

## 3. Key Files to Create/Modify

### 3.1 New Files (Phase 1)

| File Path | Purpose |
|-----------|---------|
| `idt/src/domain/wiki/entity.py` | `WikiArticle`, `WikiSourceType`, `WikiStatus` |
| `idt/src/domain/wiki/policies.py` | `WikiPolicy` (불변식/상태전이) |
| `idt/src/application/repositories/wiki_repository.py` | repo 인터페이스 |
| `idt/src/application/wiki/distill_use_case.py` | 정제 UseCase |
| `idt/src/infrastructure/wiki/wiki_repository.py` | Qdrant+ES+MySQL 구현 |
| `idt/src/infrastructure/wiki/models.py` | SQLAlchemy 모델 |
| `idt/src/api/routes/wiki_router.py` | API 라우터 |
| `idt/db/migration/V0xx__create_wiki_article.sql` | 마이그레이션 |
| `idt_front/src/types/wiki.ts` | 타입 |
| `idt_front/src/services/wikiService.ts` | API 클라이언트 |
| `idt_front/src/hooks/useWikiArticles.ts` | TanStack Query 훅 |
| `idt_front/src/components/wiki/WikiManagePage.tsx` 외 | UI |

### 3.2 Files to Modify

| File Path | Changes | Reason |
|-----------|---------|--------|
| `idt/src/application/hybrid_search/use_case.py` | 위키 우선 검색 + 폴백 | 검색 통합 |
| `idt/src/domain/agent_builder/rag_tool_config.py` | 위키 검색 옵션 반영 | 검색 모드 |
| `idt/src/api/main.py` | wiki_router 등록 | 라우팅 |
| `idt/.env.example` | WIKI_* 변수 추가 | 환경변수 |
| `idt_front/src/constants/api.ts` | wiki 엔드포인트 상수 | API 계약 |
| `idt_front/src/App.tsx` | 위키 관리 라우트 | 네비게이션 |

---

## 4. Dependencies

기존 스택(Qdrant SDK, elasticsearch, SQLAlchemy, LangChain, OpenAI/Anthropic, TanStack Query) 재사용. **신규 패키지 불필요** 예상. 정제용 LLM은 기존 `llm_factory`/`embedding_factory` 활용.

```bash
# 신규 의존성 없음. 프론트는 기존 환경:
# (idt_front/) npm install --legacy-peer-deps
```

---

## 5. Implementation Notes

### 5.1 Design Decisions Reference

| Decision | Choice | Rationale |
|----------|--------|-----------|
| 파일럿 범위 | 단일 에이전트 한정 (agent_id 스코프) | 리스크·비용 최소화 |
| 정제 단위 | 문서/섹션 요약 | 구현 난이도·비용 저렴 (MVP) |
| GraphRAG | 제외 | 후속 고도화 |
| 검색 통합 | `HybridSearchUseCase` 확장(우선+폴백) | 기존 인터페이스 재사용 |
| 거버넌스 | HITL 승인(draft→approved) | 금융/정책 보수적 원칙 |

### 5.2 Code Patterns to Follow (백엔드)

```python
# UseCase 패턴: 생성자 DI, execute() 단일 진입점, 도메인 정책으로 검증
class DistillToWikiUseCase:
    def __init__(self, wiki_repo, search_uc, llm, embedder):
        self._wiki_repo = wiki_repo
        ...
    async def execute(self, agent_id: str, collection_name: str, max_articles: int) -> list[WikiArticle]:
        # 1) 원본 청크 조회  2) 군집  3) LLM 요약  4) WikiPolicy.validate_for_creation  5) 저장
        ...
```

### 5.3 Things to Avoid

- [ ] 하드코딩(컬렉션명/모델명 → 환경변수·설정)
- [ ] 도메인 레이어에서 인프라 import (DDD 위반 — `verify-architecture`)
- [ ] source_refs 없는 항목 저장 (불변식 위반)
- [ ] 로깅 누락 (LOG-001 — `verify-logging`)

### 5.4 Architecture Checklist (Enterprise / DDD)

- [ ] Domain은 외부 의존 0, Infrastructure → Domain만 의존
- [ ] Application은 repo 인터페이스에만 의존(구현은 DI 주입)
- [ ] `verify-architecture`로 레이어 의존성 검증

### 5.7 API Checklist

- [ ] 응답 포맷: 성공 `{ data }` / 에러 `{ error: { code, message, details? } }`
- [ ] 에러코드: INVALID_TRANSITION, MISSING_SOURCE_REFS, WIKI_NOT_FOUND 등 (Design §6.1)
- [ ] HTTP 메서드: 조회 GET, 정제 POST, 상태전이 PATCH

---

## 6. Testing Checklist

### 6.1 핵심 테스트 (Design §8.2)

- [ ] distill → draft N개, 모두 source_refs 보유
- [ ] draft→approved 전이 성공 / approved→draft INVALID_TRANSITION
- [ ] source_refs 빈 항목 생성 예외
- [ ] approved만 검색 노출, draft 제외, 폴백 동작
- [ ] valid_until 만료 항목 검색 제외

### 6.2 Code Quality

- [ ] pytest 통과 (Windows 이벤트 루프 산발 실패 시 격리 실행 — 메모리 노트)
- [ ] vitest `--pool=threads` (메모리 노트)
- [ ] lint/타입 에러 0, 커버리지 ≥ 80%

---

## 7. Progress Tracking

| Date | Tasks Completed | Notes |
|------|-----------------|-------|
| 2026-06-28 | Do 가이드 작성, 구현 착수 준비 | Phase 1 Step 1부터 시작 |

---

## 8. Post-Implementation

### 8.1 Self-Review Checklist

- [ ] Phase 1 FR(01~04) 구현 완료
- [ ] 컨벤션·레이어·로깅 검증 통과
- [ ] API 계약 동기화 완료
- [ ] 에러 처리/타입 정의 완료

### 8.2 Ready for Check Phase

```bash
/pdca analyze llm-wiki-knowledge-base
```

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-06-28 | 구현 착수 가이드 초안 | 배상규 |
