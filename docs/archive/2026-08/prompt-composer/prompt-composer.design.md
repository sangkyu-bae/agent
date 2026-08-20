---
template: design
version: 1.3
feature: prompt-composer
---

# prompt-composer Design Document

> **Summary**: 채팅 + 주입된 `IntentResult` + 지정 `tool_ids` → LLM 1회 호출로 구조화 섹션 생성 → **domain Policy가 결정적으로 조립** → 세션/버전 2테이블에 이력 저장. 기존 `AgentComposer` 경로 무변경.
>
> **Project**: sangplusbot (idt — 백엔드)
> **Author**: 배상규
> **Date**: 2026-08-14
> **Status**: Draft
> **Planning Doc**: [prompt-composer.plan.md](../../01-plan/features/prompt-composer.plan.md)

### Pipeline References

| Phase | Document | Status |
|-------|----------|--------|
| Phase 1 | 데이터 모델 — `prompt_session` / `prompt_version` (본 문서 §3) | ✅ |
| Phase 4 | API 신규 3종 (`/api/v1/prompt-composer/*`) | 본 문서 §4 |
| Phase 6 | UI 배선 — **스코프 밖** (Plan O1 / N1) | N/A |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 프롬프트 생성이 도구 선정과 한 호출에 엉켜 있어 단독 재생성·부분 수정·근거 추적이 전부 불가능하다 |
| **WHO** | P2(에이전트 소유자). 1차 소비자는 백엔드 — UI 배선은 다음 사이클 |
| **RISK** | `AgentComposer`와 프롬프트 생성 로직이 **2벌 공존**한다. 배선 없이 출하하므로 검증 없는 죽은 코드가 될 위험 + 두 프롬프트 규칙이 서로 벌어질 위험 |
| **SUCCESS** | 기존 경로 회귀 0건 · LLM 실패 3종 모두 `degraded=true` + 규칙기반 폴백 반환 · 동일 입력 → 동일 `assembled` (조립 결정성) · DDL 전 컬럼 COMMENT |
| **SCOPE** | 백엔드 모듈 + 독립 API + 마이그레이션 2건. **스코프 밖**: 프론트 UI, `AgentComposer` 수정/대체, `tool_selection` 배선, 의도 분석 내부 호출 |

---

## 1. Overview

### 1.1 Design Goals

1. **오염 불가능한 구조** — LLM이 시스템 계산 필드를 채울 **경로 자체를 없앤다**. 방어 코드로 막지 않는다.
2. **조립 결정성** — 동일 섹션 입력 → 바이트 동일 `assembled`. 순수 함수로 보장한다.
3. **기존 경로 물리적 무변경** — `agent_composer` 패키지를 **import 하지 않는다**. 공용화 유혹을 구조로 차단한다.
4. **실패해도 프롬프트는 나온다** — LLM이 죽어도 도구 메타만으로 조립한 프롬프트를 200으로 반환한다.

### 1.2 Design Principles

- **Draft/Result 분리**: LLM이 보는 스키마(`_PromptDraft`)와 도메인 VO(`ComposedPrompt`)는 다른 타입이다. 계산 필드는 Draft에 **존재하지 않는다**.
- **Policy는 순수**: `assemble()`·`drop_hallucinated()`·`clamp_history()`는 시간·UUID·I/O를 쓰지 않는다. 인자만으로 결정된다.
- **어댑터가 모든 실패를 흡수**: 어댑터는 예외를 밖으로 던지지 않는다. UseCase에 try/except를 두지 않는 것이 계약이다 (`intent` 관례).
- **DB 실패는 예외**: LLM 실패만 `degraded`다. 저장 실패는 숨기지 않고 5xx로 올린다.

### 1.3 선행 사이클의 교훈 (설계 근거)

`infrastructure/intent/adapter.py:6-10`이 기록한 실패:

> `IntentDraft`를 쓰는 이유: 시스템이 계산하는 필드(`missing_slots`/`complete`/`degraded`)가 LLM 스키마에 아예 없으므로, LLM이 그 값을 오염시킬 경로 자체가 존재하지 않는다. **선행 사이클은 `IntentResult`를 겸용하고 3층 방어를 쌓았으나 계산 필드가 3개로 늘면서 그 방식이 확장에 실패했다.**

본 모듈의 계산 필드는 **4개**(`degraded`, `dropped_tool_ids`, `unknown_tool_ids`, `elapsed_ms`)이고 중첩이 3단이며, 결과가 **DB에 영속**된다. 따라서 겸용은 처음부터 배제한다 (D8).

> ⚠️ **Plan 대비 변경**: Plan §3.3의 `IntentResult` 필드 가정(`entities`)은 의도 모듈 2차 사이클로 바뀌었다. 현재 형태는 §3.4에 반영했다. `intent_snapshot`은 **원본 JSON을 그대로 보관**하므로 이 변화가 스키마에 영향을 주지 않는다.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal (겹용·통합) | Option B: Clean (완전 3층) | Option C: Pragmatic (2층) |
|----------|:-:|:-:|:-:|
| **LLM 스키마 ↔ VO** | pydantic 1벌 겸용 | domain/infra/API 3벌, 매핑 2회 | domain dataclass + infra pydantic, 매핑 1회 |
| **포트 개수** | 2 | 4 (+IdGen/Clock) | 3 |
| **조립 위치** | 어댑터 내부 | Policy + 섹션별 생성 인터페이스 | domain Policy 순수 함수 |
| **New Files** | ~8 | ~14 | ~11 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Low | High | High |
| **Effort** | Low | High | Medium |
| **오염 리스크** | **High** (DB에 영속) | None | None |
| **규칙 충돌** | — | CLAUDE.md §6 "과도한 추상화 금지" | — |

**Selected**: **Option C (Pragmatic)** — **Rationale**: A는 이 저장소가 이미 실패를 기록한 방식이며(§1.3), 여기선 오염값이 DB에 남아 되돌릴 수 없다. B의 `IdGeneratorPort`/`ClockPort`/섹션별 생성 인터페이스는 부분 재생성(Plan O6)이 스코프 밖인 현재 **호출자가 없는 추상화**다. C는 오염 경로를 구조로 차단하면서 쓰지 않는 포트를 만들지 않는다.

**Q1~Q4 결정** (Plan §7.4):

| # | 쟁점 | 결정 | 근거 |
|---|------|------|------|
| Q1 | `roles[]` 자유 생성 vs 도구 종속 | **자유 생성**, 상한 6개 | 도구 0개 요청(`tool_ids=[]`)에서도 프롬프트가 성립해야 한다. 역할은 도구의 함수가 아니다 |
| Q2 | 조립 위치 | **domain Policy 순수 함수** | SC-03(결정성)을 인프라 대역 없이 단위 테스트로 증명할 수 있다 |
| Q3 | `clamp_history` 재사용 vs 자체 구현 | **자체 구현 (복제)** | `ComposePolicy.clamp_history`(12줄)를 쓰면 `domain/prompt_composer` → `domain/agent_composer` 의존이 생겨 D1(물리적 무변경)의 첫 실이 된다. 12줄 복제가 더 싸다 |
| Q4 | `schema_version` 선반영 | **컬럼 추가** (`SMALLINT NOT NULL DEFAULT 1`) | 이력 테이블은 지우지 않으므로 장기 보관된다. 나중에 추가하면 전 행 백필이 필요하다 (R6) |

### 2.1 Component Diagram

```
POST /api/v1/prompt-composer/compose
        │
        ▼
┌──────────────────────────────────────────────────────────────┐
│ prompt_composer_router.py            (interfaces)            │
│  요청 검증(pydantic) → UseCase 위임 → 응답 직렬화             │
└──────────────────────────────────────────────────────────────┘
        │ Depends(get_prompt_composer_use_case)  ← main.py override
        ▼
┌──────────────────────────────────────────────────────────────┐
│ ComposePromptUseCase                 (application)           │
│  ① tool_ids → ToolMetaReaderPort.fetch()                     │
│  ② PromptGeneratorPort.generate()   ← 예외 안 던짐            │
│  ③ Policy.drop_hallucinated() → Policy.assemble()            │
│  ④ PromptRepositoryPort.append_version()                     │
└──────────────────────────────────────────────────────────────┘
   │              │                   │                  │
   ▼              ▼                   ▼                  ▼
┌────────┐  ┌──────────────┐  ┌───────────────┐  ┌──────────────┐
│ domain │  │ ToolCatalog  │  │ LLMPrompt     │  │ PromptRepo   │
│ policies│ │ MetaReader   │  │ GeneratorAdap │  │ (SQLAlchemy) │
│ (순수)  │  │ (tool_catalog│  │ _PromptDraft  │  │ session 공유  │
└────────┘  │  조회 전용)   │  │  → VO 매핑    │  └──────────────┘
            └──────────────┘  └───────────────┘
                                      │
                                      ▼
                              ChatOpenAI.with_structured_output
```

### 2.2 Data Flow

```
요청 {user_request, history?, intent?, tool_ids[], session_id?}
  │
  ├─① 검증 (interfaces/pydantic)  ── 실패 → 422
  │
  ├─② tool_catalog 조회 (tool_ids, is_active=true)
  │     found      → ToolMeta[]
  │     not found  → unknown_tool_ids[]  (무시하고 진행)
  │
  ├─③ 프롬프트 컨텍스트 조립
  │     - 도구 블록  (ToolMeta[])
  │     - 의도 블록  (intent 있고 intent.degraded=false 일 때만)   ← FR-13
  │     - 이력 블록  (clamp_history: 최근 20턴 · 턴당 1000자)
  │
  ├─④ LLM 1회  →  _PromptDraft{purpose, roles[], tool_guides[], principles[]}
  │     예외/타임아웃/스키마위반/purpose 공백
  │        └─▶ Policy.fallback_draft(tool_metas, user_request)   degraded=true
  │
  ├─⑤ Policy.drop_hallucinated(draft, known_ids) → dropped_tool_ids[]
  │
  ├─⑥ Policy.assemble(sections) → assembled  (순수·결정적)
  │
  ├─⑦ 저장   session_id 없음 → prompt_session INSERT + version_no=1
  │          session_id 있음 → 소유자 확인 → version_no = MAX+1
  │            소유자 불일치/부재 → 404 (저장 안 함)
  │            DB 실패        → 500 (rollback, degraded 아님)
  │
  └─⑧ 200 {session_id, version_id, version_no, sections, assembled,
           degraded, reason, dropped_tool_ids, unknown_tool_ids, elapsed_ms}
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `prompt_composer_router` | `ComposePromptUseCase`, `get_current_user` | 요청 위임 + 인증 |
| `ComposePromptUseCase` | 3 포트 + `PromptAssemblyPolicy` + `LoggerInterface` | 흐름 제어만 |
| `LLMPromptGeneratorAdapter` | `ChatOpenAI`, `PromptComposerConfig`, `LoggerInterface` | LLM 1회 + 실패 흡수 |
| `ToolCatalogMetaReader` | `ToolCatalogModel`, `AsyncSession` | `tool_ids` → `ToolMeta[]` |
| `PromptRepository` | `PromptSessionModel`, `PromptVersionModel`, `AsyncSession` | 세션/버전 CRUD |
| `PromptAssemblyPolicy` | **없음** (순수) | 조립·폐기·절단·폴백 |

> **금지 의존**: `domain|application|infrastructure/prompt_composer` 어디에서도 `src.application.agent_composer` / `src.domain.agent_composer`를 import 하지 않는다 (D1 · Q3). 아키텍처 테스트로 강제한다 (§8.2 #5).

### 2.4 오염 차단 계약 (Option C 핵심)

| ID | 규칙 | 이유 | 검증 |
|----|------|------|------|
| **P1** | `_PromptDraft`는 `infrastructure/prompt_composer/adapter.py`에만 존재한다. domain은 이 타입을 모른다 | 도메인이 LLM 스키마를 알면 겸용으로 되돌아간다 | import 테스트 |
| **P2** | `_PromptDraft`에 `degraded`/`dropped_tool_ids`/`unknown_tool_ids`/`elapsed_ms` 필드를 **두지 않는다** | LLM이 채울 경로 자체를 제거 (§1.3) | 스키마 필드 목록 단위 테스트 |
| **P3** | Draft → VO 매핑은 어댑터의 단일 함수(`_to_sections`)에서만 일어난다 | 매핑 지점이 흩어지면 누락 필드가 생긴다 | 코드 리뷰 |
| **P4** | `Policy.assemble()`은 `datetime`·`uuid`·랜덤을 쓰지 않는다 | SC-03 결정성 | 반복 호출 동일성 테스트 |
| **P5** | 어댑터는 `except Exception`으로 전부 흡수하고 폴백 Draft를 반환한다. **예외를 던지지 않는다** | UseCase에 try/except가 생기면 실패 경로가 2벌이 된다 | 실패 3종 테스트 |

---

## 3. Data Model

### 3.1 도메인 VO (`domain/prompt_composer/schemas.py`)

```python
"""prompt_composer 도메인 VO — 외부 의존 없음(순수 frozen dataclass).

Design Ref: §2.4 P1 — LLM 스키마(_PromptDraft)는 여기 없다.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ToolMeta:
    """tool_catalog 1건의 프롬프트용 투영."""
    tool_id: str
    name: str
    description: str
    source: str                    # "internal" | "mcp"
    server_name: str | None = None


@dataclass(frozen=True)
class RoleSection:
    title: str
    detail: str


@dataclass(frozen=True)
class ToolGuide:
    tool_id: str
    name: str                      # 조립 시 표기용 (ToolMeta에서 채움)
    when: str
    how: str
    caution: str = ""


@dataclass(frozen=True)
class PromptSections:
    """LLM이 생성하는 4개 섹션. 계산 필드 없음 (P2)."""
    purpose: str
    roles: tuple[RoleSection, ...] = ()
    tool_guides: tuple[ToolGuide, ...] = ()
    principles: tuple[str, ...] = ()


@dataclass(frozen=True)
class ComposedPrompt:
    """생성 결과 + 관측 정보. 하단 5개는 **시스템만** 채운다."""
    sections: PromptSections
    assembled: str
    degraded: bool = False
    reason: str | None = None
    dropped_tool_ids: tuple[str, ...] = ()
    unknown_tool_ids: tuple[str, ...] = ()
    elapsed_ms: int = 0
```

### 3.2 조립 규칙 (`domain/prompt_composer/policies.py`)

```python
class PromptAssemblyPolicy:
    MAX_ROLES = 6
    MAX_TOOL_GUIDES = 50
    MAX_PRINCIPLES = 10
    MAX_HISTORY_TURNS = 20
    MAX_HISTORY_TURN_CHARS = 1000

    @staticmethod
    def assemble(sections: PromptSections) -> str: ...
    @staticmethod
    def drop_hallucinated(
        sections: PromptSections, known: dict[str, ToolMeta]
    ) -> tuple[PromptSections, tuple[str, ...]]: ...
    @staticmethod
    def clamp_history(turns: list) -> list[dict]: ...      # Q3 — 자체 구현
    @staticmethod
    def fallback_sections(
        metas: tuple[ToolMeta, ...], user_request: str
    ) -> PromptSections: ...
```

**`assemble()` 출력 포맷 (P4 — 결정적)**

```
{purpose}

[역할]
- {title}: {detail}

[도구 지침]
- {name} ({tool_id}): {when} / {how}
  주의: {caution}

[동작 원칙]
- {principle}
```

규칙:
- 섹션이 비면 **헤더째 생략**한다 (빈 `[역할]` 헤더를 남기지 않는다).
- `caution`이 빈 문자열이면 "주의:" 줄을 생략한다.
- 순서는 `purpose → 역할 → 도구 지침 → 동작 원칙` 고정. 항목 순서는 입력 순서 보존.
- 섹션 사이 구분은 빈 줄 1개. 끝에 개행을 남기지 않는다 (`rstrip`).
- 모든 섹션이 비면 `purpose`만 반환한다. `purpose`까지 비면 `fallback_sections`가 이미 채웠으므로 도달하지 않는다.

**`fallback_sections()` (LLM 실패 시 · degraded 경로)**

| 섹션 | 값 |
|------|-----|
| `purpose` | `"사용자의 요청을 처리하는 에이전트입니다. 요청 요약: {user_request[:200]}"` |
| `roles` | `()` — 생성 근거 없음 |
| `tool_guides` | 도구별 `when=meta.description`, `how=""`, `caution=""` |
| `principles` | 고정 3개: 한국어 응답 / 도구 결과에 없는 내용은 지어내지 않음 / 확인 불가 시 모른다고 답함 |

### 3.3 DB 스키마

```sql
-- V061__create_prompt_session.sql
CREATE TABLE prompt_session (
  id            VARCHAR(36)  NOT NULL COMMENT '세션 UUID',
  user_id       VARCHAR(36)  NOT NULL COMMENT '생성 요청 사용자 ID',
  agent_id      VARCHAR(36)  NULL     COMMENT '바인딩된 에이전트 ID. 생성 시점엔 미저장 상태라 NULL 허용(Plan D5). FK 미설정 — 에이전트 삭제가 이력 삭제로 전이되면 안 됨',
  user_request  TEXT         NOT NULL COMMENT '최초 자연어 요청 원문',
  created_at    DATETIME     NOT NULL COMMENT '생성 시각',
  updated_at    DATETIME     NOT NULL COMMENT '수정 시각. agent_id 백필 시 갱신',
  PRIMARY KEY (id),
  KEY ix_prompt_session_user (user_id, created_at),
  KEY ix_prompt_session_agent (agent_id)
) COMMENT='시스템 프롬프트 생성 세션 — 하나의 요청에서 파생된 버전들의 묶음';

-- V062__create_prompt_version.sql
CREATE TABLE prompt_version (
  id              VARCHAR(36)  NOT NULL COMMENT '버전 UUID',
  session_id      VARCHAR(36)  NOT NULL COMMENT '소속 prompt_session ID',
  version_no      INT          NOT NULL COMMENT '세션 내 버전 번호. 1부터 증가',
  schema_version  SMALLINT     NOT NULL DEFAULT 1 COMMENT 'sections JSON 구조 버전. 구조 변경 시 증가시켜 과거 행 파싱 분기(Design Q4)',
  sections        JSON         NOT NULL COMMENT '구조화 섹션 {purpose, roles, tool_guides, principles}',
  assembled       TEXT         NOT NULL COMMENT '서버가 결정적으로 조립한 최종 시스템 프롬프트',
  intent_snapshot JSON         NULL     COMMENT '생성에 사용된 IntentResult 원본 스냅샷. 미주입이거나 degraded면 NULL',
  tool_ids        JSON         NOT NULL COMMENT '생성에 실제 반영된 tool_id 배열. 환각 폐기·미존재 제외 후',
  degraded        TINYINT(1)   NOT NULL COMMENT 'LLM 실패로 규칙기반 폴백이 쓰였는지 여부',
  reason          VARCHAR(500) NULL     COMMENT 'degraded 사유 또는 관측 메모',
  elapsed_ms      INT          NOT NULL DEFAULT 0 COMMENT 'LLM 호출 소요 시간(ms). 관측용',
  created_at      DATETIME     NOT NULL COMMENT '생성 시각',
  PRIMARY KEY (id),
  UNIQUE KEY uq_session_version (session_id, version_no),
  CONSTRAINT fk_prompt_version_session FOREIGN KEY (session_id)
    REFERENCES prompt_session(id) ON DELETE CASCADE
) COMMENT='시스템 프롬프트 버전 이력 — 생성 1회당 1행, 근거(의도·도구) 동봉';
```

> SQLAlchemy 모델에도 동일 `comment=`를 반영한다 (CLAUDE.md §3 · `tests/db/test_migration_ddl_comments.py`).

### 3.4 `intent_snapshot` 보관 정책

의도 모듈은 2차 사이클에서 필드가 바뀌었고 앞으로도 바뀔 수 있다. 따라서 **파싱하지 않고 요청 본문의 `intent` 객체를 그대로 JSON 저장**한다.

```jsonc
// 현재(2026-08-14) IntentResult 형태 — 이 모듈은 이 구조에 의존하지 않는다
{ "label": "document_qa", "confidence": 0.8, "ambiguous": false, "reason": "...",
  "filled_slots": {...}, "suggestions": {...}, "questions": [...],
  "missing_slots": [...], "complete": true, "degraded": false }
```

이 모듈이 **읽는 필드는 3개뿐**이다 — `degraded`(부착 여부 판단), `label`, `reason`. 나머지는 통과 저장한다. 요청 스키마도 이에 맞춰 `extra="allow"`로 둔다.

---

## 4. API Specification

Base: `/api/v1/prompt-composer` · 전 엔드포인트 `Depends(get_current_user)` 필수.

### 4.1 `POST /compose`

**Request**

```jsonc
{
  "user_request": "사내 규정 문서를 찾아 답하고 결과를 엑셀로 내보내는 봇",  // 1~1000자, 필수
  "history": [ { "role": "user", "content": "..." } ],                    // 선택, 최대 20턴
  "intent": { "label": "document_qa", "degraded": false },                // 선택, extra 허용
  "tool_ids": ["internal:excel_export", "mcp:srv-1:search_docs"],         // 선택, 최대 50개
  "session_id": "8f2c...",                                                // 선택. 있으면 버전 append
  "agent_id": null                                                        // 선택. 신규 세션에만 반영
}
```

**Response 200**

```jsonc
{
  "session_id": "8f2c...",
  "version_id": "b71d...",
  "version_no": 1,
  "sections": {
    "purpose": "사내 규정 문서를 검색해 근거와 함께 답하고, 필요 시 결과를 엑셀로 제공합니다.",
    "roles": [ { "title": "문서 검색", "detail": "질의에 해당하는 규정 원문을 찾는다" } ],
    "tool_guides": [
      { "tool_id": "internal:excel_export", "name": "엑셀 내보내기",
        "when": "사용자가 표·목록 형태의 결과 저장을 요청할 때",
        "how": "정리된 행 데이터를 전달해 호출한다",
        "caution": "원문 인용 없이 수치를 만들어 넣지 않는다" }
    ],
    "principles": ["한국어로 답한다", "근거 문서가 없으면 모른다고 답한다"]
  },
  "assembled": "사내 규정 문서를...\n\n[역할]\n- 문서 검색: ...\n\n[도구 지침]\n- 엑셀 내보내기 (internal:excel_export): ...",
  "degraded": false,
  "reason": null,
  "dropped_tool_ids": [],
  "unknown_tool_ids": ["mcp:srv-1:search_docs"],
  "elapsed_ms": 2431
}
```

**상태 코드**

| 코드 | 조건 |
|------|------|
| 200 | 정상 **및 LLM 실패(degraded=true)** — Plan D6 |
| 401 | 인증 실패 |
| 404 | `session_id`가 없거나 타인 소유 (403 아님 — 존재 노출 방지, SC-07) |
| 422 | `user_request` 길이 위반 / `tool_ids` 50개 초과 / `history` 형식 오류 |
| 500 | DB 저장 실패 (rollback) — LLM 실패와 구분 |

### 4.2 `GET /sessions/{session_id}`

세션 메타 + 버전 목록(`version_no` 내림차순). 본인 세션만. 없거나 타인이면 404.

```jsonc
{
  "session_id": "8f2c...", "agent_id": null, "user_request": "...",
  "created_at": "2026-08-14T05:00:00Z",
  "versions": [
    { "version_id": "c92e...", "version_no": 2, "degraded": false,
      "tool_ids": ["internal:excel_export"], "created_at": "...", "assembled": "..." }
  ]
}
```

> `sections`는 목록 응답에 싣지 않는다 (페이로드 비대화 방지). 필요 시 `?include=sections`로 확장 — **이번 스코프는 미구현**.

### 4.3 `PATCH /sessions/{session_id}`

```jsonc
{ "agent_id": "a13f..." }
```

| 코드 | 조건 |
|------|------|
| 200 | 백필 성공 |
| 404 | 세션 없음 / 타인 소유 |
| 409 | 이미 `agent_id`가 바인딩된 세션 (덮어쓰기 금지) |
| 422 | `agent_id` 형식 오류 |

> `agent_id` **존재 검증은 하지 않는다** — `agent_builder` 리포지토리 의존이 생기면 D1의 두 번째 실이 된다. 정합성은 호출자(저장 직후 백필) 책임이며, FK 미설정과 같은 이유다(§3.3).

### 4.4 LLM 프롬프트 구조 (`infrastructure/prompt_composer/prompts.py`)

```
[시스템]
당신은 AI 에이전트의 시스템 프롬프트를 설계하는 전문가입니다.
아래 재료만으로 에이전트 프롬프트의 각 섹션을 작성하세요.

{tools_block}      ← tool_ids가 비면 블록 자체를 싣지 않는다
{intent_block}     ← intent 없음/degraded면 싣지 않는다 (FR-13)

[규칙]
- purpose: 이 에이전트가 무엇을 하는지 1~2문장.
- roles: 에이전트가 수행하는 역할. 최대 6개. 도구가 없어도 작성합니다.
- tool_guides: **위 도구 목록에 있는 tool_id만** 사용하세요. 목록에 없는 도구를
  지어내지 마세요. 각 항목에 when(언제) / how(어떤 입력으로) / caution(주의)을 씁니다.
- principles: 응답 언어·거절 조건·환각 금지 등 동작 원칙. 최대 10개.
- 전부 한국어로 작성합니다.

[사용자]
{history_block}
[현재 요청]
{user_request}
```

> 이 템플릿은 `application/agent_composer/composer.py:_SYSTEM_PROMPT:97-102`의 4섹션 규칙(목적/역할/도구지침/동작원칙)을 **구조화 형태로 계승**한 것이다. 두 템플릿의 대조는 §10.3.

---

## 5. UI/UX Design

**해당 없음** — 백엔드 전용 사이클 (Plan D7 / O1). UI 배선은 N1로 이월.

배선 사이클에서 필요할 최소 요구사항만 남긴다:

- `degraded=true` 응답은 사용자에게 **"자동 생성 실패, 기본 문안입니다"**를 표시해야 한다 (Plan R4).
- `unknown_tool_ids`/`dropped_tool_ids`가 비어 있지 않으면 어떤 도구가 반영되지 않았는지 알려야 한다.

---

## 6. Error Handling

### 6.1 오류 분류

| ID | 상황 | 계층 | 처리 | 응답 |
|----|------|------|------|------|
| **E1** | LLM 예외 (API 오류·인증·레이트리밋) | 어댑터 | `logger.error` + 폴백 Draft | 200 · `degraded=true` · `reason="error"` |
| **E2** | LLM 타임아웃 | 어댑터 | `logger.warning` + 폴백 Draft | 200 · `degraded=true` · `reason="timeout"` |
| **E3** | structured output 스키마 위반 | 어댑터 | `logger.error` + 폴백 Draft | 200 · `degraded=true` · `reason="schema"` |
| **E4** | `purpose`가 공백 (빈 결과) | 어댑터 | `logger.warning` + 폴백 Draft | 200 · `degraded=true` · `reason="empty"` |
| **E5** | 후보에 없는 `tool_id` 생성 (환각) | Policy | 해당 guide 폐기 | 200 · `dropped_tool_ids` |
| **E6** | `tool_ids`가 카탈로그에 없음/비활성 | UseCase | 무시하고 진행 | 200 · `unknown_tool_ids` |
| **E7** | `tool_catalog` 조회 실패 (DB) | Repository | 예외 전파 | 500 |
| **E8** | 저장 실패 (`prompt_version` INSERT) | Repository | 예외 전파 · `get_session` rollback | 500 |
| **E9** | `session_id` 부재/타인 소유 | UseCase | 저장 없이 중단 | 404 |
| **E10** | `version_no` 유니크 충돌 (동시 요청) | Repository | 1회 재조회 후 재시도, 재실패 시 전파 | 200 또는 500 |
| **E11** | 과거 `sections` JSON 파싱 실패 (R6) | Repository | 누락 키 기본값 · `assembled`는 원본 그대로 | 200 (조회 API) |

### 6.2 degraded와 5xx의 경계

> **LLM 실패만 `degraded`다. DB 실패는 5xx다.**

`degraded`는 "품질이 낮지만 쓸 수 있는 결과가 있다"는 뜻이다. 저장이 실패하면 결과가 **존재하지 않으므로**(version_id를 줄 수 없다) 200으로 위장하면 호출자가 없는 버전을 참조하게 된다. E7/E8은 예외를 그대로 올린다.

### 6.3 동시성 (E10)

같은 `session_id`로 동시 요청이 오면 `uq_session_version`이 두 번째를 거부한다. Repository는 `IntegrityError`를 1회만 잡아 `MAX(version_no)`를 재조회하고 재시도한다. 무한 재시도는 하지 않는다 — 실사용에서 동일 세션 동시 재생성은 드물고, 재시도 루프가 락 경합을 키운다.

---

## 7. Security Considerations

- [x] **인증**: 3개 엔드포인트 모두 `Depends(get_current_user)`
- [x] **소유권**: `session_id` 조회/수정은 `user_id` 일치 검사. 불일치는 **404**(403 아님 — 타인 세션 존재 여부를 노출하지 않는다)
- [x] **입력 검증**: `user_request` 1~1000자, `tool_ids` ≤50, `history` ≤20턴, `agent_id` UUID 형식 — pydantic 이중 방어
- [x] **프롬프트 인젝션**: 사용자 입력은 system이 아닌 **human 메시지**에 싣는다. 도구 목록은 system에 두되 "목록에 없는 tool_id 금지"를 명시하고, 실제 차단은 프롬프트가 아니라 `drop_hallucinated()`가 한다 (프롬프트만 믿지 않는다 — `intent` adapter `_round_block` 관례)
- [x] **PII 로깅**: `user_request` 원문·`filled_slots` 값은 로그에 남기지 않는다. 길이·개수만 남긴다 (`intent` `_log_success` 관례 C4)
- [x] **저장 데이터**: `user_request`와 `intent_snapshot`은 사용자 입력이므로 PII 가능. 세션이 `user_id`로 격리되며 조회는 소유자 한정
- [x] **권한 상승 없음**: 이 모듈은 도구를 실행하지 않는다. 프롬프트 문자열만 만든다

---

## 8. Test Plan

> 백엔드 전용 — Playwright 미해당. pytest + `httpx.AsyncClient` + 테스트 DB로 L1~L3를 수행한다.

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| L0: 단위 | Policy 조립·폐기·절단·폴백 | pytest (순수) | Do |
| L1: API 계약 | 3 엔드포인트 상태코드·응답 형태 | pytest + AsyncClient | Do |
| L2: 통합 | UseCase ↔ 어댑터 대역 ↔ Repository | pytest + 테스트 DB | Do |
| L3: 실 LLM | 실제 생성 품질 1건 | `@pytest.mark.real_llm` (기본 제외) | Do |

### 8.2 L0 — 단위 시나리오

| # | 검증 대상 | 기대 |
|---|-----------|------|
| 1 | `assemble()` 반복 호출 | 동일 입력 → 바이트 동일 출력 (SC-03) |
| 2 | 빈 섹션 조립 | `roles=()` → `[역할]` 헤더 미출력. 전부 비면 `purpose`만 |
| 3 | `caution=""` | "주의:" 줄 생략 |
| 4 | `drop_hallucinated()` | 후보 밖 `tool_id` 폐기 + `dropped_tool_ids` 반환 (SC-04) |
| 5 | **아키텍처** | `domain/prompt_composer/*`에 `langchain`·`sqlalchemy`·`fastapi`·`agent_composer` import 0 (SC-05 · D1) |
| 6 | `clamp_history()` | 25턴 → 최근 20턴, 1500자 → 1000자 절단 |
| 7 | `fallback_sections()` | 도구 3개 → `tool_guides` 3개 + 고정 원칙 3개, `purpose` 비지 않음 |
| 8 | `_PromptDraft` 필드 목록 | `degraded`/`dropped_tool_ids`/`unknown_tool_ids`/`elapsed_ms` **부재** (P2) |

### 8.3 L1 — API 계약 시나리오

| # | 요청 | 기대 |
|---|------|------|
| 1 | 정상 compose | 200, `session_id`·`version_no=1`, `assembled` 비어있지 않음 |
| 2 | 같은 `session_id`로 반복 호출 | `version_no` 단조 증가 (SC-08). **측정은 L2(Repository/UseCase)에서 한다** — L1 라우터 테스트는 UseCase 대역 기반이라 구조적으로 버전 증가를 볼 수 없다 (v0.2 정정) |
| 3 | 타인 `session_id` | 404 |
| 4 | 없는 `session_id` | 404 |
| 5 | `user_request` 0자 / 1001자 | 422 |
| 6 | `tool_ids` 51개 | 422 |
| 7 | 미인증 | 401 |
| 8 | 존재하지 않는 `tool_id` 포함 | 200 + `unknown_tool_ids`에 포함 |
| 9 | `tool_ids=[]` | 200, `tool_guides=[]`, `purpose`·`roles` 존재 (Q1) |
| 10 | `GET /sessions/{id}` | 200, 버전 내림차순 |
| 11 | `PATCH` 최초 바인딩 / 재바인딩 | 200 / 409 |
| 12 | `intent.degraded=true` 주입 | 200, `intent_snapshot`은 **NULL** 저장 (FR-13) |

### 8.4 L2 — 통합 시나리오

| # | 시나리오 | 성공 기준 |
|---|----------|-----------|
| 1 | 어댑터 예외 (E1) | 200 · `degraded=true` · `reason="error"` · 폴백 저장됨 |
| 2 | 어댑터 타임아웃 (E2) | 200 · `reason="timeout"` (SC-02) |
| 3 | 스키마 위반 (E3) | 200 · `reason="schema"` |
| 4 | `purpose` 공백 (E4) | 200 · `reason="empty"` |
| 5 | 저장 실패 (E8) | 500, 세션/버전 **미생성** (rollback 확인) |
| 6 | 단일 세션 검증 | UseCase 내 두 Repository가 동일 `AsyncSession` 사용 |
| 7 | 환각 도구 (E5) | `dropped_tool_ids` 반영 + `tool_ids` 저장값에서 제외 |
| 8 | 회귀 | `agent_composer`·`general_chat`·`intent` 기존 테스트 전량 통과 (SC-01) |

### 8.5 Seed Data Requirements

| Entity | Minimum | Key Fields |
|--------|:------:|------------|
| `tool_catalog` | 3건 | internal 2 (1건 `is_active=false`) + mcp 1 |
| `mcp_server_registry` | 1건 | mcp 도구의 `server_name` 표기용 |
| User | 2명 | 소유권 격리 테스트(SC-07) |
| LLM 대역 | 5 variant | 정상 / 예외 / 타임아웃 / 스키마위반 / 빈결과 |

---

## 9. Clean Architecture

### 9.1 Layer Structure

| Layer | Responsibility | Location |
|-------|---------------|----------|
| **domain** | VO, 조립·폐기·절단·폴백 Policy, 3개 포트 | `src/domain/prompt_composer/` |
| **application** | `ComposePromptUseCase` — 흐름 제어 | `src/application/prompt_composer/` |
| **infrastructure** | LLM 어댑터, ORM 모델, Repository, 설정 | `src/infrastructure/prompt_composer/` |
| **interfaces** | 라우터, 요청/응답 스키마 | `src/api/routes/`, `src/interfaces/schemas/` |

### 9.2 Dependency Rules

```
interfaces ──→ application ──→ domain ←── infrastructure
  (router)      (use case)     (VO/Policy/Port)   (adapter/repo)

규칙 1: domain은 langchain·sqlalchemy·fastapi를 import 하지 않는다.
규칙 2: prompt_composer 어느 계층도 agent_composer를 import 하지 않는다 (D1/Q3).
규칙 3: application은 infrastructure 구현체가 아니라 포트에만 의존한다.
```

### 9.3 포트 정의 (`domain/prompt_composer/interfaces.py`)

```python
class PromptGeneratorPort(Protocol):
    async def generate(
        self, user_request: str, metas: tuple[ToolMeta, ...],
        intent: dict | None, history: list[dict], request_id: str,
    ) -> tuple[PromptSections, bool, str | None, int]:
        """→ (sections, degraded, reason, elapsed_ms). **예외를 던지지 않는다** (P5)."""

class ToolMetaReaderPort(Protocol):
    async def fetch(
        self, tool_ids: tuple[str, ...]
    ) -> tuple[tuple[ToolMeta, ...], tuple[str, ...]]:
        """→ (found_metas, unknown_ids). is_active=false는 unknown 취급."""

class PromptRepositoryPort(Protocol):
    async def create_session(
        self, user_id: str, user_request: str, agent_id: str | None
    ) -> str: ...
    async def find_session(self, session_id: str, user_id: str) -> object | None: ...
    async def append_version(self, session_id: str, prompt: ComposedPrompt, ...) -> tuple[str, int]: ...
    async def list_versions(self, session_id: str) -> list: ...   # FR-09 (v0.2 추가)
    async def bind_agent(self, session_id: str, user_id: str, agent_id: str) -> str | None: ...
```

### 9.4 DI 조립 (`main.py` — db-session.md 준수)

```python
def create_prompt_composer_factories():
    """LLM 어댑터는 lifespan 1회 생성, 세션 의존 컴포넌트는 요청마다 조립."""
    settings = get_settings()
    generator = LLMPromptGeneratorAdapter(logger=..., config=PromptComposerConfig())

    def factory(session: AsyncSession = Depends(get_session)):
        return ComposePromptUseCase(
            generator=generator,                    # 세션 무관 — 공유 안전
            tool_reader=ToolCatalogMetaReader(session),   # 동일 세션
            repository=PromptRepository(session),         # 동일 세션
            logger=...,
        )
    return factory
```

- ❌ lifespan에서 UseCase를 싱글턴으로 만들지 않는다 (풀 고갈)
- ❌ Repository 내부 `commit()`/`rollback()` 금지 — `get_session`이 경계
- ✅ 조립 실패 시 라우터를 등록하지 않고 `logger.error`로 낙하 (`tool_selection` 관례)

---

## 10. Coding Convention Reference

### 10.1 이 기능의 규약

| Item | 적용 |
|------|------|
| 모듈 경로 | `{layer}/prompt_composer/` — 기존 `intent`·`tool_selection`과 동일 |
| 파일명 | `schemas.py` / `policies.py` / `interfaces.py` / `adapter.py` / `prompts.py` / `models.py` / `repository.py` |
| 라우터 | `src/api/routes/prompt_composer_router.py`, prefix `/api/v1/prompt-composer` |
| 비공개 타입 | LLM 스키마는 `_PromptDraft`처럼 언더스코어 접두 (모듈 밖 노출 금지) |
| 함수 길이 | 40줄 초과 금지 — `assemble()`은 섹션별 헬퍼로 분해 |
| if 중첩 | 2단 초과 금지 — 조립의 빈 섹션 분기는 early-continue |
| 로깅 | `logger.info/warning/error` + `request_id`. `print()` 금지, 스택 트레이스 필수 |
| 테스트 위치 | `tests/{layer}/prompt_composer/test_*.py` + `tests/api/test_prompt_composer_router.py` |

### 10.2 Design 참조 주석 규칙 (Do 단계 필수)

```python
# Design §2.4 P2 — 계산 필드를 두지 않는다. LLM이 채울 경로 자체를 없앤다.
class _PromptDraft(BaseModel):
    purpose: str = Field(description="이 에이전트가 무엇을 하는지 1~2문장")
    ...

# Plan SC-03 — 시간·UUID·랜덤 미사용. 인자만으로 결정된다.
@staticmethod
def assemble(sections: PromptSections) -> str:
```

### 10.3 `AgentComposer`와의 섹션 대조 (Plan R1 완화)

두 모듈이 벌어지는지 확인할 기준표. **Do 단계에서 이 표를 `prompts.py` 상단 주석으로 복사한다.**

| 섹션 | `agent_composer/composer.py:_SYSTEM_PROMPT:97-102` | `prompt_composer/prompts.py` |
|------|---------------------------------------------------|------------------------------|
| 목적 | "에이전트 목적 (1~2문장)" | `purpose` (동일) |
| 역할 | "[역할] 섹션: 각 워커의 역할과 언제 사용하는지" | `roles[]` — **워커 비종속** (Q1) |
| 도구 지침 | "[도구 지침] 섹션: 사용 시점·호출 방법·주의사항" | `tool_guides[]{when,how,caution}` (구조화) |
| 동작 원칙 | "[동작 원칙] 섹션: 실행 순서, 응답 언어, 주의사항" | `principles[]` — **실행 순서 제외**(워커 개념 없음) |
| 산출 형태 | 문자열 1개 | 구조 + 서버 조립 |

> 차이 2건(역할의 워커 비종속 / 원칙의 실행 순서 제외)은 **의도된 것**이다. 이 모듈은 워커·flow를 모른다.

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt/
├── src/
│   ├── domain/prompt_composer/
│   │   ├── __init__.py                         [신규]
│   │   ├── schemas.py                          [신규] §3.1
│   │   ├── policies.py                         [신규] §3.2
│   │   └── interfaces.py                       [신규] §9.3
│   ├── application/prompt_composer/
│   │   ├── __init__.py                         [신규]
│   │   └── compose_prompt_use_case.py          [신규]
│   ├── infrastructure/prompt_composer/
│   │   ├── __init__.py                         [신규]
│   │   ├── adapter.py                          [신규] _PromptDraft + 실패 흡수
│   │   ├── prompts.py                          [신규] §4.4 + §10.3 대조표
│   │   ├── models.py                           [신규] 2 모델 (comment= 필수)
│   │   ├── repository.py                       [신규] ToolCatalogMetaReader + PromptRepository
│   │   └── ../config/prompt_composer_config.py [신규]
│   ├── interfaces/schemas/prompt_composer.py   [신규]
│   ├── api/routes/prompt_composer_router.py    [신규]
│   └── api/main.py                             [수정] DI + 라우터 등록
├── db/migration/
│   ├── V061__create_prompt_session.sql         [신규]
│   └── V062__create_prompt_version.sql         [신규]
└── tests/
    ├── domain/prompt_composer/test_policies.py      [신규]
    ├── application/prompt_composer/test_use_case.py [신규]
    ├── infrastructure/prompt_composer/test_adapter.py    [신규]
    ├── infrastructure/prompt_composer/test_repository.py [신규]
    └── api/test_prompt_composer_router.py           [신규]
```

신규 22개 / 수정 1개.

> **v0.2 정정**: `src/config.py`는 수정하지 않는다. 설정은 `PromptComposerConfig(BaseSettings)`
> 단일 소스로 두며(`intent`·`tool_selection` 관례), 두 곳에 나뉘면 어느 값이 먹는지가 모호해진다.

### 11.2 Implementation Order

1. [ ] `domain/prompt_composer/schemas.py` + `policies.py` — **테스트 먼저** (L0 #1~4,6,7)
2. [ ] `interfaces.py` 포트 3종 (Protocol)
3. [ ] `V061`/`V062` 마이그레이션 + `models.py` (`comment=` 동일 반영) → `test_migration_ddl_comments.py` 통과 확인
4. [ ] `repository.py` — `ToolCatalogMetaReader` + `PromptRepository` (commit 금지, E10 재시도)
5. [ ] `prompt_composer_config.py` + `config.py` 5종
6. [ ] `adapter.py` — `_PromptDraft`(P2) + 실패 4종 흡수(P5) + `_to_sections`(P3)
7. [ ] `compose_prompt_use_case.py` — 흐름 6단계, try/except 없음
8. [ ] `interfaces/schemas/` + 라우터 3 엔드포인트
9. [ ] `main.py` DI(§9.4) + 라우터 등록
10. [ ] L1/L2 테스트 + 기존 테스트 전량 재실행 (SC-01)
11. [ ] `/verify-architecture` · `/verify-logging` · `/verify-tdd`

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| 도메인 코어 | `module-1` | VO + Policy(조립·폐기·절단·폴백) + 포트 3종. 순수 함수라 DB·LLM 없이 완결 (구현 1~2) | 15-20 |
| 영속 계층 | `module-2` | 마이그레이션 2건 + ORM 모델 + Repository 2종 + 설정 (3~5) | 20-28 |
| 생성·배선 | `module-3` | LLM 어댑터 + UseCase + 라우터 + DI + 통합 테스트 (6~11) | 30-40 |

> `module-1`을 **먼저 끝내고 L0 테스트가 초록인 것을 확인**한다. SC-03(조립 결정성)과 SC-05(레이어)는 이 모듈만으로 증명되며, 여기가 깨진 채 진행하면 이후 실패 원인이 LLM인지 조립인지 구분되지 않는다.
>
> `module-2`의 DDL COMMENT는 `tests/db/test_migration_ddl_comments.py`가 V054 이후 파일을 검사하므로, 모듈 종료 조건에 이 테스트 통과를 포함한다.

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Plan + Design | 전체 | 완료 |
| Session 2 | Do | `--scope module-1,module-2` | 35-48 |
| Session 3 | Do | `--scope module-3` | 30-40 |
| Session 4 | Check + Report | 전체 | 25-35 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.2 | 2026-08-18 | Check 정정 — `config.py` 수정 대상에서 제외(설정 단일 소스), SC-08 측정 지점을 L1→L2로 정정. 포트에 `list_versions` 선언 추가 | 배상규 |
| 0.1 | 2026-08-14 | 초안 — Option C(2층 분리) 선택. 오염 차단 계약 P1~P5 정의. Q1(역할 자유생성)·Q2(Policy 조립)·Q3(clamp 자체구현)·Q4(schema_version 추가) 결정. intent 모듈 2차 사이클 반영(`intent_snapshot` 통과 저장) | 배상규 |
