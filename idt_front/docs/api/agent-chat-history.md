# agent-chat-history API

> 에이전트별 채팅 기록 분리 조회 API (에이전트 목록, 세션 목록, 메시지 조회)

## 개요

| 항목 | 내용 |
|------|------|
| Base URL | `/api/v1/conversations` |
| Auth | `Authorization: Bearer {token}` |

---

## 엔드포인트 목록

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/v1/conversations/agents` | 대화 기록이 있는 에이전트 목록 조회 |
| GET | `/api/v1/conversations/agents/{agent_id}/sessions` | 에이전트별 세션 목록 조회 |
| GET | `/api/v1/conversations/agents/{agent_id}/sessions/{session_id}/messages` | 에이전트 세션의 메시지 조회 |

---

## 상세 스펙

### GET /api/v1/conversations/agents

대화 기록이 있는 에이전트 목록을 최신 채팅 순으로 반환한다.

**Request**

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| user_id | query | string | Y | 사용자 ID |

```json
GET /api/v1/conversations/agents?user_id=user123
Authorization: Bearer {token}
```

**Response (200)**

```json
{
  "user_id": "user123",
  "agents": [
    {
      "agent_id": "super",
      "agent_name": "일반 채팅",
      "session_count": 5,
      "last_chat_at": "2026-04-30T10:30:00"
    },
    {
      "agent_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "agent_name": "금융 분석 에이전트",
      "session_count": 3,
      "last_chat_at": "2026-04-29T15:00:00"
    }
  ]
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 422 | user_id 미전달 (FastAPI Query 검증) |

---

### GET /api/v1/conversations/agents/{agent_id}/sessions

특정 에이전트의 세션 목록을 최신순으로 반환한다.

**Request**

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| agent_id | path | string | Y | 에이전트 ID (`"super"` 또는 UUID) |
| user_id | query | string | Y | 사용자 ID |

```json
GET /api/v1/conversations/agents/super/sessions?user_id=user123
Authorization: Bearer {token}
```

**Response (200)**

```json
{
  "user_id": "user123",
  "agent_id": "super",
  "sessions": [
    {
      "session_id": "sess-abc",
      "message_count": 8,
      "last_message": "부동산 취득세 면제 조건이 뭔가요?",
      "last_message_at": "2026-04-30T10:30:00"
    }
  ]
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 422 | user_id 미전달 또는 agent_id 빈 문자열 (AgentId VO 검증) |

---

### GET /api/v1/conversations/agents/{agent_id}/sessions/{session_id}/messages

에이전트 세션의 메시지 목록을 turn_index 오름차순으로 반환한다.

**Request**

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| agent_id | path | string | Y | 에이전트 ID |
| session_id | path | string | Y | 세션 ID |
| user_id | query | string | Y | 사용자 ID |

```json
GET /api/v1/conversations/agents/super/sessions/sess-abc/messages?user_id=user123
Authorization: Bearer {token}
```

**Response (200)**

```json
{
  "user_id": "user123",
  "agent_id": "super",
  "session_id": "sess-abc",
  "messages": [
    {
      "id": 1,
      "role": "user",
      "content": "안녕하세요",
      "turn_index": 1,
      "created_at": "2026-04-30T09:00:00"
    },
    {
      "id": 2,
      "role": "assistant",
      "content": "안녕하세요! 무엇을 도와드릴까요?",
      "turn_index": 2,
      "created_at": "2026-04-30T09:00:05"
    }
  ]
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 422 | user_id 미전달 또는 agent_id/session_id 빈 문자열 |
