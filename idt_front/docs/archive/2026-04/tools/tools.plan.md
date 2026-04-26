# Plan: tools

> AgentBuilderPage 도구 목록을 서버 API(`GET /api/v1/tool-catalog`)에서 받아오도록 교체

## 1. 목표

| 항목 | 내용 |
|------|------|
| Feature | AgentBuilder 도구 카탈로그 API 연동 |
| 우선순위 | P1 |
| 난이도 | Low |
| 예상 소요 | 1~2시간 |

## 2. 현재 상태 (As-Is)

- `src/pages/AgentBuilderPage/index.tsx`의 `AVAILABLE_TOOLS` 배열이 하드코딩
- 도구 6개가 정적으로 정의됨 (id, label, icon)
- 에이전트의 `tools` 필드는 이 하드코딩 id를 참조

## 3. 목표 상태 (To-Be)

- `GET /api/v1/tool-catalog` API를 호출하여 도구 목록을 동적으로 가져옴
- 서버 응답의 `tool_id`를 에이전트 폼의 도구 선택에 사용
- 로딩/에러 상태 처리
- 인증 필요 (Bearer Token — authClient 사용)

## 4. API 스펙

### GET /api/v1/tool-catalog

| 항목 | 값 |
|------|-----|
| Method | GET |
| Auth | Bearer Token (CurrentUser) |
| Request Body | 없음 |

**Response 200:**
```json
{
  "tools": [
    {
      "tool_id": "internal:excel_export",
      "source": "internal",
      "name": "Excel 파일 생성",
      "description": "pandas로 데이터를 Excel(.xlsx) 파일로 저장합니다.",
      "mcp_server_id": null,
      "mcp_server_name": null,
      "requires_env": []
    },
    {
      "tool_id": "mcp:server-uuid:search",
      "source": "mcp",
      "name": "search",
      "description": "MCP 서버의 검색 도구",
      "mcp_server_id": "server-uuid",
      "mcp_server_name": "Search Server",
      "requires_env": []
    }
  ]
}
```

**Error:**
| 코드 | 설명 |
|------|------|
| 401 | 인증 실패 |

## 5. 구현 범위

### 5-1. 타입 정의
- `src/types/toolCatalog.ts` — `CatalogTool`, `ToolCatalogResponse` 타입

### 5-2. API 상수 추가
- `src/constants/api.ts` — `TOOL_CATALOG` 엔드포인트 추가

### 5-3. 서비스 레이어
- `src/services/toolCatalogService.ts` — `getToolCatalog()` 메서드 (authClient 사용)

### 5-4. TanStack Query 훅
- `src/hooks/useToolCatalog.ts` — `useToolCatalog()` 훅 (queryKeys 팩토리 활용)

### 5-5. 페이지 수정
- `src/pages/AgentBuilderPage/index.tsx`
  - `AVAILABLE_TOOLS` 하드코딩 제거
  - `useToolCatalog()` 훅으로 도구 목록 fetch
  - 로딩/에러 UI 처리
  - `FormView`에서 서버 데이터로 도구 선택 렌더링

## 6. 구현 순서

```
1. [타입] src/types/toolCatalog.ts 작성
2. [상수] src/constants/api.ts에 TOOL_CATALOG 추가
3. [서비스] src/services/toolCatalogService.ts 작성
4. [쿼리키] src/lib/queryKeys.ts에 toolCatalog 키 추가
5. [훅] src/hooks/useToolCatalog.ts 작성
6. [페이지] AgentBuilderPage 수정 — Mock 제거, API 연동
```

## 7. 의존성

- `src/services/api/authClient.ts` — 인증된 axios 인스턴스 (이미 존재)
- `src/lib/queryClient.ts` — TanStack Query 설정 (이미 존재)
- `src/lib/queryKeys.ts` — 쿼리 키 팩토리 (이미 존재)

## 8. 테스트 계획

| 대상 | 테스트 내용 |
|------|-------------|
| `useToolCatalog` 훅 | 성공/실패 시나리오, 로딩 상태 |
| `FormView` 컴포넌트 | 도구 목록 렌더링, 선택 토글 동작 |
| MSW 핸들러 | `GET /api/v1/tool-catalog` 모킹 |

## 9. 영향 범위

- AgentBuilderPage의 도구 선택 UI만 변경
- 기존 에이전트 카드의 도구 표시도 서버 데이터 기반으로 전환
- 다른 페이지(ToolConnectionPage, ToolAdminPage)에는 영향 없음
