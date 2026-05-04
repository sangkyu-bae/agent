# Agent Subscription & Customization Design Document

> **Summary**: 공유 에이전트 구독(북마크) + 포크(전체 복사 커스터마이징) 상세 설계
>
> **Project**: sangplusbot (idt)
> **Version**: -
> **Author**: 배상규
> **Date**: 2026-05-04
> **Status**: Draft
> **Planning Doc**: [agent-subscription-customization.plan.md](../01-plan/features/agent-subscription-customization.plan.md)

---

## 1. Overview

### 1.1 Design Goals

- 기존 `agent_definition` + `agent_tool` 구조를 **최대한 재사용**하여 포크 구현
- 구독(lightweight bookmark)과 포크(full copy)를 **분리된 관심사**로 설계
- 원본 삭제/비공개 시 **자동 포크 전환**으로 서비스 연속성 보장
- Thin DDD 레이어 규칙 준수 (domain → application → infrastructure)

### 1.2 Design Principles

- 기존 `AgentDefinition` 도메인 객체에 최소한의 필드만 추가 (`forked_from`, `forked_at`)
- 포크는 **기존 save() 메서드를 재사용** — 새 UUID로 agent_definition + agent_tool INSERT
- 구독은 별도 Aggregate로 분리 — agent_definition과 독립적 생명주기

---

## 2. Architecture

### 2.1 Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│ API Layer (FastAPI Router)                                       │
│  POST /agents/{id}/subscribe    → SubscribeUseCase              │
│  DELETE /agents/{id}/subscribe  → UnsubscribeUseCase            │
│  PATCH /agents/{id}/subscribe   → UpdateSubscriptionUseCase     │
│  POST /agents/{id}/fork         → ForkAgentUseCase              │
│  GET /agents/my                 → ListMyAgentsUseCase           │
│  DELETE /agents/{id}            → DeleteAgentUseCase (수정)     │
├─────────────────────────────────────────────────────────────────┤
│ Application Layer (Use Cases)                                    │
│  SubscribeUseCase         — 구독/해제/설정변경                   │
│  ForkAgentUseCase         — 포크 생성 (전체 복사)                │
│  ListMyAgentsUseCase      — 통합 목록 (소유+구독+포크)           │
│  AutoForkService          — 원본 삭제 시 구독자 자동 포크        │
├─────────────────────────────────────────────────────────────────┤
│ Domain Layer                                                     │
│  AgentDefinition          — +forked_from, +forked_at             │
│  Subscription (NEW)       — user_id + agent_id + is_pinned       │
│  ForkPolicy (NEW)         — 포크 가능 여부 판단                  │
│  SubscriptionPolicy (NEW) — 구독 가능 여부 판단                  │
├─────────────────────────────────────────────────────────────────┤
│ Infrastructure Layer                                             │
│  AgentDefinitionModel     — +forked_from, +forked_at 컬럼        │
│  SubscriptionModel (NEW)  — user_agent_subscription 테이블       │
│  AgentDefinitionRepo      — +fork(), +find_subscribers()         │
│  SubscriptionRepo (NEW)   — 구독 CRUD                            │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

```
[구독 플로우]
  사용자 → POST /subscribe → SubscriptionPolicy.can_subscribe()
         → SubscriptionRepository.save()

[포크 플로우]
  사용자 → POST /fork → ForkPolicy.can_fork()
         → AgentDefinitionRepo.find_by_id() (원본 로드)
         → AgentDefinition 복사 (새 UUID, forked_from 설정)
         → AgentDefinitionRepo.save() (포크 저장)

[삭제 + 자동 포크 플로우]
  소유자 → DELETE /agents/{id}
         → VisibilityPolicy.can_delete()
         → AutoForkService.fork_for_subscribers() (visibility != private일 때)
         → AgentDefinitionRepo.soft_delete()
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| ForkAgentUseCase | AgentDefinitionRepo, SubscriptionRepo | 원본 조회 + 포크 저장 |
| SubscribeUseCase | SubscriptionRepo, AgentDefinitionRepo | 에이전트 존재 확인 + 구독 |
| AutoForkService | SubscriptionRepo, AgentDefinitionRepo | 구독자 조회 + 포크 생성 |
| DeleteAgentUseCase | AutoForkService (추가) | 삭제 전 자동 포크 트리거 |
| ListMyAgentsUseCase | AgentDefinitionRepo, SubscriptionRepo | 통합 목록 조회 |

---

## 3. Data Model

### 3.1 AgentDefinition 확장

```python
@dataclass
class AgentDefinition:
    # ... 기존 필드 유지 ...
    id: str
    user_id: str
    name: str
    description: str
    system_prompt: str
    flow_hint: str
    workers: list[WorkerDefinition]
    llm_model_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    visibility: str = "private"
    department_id: str | None = None
    temperature: float = 0.70
    llm_model: LlmModel | None = None
    # --- 신규 필드 ---
    forked_from: str | None = None    # 원본 agent_id (NULL이면 원본)
    forked_at: datetime | None = None  # 포크 생성 시각
```

### 3.2 Subscription 엔티티 (NEW)

```python
# src/domain/agent_builder/subscription.py

@dataclass
class Subscription:
    """사용자의 에이전트 구독 (북마크)."""
    id: str
    user_id: str
    agent_id: str
    is_pinned: bool = False
    subscribed_at: datetime
```

### 3.3 Entity Relationships

```
[User] 1 ──── N [AgentDefinition] (소유)
   │                    │
   │                    │ forked_from (nullable, 자기참조)
   │                    ▼
   │             [AgentDefinition] (원본)
   │
   └── 1 ──── N [Subscription] N ──── 1 [AgentDefinition]
```

### 3.4 Database Schema

#### V017 마이그레이션

```sql
-- V017__add_agent_subscription_and_fork.sql

-- 1. agent_definition에 포크 관련 컬럼 추가
ALTER TABLE agent_definition
    ADD COLUMN forked_from VARCHAR(36) NULL AFTER temperature,
    ADD COLUMN forked_at DATETIME NULL AFTER forked_from;

ALTER TABLE agent_definition
    ADD INDEX ix_agent_forked_from (forked_from);

-- 2. 구독 테이블 생성
CREATE TABLE user_agent_subscription (
    id VARCHAR(36) NOT NULL,
    user_id VARCHAR(100) NOT NULL,
    agent_id VARCHAR(36) NOT NULL,
    is_pinned TINYINT(1) NOT NULL DEFAULT 0,
    subscribed_at DATETIME NOT NULL,

    PRIMARY KEY (id),
    UNIQUE KEY uq_user_agent_sub (user_id, agent_id),
    INDEX ix_subscription_user (user_id),
    INDEX ix_subscription_agent (agent_id),

    CONSTRAINT fk_sub_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_sub_agent FOREIGN KEY (agent_id) REFERENCES agent_definition(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/api/v1/agents/{agent_id}/subscribe` | 에이전트 구독 | Required |
| DELETE | `/api/v1/agents/{agent_id}/subscribe` | 구독 해제 | Required |
| PATCH | `/api/v1/agents/{agent_id}/subscribe` | 구독 설정 변경 (pin) | Required |
| POST | `/api/v1/agents/{agent_id}/fork` | 에이전트 포크 | Required |
| GET | `/api/v1/agents/my` | 내 에이전트 통합 목록 | Required |
| GET | `/api/v1/agents/{agent_id}/forks` | 포크 목록 (원본 소유자) | Required |

### 4.2 Detailed Specification

#### `POST /api/v1/agents/{agent_id}/subscribe`

구독 생성. 이미 구독 중이면 409 Conflict.

**Request**: Body 없음 (path param만)

**Response (201):**
```json
{
  "subscription_id": "uuid",
  "agent_id": "uuid",
  "agent_name": "원본 에이전트명",
  "is_pinned": false,
  "subscribed_at": "2026-05-04T12:00:00Z"
}
```

**Error Responses:**
- `404`: 에이전트 없음 또는 접근 불가
- `409`: 이미 구독 중
- `400`: 자신의 에이전트는 구독 불가

---

#### `DELETE /api/v1/agents/{agent_id}/subscribe`

구독 해제. 204 No Content.

**Error Responses:**
- `404`: 구독 없음

---

#### `PATCH /api/v1/agents/{agent_id}/subscribe`

구독 설정 변경 (즐겨찾기 등).

**Request:**
```json
{
  "is_pinned": true
}
```

**Response (200):**
```json
{
  "subscription_id": "uuid",
  "agent_id": "uuid",
  "is_pinned": true,
  "subscribed_at": "2026-05-04T12:00:00Z"
}
```

---

#### `POST /api/v1/agents/{agent_id}/fork`

에이전트 포크 (전체 복사). 원본의 agent_definition + agent_tool을 모두 복사하여 새 에이전트 생성.

**Request:**
```json
{
  "name": "내 커스텀 에이전트"
}
```
- `name`: 선택. 생략 시 `"{원본이름} (사본)"` 자동 생성.

**Response (201):**
```json
{
  "agent_id": "새-uuid",
  "name": "내 커스텀 에이전트",
  "forked_from": "원본-uuid",
  "forked_at": "2026-05-04T12:00:00Z",
  "system_prompt": "복사된 프롬프트",
  "workers": [...],
  "visibility": "private",
  "temperature": 0.70,
  "llm_model_id": "model-uuid"
}
```

**Error Responses:**
- `404`: 원본 에이전트 없음 또는 접근 불가
- `400`: 이미 삭제된 에이전트

---

#### `GET /api/v1/agents/my`

내 에이전트 통합 목록. 소유(owned) + 구독(subscribed) + 포크(forked) 구분.

**Query Params:**
- `filter`: `all` | `owned` | `subscribed` | `forked` (기본: `all`)
- `search`: 이름 검색
- `page`: 페이지 (기본: 1)
- `size`: 페이지 크기 (기본: 20)

**Response (200):**
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

---

#### `GET /api/v1/agents/{agent_id}/forks`

특정 에이전트의 포크 통계 (원본 소유자 전용).

**Response (200):**
```json
{
  "agent_id": "original-uuid",
  "fork_count": 5,
  "subscriber_count": 12
}
```

---

## 5. Domain Layer 상세 설계

### 5.1 ForkPolicy (NEW)

```python
# src/domain/agent_builder/policies.py 에 추가

class ForkPolicy:
    @staticmethod
    def can_fork(ctx: AccessCheckInput) -> bool:
        """포크 가능 여부: 접근 가능 + 자신의 에이전트가 아닌 경우."""
        if ctx.agent_owner_id == ctx.viewer_user_id:
            return False  # 자신의 에이전트는 포크 불필요
        return VisibilityPolicy.can_access(ctx)

    @staticmethod
    def validate_source_status(status: str) -> None:
        """삭제된 에이전트는 포크 불가."""
        if status == "deleted":
            raise ValueError("삭제된 에이전트는 포크할 수 없습니다.")
```

### 5.2 SubscriptionPolicy (NEW)

```python
# src/domain/agent_builder/subscription.py 에 포함

class SubscriptionPolicy:
    @staticmethod
    def can_subscribe(ctx: AccessCheckInput) -> bool:
        """구독 가능 여부: 접근 가능 + 자신의 에이전트가 아닌 경우."""
        if ctx.agent_owner_id == ctx.viewer_user_id:
            return False  # 자신의 에이전트는 구독 불필요
        return VisibilityPolicy.can_access(ctx)
```

### 5.3 SubscriptionRepositoryInterface (NEW)

```python
# src/domain/agent_builder/interfaces.py 에 추가

class SubscriptionRepositoryInterface(ABC):
    @abstractmethod
    async def save(self, subscription: Subscription, request_id: str) -> Subscription:
        """구독 INSERT."""

    @abstractmethod
    async def find_by_user_and_agent(
        self, user_id: str, agent_id: str, request_id: str
    ) -> Subscription | None:
        """특정 사용자의 특정 에이전트 구독 조회."""

    @abstractmethod
    async def delete(self, user_id: str, agent_id: str, request_id: str) -> None:
        """구독 DELETE."""

    @abstractmethod
    async def update_pin(
        self, user_id: str, agent_id: str, is_pinned: bool, request_id: str
    ) -> Subscription:
        """즐겨찾기 토글."""

    @abstractmethod
    async def list_by_user(
        self, user_id: str, request_id: str
    ) -> list[Subscription]:
        """사용자의 전체 구독 목록."""

    @abstractmethod
    async def find_subscribers_by_agent(
        self, agent_id: str, request_id: str
    ) -> list[Subscription]:
        """특정 에이전트의 전체 구독자 목록 (자동 포크용)."""

    @abstractmethod
    async def delete_by_agent(self, agent_id: str, request_id: str) -> int:
        """에이전트 삭제 시 관련 구독 일괄 삭제. 삭제 건수 반환."""
```

### 5.4 AgentDefinitionRepositoryInterface 확장

```python
# 기존 인터페이스에 추가

@abstractmethod
async def find_by_id_with_status(
    self, agent_id: str, request_id: str
) -> AgentDefinition | None:
    """삭제된 에이전트 포함 조회 (자동 포크 시 마지막 상태 스냅샷용)."""

@abstractmethod
async def count_forks(self, source_agent_id: str, request_id: str) -> int:
    """특정 에이전트의 포크 수."""

@abstractmethod
async def count_subscribers(self, agent_id: str, request_id: str) -> int:
    """특정 에이전트의 구독자 수."""
```

---

## 6. Application Layer 상세 설계

### 6.1 SubscribeUseCase

```python
# src/application/agent_builder/subscribe_use_case.py

class SubscribeUseCase:
    def __init__(
        self,
        agent_repo: AgentDefinitionRepositoryInterface,
        subscription_repo: SubscriptionRepositoryInterface,
        logger: LoggerInterface,
    ) -> None: ...

    async def subscribe(
        self, agent_id: str, user_id: str, request_id: str
    ) -> SubscribeResponse:
        """구독 생성."""
        # 1. 에이전트 존재 + 접근 가능 확인
        # 2. SubscriptionPolicy.can_subscribe() 검증
        # 3. 중복 구독 확인 → 있으면 409
        # 4. Subscription 생성 및 저장

    async def unsubscribe(
        self, agent_id: str, user_id: str, request_id: str
    ) -> None:
        """구독 해제."""
        # 1. 구독 존재 확인
        # 2. 삭제

    async def update_pin(
        self, agent_id: str, user_id: str, is_pinned: bool, request_id: str
    ) -> SubscribeResponse:
        """즐겨찾기 토글."""
```

### 6.2 ForkAgentUseCase

```python
# src/application/agent_builder/fork_agent_use_case.py

class ForkAgentUseCase:
    def __init__(
        self,
        agent_repo: AgentDefinitionRepositoryInterface,
        logger: LoggerInterface,
    ) -> None: ...

    async def execute(
        self,
        source_agent_id: str,
        user_id: str,
        custom_name: str | None,
        request_id: str,
        viewer_department_ids: list[str] | None = None,
    ) -> ForkAgentResponse:
        """포크 생성 (전체 복사)."""
        # 1. 원본 에이전트 조회
        # 2. ForkPolicy.can_fork() 검증
        # 3. ForkPolicy.validate_source_status() 검증
        # 4. 새 AgentDefinition 생성:
        #    - id: 새 UUID
        #    - user_id: 요청 사용자
        #    - name: custom_name or "{원본이름} (사본)"
        #    - system_prompt, flow_hint, workers: 원본 그대로 복사
        #    - llm_model_id, temperature: 원본 그대로 복사
        #    - visibility: "private" (고정)
        #    - department_id: None (고정)
        #    - forked_from: source_agent_id
        #    - forked_at: now()
        # 5. agent_repo.save() — 기존 save 메서드 재사용
```

### 6.3 ListMyAgentsUseCase

```python
# src/application/agent_builder/list_my_agents_use_case.py

class ListMyAgentsUseCase:
    def __init__(
        self,
        agent_repo: AgentDefinitionRepositoryInterface,
        subscription_repo: SubscriptionRepositoryInterface,
        logger: LoggerInterface,
    ) -> None: ...

    async def execute(
        self,
        user_id: str,
        filter: str,  # "all" | "owned" | "subscribed" | "forked"
        search: str | None,
        page: int,
        size: int,
        request_id: str,
    ) -> ListMyAgentsResponse:
        """통합 목록 조회."""
        # filter == "owned": agent_repo.list_by_user() + forked_from IS NULL
        # filter == "forked": agent_repo.list_by_user() + forked_from IS NOT NULL
        # filter == "subscribed": subscription_repo.list_by_user()
        #                        → agent_repo.find_by_ids()로 상세 조회
        # filter == "all": 위 3개 합산 + 중복 제거 + 정렬
        #
        # 각 항목에 source_type ("owned"/"subscribed"/"forked") 태깅
```

### 6.4 AutoForkService

```python
# src/application/agent_builder/auto_fork_service.py

class AutoForkService:
    """원본 에이전트 삭제/비공개 시 구독자를 위한 자동 포크 서비스."""

    def __init__(
        self,
        agent_repo: AgentDefinitionRepositoryInterface,
        subscription_repo: SubscriptionRepositoryInterface,
        logger: LoggerInterface,
    ) -> None: ...

    async def fork_for_subscribers(
        self, agent: AgentDefinition, request_id: str
    ) -> int:
        """삭제 직전, 구독자들에게 자동 포크 생성. 생성 건수 반환."""
        # 1. subscription_repo.find_subscribers_by_agent(agent.id)
        # 2. 각 구독자에 대해:
        #    a. 이미 해당 에이전트를 포크했는지 확인 (중복 방지)
        #    b. 포크 생성 (name: "{원본이름} (자동 보존)")
        # 3. subscription_repo.delete_by_agent(agent.id) — 구독 일괄 삭제
        # 4. 생성 건수 반환
```

### 6.5 DeleteAgentUseCase 수정

```python
# 기존 DeleteAgentUseCase.execute() 에서 soft_delete 전에 AutoForkService 호출

async def execute(self, agent_id, viewer_user_id, viewer_role, request_id):
    agent = await self._repository.find_by_id(agent_id, request_id)
    # ... 권한 확인 ...

    # --- 신규 삽입 ---
    if agent.visibility != "private":
        fork_count = await self._auto_fork_service.fork_for_subscribers(
            agent, request_id
        )
        self._logger.info(
            "AutoFork completed",
            request_id=request_id,
            fork_count=fork_count,
        )
    # --- 신규 끝 ---

    await self._repository.soft_delete(agent_id, request_id)
```

---

## 7. Infrastructure Layer 상세 설계

### 7.1 AgentDefinitionModel 확장

```python
# src/infrastructure/agent_builder/models.py 에 추가

class AgentDefinitionModel(Base):
    # ... 기존 컬럼 유지 ...
    forked_from: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    forked_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
```

### 7.2 UserAgentSubscriptionModel (NEW)

```python
# src/infrastructure/agent_builder/subscription_model.py

class UserAgentSubscriptionModel(Base):
    __tablename__ = "user_agent_subscription"
    __table_args__ = (
        UniqueConstraint("user_id", "agent_id", name="uq_user_agent_sub"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agent_definition.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_pinned: Mapped[bool] = mapped_column(nullable=False, default=False)
    subscribed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
```

### 7.3 SubscriptionRepository (NEW)

```python
# src/infrastructure/agent_builder/subscription_repository.py

class SubscriptionRepository(SubscriptionRepositoryInterface):
    def __init__(self, session: AsyncSession, logger: LoggerInterface): ...

    async def save(self, subscription, request_id) -> Subscription: ...
    async def find_by_user_and_agent(self, user_id, agent_id, request_id) -> Subscription | None: ...
    async def delete(self, user_id, agent_id, request_id) -> None: ...
    async def update_pin(self, user_id, agent_id, is_pinned, request_id) -> Subscription: ...
    async def list_by_user(self, user_id, request_id) -> list[Subscription]: ...
    async def find_subscribers_by_agent(self, agent_id, request_id) -> list[Subscription]: ...
    async def delete_by_agent(self, agent_id, request_id) -> int: ...
```

### 7.4 AgentDefinitionRepository 확장

```python
# 기존 레포지토리에 메서드 추가

async def find_by_id_with_status(self, agent_id, request_id) -> AgentDefinition | None:
    """status 필터 없이 조회 (삭제된 것도 포함)."""

async def count_forks(self, source_agent_id, request_id) -> int:
    """SELECT COUNT(*) FROM agent_definition WHERE forked_from = :id AND status != 'deleted'"""

async def count_subscribers(self, agent_id, request_id) -> int:
    """SELECT COUNT(*) FROM user_agent_subscription WHERE agent_id = :id"""

# _to_domain 수정: forked_from, forked_at 매핑 추가
```

---

## 8. Application Schemas (Request/Response)

### 8.1 구독 관련

```python
# src/application/agent_builder/schemas.py 에 추가

class SubscribeResponse(BaseModel):
    subscription_id: str
    agent_id: str
    agent_name: str
    is_pinned: bool
    subscribed_at: str

class UpdateSubscriptionRequest(BaseModel):
    is_pinned: bool
```

### 8.2 포크 관련

```python
class ForkAgentRequest(BaseModel):
    name: str | None = Field(None, max_length=200)

class ForkAgentResponse(BaseModel):
    agent_id: str
    name: str
    forked_from: str
    forked_at: str
    system_prompt: str
    workers: list[WorkerInfo]
    visibility: str
    temperature: float
    llm_model_id: str
```

### 8.3 내 에이전트 목록 관련

```python
class MyAgentSummary(BaseModel):
    agent_id: str
    name: str
    description: str
    source_type: str      # "owned" | "subscribed" | "forked"
    visibility: str
    temperature: float
    owner_user_id: str
    forked_from: str | None = None
    is_pinned: bool = False
    created_at: str

class ListMyAgentsRequest(BaseModel):
    filter: str = Field("all", pattern="^(all|owned|subscribed|forked)$")
    search: str | None = None
    page: int = Field(1, ge=1)
    size: int = Field(20, ge=1, le=100)

class ListMyAgentsResponse(BaseModel):
    agents: list[MyAgentSummary]
    total: int
    page: int
    size: int

class ForkStatsResponse(BaseModel):
    agent_id: str
    fork_count: int
    subscriber_count: int
```

---

## 9. Error Handling

### 9.1 Error Code Definition

| Code | Message | Cause | Handling |
|------|---------|-------|----------|
| 400 | 자신의 에이전트는 구독/포크할 수 없습니다 | 자기 에이전트 구독/포크 시도 | 클라이언트에서 버튼 비활성화 |
| 400 | 삭제된 에이전트는 포크할 수 없습니다 | 삭제된 에이전트 포크 시도 | 목록 새로고침 유도 |
| 403 | 접근 권한 없음 | visibility 규칙 위반 | 로그인/부서 확인 유도 |
| 404 | 에이전트/구독 없음 | 존재하지 않는 리소스 | 목록 페이지로 리다이렉트 |
| 409 | 이미 구독 중입니다 | 중복 구독 시도 | 클라이언트에서 상태 동기화 |

---

## 10. Security Considerations

- [x] 인증 필수: 모든 엔드포인트에 `get_current_user` 의존성
- [x] 접근 제어: `VisibilityPolicy.can_access()` 재사용
- [x] 자기 에이전트 구독/포크 방지: `ForkPolicy`, `SubscriptionPolicy`에서 검증
- [x] SQL Injection 방지: SQLAlchemy ORM 사용
- [x] forked_from은 FK 아님 → 원본 삭제 시 참조 무결성 문제 없음

---

## 11. Test Plan

### 11.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit Test | Domain Policy (ForkPolicy, SubscriptionPolicy) | pytest |
| Unit Test | UseCase (Subscribe, Fork, ListMy, AutoFork) | pytest + mock |
| Integration Test | Repository (Subscription CRUD, Fork save) | pytest + DB |
| Integration Test | API Endpoint (전체 플로우) | httpx + TestClient |

### 11.2 Test Cases

**구독 (Subscription)**
- [ ] 공개 에이전트 구독 성공
- [ ] 부서 에이전트 구독 성공 (같은 부서)
- [ ] 비공개 에이전트 구독 실패 (403)
- [ ] 자기 에이전트 구독 실패 (400)
- [ ] 중복 구독 실패 (409)
- [ ] 구독 해제 성공
- [ ] 존재하지 않는 구독 해제 실패 (404)
- [ ] 즐겨찾기 토글 성공

**포크 (Fork)**
- [ ] 접근 가능한 에이전트 포크 성공
- [ ] 포크 시 모든 필드(agent_definition + agent_tool) 정확히 복사됨
- [ ] 포크된 에이전트의 visibility는 private
- [ ] 포크된 에이전트의 forked_from이 원본 ID
- [ ] 삭제된 에이전트 포크 실패 (400)
- [ ] 접근 불가 에이전트 포크 실패 (403)
- [ ] 자기 에이전트 포크 실패 (400)
- [ ] 커스텀 이름 지정하여 포크 성공

**자동 포크 (AutoFork)**
- [ ] 공개 에이전트 삭제 시 구독자에게 자동 포크 생성
- [ ] 이미 포크한 구독자에게는 중복 포크 미생성
- [ ] 자동 포크 후 구독 레코드 삭제됨
- [ ] 비공개 에이전트 삭제 시 자동 포크 미실행

**통합 목록 (ListMyAgents)**
- [ ] filter=all: 소유+구독+포크 통합 목록
- [ ] filter=owned: 내가 만든 에이전트만 (포크 제외)
- [ ] filter=forked: 내가 포크한 에이전트만
- [ ] filter=subscribed: 구독한 에이전트만
- [ ] source_type 필드 정확한 태깅
- [ ] 페이지네이션 동작

---

## 12. Clean Architecture Layer Assignment

### 12.1 Dependency Rules

```
┌─────────────────────────────────────────────────────────────┐
│                    Dependency Direction                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   API (Router) ──→ Application (UseCase) ──→ Domain         │
│                          │                    ↑             │
│                          └──→ Infrastructure ─┘             │
│                                                             │
│   Domain: Policy, Entity, Interface (순수 Python)           │
│   Infrastructure: SQLAlchemy Model, Repository 구현체       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 12.2 File Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| Subscription, SubscriptionPolicy | Domain | `src/domain/agent_builder/subscription.py` |
| ForkPolicy | Domain | `src/domain/agent_builder/policies.py` |
| SubscriptionRepositoryInterface | Domain | `src/domain/agent_builder/interfaces.py` |
| SubscribeUseCase | Application | `src/application/agent_builder/subscribe_use_case.py` |
| ForkAgentUseCase | Application | `src/application/agent_builder/fork_agent_use_case.py` |
| ListMyAgentsUseCase | Application | `src/application/agent_builder/list_my_agents_use_case.py` |
| AutoForkService | Application | `src/application/agent_builder/auto_fork_service.py` |
| Schemas (Request/Response) | Application | `src/application/agent_builder/schemas.py` |
| UserAgentSubscriptionModel | Infrastructure | `src/infrastructure/agent_builder/subscription_model.py` |
| SubscriptionRepository | Infrastructure | `src/infrastructure/agent_builder/subscription_repository.py` |
| AgentDefinitionModel (수정) | Infrastructure | `src/infrastructure/agent_builder/models.py` |
| AgentDefinitionRepository (확장) | Infrastructure | `src/infrastructure/agent_builder/agent_definition_repository.py` |
| Router (확장) | API | `src/api/routes/agent_builder_router.py` |
| DI 등록 | API | `src/api/main.py` |
| Migration | DB | `db/migration/V017__add_agent_subscription_and_fork.sql` |

---

## 13. Implementation Order

```
Step 1: DB Migration
  └── V017__add_agent_subscription_and_fork.sql

Step 2: Domain Layer
  ├── 2-1. schemas.py — AgentDefinition에 forked_from, forked_at 추가
  ├── 2-2. subscription.py — Subscription 엔티티 + SubscriptionPolicy
  ├── 2-3. policies.py — ForkPolicy 추가
  └── 2-4. interfaces.py — SubscriptionRepositoryInterface 추가
              + AgentDefinitionRepositoryInterface 확장

Step 3: Infrastructure Layer
  ├── 3-1. models.py — AgentDefinitionModel에 forked_from, forked_at 컬럼
  ├── 3-2. subscription_model.py — UserAgentSubscriptionModel (NEW)
  ├── 3-3. subscription_repository.py — SubscriptionRepository (NEW)
  └── 3-4. agent_definition_repository.py — fork 관련 메서드 추가
              + _to_domain 수정

Step 4: Application Layer
  ├── 4-1. schemas.py — 구독/포크/목록 Request/Response 추가
  ├── 4-2. subscribe_use_case.py (NEW)
  ├── 4-3. fork_agent_use_case.py (NEW)
  ├── 4-4. list_my_agents_use_case.py (NEW)
  └── 4-5. auto_fork_service.py (NEW)

Step 5: DeleteAgentUseCase 수정
  └── 5-1. delete_agent_use_case.py — AutoForkService 주입 + 호출

Step 6: API Layer
  ├── 6-1. agent_builder_router.py — 엔드포인트 추가
  └── 6-2. main.py — DI 등록

Step 7: Tests (각 Step과 병행 — TDD)
  ├── tests/domain/ — Policy 단위 테스트
  ├── tests/application/ — UseCase 단위 테스트
  ├── tests/infrastructure/ — Repository 통합 테스트
  └── tests/api/ — 엔드포인트 통합 테스트
```

---

## 14. DI Registration (main.py)

```python
# 신규 DI 플레이스홀더 (agent_builder_router.py)
def get_subscribe_use_case():
    raise NotImplementedError

def get_fork_agent_use_case():
    raise NotImplementedError

def get_list_my_agents_use_case():
    raise NotImplementedError

# main.py factory
def subscribe_uc_factory(session = Depends(get_session)):
    return SubscribeUseCase(
        agent_repo=_make_repo(session),
        subscription_repo=SubscriptionRepository(session, app_logger),
        logger=app_logger,
    )

def fork_uc_factory(session = Depends(get_session)):
    return ForkAgentUseCase(
        agent_repo=_make_repo(session),
        logger=app_logger,
    )

def list_my_uc_factory(session = Depends(get_session)):
    return ListMyAgentsUseCase(
        agent_repo=_make_repo(session),
        subscription_repo=SubscriptionRepository(session, app_logger),
        logger=app_logger,
    )

# DeleteAgentUseCase factory 수정 (AutoForkService 주입)
def delete_uc_factory(session = Depends(get_session)):
    return DeleteAgentUseCase(
        repository=_make_repo(session),
        auto_fork_service=AutoForkService(
            agent_repo=_make_repo(session),
            subscription_repo=SubscriptionRepository(session, app_logger),
            logger=app_logger,
        ),
        logger=app_logger,
    )
```

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-04 | Initial draft | 배상규 |
