# Plan: MCP 서버 등록/관리 (Admin UI + 연결 테스트)

> Created: 2026-06-18
> Feature: mcp-registry-admin-ui
> Phase: Plan
> Author: 배상규

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | MCP 서버 CRUD 백엔드 API(`/api/v1/mcp-registry`)는 이미 완성되어 있으나, 이를 관리할 **프론트엔드 화면이 전혀 없어** 운영자가 직접 DB/API 호출로만 MCP 서버를 등록·수정·삭제해야 한다. |
| **Solution** | 기존 백엔드 CRUD API를 **그대로 재사용**하고, `idt_front`에 Admin 전용 `/admin/mcp-servers` 관리 화면을 신규 구축한다. 등록 폼은 SSE·Streamable HTTP 두 transport와 시크릿(api_key·profile·headers·server_config)을 모두 지원하며, **연결 테스트 버튼**으로 등록 전/후 `list_tools` 검증이 가능하다. (연결 테스트용 백엔드 엔드포인트 1개만 신규 추가) |
| **Function UX Effect** | 운영자가 GUI에서 MCP 서버를 목록 조회·등록·수정·삭제하고, 저장 전 실제 연결을 테스트해 도구 목록을 확인할 수 있다. Admin 사이드바에 "MCP 서버" 메뉴가 추가되어 기존 부서/사용자 관리와 동일한 UX로 일관성을 유지한다. |
| **Core Value** | MCP 서버 운영의 **자가 서비스(self-service)화** — 개발자 개입 없이 비개발 운영자도 안전하게(시크릿 마스킹·암호화 유지) MCP 도구 소스를 관리하고, 연결 오류를 등록 시점에 즉시 검증해 런타임 장애를 예방한다. |

---

## 1. 배경 및 현황 분석

### 1-1. 현재 상태 (코드베이스 조사 결과)

**백엔드 (`idt/`) — CRUD API 이미 완성됨 ✅**

| 구성요소 | 경로 | 상태 |
|----------|------|------|
| 라우터 (CRUD 5종) | `src/api/routes/mcp_registry_router.py` | ✅ 존재 |
| DI 연결 | `src/api/main.py` (`create_mcp_registry_factories`, line ~2292/2679/2860) | ✅ 연결됨 |
| UseCase | `src/application/mcp_registry/{register,list,update,delete}_mcp_server_use_case.py` | ✅ 존재 |
| Request/Response 스키마 | `src/application/mcp_registry/schemas.py` | ✅ 존재 |
| Repository (Fernet 암호화) | `src/infrastructure/mcp_registry/mcp_server_repository.py` | ✅ 존재 |
| ORM 모델 | `src/infrastructure/mcp_registry/models.py` (`mcp_server_registry`) | ✅ 존재 |
| Tool Loader / Call Client | `src/infrastructure/mcp_registry/mcp_tool_loader.py`, `src/infrastructure/mcp/call_client.py` | ✅ 존재 |
| 시크릿 마이그레이션 | `db/migration/V032__alter_mcp_server_registry_add_secrets.sql` | ✅ 존재 |

**기존 API 엔드포인트 (재사용 대상)**

| Method | Path | 설명 | 응답 |
|--------|------|------|------|
| POST | `/api/v1/mcp-registry` | 등록 (body: `RegisterMCPServerRequest`) | 201, `MCPServerResponse` |
| GET | `/api/v1/mcp-registry?user_id=` | 목록 (user_id 미지정 시 전체 active) | 200, `ListMCPServersResponse` |
| GET | `/api/v1/mcp-registry/{id}` | 단건 조회 | 200 / 404 |
| PUT | `/api/v1/mcp-registry/{id}` | 수정 (body: `UpdateMCPServerRequest`) | 200 / 404 / 422 |
| DELETE | `/api/v1/mcp-registry/{id}` | 삭제 | 204 / 404 |

**프론트엔드 (`idt_front/`) — 화면 전무 ❌**

- `idt_front` 전체에 MCP 관련 파일 **0개** (서비스/타입/훅/페이지/라우트 모두 없음).
- 이것이 본 작업의 **실제 핵심 갭**이다.

### 1-2. 사용자 확정 결정사항 (Plan 인터뷰)

| # | 질문 | 결정 |
|---|------|------|
| Q1 | 소유 모델 | **Admin 전용 (전체 관리)** — `/admin/mcp-servers`, AdminRoute 보호 |
| Q2 | 백엔드 처리 | **그대로 재사용 (프론트만 구축)** |
| Q3 | 폼 범위 | **두 transport 모두 + 시크릿 전부** (SSE·Streamable HTTP / api_key·profile·headers·server_config) |
| Q4 | 연결 테스트 | **포함 (테스트 버튼)** |

> ⚠️ **결정 간 충돌 해소**: Q2("프론트만 구축")와 Q4("연결 테스트 포함")는 일부 상충한다. 현재 백엔드에는 연결 테스트(`list_tools`) 전용 HTTP 엔드포인트가 **없으므로**, Q4를 충족하려면 백엔드에 **테스트 엔드포인트 1개만** 신규 추가가 불가피하다. CRUD 자체는 기존 API를 그대로 재사용한다.

---

## 2. 목표 및 비목표 (Scope)

### 2-1. 목표 (In Scope)

1. **Admin 전용 MCP 서버 관리 화면** (`/admin/mcp-servers`) 신규 구축.
2. 목록 조회 / 등록 / 수정 / 삭제 (CRUD) — 기존 백엔드 API 연동.
3. 등록·수정 폼: **SSE · Streamable HTTP** transport 선택 + transport별 동적 필드(시크릿 포함).
4. **연결 테스트 버튼**: 입력한(또는 저장된) MCP 서버에 실제 연결해 `list_tools` 결과 표시 → 이를 위한 **백엔드 테스트 엔드포인트 1개** 추가.
5. 시크릿 마스킹 UX (응답 `****` 처리) 및 수정 시 "미입력 = 기존 유지" 정책.
6. API 계약 동기화 (백엔드 스키마 ↔ 프론트 타입).

### 2-2. 비목표 (Out of Scope)

- 사용자별 "My MCP 서버" 개인 화면 (Q1에서 Admin 전용으로 확정 — 후속 과제).
- stdio / websocket transport (백엔드 registry 정책상 SSE·Streamable HTTP만 허용).
- MCP 서버에서 로드된 도구의 Agent 연결/실행 흐름 변경 (이미 존재, 본 작업 무관).
- 백엔드 CRUD 로직 변경 (테스트 엔드포인트 외 백엔드 수정 없음).
- 백엔드 엔드포인트의 admin RBAC 가드 추가 (Q2 "그대로 재사용" — §6 리스크로 기록만).

---

## 3. 백엔드 작업 (최소 — 연결 테스트 엔드포인트만)

### 3-1. 신규 엔드포인트

**옵션 A (권장): 저장된 서버 테스트**
```
POST /api/v1/mcp-registry/{id}/test
→ 200 { "ok": true, "tools": [{"name","description"}], "elapsed_ms": 123 }
→ 200 { "ok": false, "error": "<연결 실패 사유>" }  (연결 실패는 4xx 아닌 본문 플래그로)
→ 404 (서버 미존재)
```

**옵션 B (선택): 저장 전 테스트** — body로 config를 받아 검증 (등록 폼에서 저장 없이 테스트).
- MVP에서는 **옵션 A 우선**, 저장 전 테스트는 후속 여유 시.

### 3-2. 구현 매핑 (기존 자산 재사용)

| 레이어 | 작업 | 재사용 대상 |
|--------|------|------------|
| application | `TestMCPConnectionUseCase.execute(id, request_id)` 신규 | `MCPServerRepository.find_by_id`, `MCPToolLoader`/`MCPCallClient.list_tools` |
| infrastructure | 추가 없음 (기존 `call_client.py`/`mcp_tool_loader.py` 활용) | — |
| interfaces | 라우터에 `@router.post("/{id}/test")` 추가 + main.py DI 1줄 | 기존 factory 패턴 |
| domain | 규칙 변경 없음 | — |

- **TDD 필수**: `tests/application/mcp_registry/test_test_connection_use_case.py` (성공/연결실패/미존재) → Red → 구현 → Green.
- 연결 실패는 예외를 삼켜 `ok:false`로 반환(스택트레이스 로깅은 유지) — 운영자 친화적 응답.

### 3-3. 응답 스키마 추가 (`schemas.py`)
```python
class MCPConnectionTestResponse(BaseModel):
    ok: bool
    tools: list[dict] | None = None      # [{"name","description"}]
    error: str | None = None
    elapsed_ms: int | None = None
```

---

## 4. 프론트엔드 작업 (핵심)

> 기존 Admin CRUD 페이지(부서 관리 `AdminDepartmentsPage`) 패턴을 그대로 따른다.

### 4-1. 신규/수정 파일

| 구분 | 파일 | 내용 |
|------|------|------|
| 타입 | `src/types/mcpServer.ts` (신규) | `McpServer`, `McpTransport`, `Register/Update Request`, `ListResponse`, `ConnectionTestResponse` |
| 엔드포인트 상수 | `src/constants/api.ts` (수정) | `MCP_SERVERS`, `MCP_SERVER_DETAIL(id)`, `MCP_SERVER_TEST(id)` |
| 서비스 | `src/services/mcpServerService.ts` (신규) | get/create/update/delete/test (authClient) |
| 훅 | `src/hooks/useMcpServers.ts` (신규) | `useMcpServers`, `useCreate/Update/DeleteMcpServer`, `useTestMcpConnection` (TanStack Query) |
| 쿼리키 | `src/lib/queryKeys.ts` (수정) | `admin.mcpServers()`, `admin.mcpServer(id)` |
| 페이지 | `src/pages/AdminMcpServersPage/index.tsx` (신규) | 목록 테이블 + 등록/수정 모달 + 삭제 ConfirmDialog + 테스트 결과 |
| 라우트 | `src/App.tsx` (수정) | `<Route path="/admin/mcp-servers" .../>` (AdminRoute·AdminLayout 하위) |
| 내비 | `src/constants/adminNav.ts` (수정) | `ADMIN_NAV_ITEMS`에 "MCP 서버" 항목 추가 |

### 4-2. 화면 구성

1. **헤더**: 제목 "MCP 서버 관리" + 설명 + "서버 등록" 버튼.
2. **목록 테이블**: name / endpoint / transport(뱃지) / is_active(토글 상태) / tool_id / 생성일 / 액션(수정·삭제·테스트).
3. **등록·수정 모달** (동적 폼):
   - 공통: name, description, endpoint, transport(select: SSE | Streamable HTTP), is_active(수정 시).
   - `transport === streamable_http` 일 때만 노출: `auth_config.api_key`(필수), `auth_config.profile`, `auth_config.headers`(키-값), `server_config`(키-값 또는 JSON textarea).
   - `transport === sse` 일 때: api_key 선택, headers 선택.
4. **연결 테스트**: 모달 내 "연결 테스트" 버튼 → 결과 패널(성공 시 도구 목록 / 실패 시 에러 메시지·재시도).
5. **삭제**: 공용 `ConfirmDialog`.
6. 상태: 로딩 / 에러+재시도 / 빈 상태 CTA.

### 4-3. 핵심 UX 정책

- **시크릿 마스킹 처리**: 목록·단건 응답의 `auth_config`/`server_config`는 백엔드가 `****`로 마스킹해 내려준다.
  - 수정 모달에서 시크릿 필드는 **placeholder만 마스킹 표시**하고 값은 비워둔다.
  - **빈 값으로 두면 기존 시크릿 유지** = 해당 키를 PUT 본문에서 **제외**(`auth_config`/`server_config` 미전송).
  - 값을 새로 입력하면 **전체 dict 교체**(백엔드 `UpdateMCPServerRequest` 시맨틱이 full-replace이므로, 부분 변경 시 기존 값과 병합해 전송).
- **등록 시 `user_id`**: 백엔드 `RegisterMCPServerRequest`가 `user_id`(필수)를 받으므로, **현재 로그인 admin의 user_id**(`authStore`)를 주입한다. 목록은 `user_id` 필터 없이 **전체 조회**(`execute_all`).
- **react-hook-form/zod 미사용**: 기존 admin 페이지 컨벤션대로 `useState` + 수동 검증.
- **Tailwind 커스텀 컴포넌트**: 기존 테이블/모달/버튼 스타일 토큰(violet-600/zinc-*) 재사용.

---

## 5. API 계약 (백엔드 ↔ 프론트 타입 매핑)

| 백엔드 (`schemas.py`) | 프론트 (`types/mcpServer.ts`) |
|----------------------|------------------------------|
| `RegisterMCPServerRequest` | `RegisterMcpServerRequest` |
| `UpdateMCPServerRequest` | `UpdateMcpServerRequest` |
| `MCPServerResponse` | `McpServer` |
| `ListMCPServersResponse` (`items`, `total`) | `McpServerListResponse` |
| `MCPConnectionTestResponse` (신규) | `McpConnectionTestResponse` |

- `transport`: `"sse" | "streamable_http"` (리터럴 유니온).
- 날짜 필드(`created_at`/`updated_at`)는 string(ISO).
- **`/api-contract-sync` 스킬**로 타입 동기화 검증.

---

## 6. 리스크 & 주의사항

| # | 리스크 | 영향 | 완화 |
|---|--------|------|------|
| R1 | 기존 MCP 엔드포인트는 `/admin` 하위가 아니며 **백엔드 RBAC 가드가 없다** (프론트 AdminRoute로만 보호). | 인증된 일반 사용자가 직접 API 호출 시 MCP 관리 가능 | Q2 "그대로 재사용" 결정 → 본 Plan에서는 **기록만**. 후속으로 백엔드 admin 가드 추가 권고. |
| R2 | 시크릿 full-replace 시맨틱으로 부분 수정 시 기존 시크릿 유실 가능 | 운영 사고 | §4-3 "미입력=제외, 입력=병합 후 전송" 정책 강제 + 테스트 |
| R3 | 연결 테스트가 외부 MCP 서버에 실제 네트워크 호출 → 지연/타임아웃 | UX 멈춤 | 로딩 스피너 + 백엔드 타임아웃(`MCPTimeoutConfig`) 적용, 실패는 `ok:false` 본문 |
| R4 | 등록 `user_id` 의미 모호(누가 소유?) | 데이터 일관성 | admin user_id 주입으로 통일, 목록은 전체 조회 |
| R5 | 교차 실행 시 백엔드 pytest 이벤트 루프 산발 실패(기존 알려진 이슈) | 테스트 오탐 | MCP 테스트는 격리 실행으로 검증 |

---

## 7. 작업 순서 (구현 체크리스트 — Design 단계에서 상세화)

**백엔드 (TDD)**
- [ ] `test_test_connection_use_case.py` 작성 (Red)
- [ ] `TestMCPConnectionUseCase` 구현 + `MCPConnectionTestResponse` 스키마
- [ ] 라우터 `POST /{id}/test` + main.py DI
- [ ] 라우터 테스트 (성공/실패/404)

**프론트 (TDD: Vitest + MSW)**
- [ ] `types/mcpServer.ts`, `constants/api.ts`
- [ ] `mcpServerService.ts` + MSW 핸들러 + 서비스 테스트
- [ ] `useMcpServers.ts` 훅 + 훅 테스트
- [ ] `AdminMcpServersPage` (목록→등록→수정→삭제→테스트) + 컴포넌트 테스트
- [ ] `App.tsx` 라우트 + `adminNav.ts` 메뉴
- [ ] 빈/로딩/에러 상태

**통합**
- [ ] `/api-contract-sync` 검증
- [ ] 수동 E2E (등록→테스트→수정→삭제)

---

## 8. 완료 기준 (Acceptance Criteria)

1. Admin이 `/admin/mcp-servers`에서 MCP 서버 목록을 조회한다. (비-admin 접근 차단)
2. SSE·Streamable HTTP 서버를 시크릿과 함께 등록한다.
3. 등록/저장된 서버에 "연결 테스트"로 도구 목록 또는 명확한 실패 사유를 확인한다.
4. 수정 시 시크릿을 비워두면 기존 값이 유지된다.
5. 삭제 시 확인 다이얼로그 후 목록에서 제거된다.
6. 모든 신규 모듈에 테스트가 존재한다(TDD). 백엔드 변경은 테스트 엔드포인트로 한정된다.
7. 백엔드/프론트 타입이 동기화되어 있다.

---

## 9. 다음 단계

```
/pdca design mcp-registry-admin-ui
```

설계 단계에서 ① 백엔드 테스트 엔드포인트 시그니처/에러 매핑, ② 프론트 컴포넌트 트리·상태 다이어그램, ③ 동적 폼 필드 스펙(transport별), ④ 시크릿 병합 로직을 구체화한다.
