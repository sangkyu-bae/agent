# auth API

> 이메일+비밀번호 회원가입 → 관리자 승인 흐름, JWT Access+Refresh 토큰, RBAC 역할 기반 접근 제어

## 개요

| 항목 | 내용 |
|------|------|
| Base URL | `/api/v1` |
| Auth | Bearer Token (JWT) — 보호된 엔드포인트에 `Authorization: Bearer {access_token}` 헤더 필요 |

---

## 엔드포인트 목록

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/v1/auth/register` | 회원가입 (가입 후 관리자 승인 대기) |
| POST | `/api/v1/auth/login` | 로그인 (Access + Refresh Token 발급) |
| POST | `/api/v1/auth/refresh` | Access Token 재발급 |
| POST | `/api/v1/auth/logout` | 로그아웃 (Refresh Token 무효화) |
| GET | `/api/v1/auth/me` | 현재 사용자 정보 조회 |
| GET | `/api/v1/admin/users/pending` | 승인 대기 사용자 목록 조회 (admin) |
| POST | `/api/v1/admin/users/{user_id}/approve` | 사용자 승인 (admin) |
| POST | `/api/v1/admin/users/{user_id}/reject` | 사용자 거절 (admin) |

---

## 상세 스펙

### POST /api/v1/auth/register

회원가입 요청. 가입 즉시 `status=pending` 상태로 저장되며, 관리자 승인 후 로그인 가능.

**Request**
```json
{
  "email": "user@example.com",
  "password": "mypassword123"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| email | string (EmailStr) | ✅ | 이메일 형식 검증 |
| password | string | ✅ | 8~128자 |

**Response** `201 Created`
```json
{
  "id": 1,
  "email": "user@example.com",
  "role": "user",
  "status": "pending"
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 409 Conflict | `"Email already registered"` — 이미 가입된 이메일 |
| 422 Unprocessable Entity | 이메일 형식 오류 또는 비밀번호 정책 위반 (`"Password must be at least 8 characters"`) |

---

### POST /api/v1/auth/login

로그인. `status=approved` 계정만 성공.

**Request**
```json
{
  "email": "user@example.com",
  "password": "mypassword123"
}
```

**Response** `200 OK`
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 401 Unauthorized | `"Invalid credentials"` — 이메일/비밀번호 불일치 (사용자 열거 공격 방지를 위해 통일) |
| 401 Unauthorized | `"Account is pending approval"` — 관리자 승인 대기 중 |
| 401 Unauthorized | `"Account has been rejected"` — 관리자에 의해 거절된 계정 |

---

### POST /api/v1/auth/refresh

Refresh Token으로 새 Access Token 발급.

**Request**
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response** `200 OK`
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 401 Unauthorized | `"Invalid token"` — 만료되거나 유효하지 않은 토큰 |
| 401 Unauthorized | `"Token type mismatch"` — Access Token을 Refresh Token 자리에 사용한 경우 |

---

### POST /api/v1/auth/logout

Refresh Token을 DB에서 무효화. 이미 무효화된 토큰이어도 멱등성 보장 (에러 없이 통과).

**Headers**
```
Authorization: Bearer {access_token}
```

**Request**
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response** `204 No Content`

**Error Codes**

| 코드 | 설명 |
|------|------|
| 401 Unauthorized | `"Invalid token"` — Access Token 검증 실패 |

---

### GET /api/v1/auth/me

현재 로그인된 사용자 정보 조회.

**Headers**
```
Authorization: Bearer {access_token}
```

**Response** `200 OK`
```json
{
  "id": 1,
  "email": "user@example.com",
  "role": "user",
  "status": "approved"
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 401 Unauthorized | `"Invalid token"` — 토큰 없음 또는 만료 |

---

### GET /api/v1/admin/users/pending

승인 대기(`status=pending`) 사용자 목록 조회. **admin 권한 필요**.

**Headers**
```
Authorization: Bearer {access_token}  (role=admin)
```

**Response** `200 OK`
```json
[
  {
    "id": 2,
    "email": "newuser@example.com",
    "role": "user",
    "created_at": "2026-04-08T10:00:00Z"
  }
]
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 401 Unauthorized | `"Invalid token"` — 토큰 없음 또는 만료 |
| 403 Forbidden | `"Insufficient permissions"` — admin 역할이 아닌 경우 |

---

### POST /api/v1/admin/users/{user_id}/approve

사용자를 `approved` 상태로 변경. 이미 승인된 경우 멱등성 보장. **admin 권한 필요**.

**Headers**
```
Authorization: Bearer {access_token}  (role=admin)
```

**Path Parameters**

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| user_id | integer | 승인할 사용자 ID |

**Response** `204 No Content`

**Error Codes**

| 코드 | 설명 |
|------|------|
| 401 Unauthorized | `"Invalid token"` |
| 403 Forbidden | `"Insufficient permissions"` |
| 404 Not Found | `"User not found"` |

---

### POST /api/v1/admin/users/{user_id}/reject

사용자를 `rejected` 상태로 변경. **admin 권한 필요**.

**Headers**
```
Authorization: Bearer {access_token}  (role=admin)
```

**Path Parameters**

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| user_id | integer | 거절할 사용자 ID |

**Response** `204 No Content`

**Error Codes**

| 코드 | 설명 |
|------|------|
| 401 Unauthorized | `"Invalid token"` |
| 403 Forbidden | `"Insufficient permissions"` |
| 404 Not Found | `"User not found"` |

---

## 인증 흐름 요약

```
회원가입 → status=pending → 관리자 승인 → status=approved → 로그인 가능
                          ↘ 관리자 거절 → status=rejected → 로그인 불가
```

## UserStatus 정의

| 값 | 설명 |
|----|------|
| `pending` | 가입 신청 완료, 관리자 승인 대기 |
| `approved` | 관리자 승인 완료, 로그인 가능 |
| `rejected` | 관리자에 의해 거절됨 |

## UserRole 정의

| 값 | 설명 |
|----|------|
| `user` | 일반 사용자 |
| `admin` | 관리자 (pending 목록 조회 및 승인/거절 권한) |

## JWT 토큰 구성

| 토큰 | 만료 | 용도 |
|------|------|------|
| Access Token | 15분 (기본값) | API 인증 헤더에 사용 |
| Refresh Token | 7일 (기본값) | Access Token 재발급 시 사용, DB에 SHA-256 해시로 저장 |
