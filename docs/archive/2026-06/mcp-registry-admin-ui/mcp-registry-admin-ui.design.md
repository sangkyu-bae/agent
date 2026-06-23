# Design: MCP 서버 등록/관리 (Admin UI + 연결 테스트)

> Created: 2026-06-18
> Feature: mcp-registry-admin-ui
> Phase: Design
> Plan: docs/01-plan/features/mcp-registry-admin-ui.plan.md
> Author: 배상규

---

## 0. 설계 개요

Plan에서 확정한 4대 결정(Admin 전용 / 백엔드 CRUD 재사용 / 두 transport+시크릿 전부 / 연결 테스트 포함)을 코드 레벨로 구체화한다.

- **백엔드**: CRUD는 기존 `mcp_registry_router.py` 그대로. **연결 테스트 엔드포인트 1개만 신규** 추가.
- **프론트**: `idt_front`에 Admin 전용 `/admin/mcp-servers` 화면을 부서 관리(`AdminDepartmentsPage`) 패턴으로 신규 구축.

설계 원칙: **기존 컨벤션을 그대로 복제**한다 (authClient + API_ENDPOINTS + TanStack Query + queryKeys + adminNav + useState 폼).

---

## 1. 아키텍처 흐름

```
[Admin Browser]
   /admin/mcp-servers (AdminRoute → AdminLayout)
        │
   AdminMcpServersPage (목록/모달/테스트 결과)
        │  TanStack Query
   useMcpServers / useCreate·Update·DeleteMcpServer / useTestMcpConnection
        │
   mcpServerService (authClient: Bearer + X-User-Id 자동 주입)
        │  HTTP
   ── 기존 ──────────────────────────────────────────────
   POST   /api/v1/mcp-registry              register
   GET    /api/v1/mcp-registry              list (전체 active)
   GET    /api/v1/mcp-registry/{id}         get
   PUT    /api/v1/mcp-registry/{id}         update
   DELETE /api/v1/mcp-registry/{id}         delete
   ── 신규 ──────────────────────────────────────────────
   POST   /api/v1/mcp-registry/{id}/test    connection test
        │
   라우터 → UseCase → Repository(Fernet 복호화) → MCPCallClient.list_tools
```

---

## 2. 백엔드 설계 (신규 = 연결 테스트만)

### 2-1. 신규 엔드포인트

```
POST /api/v1/mcp-registry/{id}/test
```

| 응답 | Body | 의미 |
|------|------|------|
| 200 | `{ "ok": true, "tools": [{"name","description"}], "elapsed_ms": 123 }` | 연결 성공 + 도구 목록 |
| 200 | `{ "ok": false, "error": "<사유>", "elapsed_ms": 0 }` | 연결/조회 실패 (HTTP는 200, 본문 플래그로 구분) |
| 404 | `{"detail":"MCP server not found"}` | 서버 미존재 |

> **설계 결정**: 연결 실패를 4xx/5xx가 아닌 **200 + `ok:false`** 로 내려 프론트가 "정상 응답 vs 서버 미존재(404)"를 명확히 구분. 단, 스택트레이스는 logger로 남긴다(LOG-001).

### 2-2. 응답 스키마 (`src/application/mcp_registry/schemas.py` 추가)

```python
class MCPConnectionTestResponse(BaseModel):
    ok: bool
    tools: list[dict] | None = None      # [{"name": str, "description": str}]
    error: str | None = None
    elapsed_ms: int | None = None
```

### 2-3. UseCase (신규)

`src/application/mcp_registry/test_mcp_connection_use_case.py`

```python
class TestMCPConnectionUseCase:
    def __init__(self, repository, logger):
        self._repo = repository
        self._logger = logger

    async def execute(self, id: str, request_id: str) -> MCPConnectionTestResponse | None:
        registration = await self._repo.find_by_id(id, request_id)
        if registration is None:
            return None                      # 라우터에서 404 매핑

        config = MCPToolLoader._build_config(registration)   # transport별 config 재사용
        client = MCPCallClient(config=config, logger=self._logger)
        try:
            descriptors = await client.list_tools(request_id)
            return MCPConnectionTestResponse(
                ok=True,
                tools=[{"name": d.name, "description": d.description} for d in descriptors],
            )
        except Exception as e:               # 연결/조회 실패는 삼켜 ok:false
            self._logger.error("MCP connection test failed",
                               request_id=request_id, server_id=id, exception=e)
            return MCPConnectionTestResponse(ok=False, error=str(e))
```

> **중요 설계 근거**: `MCPToolLoader.load()`는 내부 `MCPToolRegistry`가 연결 실패를 **빈 리스트로 조용히 삼키므로** 테스트 용도에 부적합하다. 따라서 **`MCPCallClient.list_tools()`를 직접 호출**해 실제 예외를 표면화한다. config 조립 로직(`_build_config`)은 SSE/Streamable HTTP 분기를 이미 담고 있어 재사용한다.
> `elapsed_ms`는 구현 시 측정(시작/종료 시각 차) — 단 스크립트성 `time` 사용은 인프라 레이어 규칙 내에서 처리.

### 2-4. 라우터 추가 (`mcp_registry_router.py`)

```python
def get_test_use_case():
    raise NotImplementedError

@router.post("/{id}/test", response_model=MCPConnectionTestResponse)
async def test_mcp_connection(id: str, use_case=Depends(get_test_use_case)):
    request_id = str(uuid.uuid4())
    result = await use_case.execute(id, request_id)
    if result is None:
        raise HTTPException(status_code=404, detail="MCP server not found")
    return result
```

### 2-5. DI 연결 (`src/api/main.py` — `create_mcp_registry_factories`)

```python
def test_factory(session: AsyncSession = Depends(get_session)):
    return TestMCPConnectionUseCase(repository=_make_repo(session), logger=app_logger)
# ...
app.dependency_overrides[get_test_use_case] = _mcp_test_f
```

기존 register/list/update/delete factory와 동일 패턴. `_make_repo`(Fernet cipher 포함) 재사용.

### 2-6. 레이어 영향 (DDD 준수)

| 레이어 | 변경 | 비고 |
|--------|------|------|
| domain | **없음** | 규칙/엔티티 불변 |
| application | UseCase 1 + Response 스키마 1 추가 | 비즈니스 규칙 직접 구현 금지 준수 |
| infrastructure | **없음** | 기존 `call_client.py` / `mcp_tool_loader.py` 재사용 |
| interfaces | 라우터 핸들러 1 + DI 1 | 비즈니스 로직 없음 |

---

## 3. 프론트엔드 설계 (핵심)

### 3-1. 타입 (`src/types/mcpServer.ts` 신규)

```typescript
export type McpTransport = 'sse' | 'streamable_http';

// 백엔드 MCPServerResponse 매핑 (시크릿은 **** 마스킹되어 옴)
export interface McpServer {
  id: string;
  user_id: string;
  name: string;
  description: string;
  endpoint: string;
  transport: McpTransport;
  input_schema: Record<string, unknown> | null;
  is_active: boolean;
  tool_id: string;
  created_at: string;
  updated_at: string;
  auth_config: Record<string, unknown> | null;   // masked
  server_config: Record<string, unknown> | null; // masked
}

// 백엔드 ListMCPServersResponse 매핑
export interface McpServerListResponse {
  items: McpServer[];
  total: number;
}

// 백엔드 RegisterMCPServerRequest 매핑 (user_id는 서비스에서 주입)
export interface RegisterMcpServerRequest {
  user_id: string;
  name: string;
  description: string;
  endpoint: string;
  transport: McpTransport;
  input_schema?: Record<string, unknown> | null;
  auth_config?: Record<string, unknown> | null;
  server_config?: Record<string, unknown> | null;
}

// 백엔드 UpdateMCPServerRequest 매핑 (모든 필드 optional)
export interface UpdateMcpServerRequest {
  name?: string;
  description?: string;
  endpoint?: string;
  transport?: McpTransport;
  is_active?: boolean;
  input_schema?: Record<string, unknown> | null;
  auth_config?: Record<string, unknown> | null;
  server_config?: Record<string, unknown> | null;
}

export interface McpConnectionTestResponse {
  ok: boolean;
  tools?: { name: string; description: string }[] | null;
  error?: string | null;
  elapsed_ms?: number | null;
}
```

### 3-2. 엔드포인트 상수 (`src/constants/api.ts` 추가)

```typescript
  // Admin — MCP Server Registry
  MCP_SERVERS: '/api/v1/mcp-registry',
  MCP_SERVER_DETAIL: (id: string) => `/api/v1/mcp-registry/${id}`,
  MCP_SERVER_TEST: (id: string) => `/api/v1/mcp-registry/${id}/test`,
```

> 기존 `ADMIN_DEPARTMENTS: '/api/v1/departments'`처럼 `/admin` 프리픽스 없는 경로가 이미 관례 — 일관성 유지.

### 3-3. 서비스 (`src/services/mcpServerService.ts` 신규)

```typescript
import authApiClient from '@/services/api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  McpServer, McpServerListResponse,
  RegisterMcpServerRequest, UpdateMcpServerRequest, McpConnectionTestResponse,
} from '@/types/mcpServer';

export const mcpServerService = {
  getServers: async (): Promise<McpServerListResponse> => {
    const { data } = await authApiClient.get<McpServerListResponse>(API_ENDPOINTS.MCP_SERVERS);
    return data;                                  // user_id 미전달 → 전체 active
  },
  createServer: async (req: RegisterMcpServerRequest): Promise<McpServer> => {
    const { data } = await authApiClient.post<McpServer>(API_ENDPOINTS.MCP_SERVERS, req);
    return data;
  },
  updateServer: async (id: string, req: UpdateMcpServerRequest): Promise<McpServer> => {
    const { data } = await authApiClient.put<McpServer>(API_ENDPOINTS.MCP_SERVER_DETAIL(id), req);
    return data;
  },
  deleteServer: async (id: string): Promise<void> => {
    await authApiClient.delete(API_ENDPOINTS.MCP_SERVER_DETAIL(id));
  },
  testConnection: async (id: string): Promise<McpConnectionTestResponse> => {
    const { data } = await authApiClient.post<McpConnectionTestResponse>(
      API_ENDPOINTS.MCP_SERVER_TEST(id),
    );
    return data;
  },
};
```

> ⚠️ 부서 서비스는 `patch`를 쓰지만 MCP 백엔드는 **`PUT`** 이다 — 백엔드 라우터에 맞춰 `put` 사용.

### 3-4. 쿼리키 (`src/lib/queryKeys.ts` — `admin` 블록에 추가)

```typescript
    /** MCP 서버 목록 */
    mcpServers: () => [...queryKeys.admin.all, 'mcpServers'] as const,
    /** 특정 MCP 서버 상세 */
    mcpServer: (id: string) => [...queryKeys.admin.mcpServers(), id] as const,
```

### 3-5. 훅 (`src/hooks/useMcpServers.ts` 신규)

```typescript
export const useMcpServers = () =>
  useQuery({ queryKey: queryKeys.admin.mcpServers(), queryFn: mcpServerService.getServers });

export const useCreateMcpServer = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: RegisterMcpServerRequest) => mcpServerService.createServer(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.admin.mcpServers() }),
  });
};

export const useUpdateMcpServer = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateMcpServerRequest }) =>
      mcpServerService.updateServer(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.admin.mcpServers() }),
  });
};

export const useDeleteMcpServer = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => mcpServerService.deleteServer(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.admin.mcpServers() }),
  });
};

// 테스트는 캐시 무효화 불필요 — 결과를 컴포넌트 로컬 상태로 표시
export const useTestMcpConnection = () =>
  useMutation({ mutationFn: (id: string) => mcpServerService.testConnection(id) });
```

### 3-6. 페이지 (`src/pages/AdminMcpServersPage/index.tsx` 신규)

컴포넌트 트리:

```
AdminMcpServersPage
├── Header (제목 "MCP 서버 관리" + "서버 등록" 버튼)
├── 상태 분기: Loading / Error+Retry / Empty(CTA)
├── ServerTable
│     └── row: name | endpoint | transport뱃지 | is_active | tool_id | 생성일 | [수정][삭제][테스트]
├── McpServerFormModal (등록·수정 공용, 동적 폼)
│     ├── 공통: name, description, endpoint, transport(select), is_active(수정 시)
│     ├── streamable_http 전용: auth_config.api_key*, profile, headers(KV), server_config(KV/JSON)
│     ├── sse: api_key(선택), headers(선택)
│     └── [연결 테스트] 버튼 → TestResultPanel
├── TestResultPanel (ok: 도구목록 / !ok: 에러+재시도)
└── ConfirmDialog (삭제, 공용 컴포넌트 재사용)
```

상태 관리(부서 페이지 컨벤션 = `useState`, react-hook-form/zod 미사용):

```
const [isModalOpen, setModalOpen] = useState(false);
const [editing, setEditing] = useState<McpServer | null>(null);
const [form, setForm] = useState<FormState>(initialForm);   // 평탄화된 폼 상태
const [deleteTarget, setDeleteTarget] = useState<McpServer | null>(null);
const [testResult, setTestResult] = useState<McpConnectionTestResponse | null>(null);
```

### 3-7. 라우트 (`src/App.tsx`) + 내비 (`src/constants/adminNav.ts`)

```tsx
// App.tsx — AdminRoute > AdminLayout 하위, departments 다음 줄
import AdminMcpServersPage from '@/pages/AdminMcpServersPage';
<Route path="/admin/mcp-servers" element={<AdminMcpServersPage />} />
```

```typescript
// adminNav.ts — ADMIN_NAV_ITEMS 배열에 항목 추가 (Agent Run 관측 뒤)
{
  label: 'MCP 서버',
  path: '/admin/mcp-servers',
  icon: '<Heroicons outline server/cpu 경로 'd' 속성>',
  description: 'MCP 서버 등록·수정·삭제 및 연결 테스트',
},
```

---

## 4. 동적 폼 필드 스펙 (transport별)

| 필드 | 폼 상태 키 | SSE | Streamable HTTP | 전송 매핑 |
|------|-----------|-----|-----------------|-----------|
| 이름 | `name` | 필수 | 필수 | `name` |
| 설명 | `description` | 필수 | 필수 | `description` |
| 엔드포인트 | `endpoint` | 필수(http/https) | 필수(http/https) | `endpoint` |
| Transport | `transport` | 선택 | 선택 | `transport` |
| 활성 | `is_active` | (수정 시) | (수정 시) | `is_active` |
| API Key | `apiKey` | 선택 | **필수** | `auth_config.api_key` |
| Profile | `profile` | 숨김 | 선택 | `auth_config.profile` |
| Headers | `headers[]` | 선택 | 선택 | `auth_config.headers` (KV→obj) |
| Server Config | `serverConfig[]` | 숨김 | 선택 | `server_config` (KV→obj) |

> Streamable HTTP에서 `api_key` 미입력 시 백엔드 `MCPRegistrationPolicy`가 422 반환 → 폼에서 선제 검증.

### 4-1. 시크릿 병합 정책 (수정 시 — R2 완화)

```
저장(수정) 시 auth_config 빌드:
  base = {}                               // 빈 객체에서 시작
  if (apiKey 입력됨)  base.api_key = apiKey
  if (profile 입력됨) base.profile = profile
  if (headers 입력됨) base.headers = headersToObj()
  → base가 비어있으면 auth_config 필드를 PUT 본문에서 "제외" (기존 값 유지)
  → 하나라도 입력되면 전체 dict 교체 (백엔드 full-replace 시맨틱)
server_config 동일 규칙.
```

- 마스킹 값(`****`)은 **절대 그대로 재전송하지 않는다**. 폼 초기값은 시크릿 필드를 **빈 값**으로 두고 placeholder에 "변경 시에만 입력" 안내.
- 수정 모달에 "기존 인증정보 유지됨(****)" 안내 텍스트 표시.

---

## 5. API 계약 매핑 (검증 체크)

| 백엔드 | 프론트 | 상태 |
|--------|--------|------|
| `RegisterMCPServerRequest` | `RegisterMcpServerRequest` | name/description/endpoint/transport/auth_config/server_config/input_schema + **user_id** |
| `UpdateMCPServerRequest` | `UpdateMcpServerRequest` | 전부 optional, **is_active 포함** |
| `MCPServerResponse` | `McpServer` | tool_id·masked auth/server_config 포함 |
| `ListMCPServersResponse` | `McpServerListResponse` | `items`·`total` (※ 부서의 `departments` 키와 다름 주의) |
| `MCPConnectionTestResponse`(신규) | `McpConnectionTestResponse` | ok/tools/error/elapsed_ms |

→ Do 단계 후 `/api-contract-sync` 스킬로 재검증.

---

## 6. 테스트 설계 (TDD)

### 6-1. 백엔드 (pytest, 격리 실행 권장)

`tests/application/mcp_registry/test_test_connection_use_case.py`

| 케이스 | Given | Then |
|--------|-------|------|
| 성공 | repo가 등록 반환 + client.list_tools가 디스크립터 반환 (mock) | `ok=True`, tools 매핑 |
| 연결 실패 | client.list_tools가 예외 | `ok=False`, error 메시지, 로깅 1회 |
| 미존재 | repo.find_by_id → None | `None` 반환 (라우터 404) |

라우터 테스트(`tests/api/...`): 200(ok)/200(!ok)/404 매핑.

### 6-2. 프론트 (Vitest + MSW, `--pool=threads`)

| 파일 | 케이스 |
|------|--------|
| `mcpServerService.test.ts` | 5개 메서드 각 호출 경로/메서드(PUT 확인) |
| `useMcpServers.test.ts` | list 쿼리, 각 mutation onSuccess 무효화, test mutation |
| `AdminMcpServersPage.test.tsx` | 목록 렌더 / 등록 모달 제출 / 수정 시 시크릿 빈값=미전송 / 삭제 confirm / 테스트 성공·실패 패널 / 빈·에러 상태 |

> MSW 핸들러는 `src/__tests__/mocks/handlers.ts`에 MCP 5종 추가.

---

## 7. 구현 순서 (Do 단계 체크리스트)

**백엔드 (TDD)**
1. `test_test_connection_use_case.py` (Red)
2. `MCPConnectionTestResponse` 스키마 + `TestMCPConnectionUseCase` (Green)
3. 라우터 `POST /{id}/test` + `get_test_use_case`
4. main.py DI (`test_factory` + override)
5. 라우터 테스트
6. `/verify-architecture`, `/verify-logging`

**프론트 (TDD)**
7. `types/mcpServer.ts` + `constants/api.ts`
8. `mcpServerService.ts` + MSW 핸들러 + 서비스 테스트
9. `queryKeys.ts` + `useMcpServers.ts` + 훅 테스트
10. `AdminMcpServersPage` (목록→폼모달→테스트→삭제) + 컴포넌트 테스트
11. `App.tsx` 라우트 + `adminNav.ts` 메뉴
12. 동적 폼 + 시크릿 병합 로직

**통합**
13. `/api-contract-sync`
14. 수동 E2E (등록→테스트→수정(시크릿 유지 확인)→삭제)

---

## 8. 미해결/주의 (Do 진입 전 확인)

1. **`elapsed_ms` 측정 방식**: 인프라 레이어 시간 측정 유틸 재사용 여부 — 없으면 UseCase에서 단순 측정(설계상 optional, 누락 허용).
2. **adminNav 아이콘**: Heroicons outline에서 server/cpu-chip 계열 path 'd' 확정 필요 (Do 단계 확정).
3. **R1(백엔드 RBAC 부재)**: 본 설계 범위 밖. 프론트 AdminRoute로만 보호. 후속 백엔드 가드 권고 유지.
4. **저장 전 테스트(옵션 B)**: 본 설계는 저장된 서버 테스트(`{id}/test`)만. 등록 폼에서 저장 전 테스트는 후속.

---

## 9. 다음 단계

```
/pdca do mcp-registry-admin-ui
```
