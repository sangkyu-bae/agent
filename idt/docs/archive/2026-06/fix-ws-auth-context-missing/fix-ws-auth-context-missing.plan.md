# FIX-WS-AUTH-CONTEXT-MISSING: WebSocket 에이전트/채팅 실행 시 system prompt에 사용자 정보(AuthContext)가 누락되는 버그 수정

> 상태: Plan
> 연관 Task: WS-AUTHCTX-001
> 작성일: 2026-06-01
> 우선순위: Critical

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 실제 화면에서 채팅을 보내면 WebSocket(`/ws/agent/{run_id}`, `/ws/chat/{session_id}`)으로 에이전트가 실행되는데, system prompt 맨 앞에 prepend되어야 할 `[현재 사용자 정보]` 블록(이름·부서·역할·권한)이 들어가지 않는다. 동일 기능을 HTTP `/run`·SSE `/run/stream`으로 호출하면 정상 동작한다. |
| **Solution** | WS 엔드포인트가 `verify_ws_token`으로 `User`만 얻고 끝나던 흐름에, `AssembleAuthContextUseCase`를 거쳐 `AuthContext`를 조립하는 단계를 추가하고, `use_case.stream(auth_ctx=..., viewer_department_ids=list(auth_ctx.department_ids))`로 전달한다. HTTP/SSE 경로와 동일한 조립 로직을 재사용. |
| **Function UX Effect** | WS로 실행한 에이전트/채팅이 "나/내/본인" 지시어를 사용자 본인으로 인식하고, 부서·권한 기반 답변 및 권한 필터링 Tool이 정상 동작. SSE와 WS의 동작이 일치. |
| **Core Value** | 금융/정책 문서 RAG 플랫폼의 **권한 일관성**과 **사용자 맥락 인지** 회복. transport(SSE vs WS)에 따라 보안·답변 품질이 달라지는 치명적 불일치 제거. |

---

## 1. 문제 정의 (Problem Statement)

사용자가 실제 화면에서 채팅을 전송하면 프론트엔드는 WebSocket으로 연결한다:

- 에이전트 실행: `/ws/agent/{run_id}` → `RunAgentUseCase.stream()`
- 일반 채팅: `/ws/chat/{session_id}` → `GeneralChatUseCase.stream()`

이때 LLM system prompt 앞에 prepend되어야 할 사용자 컨텍스트 블록이 누락된다.

`render_user_context_block()` (`prompt_rendering.py`)이 생성하는 블록:

```
[현재 사용자 정보]
- 이름: 홍길동
- 부서: 여신심사부
- 역할: 일반 사용자

사용자가 '나', '내', '본인'이라고 말하면 위 사용자를 의미합니다.

[허용된 정보 영역]
- RAG 문서 검색
...
```

**사용자 관점 증상**: WS로 실행한 에이전트가 본인 정보(이름/부서/권한)를 전혀 모른 채 답변하고, "내 부서 규정 알려줘" 같은 질문에서 사용자 식별·권한 기반 동작이 빠진다. 같은 에이전트를 HTTP/SSE로 호출하면 정상.

---

## 2. 근본 원인 분석 (Root Cause)

### 2-1. [Critical] `/ws/agent/{run_id}`가 `auth_ctx`를 전달하지 않음

**파일**: `src/api/routes/ws_router.py:139-147`

```python
async for event in use_case.stream(
    agent_id=sub.agent_id,
    request=request,
    request_id=run_id,
    viewer_user_id=str(user.id),
    viewer_department_ids=[],          # ← 하드코딩 빈 리스트
    # auth_ctx not plumbed through WS: ContextVar relies on HTTP-level assembly.
    # Full auth_ctx wiring for WS is deferred (requires AssembleUC injection).
):
```

`auth_ctx` 인자를 아예 넘기지 않아 `RunAgentUseCase.stream()`의 기본값 `auth_ctx=None`이 적용된다. 그 결과:

1. `_prepare_graph()` → `WorkflowCompiler.compile(auth_ctx=None)` → `render_user_context_block(None)`가 **빈 문자열** 반환 (`prompt_rendering.py:31-32`) → system prompt에 사용자 블록이 prepend되지 않음. **← 사용자가 겪는 증상의 직접 원인.**
2. `run_agent_use_case.py:202-204`의 `set_current_auth_context(auth_ctx)`가 `auth_ctx is None`이라 호출되지 않음 → Tool/Repository의 ContextVar fallback(`get_current_auth_context()`)도 비어 권한 필터링이 무력화.
3. `tool_factory.bind_auth_ctx(None)` → 권한 기반 Tool이 anonymous로 동작.

### 2-2. [Critical] `/ws/chat/{session_id}`도 동일 결함

**파일**: `src/api/routes/ws_router.py:225`

```python
async for event in use_case.stream(request, request_id=session_id):   # auth_ctx 미전달
```

`GeneralChatUseCase.stream()`도 `auth_ctx` 키워드를 지원하며(`general_chat/use_case.py:126,151-153,169`), `_create_agent(tools, auth_ctx)`에서 `render_user_context_block(auth_ctx) + _SYSTEM_PROMPT`로 prepend한다. WS 경로가 `auth_ctx`를 안 넘기므로 에이전트 실행과 똑같이 사용자 블록이 누락된다.

### 2-3. 근본 원인 요약 — WS 인증이 `User`에서 멈춤

**파일**: `src/infrastructure/websocket/auth.py:11-40`

`verify_ws_token()`은 토큰 검증 후 `User` 엔티티만 반환한다. HTTP/SSE 경로가 사용하는 `AssembleAuthContextUseCase.execute(user)` 단계(profile + department + permission 3회 DB 조회 후 `AuthContext` 조립)가 WS에는 빠져 있다.

**대조 (정상 경로)**:

| 경로 | AuthContext 조립 | stream 전달 |
|------|------------------|-------------|
| HTTP `POST /run` | `Depends(get_auth_context)` (`agent_builder_router.py:265`) | `auth_ctx=auth_ctx, viewer_department_ids=list(auth_ctx.department_ids)` (276-277) |
| SSE `/run/stream` | `Depends(get_auth_context_from_query_token)` (`:300`) | `auth_ctx=auth_ctx, ...` (322-324) |
| **WS `/ws/agent`** | **없음** (verify_ws_token → User) | **누락** |
| **WS `/ws/chat`** | **없음** | **누락** |

`AssembleAuthContextUseCase`는 이미 DI로 구성되어 있다 (`main.py:1266-1274`의 `assemble_auth_context_factory`, `:2391`에서 override). WS에서 이 UseCase를 호출만 하면 된다.

---

## 3. 수정 범위 (Scope)

> 결정 사항(사용자 확인): **두 WS 엔드포인트 모두 수정**, AuthContext 조립은 **전용 단기 세션**, 조립 실패 시 **fail-closed(anonymous)로 진행**.

| # | 수정 위치 | 내용 | 우선순위 |
|---|-----------|------|----------|
| 1 | `ws_router.py` | `get_ws_assemble_auth_context_use_case()` DI placeholder 추가 | Critical |
| 2 | `infrastructure/websocket/auth.py` 또는 신규 헬퍼 | `verify_ws_token` 결과 `User` → `AuthContext` 조립 헬퍼(`resolve_ws_auth_context`) 추가. 실패 시 `AuthContext.public_anonymous()` 반환 (fail-closed) | Critical |
| 3 | `ws_router.py::ws_agent_run` | 조립한 `auth_ctx`를 `stream(auth_ctx=..., viewer_department_ids=list(auth_ctx.department_ids))`로 전달. `viewer_user_id`는 기존 유지 | Critical |
| 4 | `ws_router.py::ws_chat` | `GeneralChatUseCase.stream(request, request_id=..., auth_ctx=auth_ctx)` 로 전달 | Critical |
| 5 | `main.py` WebSocket DI 블록(`:2401-2415`) | `get_ws_assemble_auth_context_use_case` override 등록 (전용 session_factory 기반 팩토리) | Critical |
| 6 | `tests/api/test_ws_router*.py` (신규/추가) | 두 WS 경로가 auth_ctx를 stream에 전달하는지 + fail-closed 회귀 테스트 | High |

**범위 외**:
- `verify_ws_token`의 토큰 검증 로직 자체 변경 없음 (그대로 재사용)
- `AssembleAuthContextUseCase` 내부 캐싱/성능 최적화 (HTTP 경로와 공통 후속 이슈)

---

## 4. 수정 방향 (Solution Design)

### 4-1. 전용 단기 세션 기반 AuthContext 조립 헬퍼

WS 연결은 스트리밍 동안 장시간 유지되므로, request-scoped `get_session`을 연결 수명 내내 점유하지 않도록 **조립 시점에만 짧게 세션을 여는 전용 팩토리**를 쓴다. (CLAUDE.md §6: 팩토리에서 `get_session_factory()()` 직접 호출 금지 → `session_factory`를 주입받아 `async with`로 사용)

```python
# ws_router.py — DI placeholder
def get_ws_assemble_auth_context_use_case() -> "WsAuthContextResolver":
    raise NotImplementedError("WsAuthContextResolver not initialized")
```

```python
# infrastructure/websocket/auth.py (또는 신규 모듈)
async def resolve_ws_auth_context(
    user: User,
    resolver: "WsAuthContextResolver",
    logger: LoggerInterface,
) -> AuthContext:
    """User → AuthContext 조립. 실패 시 fail-closed로 anonymous 반환."""
    request_id = str(uuid.uuid4())
    try:
        return await resolver.execute(user, request_id)
    except Exception as e:
        logger.error("WS AuthContext assembly failed — degrading to anonymous",
                     exception=e, request_id=request_id)
        return AuthContext.public_anonymous()
```

`WsAuthContextResolver.execute(user, request_id)`는 내부에서 전용 `session_factory`로 단기 세션을 열어 `AssembleAuthContextUseCase`를 구성·실행한다 (main.py 팩토리에서 wiring). 이로써 조립 후 세션은 즉시 반환되고, 이후 장시간 스트리밍은 세션을 점유하지 않는다.

### 4-2. `/ws/agent/{run_id}` 수정

```python
user = await verify_ws_token(websocket, jwt_adapter, user_repo)
if not user:
    return
auth_ctx = await resolve_ws_auth_context(user, assemble_resolver, logger)
...
async for event in use_case.stream(
    agent_id=sub.agent_id,
    request=request,
    request_id=run_id,
    viewer_user_id=str(user.id),
    viewer_department_ids=list(auth_ctx.department_ids),   # [] → 실제 부서
    auth_ctx=auth_ctx,                                     # 신규 전달
):
```

### 4-3. `/ws/chat/{session_id}` 수정

```python
auth_ctx = await resolve_ws_auth_context(user, assemble_resolver, logger)
...
async for event in use_case.stream(request, request_id=session_id, auth_ctx=auth_ctx):
```

### 4-4. fail-closed 동작 (조립 실패 시)

`resolve_ws_auth_context`가 예외 시 `AuthContext.public_anonymous()`를 반환 →
- `render_user_context_block(anonymous)` = 빈 문자열 (사용자 블록 없음, 기존과 동일하게 안전)
- `permissions = frozenset()` → 권한 필요한 Tool 자동 거부 (RAG 검색 등)
- WS 연결은 끊지 않고 채팅 자체는 계속 동작 → 사용자 경험 보존하되 권한은 노출 안 함.

### 4-5. DI wiring (main.py)

`main.py:2401-2415` WebSocket DI 블록에 추가:

```python
app.dependency_overrides[get_ws_assemble_auth_context_use_case] = (
    create_ws_auth_context_resolver_factory()   # 전용 session_factory 기반
)
```

기존 `assemble_auth_context_factory`가 `Depends(get_session)`를 쓰는 것과 달리, WS용은 `session_factory`를 클로저로 주입받아 `execute()` 내부에서 `async with session_factory() as session: ...`로 단기 사용한다.

---

## 5. 테스트 계획 (TDD)

> 백엔드 테스트는 Windows 이벤트 루프 teardown 산발 실패 이슈가 있어, 신규 테스트는 격리 실행으로 검증한다 (참조: backend-test-eventloop-flakiness 메모).

### 5-1. `/ws/agent` — auth_ctx가 stream에 전달되는지

```python
async def test_ws_agent_run_passes_assembled_auth_context_to_stream():
    """WS 에이전트 실행이 AuthContext를 조립해 stream(auth_ctx=...)로 전달한다."""
    # given: verify_ws_token → User, resolver → 부서·권한 있는 AuthContext
    # when: subscribe 메시지 전송
    # then: use_case.stream 호출 인자에 auth_ctx(role/부서/권한)와
    #       viewer_department_ids == list(auth_ctx.department_ids) 포함
```

### 5-2. `/ws/chat` — auth_ctx 전달

```python
async def test_ws_chat_passes_auth_context_to_general_chat_stream():
    """WS 일반 채팅이 GeneralChatUseCase.stream(auth_ctx=...)로 전달한다."""
```

### 5-3. fail-closed 회귀 — 조립 실패 시 anonymous, 연결 유지

```python
async def test_ws_auth_context_assembly_failure_degrades_to_anonymous():
    """resolver.execute 예외 시 anonymous AuthContext로 진행하고 WS는 끊기지 않는다."""
    # resolver.execute가 raise → stream에 anonymous(permissions 빈) auth_ctx 전달,
    #   websocket.close(AUTH_FAILED) 호출되지 않음
```

### 5-4. 사용자 블록 렌더링 통합 검증 (선택)

조립된 `auth_ctx`로 `render_user_context_block`이 `[현재 사용자 정보]` 블록을 실제로 생성하는지(이름/부서/역할 포함) 통합 레벨에서 1건 확인.

---

## 6. 영향 범위 / 리스크

| 항목 | 영향 | 비고 |
|------|------|------|
| HTTP `/run`, SSE `/run/stream` | **변경 없음** | 기존 Depends 경로 그대로 |
| WS 연결 수립 latency | **소폭 증가** | 조립 시 DB 3회 round-trip 추가. SSE와 동일 비용이며 스트림 시작 직전 1회뿐 |
| WS 연결 중 DB 세션 점유 | **없음** | 전용 단기 세션 — 조립 후 즉시 반환 |
| 권한 필터링 Tool 동작 | **개선** | WS에서도 권한 기반 필터 정상 작동 (이전엔 무력화) |
| 미인증/조립실패 시 | **안전(fail-closed)** | anonymous → 권한 Tool 거부, 사용자 블록 미노출 |
| 토큰/민감정보 노출 | **없음** | `render_user_context_block` whitelist 유지 (employee_no/email 비노출) |
| 프론트엔드 | **변경 없음** | wire protocol(subscribe payload) 동일 |

---

## 7. 구현 순서

1. `tests/api/test_ws_router_auth_context.py`에 5-1, 5-2, 5-3 테스트 작성 (RED 확인, 격리 실행)
2. `infrastructure/websocket/auth.py`에 `resolve_ws_auth_context` + `WsAuthContextResolver` 추가
3. `ws_router.py`에 DI placeholder 추가, `ws_agent_run`/`ws_chat`에서 auth_ctx 조립·전달
4. `main.py` WebSocket DI에 `create_ws_auth_context_resolver_factory()` override 등록
5. 테스트 GREEN 확인 (격리 실행)
6. 로컬 dev 서버에서 실제 화면 채팅 → system prompt에 `[현재 사용자 정보]` 블록 진입 수동 검증 (LangSmith trace 또는 로깅)
7. Gap 분석 → Report

---

## 8. 미해결/후속 이슈

- **AuthContext 조립 캐싱**: HTTP/SSE/WS 모두 매 요청 DB 3회 조회. p95 측정 후 공통 캐싱 도입 검토 (auth.py:91 주석 참조).
- **`/ws/echo`**: 인프라 검증용이므로 auth_ctx 불필요 — 범위 외.
- **WS auth_ctx ContextVar 전파 일관성**: `RunAgentUseCase.stream`은 auth_ctx가 있을 때만 `set_current_auth_context` 호출 — anonymous도 set할지(명시적 fail-closed 강제) 여부는 후속 검토.
