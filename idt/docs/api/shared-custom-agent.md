# shared-custom-agent API

> 에이전트 공유(visibility), Temperature 설정, 부서 관리, 통합 도구 카탈로그 API

## 개요

| 항목 | 내용 |
|------|------|
| Base URL | `/api/v1` |
| Auth | Bearer Token (`get_current_user` / `AdminUser` dependency) |

---

## 엔드포인트 목록

| Method | Path | 설명 | 권한 |
|--------|------|------|------|
| GET | `/agents` | 에이전트 목록 (scope 필터) | CurrentUser |
| POST | `/agents` | 에이전트 생성 (visibility/temperature 포함) | CurrentUser |
| GET | `/agents/{agent_id}` | 에이전트 상세 조회 (접근 제어) | CurrentUser |
| PATCH | `/agents/{agent_id}` | 에이전트 수정 (접근 제어) | CurrentUser |
| DELETE | `/agents/{agent_id}` | 에이전트 삭제 (소유자/admin) | CurrentUser |
| POST | `/agents/{agent_id}/run` | 에이전트 실행 (접근 제어 + temperature) | CurrentUser |
| GET | `/departments` | 부서 목록 | CurrentUser |
| POST | `/departments` | 부서 생성 | AdminUser |
| PATCH | `/departments/{id}` | 부서 수정 | AdminUser |
| DELETE | `/departments/{id}` | 부서 삭제 | AdminUser |
| POST | `/users/{user_id}/departments` | 사용자-부서 배정 | AdminUser |
| DELETE | `/users/{user_id}/departments/{dept_id}` | 사용자-부서 해제 | AdminUser |
| GET | `/tool-catalog` | 도구 카탈로그 목록 (활성만) | CurrentUser |
| POST | `/tool-catalog/sync` | MCP 도구 동기화 | AdminUser |

---

## 상세 스펙

### GET /agents

에이전트 목록 조회. scope에 따라 접근 가능한 에이전트만 반환.

**Query Parameters**

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| scope | string | `"all"` | `mine` / `department` / `public` / `all` |
| search | string | null | 이름/설명 검색 (LIKE) |
| page | int | 1 | 페이지 번호 (>= 1) |
| size | int | 20 | 페이지 크기 (1~100) |

**Response**
```json
{
  "agents": [
    {
      "agent_id": "uuid",
      "name": "문서 분석 에이전트",
      "description": "...",
      "visibility": "department",
      "department_name": "금융팀",
      "owner_user_id": "123",
      "owner_email": "user@example.com",
      "temperature": 0.70,
      "can_edit": false,
      "can_delete": false,
      "created_at": "2026-04-20T10:00:00"
    }
  ],
  "total": 42,
  "page": 1,
  "size": 20
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 401 | 인증 실패 |

---

### POST /agents

에이전트 생성. visibility, temperature, department_id 지원.

**Request**
```json
{
  "user_request": "금융 보고서 분석 에이전트",
  "name": "금융 분석 에이전트",
  "user_id": "123",
  "llm_model_id": "uuid-or-null",
  "visibility": "department",
  "department_id": "dept-uuid",
  "temperature": 0.70
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| user_request | string | Y | 에이전트 생성 요청 (max 1000자) |
| name | string | Y | 에이전트 이름 (max 200자) |
| user_id | string | Y | 생성자 ID |
| llm_model_id | string | N | LLM 모델 ID |
| visibility | string | N | `private`(기본) / `department` / `public` |
| department_id | string | N | 부서 ID (visibility=department 시 필수) |
| temperature | float | N | 0.0~2.0 (기본 0.70) |

**Response**
```json
{
  "agent_id": "uuid",
  "name": "금융 분석 에이전트",
  "system_prompt": "...",
  "tool_ids": ["internal:excel_export", "internal:internal_document_search"],
  "workers": [
    {
      "name": "analyzer",
      "tools": ["internal:internal_document_search"]
    }
  ],
  "flow_hint": "sequential",
  "llm_model_id": "uuid",
  "visibility": "department",
  "department_id": "dept-uuid",
  "temperature": 0.70,
  "created_at": "2026-04-20T10:00:00"
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 401 | 인증 실패 |
| 422 | 유효성 검증 실패 (temperature 범위, visibility+department_id 조합 등) |

---

### GET /agents/{agent_id}

에이전트 상세 조회. VisibilityPolicy에 따른 접근 제어 적용.

**Path Parameters**

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| agent_id | string | 에이전트 UUID |

**Response**
```json
{
  "agent_id": "uuid",
  "name": "금융 분석 에이전트",
  "description": "...",
  "system_prompt": "...",
  "tool_ids": ["internal:excel_export"],
  "workers": [],
  "flow_hint": "sequential",
  "llm_model_id": "uuid",
  "status": "active",
  "visibility": "department",
  "department_id": "dept-uuid",
  "department_name": "금융팀",
  "temperature": 0.70,
  "owner_user_id": "123",
  "can_edit": true,
  "can_delete": true,
  "created_at": "2026-04-20T10:00:00",
  "updated_at": "2026-04-20T10:00:00"
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 401 | 인증 실패 |
| 403 | 접근 권한 없음 (private 에이전트, 다른 부서 등) |
| 404 | 에이전트 없음 |

---

### PATCH /agents/{agent_id}

에이전트 수정. 소유자만 수정 가능 (`can_edit`).

**Request**
```json
{
  "system_prompt": "수정된 프롬프트",
  "name": "수정된 이름",
  "visibility": "public",
  "department_id": null,
  "temperature": 1.0
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| system_prompt | string | N | max 4000자 |
| name | string | N | max 200자 |
| visibility | string | N | `private` / `department` / `public` |
| department_id | string | N | 부서 ID |
| temperature | float | N | 0.0~2.0 |

**Response**: `GetAgentResponse`와 동일

**Error Codes**

| 코드 | 설명 |
|------|------|
| 401 | 인증 실패 |
| 403 | 수정 권한 없음 (소유자 아님) |
| 404 | 에이전트 없음 |
| 422 | 유효성 검증 실패 |

---

### DELETE /agents/{agent_id}

에이전트 삭제 (soft delete → status='deleted'). 소유자 또는 admin만 가능.

**Response**: `204 No Content`

**Error Codes**

| 코드 | 설명 |
|------|------|
| 401 | 인증 실패 |
| 403 | 삭제 권한 없음 |
| 404 | 에이전트 없음 |

---

### POST /agents/{agent_id}/run

에이전트 실행. VisibilityPolicy 접근 제어 + agent-specific temperature 적용.

**Request**
```json
{
  "message": "2024년 금융 보고서를 분석해주세요",
  "conversation_id": "conv-uuid-or-null"
}
```

**Response**: 기존 `RunAgentResponse` 스키마 유지

**Error Codes**

| 코드 | 설명 |
|------|------|
| 401 | 인증 실패 |
| 403 | 실행 권한 없음 |
| 404 | 에이전트 없음 |

---

### GET /departments

전체 부서 목록 조회.

**Response**
```json
{
  "departments": [
    {
      "id": "dept-uuid",
      "name": "금융팀",
      "description": "금융 분석 및 보고서 작성",
      "created_at": "2026-04-20T10:00:00",
      "updated_at": "2026-04-20T10:00:00"
    }
  ]
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 401 | 인증 실패 |

---

### POST /departments

부서 생성. admin 전용.

**Request**
```json
{
  "name": "금융팀",
  "description": "금융 분석 및 보고서 작성"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| name | string | Y | 부서명 (max 100자, 유니크) |
| description | string | N | 설명 (max 255자) |

**Response**
```json
{
  "id": "dept-uuid",
  "name": "금융팀",
  "description": "금융 분석 및 보고서 작성",
  "created_at": "2026-04-20T10:00:00",
  "updated_at": "2026-04-20T10:00:00"
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 401 | 인증 실패 |
| 403 | admin 아님 |
| 409 | 이름 중복 |

---

### PATCH /departments/{id}

부서 수정. admin 전용.

**Request**
```json
{
  "name": "금융분석팀",
  "description": "업데이트된 설명"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| name | string | N | 부서명 (max 100자) |
| description | string | N | 설명 (max 255자) |

**Response**: `DepartmentResponse`와 동일

**Error Codes**

| 코드 | 설명 |
|------|------|
| 401 | 인증 실패 |
| 403 | admin 아님 |
| 404 | 부서 없음 |
| 409 | 이름 중복 |

---

### DELETE /departments/{id}

부서 삭제. CASCADE로 user_departments 자동 정리.

**Response**: `204 No Content`

**Error Codes**

| 코드 | 설명 |
|------|------|
| 401 | 인증 실패 |
| 403 | admin 아님 |
| 404 | 부서 없음 |

---

### POST /users/{user_id}/departments

사용자를 부서에 배정. admin 전용.

**Path Parameters**

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| user_id | int | 사용자 ID |

**Request**
```json
{
  "department_id": "dept-uuid",
  "is_primary": true
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| department_id | string | Y | 부서 UUID |
| is_primary | bool | N | 주 소속 여부 (기본 false, 사용자당 최대 1개) |

**Response**: `201 Created`

**Error Codes**

| 코드 | 설명 |
|------|------|
| 401 | 인증 실패 |
| 403 | admin 아님 |
| 404 | 부서 없음 |
| 409 | 이미 배정됨 / is_primary 중복 |

---

### DELETE /users/{user_id}/departments/{dept_id}

사용자-부서 배정 해제. admin 전용.

**Path Parameters**

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| user_id | int | 사용자 ID |
| dept_id | string | 부서 UUID |

**Response**: `204 No Content`

**Error Codes**

| 코드 | 설명 |
|------|------|
| 401 | 인증 실패 |
| 403 | admin 아님 |
| 404 | 배정 기록 없음 |

---

### GET /tool-catalog

활성 도구 카탈로그 목록. internal + MCP 도구 통합 반환.

**Response**
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

**Error Codes**

| 코드 | 설명 |
|------|------|
| 401 | 인증 실패 |

---

### POST /tool-catalog/sync

MCP 서버의 도구를 스캔하여 tool_catalog에 동기화 (upsert). admin 전용.

**Request**
```json
{
  "mcp_server_id": "server-uuid-or-null"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| mcp_server_id | string | N | 특정 서버만 동기화. null이면 전체 활성 서버 대상 |

**Response**
```json
{
  "synced_count": 5
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 401 | 인증 실패 |
| 403 | admin 아님 |
| 404 | MCP 서버 없음 |
