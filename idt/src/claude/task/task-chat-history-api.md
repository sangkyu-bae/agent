# CHAT-HIST-001: 대화 히스토리 조회 API

> 상태: Plan
> 의존성: CONV-001 (Multi-Turn 대화), MYSQL-001 (DB Repository), LOG-001 (로깅)

---

## 개요

user_id + session_id 기준으로 저장된 대화 메시지를 UI에 제공하는 조회 전용 API.
세션 목록 조회와 특정 세션의 메시지 전체 조회 두 가지 엔드포인트를 제공한다.

---

## 엔드포인트

### GET /api/v1/conversations/sessions

사용자의 전체 세션 목록을 최신순으로 반환한다.

- Query: `user_id` (str, required)
- Response: `SessionListResponse`

```json
{
  "user_id": "user123",
  "sessions": [
    {
      "session_id": "sess-abc",
      "message_count": 8,
      "last_message": "부동산 취득세 면제 조건이 뭔가요?",
      "last_message_at": "2026-04-17T10:30:00"
    }
  ]
}
```

- `last_message_at` 내림차순 정렬
- `last_message`: 마지막 `user` role 메시지 (100자 truncate)

---

### GET /api/v1/conversations/sessions/{session_id}/messages

특정 세션의 전체 메시지를 turn_index 오름차순으로 반환한다.

- Query: `user_id` (str, required)
- Response: `MessageListResponse`

```json
{
  "user_id": "user123",
  "session_id": "sess-abc",
  "messages": [
    {
      "id": 1,
      "role": "user",
      "content": "안녕하세요",
      "turn_index": 1,
      "created_at": "2026-04-17T09:00:00"
    }
  ]
}
```

---

## 아키텍처

### Domain Layer
- `src/domain/conversation/history_schemas.py`
  - `SessionSummary`: session_id, message_count, last_message, last_message_at
  - `SessionListResponse`: user_id, sessions: List[SessionSummary]
  - `MessageItem`: id, role, content, turn_index, created_at
  - `MessageListResponse`: user_id, session_id, messages: List[MessageItem]

### Application Layer
- `src/application/conversation/history_use_case.py`
  - `ConversationHistoryUseCase`
    - `get_sessions(user_id: str, request_id: str) -> SessionListResponse`
    - `get_messages(user_id: str, session_id: str, request_id: str) -> MessageListResponse`

### Infrastructure Layer
- `src/application/repositories/conversation_repository.py` (추상 인터페이스 확장)
  - `find_sessions_by_user(user_id: UserId) -> List[SessionSummary]` ← 신규 추상 메서드
- `src/infrastructure/persistence/repositories/conversation_repository.py` (구현 추가)
  - GROUP BY session_id, MAX(created_at), COUNT(*), 마지막 user 메시지 쿼리

### API Layer
- `src/api/routes/conversation_history_router.py`
  - `GET /api/v1/conversations/sessions`
  - `GET /api/v1/conversations/sessions/{session_id}/messages`

---

## 구현 순서 (TDD)

1. `test_history_schemas.py` 작성 → 실패 확인
2. `history_schemas.py` 구현 → 통과
3. `test_history_use_case.py` 작성 → 실패 확인
4. `history_use_case.py` 구현 → 통과
5. `find_sessions_by_user` 추상 메서드 추가 → 구현체 구현
6. `test_conversation_history_router.py` 작성 → 실패 확인
7. `conversation_history_router.py` 구현 → 통과
8. `src/main.py`에 라우터 등록

---

## 테스트 목록

| 파일 | 케이스 수 |
|------|----------|
| `tests/domain/conversation/test_history_schemas.py` | 4 |
| `tests/application/conversation/test_history_use_case.py` | 8 |
| `tests/api/test_conversation_history_router.py` | 6 |
| **합계** | **18** |

### 주요 테스트 케이스

**UseCase**
- 세션 목록 정상 반환 (last_message_at 내림차순)
- user_id에 세션 없을 때 빈 리스트 반환
- 메시지 목록 정상 반환 (turn_index 오름차순)
- 다른 user_id의 session_id 조회 시 빈 결과

**Router**
- `user_id` 없을 때 400 반환
- `session_id` 존재하지 않을 때 빈 messages 배열 반환 (404 아님)

---

## 로깅 (LOG-001 준수)

```python
class ConversationHistoryUseCase:
    def __init__(self, repo: ConversationMessageRepository, logger: LoggerInterface):
        self._repo = repo
        self._logger = logger

    async def get_sessions(self, user_id: str, request_id: str) -> SessionListResponse:
        self._logger.info("get_sessions started", request_id=request_id, user_id=user_id)
        try:
            sessions = await self._repo.find_sessions_by_user(UserId(user_id))
            self._logger.info("get_sessions completed", request_id=request_id, count=len(sessions))
            return SessionListResponse(user_id=user_id, sessions=sessions)
        except Exception as e:
            self._logger.error("get_sessions failed", exception=e, request_id=request_id)
            raise
```

---

## DB 의존성

기존 `conversation_message` 테이블 재사용:
- `id, user_id, session_id, role, content, turn_index, created_at`

신규 쿼리 패턴:
```sql
-- 세션 목록 (GROUP BY)
SELECT session_id,
       COUNT(*) AS message_count,
       MAX(created_at) AS last_message_at
FROM conversation_message
WHERE user_id = :user_id
GROUP BY session_id
ORDER BY last_message_at DESC;
```
