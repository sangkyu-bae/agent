# agent-kb-quick-setup Design Document

> **Summary**: 에이전트 빌더(스튜디오·위저드) 안에서 파일만 올리면 KB·전용 컬렉션·RAG 도구가 기본값으로 자동 구성되는 원스톱 경로. 서버 `/quick` 1개가 기존 UseCase를 조합하고, 프론트는 공용 블록 1개를 두 화면이 공유한다.
>
> **Project**: sangplusbot (Agent Builder)
> **Version**: idt 0.1.0 / idt_front 0.0.0
> **Author**: 배상규
> **Date**: 2026-11-05
> **Status**: Draft
> **Planning Doc**: [agent-kb-quick-setup.plan.md](agent-kb-quick-setup.plan.md)

---

## Context Anchor

> Copied from Plan document. Ensures strategic context survives Design→Do handoff.

| Key | Value |
|-----|-------|
| **WHY** | KB를 에이전트에 붙이는 데 4개 화면·약 15개 결정이 필요하고, 벡터 크기·거리 함수 같은 용어가 비개발자를 막는다. |
| **WHO** | P2 부서 담당자(비개발자)와 IT 운영자(반개발자). 관리자(P3)는 기본 임베딩 모델을 1회 설정한다. |
| **RISK** | KB마다 컬렉션 1개 전략으로 Qdrant 컬렉션 수가 KB 수만큼 늘어난다. 자동 생성 KB가 에이전트 저장 취소 후 고아로 남는다. 부분 업로드 실패를 성공으로 위장할 가능성. |
| **SUCCESS** | 신규 사용자가 스튜디오·위저드 각각에서 파일 업로드만으로 RAG 에이전트를 만들고 테스트 채팅에서 문서 근거 답변을 받는다. 기존 KB·컬렉션·RAG 설정 경로 회귀 0건. |
| **SCOPE** | M1 기본 임베딩 모델 설정·컬렉션 자동 배정 → M2 KB 원스톱 생성 API → M3 스튜디오 도구함 "지식 문서" 블록·RAG 패널 고급 접기 → M4 위저드 문서 단계 |

---

## 1. Overview

### 1.1 Design Goals

- 사용자가 정하는 것을 "파일"과 "에이전트 공개 범위" 둘로 줄인다. 나머지는 관리자 기본값과 코드 상수가 정한다.
- 기존 경로(컬렉션 지정 KB 생성, RAG 패널 고급 설정, 위저드 5단계 steps 계약)는 바이트 단위로 바뀌지 않는다. 모든 변경은 additive다.
- 실패 경계를 한 곳에 둔다. KB 생성 실패는 전파, 파일 단위 실패는 응답에 남기는 degraded.
- 스튜디오와 위저드가 같은 서버 API·같은 프론트 블록을 쓴다. 두 화면의 동작이 갈릴 수 있는 코드 중복을 만들지 않는다.

### 1.2 Design Principles

- **이음매 재사용**: `CollectionAssignerInterface`(도메인에 이미 존재)에 자동 배정 구현을 꽂는다. `KnowledgeBaseUseCase`·라우터는 분기가 늘지 않는다.
- **기본값은 소비 지점 단일 출처**: 기본 임베딩 모델은 DB 단일 행만 읽는다. `.env` 폴백 없음(조용한 폴백은 FR-03 위반).
- **계약 additive**: 요청에는 optional 필드만 추가, 응답은 신규 타입. 기존 소비자 무변경 (`additive-contract-extension` 위키).
- **핸드오프 G1~G5 준수**: 위저드 → 스튜디오 `kbId` 전달은 기존 `AgentCreateIntent` 확장. 쿼리 settled 후 소비.
- **단일 흡수 지점**: `/quick`의 파일 루프 1곳만 예외를 흡수한다. AST 계약 테스트로 고정.

---

## 2. Architecture Options (v1.7.0)

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | 프론트가 기존 API 2종(KB 생성 → 파일별 업로드) 순차 호출 | 서버 `/quick` + 신규 bounded context `kb_provisioning` + 파이프라인 6번째 단계 | 서버 `/quick` 1개가 기존 UseCase 조합 + 도메인 정책 1파일 + 프론트 공용 블록 |
| **New Files** | 14 | 26 | 19 |
| **Modified Files** | 12 | 16 | 13 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Medium (두 화면에 순차 로직 중복) | High | High |
| **Effort** | Low | High | Medium |
| **Risk** | 파일별 실패·롤백 처리가 프론트 두 곳에서 어긋남 | 위저드 steps 계약 변경이 기존 테스트·SSE 소비자를 흔듦 | 멀티파트 다중 파일 1요청의 시간 상한 |
| **Recommendation** | 핫픽스 | 장기 분리 | **Default choice** |

**Selected**: Option C — **Rationale**: 두 호출자(스튜디오·위저드)가 같은 흐름을 쓰므로 오케스트레이션은 서버에 1곳. 파이프라인 단계 수를 바꾸지 않아 기존 위저드 계약을 보존한다. 사용자 확인(2026-11-05).

### 2.1 Component Diagram

```
┌──────────────────────── idt_front ────────────────────────┐
│  AgentBuilderPage ──┐                                     │
│   LeftConfigPanel   │   KnowledgeDocsBlock ──► useQuickKnowledgeBase ──┐
│    └ 도구함          │   (파일 드롭 / 기존 KB 선택 / ProgressCard)        │
│  AgentCreateEntryPage ┘                                                │
│   └ DocumentsStep ─► 같은 블록 (mode='wizard')                          │
│  RagConfigPanel (고급 접기)   AdminKbDefaultsPage ─► useKbDefaults      │
└──────────────────────────────────────────────────────────┼────────────┘
                                                           ▼
┌──────────────────────── idt (FastAPI) ────────────────────────────────┐
│ knowledge_base_router  POST /knowledge-bases/quick                     │
│   └ QuickCreateKnowledgeBaseUseCase                                    │
│        ├ KnowledgeBaseUseCase.create(collection_name=None)             │
│        │    └ AutoProvisionCollectionAssigner                          │
│        │         ├ KbDefaultSettingRepository.get()  ← kb_default_setting│
│        │         └ CollectionManagementUseCase.create_collection()     │
│        │              (Qdrant 생성 + 권한 행 + 활동 로그 CREATE)         │
│        └ KnowledgeBaseUploadUseCase.execute()  × 파일 수 (순차)         │
│ admin_kb_defaults_router  GET/PUT /admin/kb-defaults                   │
│ kb_defaults_router        GET /kb-defaults (사용자 조회)                 │
│ agent_pipeline_router     AgentPipelineRequest.kb_id (optional)        │
│   └ AgentCreatePipelineUseCase._run_create → RAG 도구 + tool_configs   │
│        └ CreateAgentUseCase (기존 kb_id 검증·scope clamp 그대로)         │
└────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

**스튜디오 (create 모드)**

```
파일 드롭 → KnowledgeDocsBlock
  → name = kbNameForAgent(form.name), scope = scopeForVisibility(form.visibility)
  → POST /knowledge-bases/quick (multipart)
     → KB 생성(id 선생성) → 컬렉션 kb-{id8} 생성 → 파일 순차 업로드
     ← 201 {kb_id, documents[{status}]}
  → uploaded_count ≥ 1 이면 onAttached(kb_id)
     → form.tools += RAG_TOOL_ID (없을 때), form.toolConfigs[RAG] = {...DEFAULT_RAG_CONFIG, kb_id}
  → [저장] → 기존 create 경로 (kb_id 검증·scope clamp 그대로)
```

**위저드**

```
도구 확정 → step 'documents' (클라이언트 로컬 단계, 서버 호출 없음)
  → [업로드] → /quick (scope PERSONAL) ← kb_id
     → selectedIds += RAG_TOOL_ID, state.kbId = kb_id
  → [계속] 또는 [건너뛰기] → 기존 PROMPT 요청 + kb_id
  → 프롬프트 확인 → [스튜디오로] intent.result.kbId → wizardResultToForm → RAG 도구+kb_id 프리필
  (논스톱 create 경로를 쓰는 호출자는 kb_id 를 주면 CREATE 단계가 RAG 도구를 주입)
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `AutoProvisionCollectionAssigner` | `KbDefaultSettingRepository`, `EmbeddingModelRepository`, `CollectionManagementUseCase` | 기본 모델 해석 → 컬렉션 생성(활동 로그 포함) |
| `QuickCreateKnowledgeBaseUseCase` | `KnowledgeBaseUseCase`, `KnowledgeBaseUploadUseCase`, `KnowledgeBasePolicy` | 생성 + 업로드 조합, 이름 중복 접미 |
| `AgentCreatePipelineUseCase._run_create` | `PipelinePolicy.with_knowledge_tool` | kb_id → tool_ids·tool_configs 주입 |
| `KnowledgeDocsBlock` | `useQuickKnowledgeBase`, `useKnowledgeBases`, `useKbDefaults`, `ProgressCard` | 파일 드롭·기존 KB 선택·진행 표시 |
| `AdminKbDefaultsPage` | `useAdminKbDefaults`, `useUpdateAdminKbDefaults`, `useEmbeddingModelList` | 기본 모델 선택 |

---

## 3. Data Model

### 3.1 Entity Definition

```python
# domain/kb_default_setting/entities.py
@dataclass(frozen=True)
class KbDefaultSetting:
    default_embedding_model_id: int | None   # embedding_model.id 소프트 참조, None=미설정
    updated_at: datetime | None

    @property
    def configured(self) -> bool: ...

# domain/kb_default_setting/errors.py
class KbDefaultsNotConfiguredError(ValueError): ...   # 라우터 422
class EmbeddingModelNotFoundError(ValueError): ...    # PUT 404
class EmbeddingModelInactiveError(ValueError): ...    # PUT 409

# domain/knowledge_base/quick_setup_policy.py
class KbQuickSetupPolicy:
    COLLECTION_PREFIX = "kb-"
    MAX_FILES = 10
    NAME_SUFFIX_MAX = 20            # " (2)" ~ " (20)" 까지 시도, 초과 시 ValueError
    @staticmethod
    def collection_name_for(kb_id: str) -> str: return f"kb-{kb_id[:8]}"
    @staticmethod
    def scope_for_visibility(visibility: str) -> CollectionScope   # private→PERSONAL, department→DEPARTMENT, public→PUBLIC
    @staticmethod
    def next_name(base: str, attempt: int) -> str                  # attempt 0 → base, n → f"{base} ({n+1})" (MAX_NAME_LENGTH 내 절단)
```

```typescript
// idt_front/src/types/kbQuickSetup.ts
export const KB_QUICK_DOC_STATUS = { UPLOADED: 'uploaded', FAILED: 'failed' } as const;
export interface QuickKbDocumentResult { filename: string; status: 'uploaded' | 'failed'; document_id: string | null; chunk_count: number; error: string | null; }
export interface QuickKbResponse { kb_id: string; kb_name: string; collection_name: string; scope: CollectionScope; documents: QuickKbDocumentResult[]; uploaded_count: number; failed_count: number; }
export interface KbDefaultsInfo { configured: boolean; default_embedding_model_id: number | null; model_display_name: string | null; }
export const KB_QUICK_MAX_FILES = 10;
export const KB_QUICK_ACCEPT = '.pdf,.xlsx,.xls,.hwp,.hwpx';   // KbUploadDocumentModal 과 동일

// idt_front/src/utils/kbQuickSetup.ts
export const kbNameForAgent = (agentName: string): string      // '' → '새 에이전트 지식', 그 외 `${trim} 지식` (100자 절단)
export const scopeForVisibility = (v: 'private'|'department'|'public'): CollectionScope
export const attachKbToForm = (form, kbId): AgentBuilderFormData  // tools += RAG(없을 때), toolConfigs[RAG] = {...(기존 ?? DEFAULT), kb_id, collection_name: undefined, metadata_filter: {}}
```

### 3.2 Entity Relationships

```
[kb_default_setting] 1(고정 행) ──soft──▶ [embedding_model]
[knowledge_base] N ──collection_name──▶ [Qdrant collection "kb-{id8}"] 1   (자동 생성 시 1:1)
[collection_permissions] (scope = KB scope, 자동 배정 시 생성)
[collection_activity_log] CREATE detail.embedding_model  ← 적재 시 임베딩 모델 결정(기존)
[agent_tool.tool_config.kb_id] ──soft──▶ [knowledge_base]   (기존)
```

### 3.3 Database Schema

```sql
-- V084__create_kb_default_setting.sql
-- agent-kb-quick-setup Design §3.3 (V084): 지식베이스 자동 구성 전역 기본값 — 단일 행(id 고정).
-- default_embedding_model_id 는 embedding_model.id 소프트 참조(FK 없음 — multimodal_setting.vision_model_id 선례).
-- CHARSET/COLLATE 명시 금지 (errno 3780 회피). ⚠️ COMMENT 안에 콤마 금지.

CREATE TABLE kb_default_setting (
    id                         VARCHAR(36) NOT NULL PRIMARY KEY COMMENT '고정 단일 행 식별자',
    default_embedding_model_id INT         NULL COMMENT 'embedding_model.id 소프트 참조 — NULL이면 미설정',
    created_at                 DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각',
    updated_at                 DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 시각'
) ENGINE=InnoDB COMMENT='지식베이스 자동 구성 전역 기본값 — 단일 행';

INSERT INTO kb_default_setting (id) VALUES ('c0000000-0000-4000-8000-000000000001');
```

SQLAlchemy 모델 `infrastructure/kb_default_setting/models.py`에 `comment=` 동일 반영. `tests/db/test_migration_ddl_comments.py` 대상.

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/v1/admin/kb-defaults` | 기본 설정 조회 (끊어진 참조는 warnings) | admin |
| PUT | `/api/v1/admin/kb-defaults` | 기본 임베딩 모델 전체 교체 | admin |
| GET | `/api/v1/kb-defaults` | 사용자용 조회: `configured`·모델 표시명만 | user |
| POST | `/api/v1/knowledge-bases/quick` | KB 생성 + 컬렉션 자동 생성 + 파일 업로드 | user |
| POST | `/api/v1/knowledge-bases` | **변경**: `collection_name` optional (생략 시 자동 배정) | user |
| POST | `/api/v1/agents/pipeline`, `/stream` | **변경**: 요청 `kb_id` optional | user |

### 4.2 Detailed Specification

#### `PUT /api/v1/admin/kb-defaults`

Request:
```json
{ "default_embedding_model_id": 2 }
```
Response (200):
```json
{ "configured": true, "default_embedding_model_id": 2,
  "model": { "id": 2, "provider": "openai", "model_name": "text-embedding-3-small", "display_name": "...", "vector_dimension": 1536 },
  "warnings": [], "updated_at": "2026-11-05T00:00:00Z" }
```
Errors: `400 VALIDATION_ERROR` (null 불가 — 해제는 지원하지 않음), `404 EMBEDDING_MODEL_NOT_FOUND`, `409 EMBEDDING_MODEL_INACTIVE`.
GET은 모델이 삭제·비활성이면 `configured: false` + `warnings: ["..."]`. 라우터 패턴은 `admin_multimodal_router`와 동일 (`require_role("admin")`, `_error(code, message, status)`).

#### `GET /api/v1/kb-defaults`

Response (200): `{ "configured": true, "default_embedding_model_id": 2, "model_display_name": "OpenAI text-embedding-3-small" }`
프론트 블록이 미설정 안내를 **업로드 전에** 보여주기 위한 읽기 전용 축약 응답.

#### `POST /api/v1/knowledge-bases/quick` (multipart/form-data)

| field | type | rule |
|---|---|---|
| `name` | str | 1~100자 (`KnowledgeBasePolicy.validate_name`) |
| `scope` | str | PERSONAL / DEPARTMENT / PUBLIC |
| `department_id` | str? | scope=DEPARTMENT 필수 (기존 `validate_scope`) |
| `files` | UploadFile[] | 1~10개, 확장자 `.pdf .xlsx .xls .hwp .hwpx` |

Response (201):
```json
{ "kb_id": "…", "kb_name": "여신 상담봇 지식", "collection_name": "kb-3f1a9c2e", "scope": "PERSONAL",
  "documents": [
    { "filename": "규정.pdf", "status": "uploaded", "document_id": "…", "chunk_count": 128, "error": null },
    { "filename": "암호.pdf", "status": "failed", "document_id": null, "chunk_count": 0, "error": "암호화된 문서입니다" }
  ],
  "uploaded_count": 1, "failed_count": 1 }
```

규칙:
- 이름 중복(`exists_active_name`)이면 ` (2)` ~ ` (20)` 접미로 재시도. 초과 시 422.
- KB 생성·컬렉션 생성 실패 → 4xx/5xx 전파 (파일 업로드 시작 전).
- 파일 루프는 **유일한 흡수 지점**. `ValueError`·파서 예외·`Exception` 모두 `status: failed` + `error`(사용자 메시지), 로그는 `exception=e`.
- 전부 실패해도 201 (KB는 존재). 도구 부착 여부는 프론트(FR-08).
- 요청당 순차 업로드. 응답 `documents` 순서 = 요청 순서.

Errors: `401`, `403`(DEPARTMENT 미소속), `422 KB_DEFAULTS_NOT_CONFIGURED` ("관리자가 기본 임베딩 모델을 설정해야 합니다"), `422`(파일 0개/10개 초과/이름 검증), `409`(컬렉션 이름 충돌 — kb_id 재생성 1회 후에도 충돌).

#### `POST /api/v1/knowledge-bases` (변경)

`collection_name: str | None = None`. None이면 `AutoProvisionCollectionAssigner` 경로. 기존 문자열 지정은 `UserSelectedCollectionAssigner` 경로 그대로. 응답 변경 없음.

#### `POST /api/v1/agents/pipeline` (변경)

`kb_id: str | None = None`. 있으면 CREATE 단계에서 `tool_ids`에 `internal:internal_document_search`를 (없을 때) 추가하고 `tool_configs = {RAG: RagToolConfigRequest(kb_id=kb_id)}`. KB 존재·읽기권한 검증은 기존 `CreateAgentUseCase`가 수행(실패 시 422). 응답 `AgentPipelineResponse`에 `kb_id: str | null` 에코백 추가(additive).

---

## 5. UI/UX Design

### 5.1 Screen Layout

**스튜디오 도구함 (create 모드)** — 도구함 `CollapsibleSection` 안, 빌트인 목록 위에 블록 배치

```
┌ 도구함 ──────────────────────────────── [+ 도구] ┐
│ ┌ 지식 문서 ─────────────────────────────────┐ │
│ │  📄 문서를 올리면 이 에이전트 전용 지식베이스가 │ │
│ │     만들어지고 문서 검색 도구가 연결됩니다.      │ │
│ │  [ 파일 끌어다 놓기 / 선택 ]  PDF·엑셀·한글 최대 10개 │ │
│ │  또는  [기존 지식베이스 선택 ▾]                   │ │
│ │  ─ 연결됨: "여신 상담봇 지식" [개인]  (바꾸기)    │ │
│ │  (업로드 중) ProgressCard: 지식베이스 만들기 ✓ /  │ │
│ │            문서 올리기 2/3 ⚠ 암호.pdf 실패 / 도구 연결 ✓ │ │
│ │  ⓘ 저장하지 않아도 지식베이스는 남습니다          │ │
│ └────────────────────────────────────────────┘ │
│ (기본 도구 목록 …)  (선택 도구 목록 …)            │
```

- 미설정(`configured=false`): 드롭 영역 비활성 + 문구 "관리자가 기본 임베딩 모델을 설정해야 합니다". 기존 KB 선택은 가능.
- edit 모드: 블록 대신 한 줄 안내 "지식 문서 연결은 새 에이전트 생성 시 가능합니다" (도구 구성 변경 미저장 유예 FR-6와 정합).
- 폼 공개 범위가 KB 범위보다 넓어지면 기존 clamp 알림 경로 그대로. 블록에는 "연결된 지식베이스 범위: 개인" 배지.

**RagConfigPanel (고급 접기)**

```
검색 대상 지식베이스  [▾ 선택]
도구 설명           [textarea]
▸ 고급 설정                         (기본 접힘)
   컬렉션 / 메타데이터 필터 / 검색 모드 / 결과 수 / 위키 우선 / 라우팅 검색 / 도구 이름
```
고급 값이 기본값과 다르면(컬렉션 지정·필터 1개 이상·search_mode≠hybrid·top_k≠5·토글 on·tool_name≠기본) `defaultOpen=true`로 펼쳐 기존 사용자가 설정을 못 보는 일이 없게 한다.

**위저드 문서 단계** — 도구 카드 아래, 프롬프트 카드 위

```
┌ 참고할 문서가 있나요? ───────────────────────┐
│  (KnowledgeDocsBlock mode='wizard')          │
│  [파일 올리기]            [건너뛰기]  [계속]   │
└──────────────────────────────────────────────┘
```
업로드 성공 시 "문서 검색" 도구가 도구 카드에 추가되어 보인다(selectedIds += RAG). `locked`는 프롬프트 단계 진입 후 true.

**관리자 `/admin/kb-defaults`**

```
지식베이스 기본값
  기본 임베딩 모델  [▾ 활성 모델 목록]   [저장]
  ⚠ 미설정이면 사용자가 빌더에서 문서를 올릴 수 없습니다
  ⓘ 변경은 이후 자동 생성되는 지식베이스에만 적용됩니다
```

### 5.2 User Flow

```
스튜디오: /agent-builder → [새 에이전트] → 이름 입력 → 도구함 '지식 문서' 파일 드롭
        → 진행 카드 → 연결됨 배지 → 지침 입력 → [저장] → 테스트 채팅
위저드:  /agent-builder/new → 설명 → (되묻기) → 도구 확정 → 문서 업로드/건너뛰기
        → 프롬프트 확인 → [스튜디오로] → 폼에 RAG+KB 프리필 → [저장]
관리자:  /admin/kb-defaults → 모델 선택 → 저장 (1회)
```

### 5.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `KnowledgeDocsBlock` | `idt_front/src/components/agent-builder/KnowledgeDocsBlock.tsx` | 파일 드롭·기존 KB 선택·진행 카드·연결 배지. props: `agentName, visibility, attachedKbId, mode, locked?, onAttached(kbId), onDetach()` |
| `useQuickKnowledgeBase` | `idt_front/src/hooks/useQuickKnowledgeBase.ts` | `/quick` 뮤테이션 + `ProgressStep[]` 파생 + KB 목록 invalidate |
| `useKbDefaults`, `useAdminKbDefaults`, `useUpdateAdminKbDefaults` | `idt_front/src/hooks/useKbDefaults.ts` | 사용자/관리자 조회·수정 (진행 단계 파생은 `utils/kbQuickSetup.ts`) |
| `kbQuickSetupService` | `idt_front/src/services/kbQuickSetupService.ts` | `/quick`, `/kb-defaults`, `/admin/kb-defaults` |
| `DocumentsStep` | `idt_front/src/pages/AgentCreateEntryPage/components/DocumentsStep.tsx` | 위저드 문서 단계 카드 (블록 래핑 + 건너뛰기/계속) |
| `AdminKbDefaultsPage` | `idt_front/src/pages/AdminKbDefaultsPage/index.tsx` | 기본 모델 설정 화면 |
| `RagConfigPanel` (수정) | 기존 | 고급 접기 |
| `LeftConfigPanel` (수정) | 기존 | 도구함에 블록 마운트, edit 안내 |
| `AgentCreateEntryPage` (수정) | 기존 | `documents` 단계·`kbId` 상태·요청 전달 |
| `wizardResultToForm` (수정) | `idt_front/src/utils/` | `kbId` → `attachKbToForm` |
| `adminNav.ts`, `App.tsx`, `constants/api.ts` (수정) | 기존 | 라우트·상수 |

### 5.4 Page UI Checklist (v2.1.0)

#### 스튜디오 도구함 — 지식 문서 블록 (create)
- [ ] 드롭 영역: `input[type=file]` multiple, accept `.pdf,.xlsx,.xls,.hwp,.hwpx`, 라벨 "파일 끌어다 놓기 / 선택", 보조 문구 "PDF·엑셀·한글 최대 10개"
- [ ] 드롭다운: "기존 지식베이스 선택" (접근 가능 KB, `[범위] 이름` 라벨)
- [ ] 진행 카드: `ProgressCard` steps 3개 — "지식베이스 만들기", "문서 올리기"(badgeLabel `n/m`), "도구 연결"
- [ ] 실패 목록: 파일명 + 사유 (status failed 건), 전부 실패 시 "도구를 연결하지 못했습니다" + 재시도 버튼
- [ ] 연결 배지: KB 이름 + 범위 배지(개인/부서/공개) + [바꾸기]
- [ ] 안내: "저장하지 않아도 지식베이스는 남습니다"
- [ ] 미설정 상태: 드롭 영역 disabled + "관리자가 기본 임베딩 모델을 설정해야 합니다"
- [ ] 금지 용어 미노출: 컬렉션·벡터·거리 함수·청킹·BM25·RRF·top_k
- [ ] edit 모드: 블록 대신 안내 한 줄

#### RagConfigPanel
- [ ] 기본 노출: "검색 대상 지식베이스" 드롭다운, "도구 설명" textarea
- [ ] `CollapsibleSection title="고급 설정"` 기본 접힘, 비기본값이면 펼침
- [ ] 접힘 내부: 컬렉션, 메타데이터 필터(+추가), 검색 모드 라디오 3종, 결과 수 슬라이더 1~20, 위키 우선·라우팅 검색 체크박스, 도구 이름
- [ ] KB 범위 제한 안내 문구(기존) 유지

#### 위저드 — 문서 단계
- [ ] 카드 제목 "참고할 문서가 있나요?"
- [ ] `KnowledgeDocsBlock mode='wizard'` (기존 KB 선택 포함)
- [ ] 버튼: [건너뛰기], [계속](업로드 성공 또는 KB 선택 후 활성)
- [ ] 업로드 성공 시 도구 카드에 "문서 검색" 항목 표시
- [ ] 프롬프트 단계 진입 후 `locked` 표시(완료 배지)

#### 관리자 — 지식베이스 기본값
- [ ] 드롭다운: 활성 임베딩 모델 (`display_name`, 차원 표기)
- [ ] 저장 버튼: `LoadingButton` isPending
- [ ] 미설정 경고 문구, 끊어진 참조 warnings 표시
- [ ] "변경은 이후 생성분에만 적용" 안내
- [ ] adminNav "문서·품질" 그룹 항목 "지식베이스 기본값" `/admin/kb-defaults`

---

## 6. Error Handling

### 6.1 Error Code Definition

| Code | HTTP | Message | Cause | Handling |
|------|:---:|---------|-------|----------|
| `KB_DEFAULTS_NOT_CONFIGURED` | 422 | 관리자가 기본 임베딩 모델을 설정해야 합니다 | 단일 행 model_id NULL 또는 모델 비활성 | 블록에 문구 그대로 노출, 드롭 비활성 |
| `VALIDATION_ERROR` | 400/422 | 입력 오류 메시지 | 이름·범위·파일 수 | 인라인 표시 |
| `EMBEDDING_MODEL_NOT_FOUND` | 404 | 임베딩 모델을 찾을 수 없습니다 | PUT에 없는 id | 관리자 화면 토스트 |
| `EMBEDDING_MODEL_INACTIVE` | 409 | 비활성 모델은 기본값으로 지정할 수 없습니다 | PUT에 비활성 id | 관리자 화면 토스트 |
| (컬렉션 이름 충돌) | 409 | `Collection 'kb-…' already exists` (문자열 detail) | `kb-{id8}` 기존재 — uuid 충돌이라 실질 불가, 전용 code·재생성 없음 (Check G3 확정) | 재시도 안내 |
| (파일 단위) | 201 내 `status: failed` | 서버 파서 메시지 그대로 | 암호·손상·미지원 | 실패 목록 표시 |

### 6.2 Error Response Format

기존 라우터 관례 유지: `{"detail": {"code": "...", "message": "..."}}` (admin) / `{"detail": "..."}` (knowledge_base_router `_raise_http`). `/quick`은 `_raise_http`를 따르되 `KbDefaultsNotConfiguredError`만 `code` 포함 dict로 내려 프론트가 분기한다.

---

## 7. Security Considerations

- [ ] `/quick` 파일 수 ≤ 10, 확장자 화이트리스트, 개별 파일은 기존 업로드 경로의 크기·형식 검증 그대로
- [ ] scope=DEPARTMENT는 사용자 소속 부서만 (`KnowledgeBasePolicy.validate_scope` 기존)
- [ ] 자동 컬렉션 권한 행은 KB scope와 동일 — PERSONAL 컬렉션은 타 사용자 비노출(기존 `collection_permissions` 판정)
- [ ] 관리자 엔드포인트 `require_role("admin")`
- [ ] 파이프라인 `kb_id`는 기존 `CreateAgentUseCase` 읽기권한 검증을 반드시 거친다(우회 경로 없음, AST 테스트)
- [ ] 에러 메시지에 내부 경로·스택 미포함

---

## 8. Test Plan (v2.3.0)

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| Domain | `KbQuickSetupPolicy`, `KbDefaultSetting`, `PipelinePolicy.with_knowledge_tool` | pytest (mock 금지) | Do |
| Application | `AutoProvisionCollectionAssigner`, `QuickCreateKnowledgeBaseUseCase`, `KbDefaultSettingUseCase`, 파이프라인 `_run_create` | pytest + fake repo | Do |
| L1: API | 6 엔드포인트 | pytest TestClient (`tests/api/`) | Do |
| L2: UI | 블록·패널·위저드 단계·관리자 화면 | Vitest + RTL + MSW | Do |
| L3: E2E | 스튜디오·위저드 완주 | 실런 스모크(로컬 서버) + 통합 테스트 `agentCreateWizard.test.tsx` 확장 | Do/Check |
| 계약 | AST: 흡수 지점 1곳, kb_id 우회 없음, 기존 요청 동일 응답 | pytest | Do |

### 8.2 L1: API Test Scenarios

| # | Endpoint | Method | Test | Status | Response |
|---|----------|--------|------|:---:|----------|
| 1 | /admin/kb-defaults | GET | 미설정 | 200 | `configured=false`, `warnings=[]` |
| 2 | /admin/kb-defaults | PUT | 활성 모델 id | 200 | `configured=true`, `model.id` 일치 |
| 3 | /admin/kb-defaults | PUT | 없는 id / 비활성 id | 404 / 409 | code 일치 |
| 4 | /admin/kb-defaults | GET | 일반 사용자 | 403 | — |
| 5 | /kb-defaults | GET | 설정 후 | 200 | `configured=true`, `model_display_name` |
| 6 | /knowledge-bases | POST | `collection_name` 생략 + 설정됨 | 201 | `collection_name` = `kb-{id[:8]}`, 활동 로그 CREATE에 `embedding_model` |
| 7 | /knowledge-bases | POST | `collection_name` 생략 + 미설정 | 422 | `KB_DEFAULTS_NOT_CONFIGURED` |
| 8 | /knowledge-bases | POST | 기존 요청(컬렉션 지정) | 201 | 기존 응답과 동일(회귀) |
| 9 | /knowledge-bases/quick | POST | PDF 2개 | 201 | `uploaded_count=2`, documents 순서 보존 |
| 10 | /knowledge-bases/quick | POST | 정상 1 + 암호 PDF 1 | 201 | `uploaded_count=1`, `failed_count=1`, error 메시지 |
| 11 | /knowledge-bases/quick | POST | 파일 0개 / 11개 | 422 | — |
| 12 | /knowledge-bases/quick | POST | 이름 중복 | 201 | `kb_name` = `… (2)` |
| 13 | /knowledge-bases/quick | POST | DEPARTMENT 미소속 | 403 | — |
| 14 | /agent-pipeline | POST | `kb_id` 지정, 논스톱 | 200 | 생성 에이전트 워커에 RAG + `tool_config.kb_id` |
| 15 | /agent-pipeline | POST | `kb_id` 없음 | 200 | 기존 응답 동일(회귀), `kb_id=null` |
| 16 | /agent-pipeline | POST | 읽기권한 없는 `kb_id` | 422 | — |

### 8.3 L2: UI Action Test Scenarios

| # | Page | Action | Expected | Verification |
|---|------|--------|----------|--------------|
| 1 | 스튜디오 create | 파일 2개 드롭 | 진행 카드 → 연결 배지, `form.tools`에 RAG, `toolConfigs[RAG].kb_id` | MSW `/quick` 호출 1회, multipart 파일 2개 |
| 2 | 스튜디오 create | 1개 실패 응답 | 실패 목록에 파일명, 도구 연결 완료 | `uploaded_count=1` |
| 3 | 스튜디오 create | 전부 실패 응답 | 도구 미부착, 재시도 버튼 | `form.tools`에 RAG 없음 |
| 4 | 스튜디오 create | 기존 KB 선택 | 연결 배지 + 같은 폼 상태 | `/quick` 미호출 |
| 5 | 스튜디오 create | 미설정 응답 | 드롭 disabled + 문구 | `/kb-defaults configured=false` |
| 6 | 스튜디오 create | 블록 텍스트 | 금지 용어 7종 부재 | `queryByText` 부재 단언 |
| 7 | 스튜디오 edit | 진입 | 블록 대신 안내 한 줄 | — |
| 8 | RagConfigPanel | 기본값 config | 고급 접힘, KB·설명만 보임 | — |
| 9 | RagConfigPanel | 비기본값 config | 고급 펼침 | 기존 15개 테스트는 펼침 상태에서 통과 |
| 10 | 위저드 | 도구 확정 | 문서 단계 카드 표시, 서버 호출 없음 | MSW 미호출 |
| 11 | 위저드 | 업로드 → 계속 | PROMPT 요청에 `kb_id`, `tool_ids`에 RAG | 요청 본문 단언 |
| 12 | 위저드 | 건너뛰기 | PROMPT 요청에 `kb_id` 없음 | — |
| 13 | 위저드 → 스튜디오 | [스튜디오로] | 폼에 RAG + kb_id 프리필 (G5: KB 쿼리 settled 후) | 통합 테스트 |
| 14 | 관리자 | 모델 선택 → 저장 | PUT 호출, 토스트 | — |

### 8.4 L3: E2E Scenario Test Scenarios

| # | Scenario | Steps | Success |
|---|----------|-------|---------|
| 1 | 스튜디오 완주 (SC-1) | 관리자 설정 → 새 에이전트 → PDF 드롭 → 저장 → 테스트 채팅 | 문서 근거 답변, `/knowledge-bases`에 `{이름} 지식` |
| 2 | 위저드 완주 (SC-2) | 설명 → 도구 → PDF 업로드 → 프롬프트 → 스튜디오 → 저장 | 에이전트 상세에 RAG+KB |
| 3 | 미설정 차단 (SC-3) | 설정 해제 상태에서 블록 진입 | 문구 노출, 업로드 불가 |
| 4 | 부분 실패 (SC-4) | 정상+암호 PDF | 실패 파일명 표시, 도구 연결 |

### 8.5 Seed Data Requirements

| Entity | Count | Fields |
|--------|:-----:|--------|
| `embedding_model` | 1 활성 | `text-embedding-3-small` (시드 존재) |
| `kb_default_setting` | 1 | V084 INSERT (model NULL) → 테스트에서 PUT |
| `chunking_profile` | 1 `is_default` | V041 시드 |
| 픽스처 PDF | 2 | 정상 1 + 암호 1 (`tests/fixtures/` 기존 hwp/pdf 샘플 재사용) |

---

## 9. Clean Architecture

### 9.1 Layer Structure

| Layer | Responsibility | Location |
|-------|---------------|----------|
| domain | `KbDefaultSetting`, errors, `KbQuickSetupPolicy`, `PipelinePolicy.with_knowledge_tool` | `idt/src/domain/kb_default_setting/`, `idt/src/domain/knowledge_base/quick_setup_policy.py`, `idt/src/domain/agent_create_pipeline/policies.py` |
| application | `KbDefaultSettingUseCase`, `AutoProvisionCollectionAssigner`, `QuickCreateKnowledgeBaseUseCase`, 파이프라인 `_run_create` 수정 | `idt/src/application/kb_default_setting/`, `idt/src/application/knowledge_base/` |
| infrastructure | `KbDefaultSettingModel`, `KbDefaultSettingRepository` | `idt/src/infrastructure/kb_default_setting/` |
| interfaces/api | `admin_kb_defaults_router`, `kb_defaults_router`, `knowledge_base_router(/quick)`, `agent_pipeline` 스키마 `kb_id` | `idt/src/api/routes/`, `idt/src/interfaces/schemas/agent_pipeline.py` |
| front | 블록·훅·서비스·타입·페이지 | §5.3 |

### 9.2 Dependency Rules

기존 Thin DDD 규칙. `AutoProvisionCollectionAssigner`는 application 레이어에서 `CollectionManagementUseCase`(application)를 협력자로 받는다 — UseCase 간 조합은 `ListKbDocumentsUseCase(kb_use_case=…)` 선례와 동일. 같은 요청 세션 하나로 조립(`db-session` 규칙).

### 9.3 File Import Rules

| From | Can Import | Cannot Import |
|------|-----------|---------------|
| domain | 표준 라이브러리, 같은 domain | application / infrastructure / LangChain |
| application | domain, 다른 application UseCase(협력자 주입) | api, infrastructure 구체 클래스 직접 생성 |
| infrastructure | domain | application |
| api | application, interfaces | 비즈니스 규칙 |

### 9.4 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `KbDefaultSetting`, `KbDefaultsNotConfiguredError` 외 2 | domain | `domain/kb_default_setting/{entities,errors,interfaces}.py` |
| `KbQuickSetupPolicy` | domain | `domain/knowledge_base/quick_setup_policy.py` |
| `PipelinePolicy.with_knowledge_tool(final_ids, kb_id) -> (tool_ids, tool_configs)` | domain | `domain/agent_create_pipeline/policies.py` |
| `KbDefaultSettingUseCase` (get / update) | application | `application/kb_default_setting/use_case.py` |
| `AutoProvisionCollectionAssigner` | application | `application/knowledge_base/collection_assigner.py` (같은 파일, 클래스 추가) |
| `QuickCreateKnowledgeBaseUseCase` | application | `application/knowledge_base/quick_create_use_case.py` |
| `KbDefaultSettingModel`, `KbDefaultSettingRepository` | infrastructure | `infrastructure/kb_default_setting/{models,repository}.py` |
| 라우터 2개 + `/quick` + DI | api | `api/routes/admin_kb_defaults_router.py`, `api/routes/kb_defaults_router.py`, `knowledge_base_router.py`, `main.py` |
| 프론트 | presentation | §5.3 |

**`KnowledgeBaseUseCase.create` 변경점 (최소)**: `kb_id = str(uuid.uuid4())`를 `assigner.assign(...)` **앞**에서 생성하고 `assign(user, collection_name, request_id, kb_id=kb_id)`로 넘긴다. `CollectionAssignerInterface.assign`에 키워드 전용 `kb_id: str | None = None` 추가(additive). `UserSelectedCollectionAssigner`는 무시한다.

**`AutoProvisionCollectionAssigner.assign` 순서**: 설정 조회 → 모델 활성 확인(실패 시 `KbDefaultsNotConfiguredError`) → `CollectionPolicy.validate_name` → `collection_exists` 시 `kb_id` 재생성 불가이므로 `ConflictError`(409) → `CollectionManagementUseCase.create_collection(req(vector_size=model.vector_dimension, embedding_model=model.model_name), user=user, scope=kb_scope, department_id=...)` → 이름 반환. KB `save` 실패 시 컬렉션 best-effort 삭제는 `KnowledgeBaseUseCase.create`에서 `try/except` 후 `logger.warning(exception=e)` — 고아 컬렉션 허용(Plan 리스크 수용).

---

## 10. Coding Convention Reference

### 10.1 Naming Conventions

프로젝트 기존 규칙(`idt/CLAUDE.md`, `idt_front/CLAUDE.md`). 함수 40줄·if 중첩 2단계 상한.

### 10.4 This Feature's Conventions

| Item | Convention Applied |
|------|-------------------|
| 런타임 상수 | 컴포넌트 파일 금지 → `types/kbQuickSetup.ts` (`tsx-authoring-pitfalls`) |
| 뮤테이션 버튼 | `LoadingButton` + `isPending` |
| 진행 표시 | `common/ProgressCard` 재사용 |
| 핸드오프 | `AgentCreateIntent.wizard.result.kbId?` + `getState()` 소비. 별도 settled 가드 없음 — `attachKbToForm` 이 순수 함수이고 블록이 KB 를 반응형으로 조회한다 (Check G5 확정) |
| 로깅 | 흡수 지점 `logger.warning(..., exception=e)` |
| Design 참조 주석 | 핵심 결정에 `# Design Ref: agent-kb-quick-setup §9.4` |
| DDL | 테이블·전 컬럼 COMMENT, 콤마 금지, CHARSET 미지정 |

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt/
├── db/migration/V084__create_kb_default_setting.sql                 (신규)
├── src/domain/kb_default_setting/{__init__,entities,errors,interfaces}.py   (신규)
├── src/domain/knowledge_base/quick_setup_policy.py                  (신규)
├── src/domain/knowledge_base/interfaces.py                          (수정: assign kb_id kwarg)
├── src/domain/agent_create_pipeline/policies.py                     (수정: with_knowledge_tool)
├── src/application/kb_default_setting/{__init__,use_case}.py        (신규)
├── src/application/knowledge_base/collection_assigner.py            (수정: AutoProvision 추가)
├── src/application/knowledge_base/use_case.py                       (수정: id 선생성·롤백 로그)
├── src/application/knowledge_base/quick_create_use_case.py          (신규)
├── src/application/agent_create_pipeline/use_case.py                (수정: kb_id)
├── src/infrastructure/kb_default_setting/{__init__,models,repository}.py   (신규)
├── src/api/routes/admin_kb_defaults_router.py                       (신규)
├── src/api/routes/kb_defaults_router.py                             (신규)
├── src/api/routes/knowledge_base_router.py                          (수정: /quick, collection_name optional)
├── src/api/routes/agent_pipeline_router.py                          (수정: kb_id 전달·에코)
├── src/interfaces/schemas/agent_pipeline.py                         (수정)
├── src/api/main.py                                                  (수정: DI·라우터 등록)
└── tests/{domain,application,api,db}/...                            (신규)

idt_front/src/
├── types/kbQuickSetup.ts                                            (신규)
├── utils/kbQuickSetup.ts                                            (신규)
├── services/kbQuickSetupService.ts                                  (신규)
├── hooks/useQuickKnowledgeBase.ts, hooks/useKbDefaults.ts           (신규)
├── components/agent-builder/KnowledgeDocsBlock.tsx                  (신규)
├── components/agent-builder/RagConfigPanel.tsx                      (수정: 고급 접기)
├── components/agent-builder/LeftConfigPanel.tsx                     (수정: 블록 마운트)
├── pages/AgentBuilderPage/index.tsx                                 (수정: onAttached, KB settled 가드)
├── pages/AgentCreateEntryPage/index.tsx                             (수정: documents 단계·kbId)
├── pages/AgentCreateEntryPage/components/DocumentsStep.tsx          (신규)
├── pages/AdminKbDefaultsPage/index.tsx                              (신규)
├── store/agentDraftStore.ts (WizardResult.kbId?)                    (수정)
├── utils/wizardResultToForm (attachKbToForm 호출)                   (수정)
├── types/agentPipeline.ts (kb_id)                                   (수정)
├── constants/api.ts, constants/adminNav.ts, App.tsx                 (수정)
└── __tests__ / *.test.tsx                                           (신규·수정)
```

### 11.2 Implementation Order

1. [ ] V084 + 도메인 엔티티·에러 + 리포지토리 + `KbDefaultSettingUseCase` + 관리자/사용자 라우터 (테스트 선행)
2. [ ] `KbQuickSetupPolicy` + `AutoProvisionCollectionAssigner` + `KnowledgeBaseUseCase.create` id 선생성 + 라우터 `collection_name` optional + DI
3. [ ] `QuickCreateKnowledgeBaseUseCase` + `/quick` 라우터 + AST 계약 테스트(흡수 지점 1곳)
4. [ ] 프론트 타입·서비스·훅 + `KnowledgeDocsBlock` + `LeftConfigPanel` 마운트 + `RagConfigPanel` 고급 접기 + `AdminKbDefaultsPage` + nav/route
5. [ ] 파이프라인 `kb_id` (스키마·`_run_kwargs`·`_Run`·`_run_create`·`PipelinePolicy`·응답 에코) + 테스트
6. [ ] 위저드 `documents` 단계 + `DocumentsStep` + `WizardResult.kbId` + `wizardResultToForm` + 통합 테스트
7. [ ] 회귀 `FAILED` diff(백엔드·프론트) + 실런 스모크 SC-1·SC-2·SC-4

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---:|
| 기본 임베딩 설정 + 자동 컬렉션 | `module-1` | 순서 1~2: V084, 설정 UseCase·라우터, 자동 배정기, KB 생성 optional | 40-50 |
| 원스톱 API | `module-2` | 순서 3: `/quick` UseCase·라우터·계약 테스트 | 25-35 |
| 스튜디오 + 관리자 화면 | `module-3` | 순서 4: 블록·훅·고급 접기·관리자 페이지·nav | 45-55 |
| 위저드 + 파이프라인 | `module-4` | 순서 5~6: `kb_id` 전달·문서 단계·핸드오프 | 40-50 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:---:|
| Session 1 | Plan + Design | 전체 | 완료 |
| Session 2 | Do | `--scope module-1` | 40-50 |
| Session 3 | Do | `--scope module-2` | 25-35 |
| Session 4 | Do | `--scope module-3` | 45-55 |
| Session 5 | Do | `--scope module-4` | 40-50 |
| Session 6 | Check + Report | 전체 + 실런 스모크 | 30-40 |

module-1·2는 백엔드 단독 PR로 먼저 머지 가능. module-3는 module-2 머지 후, module-4는 module-2·3 후.

---

## 12. Plan FR 역추적

| Plan FR | Design 위치 |
|---|---|
| FR-01 기본 임베딩 설정 | §3.1, §3.3, §4.2 admin |
| FR-02 자동 컬렉션 | §9.4 Assigner 순서, §4.2 KB 생성 변경 |
| FR-03 미설정 422 | §6.1 `KB_DEFAULTS_NOT_CONFIGURED` |
| FR-04 원스톱 API | §4.2 `/quick` |
| FR-05 기본 청킹 | `/quick`은 `KnowledgeBaseUseCase.create` 기본 인자(청킹 미지정) → 업로드 시 `ChunkingSettingsResolver`가 `is_default` 해석(기존) |
| FR-06 블록·이름·범위 | §3.1 `kbNameForAgent`·`scopeForVisibility`, §5.1 |
| FR-07 RAG 자동 부착 | §3.1 `attachKbToForm` |
| FR-08 진행·부분 실패 | §5.4 블록 체크리스트, §8.3 #2·#3 |
| FR-09 기존 KB 선택 | §5.1 드롭다운 |
| FR-10 고급 접기 | §5.1 RagConfigPanel |
| FR-11 위저드 단계 | §2.2, §5.1, §5.4 |
| FR-12 파이프라인 kb_id | §4.2 agent-pipeline, §9.4 `with_knowledge_tool` |
| FR-13 핸드오프 kbId | §10.4, `WizardResult.kbId` |
| FR-14 관리자 화면 | §5.1, §5.4 |
| FR-15 기존 화면 노출 | 자동 KB·컬렉션은 기존 테이블 행이므로 추가 작업 없음. L3 #1에서 확인 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-05 | Initial draft — Option C 선택 | 배상규 |
