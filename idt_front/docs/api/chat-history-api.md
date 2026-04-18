# chat-history-api API

> 저장된 멀티턴 대화 기록을 UI에서 조회할 수 있도록 세션 목록과 세션 내 메시지를 제공하는 REST API.

## 개요

| 항목 | 내용 |
|------|------|
| Base URL | `/api/v1/conversations` |
| Auth | 미적용 (user_id 쿼리 파라미터로 식별) |
| Task ID | CHAT-HIST-001 |
| Content-Type | `application/json` |

---

## 엔드포인트 목록

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/v1/conversations/sessions` | 특정 사용자의 대화 세션 목록 조회 (최근 메시지 시각 내림차순) |
| GET | `/api/v1/conversations/sessions/{session_id}/messages` | 세션 내 전체 메시지 조회 (turn_index 오름차순) |

---

## 상세 스펙

### GET /api/v1/conversations/sessions

`user_id` 기준으로 저장된 모든 세션의 요약을 반환한다. 각 세션에 대해 메시지 수, 마지막 user 메시지(100자 truncate), 마지막 메시지 시각을 제공한다.

**Query Parameters**

| 이름 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `user_id` | string | ✅ | 조회 대상 사용자 ID |

**Request**

```
GET /api/v1/conversations/sessions?user_id=user-123 HTTP/1.1
Host: localhost:8000
```

**Response (200 OK)**

```json
{
  "user_id": "user-123",
  "sessions": [
    {
      "session_id": "session-abc",
      "message_count": 12,
      "last_message": "금융 정책 문서에서 2025년 개정 내용 알려줘",
      "last_message_at": "2026-04-17T10:23:45.000Z"
    },
    {
      "session_id": "session-def",
      "message_count": 4,
      "last_message": "이전 답변 요약해줘",
      "last_message_at": "2026-04-16T18:02:11.000Z"
    }
  ]
}
```

**동작 규칙**

- 세션이 없는 경우에도 `200 OK` 와 함께 `sessions: []` 을 반환한다 (404 미사용).
- `last_message` 는 해당 세션의 마지막 **user** 메시지이며 100자 초과 시 truncate 된다.
- 정렬은 `last_message_at` 내림차순이다.

**Error Codes**

| 코드 | 설명 |
|------|------|
| 422 | `user_id` 쿼리 파라미터 누락 (FastAPI 자동 검증) |
| 500 | UseCase/Repository 내부 예외 (서버 로그에 스택트레이스 기록) |

---

### GET /api/v1/conversations/sessions/{session_id}/messages

특정 세션의 전체 메시지를 `turn_index` 오름차순으로 반환한다. UI의 대화 히스토리 재구성에 사용된다.

**Path Parameters**

| 이름 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `session_id` | string | ✅ | 조회 대상 세션 ID |

**Query Parameters**

| 이름 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `user_id` | string | ✅ | 세션 소유자 ID |

**Request**

```
GET /api/v1/conversations/sessions/session-abc/messages?user_id=user-123 HTTP/1.1
Host: localhost:8000
```

**Response (200 OK)**

```json
{
  "user_id": "user-123",
  "session_id": "session-abc",
  "messages": [
    {
      "id": 1001,
      "role": "user",
      "content": "금융 정책 문서에서 2025년 개정 내용 알려줘",
      "turn_index": 1,
      "created_at": "2026-04-17T10:20:10.000Z"
    },
    {
      "id": 1002,
      "role": "assistant",
      "content": "2025년 개정된 주요 정책은 다음과 같습니다...",
      "turn_index": 1,
      "created_at": "2026-04-17T10:20:13.000Z"
    },
    {
      "id": 1003,
      "role": "user",
      "content": "좀 더 자세히 설명해줘",
      "turn_index": 2,
      "created_at": "2026-04-17T10:23:30.000Z"
    }
  ]
}
```

**동작 규칙**

- 존재하지 않는 `session_id` 또는 `user_id` 의 경우에도 `200 OK` 와 함께 `messages: []` 을 반환한다.
- `role` 은 `"user"` 또는 `"assistant"` 문자열이다.
- 정렬은 `turn_index` 오름차순 → 동일 turn 내에서는 `created_at` 오름차순이다.

**Error Codes**

| 코드 | 설명 |
|------|------|
| 422 | `user_id` 쿼리 파라미터 누락 |
| 500 | UseCase/Repository 내부 예외 (서버 로그에 스택트레이스 기록) |

---

## 응답 스키마 레퍼런스

### SessionSummary

| 필드 | 타입 | 설명 |
|------|------|------|
| `session_id` | string | 세션 식별자 |
| `message_count` | integer | 해당 세션의 총 메시지 수 |
| `last_message` | string | 마지막 user 메시지 (최대 100자) |
| `last_message_at` | datetime (ISO 8601) | 마지막 메시지 생성 시각 |

### MessageItem

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | integer | 메시지 PK |
| `role` | string | `"user"` \| `"assistant"` |
| `content` | string | 메시지 본문 |
| `turn_index` | integer | 대화 턴 순서 (1부터) |
| `created_at` | datetime (ISO 8601) | 메시지 생성 시각 |

---

## 관련 문서

- Plan: `docs/01-plan/features/chat-history-api.plan.md`
- Design: `docs/02-design/features/chat-history-api.design.md`
- Task: `src/claude/task/task-chat-history-api.md`
- 연관 API: CHAT-001 (`POST /api/v1/chat` — 대화 생성)
