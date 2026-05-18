# Fix Agent Creation Tool Bypass Planning Document

> **Summary**: 프론트엔드에서 명시적으로 선택한 도구가 백엔드 Agent 생성에서 무시되는 버그를 수정한다
>
> **Project**: sangplusbot (idt)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-05-09
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 프론트엔드에서 사용자가 도구를 명시 선택하고 `tool_configs`를 전달해도, `CreateAgentUseCase`가 LLM `ToolSelector`에만 의존하여 도구를 결정하므로 사용자 선택이 무시되어 workers=0 → ValueError 발생 |
| **Solution** | `tool_configs`가 존재하면 LLM 자동 선택을 건너뛰고 해당 도구들로 직접 `WorkerDefinition`을 생성하며, `ValueError`를 422 응답으로 변환하는 에러 핸들링을 추가한다 |
| **Function/UX Effect** | 사용자가 Agent Builder에서 도구를 선택하면 해당 도구가 정확히 반영된 에이전트가 생성되고, 실패 시 명확한 에러 메시지를 받는다 |
| **Core Value** | 사용자 의도가 Agent 생성에 확실하게 반영되는 예측 가능한 동작 보장 |

---

## 1. Overview

### 1.1 Purpose

`POST /api/v1/agents` 엔드포인트에서 발생하는 2가지 버그를 수정한다:

1. **도구 선택 무시**: 프론트에서 `tool_configs`로 도구를 지정해도, `ToolSelector`(LLM)가 독립적으로 도구를 판단하여 사용자 선택이 무시됨
2. **에러 응답 부적절**: 비즈니스 검증 실패(`ValueError`)가 500 Internal Server Error로 반환되어 프론트엔드에서 적절한 에러 처리 불가

### 1.2 Background

**현재 흐름 (버그):**

```
프론트: tool_configs = { "internal:internal_document_search": {...} }
  ↓
Step 1: ToolSelector.select("테스트입니다")   ← user_request만 전달, tool_configs 무시
  → LLM이 "테스트입니다"에서 도구 추론 실패 → workers = []
  ↓
Step 1.5: tool_configs를 workers에 매칭
  → workers가 []이므로 매칭 대상 없음 → 스킵
  ↓
Step 2: validate_tool_count(0)
  → ValueError("최소 1개 이상의 도구가 필요합니다.")
  → exception_handler_middleware가 500으로 반환
```

**추가 문제 — tool_id 불일치:**

| 위치 | tool_id 형식 | 예시 |
|------|-------------|------|
| 프론트엔드 `RAG_TOOL_ID` | `internal:` 접두사 포함 | `internal:internal_document_search` |
| 백엔드 `TOOL_REGISTRY` | 접두사 없음 | `internal_document_search` |

프론트에서 보내는 `tool_configs` 키가 `internal:internal_document_search`인데, 백엔드 `TOOL_REGISTRY` 키는 `internal_document_search`이므로 매칭이 안 됨.

### 1.3 Related Documents

- `src/application/agent_builder/create_agent_use_case.py` — UseCase 메인 로직
- `src/application/agent_builder/tool_selector.py` — LLM 기반 도구 자동 선택
- `src/domain/agent_builder/tool_registry.py` — 도구 레지스트리 (4개 도구)
- `src/infrastructure/logging/middleware/exception_handler_middleware.py` — 전역 예외 처리
- `idt_front/src/pages/AgentBuilderPage/index.tsx` — 프론트 Agent Builder

---

## 2. Scope

### 2.1 In Scope

- [x] `CreateAgentUseCase.execute()` — `tool_configs` 존재 시 LLM 자동 선택 건너뛰기
- [x] `tool_configs` 키에서 `internal:` 접두사 정규화 처리
- [x] `tool_configs`로부터 직접 `WorkerDefinition` 리스트 생성하는 로직
- [x] `exception_handler_middleware` — `ValueError`를 422로 분류
- [x] 기존 테스트 수정 및 신규 테스트 작성

### 2.2 Out of Scope

- 프론트엔드 코드 변경 (현재 프론트 동작은 의도대로 도구를 보내고 있음)
- `ToolSelector` 내부 LLM 프롬프트 개선 (별도 피처)
- 새 도구 추가

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `tool_configs`가 존재하면 `ToolSelector.select()`를 호출하지 않고, `tool_configs` 키를 기반으로 `WorkerDefinition` 리스트를 직접 생성한다 | High | Pending |
| FR-02 | `tool_configs` 키의 `internal:` 등 접두사를 제거하여 `TOOL_REGISTRY` 키와 매칭한다 | High | Pending |
| FR-03 | `tool_configs`에 없는 도구 ID가 포함된 경우 `ValueError`를 발생시킨다 | Medium | Pending |
| FR-04 | `tool_configs`가 없을 때는 기존 LLM 자동 선택 흐름을 유지한다 | High | Pending |
| FR-05 | `ValueError`를 422 Unprocessable Entity로 반환하고, 에러 메시지를 body에 포함한다 | High | Pending |
| FR-06 | `tool_configs`로 생성된 workers에도 `flow_hint`를 자동 생성한다 | Low | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 하위 호환 | `tool_configs` 없이 기존 LLM 자동 선택 흐름 동작 유지 | 기존 테스트 통과 |
| 성능 | `tool_configs` 지정 시 LLM 호출 없이 즉시 응답 | 응답 시간 측정 |
| 테스트 | 신규 로직 단위 테스트 커버리지 100% | pytest --cov |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] `tool_configs` 있을 때 LLM 건너뛰고 직접 workers 생성
- [ ] `internal:` 접두사 정규화 처리
- [ ] `ValueError` → 422 응답 변환
- [ ] 기존 테스트 전부 통과 (regression 없음)
- [ ] 신규 테스트 작성 및 통과

### 4.2 Quality Criteria

- [ ] 프론트엔드에서 도구 선택 후 Agent 생성이 성공하는 E2E 확인
- [ ] `tool_configs` 없이 생성하는 기존 흐름도 정상 동작 확인

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| `tool_configs` 키 정규화 시 잘못된 tool_id 매칭 | High | Low | TOOL_REGISTRY에 존재하지 않으면 즉시 ValueError |
| LLM 자동 선택 건너뛰기로 인한 flow_hint 누락 | Medium | Medium | 명시적 도구 목록으로 간단한 flow_hint 자동 생성 |
| 422 변환으로 기존 에러 핸들링 영향 | Low | Low | ValueError만 422, 나머지는 기존 500 유지 |

---

## 6. Architecture Considerations

### 6.1 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 도구 직접 생성 위치 | UseCase 내부 / 별도 서비스 | UseCase 내부 | 로직이 간단 (키 → WorkerDefinition 변환), 별도 서비스 불필요 |
| 접두사 정규화 | 프론트에서 제거 / 백엔드에서 제거 | 백엔드에서 제거 | 프론트 변경 최소화, 하위 호환성 유지 |
| 에러 분류 | 미들웨어에서 / 라우터에서 try-catch | 미들웨어에서 | 전역 일관성, 코드 중복 방지 |

### 6.2 변경 대상 파일

| 파일 | 변경 내용 |
|------|----------|
| `src/application/agent_builder/create_agent_use_case.py` | `tool_configs` 존재 시 workers 직접 생성 로직 추가 |
| `src/infrastructure/logging/middleware/exception_handler_middleware.py` | `ValueError` → 422 분류 |
| `tests/application/agent_builder/test_create_agent_use_case.py` | 신규 테스트 추가 |
| `tests/infrastructure/logging/middleware/test_exception_handler_middleware.py` | 422 반환 테스트 |

---

## 7. Implementation Strategy

### 7.1 변경 1: `CreateAgentUseCase` — 명시적 도구 선택 지원

**Before:**
```python
# Step 1: 도구 선택 + 플로우 결정 (항상 LLM)
skeleton = await self._selector.select(request.user_request, request_id)

# Step 1.5: tool_configs 적용 (이미 선택된 workers에만)
if request.tool_configs:
    for worker in skeleton.workers:
        if worker.tool_id in request.tool_configs:
            worker.tool_config = request.tool_configs[worker.tool_id].model_dump()
```

**After:**
```python
# Step 1: 도구 선택 + 플로우 결정
if request.tool_configs:
    # 명시적 도구 선택: tool_configs 키 기반으로 직접 workers 생성
    skeleton = self._build_skeleton_from_configs(request.tool_configs, request_id)
else:
    # LLM 자동 선택: 기존 흐름 유지
    skeleton = await self._selector.select(request.user_request, request_id)
```

**신규 메서드:**
```python
def _build_skeleton_from_configs(
    self,
    tool_configs: dict[str, RagToolConfigRequest],
    request_id: str,
) -> WorkflowSkeleton:
    workers = []
    for i, (raw_key, config) in enumerate(tool_configs.items()):
        tool_id = self._normalize_tool_id(raw_key)
        meta = get_tool_meta(tool_id)  # ValueError if not found
        workers.append(WorkerDefinition(
            tool_id=tool_id,
            worker_id=f"{tool_id}_worker",
            description=meta.description,
            sort_order=i,
            tool_config=config.model_dump(),
        ))
    flow_hint = " → ".join(w.tool_id for w in workers)
    return WorkflowSkeleton(workers=workers, flow_hint=flow_hint)

@staticmethod
def _normalize_tool_id(raw_key: str) -> str:
    """'internal:internal_document_search' → 'internal_document_search'"""
    return raw_key.split(":")[-1] if ":" in raw_key else raw_key
```

### 7.2 변경 2: `ExceptionHandlerMiddleware` — ValueError 422 분류

```python
async def _handle_exception(self, request, exc):
    status_code = 500
    if isinstance(exc, ValueError):
        status_code = 422

    return JSONResponse(
        status_code=status_code,
        content=error_response.model_dump(...),
        ...
    )
```

### 7.3 Implementation Order (TDD)

1. [ ] `test_create_agent_use_case.py` — 명시적 도구 선택 테스트 작성 (Red)
2. [ ] `test_exception_handler_middleware.py` — ValueError → 422 테스트 작성 (Red)
3. [ ] `create_agent_use_case.py` — `_build_skeleton_from_configs()`, `_normalize_tool_id()` 구현 (Green)
4. [ ] `exception_handler_middleware.py` — ValueError 422 분류 구현 (Green)
5. [ ] 기존 테스트 실행 — regression 없음 확인
6. [ ] E2E: 프론트에서 Agent 생성 테스트

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] DDD 레이어 규칙 (domain → infrastructure 참조 금지)
- [x] TDD 필수 (테스트 먼저 작성)
- [x] 함수 40줄 초과 금지
- [x] 타입 힌트 필수

### 8.2 Environment Variables Needed

신규 환경변수 없음.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-09 | Initial draft | 배상규 |
