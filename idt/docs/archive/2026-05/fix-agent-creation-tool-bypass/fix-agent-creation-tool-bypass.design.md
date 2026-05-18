# Fix Agent Creation Tool Bypass Design Document

> **Summary**: `tool_configs` 존재 시 LLM 자동 선택을 건너뛰고 직접 workers를 생성하며, ValueError를 422로 반환하는 설계
>
> **Project**: sangplusbot (idt)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-05-09
> **Status**: Draft
> **Planning Doc**: [fix-agent-creation-tool-bypass.plan.md](../01-plan/features/fix-agent-creation-tool-bypass.plan.md)

---

## 1. Overview

### 1.1 Design Goals

1. `tool_configs`가 존재하면 LLM `ToolSelector.select()` 호출 없이 직접 `WorkerDefinition` 리스트를 생성한다
2. `tool_configs` 키의 `internal:` 접두사를 정규화하여 `TOOL_REGISTRY` 키와 매칭한다
3. `ValueError`를 전역 미들웨어에서 422 Unprocessable Entity로 분류한다
4. 기존 LLM 자동 선택 흐름(tool_configs 미전달)은 변경하지 않는다

### 1.2 Design Principles

- 단일 책임: 분기 로직은 UseCase 내부, 에러 분류는 미들웨어에서 처리
- 하위 호환성: tool_configs가 없을 때 기존 흐름 100% 유지
- 방어적 정규화: 백엔드에서 접두사 제거하여 프론트 변경 불필요

---

## 2. Architecture

### 2.1 변경 전 흐름 (Bug)

```
프론트: tool_configs = { "internal:internal_document_search": {...} }
  ↓
Step 1: ToolSelector.select(user_request)  ← tool_configs 무시
  → LLM 추론 실패 → workers = []
  ↓
Step 1.5: tool_configs → workers 매칭 시도
  → workers가 []이므로 매칭 대상 없음
  ↓
Step 2: validate_tool_count(0) → ValueError
  ↓
ExceptionHandlerMiddleware → 500 Internal Server Error
```

### 2.2 변경 후 흐름 (Fix)

```
프론트: tool_configs = { "internal:internal_document_search": {...} }
  ↓
분기: tool_configs 존재?
  ├─ YES → _build_skeleton_from_configs(tool_configs)
  │         ├─ 키 정규화: "internal:internal_document_search" → "internal_document_search"
  │         ├─ TOOL_REGISTRY 조회 → ToolMeta 획득
  │         ├─ WorkerDefinition 생성 + tool_config 적용
  │         └─ WorkflowSkeleton(workers, flow_hint) 반환
  │
  └─ NO → ToolSelector.select(user_request)  ← 기존 LLM 흐름 유지
  ↓
Step 2: validate_tool_count(len(workers))  → 정상 통과
  ↓
Step 3~4: 시스템 프롬프트 생성 → DB 저장 → 응답
```

### 2.3 에러 흐름 개선

```
ValueError 발생 (어떤 라우터에서든)
  ↓
ExceptionHandlerMiddleware._handle_exception()
  ├─ isinstance(exc, ValueError) → status_code = 422
  └─ 그 외 Exception → status_code = 500 (기존 유지)
  ↓
JSONResponse(status_code, error_response)
```

### 2.4 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `CreateAgentUseCase._build_skeleton_from_configs()` | `tool_registry.get_tool_meta()` | tool_id 유효성 검증 + 메타데이터 조회 |
| `CreateAgentUseCase._normalize_tool_id()` | 없음 (순수 함수) | 접두사 제거 |
| `ExceptionHandlerMiddleware._handle_exception()` | 없음 | ValueError 분류 |

---

## 3. Detailed Design

### 3.1 `CreateAgentUseCase` 변경

#### 3.1.1 `execute()` 메서드 — Step 1 분기 추가

**파일**: `src/application/agent_builder/create_agent_use_case.py`

**변경 위치**: Line 46~55 (Step 1 + Step 1.5)

```python
# Step 1: 도구 선택 + 플로우 결정
if request.tool_configs:
    skeleton = self._build_skeleton_from_configs(
        request.tool_configs, request_id
    )
else:
    skeleton = await self._selector.select(
        request.user_request, request_id
    )
```

기존 Step 1.5 (tool_configs → workers 매칭) 블록은 **삭제**한다.
- `_build_skeleton_from_configs()`에서 `tool_config`를 직접 적용하므로 별도 매칭 불필요

#### 3.1.2 `_build_skeleton_from_configs()` — 신규 메서드

```python
def _build_skeleton_from_configs(
    self,
    tool_configs: dict[str, RagToolConfigRequest],
    request_id: str,
) -> WorkflowSkeleton:
    workers: list[WorkerDefinition] = []
    for i, (raw_key, config) in enumerate(tool_configs.items()):
        tool_id = self._normalize_tool_id(raw_key)
        meta = get_tool_meta(tool_id)
        workers.append(WorkerDefinition(
            tool_id=tool_id,
            worker_id=f"{tool_id}_worker",
            description=meta.description,
            sort_order=i,
            tool_config=config.model_dump(),
        ))
    flow_hint = " → ".join(w.tool_id for w in workers)
    self._logger.info(
        "Built skeleton from tool_configs",
        request_id=request_id,
        tool_ids=[w.tool_id for w in workers],
    )
    return WorkflowSkeleton(workers=workers, flow_hint=flow_hint)
```

**동작 설명**:
1. `tool_configs` dict를 순회하며 각 키를 `_normalize_tool_id()`로 정규화
2. `get_tool_meta(tool_id)` 호출 — 존재하지 않으면 `ValueError("Unknown tool_id: ...")` 발생
3. `WorkerDefinition` 생성 시 `tool_config`에 `config.model_dump()` 직접 적용
4. `flow_hint`는 tool_id들을 `" → "`로 연결

**함수 길이**: 약 15줄 (40줄 제한 준수)

#### 3.1.3 `_normalize_tool_id()` — 신규 정적 메서드

```python
@staticmethod
def _normalize_tool_id(raw_key: str) -> str:
    return raw_key.split(":")[-1] if ":" in raw_key else raw_key
```

**동작 설명**:
- `"internal:internal_document_search"` → `"internal_document_search"`
- `"internal_document_search"` → `"internal_document_search"` (접두사 없으면 그대로)
- `"mcp:some_tool"` → `"some_tool"` (향후 MCP 도구 접두사도 처리 가능)

#### 3.1.4 import 추가

```python
from src.application.agent_builder.schemas import (
    CreateAgentRequest, CreateAgentResponse, RagToolConfigRequest, WorkerInfo
)
```

`RagToolConfigRequest` import 추가 (타입 힌트용)

### 3.2 `ExceptionHandlerMiddleware` 변경

**파일**: `src/infrastructure/logging/middleware/exception_handler_middleware.py`

**변경 위치**: `_handle_exception()` 메서드 (Line 52~97)

```python
async def _handle_exception(
    self, request: Request, exc: Exception
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))

    stacktrace = "".join(
        traceback.format_exception(type(exc), exc, exc.__traceback__)
    )

    self._logger.error(
        "Unhandled exception",
        exception=exc,
        request_id=request_id,
        endpoint=request.url.path,
        method=request.method,
    )

    error_detail = ErrorDetail(
        type=type(exc).__name__,
        message=str(exc),
        stacktrace=stacktrace if self._debug else None,
    )

    error_response = ErrorResponse(
        request_id=request_id,
        error=error_detail,
    )

    status_code = 422 if isinstance(exc, ValueError) else 500

    return JSONResponse(
        status_code=status_code,
        content=error_response.model_dump(exclude_none=not self._debug),
        headers={"X-Request-ID": request_id},
    )
```

**변경점**: `status_code = 500` 하드코딩 → `isinstance(exc, ValueError)` 분기

---

## 4. Error Handling

### 4.1 에러 시나리오

| 시나리오 | 예외 | HTTP 코드 | 메시지 |
|---------|------|-----------|--------|
| tool_configs에 알 수 없는 tool_id | `ValueError` | 422 | `Unknown tool_id: 'wrong_tool'` |
| tool_configs가 빈 dict `{}` | `ValueError` | 422 | `최소 1개 이상의 도구가 필요합니다.` |
| 정상 흐름에서 LLM이 도구 0개 선택 | `ValueError` | 422 | `최소 1개 이상의 도구가 필요합니다.` |
| LLM 모델 미등록 | `ValueError` | 422 | `LLM 모델을 찾을 수 없습니다: ...` |
| 기타 예외 (DB, 네트워크 등) | `Exception` | 500 | 원래 예외 메시지 |

### 4.2 기존 라우터 영향 분석

`ValueError` → 422 전역 변경의 영향 범위:

| 라우터 | 기존 ValueError 처리 | 영향 |
|--------|---------------------|------|
| `create_agent` | 미들웨어 폴스루 → 500 | **422로 개선** (의도한 변경) |
| `update_agent` | 라우터에서 try-catch → 404/422 | 영향 없음 (라우터에서 먼저 처리) |
| `run_agent` | 라우터에서 try-catch → 404 | 영향 없음 (라우터에서 먼저 처리) |
| `delete_agent` | 라우터에서 try-catch → 404 | 영향 없음 (라우터에서 먼저 처리) |
| `interview/*` | 라우터에서 try-catch → 404/422 | 영향 없음 (라우터에서 먼저 처리) |
| `subscribe` | 라우터에서 try-catch → 400/404/409 | 영향 없음 (라우터에서 먼저 처리) |
| `fork` | 라우터에서 try-catch → 400/404 | 영향 없음 (라우터에서 먼저 처리) |

**결론**: 라우터에서 `ValueError`를 `try-catch`로 `HTTPException`으로 변환하는 경우, FastAPI가 `HTTPException`을 자체 처리하므로 미들웨어에 도달하지 않음. `create_agent`만 `ValueError`가 미들웨어까지 전파되는 유일한 케이스.

---

## 5. Test Plan

### 5.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit Test | `_build_skeleton_from_configs()` | pytest |
| Unit Test | `_normalize_tool_id()` | pytest |
| Unit Test | `execute()` — tool_configs 분기 | pytest + AsyncMock |
| Unit Test | `ExceptionHandlerMiddleware` — 422 분류 | pytest + TestClient |

### 5.2 `test_create_agent_use_case.py` — 신규 테스트 케이스

#### TC-01: tool_configs로 직접 workers 생성

```python
class TestExplicitToolSelection:
    @pytest.mark.asyncio
    async def test_tool_configs_skips_llm_selector(self):
        """tool_configs 존재 시 ToolSelector.select()를 호출하지 않는다."""
        use_case, tool_selector, _, _, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="테스트",
            name="테스트 에이전트",
            user_id="user-1",
            tool_configs={
                "internal:internal_document_search": RagToolConfigRequest(
                    collection_name="my-docs"
                )
            },
        )
        await use_case.execute(request, "req-1")
        tool_selector.select.assert_not_awaited()
```

#### TC-02: 정규화된 tool_id로 worker 생성

```python
    @pytest.mark.asyncio
    async def test_tool_configs_normalizes_prefix(self):
        """'internal:internal_document_search' → 'internal_document_search'."""
        use_case, _, _, repo, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="테스트",
            name="테스트 에이전트",
            user_id="user-1",
            tool_configs={
                "internal:internal_document_search": RagToolConfigRequest(
                    collection_name="my-docs"
                )
            },
        )
        result = await use_case.execute(request, "req-1")
        assert "internal_document_search" in result.tool_ids
```

#### TC-03: tool_configs에 알 수 없는 tool_id → ValueError

```python
    @pytest.mark.asyncio
    async def test_unknown_tool_id_raises_value_error(self):
        """TOOL_REGISTRY에 없는 tool_id → ValueError."""
        use_case, _, _, _, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="테스트",
            name="테스트 에이전트",
            user_id="user-1",
            tool_configs={
                "internal:nonexistent_tool": RagToolConfigRequest()
            },
        )
        with pytest.raises(ValueError, match="Unknown tool_id"):
            await use_case.execute(request, "req-1")
```

#### TC-04: tool_configs 없으면 기존 LLM 흐름 유지

```python
    @pytest.mark.asyncio
    async def test_no_tool_configs_uses_llm_selector(self):
        """tool_configs 없을 때 ToolSelector.select() 호출."""
        use_case, tool_selector, _, _, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="테스트 요청",
            name="테스트",
            user_id="user-1",
        )
        await use_case.execute(request, "req-1")
        tool_selector.select.assert_awaited_once()
```

#### TC-05: tool_config가 worker에 적용됨

```python
    @pytest.mark.asyncio
    async def test_tool_config_applied_to_worker(self):
        """tool_configs의 설정이 WorkerDefinition.tool_config에 적용된다."""
        use_case, _, _, repo, _ = _make_use_case()
        config = RagToolConfigRequest(
            collection_name="my-docs",
            top_k=10,
            search_mode="vector_only",
        )
        request = CreateAgentRequest(
            user_request="테스트",
            name="테스트 에이전트",
            user_id="user-1",
            tool_configs={"internal:internal_document_search": config},
        )
        await use_case.execute(request, "req-1")
        saved_agent = repo.save.call_args[0][0]
        worker = saved_agent.workers[0]
        assert worker.tool_config["collection_name"] == "my-docs"
        assert worker.tool_config["top_k"] == 10
```

### 5.3 `test_exception_handler_middleware.py` — 신규 테스트 케이스

#### TC-06: ValueError → 422

```python
    def test_value_error_returns_422(self, client_debug_true):
        """ValueError 발생 시 422 상태 코드를 반환한다."""
        response = client_debug_true.get("/error")  # 기존 /error = ValueError
        assert response.status_code == 422
```

#### TC-07: RuntimeError → 500 유지

```python
    def test_runtime_error_still_returns_500(self, client_debug_true):
        """RuntimeError는 여전히 500을 반환한다."""
        response = client_debug_true.get("/runtime-error")
        assert response.status_code == 500
```

**주의**: TC-06은 기존 테스트 `test_exception_returns_500_status`와 충돌. 기존 테스트에서 `/error` 엔드포인트가 `ValueError`를 발생시키므로, 기존 테스트의 기대값을 500 → 422로 수정해야 함.

### 5.4 기존 테스트 수정 목록

| 파일 | 테스트 | 변경 |
|------|--------|------|
| `test_exception_handler_middleware.py` | `test_exception_returns_500_status` | `assert response.status_code == 500` → `422` |

---

## 6. Clean Architecture

### 6.1 Layer Structure

| Layer | Responsibility | Location |
|-------|---------------|----------|
| **Interfaces** | 라우터, 요청/응답 스키마 | `src/api/routes/agent_builder_router.py` |
| **Application** | UseCase, 도구 선택 분기, workers 생성 | `src/application/agent_builder/create_agent_use_case.py` |
| **Domain** | ToolMeta, WorkerDefinition, WorkflowSkeleton, Policy | `src/domain/agent_builder/` |
| **Infrastructure** | ExceptionHandlerMiddleware | `src/infrastructure/logging/middleware/` |

### 6.2 Dependency Rules 준수

```
CreateAgentUseCase (Application)
  → tool_registry.get_tool_meta() (Domain) ✅
  → schemas.WorkerDefinition (Domain) ✅
  → schemas.WorkflowSkeleton (Domain) ✅
  → schemas.RagToolConfigRequest (Application) ✅

ExceptionHandlerMiddleware (Infrastructure)
  → ErrorDetail, ErrorResponse (Domain) ✅
```

### 6.3 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `_build_skeleton_from_configs()` | Application | `src/application/agent_builder/create_agent_use_case.py` |
| `_normalize_tool_id()` | Application | `src/application/agent_builder/create_agent_use_case.py` |
| `_handle_exception()` 수정 | Infrastructure | `src/infrastructure/logging/middleware/exception_handler_middleware.py` |

---

## 7. Implementation Guide

### 7.1 변경 대상 파일

```
src/
├── application/agent_builder/
│   └── create_agent_use_case.py     # 신규 메서드 2개, execute() 분기 수정
├── infrastructure/logging/middleware/
│   └── exception_handler_middleware.py  # status_code 분류 1줄 변경
tests/
├── application/agent_builder/
│   └── test_create_agent_use_case.py   # 신규 테스트 클래스 1개 (5 케이스)
├── infrastructure/logging/
│   └── test_exception_handler_middleware.py  # 기존 수정 1개 + 신규 1개
```

### 7.2 Implementation Order (TDD)

1. [ ] `test_create_agent_use_case.py` — `TestExplicitToolSelection` 클래스 작성 (Red)
2. [ ] `test_exception_handler_middleware.py` — ValueError → 422 테스트 수정/추가 (Red)
3. [ ] `create_agent_use_case.py` — `_build_skeleton_from_configs()`, `_normalize_tool_id()` 구현, `execute()` 분기 수정 (Green)
4. [ ] `exception_handler_middleware.py` — `isinstance(exc, ValueError)` 분기 추가 (Green)
5. [ ] 전체 테스트 실행 — regression 없음 확인
6. [ ] E2E: 프론트에서 Agent Builder → 도구 선택 → 생성 테스트

### 7.3 `_make_use_case()` 헬퍼 수정 필요

기존 `_make_use_case()` 헬퍼의 `repository.save` mock이 하드코딩된 `saved_agent`를 반환하는데, `_build_skeleton_from_configs()`로 생성된 workers가 반영되지 않음. 

**해결**: `save` mock을 `side_effect`로 변경하여 입력된 `AgentDefinition`을 그대로 반환.

```python
repository.save = AsyncMock(side_effect=lambda agent, req_id: agent)
```

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-09 | Initial draft | 배상규 |
