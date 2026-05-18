# department-management API

> 부서 CRUD + 사용자-부서 배정 관리 API (관리자 전용)

## 개요

| 항목 | 내용 |
|------|------|
| Base URL | `/api/v1` |
| Auth | Bearer Token (JWT) — 목록 조회는 일반 사용자, 나머지는 admin 역할 필요 |

---

## 엔드포인트 목록

| Method | Path | 설명 | 권한 |
|--------|------|------|------|
| GET | `/api/v1/departments` | 부서 전체 목록 조회 | 인증된 사용자 |
| POST | `/api/v1/departments` | 부서 생성 | admin |
| PATCH | `/api/v1/departments/{dept_id}` | 부서 수정 | admin |
| DELETE | `/api/v1/departments/{dept_id}` | 부서 삭제 | admin |
| POST | `/api/v1/users/{user_id}/departments` | 사용자에 부서 배정 | admin |
| DELETE | `/api/v1/users/{user_id}/departments/{dept_id}` | 사용자 부서 배정 해제 | admin |

---

## 상세 스펙

### GET /api/v1/departments

부서 전체 목록 조회. 인증된 모든 사용자 접근 가능.

**Headers**
```
Authorization: Bearer {access_token}
```

**Request**
```json
(Body 없음)
```

**Response** `200 OK`
```json
{
  "departments": [
    {
      "id": "uuid-string",
      "name": "개발팀",
      "description": "소프트웨어 개발 부서",
      "created_at": "2026-05-01T10:00:00",
      "updated_at": "2026-05-01T10:00:00"
    },
    {
      "id": "uuid-string",
      "name": "기획팀",
      "description": null,
      "created_at": "2026-05-02T09:00:00",
      "updated_at": "2026-05-02T09:00:00"
    }
  ]
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 401 Unauthorized | 인증 토큰 없음 또는 만료 |

---

### POST /api/v1/departments

새 부서 생성. **admin 권한 필요**.

**Headers**
```
Authorization: Bearer {access_token}  (role=admin)
```

**Request**
```json
{
  "name": "개발팀",
  "description": "소프트웨어 개발 부서"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| name | string | ✅ | 부서명 (최대 100자, UNIQUE) |
| description | string \| null | ❌ | 부서 설명 (최대 255자) |

**Response** `201 Created`
```json
{
  "id": "uuid-string",
  "name": "개발팀",
  "description": "소프트웨어 개발 부서",
  "created_at": "2026-05-05T10:00:00",
  "updated_at": "2026-05-05T10:00:00"
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 401 Unauthorized | 인증 토큰 없음 또는 만료 |
| 403 Forbidden | admin 역할이 아닌 경우 |
| 409 Conflict | 이미 존재하는 부서명 |
| 422 Unprocessable Entity | 유효성 검증 실패 (이름 누락, 길이 초과 등) |

---

### PATCH /api/v1/departments/{dept_id}

부서 정보 수정. 전달된 필드만 업데이트 (partial update). **admin 권한 필요**.

**Headers**
```
Authorization: Bearer {access_token}  (role=admin)
```

**Path Parameters**

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| dept_id | string (UUID) | 수정할 부서 ID |

**Request**
```json
{
  "name": "개발1팀",
  "description": "프론트엔드 개발 부서"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| name | string \| null | ❌ | 변경할 부서명 (최대 100자) |
| description | string \| null | ❌ | 변경할 부서 설명 (최대 255자) |

**Response** `200 OK`
```json
{
  "id": "uuid-string",
  "name": "개발1팀",
  "description": "프론트엔드 개발 부서",
  "created_at": "2026-05-01T10:00:00",
  "updated_at": "2026-05-05T11:00:00"
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 401 Unauthorized | 인증 토큰 없음 또는 만료 |
| 403 Forbidden | admin 역할이 아닌 경우 |
| 404 Not Found | 해당 ID의 부서 없음 |

---

### DELETE /api/v1/departments/{dept_id}

부서 삭제. CASCADE로 해당 부서의 사용자 배정(user_departments)도 함께 삭제됨. **admin 권한 필요**.

**Headers**
```
Authorization: Bearer {access_token}  (role=admin)
```

**Path Parameters**

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| dept_id | string (UUID) | 삭제할 부서 ID |

**Request**
```json
(Body 없음)
```

**Response** `204 No Content`

**Error Codes**

| 코드 | 설명 |
|------|------|
| 401 Unauthorized | 인증 토큰 없음 또는 만료 |
| 403 Forbidden | admin 역할이 아닌 경우 |
| 404 Not Found | 해당 ID의 부서 없음 |

---

### POST /api/v1/users/{user_id}/departments

사용자에 부서를 배정. **admin 권한 필요**.

**Headers**
```
Authorization: Bearer {access_token}  (role=admin)
```

**Path Parameters**

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| user_id | integer | 배정할 사용자 ID |

**Request**
```json
{
  "department_id": "uuid-string",
  "is_primary": true
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| department_id | string (UUID) | ✅ | 배정할 부서 ID |
| is_primary | boolean | ❌ | 주 부서 여부 (기본값: false, 사용자당 최대 1개) |

**Response** `204 No Content`

**Error Codes**

| 코드 | 설명 |
|------|------|
| 401 Unauthorized | 인증 토큰 없음 또는 만료 |
| 403 Forbidden | admin 역할이 아닌 경우 |
| 422 Unprocessable Entity | 이미 주 부서가 존재하는데 `is_primary=true`로 배정 시도 |

---

### DELETE /api/v1/users/{user_id}/departments/{dept_id}

사용자의 부서 배정 해제. **admin 권한 필요**.

**Headers**
```
Authorization: Bearer {access_token}  (role=admin)
```

**Path Parameters**

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| user_id | integer | 사용자 ID |
| dept_id | string (UUID) | 해제할 부서 ID |

**Request**
```json
(Body 없음)
```

**Response** `204 No Content`

**Error Codes**

| 코드 | 설명 |
|------|------|
| 401 Unauthorized | 인증 토큰 없음 또는 만료 |
| 403 Forbidden | admin 역할이 아닌 경우 |

---

## 데이터 모델

### departments 테이블

| 컬럼 | 타입 | 제약 | 설명 |
|-------|------|------|------|
| id | VARCHAR(36) | PK | UUID 문자열 |
| name | VARCHAR(100) | NOT NULL, UNIQUE | 부서명 |
| description | VARCHAR(255) | NULLABLE | 부서 설명 |
| created_at | DATETIME | NOT NULL | 생성 일시 |
| updated_at | DATETIME | NOT NULL | 수정 일시 |

### user_departments 테이블 (사용자-부서 연결)

| 컬럼 | 타입 | 제약 | 설명 |
|-------|------|------|------|
| user_id | INT | PK, FK → users.id | 사용자 ID |
| department_id | VARCHAR(36) | PK, FK → departments.id (CASCADE) | 부서 ID |
| is_primary | TINYINT(1) | DEFAULT 0 | 주 부서 여부 (사용자당 최대 1개) |
| created_at | DATETIME | NOT NULL | 배정 일시 |

**인덱스**: `ix_user_primary` ON (user_id, is_primary)

---

## 비즈니스 규칙

| 규칙 | 설명 |
|------|------|
| 부서명 유니크 | 동일 이름의 부서 생성 불가 (409 Conflict) |
| 주 부서 1개 제한 | 사용자당 `is_primary=true` 부서는 최대 1개 |
| CASCADE 삭제 | 부서 삭제 시 해당 부서의 모든 user_departments 레코드 자동 삭제 |
| 부분 수정 | PATCH는 전달된 필드만 업데이트, 나머지 유지 |

---

## 관련 참조

- **마이그레이션**: `db/migration/V005__create_departments.sql`
- **에이전트 연동**: `agent_definition.department_id` FK로 부서별 에이전트 공유 범위 지정
- **컬렉션 권한**: `collection_permissions.department_id` FK로 부서별 문서 접근 제어
