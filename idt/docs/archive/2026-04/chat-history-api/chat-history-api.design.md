# CHAT-HIST-001: 대화 히스토리 조회 API — Design

> 상태: Design
> Plan 참조: docs/01-plan/features/chat-history-api.plan.md
> 작성일: 2026-04-17

---

## 1. 설계 목표

Plan에서 정의한 두 엔드포인트를 기존 DDD 레이어 구조에 맞게 설계한다.
- 기존 `ConversationMessageRepository` 를 최소 변경(추상 메서드 1개 추가)으로 확장
- 신규 도메인 스키마(`history_schemas.py`) 추가 — 기존 `schemas.py` 수정 없음
- TDD 순서(schema → use_case → router) 준수

---

## 2. 레이어별 세부 설계

### 2-1. Domain Layer

**파일**: `src/domain/conversation/history_schemas.py` (신규)

```python
@dataclass(frozen=True)
class SessionSummary:
    session_id: str
    message_count: int
    last_message: str          # 100자 truncate
    last_message_at: datetime

@dataclass(frozen=True)
class SessionListResponse:
    user_id: str
    sessions: List[SessionSummary]

@dataclass(frozen=True)
class MessageItem:
    id: int
    role: str                  # "user" | "assistant"
    content: str
    turn_index: int
    created_at: datetime

@dataclass(frozen=True)
class MessageListResponse:
    user_id: str
    session_id: str
    messages: List[MessageItem]
```

**설계 결정**:
- 도메인 dataclass는 `frozen=True` — 기존 패턴과 동일
- `last_message` truncate 규칙은 도메인 메서드로 캡슐화 (`SessionSummary.from_raw(content, ...)`)
- `MessageItem.role` 은 문자열 — API 응답 직렬화 편의를 위해 enum 미사용

---

### 2-2. Application Layer

**파일**: `src/application/conversation/history_use_case.py` (신규)

```python
class ConversationHistoryUseCase:
    def __init__(
        self,
        repo: ConversationMessageRepository,
        logger: LoggerInterface,
    ) -> None: ...

    async def get_sessions(
        self, user_id: str, request_id: str
    ) -> SessionListResponse: ...

    async def get_messages(
        self, user_id: str, session_id: str, request_id: str
    ) -> MessageListResponse: ...
```

**의존성 주입 규칙**:
- `ConversationMessageRepository` (추상) 주입 — infra 직접 참조 금지
- `LoggerInterface` 주입 — LOG-001 준수

**에러 정책**:
- `user_id` 존재하지 않으면 → 빈 SessionListResponse 반환 (예외 없음)
- `session_id` 존재하지 않으면 → 빈 MessageListResponse 반환 (예외 없음)
- 예외는 `logger.error(exception=e)` 후 `raise`

---

### 2-3. Infrastructure Layer

**수정 파일**: `src/application/repositories/conversation_repository.py`

```python
@abstractmethod
async def find_sessions_by_user(
    self, user_id: UserId
) -> List[SessionSummary]:
    """user_id 기준 세션 목록을 last_message_at 내림차순으로 반환."""
    pass
```

**수정 파일**: `src/infrastructure/persistence/repositories/conversation_repository.py`

```python
async def find_sessions_by_user(
    self, user_id: UserId
) -> List[SessionSummary]:
    # 1단계: GROUP BY session_id → message_count, last_message_at
    subq = (
        select(
            ConversationMessageModel.session_id,
            func.count().label("message_count"),
            func.max(ConversationMessageModel.created_at).label("last_message_at"),
        )
        .where(ConversationMessageModel.user_id == user_id.value)
        .group_by(ConversationMessageModel.session_id)
        .subquery()
    )

    # 2단계: 각 세션의 마지막 user 메시지 서브쿼리 (correlated)
    # → 별도 SELECT + Python-side 매핑으로 단순화
    # (MySQL 서브쿼리 복잡도 회피)
```

**쿼리 전략**:
- `last_message` (마지막 user 메시지) 조회는 **두 번의 쿼리**로 분리
  1. GROUP BY 집계 쿼리
  2. 각 session_id 별 최신 user 메시지 IN 쿼리
- 이유: SQLAlchemy async에서 correlated subquery 복잡성 회피, 코드 가독성 우선

`find_by_session` 기존 메서드를 `get_messages`에서 **그대로 재사용**한다.

---

### 2-4. API Layer

**파일**: `src/api/routes/conversation_history_router.py` (신규)

```python
router = APIRouter(prefix="/api/v1/conversations", tags=["conversation-history"])

@router.get("/sessions", response_model=SessionListAPIResponse)
async def get_sessions(
    user_id: str = Query(..., description="사용자 ID"),
    use_case: ConversationHistoryUseCase = Depends(get_history_use_case),
) -> SessionListAPIResponse: ...

@router.get(
    "/sessions/{session_id}/messages",
    response_model=MessageListAPIResponse,
)
async def get_messages(
    session_id: str,
    user_id: str = Query(..., description="사용자 ID"),
    use_case: ConversationHistoryUseCase = Depends(get_history_use_case),
) -> MessageListAPIResponse: ...
```

**Pydantic 응답 스키마** (router 파일 내 정의):

```python
class SessionSummaryAPI(BaseModel):
    session_id: str
    message_count: int
    last_message: str
    last_message_at: datetime

class SessionListAPIResponse(BaseModel):
    user_id: str
    sessions: List[SessionSummaryAPI]

class MessageItemAPI(BaseModel):
    id: int
    role: str
    content: str
    turn_index: int
    created_at: datetime

class MessageListAPIResponse(BaseModel):
    user_id: str
    session_id: str
    messages: List[MessageItemAPI]
```

**에러 응답**:
- `user_id` 미전달 → FastAPI 자동 422 반환
- 세션/메시지 없음 → 200 + 빈 배열 (404 미사용 — Plan 결정 유지)

---

## 3. 의존성 주입 (DI) 설계

`conversation_history_router.py` 에 placeholder 함수 정의:

```python
def get_history_use_case() -> ConversationHistoryUseCase:
    raise NotImplementedError("ConversationHistoryUseCase not initialized")
```

`src/main.py` 에서 오버라이드:

```python
from src.api.routes.conversation_history_router import (
    get_history_use_case,
    router as conversation_history_router,
)

async def lifespan(app: FastAPI):
    session = create_async_session()
    repo = SQLAlchemyConversationMessageRepository(session)
    logger = StructuredLogger("conversation_history")
    use_case = ConversationHistoryUseCase(repo, logger)

    app.dependency_overrides[get_history_use_case] = lambda: use_case
    yield

app.include_router(conversation_history_router)
```

기존 `conversation_router.py` DI 패턴과 동일하게 적용.

---

## 4. 파일 변경 목록

### 신규 파일 (4개)
| 파일 | 레이어 | 역할 |
|------|--------|------|
| `src/domain/conversation/history_schemas.py` | domain | SessionSummary, SessionListResponse, MessageItem, MessageListResponse |
| `src/application/conversation/history_use_case.py` | application | ConversationHistoryUseCase |
| `src/api/routes/conversation_history_router.py` | interfaces | GET /sessions, GET /sessions/{id}/messages |
| `tests/application/conversation/test_history_use_case.py` | test | UseCase 8개 케이스 |

### 수정 파일 (3개)
| 파일 | 변경 내용 |
|------|----------|
| `src/application/repositories/conversation_repository.py` | `find_sessions_by_user` 추상 메서드 추가 |
| `src/infrastructure/persistence/repositories/conversation_repository.py` | `find_sessions_by_user` 구현 |
| `src/main.py` | `conversation_history_router` 등록, DI 오버라이드 |

### 테스트 파일 (3개)
| 파일 | 케이스 수 |
|------|----------|
| `tests/domain/conversation/test_history_schemas.py` | 4 |
| `tests/application/conversation/test_history_use_case.py` | 8 |
| `tests/api/test_conversation_history_router.py` | 6 |

---

## 5. TDD 구현 순서

```
1. tests/domain/conversation/test_history_schemas.py 작성
   ↓ pytest 실패 확인
2. src/domain/conversation/history_schemas.py 구현
   ↓ pytest 통과
3. tests/application/conversation/test_history_use_case.py 작성
   ↓ pytest 실패 확인
4. src/application/repositories/conversation_repository.py 추상 메서드 추가
5. src/application/conversation/history_use_case.py 구현
6. src/infrastructure/persistence/repositories/conversation_repository.py 구현
   ↓ pytest 통과
7. tests/api/test_conversation_history_router.py 작성
   ↓ pytest 실패 확인
8. src/api/routes/conversation_history_router.py 구현
9. src/main.py 라우터 등록
   ↓ pytest 통과
```

---

## 6. 테스트 케이스 명세

### 6-1. test_history_schemas.py (4케이스)

| # | 케이스 | 검증 포인트 |
|---|--------|------------|
| 1 | SessionSummary 생성 | 모든 필드 정상 할당 |
| 2 | last_message 100자 초과 시 truncate | `"a" * 101` → 100자로 잘림 |
| 3 | SessionListResponse sessions 정렬 보존 | 입력 순서 그대로 반환 |
| 4 | MessageItem 생성 | role 문자열 "user"/"assistant" 허용 |

### 6-2. test_history_use_case.py (8케이스)

| # | 케이스 | Mock 대상 |
|---|--------|----------|
| 1 | 세션 목록 정상 반환 | repo.find_sessions_by_user |
| 2 | 세션 없을 때 빈 리스트 반환 | repo.find_sessions_by_user → [] |
| 3 | 메시지 목록 정상 반환 (turn_index 오름차순) | repo.find_by_session |
| 4 | 메시지 없을 때 빈 리스트 반환 | repo.find_by_session → [] |
| 5 | INFO 로그 호출 확인 (get_sessions) | logger.info 호출 횟수 |
| 6 | INFO 로그 호출 확인 (get_messages) | logger.info 호출 횟수 |
| 7 | repo 예외 시 ERROR 로그 + re-raise | repo 예외 → logger.error 호출 |
| 8 | request_id 로그에 전파 | logger.info kwargs에 request_id 포함 |

### 6-3. test_conversation_history_router.py (6케이스)

| # | 케이스 | HTTP 상태 |
|---|--------|----------|
| 1 | GET /sessions?user_id=X 정상 응답 | 200 + sessions 배열 |
| 2 | user_id 없이 GET /sessions | 422 |
| 3 | GET /sessions/{id}/messages?user_id=X 정상 응답 | 200 + messages 배열 |
| 4 | user_id 없이 GET /sessions/{id}/messages | 422 |
| 5 | 세션 없을 때 GET /sessions/{id}/messages | 200 + messages: [] |
| 6 | use_case 예외 시 500 반환 | 500 |

---

## 7. 로깅 설계 (LOG-001)

```python
async def get_sessions(self, user_id: str, request_id: str) -> SessionListResponse:
    self._logger.info("get_sessions started", request_id=request_id, user_id=user_id)
    try:
        sessions = await self._repo.find_sessions_by_user(UserId(user_id))
        self._logger.info(
            "get_sessions completed",
            request_id=request_id,
            session_count=len(sessions),
        )
        return SessionListResponse(user_id=user_id, sessions=sessions)
    except Exception as e:
        self._logger.error("get_sessions failed", exception=e, request_id=request_id)
        raise

async def get_messages(
    self, user_id: str, session_id: str, request_id: str
) -> MessageListResponse:
    self._logger.info(
        "get_messages started",
        request_id=request_id,
        user_id=user_id,
        session_id=session_id,
    )
    try:
        messages = await self._repo.find_by_session(UserId(user_id), SessionId(session_id))
        self._logger.info(
            "get_messages completed",
            request_id=request_id,
            message_count=len(messages),
        )
        return MessageListResponse(
            user_id=user_id,
            session_id=session_id,
            messages=[
                MessageItem(
                    id=m.id.value,
                    role=m.role.value,
                    content=m.content,
                    turn_index=m.turn_index.value,
                    created_at=m.created_at,
                )
                for m in messages
            ],
        )
    except Exception as e:
        self._logger.error("get_messages failed", exception=e, request_id=request_id)
        raise
```

---

## 8. 완료 기준 (Definition of Done)

- [ ] 신규 테스트 18개 모두 통과
- [ ] `GET /api/v1/conversations/sessions?user_id=X` 200 응답
- [ ] `GET /api/v1/conversations/sessions/{id}/messages?user_id=X` 200 응답
- [ ] `/verify-logging` 통과
- [ ] `/verify-architecture` 통과
- [ ] `/verify-tdd` 통과
