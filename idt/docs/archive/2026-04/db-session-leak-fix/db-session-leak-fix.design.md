# DB-SESSION-LEAK-FIX: 설계 문서

> 상태: Design
> Plan 참조: `docs/01-plan/features/db-session-leak-fix.plan.md`
> 연관 Task: CHAT-001, CONV-001, MYSQL-001, AUTH-001, AGENT-004, AGENT-005, AGENT-006, MCP-REG-001
> 작성일: 2026-04-18

---

## 1. 설계 개요

### 1-1. 문제 요약

`POST /api/v1/chat` 등 대화/인증/에이전트 빌더 엔드포인트가 누적 호출되면
SQLAlchemy AsyncSession이 풀로 반환되지 않아 `flush()` 단계에서 greenlet 실패한다.
원인은 3가지:

| # | 원인 | 영향 | 해결 전략 |
|---|------|------|----------|
| C-1 | 팩토리가 `session_factory()` 호출 후 close 경로가 없음 | 요청 1회당 커넥션 1~3 개 누수 | 요청 스코프 `Depends(get_db_session)` 통일 |
| C-2 | 동일 UseCase 내 여러 repository가 서로 다른 세션을 사용 | 원자성 붕괴 + 누수 배수 | UseCase당 1 세션으로 공유 |
| C-3 | Repository가 `session.commit()`을 직접 호출 | 트랜잭션 경계 혼재, 풀 반환 전 커밋 누락 | 레포에서 commit 제거, dependency에서 일괄 commit |

### 1-2. 해결 전략 (한 줄 요약)

> **"요청 1건 = AsyncSession 1개 = 트랜잭션 1건"** 원칙을
> FastAPI dependency (`get_db_session`)로 강제하고,
> 모든 use case 팩토리를 해당 dependency에서 세션을 주입받도록 리팩토링한다.
> Repository는 `session.commit()`을 호출하지 않는다.

---

## 2. 세션 수명주기 설계

### 2-1. `get_db_session` dependency 정의 (핵심)

**파일**: `src/infrastructure/persistence/database.py`

**변경 전** (line 55–66):

```python
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()
```

**변경 후**:

```python
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Per-request AsyncSession with automatic commit/rollback.

    - 정상 종료: session.begin() 블록 종료 시 자동 commit
    - 예외 발생: session.begin() 블록이 자동 rollback
    - 어떤 경우에도 session은 async with 블록에서 close → 풀 반환
    """
    factory = get_session_factory()
    async with factory() as session:
        async with session.begin():
            yield session
```

변경 요점:
- `async with session.begin()` 블록으로 **자동 트랜잭션 경계** 보장.
- 기존 `try/finally close()`는 `async with factory()`가 이미 처리하므로 중복 제거.
- 함수명은 `get_session` 유지 (기존 호출부 변경 최소화).
- `settings.database_url`, `pool_size=5/max_overflow=10`은 건드리지 않는다.

### 2-2. 팩토리 패턴 전환 (핵심)

모든 `create_*_use_case_factory` 는 세션을 **스스로 만들지 않고**, FastAPI dependency로
`session: AsyncSession = Depends(get_session)` 을 받아서 repository 를 조립한다.

**패턴 (전후 비교)**:

변경 전 (예: `create_general_chat_use_case_factory`):

```python
async def _factory() -> GeneralChatUseCase:
    session_factory = get_session_factory()
    message_repo = SQLAlchemyConversationMessageRepository(session_factory())  # 세션 A
    summary_repo = SQLAlchemyConversationSummaryRepository(session_factory())  # 세션 B
    ...
    mcp_repo = MCPServerRepository(session=session_factory(), logger=app_logger)  # 세션 C
    ...
```

변경 후:

```python
from fastapi import Depends
from src.infrastructure.persistence.database import get_session

async def _factory(
    session: AsyncSession = Depends(get_session),
) -> GeneralChatUseCase:
    message_repo = SQLAlchemyConversationMessageRepository(session)   # 공유
    summary_repo = SQLAlchemyConversationSummaryRepository(session)   # 공유
    mcp_repo     = MCPServerRepository(session=session, logger=app_logger)  # 공유
    ...
```

**대상 팩토리 (전수)**:

| 파일 | 팩토리 | 현재 세션 개수 | 수정 후 |
|------|-------|----------------|---------|
| `src/api/main.py` | `create_general_chat_use_case_factory` | 3 | 1 (Depends) |
| `src/api/main.py` | `create_conversation_use_case_factory` | 1 (but uncommitted close) | 1 (Depends) |
| `src/api/main.py` | `create_history_use_case_factory` | 1 | 1 (Depends) |
| `src/api/main.py` | `create_auth_factories._make_user_repo` | 1/호출 | 1 (Depends) |
| `src/api/main.py` | `create_auth_factories._make_rt_repo` | 1/호출 | 1 (Depends) |
| `src/api/main.py` | `create_agent_builder_factories._make_repo` | 1/호출 | 1 (Depends) |
| `src/api/main.py` | `create_auto_build_components._make_create_middleware_agent_uc` | 1/호출 | ⚠ 설계 변경 (아래 §2-3) |
| `src/api/main.py` | `create_auth_factories.user_repo_factory` | 1/호출 | 1 (Depends) |

### 2-3. `AutoBuild*` 사용 케이스의 특이점 (lifespan-scoped UC)

`AutoBuildUseCase` / `AutoBuildReplyUseCase` 는 현재 lifespan startup에서
**앱 전체 공유 인스턴스**로 생성된다 (`main.py:746-758`).
이 경로에서 내부적으로 `CreateMiddlewareAgentUseCase` 를 만들고
`MiddlewareAgentRepository(session=get_session_factory()())` 으로 세션을 짠 채 **영구 점유**한다.

**수정 설계**:

- `AutoBuildUseCase` / `AutoBuildReplyUseCase`는 앱 전체 공유를 유지한다 (inference_service, logger는 stateless).
- **다만** 내부에서 `CreateMiddlewareAgentUseCase`를 만들던 로직은 제거하고,
  UC 실행 시점에 외부에서 주입받도록 signature를 변경한다:

```python
# application/auto_agent_builder/auto_build_use_case.py
class AutoBuildUseCase:
    async def execute(
        self,
        request: ...,
        *,
        create_agent_use_case: CreateMiddlewareAgentUseCase,   # ← 매 호출 주입
    ):
        ...
```

- 라우터(`auto_agent_builder_router.py`)에서 `Depends(get_session)` → `CreateMiddlewareAgentUseCase`
  팩토리를 `Depends` 로 해결한 뒤, UC.execute에 kwarg로 전달.
- lifespan 초기화 시 `create_agent_use_case=...` 인자는 제거.

> 이 변경은 설계 원칙상 "UseCase는 자기 의존성을 자체 생성하지 않는다"는 원칙에도 맞다.
> 테스트/리팩토링이 용이해지는 부수효과가 있다.

### 2-4. `conversation_router` / `general_chat_router` 의 Depends 체인

기존 라우터는 이미 `Depends(get_general_chat_use_case)` 를 사용한다.
`app.dependency_overrides[get_general_chat_use_case] = create_general_chat_use_case_factory()` 가
override 대상인 `_factory` 의 signature에 Depends를 갖게 되면, FastAPI는 그 Depends를
**자동으로** 해석하여 `session`을 주입한다.

검증 포인트:
- `app.dependency_overrides` 에 등록된 팩토리 함수의 Depends는 FastAPI가 주입한다.
  (공식 문서: overrides는 그대로 함수이며, 라우트에서 `Depends(X)` 대신 사용되는 대체 함수.)
- 실제로 동일 패턴이 잘 동작함을 확인하기 위해 `tests/integration/test_db_session_lifecycle.py`
  TC-1 (§5-1) 에서 실제 엔드포인트 호출로 검증한다.

---

## 3. Repository 변경 설계

### 3-1. 공통 규칙

> **Repository는 `session.add`, `session.flush`, `session.execute` 만 사용한다.**
> **Repository는 `session.commit()` / `session.rollback()` 을 호출하지 않는다.**

이유: 트랜잭션 경계는 dependency (`get_session` 의 `session.begin()`) 가 책임진다.

### 3-2. `SQLAlchemyConversationMessageRepository.save` 수정

**파일**: `src/infrastructure/persistence/repositories/conversation_repository.py`

변경 전 (line 32–46):

```python
async def save(self, message: ConversationMessage) -> ConversationMessage:
    model = ConversationMessageMapper.to_model(message)
    self._session.add(model)
    await self._session.flush()
    await self._session.commit()        # ← 제거
    await self._session.refresh(model)  # ← 축소 (id만 필요하면 불필요)
    return ConversationMessageMapper.to_entity(model)
```

변경 후:

```python
async def save(self, message: ConversationMessage) -> ConversationMessage:
    model = ConversationMessageMapper.to_model(message)
    self._session.add(model)
    await self._session.flush()   # auto-assigned id 확보까지만
    return ConversationMessageMapper.to_entity(model)
```

> `flush()` 직후 `model.id` 는 채워진다 → `refresh()` 불필요.
> `created_at` 은 DB default 로 찍히지만 `flush` 후 model에 반영되지 않을 수 있다.
> Entity 변환 후 필드가 필요한 소비자가 있다면 `refresh` 유지 (기존 사용처 조사: `GeneralChatUseCase`, `ConversationUseCase` 는 반환 entity의 id만 사용).
> → `refresh` 제거해도 안전.

### 3-3. `UserRepository.save` / `update_status` 수정

**파일**: `src/infrastructure/auth/user_repository.py`

변경 전 (line 38–40, 70):

```python
await self._session.flush()
await self._session.refresh(model)
await self._session.commit()    # ← 제거
...
await self._session.commit()    # ← 제거
```

변경 후: `commit()` 두 줄 모두 삭제.

- `refresh(model)` 은 `UserRepository.save` 에서 **유지**.
  이유: 반환 Entity의 `created_at` / `updated_at` (DB default) 가 소비되는지 확인 필요 →
  RegisterUseCase 구현 확인 후 결정. 1차 설계에서는 **유지** (보수적 선택).

### 3-4. `RefreshTokenRepository` 수정

**파일**: `src/infrastructure/auth/refresh_token_repository.py`

변경 전 (line 25–26, 58):

```python
await self._session.flush()
await self._session.commit()    # ← 제거
...
await self._session.commit()    # ← 제거
```

변경 후: `commit()` 제거.

### 3-5. 다른 Repository는 변경 없음 (이미 규칙 준수)

| 파일 | 현재 상태 | 조치 |
|------|----------|------|
| `conversation_summary_repository.py` | flush만 | 변경 없음 |
| `agent_definition_repository.py` | flush만 | 변경 없음 |
| `middleware_agent_repository.py` | flush만 | 변경 없음 |
| `mysql_base_repository.py` (Generic) | flush만 | 변경 없음 |
| `mcp_server_repository.py` | 확인 필요 (Do 단계에서 grep) | commit 있으면 제거 |

---

## 4. 팩토리 리팩토링 상세 (api/main.py)

### 4-1. `create_general_chat_use_case_factory` (현재 line 892–948)

```python
def create_general_chat_use_case_factory():
    app_logger = get_app_logger()

    async def _factory(
        session: AsyncSession = Depends(get_session),
    ) -> GeneralChatUseCase:
        message_repo = SQLAlchemyConversationMessageRepository(session)
        summary_repo = SQLAlchemyConversationSummaryRepository(session)
        summarizer = LangChainSummarizer(
            model_name=settings.openai_llm_model,
            api_key=settings.openai_api_key,
            logger=app_logger,
        )
        policy = SummarizationPolicy()

        tavily_tool = TavilySearchTool()
        hybrid_search_uc = get_configured_hybrid_search_use_case()
        internal_doc_tool = InternalDocumentSearchTool(
            hybrid_search_use_case=hybrid_search_uc,
            top_k=5,
            request_id="",
        )

        mcp_repo = MCPServerRepository(session=session, logger=app_logger)  # 공유
        mcp_loader = MCPToolLoader(logger=app_logger)
        load_mcp_uc = LoadMCPToolsUseCase(
            repository=mcp_repo,
            mcp_tool_loader=mcp_loader,
            logger=app_logger,
        )

        tool_builder = ChatToolBuilder(
            tavily_tool=tavily_tool,
            internal_doc_tool=internal_doc_tool,
            mcp_cache=MCPToolCache,
            load_mcp_use_case=load_mcp_uc,
            logger=app_logger,
        )

        return GeneralChatUseCase(
            chat_tool_builder=tool_builder,
            message_repo=message_repo,
            summary_repo=summary_repo,
            summarizer=summarizer,
            summarization_policy=policy,
            logger=app_logger,
            openai_api_key=settings.openai_api_key,
            model_name=settings.openai_llm_model,
        )

    return _factory
```

차이: 세션 3개 → 1개, `Depends(get_session)` 주입.

### 4-2. `create_conversation_use_case_factory` (현재 line 395–424)

```python
def create_conversation_use_case_factory():
    app_logger = get_app_logger()

    async def _factory(
        session: AsyncSession = Depends(get_session),
    ) -> ConversationUseCase:
        message_repo = SQLAlchemyConversationMessageRepository(session)
        summary_repo = SQLAlchemyConversationSummaryRepository(session)
        summarizer = LangChainSummarizer(...)
        llm = LangChainConversationLLM(...)
        policy = SummarizationPolicy()
        return ConversationUseCase(
            message_repo=message_repo,
            summary_repo=summary_repo,
            summarizer=summarizer,
            llm=llm,
            policy=policy,
            logger=app_logger,
        )

    return _factory
```

### 4-3. `create_history_use_case_factory` (현재 line 880–889)

```python
def create_history_use_case_factory():
    app_logger = get_app_logger()

    def _factory(
        session: AsyncSession = Depends(get_session),
    ) -> ConversationHistoryUseCase:
        repo = SQLAlchemyConversationMessageRepository(session)
        return ConversationHistoryUseCase(repo=repo, logger=app_logger)

    return _factory
```

### 4-4. `create_auth_factories` (현재 line 781–877)

`_make_user_repo()` / `_make_rt_repo()` 는 **세션 인자를 받도록 변경** 후,
각 factory (register/login/refresh/logout/...) 가 `Depends(get_session)` 을 받아
`_make_user_repo(session)` 형태로 호출한다.

```python
def _make_user_repo(session: AsyncSession):
    return UserRepository(session=session, logger=app_logger)

def _make_rt_repo(session: AsyncSession):
    return RefreshTokenRepository(session=session, logger=app_logger)

def register_factory(session: AsyncSession = Depends(get_session)):
    return RegisterUseCase(
        user_repo=_make_user_repo(session),
        password_hasher=password_hasher,
        logger=app_logger,
    )

def login_factory(session: AsyncSession = Depends(get_session)):
    return LoginUseCase(
        user_repo=_make_user_repo(session),
        refresh_token_repo=_make_rt_repo(session),
        ...
    )
# (refresh/logout/pending/approve/reject/user_repo_factory 동일 패턴)
```

> `user_repo_factory` 는 `get_user_repository` dependency 의 override 이므로 signature에 `Depends(get_session)` 을 써도 FastAPI가 체인 해석한다.

### 4-5. `create_agent_builder_factories` (현재 line 951–1011)

`_make_repo()` 도 세션을 인자로 받는 형태로 변경, 각 factory는 `Depends(get_session)` 주입.

```python
def _make_repo(session: AsyncSession):
    return AgentDefinitionRepository(session=session, logger=app_logger)

def create_uc_factory(session: AsyncSession = Depends(get_session)):
    return CreateAgentUseCase(
        tool_selector=tool_selector,
        prompt_generator=prompt_generator,
        repository=_make_repo(session),
        logger=app_logger,
    )
# (update/run/get/interview 동일)
```

### 4-6. `create_auto_build_components` (현재 line 715–760)

§2-3 설계대로 수정:

```python
def create_auto_build_components():
    """AutoBuildUseCase / AutoBuildReplyUseCase (stateless singletons) + session_repo."""
    # ... redis / inference_service 그대로 ...

    auto_build_uc = AutoBuildUseCase(
        inference_service=inference_service,
        session_repository=session_repo,
        # create_agent_use_case 인자 제거
        logger=app_logger,
    )
    auto_build_reply_uc = AutoBuildReplyUseCase(
        inference_service=inference_service,
        session_repository=session_repo,
        logger=app_logger,
    )
    return auto_build_uc, auto_build_reply_uc, session_repo
```

추가로:

```python
# api/routes/auto_agent_builder_router.py
def get_create_middleware_agent_use_case(
    session: AsyncSession = Depends(get_session),
) -> CreateMiddlewareAgentUseCase:
    return CreateMiddlewareAgentUseCase(
        repository=MiddlewareAgentRepository(session=session),
        logger=get_app_logger(),
    )

# 라우트 핸들러 예시
@router.post("/agents/auto")
async def auto_build(
    request: ...,
    uc: AutoBuildUseCase = Depends(get_auto_build_use_case),
    create_agent_uc: CreateMiddlewareAgentUseCase = Depends(
        get_create_middleware_agent_use_case
    ),
):
    return await uc.execute(request, create_agent_use_case=create_agent_uc)
```

`AutoBuildUseCase.execute(request, *, create_agent_use_case)` signature로 변경.

---

## 5. 테스트 설계

### 5-1. 신규 통합 테스트: `tests/integration/test_db_session_lifecycle.py`

> testcontainers MySQL 또는 `.env` 기반 로컬 MySQL 사용.
> CONV-001 기존 통합 테스트 하네스 재사용.

#### TC-DB-1: 50회 연속 `/api/v1/chat` 후 풀 상태 확인

```python
import asyncio
import httpx

async def test_pool_stable_after_many_chats(test_client, engine):
    """풀 누수 회귀 방지: 50회 호출 후 checkedout == 0."""
    pool = engine.pool
    for i in range(50):
        resp = await test_client.post(
            "/api/v1/chat",
            json={"user_id": "u1", "session_id": f"s-{i}", "message": "ping"},
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert resp.status_code == 200

    # 모든 요청 종료 후 풀 상태
    assert pool.checkedout() == 0
    assert pool.checkedin() <= pool.size() + pool.overflow()
```

#### TC-DB-2: 7턴 이상 대화에서 flush 예외 없이 요약 저장

```python
async def test_summary_persisted_after_seven_turns(test_client, db_session):
    user_id, session_id = "u-sum", "s-sum"
    for i in range(7):
        resp = await test_client.post(
            "/api/v1/chat",
            json={"user_id": user_id, "session_id": session_id, "message": f"msg-{i}"},
        )
        assert resp.status_code == 200

    summaries = await db_session.execute(
        select(ConversationSummaryModel)
        .where(ConversationSummaryModel.user_id == user_id)
        .where(ConversationSummaryModel.session_id == session_id)
    )
    assert len(summaries.scalars().all()) >= 1
```

#### TC-DB-3: UseCase 내부 예외 시 원자성 (partial row 없음)

```python
async def test_rollback_on_use_case_exception(test_client, db_session, monkeypatch):
    # summarizer가 6턴 초과 지점에서 예외를 던지도록 monkeypatch
    from src.infrastructure.conversation.langchain_summarizer import LangChainSummarizer
    monkeypatch.setattr(
        LangChainSummarizer, "summarize",
        AsyncMock(side_effect=RuntimeError("boom")),
    )

    for i in range(6):
        await test_client.post("/api/v1/chat", json={...})

    # 7번째 요청: 요약 분기에서 예외
    resp = await test_client.post("/api/v1/chat", json={...})
    assert resp.status_code == 500

    # 해당 요청의 message/summary는 저장되지 않아야 함
    turn_count = await db_session.scalar(
        select(func.count()).select_from(ConversationMessageModel)
        .where(ConversationMessageModel.session_id == "s-fail")
    )
    assert turn_count == 6  # 7번째 요청의 user/assistant 메시지는 롤백됨
```

### 5-2. 기존 회귀 테스트 영향

| 테스트 파일 | 영향 | 대응 |
|-------------|------|------|
| `tests/application/general_chat/test_use_case.py` | session 직접 의존 없음 (Mock repo) | 변경 없음 |
| `tests/application/conversation/test_use_case.py` | 상동 | 변경 없음 |
| `tests/infrastructure/persistence/test_conversation_repository.py` | `save` 후 commit 여부 assert 있으면 수정 | **verify 필요** |
| `tests/infrastructure/persistence/test_conversation_summary_repository.py` | 무영향 | 변경 없음 |
| `tests/infrastructure/auth/test_user_repository.py` | `save` 후 commit assert 있으면 수정 | **verify 필요** |
| `tests/infrastructure/auth/test_refresh_token_repository.py` | 상동 | **verify 필요** |
| `tests/integration/test_conversation_api.py` | 실제 DB 흐름 통과해야 함 | 풀 고갈 회귀 테스트 추가분만 영향 |
| `tests/application/auto_agent_builder/test_auto_build_use_case.py` | `create_agent_use_case` 생성자 주입 → execute kwarg 주입으로 변경 | **시그니처 수정** |

**시그니처 변경이 발생하는 테스트**:
- `test_auto_build_use_case.py` — `AutoBuildUseCase(..., create_agent_use_case=uc)` → `uc.execute(..., create_agent_use_case=uc)` 로 수정.
- `test_auto_build_reply_use_case.py` — 동일.

---

## 6. 변경 파일 목록

| 파일 | 변경 유형 | 변경 요약 |
|------|-----------|-----------|
| `idt/src/infrastructure/persistence/database.py` | 수정 | `get_session` 에 `async with session.begin()` 추가, close 중복 제거 |
| `idt/src/infrastructure/persistence/repositories/conversation_repository.py` | 수정 | `save()` 의 `commit()` + `refresh()` 제거 |
| `idt/src/infrastructure/auth/user_repository.py` | 수정 | `save()` + `update_status()` 의 `commit()` 제거 |
| `idt/src/infrastructure/auth/refresh_token_repository.py` | 수정 | `save()` + `delete()` 의 `commit()` 제거 |
| `idt/src/api/main.py` | 수정 | 8개 팩토리를 `Depends(get_session)` 기반으로 리팩토링 |
| `idt/src/api/routes/auto_agent_builder_router.py` | 수정 | `CreateMiddlewareAgentUseCase` DI 추가, execute kwarg 전달 |
| `idt/src/application/auto_agent_builder/auto_build_use_case.py` | 수정 | `__init__` 에서 `create_agent_use_case` 제거, `execute(*, create_agent_use_case)` 주입 |
| `idt/src/application/auto_agent_builder/auto_build_reply_use_case.py` | 수정 | 상동 |
| `idt/src/infrastructure/mcp_registry/mcp_server_repository.py` | 조사 후 수정 | `commit()` 존재 여부 확인 → 있으면 제거 |
| `idt/tests/integration/test_db_session_lifecycle.py` | 신규 | TC-DB-1 ~ TC-DB-3 |
| `idt/tests/infrastructure/persistence/test_conversation_repository.py` | 수정 | `commit` 관련 assert 제거 |
| `idt/tests/infrastructure/auth/test_user_repository.py` | 수정 | 상동 |
| `idt/tests/infrastructure/auth/test_refresh_token_repository.py` | 수정 | 상동 |
| `idt/tests/application/auto_agent_builder/test_auto_build_use_case.py` | 수정 | signature 변경 반영 |
| `idt/tests/application/auto_agent_builder/test_auto_build_reply_use_case.py` | 수정 | 상동 |

---

## 7. 구현 순서 (Do Phase 체크리스트)

```
[Red]
 1. tests/integration/test_db_session_lifecycle.py 작성 (TC-DB-1 ~ TC-DB-3)
 2. pytest 실행 → 실패 확인 (풀 고갈 또는 원자성 실패)

[Green - Core]
 3. src/infrastructure/persistence/database.py :: get_session 수정 (§2-1)
 4. src/infrastructure/persistence/repositories/conversation_repository.py :: save() 수정 (§3-2)
 5. src/infrastructure/auth/user_repository.py, refresh_token_repository.py :: commit 제거 (§3-3, §3-4)
 6. 관련 단위 테스트 수정 (§5-2, commit assert 제거)

[Green - Factory Refactor]
 7. src/api/main.py :: create_general_chat_use_case_factory (§4-1)
 8. create_conversation_use_case_factory (§4-2)
 9. create_history_use_case_factory (§4-3)
10. create_auth_factories (§4-4)
11. create_agent_builder_factories (§4-5)
12. auto_build 경로 (§2-3, §4-6)
     - AutoBuildUseCase / AutoBuildReplyUseCase signature 변경
     - auto_agent_builder_router.py 에 CreateMiddlewareAgentUseCase DI 추가
     - lifespan create_auto_build_components 수정
13. mcp_server_repository.py 조사 → commit 있으면 제거

[Green - Integration]
14. pytest tests/integration/test_db_session_lifecycle.py → 3개 TC 통과 확인
15. 기존 회귀 테스트 전체 통과 확인

[Refactor]
16. 중복되는 "Depends(get_session) 후 repo 생성" 패턴이 유의미하면 헬퍼 추출 (선택)
17. verify-architecture / verify-logging / verify-tdd 실행
18. /pdca analyze db-session-leak-fix
```

---

## 8. 리스크 및 완화

| 리스크 | 영향 | 완화 |
|--------|------|------|
| `Depends(get_session)` 가 `app.dependency_overrides` 내 팩토리의 파라미터로 동작하지 않을 가능성 | 높음(설계 무효화) | TC-DB-1 로 실환경 검증. Fallback: 라우터 레벨로 Depends 이동 |
| `session.begin()` 중첩 — Repository 내부에서 다시 `begin_nested()` 호출 시 | 중 | 레포는 `savepoint` 불필요하므로 원칙 문서화 (§3-1). begin 중복 호출 없는지 grep 으로 확인 |
| AutoBuildUseCase 시그니처 변경이 호출처에 전파 | 중 | 1개 라우터, 2개 테스트만 영향 (현재 호출처 확인됨) |
| `refresh()` 제거로 `created_at` 등 Entity 필드가 None 이 되는 소비자 | 낮음 | MessageRepository 는 `id`만 사용. UserRepository 는 보수적으로 refresh 유지 |
| 풀 `checkedout` 카운터가 비동기적으로 감소 → assert 타이밍 이슈 | 낮음 | TC-DB-1 에서 `await asyncio.sleep(0)` 삽입 후 검사 |
| 프론트엔드 API 계약 영향 | 없음 | Request/Response 스키마 미변경 |

---

## 9. 수용 기준 (Design 완료 시점)

- [x] 모든 팩토리에서 세션이 어떻게 주입되는지 명확히 기술
- [x] Repository 의 트랜잭션 책임 제거 경로 정의
- [x] 회귀 방지 테스트 3개 (TC-DB-1~3) 상세 작성
- [x] 변경 파일 목록 전수 나열
- [x] AutoBuild 경로의 예외 설계 명시 (lifespan ↔ request 혼재 해소)
- [x] LOG-001 / 아키텍처 원칙 위반 없음 (domain → infra 참조 없음, print 없음)

---

## 10. 영향 범위 요약

- **DB 스키마**: 변경 없음
- **API 계약**: 변경 없음 (프론트엔드 영향 0)
- **도메인 레이어**: 변경 없음
- **애플리케이션 레이어**: `AutoBuildUseCase.__init__` / `.execute` signature 한정 변경
- **인프라 레이어**: Repository commit 제거, database.py 의 `get_session` 에 `session.begin()` 추가
- **인터페이스 레이어**: `api/main.py` 팩토리 전면 리팩토링, `auto_agent_builder_router.py` DI 추가

---

## 11. 연관 문서

- Plan: `docs/01-plan/features/db-session-leak-fix.plan.md`
- 관련 Task: CONV-001, CHAT-001, AUTH-001, AGENT-004/005/006, MCP-REG-001, MYSQL-001, LOG-001
- 기존 참조 설계: `docs/02-design/features/chat-context-fix.design.md` (DI/테스트 패턴 참조)
