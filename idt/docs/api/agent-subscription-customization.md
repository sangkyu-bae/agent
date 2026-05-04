# agent-subscription-customization API

> 공유 에이전트 구독(북마크) + 포크(전체 복사 커스터마이징) API

## 개요

| 항목 | 내용 |
|------|------|
| Base URL | `/api/v1/agents` |
| Auth | Required (모든 엔드포인트에 `get_current_user` 의존성) |

---

## 엔드포인트 목록

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/v1/agents/{agent_id}/subscribe` | 에이전트 구독 |
| DELETE | `/api/v1/agents/{agent_id}/subscribe` | 구독 해제 |
| PATCH | `/api/v1/agents/{agent_id}/subscribe` | 구독 설정 변경 (pin) |
| POST | `/api/v1/agents/{agent_id}/fork` | 에이전트 포크 (전체 복사) |
| GET | `/api/v1/agents/my` | 내 에이전트 통합 목록 |
| GET | `/api/v1/agents/{agent_id}/forks` | 포크/구독 통계 (원본 소유자) |

---

## 상세 스펙

### POST `/api/v1/agents/{agent_id}/subscribe`

에이전트 구독 생성. 이미 구독 중이면 409 Conflict.

**Request**
```json
(Body 없음 — path param만 사용)
```

**Response (201)**
```json
{
  "subscription_id": "uuid",
  "agent_id": "uuid",
  "agent_name": "원본 에이전트명",
  "is_pinned": false,
  "subscribed_at": "2026-05-04T12:00:00Z"
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 400 | 자신의 에이전트는 구독할 수 없습니다 |
| 404 | 에이전트 없음 또는 접근 불가 |
| 409 | 이미 구독 중입니다 |

---

### DELETE `/api/v1/agents/{agent_id}/subscribe`

구독 해제. 성공 시 204 No Content.

**Request**
```json
(Body 없음 — path param만 사용)
```

**Response (204)**
```json
(No Content)
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 404 | 구독 없음 |

---

### PATCH `/api/v1/agents/{agent_id}/subscribe`

구독 설정 변경 (즐겨찾기 토글).

**Request**
```json
{
  "is_pinned": true
}
```

**Response (200)**
```json
{
  "subscription_id": "uuid",
  "agent_id": "uuid",
  "is_pinned": true,
  "subscribed_at": "2026-05-04T12:00:00Z"
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 404 | 구독 없음 |

---

### POST `/api/v1/agents/{agent_id}/fork`

에이전트 포크 (전체 복사). 원본의 `agent_definition` + `agent_tool`을 모두 복사하여 새 에이전트 생성.

**Request**
```json
{
  "name": "내 커스텀 에이전트"
}
```
- `name`: 선택. 생략 시 `"{원본이름} (사본)"` 자동 생성.

**Response (201)**
```json
{
  "agent_id": "새-uuid",
  "name": "내 커스텀 에이전트",
  "forked_from": "원본-uuid",
  "forked_at": "2026-05-04T12:00:00Z",
  "system_prompt": "복사된 프롬프트",
  "workers": [
    {
      "name": "worker-name",
      "tool_type": "rag_search",
      "config": {}
    }
  ],
  "visibility": "private",
  "temperature": 0.70,
  "llm_model_id": "model-uuid"
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 400 | 자신의 에이전트는 포크할 수 없습니다 / 삭제된 에이전트는 포크할 수 없습니다 |
| 403 | 접근 권한 없음 (visibility 규칙 위반) |
| 404 | 원본 에이전트 없음 |

---

### GET `/api/v1/agents/my`

내 에이전트 통합 목록. 소유(owned) + 구독(subscribed) + 포크(forked) 구분.

**Query Params**

| Param | Type | Default | 설명 |
|-------|------|---------|------|
| `filter` | string | `all` | `all` \| `owned` \| `subscribed` \| `forked` |
| `search` | string | null | 이름 검색 |
| `page` | int | 1 | 페이지 번호 (>= 1) |
| `size` | int | 20 | 페이지 크기 (1~100) |

**Request**
```json
(Query params만 사용)
```

**Response (200)**
```json
{
  "agents": [
    {
      "agent_id": "uuid",
      "name": "에이전트명",
      "description": "설명",
      "source_type": "owned",
      "visibility": "private",
      "temperature": 0.70,
      "owner_user_id": "user-id",
      "forked_from": null,
      "is_pinned": false,
      "created_at": "2026-05-04T12:00:00Z"
    },
    {
      "agent_id": "uuid",
      "name": "구독한 에이전트",
      "description": "설명",
      "source_type": "subscribed",
      "visibility": "public",
      "temperature": 0.50,
      "owner_user_id": "other-user",
      "forked_from": null,
      "is_pinned": true,
      "created_at": "2026-05-01T10:00:00Z"
    },
    {
      "agent_id": "forked-uuid",
      "name": "내 커스텀 버전",
      "description": "포크한 에이전트",
      "source_type": "forked",
      "visibility": "private",
      "temperature": 0.90,
      "owner_user_id": "my-id",
      "forked_from": "original-uuid",
      "is_pinned": false,
      "created_at": "2026-05-03T15:00:00Z"
    }
  ],
  "total": 3,
  "page": 1,
  "size": 20
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 400 | 잘못된 filter 값 |

---

### GET `/api/v1/agents/{agent_id}/forks`

특정 에이전트의 포크/구독 통계 (원본 소유자 전용).

**Request**
```json
(Path param만 사용)
```

**Response (200)**
```json
{
  "agent_id": "original-uuid",
  "fork_count": 5,
  "subscriber_count": 12
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 403 | 원본 소유자가 아닌 경우 |
| 404 | 에이전트 없음 |
