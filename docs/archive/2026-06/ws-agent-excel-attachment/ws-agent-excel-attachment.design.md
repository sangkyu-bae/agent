---
template: design
version: 1.2
feature: ws-agent-excel-attachment
date: 2026-06-06
author: 배상규
project: sangplusbot (idt 백엔드 + idt_front 프론트)
status: Draft
---

# ws-agent-excel-attachment Design Document

> **Summary**: 엑셀을 HTTP로 업로드해 `file_id`를 발급받고, `/ws/agent/{run_id}` subscribe 메시지가 그 참조를 실어 분석 노드까지 전달한다. run 종료 시 임시 파일을 자동 삭제한다.
>
> **Project**: sangplusbot
> **Author**: 배상규
> **Date**: 2026-06-06
> **Status**: Draft
> **Planning Doc**: [ws-agent-excel-attachment.plan.md](../../01-plan/features/ws-agent-excel-attachment.plan.md)

---

## 1. Overview

### 1.1 Design Goals

- `/ws/agent/{run_id}` 입구가 엑셀 첨부 참조를 수용하고, 기존 `RunAgentRequest.attachments`로 전달한다.
- 분석 노드(`workflow_compiler._create_analysis_node`)가 요구하는 **서버 `file_path`** 를 안전하게 공급한다.
- run 1회성: 업로드 파일은 run 종료(정상/예외/disconnect) 시 **반드시** 삭제한다.
- 첨부 타입은 `excel` 우선, **타입 추가에 열린(OCP)** 디스패치 구조로 둔다.
- 첨부 없는 기존 WS 경로는 **무변경**(하위 호환).

### 1.2 Design Principles

- **Thin DDD 준수**: 검증=domain 정책, 흐름=application, 파일 I/O=infrastructure, 입구=interfaces.
- **과도한 추상화 회피** (idt/CLAUDE.md): DB 신설 없이 로컬 임시 디렉토리 + 사이드카 메타로 충분.
- **Fail-closed 보안**: file_id 추측 불가(uuid4), 업로더≠뷰어면 거부, 경로 traversal 차단.
- **WS는 JSON 텍스트 채널 유지**: 바이너리는 HTTP가 담당.

---

## 2. Architecture

### 2.1 Component Diagram

```
┌──────────────┐  1. POST multipart (xlsx)   ┌───────────────────────────┐
│  Front (SPA) │ ──────────────────────────▶ │ POST /api/v1/agent/        │
│  ChatPage    │ ◀── { file_id, type, ... } ─ │      attachments (HTTP)    │
│              │                              └────────────┬──────────────┘
│              │                                           │ save
│              │  2. WS subscribe                          ▼
│              │  { ..., attachments:[{type,file_id}] }  ┌──────────────────┐
│              │ ──────────────────────────────────────▶ │ AgentAttachment   │
│              │                                          │ Store (tmp dir)   │
└──────────────┘                                          └────────┬─────────┘
        ▲                                                          │ resolve(file_id)→path
        │  3. AgentRunEvent stream                                 ▼
┌───────┴────────────────────────────────────────────────────────────────────┐
│ ws_router.ws_agent_run                                                       │
│   resolve refs → RunAgentRequest.attachments=[{type,file_path,user_id}]      │
│   → RunAgentUseCase.stream → 분석 노드 → ExcelAnalysisWorkflow               │
│   finally: store.delete(file_id) for each  (4. 자동 삭제)                    │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

```
[Upload]  file → AttachmentPolicy.validate(ext,size) → Store.save → file_id 반환
[Run]     subscribe(attachments[file_id]) → Resolver.resolve(file_id, viewer_id)
          → 소유자 검증 → file_path → RunAgentRequest.attachments
          → stream → analysis_node → ExcelAnalysisWorkflow(file_path)
[Cleanup] stream 종료/예외/disconnect → finally → Store.delete(file_id)*
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| upload router | `UploadAttachmentUseCase` | 파일 저장 + file_id 발급 |
| `UploadAttachmentUseCase` | `AttachmentPolicy`(domain), `AgentAttachmentStore`(infra) | 검증 → 저장 |
| `ws_router.ws_agent_run` | `AttachmentResolver`(app) | file_id→file_path + 소유자 검증 |
| `AttachmentResolver` | `AgentAttachmentStore` | resolve / delete |
| 분석 노드 (기존) | `RunAgentRequest.attachments` | 변경 없음 — 이미 소비 |

---

## 3. Data Model

### 3.1 Domain (idt/src/domain/agent_attachment/)

```python
# value_objects.py
class AttachmentType(str, Enum):
    EXCEL = "excel"          # 확장 지점: CSV = "csv" 등 추가

@dataclass(frozen=True)
class AttachmentRef:
    file_id: str             # uuid4
    type: AttachmentType
    filename: str
    size: int

# policies.py
class AttachmentPolicy:
    """타입별 허용 확장자/최대 크기 규칙 (순수 규칙, 외부 의존 금지)."""
    ALLOWED_EXT: dict[AttachmentType, frozenset[str]] = {
        AttachmentType.EXCEL: frozenset({".xlsx", ".xls"}),
    }
    @classmethod
    def resolve_type(cls, filename: str) -> AttachmentType: ...   # ext→type
    @classmethod
    def validate(cls, filename: str, size: int, max_size: int) -> None:
        # 미허용 확장자 → InvalidAttachmentError
        # size > max_size → AttachmentTooLargeError
```

> 도메인 예외: `InvalidAttachmentError`, `AttachmentTooLargeError`, `AttachmentNotFoundError`, `AttachmentAccessDeniedError`.

### 3.2 Store metadata (사이드카 JSON, DB 미사용)

저장 경로(파일별 결정적): `{upload_dir}/{file_id}{ext}`
메타: `{upload_dir}/{file_id}.meta.json`

| Field | Type | 설명 |
|-------|------|------|
| file_id | str(uuid4) | 추측 불가 식별자 |
| type | str | "excel" |
| filename | str | 원본 파일명(표시용, sanitized) |
| owner_user_id | str | 업로더 — 뷰어 검증용 |
| size | int | 바이트 |
| created_at | str(ISO) | TTL 백업 정리 기준 |

> 단일 프로세스(WS sticky) 전제. 사이드카 메타로 프로세스 재기동에도 소유자 검증 가능.
> in-memory dict 대신 파일 메타를 택해 누수·정합성 위험을 줄인다.

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/api/v1/agent/attachments` | 엑셀 업로드 → file_id 발급 | Required(JWT) |

> WS subscribe는 엔드포인트가 아닌 wire 메시지 변경(§4.3).

### 4.2 `POST /api/v1/agent/attachments`

**Request** (multipart/form-data):
- `file`: UploadFile (`.xlsx`/`.xls`)
- 인증 사용자(JWT) = owner_user_id (Form `user_id` 신뢰 금지)

**Response (201):**
```json
{
  "file_id": "8f3c...uuid",
  "type": "excel",
  "filename": "sales_2026.xlsx",
  "size": 20480
}
```

**Errors:**
- `400 INVALID_ATTACHMENT` — 미허용 확장자
- `413 ATTACHMENT_TOO_LARGE` — 최대 크기 초과
- `401 Unauthorized` — 토큰 없음/무효

### 4.3 WS subscribe wire protocol 변경 (`/ws/agent/{run_id}`)

```
C → S (첫 메시지):
{
  "type": "subscribe",
  "agent_id": "...",
  "query": "이 엑셀 매출 추이 분석해줘",
  "session_id": "optional",
  "attachments": [                 // ← 신규(optional, 없으면 기존과 동일)
    { "type": "excel", "file_id": "8f3c...uuid" }
  ]
}
```

서버 처리:
1. `SubscribeAgentRunPayload` 검증 (attachments optional).
2. 각 file_id에 대해 `AttachmentResolver.resolve(file_id, viewer_user_id=user.id)`:
   - 메타 없음 → `ATTACHMENT_NOT_FOUND`
   - owner ≠ viewer → `ATTACHMENT_ACCESS_DENIED`
   - OK → `{type, file_path, user_id}` 조립
3. `RunAgentRequest(query, user_id, session_id, attachments=resolved)` 생성.
4. 기존 `use_case.stream(...)` 그대로 — 분석 노드가 소비.
5. **finally**: resolve된 모든 file_id를 `store.delete()`.

검증 실패 시: `WSMessage(type="error", data={code, message})` 전송 후 `close(WSCloseCode.FORBIDDEN=4002)` (기존 INVALID_SUBSCRIBE와 동일 패턴).

---

## 5. UI/UX Design (프론트)

### 5.1 화면 (ChatPage)

```
┌──────────────────────────────────────────────┐
│  [📎]  메시지 입력...               [ 전송 ]  │
│   └ 클릭 시 .xlsx/.xls 파일 선택               │
│  ┌───────────────────────────┐                │
│  │ 📄 sales_2026.xlsx  ✕      │ ← 업로드된 칩  │
│  └───────────────────────────┘                │
└──────────────────────────────────────────────┘
```

### 5.2 User Flow

```
파일 선택 → (업로드 진행) → file_id 수신 → 첨부 칩 표시
→ 질문 입력 + 전송 → useAgentRunStream가 subscribe.attachments에 포함
→ 실시간 분석 스트리밍 표시
```

### 5.3 Component / Hook List

| 항목 | 위치 | 책임 |
|------|------|------|
| `agentAttachmentService` | `src/services/agentAttachmentService.ts` | multipart 업로드 → file_id |
| `useAgentAttachment` | `src/hooks/useAgentAttachment.ts` | 업로드 상태·file_id 보관(선택) |
| `useAgentRunStream` (수정) | `src/hooks/useAgentRunStream.ts` | subscribe에 attachments 추가 |
| ChatPage 첨부 UI | `src/pages/ChatPage/` | 파일 선택/칩/제거 |
| 타입 | `src/types/agentAttachment.ts` | `AgentAttachmentRef`, 업로드 응답 |
| 엔드포인트 상수 | `src/constants/api.ts` | `AGENT_ATTACHMENT_UPLOAD` |

---

## 6. Error Handling

### 6.1 Error Code 정의

| 계층 | Code | 원인 | 처리 |
|------|------|------|------|
| HTTP | 400 INVALID_ATTACHMENT | 미허용 확장자 | 프론트 토스트, 재선택 |
| HTTP | 413 ATTACHMENT_TOO_LARGE | 크기 초과 | 프론트 안내 |
| WS | INVALID_SUBSCRIBE | 페이로드 스키마 위반 | close 4002 |
| WS | ATTACHMENT_NOT_FOUND | file_id 만료/없음 | close 4002, 재업로드 유도 |
| WS | ATTACHMENT_ACCESS_DENIED | 업로더≠뷰어 | close 4002 |
| 분석 | (기존) "엑셀 분석 실패: ..." | 워크플로우 예외 | 그래프 비중단, 메시지 반환 |

### 6.2 Error Response Format (WS, 기존 유지)

```json
{ "type": "error", "data": { "code": "ATTACHMENT_NOT_FOUND", "message": "..." } }
```

---

## 7. Security Considerations

- [x] file_id = uuid4 (추측·열거 불가)
- [x] 소유자 검증: 업로드 owner_user_id == WS 인증 user.id (불일치 거부)
- [x] 경로 traversal 차단: 저장 경로는 file_id로만 구성, 원본 filename은 표시용으로만 보관(sanitize)
- [x] 확장자 allowlist + 최대 크기 제한(config)
- [x] HTTP 업로드 JWT 필수
- [x] run 종료 시 즉시 삭제 + TTL 백업 정리(누수 방지)
- [ ] (out of scope) 바이러스 스캔 / 콘텐츠 심층 검증

---

## 8. Test Plan (TDD — Red→Green)

### 8.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit | `AttachmentPolicy.validate/resolve_type` | pytest |
| Unit | `AgentAttachmentStore.save/resolve/delete` (tmp_path) | pytest |
| Unit | `UploadAttachmentUseCase`, `AttachmentResolver`(소유자 검증) | pytest |
| Integration | `ws_router.ws_agent_run` 첨부 전달 + finally 삭제 | pytest + ws test client |
| Regression | 첨부 없는 subscribe 기존 동작 무변경 | pytest |
| Front Unit | `agentAttachmentService` 업로드, `useAgentRunStream` subscribe 포함 | Vitest + MSW |

### 8.2 Test Cases (Key)

- [ ] Happy: 업로드→file_id→subscribe attachments→분석 노드 excel 분기 실행
- [ ] Cleanup: stream 정상 종료 후 파일 삭제됨
- [ ] Cleanup(예외): stream 중 예외/disconnect에도 `finally`로 삭제됨
- [ ] Security: 다른 user의 file_id → ATTACHMENT_ACCESS_DENIED, close 4002
- [ ] Validation: `.csv` 업로드 → 400 INVALID_ATTACHMENT (현재 excel만 허용)
- [ ] Regression: attachments 없는 subscribe → 기존과 동일 응답
- [ ] Edge: 존재하지 않는 file_id → ATTACHMENT_NOT_FOUND

---

## 9. Clean Architecture (idt Thin DDD)

### 9.1 레이어 배치

| Layer | 책임 | 위치 |
|-------|------|------|
| **interfaces** | 업로드 라우터, subscribe 스키마 확장, ws_router 첨부 해석/cleanup 연결 | `src/api/routes/agent_attachment_router.py`, `ws_schemas.py`, `ws_router.py` |
| **application** | `UploadAttachmentUseCase`, `AttachmentResolver` | `src/application/agent_attachment/` |
| **domain** | `AttachmentType`, `AttachmentRef`, `AttachmentPolicy`, 예외 | `src/domain/agent_attachment/` |
| **infrastructure** | `AgentAttachmentStore`(파일 I/O + 사이드카 메타) | `src/infrastructure/agent_attachment/store.py` |

### 9.2 Dependency Rules

```
interfaces → application → domain ← infrastructure
                        └→ infrastructure
규칙: domain은 외부 의존 0. 라우터에 비즈니스 로직 금지.
검증=domain, 흐름/조립=application, 파일 I/O=infrastructure.
```

### 9.3 Import 규칙 (위반 금지)

| From | Import 허용 | 금지 |
|------|------------|------|
| interfaces(router) | application, domain | infrastructure 직접 호출(검증 로직) |
| application | domain, infrastructure(인터페이스) | interfaces |
| domain | 없음(순수) | 모든 외부 레이어 |
| infrastructure | domain | application, interfaces |

> `AgentAttachmentStore`는 domain의 `AttachmentStoreInterface`(Protocol)를 구현, application은 인터페이스에 의존.

---

## 10. Coding Convention Reference

### 10.1 Naming / Rules (idt/CLAUDE.md)

| 대상 | 규칙 | 예 |
|------|------|-----|
| 클래스 | PascalCase, 단일 책임 | `AttachmentResolver` |
| 함수 | snake_case, 40줄 이내 | `resolve_type()` |
| 상수 | UPPER_SNAKE | `ALLOWED_EXT`, `ATTACHMENT_UPLOAD_DIR` |
| if 중첩 | 2단계 이내 | early return 활용 |
| 로깅 | print 금지, logger + 스택트레이스 | `logger.error(..., exception=e)` |

### 10.2 Config (하드코딩 금지 — `src/config.py` Settings)

| 변수 | 기본값 | 용도 |
|------|--------|------|
| `agent_attachment_upload_dir` | 시스템 tmp 하위 `agent_attachments/` | 임시 저장 경로 |
| `agent_attachment_max_bytes` | 10 * 1024 * 1024 | 업로드 최대 크기 |
| `agent_attachment_ttl_seconds` | 3600 | TTL 백업 정리 기준 |

### 10.3 환경/문서 동기화

- `.env.example`에 신규 설정 주석 추가
- API 계약 동기화(`/api-contract-sync`): 업로드 응답 스키마 ↔ `src/types/agentAttachment.ts`

---

## 11. Implementation Guide

### 11.1 파일 구조

```
idt/src/
├── domain/agent_attachment/
│   ├── value_objects.py        # AttachmentType, AttachmentRef
│   ├── policies.py             # AttachmentPolicy
│   ├── interfaces.py           # AttachmentStoreInterface (Protocol)
│   └── exceptions.py
├── application/agent_attachment/
│   ├── upload_use_case.py      # UploadAttachmentUseCase
│   └── resolver.py             # AttachmentResolver (file_id→path, owner check, delete)
├── infrastructure/agent_attachment/
│   └── store.py                # AgentAttachmentStore (tmp dir + sidecar meta)
└── api/routes/
    ├── agent_attachment_router.py   # POST /api/v1/agent/attachments
    ├── ws_schemas.py                # SubscribeAgentRunPayload.attachments
    └── ws_router.py                 # 해석 + finally cleanup

idt_front/src/
├── types/agentAttachment.ts
├── services/agentAttachmentService.ts
├── hooks/useAgentRunStream.ts       # subscribe.attachments
└── pages/ChatPage/                  # 첨부 UI
```

### 11.2 구현 순서 (TDD)

**Backend**
1. [ ] domain: `AttachmentType`/`AttachmentRef`/`AttachmentPolicy`/exceptions + 테스트(Red→Green)
2. [ ] infrastructure: `AgentAttachmentStore` save/resolve/delete + tmp_path 테스트
3. [ ] application: `UploadAttachmentUseCase`, `AttachmentResolver`(owner check) + 테스트
4. [ ] config: 3개 설정 추가 + `.env.example`
5. [ ] interfaces: `agent_attachment_router` + DI override(main.py lifespan, 기존 패턴)
6. [ ] interfaces: `SubscribeAgentRunPayload.attachments` + `ws_router` 해석/`finally` cleanup + 통합 테스트
7. [ ] 회귀: 첨부 없는 subscribe 무변경 확인

**Frontend** (API 계약 동기화)
8. [ ] types + `agentAttachmentService` + `api.ts` 상수 + Vitest(MSW)
9. [ ] `useAgentRunStream` subscribe attachments + 테스트
10. [ ] ChatPage 첨부 UI(선택/칩/제거) 연동

**검증**
11. [ ] `/verify-architecture`, `/verify-logging`, `/api-contract-sync`

### 11.3 DI 와이어링 (기존 패턴 재사용)

- `main.py` lifespan: `_attachment_store` 생성 → `get_*_attachment_*` placeholder를 `app.dependency_overrides`로 주입 (기존 `get_configured_excel_upload_use_case` 등과 동일 방식, line 2370~2477 영역).
- `ws_router`에 `get_ws_attachment_resolver()` placeholder 추가 → override.
- 분석 노드 측 `get_configured_excel_analysis_workflow` getter는 **이미 컴파일러에 주입됨**(main.py:1763) — 추가 작업 불필요.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-06-06 | 초안: 업로드 엔드포인트/file_id/WS wire/cleanup/Thin DDD 레이어 배치 확정 | 배상규 |
