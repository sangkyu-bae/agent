---
template: design
version: 1.2
feature: llm-wiki-knowledge-base
date: 2026-06-28
author: 배상규
project: sangplusbot
---

# llm-wiki-knowledge-base Design Document

> **Summary**: Pull-only 지식베이스에 "검색→정제→기억" 환류 루프를 더한 Self-Improving RAG(LLM Wiki)의 DDD 설계. Phase 1은 단일 에이전트 한정 문서/섹션 요약 정제층(B)으로 시작한다.
>
> **Project**: sangplusbot
> **Version**: feature/mcp-server-registry 기반
> **Author**: 배상규
> **Date**: 2026-06-28
> **Status**: Draft
> **Planning Doc**: [llm-wiki-knowledge-base.plan.md](../../01-plan/features/llm-wiki-knowledge-base.plan.md)
> **Analysis Report**: [llm-wiki-knowledge-base-analysis-2026-06-28.md](../../llm-wiki-knowledge-base-analysis-2026-06-28.md)

### 확정된 Plan 결정사항 (Design 입력)

| 결정 항목 | 선택 | 영향 |
|-----------|------|------|
| Phase 1 파일럿 범위 | **특정 에이전트 한정** | 위키 컬렉션을 agent_id로 스코프, 리스크·비용 최소화 |
| 위키 정제 단위 | **문서/섹션 요약** | 청크 군집 → LLM 요약 아티클 (명제/RAPTOR는 후속) |
| GraphRAG 포함 여부 | **MVP 제외** | 엔티티-관계 그래프는 후속 고도화 |

---

## 1. Overview

### 1.1 Design Goals

1. 기존 하이브리드 검색·관측 인프라를 **최소 침습**으로 확장해 "정제된 위키 지식층"을 추가한다.
2. 자동 생성 지식이 검증(승인) 없이 답변에 노출되지 않도록 **거버넌스 게이트**를 도메인 규칙으로 강제한다.
3. `ai_retrieval_source`의 기여도 신호를 **환류 신호원**으로 재활용해 `confidence`를 갱신한다.
4. DDD 레이어 의존성 규칙을 준수하며 `domain/wiki`는 외부 의존 없는 순수 도메인으로 유지한다.

### 1.2 Design Principles

- **Single Responsibility**: Distill(정제) / Review(거버넌스) / WriteBack(환류)을 독립 UseCase로 분리.
- **보수적 기본값 (Fail-safe)**: 자동 생성분은 `status=draft`로만 시작, 승인 전 검색 비노출. (금융/정책 도메인 원칙, CLAUDE.md §1)
- **출처 불변식 (Invariant)**: `source_refs`가 비어 있으면 위키 항목을 생성할 수 없다.
- **기존 인터페이스 재사용**: 새 검색 툴을 만들지 않고 `RagToolConfig`/`HybridSearchUseCase`를 확장.

---

## 2. Architecture

### 2.1 Component Diagram

```
                       LangGraph (workflow_compiler.py)
   ┌──────────────────────────────────────────────────────────┐
   │  Supervisor → [WikiSearch worker] → ... → wiki_writer 노드 │
   └──────────────────────────────────────────────────────────┘
        │ (검색)                              │ (환류, Phase 3)
        ▼                                     ▼
 ┌───────────────────┐               ┌────────────────────┐
 │ HybridSearchUseCase│  ← 확장 →     │ WikiWriteBackUseCase│ (application/wiki)
 │ (wiki 우선+폴백)   │               └─────────┬──────────┘
 └─────────┬─────────┘                         │ draft 후보
           │                                   ▼
           ▼                         ┌────────────────────┐
 ┌───────────────────┐              │ WikiReviewUseCase   │ (거버넌스 게이트, C)
 │ wiki_knowledge     │◀── 승인분만 ─┤ draft→approved      │
 │ (Qdrant + ES)      │              └────────────────────┘
 └───────────────────┘                         ▲
           ▲                                    │ 정제 생성 (B)
           │                          ┌────────────────────┐
           └──────────────────────────┤ DistillToWikiUseCase│ (application/wiki)
                                       └─────────┬──────────┘
                                                 │ 원본 청크
                                       ┌────────────────────┐
                                       │ 기존 RAG 컬렉션      │
                                       │ (hybrid_search)     │
                                       └────────────────────┘
```

### 2.2 Data Flow

**Phase 1 (B) — 정제 (배치/온디맨드)**
```
대상 agent 지정 → 원본 청크 조회(컬렉션 스코프) → 군집/그룹핑
  → LLM 요약(WIKI_DISTILL_MODEL) → WikiArticle(status=draft) 생성
  → 임베딩 → wiki_knowledge upsert + ES 인덱싱
```

**Phase 2 (C) — 승인 (운영자)**
```
운영자 위키 목록 조회 → draft 검토 → approve / reject / deprecate
  → status 전이 (도메인 정책 검증) → approved만 검색 노출
```

**Phase 3 (A) — 환류 (추론 후)**
```
에이전트 응답 완료 → wiki_writer 노드: "기억할 가치" 판단(LLM)
  → 가치 있으면 WikiArticle(source_type=conversation, status=draft) 생성
  → confidence: ai_retrieval_source 기여 신호로 후속 갱신/감쇠
```

**검색 (런타임)**
```
worker 검색 → wiki_knowledge(approved, agent 스코프) 우선 검색
  → 결과 부족 시 기존 RAG 컬렉션 폴백 → RRF 융합
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `DistillToWikiUseCase` | `WikiArticleRepository`, EmbeddingFactory, LLMFactory, 기존 RAG 검색 | 원본→정제 아티클 |
| `WikiReviewUseCase` | `WikiArticleRepository`, `WikiPolicy` | status 전이 검증 |
| `WikiWriteBackUseCase` | `WikiArticleRepository`, LLMFactory | 추론 결과 환류 |
| `HybridSearchUseCase`(확장) | `WikiArticleRepository`(읽기), 기존 Qdrant/ES | 위키 우선 검색 |
| `wiki_writer` 노드 | `WikiWriteBackUseCase` | 그래프 환류 훅 |
| `WikiArticleRepository`(infra) | Qdrant, Elasticsearch, MySQL | 영속화 |

---

## 3. Data Model

### 3.1 Entity Definition

```python
# idt/src/domain/wiki/entity.py  (순수 도메인, 외부 의존 없음)
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

class WikiSourceType(str, Enum):
    DISTILLED = "distilled"        # B: 원본 정제
    CONVERSATION = "conversation"  # A: 대화 환류
    WEBSEARCH = "websearch"        # A: 웹서치 환류
    HUMAN = "human"                # C: 사람 작성

class WikiStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    DEPRECATED = "deprecated"

@dataclass
class WikiArticle:
    id: str
    agent_id: str                  # Phase1 스코프 키 (특정 에이전트 한정)
    title: str
    content: str                   # 정제된 본문 (문서/섹션 요약)
    source_type: WikiSourceType
    source_refs: list[str]         # 출처 추적 (필수, 비면 생성 불가)
    status: WikiStatus = WikiStatus.DRAFT
    confidence: float = 0.5        # 0~1, 환류 신호로 갱신
    valid_until: datetime | None = None  # TTL (websearch 권장)
    version: int = 1
    editor_id: str | None = None
    reviewer_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
```

### 3.2 도메인 정책 (불변식)

```python
# idt/src/domain/wiki/policies.py
class WikiPolicy:
    TITLE_MAX = 200
    CONTENT_MAX = 8000
    SOURCE_REFS_MIN = 1            # 출처 불변식
    CONFIDENCE_MIN, CONFIDENCE_MAX = 0.0, 1.0

    # 허용된 상태 전이만 통과
    ALLOWED_TRANSITIONS = {
        WikiStatus.DRAFT:      {WikiStatus.APPROVED, WikiStatus.DEPRECATED},
        WikiStatus.APPROVED:   {WikiStatus.DEPRECATED},
        WikiStatus.DEPRECATED: {WikiStatus.APPROVED},   # 복구
    }

    @classmethod
    def validate_for_creation(cls, article: WikiArticle) -> None:
        # title/content 길이, source_refs 최소 1개, confidence 범위 검증
        ...

    @classmethod
    def validate_transition(cls, current: WikiStatus, target: WikiStatus) -> None:
        # ALLOWED_TRANSITIONS 위반 시 예외
        ...
```

### 3.3 Database Schema

```sql
-- db/migration/V0xx__create_wiki_article.sql  (Flyway, db-migration 스킬로 생성)
CREATE TABLE wiki_article (
    id            VARCHAR(64)  NOT NULL,
    agent_id      VARCHAR(64)  NOT NULL,
    title         VARCHAR(200) NOT NULL,
    content       TEXT         NOT NULL,
    source_type   VARCHAR(20)  NOT NULL,
    source_refs   JSON         NOT NULL,
    status        VARCHAR(20)  NOT NULL DEFAULT 'draft',
    confidence    DECIMAL(4,3) NOT NULL DEFAULT 0.500,
    valid_until   DATETIME     NULL,
    version       INT          NOT NULL DEFAULT 1,
    editor_id     VARCHAR(64)  NULL,
    reviewer_id   VARCHAR(64)  NULL,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_agent_status (agent_id, status),
    KEY idx_valid_until (valid_until)
);
```

> 벡터/역색인 본문은 `wiki_knowledge` Qdrant 컬렉션 + ES 인덱스에 저장(임베딩 + content). MySQL은 메타데이터·라이프사이클의 SoT(Source of Truth).

---

## 4. API Specification

> 백엔드 변경 시 프론트 타입 동기화 필수 (CLAUDE.md §4-1, `api-cotract` 스킬). 엔드포인트 상수: `idt_front/src/constants/api.ts`.

### 4.1 Endpoint List (신규 라우터 `idt/src/api/routes/wiki_router.py`)

| Method | Path | Description | Auth | Phase |
|--------|------|-------------|------|:---:|
| POST | `/api/wiki/distill` | 특정 agent 대상 정제 실행(배치 트리거) | Admin | 1 |
| GET | `/api/wiki` | 위키 목록 (agent_id/status 필터, 페이지네이션) | Required | 1 |
| GET | `/api/wiki/{id}` | 위키 상세 | Required | 1 |
| PATCH | `/api/wiki/{id}/approve` | draft→approved | Admin | 2 |
| PATCH | `/api/wiki/{id}/reject` | draft→deprecated | Admin | 2 |
| PATCH | `/api/wiki/{id}/deprecate` | approved→deprecated | Admin | 2 |
| PUT | `/api/wiki/{id}` | 내용 수정 (사람 편집, version++) | Admin | 2 |

### 4.2 Detailed Specification

#### `POST /api/wiki/distill`

**Request:**
```json
{
  "agent_id": "agent_123",
  "collection_name": "policy_docs",
  "max_articles": 50
}
```

**Response (202 Accepted):**
```json
{
  "job_id": "distill_job_456",
  "agent_id": "agent_123",
  "status": "running",
  "created_count": 0
}
```

#### `PATCH /api/wiki/{id}/approve`

**Response (200 OK):**
```json
{
  "id": "wiki_789",
  "status": "approved",
  "reviewer_id": "user_admin",
  "version": 1,
  "updated_at": "2026-06-28T00:00:00Z"
}
```

**Error Responses:**
- `400`: 허용되지 않은 상태 전이 (WikiPolicy.validate_transition 실패)
- `401/403`: 인증/권한 (Admin RBAC)
- `404`: 위키 항목 없음

---

## 5. UI/UX Design

### 5.1 Screen Layout (`idt_front/src/components/wiki/`)

```
┌──────────────────────────────────────────────────┐
│ Wiki 관리           [에이전트 ▼] [상태 ▼] [정제실행]│
├──────────────────────────────────────────────────┤
│ ☐ title          source  status   conf  updated   │
│ ─────────────────────────────────────────────────│
│ 여신 한도 산정…  distilled draft   0.50  06-28  [▸]│  → 행 클릭 시
│ 정책 자금 금리…  distilled approved 0.82  06-27  [▸]│    상세/승인 패널
├──────────────────────────────────────────────────┤
│ [상세 패널] content 미리보기 / source_refs 링크    │
│            [승인] [반려] [폐기] [편집]              │
└──────────────────────────────────────────────────┘
```

### 5.2 User Flow

```
관리자 로그인 → Wiki 관리 → 에이전트 선택 → [정제 실행]
  → draft 목록 검토 → 상세 확인(출처 추적) → [승인]/[반려]
```

### 5.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `WikiManagePage` | `src/components/wiki/` | 목록 + 필터 + 정제 트리거 |
| `WikiArticleTable` | `src/components/wiki/` | 위키 목록 테이블 |
| `WikiDetailPanel` | `src/components/wiki/` | 상세 + 승인/반려/편집 (`RagConfigPanel` 패턴 재사용) |
| `useWikiArticles` | `src/hooks/` | TanStack Query 조회 |
| `wikiService` | `src/services/` | API 클라이언트 |

---

## 6. Error Handling

### 6.1 Error Code Definition

| Code | Message | Cause | Handling |
|------|---------|-------|----------|
| 400 | INVALID_TRANSITION | 허용되지 않은 status 전이 | 클라이언트에 가능한 액션만 노출 |
| 400 | MISSING_SOURCE_REFS | source_refs 비어 정제/생성 시도 | 정제 파이프라인에서 항목 스킵 + 로그 |
| 403 | FORBIDDEN | 비관리자 승인 시도 | 권한 안내 |
| 404 | WIKI_NOT_FOUND | 잘못된 id | 404 표시 |
| 409 | DISTILL_IN_PROGRESS | 동일 agent 정제 중복 실행 | 기존 job 안내 |
| 500 | DISTILL_FAILED | LLM/벡터 저장 실패 | 로그(LOG-001) + 부분 롤백 |

### 6.2 Error Response Format

```json
{ "error": { "code": "INVALID_TRANSITION", "message": "draft에서 approved로만 전이 가능합니다", "details": { "from": "deprecated", "to": "approved" } } }
```

---

## 7. Security Considerations

- [x] 입력 검증: title/content 길이, source_type/status enum 화이트리스트
- [x] 인가: 정제·승인·편집은 Admin RBAC (기존 RBAC 재사용)
- [x] 출처 불변식: source_refs 없는 항목 KB 진입 차단 (환각 누적 방지)
- [x] 보수적 노출: draft는 검색 비노출(또는 confidence 가중치 0)
- [x] TTL: websearch 출처 항목 valid_until 설정, 만료 시 재검증/비노출
- [ ] 정제 LLM 호출 비용 상한 (max_articles, rate limit)

---

## 8. Test Plan (TDD — Red→Green, `idt:tdd` / `idt_front:tdd`)

### 8.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit (domain) | WikiPolicy 검증/전이, WikiArticle 불변식 | pytest |
| Unit (application) | Distill/Review/WriteBack UseCase | pytest + fake repo |
| Integration | wiki_router 엔드포인트, repository(Qdrant/ES/MySQL) | pytest |
| Frontend | WikiManagePage/DetailPanel, hooks | Vitest + RTL + MSW (`--pool=threads`) |

### 8.2 Test Cases (Key)

- [ ] Happy: distill 실행 → draft N개 생성, 모두 source_refs 보유
- [ ] Governance: draft→approved 전이 성공, deprecated→approved 복구
- [ ] Invariant: source_refs 빈 항목 생성 시 예외, KB 미진입
- [ ] Transition error: approved→draft 시도 시 INVALID_TRANSITION
- [ ] Search: approved만 검색 노출, draft 제외, 폴백 동작
- [ ] Edge: valid_until 만료 항목 검색 제외
- [ ] (Phase3) WriteBack: "기억 가치 없음" 판단 시 생성 안 함

> 백엔드 테스트는 Windows 이벤트 루프 teardown 산발 실패 가능 — 격리 실행으로 검증(메모리 노트 `backend-test-eventloop-flakiness`).

---

## 9. Clean Architecture

### 9.1 Layer Structure (백엔드 idt/, DDD 4-layer)

| Layer | Responsibility | Location |
|-------|---------------|----------|
| **Domain** | WikiArticle, WikiPolicy, enum (순수) | `idt/src/domain/wiki/` |
| **Application** | Distill/Review/WriteBack UseCase, repo 인터페이스 | `idt/src/application/wiki/` |
| **Infrastructure** | WikiArticleRepository(Qdrant/ES/MySQL), 모델 | `idt/src/infrastructure/wiki/` |
| **API** | wiki_router, 스키마 | `idt/src/api/routes/wiki_router.py` |

### 9.2 Dependency Rules

```
API ──→ Application ──→ Domain ←── Infrastructure
              └──→ Infrastructure(인터페이스 경유)
규칙: Domain은 외부 의존 0. verify-architecture 스킬로 검증.
```

### 9.4 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `WikiArticle`, `WikiPolicy` | Domain | `idt/src/domain/wiki/` |
| `DistillToWikiUseCase` 등 | Application | `idt/src/application/wiki/` |
| `WikiArticleRepository` 인터페이스 | Application | `idt/src/application/repositories/wiki_repository.py` |
| `WikiArticleRepository` 구현 | Infrastructure | `idt/src/infrastructure/wiki/` |
| `wiki_router` | API | `idt/src/api/routes/wiki_router.py` |
| `WikiManagePage` 등 | Presentation | `idt_front/src/components/wiki/` |

---

## 10. Coding Convention Reference

- 백엔드: snake_case 함수/모듈, PascalCase 클래스, DDD 레이어 import 규칙 (`verify-architecture`)
- 로깅: LOG-001 준수 (`verify-logging`) — 정제 실패/스킵, 상태 전이 감사 로그
- 프론트: 컴포넌트 PascalCase, 훅 `useXxx`, 폴더 kebab-case
- 환경변수: `WIKI_COLLECTION_NAME`, `WIKI_DISTILL_MODEL`, `WIKI_AUTO_APPROVE_THRESHOLD` (`.env.example` 갱신)

---

## 11. Implementation Guide

### 11.1 File Structure (신규/변경)

```
idt/
├── src/domain/wiki/
│   ├── entity.py          (WikiArticle, enum)
│   └── policies.py        (WikiPolicy)
├── src/application/wiki/
│   ├── distill_use_case.py
│   ├── review_use_case.py
│   └── write_back_use_case.py     (Phase 3)
├── src/application/repositories/wiki_repository.py  (인터페이스)
├── src/infrastructure/wiki/
│   ├── wiki_repository.py (Qdrant+ES+MySQL 구현)
│   └── models.py          (SQLAlchemy)
├── src/api/routes/wiki_router.py
└── db/migration/V0xx__create_wiki_article.sql

idt_front/src/
├── components/wiki/  (WikiManagePage, WikiArticleTable, WikiDetailPanel)
├── hooks/useWikiArticles.ts
├── services/wikiService.ts
└── types/wiki.ts
```

### 11.2 Implementation Order

**Phase 1 (B) — 정제 정적층 [MVP]**
1. [ ] (TDD) `domain/wiki` 엔티티·정책 → Red→Green
2. [ ] `wiki_article` 마이그레이션 생성 (`db-migration`)
3. [ ] `WikiArticleRepository` 인터페이스 + infra 구현(Qdrant/ES/MySQL)
4. [ ] `DistillToWikiUseCase` 구현 (원본 청크→LLM 요약→draft 생성)
5. [ ] `HybridSearchUseCase` 확장: 위키(approved, agent스코프) 우선 + 폴백
6. [ ] `wiki_router` distill/목록/상세 엔드포인트
7. [ ] 프론트 목록/상세 UI + `api-cotract` 동기화

**Phase 2 (C) — 거버넌스 게이트**
8. [ ] `WikiReviewUseCase` + approve/reject/deprecate/edit 엔드포인트
9. [ ] 프론트 승인 패널 + Admin RBAC 가드

**Phase 3 (A) — 자가 진화**
10. [ ] `wiki_writer` 노드 (`workflow_compiler.py` 확장) + `WikiWriteBackUseCase`
11. [ ] `confidence` 환류 갱신 (`ai_retrieval_source` 신호) + TTL 만료 배치

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-06-28 | Plan 기반 초안, 3개 결정사항 반영(단일에이전트/문서요약/GraphRAG제외) | 배상규 |
