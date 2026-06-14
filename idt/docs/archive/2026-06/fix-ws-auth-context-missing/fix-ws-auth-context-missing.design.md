# fix-ws-auth-context-missing Design Document

> **Summary**: WebSocket(`/ws/agent`, `/ws/chat`)에서 `verify_ws_token`이 `User`까지만 만들고 끝나 system prompt에 사용자 컨텍스트 블록이 누락되는 문제를, 전용 단기 세션 기반 `WsAuthContextResolver`로 `AuthContext`를 조립해 `stream(auth_ctx=...)`에 전달하도록 수정 (실패 시 fail-closed).
>
> **Project**: sangplusbot (idt)
> **Author**: AI Assistant
> **Date**: 2026-06-01
> **Status**: Draft
> **Planning Doc**: [fix-ws-auth-context-missing.plan.md](../../01-plan/features/fix-ws-auth-context-missing.plan.md)

---

## 1. Overview

### 1.1 Design Goals

- WS 두 엔드포인트(`ws_agent_run`, `ws_chat`)가 `AuthContext`를 조립해 `stream(auth_ctx=...)`로 전달
- `viewer_department_ids=[]` 하드코딩을 `list(auth_ctx.department_ids)`로 교체
- AuthContext 조립은 **전용 단기 세션**으로 수행 — 장시간 WS 스트리밍 동안 DB 세션 점유 금지
- 조립 실패 시 **fail-closed**: `AuthContext.public_anonymous()`로 degrade, WS 연결은 유지
- HTTP/SSE 경로(`get_auth_context*`) 동작·계약 불변

### 1.2 Design Principles

- 최소 변경 + 기존 자산 재사용: 조립 로직은 기존 `AssembleAuthContextUseCase`를 그대로 호출
- DDD 레이어 준수: 조립 wiring은 composition root(`main.py`)에 둠. application은 infrastructure repo를 직접 import하지 않음 (`session→UseCase` 빌더를 주입받음)
- CLAUDE.md §6 준수: 팩토리에서 `get_session_factory()()` 직접 호출 금지 → `session_factory`를 주입받아 `async with`로 단기 사용
- 과도한 추상화 회피: 신규 클래스는 `WsAuthContextResolver` 1개로 한정

---

## 2. Architecture

### 2.1 영향 레이어

```
domain/          → 변경 없음 (AuthContext.public_anonymous 기존 활용)
application/     → 변경 대상 (WsAuthContextResolver 신규 — 조립 + 단기 세션 캡슐화)
infrastructure/  → 변경 없음 (기존 repo 재사용, websocket/auth.py 그대로)
interfaces/      → 변경 대상 (api/routes/ws_router.py, api/main.py wiring)
```

### 2.2 변경 흐름 (Before → After)

**Before (현재 — 사용자 블록 누락)**:
```
ws_agent_run / ws_chat
  └─ user = verify_ws_token(...)            # User 까지만
  └─ use_case.stream(... viewer_department_ids=[])   # auth_ctx 미전달 → None
       └─ render_user_context_block(None) → ""        # 사용자 블록 누락
       └─ set_current_auth_context 미호출 → 권한 Tool 무력화
```

**After (수정 후)**:
```
ws_agent_run / ws_chat
  └─ user = verify_ws_token(...)
  └─ auth_ctx = await _resolve_ws_auth_ctx(user, resolver, logger)   # 단기 세션 조립, 실패 시 anonymous
  └─ use_case.stream(
        ... auth_ctx=auth_ctx,
            viewer_department_ids=list(auth_ctx.department_ids))
       └─ render_user_context_block(auth_ctx) → [현재 사용자 정보] 블록
       └─ set_current_auth_context(auth_ctx) → 권한 Tool 정상
```

### 2.3 SSE 경로와의 정합

| 경로 | AuthContext 출처 | 세션 수명 |
|------|------------------|-----------|
| SSE `/run/stream` | `Depends(get_auth_context_from_query_token)` → request-scoped session | request 수명 (SSE도 길지만 기존 동작 유지) |
| **WS (신규)** | `WsAuthContextResolver.execute(user)` → **단기 세션 (조립 후 즉시 반환)** | 조립 1회뿐 |

> WS는 연결 수명이 더 길고 동시 연결이 많을 수 있어 request-scoped 세션 점유를 피하는 단기 세션 방식을 채택 (Plan §3 결정).

---

## 3. Detailed Design

### 3.1 File: `src/application/agent_run/ws_auth_context.py` (신규)

WS 전용 AuthContext 조립기. 단기 세션을 `async with`로 열어 1회 조립 후 닫는다.
infrastructure repo를 직접 import하지 않고, `session → AssembleAuthContextUseCase` 빌더를 주입받는다 (레이어 규칙).

```python
"""WsAuthContextResolver — WebSocket 전용 AuthContext 조립기.

fix-ws-auth-context-missing Design §3.1:
- WS 연결은 스트리밍 동안 장시간 유지되므로, request-scoped 세션을 점유하지 않도록
  조립 시점에만 단기 세션을 연다 (CLAUDE.md §6: session_factory 주입, async with 사용).
- infra repo를 직접 import하지 않고 session→UseCase 빌더를 주입받아 레이어 규칙 준수.
"""
from typing import Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.application.permission.assemble_auth_context import (
    AssembleAuthContextUseCase,
)
from src.domain.agent_run.auth_context import AuthContext
from src.domain.auth.entities import User


class WsAuthContextResolver:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        assemble_uc_builder: Callable[[AsyncSession], AssembleAuthContextUseCase],
    ) -> None:
        self._session_factory = session_factory
        self._assemble_uc_builder = assemble_uc_builder

    async def execute(self, user: User, request_id: str) -> AuthContext:
        """단기 세션으로 AuthContext 조립 (예외는 호출자가 fail-closed 처리)."""
        async with self._session_factory() as session:
            uc = self._assemble_uc_builder(session)
            return await uc.execute(user, request_id)
```

> `execute()`는 예외를 그대로 전파한다 (단일 책임). fail-closed 처리는 §3.2의 라우터 헬퍼가 담당.

### 3.2 File: `src/api/routes/ws_router.py`

#### 3.2.1 DI placeholder 추가 (기존 placeholder 패턴과 동일)

```python
from src.application.agent_run.ws_auth_context import WsAuthContextResolver
from src.domain.agent_run.auth_context import AuthContext
from src.domain.logging.interfaces.logger_interface import LoggerInterface


def get_ws_auth_context_resolver() -> WsAuthContextResolver:
    raise NotImplementedError("WsAuthContextResolver not initialized")


def get_ws_logger() -> LoggerInterface:
    raise NotImplementedError("WS logger not initialized")
```

#### 3.2.2 fail-closed 헬퍼 (모듈 레벨)

```python
async def _resolve_ws_auth_ctx(
    user, resolver: WsAuthContextResolver, logger: LoggerInterface,
) -> AuthContext:
    """User → AuthContext. 조립 실패 시 anonymous로 degrade (fail-closed)."""
    request_id = str(uuid.uuid4())
    try:
        return await resolver.execute(user, request_id)
    except Exception as e:
        logger.error(
            "WS AuthContext assembly failed — degrading to anonymous",
            exception=e, request_id=request_id,
        )
        return AuthContext.public_anonymous()
```

(`import uuid` 추가 필요.)

#### 3.2.3 `ws_agent_run` 수정

시그니처에 resolver/logger 주입 추가, `verify_ws_token` 직후 조립, stream 호출 인자 변경:

```python
@router.websocket("/ws/agent/{run_id}")
async def ws_agent_run(
    websocket: WebSocket,
    run_id: str,
    manager: ConnectionManagerInterface = Depends(get_connection_manager),
    jwt_adapter: JWTAdapterInterface = Depends(get_ws_jwt_adapter),
    user_repo: UserRepositoryInterface = Depends(get_ws_user_repository),
    use_case: RunAgentUseCase = Depends(get_ws_run_agent_use_case),
    auth_resolver: WsAuthContextResolver = Depends(get_ws_auth_context_resolver),
    logger: LoggerInterface = Depends(get_ws_logger),
):
    user = await verify_ws_token(websocket, jwt_adapter, user_repo)
    if not user:
        return
    auth_ctx = await _resolve_ws_auth_ctx(user, auth_resolver, logger)

    await manager.connect(websocket, user.id, room_id=run_id)
    ...
        async for event in use_case.stream(
            agent_id=sub.agent_id,
            request=request,
            request_id=run_id,
            viewer_user_id=str(user.id),
            viewer_department_ids=list(auth_ctx.department_ids),   # [] → 실제 부서
            auth_ctx=auth_ctx,                                     # 신규
        ):
```

기존 145-146번 줄 "auth_ctx not plumbed through WS … deferred" 주석은 제거.

#### 3.2.4 `ws_chat` 수정

```python
@router.websocket("/ws/chat/{session_id}")
async def ws_chat(
    websocket: WebSocket,
    session_id: str,
    ...
    use_case: GeneralChatUseCase = Depends(get_ws_general_chat_use_case),
    cache: ChatStreamCacheInterface = Depends(get_chat_stream_cache),
    auth_resolver: WsAuthContextResolver = Depends(get_ws_auth_context_resolver),
    logger: LoggerInterface = Depends(get_ws_logger),
):
    user = await verify_ws_token(websocket, jwt_adapter, user_repo)
    if not user:
        return
    auth_ctx = await _resolve_ws_auth_ctx(user, auth_resolver, logger)
    ...
        async for event in use_case.stream(
            request, request_id=session_id, auth_ctx=auth_ctx,   # 신규
        ):
```

> 조립은 replay 루프(`cache.replay`)보다 먼저/직후 어디서 해도 무방하나, `verify_ws_token` 직후로 통일해 두 엔드포인트 동일 패턴 유지.

### 3.3 File: `src/api/main.py`

#### 3.3.1 WS 조립 팩토리 (단기 세션 기반)

기존 `create_auth_context_factories`의 repo 빌더(`UserProfileRepository`/`DepartmentRepository`/`PermissionRepository`)를 재사용해 `assemble_uc_builder`를 만들고, `get_session_factory()`를 주입한다.

```python
def create_ws_auth_context_resolver() -> WsAuthContextResolver:
    """WS 전용 AuthContext 조립기 (단기 세션). agent-user-context + fix-ws-auth-context-missing.

    DB-001 §10.2: session_factory 주입, resolver.execute() 내부 async with로 단기 사용.
    """
    app_logger = get_app_logger()

    def _assemble_uc_builder(session: AsyncSession) -> AssembleAuthContextUseCase:
        return AssembleAuthContextUseCase(
            profile_repo=UserProfileRepository(session=session, logger=app_logger),
            department_repo=DepartmentRepository(session=session, logger=app_logger),
            permission_repo=PermissionRepository(session=session, logger=app_logger),
            logger=app_logger,
        )

    return WsAuthContextResolver(
        session_factory=get_session_factory(),
        assemble_uc_builder=_assemble_uc_builder,
    )
```

#### 3.3.2 WebSocket DI 블록 override 등록 (`main.py:2401-2415` 영역)

```python
# WebSocket DI (기존)
...
app.dependency_overrides[get_ws_run_agent_use_case] = _run_uc
# fix-ws-auth-context-missing: WS AuthContext 조립기 + logger
_ws_auth_resolver = create_ws_auth_context_resolver()
app.dependency_overrides[get_ws_auth_context_resolver] = lambda: _ws_auth_resolver
app.dependency_overrides[get_ws_logger] = lambda: logger
```

(`logger`는 해당 함수 스코프에서 이미 사용 중인 app logger 인스턴스. import에 `get_ws_auth_context_resolver`, `get_ws_logger`, `WsAuthContextResolver` 추가.)

### 3.4 Test Changes

#### 3.4.1 `tests/api/test_ws_router_auth_context.py` (신규)

`FakeResolver`(`execute` 구현) + `RunAgentUseCase`/`GeneralChatUseCase` mock으로 stream 호출 인자를 검증한다. (Windows event loop 이슈 → 격리 실행)

| 테스트 | 검증 |
|--------|------|
| `test_ws_agent_run_passes_auth_context` | `use_case.stream` 호출 kwargs에 `auth_ctx`(role/부서/권한) 존재 + `viewer_department_ids == list(auth_ctx.department_ids)` |
| `test_ws_chat_passes_auth_context` | `GeneralChatUseCase.stream` 호출 kwargs에 `auth_ctx` 존재 |
| `test_ws_auth_assembly_failure_degrades_anonymous` | resolver.execute가 raise → stream에 `permissions==frozenset()` anonymous 전달, `websocket.close(AUTH_FAILED)` 미호출 |

#### 3.4.2 `tests/application/agent_run/test_ws_auth_context.py` (신규)

| 테스트 | 검증 |
|--------|------|
| `test_resolver_opens_and_closes_short_session` | `execute()`가 session_factory()를 1회 열고 닫음 (context manager 호출 검증) |
| `test_resolver_returns_assembled_context` | builder가 만든 UC.execute 결과 AuthContext를 그대로 반환 |
| `test_resolver_propagates_exception` | UC.execute 예외를 전파 (fail-closed는 라우터 책임) |

---

## 4. Implementation Order

```
Step 1: 테스트 작성 (RED, 격리 실행)
  ├─ tests/application/agent_run/test_ws_auth_context.py
  └─ tests/api/test_ws_router_auth_context.py

Step 2: application — WsAuthContextResolver
  └─ src/application/agent_run/ws_auth_context.py (신규)

Step 3: interfaces — ws_router.py
  ├─ DI placeholder 2개 + _resolve_ws_auth_ctx 헬퍼 (+import uuid)
  ├─ ws_agent_run: auth_ctx 조립·전달, viewer_department_ids 교체, deferred 주석 제거
  └─ ws_chat: auth_ctx 전달

Step 4: composition root — main.py
  ├─ create_ws_auth_context_resolver()
  └─ WebSocket DI 블록에 override 2개 등록

Step 5: 테스트 GREEN (격리 실행) → 로컬 dev 수동 검증 (실제 화면 채팅 → 사용자 블록 진입)
```

---

## 5. Risk & Mitigation

| 리스크 | 심각도 | 대응 |
|--------|--------|------|
| 단기 세션 조립 추가로 WS 연결 latency 증가 | Low | DB 3 round-trip 1회뿐, 스트림 시작 직전. SSE와 동일 비용 |
| `WsAuthContextResolver` 세션 누수 | Low | `async with session_factory()`로 컨텍스트 종료 시 자동 close. 테스트 3.4.2로 검증 |
| 조립 실패 시 사용자가 권한 답변 못 받음 | Medium | fail-closed 정책상 의도된 동작 — anonymous로 안전 degrade, 로그로 추적 |
| WebSocket에서 `Depends` 주입 동작 | Low | 기존 ws_router가 이미 `Depends`로 manager/jwt 등 주입 중 — 동일 패턴 |
| `main.py`의 `logger` 변수 스코프 | Low | WS DI 블록은 이미 `logger`(ConnectionManager에 전달) 사용 중 — 재사용 |
| anonymous도 `set_current_auth_context` 호출 여부 | Low | 범위 외(Plan §8). 현 동작 유지 — anonymous면 블록 빈 문자열로 기존과 동일하게 안전 |

---

## 6. Acceptance Criteria

- [ ] `ws_agent_run`이 `auth_ctx` + `viewer_department_ids=list(auth_ctx.department_ids)`를 `stream`에 전달
- [ ] `ws_chat`이 `auth_ctx`를 `stream`에 전달
- [ ] `WsAuthContextResolver`가 단기 세션을 열고 닫으며 AuthContext 조립
- [ ] 조립 실패 시 anonymous로 degrade하고 WS 연결은 유지 (fail-closed)
- [ ] `main.py` WS DI에 resolver/logger override 등록
- [ ] HTTP `/run`, SSE `/run/stream` 동작·시그니처 불변
- [ ] `domain/` 무변경, application이 infra repo를 직접 import하지 않음 (레이어 규칙)
- [ ] 신규/기존 테스트 통과 (격리 실행), `render_user_context_block`이 실제 사용자 블록 생성 확인
- [ ] `ws_router.py`의 "deferred" 주석 제거
