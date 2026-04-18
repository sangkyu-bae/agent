# CHAT-HIST-001: 대화 히스토리 조회 API

> 상태: Plan
> 연관 Task: CONV-001 (Multi-Turn 대화 메모리)
> 작성일: 2026-04-17
> 우선순위: High

---

## 1. 배경 및 목적 (Background)

현재 `POST /api/v1/chat` 및 `POST /api/v1/conversation/chat` 으로 발생한 대화 메시지는
`conversation_message` 테이블에 **user_id + session_id** 기준으로 저장되고 있다.

그러나 UI에서 이를 조회할 API가 없어:
- 사용자가 이전 대화 세션 목록을 확인할 수 없음
- 특정 세션의 대화 내용을 다시 열람할 수 없음
- 페이지 새로고침 시 채팅 기록이 사라짐

이 기능은 UI의 채팅 히스토리 사이드바 및 대화 복원에 필수적이다.

---

## 2. 목표 (Goals)

1. 특정 사용자의 **세션 목록** 반환 API 구현
2. 특정 세션의 **전체 메시지 목록** 반환 API 구현
3. 기존 `ConversationMessageRepository` 확장 (신규 조회 메서드 추가)
4. TDD 방식으로 구현 (테스트 먼저)
5. LOG-001 로깅 규칙 준수

---

## 3. 범위 외 (Non-Goals)

- 대화 내용 수정/삭제 API (별도 기능)
- 세션 제목 자동 생성 (별도 기능)
- 페이지네이션 (v1은 세션 단위 전체 반환, 추후 추가)
- 실시간 스트리밍 (기존 채팅 API 담당)

---

## 4. API 설계 (Endpoint Design)

### 4-1. 세션 목록 조회

```
GET /api/v1/conversations/sessions
Query: user_id (str, required)
```

**Response**:
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

- `session_id` 기준으로 그룹핑하여 반환
- `last_message_at` 내림차순 정렬 (최신 세션 먼저)
- `last_message` 는 마지막 `user` role 메시지 내용 (100자 truncate)

### 4-2. 세션 메시지 조회

```
GET /api/v1/conversations/sessions/{session_id}/messages
Query: user_id (str, required)
```

**Response**:
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
    },
    {
      "id": 2,
      "role": "assistant",
      "content": "안녕하세요! 무엇을 도와드릴까요?",
      "turn_index": 2,
      "created_at": "2026-04-17T09:00:01"
    }
  ]
}
```

- `turn_index` 오름차순 정렬
- 전체 메시지 반환 (요약 여부와 무관하게 원문 메시지 모두 반환)

---

## 5. 아키텍처 설계 (Architecture)

### 레이어별 역할

```
interfaces/ (router)
  └─ GET /api/v1/conversations/sessions
  └─ GET /api/v1/conversations/sessions/{session_id}/messages

application/ (use case)
  └─ ConversationHistoryUseCase
       ├─ get_sessions(user_id) → SessionListResponse
       └─ get_messages(user_id, session_id) → MessageListResponse

infrastructure/ (repository 확장)
  └─ SQLAlchemyConversationMessageRepository
       ├─ find_sessions_by_user(user_id) → List[SessionSummary]  ← 신규
       └─ find_by_session() ← 기존 재사용

domain/ (schemas 추가)
  └─ SessionSummary, SessionListResponse, MessageListResponse
```

### 신규 Repository 메서드

```python
async def find_sessions_by_user(self, user_id: UserId) -> List[SessionSummary]:
    """user_id 기준으로 고유 session_id 목록과 메타데이터를 반환."""
    # GROUP BY session_id, MAX(created_at), COUNT(*), 마지막 user 메시지 내용
```

---

## 6. 파일 변경 목록 (File Changes)

### 신규 파일
| 파일 | 설명 |
|------|------|
| `src/domain/conversation/history_schemas.py` | SessionSummary, SessionListResponse, MessageListResponse |
| `src/application/conversation/history_use_case.py` | ConversationHistoryUseCase |
| `src/api/routes/conversation_history_router.py` | GET /sessions, GET /sessions/{id}/messages |
| `tests/domain/conversation/test_history_schemas.py` | 도메인 스키마 테스트 |
| `tests/application/conversation/test_history_use_case.py` | UseCase 테스트 (AsyncMock) |
| `tests/api/test_conversation_history_router.py` | API 라우터 테스트 |

### 수정 파일
| 파일 | 변경 내용 |
|------|----------|
| `src/application/repositories/conversation_repository.py` | `find_sessions_by_user` 추상 메서드 추가 |
| `src/infrastructure/persistence/repositories/conversation_repository.py` | `find_sessions_by_user` 구현 추가 |
| `src/main.py` | `conversation_history_router` 등록 |

---

## 7. TDD 계획 (Test Plan)

| 파일 | 테스트 케이스 | 설명 |
|------|-------------|------|
| `test_history_schemas.py` | 4 | SessionSummary 생성, 필드 검증, truncate 동작 |
| `test_history_use_case.py` | 8 | 세션 목록 반환, 빈 결과, 메시지 조회, user_id 불일치 |
| `test_conversation_history_router.py` | 6 | 200/400/404 응답 코드 및 응답 스키마 검증 |

---

## 8. 완료 기준 (Definition of Done)

- [ ] `GET /api/v1/conversations/sessions` 정상 동작
- [ ] `GET /api/v1/conversations/sessions/{session_id}/messages` 정상 동작
- [ ] 전체 테스트 18개 통과
- [ ] `/verify-logging` 통과
- [ ] `/verify-architecture` 통과
- [ ] `/verify-tdd` 통과
- [ ] 프론트엔드에서 세션 목록 사이드바 연동 가능 (API 계약 문서화)

---

## 9. 의존성 (Dependencies)

- **CONV-001** (Multi-Turn 대화 메모리): conversation_message 테이블 구조 재사용
- **MYSQL-001**: SQLAlchemy AsyncSession 패턴 재사용
- **LOG-001**: 로깅 규칙 준수
- **AUTH-001**: (선택) user_id 인증 토큰 검증 — v1은 query param으로 받되, 추후 JWT 연동
