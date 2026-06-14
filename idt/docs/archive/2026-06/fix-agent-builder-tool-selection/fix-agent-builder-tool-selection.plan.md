# FIX-AGENT-BUILDER-TOOL-SELECTION: 에이전트 생성 시 선택한 도구가 서버로 전송되지 않는 버그 수정

> 상태: Plan
> 연관 Task: AB-TOOL-001
> 작성일: 2026-05-31
> 우선순위: High
> 범위: 풀스택 (idt 백엔드 + idt_front 프론트엔드)

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | `/agent-builder` 생성 화면에서 도구를 선택해도 선택한 도구 ID가 서버 요청 바디에 포함되지 않아, 사용자의 도구 선택이 무시되고 AI 자동 선택으로만 에이전트가 생성된다. |
| **Solution** | 프론트 `handleSave`에 `form.tools`를 `tool_ids`로 추가 전송하고, 백엔드 `CreateAgentRequest`에 `tool_ids` 필드를 추가하여 명시적 도구 선택 시 해당 도구로 스켈레톤을 구성한다(미선택 시 기존 AI 자동 선택 유지). |
| **Function/UX Effect** | 사용자가 고른 도구가 그대로 에이전트에 반영된다. 도구를 안 고르면 종전처럼 AI가 자동 선택한다. |
| **Core Value** | "선택한 대로 동작한다"는 예측 가능성 회복 — Agent Builder의 신뢰성·통제권 확보. |

---

## 1. 문제 정의 (Problem Statement)

`/agent-builder` 페이지에서 새 에이전트를 만들 때 도구(Excel 생성, Python 실행, Tavily 검색 등)를 선택하고 저장해도, **선택한 도구가 생성된 에이전트에 반영되지 않는다.**

사용자 관점: 도구를 분명히 선택(✓ 체크 표시까지 확인)했는데도 서버로 도구 리스트가 전달되지 않아, 의도와 다른 에이전트가 만들어지거나 도구 없이 생성된 것처럼 동작한다.

---

## 2. 근본 원인 분석 (Root Cause)

> **핵심: `useState` 저장 문제가 아니다.** `form.tools` state 값은 정상적으로 채워진다.
> 문제는 ① 저장 시 그 값을 요청 바디에 매핑하지 않는 것, ② 백엔드에 수신 필드가 없는 것 — 두 가지다.

### 2-1. [프론트엔드] `form.tools`는 정상 저장됨 (버그 아님)

**파일**: `idt_front/src/pages/AgentBuilderPage/index.tsx:170-188`

```javascript
const handleToolToggle = (toolId: string) => {
  setForm((prev) => {
    const isRemoving = prev.tools.includes(toolId);
    const newTools = isRemoving
      ? prev.tools.filter((t) => t !== toolId)
      : [...prev.tools, toolId];
    // ... RAG 도구일 때만 toolConfigs 갱신
    return { ...prev, tools: newTools, toolConfigs: newConfigs };  // ✅ form.tools 정상 갱신
  });
};
```

→ state(`form.tools`)에는 선택한 도구 ID가 정확히 들어가고, 화면 체크 표시도 이 값으로 렌더된다.

### 2-2. [프론트엔드] `handleSave`가 `form.tools`를 페이로드에 넣지 않음 (Critical)

**파일**: `idt_front/src/pages/AgentBuilderPage/index.tsx:140-167`

```javascript
// 생성(create) 분기
const toolConfigs = Object.keys(form.toolConfigs).length > 0 ? form.toolConfigs : undefined;
createMutation.mutate({
  user_request: form.description || form.name,
  name: form.name,
  llm_model_id: selectedModel?.id,
  temperature: form.temperature,
  tool_configs: toolConfigs,   // ❌ RAG 도구만. form.tools 는 어디에도 전달 안 됨
});
```

`form.tools`(선택한 도구 ID 배열)가 `createMutation.mutate` 페이로드 어디에도 포함되지 않는다.
RAG 도구(`internal:internal_document_search`)만 `toolConfigs`를 통해 우회 전달되고, 그 외 도구는 전부 누락된다.

### 2-3. [백엔드] `CreateAgentRequest`에 `tool_ids` 필드 부재 (Critical)

**파일**: `idt/src/application/agent_builder/schemas.py:34-43`

```python
class CreateAgentRequest(BaseModel):
    user_request: str = Field(..., max_length=1000)
    name: str = Field(..., max_length=200)
    user_id: str = ""
    llm_model_id: str | None = None
    visibility: str = Field("private", pattern="^(private|department|public)$")
    department_id: str | None = None
    temperature: float = Field(0.70, ge=0.0, le=2.0)
    tool_configs: dict[str, RagToolConfigRequest] | None = None   # ← 도구 설정만
    sub_agent_configs: list[SubAgentConfigRequest] | None = None
    # ❌ tool_ids 필드 자체가 없음 → 프론트가 보내도 받을 곳이 없음
```

`create_agent_use_case.execute`의 도구 결정 로직도 `tool_configs`(있으면 명시 스켈레톤) 또는 AI 자동 선택 두 갈래뿐이며, 명시적 `tool_ids` 경로가 없다(`create_agent_use_case.py:58-66`).

### 2-4. [제약] 현재 생성 플로우는 내부 도구 4종만 지원 (Scope 경계)

`create_agent_use_case.py:93`의 `tool_metas = [get_tool_meta(w.tool_id) ...]`와 `ToolSelector`(`tool_selector.py`)는 모두 `TOOL_REGISTRY`(내부 도구: `excel_export`, `internal_document_search`, `python_code_executor`, `tavily_search`)만 인식한다. **MCP 도구는 현재 생성 플로우에서 지원되지 않으며**, 명시적으로 넘겨도 `get_tool_meta`에서 `ValueError`가 발생한다. (참고: tool_id는 DB/카탈로그에서 `internal:` prefix 보유, 내부 로직은 `_normalize_tool_id`로 prefix 제거 후 사용)

---

## 3. 의도된 동작 (Decision)

> 생성 화면 UI는 도구 토글에 ✓ 체크를 표시하므로, **선택은 명시적 의미를 가져야 한다.**

| 사용자 행동 | 동작 |
|-------------|------|
| 도구를 1개 이상 선택 | 선택한 도구로 에이전트 구성 (명시적, AI 자동선택 미수행) |
| 도구를 하나도 선택 안 함 | 기존대로 `user_request` 기반 AI 자동 선택 |
| RAG 도구 선택 + 설정 | `tool_ids`에 포함 + 해당 `tool_configs`를 매칭하여 설정 적용 |

---

## 4. 수정 범위 (Scope)

| # | 수정 위치 | 내용 | 우선순위 |
|---|-----------|------|----------|
| 1 | `schemas.py` `CreateAgentRequest` | `tool_ids: list[str] | None = None` 필드 추가 | Critical |
| 2 | `create_agent_use_case.py` `execute()` | `tool_ids` 우선 분기 추가 (`tool_ids` → `tool_configs` → AI 자동) | Critical |
| 3 | `create_agent_use_case.py` | `_build_skeleton_from_tool_ids(tool_ids, tool_configs)` 신규 메서드 | Critical |
| 4 | `agentBuilder.ts` `CreateBuilderAgentRequest` | `tool_ids?: string[]` 필드 추가 (API 계약 동기화) | Critical |
| 5 | `AgentBuilderPage/index.tsx` `handleSave` | `tool_ids: form.tools.length > 0 ? form.tools : undefined` 전송 | Critical |
| 6 | `AgentBuilderPage/index.tsx` (UI 가드) | MCP 도구는 생성 단계 미지원 — 비활성/툴팁 안내 또는 전송 제외 | Medium |

---

## 5. 수정 방향 (Solution Design)

### 5-1. 백엔드: `CreateAgentRequest`에 `tool_ids` 추가

```python
class CreateAgentRequest(BaseModel):
    # ... 기존 필드 ...
    tool_ids: list[str] | None = None           # ✅ 명시적 도구 선택
    tool_configs: dict[str, RagToolConfigRequest] | None = None
    sub_agent_configs: list[SubAgentConfigRequest] | None = None
```

### 5-2. 백엔드: 도구 결정 분기 (우선순위)

```python
# create_agent_use_case.py execute() Step 1
if request.tool_ids:
    skeleton = self._build_skeleton_from_tool_ids(
        request.tool_ids, request.tool_configs, request_id
    )
elif request.tool_configs:
    skeleton = self._build_skeleton_from_configs(request.tool_configs, request_id)
else:
    skeleton = await self._selector.select(request.user_request, request_id)
```

### 5-3. 백엔드: `_build_skeleton_from_tool_ids`

```python
def _build_skeleton_from_tool_ids(
    self,
    tool_ids: list[str],
    tool_configs: dict[str, RagToolConfigRequest] | None,
    request_id: str,
) -> WorkflowSkeleton:
    # tool_configs 키를 normalize 하여 tool_id 매칭용 맵 구성
    configs_by_id = {
        self._normalize_tool_id(k): v for k, v in (tool_configs or {}).items()
    }
    workers: list[WorkerDefinition] = []
    for i, raw_id in enumerate(tool_ids):
        tool_id = self._normalize_tool_id(raw_id)
        meta = get_tool_meta(tool_id)           # 내부 도구만 유효 (§2-4 제약)
        cfg = configs_by_id.get(tool_id)
        workers.append(WorkerDefinition(
            tool_id=tool_id,
            worker_id=f"{tool_id}_worker",
            description=meta.description,
            sort_order=i,
            tool_config=cfg.model_dump() if cfg else None,
        ))
    flow_hint = " → ".join(w.tool_id for w in workers)
    self._logger.info(
        "Built skeleton from tool_ids",
        request_id=request_id, tool_ids=[w.tool_id for w in workers],
    )
    return WorkflowSkeleton(workers=workers, flow_hint=flow_hint)
```

> `get_tool_meta`가 미등록 도구(MCP 등)에 `ValueError`를 던지므로, 라우터에서 422로 매핑하거나
> 프론트에서 MCP 도구 선택을 차단(§5-5)하여 방어한다.

### 5-4. 프론트엔드: 타입 + 전송

```typescript
// types/agentBuilder.ts
export interface CreateBuilderAgentRequest {
  user_request: string;
  name: string;
  llm_model_id?: string;
  visibility?: 'private' | 'department' | 'public';
  department_id?: string;
  temperature?: number;
  tool_ids?: string[];                                  // ✅ 추가
  tool_configs?: Record<string, RagToolConfig>;
}
```

```typescript
// AgentBuilderPage/index.tsx handleSave (create 분기)
createMutation.mutate({
  user_request: form.description || form.name,
  name: form.name,
  llm_model_id: selectedModel?.id,
  temperature: form.temperature,
  tool_ids: form.tools.length > 0 ? form.tools : undefined,   // ✅ 선택 도구 전송
  tool_configs: toolConfigs,
});
```

### 5-5. 프론트엔드: MCP 도구 생성 단계 가드 (Medium)

생성 플로우가 내부 도구만 지원하므로(§2-4), 카탈로그에서 `source === 'mcp'`인 도구는:
- (택1-A) 생성 모드에서 비활성화 + "생성 후 편집에서 연결 가능" 툴팁, 또는
- (택1-B) 전송 시 `tool_ids`에서 제외

> 본 Plan은 내부 도구 명시 선택 end-to-end 동작을 1차 목표로 하고, MCP 도구 생성-시 연결은 후속 과제로 분리한다.

---

## 6. 영향 범위 (Impact)

### 변경 파일 목록
- `idt/src/application/agent_builder/schemas.py` (백엔드 — 스키마)
- `idt/src/application/agent_builder/create_agent_use_case.py` (백엔드 — UseCase)
- `idt_front/src/types/agentBuilder.ts` (프론트 — 타입)
- `idt_front/src/pages/AgentBuilderPage/index.tsx` (프론트 — 전송/가드)

### 영향을 받지 않는 것
- DB 스키마 변경 없음 (기존 `agent_tool`, `tool_catalog` 구조 유지)
- 수정(edit) 플로우 변경 없음 (현재도 도구 변경 미지원, 본 Plan 범위 외)
- AI 자동 선택 경로 유지 (도구 미선택 시 동일 동작 — 하위 호환)
- RAG `tool_configs` 단독 경로 유지 (백워드 호환)
- `CreateAgentResponse` 스키마 변경 없음

### API 계약 동기화 (CLAUDE.md §4-1)
- 백엔드 `CreateAgentRequest` ↔ 프론트 `CreateBuilderAgentRequest` 동시 수정 필수.

---

## 7. TDD 계획

### 백엔드 테스트
**파일**: `idt/tests/application/agent_builder/test_create_agent_use_case.py`

| 테스트 케이스 | 설명 |
|--------------|------|
| `test_explicit_tool_ids_builds_skeleton` | `tool_ids` 전달 시 해당 도구로 워커 구성, AI 셀렉터 미호출 |
| `test_tool_ids_with_rag_config_merges_config` | `tool_ids` + 매칭 `tool_configs` 시 `tool_config` 주입 확인 |
| `test_empty_tool_ids_falls_back_to_ai_selection` | `tool_ids` 미전달 시 기존 AI 자동 선택 경로 동작 |
| `test_tool_ids_prefix_normalized` | `internal:tavily_search` → `tavily_search` 정규화 확인 |
| `test_unknown_tool_id_raises_value_error` | 미등록(MCP 등) tool_id 시 `ValueError` 발생 확인 |

**파일**: `idt/tests/application/agent_builder/test_schemas.py` (또는 라우터 테스트)
| `test_create_request_accepts_tool_ids` | `CreateAgentRequest`가 `tool_ids` 수용 확인 |

### 프론트엔드 테스트
**파일**: `idt_front/src/__tests__/AgentBuilderPage.test.tsx` (MSW)

| 테스트 케이스 | 설명 |
|--------------|------|
| `test_selected_tools_sent_as_tool_ids` | 도구 선택 후 저장 시 요청 바디에 `tool_ids` 포함 확인 |
| `test_no_tool_selected_omits_tool_ids` | 미선택 시 `tool_ids`가 undefined(미전송) 확인 |
| `test_mcp_tool_not_sent_or_disabled` | MCP 도구는 전송 제외/비활성 확인 (§5-5 채택안 기준) |

---

## 8. 완료 기준 (Definition of Done)

- [ ] 백엔드: `CreateAgentRequest.tool_ids` 필드 추가
- [ ] 백엔드: `execute()` 분기에서 `tool_ids` 우선 처리
- [ ] 백엔드: `_build_skeleton_from_tool_ids` 구현 (RAG config 매칭 포함)
- [ ] 프론트: `CreateBuilderAgentRequest.tool_ids` 타입 추가
- [ ] 프론트: `handleSave`에서 `form.tools` → `tool_ids` 전송
- [ ] 프론트: MCP 도구 생성-시 가드(§5-5) 적용
- [ ] 백엔드 신규 테스트 6개 통과
- [ ] 프론트 신규 테스트 3개 통과
- [ ] 실제 화면에서 내부 도구 선택 → 그 도구로 에이전트 생성 확인
- [ ] 도구 미선택 시 AI 자동 선택 정상 동작 확인 (하위 호환)
- [ ] `/verify-architecture` 통과
- [ ] `/verify-logging` 통과
- [ ] `/verify-tdd` 통과
- [ ] `/api-contract-sync` 체크리스트 통과

---

## 9. 참고 문서 / 코드

- `idt_front/src/pages/AgentBuilderPage/index.tsx` (140-188 — handleSave/handleToolToggle)
- `idt_front/src/types/agentBuilder.ts`
- `idt/src/application/agent_builder/schemas.py` (34-43)
- `idt/src/application/agent_builder/create_agent_use_case.py` (46-181)
- `idt/src/application/agent_builder/tool_selector.py`
- `idt/src/domain/agent_builder/tool_registry.py`
- `idt/db/migration/V008__seed_internal_tools.sql` (tool_id `internal:` prefix 규칙)
