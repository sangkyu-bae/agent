# WebSocket Common Module Design Document

> **Summary**: 백엔드 공통 WebSocket 인프라 — ConnectionManager, 메시지 프로토콜, JWT 토큰 인증, 피처별 핸들러 확장 구조
>
> **Project**: sangplusbot (idt)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-05-15
> **Status**: Draft
> **Planning Doc**: [websocket-common-module.plan.md](../01-plan/features/websocket-common-module.plan.md)

---

## 1. Overview

### 1.1 Design Goals

1. **범용성**: Agent 스트리밍, RAG 채팅, 문서 처리 등 다양한 피처에서 핸들러만 추가하면 사용 가능한 구조
2. **DDD 준수**: domain(스키마/인터페이스) → infrastructure(구현체) → api(라우터) 레이어 분리
3. **기존 인증 재사용**: `JWTAdapterInterface`를 그대로 활용한 쿼리 파라미터 토큰 검증
4. **프론트엔드 호환**: `useWebSocket` 훅의 `WebSocketMessage { type, data, ... }` 구조와 일치하는 메시지 프로토콜

### 1.2 Design Principles

- DDD 레이어 의존성 규칙 (domain은 외부 의존성 없음)
- 기존 DI 패턴 유지 (lifespan 싱글턴 + dependency_overrides)
- StructuredLogger를 통한 일관된 로깅
- Pydantic 기반 타입 안전 메시지 스키마

---

## 2. Architecture

### 2.1 Component Diagram

```
┌──────────────────┐          ┌──────────────────────────────────┐
│  Frontend        │          │  Backend (FastAPI)                │
│  (useWebSocket)  │          │                                  │
│                  │  ws://   │  ┌───────────────────────┐       │
│  connect(url)    │─────────▶│  │   ws_router.py        │       │
│  send(msg)       │◀─────────│  │   (api/routes/)       │       │
│  onMessage(cb)   │          │  │                       │       │
└──────────────────┘          │  │  ┌─ ws_auth ──────┐   │       │
                              │  │  │ verify_token() │   │       │
                              │  │  └────────────────┘   │       │
                              │  │         │             │       │
                              │  │         ▼             │       │
                              │  │  ┌─ ConnectionMgr ─┐  │       │
                              │  │  │ connect()       │  │       │
                              │  │  │ disconnect()    │  │       │
                              │  │  │ send_personal() │  │       │
                              │  │  │ send_to_room()  │  │       │
                              │  │  │ broadcast()     │  │       │
                              │  │  └─────────────────┘  │       │
                              │  └───────────────────────┘       │
                              └──────────────────────────────────┘
```

### 2.2 Data Flow

```
1. Client: ws://host/ws/echo?token=eyJ...
2. ws_router: 쿼리 파라미터에서 token 추출
3. ws_auth.verify_ws_token(token, jwt_adapter) → User | close(4001)
4. ConnectionManager.connect(ws, user_id, room_id)
5. Loop: receive → handler(message) → send response
6. Disconnect: ConnectionManager.disconnect(ws, user_id, room_id)
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `ws_router` | `ConnectionManager`, `ws_auth` | WebSocket 엔드포인트, 라우팅 |
| `ws_auth` | `JWTAdapterInterface`, `UserRepositoryInterface` | 토큰 검증, 사용자 조회 |
| `ConnectionManager` | `LoggerInterface` | 연결 관리, 로깅 |
| `domain/websocket/schemas` | (없음 - 순수 도메인) | 메시지 타입 정의 |

---

## 3. Data Model

### 3.1 메시지 스키마 (domain/websocket/schemas.py)

```python
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class WSMessageType(str, Enum):
    # 시스템 메시지
    PING = "ping"
    PONG = "pong"
    ERROR = "error"
    CONNECTED = "connected"

    # 피처별 메시지 (확장 시 추가)
    AGENT_STEP = "agent_step"
    AGENT_DONE = "agent_done"
    CHAT_TOKEN = "chat_token"
    CHAT_DONE = "chat_done"
    INGEST_PROGRESS = "ingest_progress"
    INGEST_DONE = "ingest_done"


class WSMessage(BaseModel):
    type: str
    data: Any = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[dict[str, Any]] = None


class WSErrorData(BaseModel):
    code: str
    message: str


class WSErrorMessage(WSMessage):
    type: str = "error"
    data: WSErrorData
```

### 3.2 연결 정보 (domain/websocket/schemas.py)

```python
@dataclass(frozen=True)
class WSConnection:
    user_id: int
    room_id: Optional[str] = None
    connected_at: datetime = field(default_factory=datetime.utcnow)
```

### 3.3 WS Close 코드 (domain/websocket/schemas.py)

```python
class WSCloseCode:
    NORMAL = 1000
    AUTH_FAILED = 4001
    FORBIDDEN = 4002
    NOT_FOUND = 4003
    RATE_LIMITED = 4004
    INTERNAL_ERROR = 4500
```

---

## 4. API Specification

### 4.1 WebSocket Endpoint List

| Path | Description | Auth | Room |
|------|-------------|------|------|
| `ws://host/ws/echo?token=xxx` | 연결 테스트용 에코 핸들러 | Required | 없음 |

> 피처별 엔드포인트(agent, chat, ingest)는 이 모듈 위에 별도 라우터로 추가 예정

### 4.2 Echo Endpoint 상세

**연결:**
```
ws://localhost:8000/ws/echo?token=eyJhbGciOiJIUzI1NiIs...
```

**인증 성공 시 서버 → 클라이언트:**
```json
{
  "type": "connected",
  "data": { "user_id": 1, "message": "WebSocket connected" },
  "timestamp": "2026-05-15T10:30:00Z"
}
```

**클라이언트 → 서버 (아무 메시지):**
```json
{ "type": "chat_message", "data": { "text": "hello" } }
```

**서버 → 클라이언트 (에코 응답):**
```json
{
  "type": "echo",
  "data": { "original": { "type": "chat_message", "data": { "text": "hello" } } },
  "timestamp": "2026-05-15T10:30:01Z"
}
```

**인증 실패 시:**
```
WebSocket close(code=4001, reason="Invalid or expired token")
```

### 4.3 메시지 프로토콜 규격

**서버 → 클라이언트 (envelope):**
```json
{
  "type": "string (snake_case)",
  "data": "any | null",
  "timestamp": "ISO 8601 UTC",
  "metadata": { "room_id": "string?", "seq": "int?" }
}
```

**클라이언트 → 서버:**
```json
{
  "type": "string (snake_case)",
  "data": "any | null"
}
```

> 프론트엔드 `WebSocketMessage` 인터페이스(`{ type: string, data?: unknown, [key: string]: unknown }`)와 상위 호환

---

## 5. Domain Layer Design

### 5.1 domain/websocket/schemas.py

| 클래스 | 유형 | 역할 |
|--------|------|------|
| `WSMessageType` | Enum | 메시지 type 필드의 표준 값 정의 |
| `WSMessage` | Pydantic BaseModel | 서버↔클라이언트 공통 메시지 envelope |
| `WSErrorData` | Pydantic BaseModel | 에러 메시지 data 필드 구조 |
| `WSErrorMessage` | Pydantic BaseModel | 에러 전용 메시지 (type="error" 고정) |
| `WSConnection` | dataclass (frozen) | 연결 메타데이터 VO |
| `WSCloseCode` | 상수 클래스 | WebSocket close 코드 표준 값 |

### 5.2 domain/websocket/interfaces.py

```python
from abc import ABC, abstractmethod
from typing import Any, Optional

from fastapi import WebSocket


class ConnectionManagerInterface(ABC):
    @abstractmethod
    async def connect(
        self, websocket: WebSocket, user_id: int, room_id: Optional[str] = None
    ) -> None: ...

    @abstractmethod
    async def disconnect(
        self, websocket: WebSocket, user_id: int, room_id: Optional[str] = None
    ) -> None: ...

    @abstractmethod
    async def send_personal(
        self, websocket: WebSocket, message: dict[str, Any]
    ) -> None: ...

    @abstractmethod
    async def send_to_room(
        self, room_id: str, message: dict[str, Any]
    ) -> None: ...

    @abstractmethod
    async def broadcast(
        self, message: dict[str, Any]
    ) -> None: ...

    @abstractmethod
    def get_connection_count(self) -> int: ...

    @abstractmethod
    def get_room_count(self, room_id: str) -> int: ...
```

> **주의**: `fastapi.WebSocket`을 domain에서 참조하는 것은 레이어 위반 가능성이 있으나, WebSocket은 Python 표준 프로토콜 객체의 래퍼이고 ABC 시그니처에만 사용하므로 실용적 타협으로 허용한다. 대안으로 `Any` 타입을 쓸 수 있으나 타입 안전성이 떨어진다.

---

## 6. Infrastructure Layer Design

### 6.1 infrastructure/websocket/connection_manager.py

```python
class ConnectionManager(ConnectionManagerInterface):
    def __init__(self, logger: LoggerInterface, max_connections: int = 100) -> None:
        self._active: dict[WebSocket, WSConnection] = {}
        self._rooms: dict[str, set[WebSocket]] = defaultdict(set)
        self._logger = logger
        self._max_connections = max_connections

    async def connect(self, websocket: WebSocket, user_id: int, room_id: str | None = None) -> None:
        if len(self._active) >= self._max_connections:
            await websocket.close(code=WSCloseCode.RATE_LIMITED, reason="Max connections reached")
            return
        await websocket.accept()
        self._active[websocket] = WSConnection(user_id=user_id, room_id=room_id)
        if room_id:
            self._rooms[room_id].add(websocket)
        self._logger.info("ws_connected", user_id=user_id, room_id=room_id,
                          total=len(self._active))

    async def disconnect(self, websocket: WebSocket, user_id: int, room_id: str | None = None) -> None:
        self._active.pop(websocket, None)
        if room_id and room_id in self._rooms:
            self._rooms[room_id].discard(websocket)
            if not self._rooms[room_id]:
                del self._rooms[room_id]
        self._logger.info("ws_disconnected", user_id=user_id, room_id=room_id,
                          total=len(self._active))

    async def send_personal(self, websocket: WebSocket, message: dict[str, Any]) -> None:
        await websocket.send_json(message)

    async def send_to_room(self, room_id: str, message: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for ws in self._rooms.get(room_id, set()):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            conn = self._active.get(ws)
            if conn:
                await self.disconnect(ws, conn.user_id, room_id)

    async def broadcast(self, message: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for ws in list(self._active.keys()):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            conn = self._active.get(ws)
            if conn:
                await self.disconnect(ws, conn.user_id, conn.room_id)

    def get_connection_count(self) -> int:
        return len(self._active)

    def get_room_count(self, room_id: str) -> int:
        return len(self._rooms.get(room_id, set()))
```

### 6.2 infrastructure/websocket/auth.py

```python
from typing import Optional

from fastapi import WebSocket

from src.domain.auth.entities import User
from src.domain.auth.interfaces import JWTAdapterInterface, UserRepositoryInterface
from src.domain.websocket.schemas import WSCloseCode


async def verify_ws_token(
    websocket: WebSocket,
    jwt_adapter: JWTAdapterInterface,
    user_repo: UserRepositoryInterface,
) -> Optional[User]:
    """쿼리 파라미터 token에서 JWT를 검증하고 User를 반환한다.

    검증 실패 시 WebSocket을 close하고 None을 반환한다.
    """
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=WSCloseCode.AUTH_FAILED, reason="Token required")
        return None

    try:
        payload = jwt_adapter.decode(token)
    except ValueError:
        await websocket.close(code=WSCloseCode.AUTH_FAILED, reason="Invalid or expired token")
        return None

    if payload.token_type != "access":
        await websocket.close(code=WSCloseCode.AUTH_FAILED, reason="Invalid token type")
        return None

    user = await user_repo.find_by_id(int(payload.sub))
    if not user:
        await websocket.close(code=WSCloseCode.AUTH_FAILED, reason="User not found")
        return None

    return user
```

---

## 7. API Layer Design

### 7.1 api/routes/ws_router.py

```python
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from src.domain.auth.interfaces import JWTAdapterInterface, UserRepositoryInterface
from src.domain.websocket.interfaces import ConnectionManagerInterface
from src.domain.websocket.schemas import WSMessage
from src.infrastructure.websocket.auth import verify_ws_token

router = APIRouter(tags=["websocket"])


def get_connection_manager() -> ConnectionManagerInterface:
    raise NotImplementedError("ConnectionManager not initialized")


def get_ws_jwt_adapter() -> JWTAdapterInterface:
    raise NotImplementedError("JWTAdapter not initialized")


def get_ws_user_repository() -> UserRepositoryInterface:
    raise NotImplementedError("UserRepository not initialized")


@router.websocket("/ws/echo")
async def ws_echo(
    websocket: WebSocket,
    manager: ConnectionManagerInterface = Depends(get_connection_manager),
    jwt_adapter: JWTAdapterInterface = Depends(get_ws_jwt_adapter),
    user_repo: UserRepositoryInterface = Depends(get_ws_user_repository),
):
    user = await verify_ws_token(websocket, jwt_adapter, user_repo)
    if not user:
        return

    await manager.connect(websocket, user.id)
    try:
        connected_msg = WSMessage(
            type="connected",
            data={"user_id": user.id, "message": "WebSocket connected"},
        )
        await manager.send_personal(websocket, connected_msg.model_dump(mode="json"))

        while True:
            raw = await websocket.receive_json()
            echo_msg = WSMessage(type="echo", data={"original": raw})
            await manager.send_personal(websocket, echo_msg.model_dump(mode="json"))

    except WebSocketDisconnect:
        await manager.disconnect(websocket, user.id)
    except Exception as e:
        error_msg = WSMessage(
            type="error",
            data={"code": "INTERNAL_ERROR", "message": str(e)},
        )
        try:
            await manager.send_personal(websocket, error_msg.model_dump(mode="json"))
        except Exception:
            pass
        await manager.disconnect(websocket, user.id)
```

### 7.2 DI 등록 (api/main.py 수정)

```python
# lifespan 내부에 추가:
_connection_manager = ConnectionManager(logger=app_logger, max_connections=100)

# create_app() 내부에 추가:
from src.api.routes.ws_router import (
    router as ws_router,
    get_connection_manager,
    get_ws_jwt_adapter,
    get_ws_user_repository,
)

app.include_router(ws_router)
app.dependency_overrides[get_connection_manager] = lambda: _connection_manager
# get_ws_jwt_adapter, get_ws_user_repository는 기존 auth DI의 _jwt_f, _user_repo_f 재사용
app.dependency_overrides[get_ws_jwt_adapter] = _jwt_f
app.dependency_overrides[get_ws_user_repository] = _user_repo_f
```

---

## 8. Error Handling

### 8.1 WebSocket Close Code 정의

| Code | 의미 | 발생 조건 |
|------|------|----------|
| 1000 | 정상 종료 | 클라이언트/서버 정상 종료 |
| 4001 | 인증 실패 | 토큰 없음/만료/위변조/타입 불일치/유저 없음 |
| 4002 | 권한 부족 | role 검증 실패 (향후 확장) |
| 4003 | 리소스 없음 | room/agent/session 없음 (향후 확장) |
| 4004 | 속도 제한 | 최대 연결 수 초과 |
| 4500 | 서버 내부 오류 | 예기치 못한 서버 에러 |

### 8.2 에러 메시지 형식

```json
{
  "type": "error",
  "data": {
    "code": "AUTH_FAILED | FORBIDDEN | NOT_FOUND | RATE_LIMITED | INTERNAL_ERROR",
    "message": "Human-readable description"
  },
  "timestamp": "2026-05-15T10:30:00Z"
}
```

---

## 9. Security Considerations

- [x] JWT 토큰 검증: 기존 `JWTAdapterInterface.decode()` 재사용
- [x] 토큰 타입 검증: `access` 토큰만 허용
- [x] 사용자 존재 확인: DB 조회 후 연결 허용
- [x] 최대 연결 수 제한: `max_connections` 설정으로 DoS 방어
- [x] 에러 시 안전한 연결 해제: try/except로 리소스 정리 보장
- [ ] 토큰 재검증 (Heartbeat 시): 첫 버전에서는 연결 시 1회만 검증 (향후 확장)

---

## 10. Test Plan

### 10.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit Test | `ConnectionManager` (connect/disconnect/send/room) | pytest |
| Unit Test | `verify_ws_token` (성공/실패 케이스) | pytest + mock |
| Unit Test | `WSMessage` 직렬화/역직렬화 | pytest |
| Integration Test | Echo 엔드포인트 연결→메시지→응답 | pytest + httpx WebSocket |

### 10.2 Test Cases

- [ ] **CM-01**: connect → 연결 카운트 증가 확인
- [ ] **CM-02**: disconnect → 연결 카운트 감소, room에서 제거 확인
- [ ] **CM-03**: send_to_room → 같은 room의 연결에만 전송 확인
- [ ] **CM-04**: broadcast → 모든 활성 연결에 전송 확인
- [ ] **CM-05**: max_connections 초과 시 close(4004) 확인
- [ ] **CM-06**: dead connection 발생 시 자동 정리 확인
- [ ] **AUTH-01**: 유효한 토큰 → User 반환 확인
- [ ] **AUTH-02**: 토큰 없음 → close(4001) 확인
- [ ] **AUTH-03**: 만료된 토큰 → close(4001) 확인
- [ ] **AUTH-04**: refresh 토큰 사용 시 → close(4001) 확인
- [ ] **AUTH-05**: 존재하지 않는 user_id → close(4001) 확인
- [ ] **MSG-01**: WSMessage 직렬화 → JSON 형식 검증
- [ ] **MSG-02**: WSErrorMessage → type="error" 고정 확인
- [ ] **ECHO-01**: echo 엔드포인트 연결 → "connected" 메시지 수신 확인
- [ ] **ECHO-02**: 메시지 전송 → 에코 응답 수신 확인

---

## 11. Clean Architecture Layer Assignment

### 11.1 Layer Structure

| Layer | Responsibility | Location |
|-------|---------------|----------|
| **Domain** | 메시지 스키마(VO), ConnectionManager 인터페이스(ABC), Close 코드 상수 | `src/domain/websocket/` |
| **Infrastructure** | ConnectionManager 구현체, WS 토큰 인증 헬퍼 | `src/infrastructure/websocket/` |
| **API (Interfaces)** | WebSocket 라우터, DI placeholder 함수 | `src/api/routes/ws_router.py` |

### 11.2 Dependency Rules 검증

```
ws_router (API) ──imports──→ ConnectionManagerInterface (Domain) ✅
ws_router (API) ──imports──→ verify_ws_token (Infrastructure)    ✅
ws_router (API) ──imports──→ WSMessage (Domain)                  ✅

ConnectionManager (Infra) ──imports──→ ConnectionManagerInterface (Domain)  ✅
ConnectionManager (Infra) ──imports──→ WSConnection, WSCloseCode (Domain)   ✅
ConnectionManager (Infra) ──imports──→ LoggerInterface (Domain)             ✅

verify_ws_token (Infra) ──imports──→ JWTAdapterInterface (Domain)  ✅
verify_ws_token (Infra) ──imports──→ User (Domain)                 ✅
verify_ws_token (Infra) ──imports──→ WSCloseCode (Domain)          ✅

Domain ──imports──→ (외부 의존성 없음, pydantic만 사용)  ✅
```

### 11.3 File Structure

```
src/
├── domain/websocket/
│   ├── __init__.py
│   ├── schemas.py           # WSMessage, WSErrorMessage, WSConnection, WSCloseCode, WSMessageType
│   └── interfaces.py        # ConnectionManagerInterface (ABC)
├── infrastructure/websocket/
│   ├── __init__.py
│   ├── connection_manager.py # ConnectionManager 구현체
│   └── auth.py              # verify_ws_token 함수
└── api/routes/
    └── ws_router.py          # WebSocket 라우터 + echo 핸들러
```

---

## 12. Implementation Order

| Step | File | FR | Description |
|------|------|----|-------------|
| 1 | `src/domain/websocket/__init__.py` | - | 패키지 초기화 |
| 2 | `src/domain/websocket/schemas.py` | FR-02, FR-06 | 메시지 스키마, Close 코드, 연결 VO |
| 3 | `src/domain/websocket/interfaces.py` | FR-01 | ConnectionManagerInterface ABC |
| 4 | `src/infrastructure/websocket/__init__.py` | - | 패키지 초기화 |
| 5 | `src/infrastructure/websocket/connection_manager.py` | FR-01, FR-04, FR-05 | ConnectionManager 구현체 |
| 6 | `src/infrastructure/websocket/auth.py` | FR-03 | WS 토큰 인증 |
| 7 | `src/api/routes/ws_router.py` | FR-07 | 라우터 + echo 핸들러 |
| 8 | `src/api/main.py` (수정) | - | 라우터 등록 + DI 설정 |
| 9 | `tests/unit/domain/websocket/test_schemas.py` | FR-02 | 스키마 테스트 |
| 10 | `tests/unit/infrastructure/websocket/test_connection_manager.py` | FR-01 | CM 테스트 |
| 11 | `tests/unit/infrastructure/websocket/test_auth.py` | FR-03 | 인증 테스트 |

---

## 13. Coding Convention Reference

### 13.1 Naming Conventions (이 피처)

| Target | Rule | Example |
|--------|------|---------|
| 모듈 | snake_case | `connection_manager.py`, `ws_router.py` |
| 클래스 | PascalCase | `ConnectionManager`, `WSMessage` |
| 메서드 | snake_case | `send_to_room()`, `verify_ws_token()` |
| 상수 | UPPER_SNAKE_CASE | `WSCloseCode.AUTH_FAILED` |
| WS 메시지 type | snake_case 문자열 | `"agent_step"`, `"chat_token"`, `"error"` |
| WS 경로 | `/ws/{feature}` 패턴 | `/ws/echo`, `/ws/agent/{run_id}` |

### 13.2 로깅 규칙

| 이벤트 | 레벨 | 필수 kwargs |
|--------|------|------------|
| 연결 성공 | INFO | `user_id`, `room_id`, `total` |
| 연결 해제 | INFO | `user_id`, `room_id`, `total` |
| 인증 실패 | WARNING | `reason`, `remote_addr` |
| 전송 실패 (dead connection) | WARNING | `user_id`, `room_id` |
| 예기치 못한 에러 | ERROR | `exception`, `user_id` |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-15 | Initial draft | 배상규 |
