# collection-permission-management API

> 벡터 DB 컬렉션에 대한 권한 기반 접근 제어 (개인/부서/공개 scope별 읽기·쓰기·삭제 관리)

## 개요

| 항목 | 내용 |
|------|------|
| Base URL | `/api/v1/collections` |
| Auth | Bearer Token (필수) |

---

## 엔드포인트 목록

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/v1/collections` | 접근 가능한 컬렉션 목록 조회 (권한 필터 적용) |
| GET | `/api/v1/collections/{name}` | 컬렉션 상세 조회 (read 권한 검사) |
| POST | `/api/v1/collections` | 컬렉션 생성 + 권한 레코드 동시 생성 |
| PATCH | `/api/v1/collections/{name}` | 컬렉션 이름 변경 (소유자/Admin만 가능) |
| DELETE | `/api/v1/collections/{name}` | 컬렉션 삭제 (소유자/Admin만 가능) |
| PATCH | `/api/v1/collections/{name}/permission` | 컬렉션 scope 변경 (소유자/Admin만 가능) |

---

## 상세 스펙

### GET /api/v1/collections

접근 가능한 컬렉션 목록을 조회한다. 사용자 역할(Admin/일반)과 scope(PERSONAL/DEPARTMENT/PUBLIC)에 따라 자동 필터링된다.

**Request**

```
Authorization: Bearer <token>
```

**Response 200**

```json
{
  "collections": [
    {
      "name": "my-docs",
      "vectors_count": 150,
      "points_count": 150,
      "status": "green",
      "scope": "PERSONAL",
      "owner_id": 1
    },
    {
      "name": "team-docs",
      "vectors_count": 320,
      "points_count": 320,
      "status": "green",
      "scope": "DEPARTMENT",
      "owner_id": 5
    }
  ],
  "total": 2
}
```

**필터 규칙**

| 역할 | 필터 |
|------|------|
| Admin | 전체 컬렉션 접근 |
| 일반 사용자 | PUBLIC + 본인 PERSONAL + 소속 부서 DEPARTMENT |

---

### GET /api/v1/collections/{name}

컬렉션 상세 정보를 조회한다.

**Request**

```
Authorization: Bearer <token>
```

**Response 200**

```json
{
  "name": "my-docs",
  "vectors_count": 150,
  "points_count": 150,
  "status": "green",
  "scope": "PERSONAL",
  "owner_id": 1
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 403 | 해당 컬렉션에 대한 읽기 권한 없음 |
| 404 | 컬렉션이 존재하지 않음 |

---

### POST /api/v1/collections

컬렉션을 생성하고 권한 레코드를 동시에 생성한다.

**Request**

```json
{
  "name": "team-docs",
  "vector_size": 1536,
  "embedding_model": null,
  "distance": "Cosine",
  "scope": "DEPARTMENT",
  "department_id": "dept-uuid"
}
```

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|------|------|------|--------|------|
| name | string | O | - | 컬렉션 이름 |
| vector_size | integer | X | null | 벡터 차원 (>= 1) |
| embedding_model | string | X | null | 임베딩 모델명 |
| distance | string | X | "Cosine" | 거리 함수 |
| scope | string | X | "PERSONAL" | "PERSONAL" / "DEPARTMENT" / "PUBLIC" |
| department_id | string | X | null | scope=DEPARTMENT일 때 필수 |

**Response 200**

```json
{
  "name": "team-docs",
  "message": "Collection created successfully"
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 409 | 동일 이름의 컬렉션이 이미 존재 |
| 422 | scope=DEPARTMENT인데 department_id가 누락되거나, 소속되지 않은 부서 지정 |

---

### PATCH /api/v1/collections/{name}

컬렉션 이름을 변경한다. 소유자 또는 Admin만 가능하며, 권한 레코드의 collection_name도 함께 갱신된다.

**Request**

```json
{
  "new_name": "renamed-docs"
}
```

**Response 200**

```json
{
  "name": "renamed-docs",
  "message": "Collection renamed successfully"
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 403 | 이름 변경 권한 없음 (소유자/Admin이 아님) |
| 404 | 컬렉션이 존재하지 않음 |

---

### DELETE /api/v1/collections/{name}

컬렉션을 삭제한다. 소유자 또는 Admin만 가능하며, 권한 레코드도 함께 삭제된다.

**Request**

```
Authorization: Bearer <token>
```

**Response 200**

```json
{
  "name": "my-docs",
  "message": "Collection deleted successfully"
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 403 | 삭제 권한 없음 (소유자/Admin이 아님) |
| 404 | 컬렉션이 존재하지 않음 |

---

### PATCH /api/v1/collections/{name}/permission

컬렉션의 scope를 변경한다. 소유자 또는 Admin만 가능하다.

**Request**

```json
{
  "scope": "DEPARTMENT",
  "department_id": "dept-uuid"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| scope | string | O | "PERSONAL" / "DEPARTMENT" / "PUBLIC" |
| department_id | string | X | scope=DEPARTMENT일 때 필수 |

**Response 200**

```json
{
  "name": "my-docs",
  "message": "Collection scope updated successfully"
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 403 | scope 변경 권한 없음 (소유자/Admin이 아님) |
| 404 | 해당 컬렉션의 권한 레코드가 존재하지 않음 |
| 422 | scope=DEPARTMENT인데 department_id가 누락되거나, 소속되지 않은 부서 지정 |

---

## 권한 규칙 요약

### Scope별 접근 제어

| Scope | Read | Write | Delete | Change Scope |
|-------|------|-------|--------|-------------|
| PERSONAL | 소유자, Admin | 소유자, Admin | 소유자, Admin | 소유자, Admin |
| DEPARTMENT | 소속 부서원, Admin | 소속 부서원, Admin | 소유자, Admin | 소유자, Admin |
| PUBLIC | 전체 | Admin만 | 소유자, Admin | 소유자, Admin |

### Edge Cases

| 케이스 | 동작 |
|--------|------|
| 권한 레코드 미등록 컬렉션 (legacy) | read/write 허용 (기존 동작 유지) |
| Admin의 DEPARTMENT scope 설정 | 어떤 부서든 지정 가능 |
| 동일 컬렉션 다중 부서 공유 | 미지원 (1 컬렉션 = 1 department_id) |
