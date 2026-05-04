# AGENT-CHAT-001: 에이전트별 채팅 기록 관리 — 설계 문서

> 상태: Design
> Plan 참조: docs/01-plan/features/agent-chat-history.plan.md
> 연관 Task: AGENT-CHAT-001, CHAT-HIST-001, CONV-001
> 작성일: 2026-04-30

---

## 1. 설계 개요

기존 `conversation_message` / `conversation_summary` 테이블에 `agent_id` 컬럼을 추가하여
**사용자별 + 에이전트별** 채팅 기록을 분리 조회할 수 있게 한다.

| 변경 영역 | 핵심 내용 |
|-----------|-----------|
| DB 스키마 | 두 테이블에 `agent_id VARCHAR(36) DEFAULT 'super'` 추가 |
| Domain | `AgentId` VO, `ConversationMessage`/`ConversationSummary`에 agent_id 필드 |
| Repository | 에이전트별 세션 조회 메서드 2개 추가 |
| UseCase | `ConversationHistoryUseCase` 확장 (에이전트별 조회 3개 메서드) |
| Router | 에이전트별 엔드포인트 3개 추가 |
| 기존 채팅 흐름 | 메시지 저장 시 agent_id 전달 (`"super"` 또는 에이전트 UUID) |

---

## 2. DB 스키마 변경

### 2-1. 마이그레이션: V016__add_agent_id_to_conversation.sql

```sql
-- conversation_message에 agent_id 추가
ALTER TABLE conversation_message
  ADD COLUMN agent_id VARCHAR(36) NOT NULL DEFAULT 'super';

-- conversation_summary에 agent_id 추가
ALTER TABLE conversation_summary
  ADD COLUMN agent_id VARCHAR(36) NOT NULL DEFAULT 'super';

-- 에이전트별 조회 인덱스
CREATE INDEX ix_message_user_agent
  ON conversation_message (user_id, agent_id);

CREATE INDEX ix_summary_user_agent
  ON conversation_summary (user_id, agent_id);
```

**설계 결정**:
- `DEFAULT 'super'`로 선언하므로 기존 데이터는 ALTER 시점에 자동으로 `'super'` 값을 갖는다 (별도 UPDATE 불필요).
- FK 제약 없음 — 에이전트 삭제 후에도 채팅 기록은 보존한다.
- `VARCHAR(36)` — UUID 길이 + `"super"` (5자) 모두 수용.

### 2-2. ORM 모델 변경

**`src/infrastructure/persistence/models/conversation.py`**:

```python
class ConversationMessageModel(Base):
    __tablename__ = "conversation_message"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    session_id: Mapped[str] = mapped_column(String(255), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(36), nullable=False, default="super")  # 신규
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_message_user_session", "user_id", "session_id"),
        Index("ix_message_user_agent", "user_id", "agent_id"),  # 신규
    )


class ConversationSummaryModel(Base):
    __tablename__ = "conversation_summary"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    session_id: Mapped[str] = mapped_column(String(255), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(36), nullable=False, default="super")  # 신규
    summary_content: Mapped[str] = mapped_column(Text, nullable=False)
    start_turn: Mapped[int] = mapped_column(Integer, nullable=False)
    end_turn: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_summary_user_session", "user_id", "session_id"),
        Index("ix_summary_user_agent", "user_id", "agent_id"),  # 신규
    )
```

---

## 3. Domain 레이어 변경

### 3-1. Value Object: AgentId

**`src/domain/conversation/value_objects.py`** (추가):

```python
SUPER_AGENT_ID = "super"


@dataclass(frozen=True)
class AgentId:
    """에이전트 식별자. 일반 채팅은 'super', 커스텀 에이전트는 UUID."""

    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("AgentId cannot be empty")

    @classmethod
    def super(cls) -> "AgentId":
        return cls(SUPER_AGENT_ID)

    @property
    def is_super(self) -> bool:
        return self.value == SUPER_AGENT_ID
```

### 3-2. Entity 확장: ConversationMessage

**`src/domain/conversation/entities.py`** (수정):

```python
@dataclass(frozen=True)
class ConversationMessage:
    id: Optional[MessageId]
    user_id: UserId
    session_id: SessionId
    agent_id: AgentId           # 신규
    role: MessageRole
    content: str
    turn_index: TurnIndex
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.content or not self.content.strip():
            raise ValueError("Message content cannot be empty")
```

**`src/domain/conversation/entities.py`** (수정):

```python
@dataclass(frozen=True)
class ConversationSummary:
    id: Optional[SummaryId]
    user_id: UserId
    session_id: SessionId
    agent_id: AgentId           # 신규
    summary_content: str
    start_turn: TurnIndex
    end_turn: TurnIndex
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.summary_content or not self.summary_content.strip():
            raise ValueError("Summary content cannot be empty")
        if self.end_turn.value < self.start_turn.value:
            raise ValueError("end_turn must be >= start_turn")
```

### 3-3. History Schemas 확장

**`src/domain/conversation/history_schemas.py`** (추가):

```python
@dataclass(frozen=True)
class AgentChatSummary:
    """대화 기록이 있는 에이전트 요약."""

    agent_id: str
    agent_name: str
    session_count: int
    last_chat_at: datetime


@dataclass(frozen=True)
class AgentListResponse:
    """사용자의 에이전트 목록 응답."""

    user_id: str
    agents: List[AgentChatSummary]


@dataclass(frozen=True)
class AgentSessionListResponse:
    """에이전트별 세션 목록 응답."""

    user_id: str
    agent_id: str
    sessions: List[SessionSummary]


@dataclass(frozen=True)
class AgentMessageListResponse:
    """에이전트별 세션 메시지 응답."""

    user_id: str
    agent_id: str
    session_id: str
    messages: List[MessageItem]
```

---

## 4. Mapper 변경

**`src/infrastructure/persistence/mappers/conversation_mapper.py`** (수정):

### 4-1. ConversationMessageMapper

```python
@staticmethod
def to_entity(model: ConversationMessageModel) -> ConversationMessage:
    return ConversationMessage(
        id=MessageId(model.id) if model.id else None,
        user_id=UserId(model.user_id),
        session_id=SessionId(model.session_id),
        agent_id=AgentId(model.agent_id),    # 신규
        role=MessageRole.from_string(model.role),
        content=model.content,
        turn_index=TurnIndex(model.turn_index),
        created_at=model.created_at,
    )

@staticmethod
def to_model(entity: ConversationMessage) -> ConversationMessageModel:
    return ConversationMessageModel(
        id=entity.id.value if entity.id else None,
        user_id=entity.user_id.value,
        session_id=entity.session_id.value,
        agent_id=entity.agent_id.value,      # 신규
        role=entity.role.value,
        content=entity.content,
        turn_index=entity.turn_index.value,
        created_at=entity.created_at,
    )
```

### 4-2. ConversationSummaryMapper (동일 패턴)

```python
@staticmethod
def to_entity(model: ConversationSummaryModel) -> ConversationSummary:
    return ConversationSummary(
        id=SummaryId(model.id) if model.id else None,
        user_id=UserId(model.user_id),
        session_id=SessionId(model.session_id),
        agent_id=AgentId(model.agent_id),    # 신규
        summary_content=model.summary_content,
        start_turn=TurnIndex(model.start_turn),
        end_turn=TurnIndex(model.end_turn),
        created_at=model.created_at,
    )

@staticmethod
def to_model(entity: ConversationSummary) -> ConversationSummaryModel:
    return ConversationSummaryModel(
        id=entity.id.value if entity.id else None,
        user_id=entity.user_id.value,
        session_id=entity.session_id.value,
        agent_id=entity.agent_id.value,      # 신규
        summary_content=entity.summary_content,
        start_turn=entity.start_turn.value,
        end_turn=entity.end_turn.value,
        created_at=entity.created_at,
    )
```

---

## 5. Repository 레이어 변경

### 5-1. 추상 인터페이스 추가

**`src/application/repositories/conversation_repository.py`** (추가 메서드):

```python
from src.domain.conversation.history_schemas import AgentChatSummary, SessionSummary
from src.domain.conversation.value_objects import AgentId, UserId

class ConversationMessageRepository(ABC):
    # ... 기존 메서드 유지 ...

    @abstractmethod
    async def find_agents_by_user(
        self, user_id: UserId
    ) -> List[AgentChatSummary]:
        """user_id의 대화 기록이 있는 에이전트 목록을 최신순 반환."""
        pass

    @abstractmethod
    async def find_sessions_by_user_and_agent(
        self, user_id: UserId, agent_id: AgentId
    ) -> List[SessionSummary]:
        """user_id + agent_id 기준 세션 목록을 최신순 반환."""
        pass
```

### 5-2. SQLAlchemy 구현

**`src/infrastructure/persistence/repositories/conversation_repository.py`** (추가):

#### find_agents_by_user

```python
async def find_agents_by_user(
    self, user_id: UserId
) -> List[AgentChatSummary]:
    """user_id의 대화 기록이 있는 에이전트 목록 조회.

    SQL:
      SELECT agent_id,
             COUNT(DISTINCT session_id) AS session_count,
             MAX(created_at) AS last_chat_at
      FROM conversation_message
      WHERE user_id = :user_id
      GROUP BY agent_id
      ORDER BY last_chat_at DESC
    """
    stmt = (
        select(
            ConversationMessageModel.agent_id.label("agent_id"),
            func.count(
                func.distinct(ConversationMessageModel.session_id)
            ).label("session_count"),
            func.max(ConversationMessageModel.created_at).label("last_chat_at"),
        )
        .where(ConversationMessageModel.user_id == user_id.value)
        .group_by(ConversationMessageModel.agent_id)
        .order_by(desc("last_chat_at"))
    )
    result = await self._session.execute(stmt)
    rows = result.all()
    return [
        AgentChatSummary(
            agent_id=row.agent_id,
            agent_name="",  # UseCase에서 agent_definition 조회로 채움
            session_count=row.session_count,
            last_chat_at=row.last_chat_at,
        )
        for row in rows
    ]
```

**agent_name 채우기 전략**: Repository는 순수 conversation 테이블만 접근한다. `agent_name`은 UseCase에서 `AgentDefinitionRepository`를 통해 채운다. `"super"`인 경우 `"일반 채팅"` 하드코딩.

#### find_sessions_by_user_and_agent

```python
async def find_sessions_by_user_and_agent(
    self, user_id: UserId, agent_id: AgentId
) -> List[SessionSummary]:
    """user_id + agent_id 기준 세션 목록.

    기존 find_sessions_by_user와 동일 로직 + agent_id WHERE 조건 추가.
    """
    agg_stmt = (
        select(
            ConversationMessageModel.session_id.label("session_id"),
            func.count().label("message_count"),
            func.max(ConversationMessageModel.created_at).label("last_message_at"),
        )
        .where(ConversationMessageModel.user_id == user_id.value)
        .where(ConversationMessageModel.agent_id == agent_id.value)
        .group_by(ConversationMessageModel.session_id)
        .order_by(desc("last_message_at"))
    )
    agg_result = await self._session.execute(agg_stmt)
    agg_rows = agg_result.all()
    if not agg_rows:
        return []

    session_ids = [row.session_id for row in agg_rows]

    last_user_stmt = (
        select(
            ConversationMessageModel.session_id,
            ConversationMessageModel.content,
        )
        .where(ConversationMessageModel.user_id == user_id.value)
        .where(ConversationMessageModel.agent_id == agent_id.value)
        .where(ConversationMessageModel.session_id.in_(session_ids))
        .where(ConversationMessageModel.role == "user")
        .order_by(
            ConversationMessageModel.session_id,
            desc(ConversationMessageModel.created_at),
        )
    )
    last_user_result = await self._session.execute(last_user_stmt)
    last_user_by_session: dict[str, str] = {}
    for row in last_user_result.all():
        if row.session_id not in last_user_by_session:
            last_user_by_session[row.session_id] = row.content

    return [
        SessionSummary.from_raw(
            session_id=row.session_id,
            message_count=row.message_count,
            last_message=last_user_by_session.get(row.session_id, ""),
            last_message_at=row.last_message_at,
        )
        for row in agg_rows
    ]
```

---

## 6. UseCase 레이어 변경

### 6-1. ConversationHistoryUseCase 확장

**`src/application/conversation/history_use_case.py`** (기존 확장):

```python
from src.domain.conversation.history_schemas import (
    AgentChatSummary,
    AgentListResponse,
    AgentMessageListResponse,
    AgentSessionListResponse,
    MessageItem,
    MessageListResponse,
    SessionListResponse,
)
from src.domain.conversation.value_objects import AgentId, SessionId, UserId, SUPER_AGENT_ID


class ConversationHistoryUseCase:

    def __init__(
        self,
        repo: ConversationMessageRepository,
        logger: LoggerInterface,
        agent_repo=None,  # Optional[AgentDefinitionRepositoryInterface]
    ) -> None:
        self._repo = repo
        self._logger = logger
        self._agent_repo = agent_repo

    # --- 기존 메서드 (get_sessions, get_messages) 유지 ---

    async def get_agents_with_history(
        self, user_id: str, request_id: str
    ) -> AgentListResponse:
        """대화 기록이 있는 에이전트 목록 반환."""
        self._logger.info(
            "get_agents_with_history started",
            request_id=request_id,
            user_id=user_id,
        )
        try:
            raw_agents = await self._repo.find_agents_by_user(UserId(user_id))

            # agent_name 채우기
            agents = []
            for a in raw_agents:
                if a.agent_id == SUPER_AGENT_ID:
                    name = "일반 채팅"
                elif self._agent_repo:
                    agent_def = await self._agent_repo.find_by_id(a.agent_id)
                    name = agent_def.name if agent_def else f"삭제된 에이전트 ({a.agent_id[:8]})"
                else:
                    name = a.agent_id
                agents.append(AgentChatSummary(
                    agent_id=a.agent_id,
                    agent_name=name,
                    session_count=a.session_count,
                    last_chat_at=a.last_chat_at,
                ))

            self._logger.info(
                "get_agents_with_history completed",
                request_id=request_id,
                agent_count=len(agents),
            )
            return AgentListResponse(user_id=user_id, agents=agents)
        except Exception as e:
            self._logger.error(
                "get_agents_with_history failed",
                exception=e, request_id=request_id,
            )
            raise

    async def get_sessions_by_agent(
        self, user_id: str, agent_id: str, request_id: str
    ) -> AgentSessionListResponse:
        """에이전트별 세션 목록 반환."""
        self._logger.info(
            "get_sessions_by_agent started",
            request_id=request_id,
            user_id=user_id,
            agent_id=agent_id,
        )
        try:
            sessions = await self._repo.find_sessions_by_user_and_agent(
                UserId(user_id), AgentId(agent_id)
            )
            self._logger.info(
                "get_sessions_by_agent completed",
                request_id=request_id,
                session_count=len(sessions),
            )
            return AgentSessionListResponse(
                user_id=user_id,
                agent_id=agent_id,
                sessions=list(sessions),
            )
        except Exception as e:
            self._logger.error(
                "get_sessions_by_agent failed",
                exception=e, request_id=request_id,
            )
            raise

    async def get_messages_by_agent(
        self, user_id: str, agent_id: str, session_id: str, request_id: str
    ) -> AgentMessageListResponse:
        """에이전트 + 세션의 메시지 조회.

        agent_id 파라미터는 응답에 포함하기 위한 것이며,
        실제 조회는 user_id + session_id로 수행 (세션 자체가 에이전트에 귀속).
        """
        self._logger.info(
            "get_messages_by_agent started",
            request_id=request_id,
            user_id=user_id,
            agent_id=agent_id,
            session_id=session_id,
        )
        try:
            messages = await self._repo.find_by_session(
                UserId(user_id), SessionId(session_id)
            )
            items = [
                MessageItem(
                    id=m.id.value if m.id else 0,
                    role=m.role.value,
                    content=m.content,
                    turn_index=m.turn_index.value,
                    created_at=m.created_at,
                )
                for m in messages
            ]
            self._logger.info(
                "get_messages_by_agent completed",
                request_id=request_id,
                message_count=len(items),
            )
            return AgentMessageListResponse(
                user_id=user_id,
                agent_id=agent_id,
                session_id=session_id,
                messages=items,
            )
        except Exception as e:
            self._logger.error(
                "get_messages_by_agent failed",
                exception=e, request_id=request_id,
            )
            raise
```

### 6-2. ConversationUseCase — agent_id 전달

**`src/application/conversation/use_case.py`** (수정):

`execute()` 메서드에서 `ConversationMessage` 생성 시 `agent_id` 필드 추가.

```python
async def execute(
    self, request: ConversationChatRequest, request_id: str
) -> ConversationChatResponse:
    # ...
    user_msg = ConversationMessage(
        id=None,
        user_id=user_id,
        session_id=session_id,
        agent_id=AgentId(request.agent_id),  # 신규
        role=MessageRole.USER,
        content=request.message,
        turn_index=user_turn,
        created_at=datetime.utcnow(),
    )
    # ... assistant_msg도 동일하게 agent_id 추가 ...
```

`ConversationChatRequest`에 `agent_id: str = "super"` 필드 추가:

```python
@dataclass(frozen=True)
class ConversationChatRequest:
    user_id: str
    session_id: str
    message: str
    agent_id: str = "super"  # 신규 — 기본값 "super"
```

### 6-3. GeneralChatUseCase — agent_id="super" 고정

**`src/application/general_chat/use_case.py`** (수정):

메시지 저장 시 `agent_id=AgentId.super()` 전달:

```python
user_msg = ConversationMessage(
    id=None,
    user_id=user_id,
    session_id=session_id,
    agent_id=AgentId.super(),  # 신규
    role=MessageRole.USER,
    content=request.message,
    turn_index=TurnIndex(turn_base + 1),
    created_at=datetime.utcnow(),
)
```

### 6-4. ConversationSummary 생성 시 agent_id 전달

`_build_summarized_context` 내 ConversationSummary 생성 시에도 `agent_id` 추가:

```python
summary = ConversationSummary(
    id=None,
    user_id=user_id,
    session_id=session_id,
    agent_id=agent_id,  # 신규 — 호출 측에서 전달
    summary_content=summary_text,
    start_turn=start_turn,
    end_turn=end_turn,
    created_at=datetime.utcnow(),
)
```

---

## 7. API 엔드포인트 설계

### 7-1. 에이전트 목록 (대화 기록 있는)

**`GET /api/v1/conversations/agents`**

```
Header: Authorization: Bearer {token}
```

Response (200):
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
      "agent_id": "a1b2c3d4-...",
      "agent_name": "금융 분석 에이전트",
      "session_count": 3,
      "last_chat_at": "2026-04-29T15:00:00"
    }
  ]
}
```

### 7-2. 에이전트별 세션 목록

**`GET /api/v1/conversations/agents/{agent_id}/sessions`**

```
Header: Authorization: Bearer {token}
```

Response (200):
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

### 7-3. 에이전트 세션 메시지

**`GET /api/v1/conversations/agents/{agent_id}/sessions/{session_id}/messages`**

```
Header: Authorization: Bearer {token}
```

Response (200):
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
    }
  ]
}
```

### 7-4. Router 구현

**`src/api/routes/conversation_history_router.py`** (기존 파일에 추가):

```python
# --- Pydantic 모델 추가 ---

class AgentChatSummaryAPI(BaseModel):
    agent_id: str
    agent_name: str
    session_count: int
    last_chat_at: datetime


class AgentListAPIResponse(BaseModel):
    user_id: str
    agents: List[AgentChatSummaryAPI]


class AgentSessionListAPIResponse(BaseModel):
    user_id: str
    agent_id: str
    sessions: List[SessionSummaryAPI]


class AgentMessageListAPIResponse(BaseModel):
    user_id: str
    agent_id: str
    session_id: str
    messages: List[MessageItemAPI]


# --- 엔드포인트 추가 ---

@router.get("/agents", response_model=AgentListAPIResponse)
async def get_agents(
    user_id: str = Query(..., description="사용자 ID"),
    use_case: ConversationHistoryUseCase = Depends(get_history_use_case),
) -> AgentListAPIResponse:
    """대화 기록이 있는 에이전트 목록."""
    request_id = str(uuid.uuid4())
    result = await use_case.get_agents_with_history(
        user_id=user_id, request_id=request_id
    )
    return AgentListAPIResponse(
        user_id=result.user_id,
        agents=[
            AgentChatSummaryAPI(
                agent_id=a.agent_id,
                agent_name=a.agent_name,
                session_count=a.session_count,
                last_chat_at=a.last_chat_at,
            )
            for a in result.agents
        ],
    )


@router.get(
    "/agents/{agent_id}/sessions",
    response_model=AgentSessionListAPIResponse,
)
async def get_agent_sessions(
    agent_id: str,
    user_id: str = Query(..., description="사용자 ID"),
    use_case: ConversationHistoryUseCase = Depends(get_history_use_case),
) -> AgentSessionListAPIResponse:
    """에이전트별 세션 목록."""
    request_id = str(uuid.uuid4())
    result = await use_case.get_sessions_by_agent(
        user_id=user_id, agent_id=agent_id, request_id=request_id
    )
    return AgentSessionListAPIResponse(
        user_id=result.user_id,
        agent_id=result.agent_id,
        sessions=[
            SessionSummaryAPI(
                session_id=s.session_id,
                message_count=s.message_count,
                last_message=s.last_message,
                last_message_at=s.last_message_at,
            )
            for s in result.sessions
        ],
    )


@router.get(
    "/agents/{agent_id}/sessions/{session_id}/messages",
    response_model=AgentMessageListAPIResponse,
)
async def get_agent_session_messages(
    agent_id: str,
    session_id: str,
    user_id: str = Query(..., description="사용자 ID"),
    use_case: ConversationHistoryUseCase = Depends(get_history_use_case),
) -> AgentMessageListAPIResponse:
    """에이전트 세션의 메시지 목록."""
    request_id = str(uuid.uuid4())
    result = await use_case.get_messages_by_agent(
        user_id=user_id,
        agent_id=agent_id,
        session_id=session_id,
        request_id=request_id,
    )
    return AgentMessageListAPIResponse(
        user_id=result.user_id,
        agent_id=result.agent_id,
        session_id=result.session_id,
        messages=[
            MessageItemAPI(
                id=m.id,
                role=m.role,
                content=m.content,
                turn_index=m.turn_index,
                created_at=m.created_at,
            )
            for m in result.messages
        ],
    )
```

---

## 8. 기존 채팅 흐름 연동 상세

### 8-1. 영향받는 채팅 경로

| 채팅 경로 | 파일 | agent_id 값 |
|-----------|------|------------|
| `POST /api/v1/conversation/chat` | `conversation_router.py` → `ConversationUseCase` | `request.agent_id` (기본 `"super"`) |
| `POST /api/v1/chat` | `general_chat_router.py` → `GeneralChatUseCase` | `"super"` 고정 |
| `POST /api/v2/agents/{agent_id}/run` | `middleware_agent_router.py` → `RunMiddlewareAgentUseCase` | 대화 저장 없음 (현재) — 향후 확장 |

### 8-2. 커스텀 에이전트 채팅 연동 (향후)

현재 `RunMiddlewareAgentUseCase`는 대화를 DB에 저장하지 않는다.
에이전트별 채팅 기록을 남기려면 `RunMiddlewareAgentUseCase`에도
`ConversationMessageRepository` 의존성을 추가하고 저장 로직을 넣어야 한다.

이 부분은 **Phase 5 (기존 채팅 흐름 연동)** 에서 처리:

```python
# RunMiddlewareAgentUseCase.execute() 내부 (향후 추가)
user_msg = ConversationMessage(
    id=None,
    user_id=user_id,
    session_id=session_id,
    agent_id=AgentId(agent_id),  # path parameter에서 받은 agent_id
    role=MessageRole.USER,
    content=request.query,
    turn_index=TurnIndex(turn_base + 1),
    created_at=datetime.utcnow(),
)
await self._msg_repo.save(user_msg)
```

---

## 9. DI 배선 변경

**`src/api/main.py`** (수정):

`create_history_use_case_factory`에 `agent_repo` 주입 추가:

```python
def create_history_use_case_factory():
    def _factory(
        session: AsyncSession = Depends(get_session),
    ) -> ConversationHistoryUseCase:
        repo = SQLAlchemyConversationMessageRepository(session)
        agent_repo = SQLAlchemyMiddlewareAgentRepository(session)  # 에이전트 이름 조회용
        return ConversationHistoryUseCase(
            repo=repo,
            logger=app_logger,
            agent_repo=agent_repo,
        )
    return _factory
```

---

## 10. 에러 처리

| 상황 | HTTP 코드 | 처리 |
|------|-----------|------|
| user_id 미전달 | 422 | FastAPI Query 검증 자동 |
| agent_id 빈 문자열 | 422 | AgentId VO 검증 → ValueError → 422 |
| 해당 에이전트 대화 없음 | 200 | 빈 sessions/agents 배열 반환 |
| 존재하지 않는 session_id | 200 | 빈 messages 배열 반환 |

---

## 11. 테스트 설계

### 11-1. Domain 테스트

**`tests/domain/conversation/test_agent_id_vo.py`** (신규):

| TC | 설명 |
|----|------|
| TC-D1 | `AgentId("super")` 정상 생성, `is_super == True` |
| TC-D2 | `AgentId("uuid-xxx")` 정상 생성, `is_super == False` |
| TC-D3 | `AgentId("")` → ValueError |
| TC-D4 | `AgentId.super()` 팩토리 메서드 |
| TC-D5 | `ConversationMessage`에 `agent_id` 필드 포함 확인 |
| TC-D6 | `AgentChatSummary` 생성 검증 |

### 11-2. UseCase 테스트

**`tests/application/conversation/test_agent_history_use_case.py`** (신규):

| TC | 설명 |
|----|------|
| TC-U1 | `get_agents_with_history` — super + 커스텀 에이전트 2개 반환 |
| TC-U2 | `get_agents_with_history` — 대화 없는 사용자 → 빈 배열 |
| TC-U3 | `get_agents_with_history` — super agent_name = "일반 채팅" |
| TC-U4 | `get_agents_with_history` — 삭제된 에이전트 이름 fallback |
| TC-U5 | `get_sessions_by_agent` — 특정 에이전트의 세션 3개 반환 |
| TC-U6 | `get_sessions_by_agent` — 다른 에이전트의 세션 미포함 검증 |
| TC-U7 | `get_sessions_by_agent` — 세션 없는 에이전트 → 빈 배열 |
| TC-U8 | `get_messages_by_agent` — 세션 메시지 정상 반환 |
| TC-U9 | `get_messages_by_agent` — turn_index 오름차순 정렬 |
| TC-U10 | `get_messages_by_agent` — 빈 세션 → 빈 배열 |

### 11-3. Router 테스트

**`tests/api/test_agent_conversation_history_router.py`** (신규):

| TC | 설명 |
|----|------|
| TC-R1 | `GET /conversations/agents` 200 + 스키마 검증 |
| TC-R2 | `GET /conversations/agents` user_id 누락 → 422 |
| TC-R3 | `GET /conversations/agents/{agent_id}/sessions` 200 |
| TC-R4 | `GET /conversations/agents/{agent_id}/sessions` → 빈 결과 200 |
| TC-R5 | `GET /conversations/agents/{agent_id}/sessions/{session_id}/messages` 200 |
| TC-R6 | `GET /conversations/agents/{agent_id}/sessions/{session_id}/messages` → 빈 결과 200 |

### 11-4. 기존 테스트 수정

`ConversationMessage` entity에 `agent_id` 필드가 추가되므로, 기존 테스트에서 `ConversationMessage` 를 생성하는 곳에 `agent_id=AgentId.super()` 추가 필요.

영향받는 테스트 파일:

| 파일 | 변경 |
|------|------|
| `tests/domain/conversation/test_entities.py` | agent_id 파라미터 추가 |
| `tests/domain/conversation/test_policies.py` | agent_id 파라미터 추가 |
| `tests/application/conversation/test_use_case.py` | agent_id 파라미터 추가 |
| `tests/application/conversation/test_history_use_case.py` | agent_id 파라미터 추가 |
| `tests/application/general_chat/test_use_case.py` | agent_id 파라미터 추가 |

---

## 12. 구현 순서 (Do Phase 참고용)

```
Phase 1: DB 스키마 + ORM (30분)
  1. V016 마이그레이션 SQL 작성
  2. ConversationMessageModel에 agent_id 컬럼 추가
  3. ConversationSummaryModel에 agent_id 컬럼 추가

Phase 2: Domain 레이어 (30분)
  4. TC-D1~D4: AgentId VO 테스트 → 구현
  5. TC-D5: ConversationMessage entity에 agent_id 추가 (테스트 → 구현)
  6. TC-D6: AgentChatSummary, AgentListResponse 등 스키마 추가

Phase 3: Mapper + Repository (45분)
  7. Mapper에 agent_id 매핑 추가
  8. Repository 추상 메서드 추가
  9. find_agents_by_user 구현
  10. find_sessions_by_user_and_agent 구현

Phase 4: UseCase (45분)
  11. TC-U1~U10 테스트 작성
  12. ConversationHistoryUseCase 확장 구현
  13. get_agents_with_history, get_sessions_by_agent, get_messages_by_agent

Phase 5: Router + DI (30분)
  14. TC-R1~R6 테스트 작성
  15. 엔드포인트 3개 추가
  16. main.py DI 배선 수정

Phase 6: 기존 채팅 흐름 연동 (30분)
  17. ConversationChatRequest에 agent_id 필드 추가
  18. ConversationUseCase에서 agent_id 전달
  19. GeneralChatUseCase에서 agent_id="super" 전달
  20. 기존 테스트 수정 (agent_id 파라미터 추가)

Phase 7: 검증 (15분)
  21. /verify-architecture
  22. /verify-logging
  23. /verify-tdd
  24. 전체 pytest 실행
```

---

## 13. 변경 파일 요약

| 파일 | 유형 | 설명 |
|------|------|------|
| `db/migration/V016__add_agent_id_to_conversation.sql` | 신규 | agent_id 컬럼 + 인덱스 |
| `src/domain/conversation/value_objects.py` | 수정 | AgentId VO, SUPER_AGENT_ID 상수 |
| `src/domain/conversation/entities.py` | 수정 | agent_id 필드 추가 |
| `src/domain/conversation/schemas.py` | 수정 | ConversationChatRequest에 agent_id |
| `src/domain/conversation/history_schemas.py` | 수정 | AgentChatSummary, AgentListResponse 등 |
| `src/infrastructure/persistence/models/conversation.py` | 수정 | ORM agent_id 컬럼 |
| `src/infrastructure/persistence/mappers/conversation_mapper.py` | 수정 | agent_id 매핑 |
| `src/infrastructure/persistence/repositories/conversation_repository.py` | 수정 | 에이전트별 조회 메서드 |
| `src/application/repositories/conversation_repository.py` | 수정 | 추상 메서드 추가 |
| `src/application/conversation/history_use_case.py` | 수정 | 에이전트별 조회 UseCase |
| `src/application/conversation/use_case.py` | 수정 | agent_id 전달 |
| `src/application/general_chat/use_case.py` | 수정 | agent_id="super" |
| `src/api/routes/conversation_history_router.py` | 수정 | 에이전트별 엔드포인트 3개 |
| `src/api/main.py` | 수정 | DI 배선 |
| `tests/domain/conversation/test_agent_id_vo.py` | 신규 | AgentId VO 테스트 |
| `tests/application/conversation/test_agent_history_use_case.py` | 신규 | UseCase 테스트 |
| `tests/api/test_agent_conversation_history_router.py` | 신규 | Router 테스트 |

---

## 14. 하위 호환성

| 항목 | 영향 | 대응 |
|------|------|------|
| 기존 `POST /api/v1/chat` | 없음 | agent_id="super" 자동 적용 |
| 기존 `POST /api/v1/conversation/chat` | 없음 | agent_id 기본값 "super" |
| 기존 `GET /api/v1/conversations/sessions` | 없음 | 변경 없이 동작 (모든 agent의 세션 반환) |
| 기존 테스트 | agent_id 파라미터 추가 필요 | Phase 6에서 일괄 수정 |
| 프론트엔드 | API 응답 형식 변경 없음 | 신규 API만 추가, 기존 API 그대로 |
