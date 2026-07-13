# agent-instruction-required Design Document

> **Summary**: 에이전트 생성/수정 시 지침(system_prompt) 필수화 + 레거시 자동생성 경로(PromptGenerator·ToolSelector·interview) 전면 삭제 설계
>
> **Project**: sangplusbot (idt 백엔드 + idt_front 프론트엔드)
> **Author**: 배상규
> **Date**: 2026-07-06
> **Status**: Draft
> **Planning Doc**: [agent-instruction-required.plan.md](../../01-plan/features/agent-instruction-required.plan.md)

---

## 1. Overview

### 1.1 Design Goals

1. **지침 필수화**: 생성·수정 API 모두 `system_prompt`가 비어 있으면(공백 포함) 422 에러. 프론트는 저장 전에 차단하고 지침 입력란에 인라인 에러 표시.
2. **자동생성 경로 완전 삭제**: `PromptGenerator`, `ToolSelector`, interview 흐름(엔드포인트 3종 + 유스케이스 + 세션 스토어 + Interviewer)을 코드베이스에서 제거. 자동 구성은 Fix 에이전트(agent_composer)가 유일한 경로.
3. **도구 0개 허용**: `tool_ids`/`tool_configs` 미제공 시 에러 없이 워커 0개로 생성. 실행 시 supervisor가 직접 답변(FINISH + answer)하는 순수 대화형 에이전트로 동작.
4. **생성 호출 단순화**: 프론트 create→update 2-call 패치를 create 1-call로 통합.

### 1.2 Design Principles

- 검증 규칙은 domain policy(`AgentBuilderPolicy`)에 단일 정의 — create/update가 같은 규칙을 공유
- 스키마(`CreateAgentRequest.system_prompt`)는 `str | None` 유지, 필수성은 policy가 강제 (v1 스키마 파급 최소화 — Plan §6.2)
- 삭제는 배선(main.py DI)까지 완결 — 미사용 의존성 잔존 금지
- 기존 라우터의 ValueError→HTTP 매핑(`_attach_skill_http_error`) 재사용, 새 에러 코드 도입 없음

### 1.3 사전 검증 결과 (Plan §5 리스크 해소)

**0-worker 실행 경로 — 구조적으로 이미 지원됨을 확인:**
- `supervisor_nodes.py:130-133` — 워커 목록이 비면 `worker_descriptions=""`, `available_ids=∅`로 프롬프트 구성만 달라짐 (컴파일 에러 없음)
- `supervisor_nodes.py:203-215` — LLM이 FINISH 선택 + `last_worker_id` 없음 → `decision.answer`를 AIMessage로 추가하고 `__end__` 라우팅 = **supervisor 직접 답변 경로가 이미 존재**
- `route_to_worker_or_final`(L297-306) — `last_worker_id`가 없으면 final_answer 우회 없이 즉시 종료
- **잔여 리스크 1건**: `workflow_compiler.compile()`에서 워커 0개면 `quality_gate` 노드가 정적으로 도달 불가(진입 간선 0개)가 됨. LangGraph 버전에 따라 unreachable 노드 검증 에러 가능 → §3.6에서 조건부 등록으로 제거

---

## 2. Architecture

### 2.1 변경 전후 흐름

```
[변경 전 — 생성]
FE handleSave ─ create(system_prompt 없음) ─▶ CreateAgentUseCase
                                               ├─ tool_ids 없으면 ToolSelector(LLM) 자동선택
                                               ├─ system_prompt 없으면 PromptGenerator(LLM) 자동생성
                                               └─ 저장
FE onSuccess ─ update(system_prompt) ─▶ 덮어쓰기   ← 2-call

[변경 후 — 생성]
FE handleSave ─ 검증(name·systemPrompt) 실패 시 인라인 에러 + 차단
             └ create(system_prompt 포함) ─▶ CreateAgentUseCase          ← 1-call
                                               ├─ tool_ids 없으면 워커 0개 (에러 아님)
                                               ├─ validate_system_prompt: 빈 값 → ValueError → 422
                                               └─ 저장
```

### 2.2 삭제되는 컴포넌트

```
src/application/agent_builder/
├── prompt_generator.py          ← 삭제 (유일 소비자: create fallback·interview)
├── tool_selector.py             ← 삭제 (유일 소비자: create 자동선택·interview)
├── interviewer.py               ← 삭제 (interview 전용)
├── interview_use_case.py        ← 삭제
└── interview_session_store.py   ← 삭제

/api/v1/agents/interview                    ← 엔드포인트 삭제 (router L409-457)
/api/v1/agents/interview/{sid}/answer
/api/v1/agents/interview/{sid}/finalize
```

**비영향 확인 (Plan §1.2)**: `/api/v3/agents/auto`는 `CreateMiddlewareAgentRequest`(v2 경로)를 사용하고 항상 `system_prompt`를 채움. Fix 에이전트(agent_composer)는 독립 모듈(compose → 폼 프리필). 둘 다 이번 삭제 대상과 import 관계 없음 (`composer.py:4`는 주석 언급뿐).

---

## 3. Backend Detailed Design

### 3.1 D1 — `domain/agent_builder/policies.py`

```python
class AgentBuilderPolicy:
    # MIN_TOOLS = 1   ← 삭제
    # MIN_WORKERS = 1 ← 삭제
    MAX_TOOLS = 5            # 유지
    MAX_WORKERS_TOTAL = ...  # 유지
    MAX_SUB_AGENTS = ...     # 유지

    @classmethod
    def validate_tool_count(cls, count: int) -> None:
        # 하한 검증 삭제 — 도구 0개 허용 (agent-instruction-required)
        if count > cls.MAX_TOOLS:
            raise ValueError(f"도구는 최대 {cls.MAX_TOOLS}개까지 선택할 수 있습니다.")

    @classmethod
    def validate_worker_count(cls, workers: list) -> None:
        # 하한 검증 삭제 — 이하 상한(MAX_WORKERS_TOTAL/MAX_TOOLS/MAX_SUB_AGENTS) 유지
        ...

    @classmethod
    def validate_system_prompt(cls, prompt: str) -> None:
        # 빈 값 검증 추가 (validate_name과 동일 패턴)
        if not prompt or not prompt.strip():
            raise ValueError(
                "지침(system_prompt)은 비어 있을 수 없습니다. "
                "직접 입력하거나 Fix 에이전트로 초안을 생성해 주세요."
            )
        if len(prompt) > cls.MAX_SYSTEM_PROMPT_LENGTH:
            raise ValueError(...)  # 기존 유지
```

- `UpdateAgentPolicy.validate_update`(L193-197)는 변경 불필요 — `system_prompt is not None`일 때 `validate_system_prompt`를 이미 호출하므로 빈 문자열이 자동으로 거부됨. `None`(변경 안 함)은 기존대로 통과.
- 에러 메시지에 "찾을 수 없"/"이미 부착"/"최대" 부분열 금지 — 라우터 `_attach_skill_http_error`(L621-627)·update 매핑(L268-274)이 404/409로 오분류하지 않도록. 위 문구는 안전(→ 422).

### 3.2 D2 — `application/agent_builder/create_agent_use_case.py`

**생성자**: `tool_selector`, `prompt_generator` 파라미터 삭제 (`self._selector`/`self._generator` 제거).

**Step 1** (L87-100): 자동선택 분기 제거.

```python
if request.tool_ids:
    skeleton = await self._build_skeleton_from_tool_ids(...)
elif request.tool_configs:
    skeleton = self._build_skeleton_from_configs(...)
else:
    # 도구 미지정 = 워커 0개 순수 대화형 에이전트 (agent-instruction-required)
    skeleton = WorkflowSkeleton(workers=[], flow_hint="")
```

**Step 3** (L143-153): 자동생성 fallback 제거 — policy 검증만 남김.

```python
# Step 3: 시스템 프롬프트 필수 (자동생성은 Fix 에이전트 전담)
AgentBuilderPolicy.validate_system_prompt(request.system_prompt or "")
system_prompt = request.system_prompt
```

**부수 정리**: `_resolve_prompt_tool_meta`(L312-321)는 프롬프트 생성 전용이므로 함께 삭제. `PromptGenerator`/`ToolSelector` import 제거. `schemas.py:73`의 `system_prompt` 주석을 "필수 — 비우면 에러(자동생성 제거)"로 갱신. 검증 순서는 기존 Step 2(name) 뒤 Step 3 유지 — name 에러가 우선되는 현행 동작 보존.

### 3.3 D3 — interview 흐름 삭제

| 위치 | 삭제 내용 |
|------|----------|
| `api/routes/agent_builder_router.py` | L409-457 엔드포인트 3종, L77-78 `get_interview_use_case`, interview 스키마 import |
| `application/agent_builder/schemas.py` | `InterviewStartRequest/Response`, `InterviewAnswerRequest/Response`, `InterviewFinalizeRequest` (grep으로 전수 확인 후 삭제) |
| `application/agent_builder/` | `interview_use_case.py`, `interviewer.py`, `interview_session_store.py` 파일 삭제 |
| `api/main.py` | L85 import, L284-286 import 3줄, L1986 `interviewer`, L2089 `interview_session_store`, L2191-2200 `interview_uc_factory`, L2257 참조, L3105·3116 dependency_overrides |

### 3.4 D4 — PromptGenerator·ToolSelector 삭제

| 위치 | 삭제 내용 |
|------|----------|
| `application/agent_builder/prompt_generator.py`, `tool_selector.py` | 파일 삭제 |
| `api/main.py` | L271-272 import, L1984-1985 인스턴스, L2122-2123 create_uc_factory 인자 |
| `domain/agent_builder/schemas.py` | L58 근처 `_SkeletonOutput` 등 ToolSelector 전용 스키마 — 다른 소비자 없으면 삭제, 있으면 유지 (Do 단계 grep 확인) |

### 3.5 D5 — API 계약 (변경 후)

#### `POST /api/v1/agents`

| 필드 | 변경 전 | 변경 후 |
|------|---------|---------|
| `system_prompt` | optional — 없으면 LLM 자동생성 | **사실상 필수** — 없음/공백이면 422 (스키마 타입은 `str \| None` 유지, policy 검증) |
| `tool_ids`/`tool_configs` | 없으면 LLM 도구 자동선택 | 없으면 워커 0개로 생성 (200 정상) |

**에러 응답 (422)**:
```json
{ "detail": "지침(system_prompt)은 비어 있을 수 없습니다. 직접 입력하거나 Fix 에이전트로 초안을 생성해 주세요." }
```

#### `PATCH /api/v1/agents/{agent_id}`

| 값 | 동작 |
|----|------|
| `system_prompt: null` / 필드 생략 | 변경 안 함 (기존 유지) |
| `system_prompt: ""` 또는 공백 | **422** (기존: MAX 길이만 검증 → 빈 값 통과되어 저장됨) |

#### 삭제: `POST /interview`, `POST /interview/{sid}/answer`, `POST /interview/{sid}/finalize` → 404

### 3.6 D6 — `workflow_compiler.py` 0-worker 대응

워커 0개일 때 `quality_gate` 노드가 진입 간선 없는 고아 노드가 됨(L321-324 등록, L399-404 워커→gate 간선이 0개, L423-426 gate 발신 간선만 존재). LangGraph unreachable 검증 대비 + 그래프 명료화를 위해 **조건부 등록**으로 변경:

```python
# quality_gate: 워커가 있을 때만 등록 (0-worker 그래프에서 고아 노드 방지)
if worker_map:
    graph.add_node("quality_gate", _wrap_step(...))
...
if worker_map:
    qg_route_map = {"supervisor": "supervisor"}
    for wid in worker_map:
        qg_route_map[wid] = wid
    graph.add_conditional_edges("quality_gate", route_after_quality, qg_route_map)
```

- `final_answer`(depth=0)는 supervisor 조건부 간선의 정적 타깃이므로 **무조건 등록 유지** (0-worker 런타임에선 `route_to_worker_or_final`이 `last_worker_id` 부재로 경유하지 않음 — 정상)
- supervisor 노드·라우팅 함수는 무변경 (§1.3 검증 완료)
- `RunAgentUseCase`는 `compile()` 결과만 소비 — 워커 수 가정 없음 확인, 무변경. 단 0-worker 실행 통합 테스트로 보증(§8)

---

## 4. Frontend Detailed Design

### 4.1 `types/agentBuilder.ts` — API 계약 동기화

```typescript
export interface CreateBuilderAgentRequest {
  user_request: string;
  name: string;
  /** agent-instruction-required: 지침 필수 — 비우면 백엔드 422 */
  system_prompt: string;
  // ...나머지 기존 필드 유지
}
```

`UpdateBuilderAgentRequest.system_prompt?: string`은 타입 유지 (PATCH 의미상 optional — "빈 문자열 금지"는 페이지 검증이 담당).

### 4.2 `pages/AgentBuilderPage/index.tsx`

**상태 추가**:
```typescript
const [promptError, setPromptError] = useState<string | null>(null);
```

**handleSave 검증** (생성·수정 공통, name 검증 다음):
```typescript
if (!form.systemPrompt.trim()) {
  setPromptError('지침을 입력해주세요. Fix 에이전트 탭에서 초안을 생성할 수도 있습니다.');
  return;
}
setPromptError(null);
```

**생성 1-call 통합** (L176-198):
- `createMutation.mutate({ ..., system_prompt: form.systemPrompt, ... })`
- onSuccess의 `if (form.systemPrompt.trim()) updateMutation.mutate(...)` 패치 블록(L193-198) **삭제** (스케줄 순차 등록 로직은 유지)

**수정 모드** (L138): `system_prompt: form.systemPrompt || undefined` → `system_prompt: form.systemPrompt` (검증 통과 후이므로 항상 non-empty)

**에러 해제**: `systemPrompt` 변경 시 초기화 — `setForm` 래퍼 또는 `useEffect(() => setPromptError(null), [form.systemPrompt])` 중 후자 채택(변경점 최소). `handleNew`/`handleEdit` 진입 시에도 초기화.

### 4.3 `StudioLayout.tsx` / `LeftConfigPanel.tsx`

**prop 파이프라인**: `AgentBuilderPage → StudioLayout → LeftConfigPanel`에 `systemPromptError?: string | null` 추가.

**LeftConfigPanel 지침 섹션** (L202-219):

```tsx
<CollapsibleSection title="지침">   {/* title 옆 필수 뱃지 추가 */}
  <div className={`... ${systemPromptError
    ? 'border-red-300 focus-within:border-red-400 focus-within:ring-red-100'
    : 'border-zinc-300 focus-within:border-violet-400 focus-within:ring-violet-100'}`}>
    <textarea
      placeholder="에이전트의 시스템 프롬프트/지침을 입력하세요..."  {/* isEditMode 분기 제거 */}
      ...
    />
  </div>
  {systemPromptError ? (
    <p role="alert" className="mt-1 text-[11.5px] text-red-500">{systemPromptError}</p>
  ) : (
    <p className="mt-1 text-right text-[11.5px] text-zinc-400">{form.systemPrompt.length}자</p>
  )}
</CollapsibleSection>
```

- placeholder의 "비워두면 AI가 설명을 기반으로 자동 생성합니다" 문구 삭제 (FR-08)
- 필수 표기: 섹션 제목을 `지침` + `필수` 뱃지(`text-[10px] text-red-400`)로 표시 — `CollapsibleSection`의 `action` prop 재사용 또는 title 문자열 `"지침 *"` 중 Do 단계에서 CollapsibleSection 시그니처에 맞춰 선택
- Fix 에이전트 초안 적용(`handleApplyDraft` → `systemPrompt` 셋팅)은 무변경 — 적용 시 promptError 자동 해제(4.2 useEffect)

### 4.4 서비스/훅

`agentBuilderService`·`useAgentBuilder` 훅은 요청 타입만 바뀌므로 **코드 변경 없음** (타입 컴파일로 전파 확인).

---

## 5. Error Handling

| 상황 | 계층 | 결과 |
|------|------|------|
| 프론트: 지침 공백 저장 시도 (생성/수정) | 페이지 검증 | API 미호출, 지침 섹션 인라인 에러(`role="alert"`) + red 보더 |
| API 직접 호출: create `system_prompt` 없음/공백 | `validate_system_prompt` | ValueError → `_attach_skill_http_error` → **422** |
| API 직접 호출: update `system_prompt: ""` | `validate_update` → `validate_system_prompt` | ValueError → 라우터 매핑 → **422** |
| API 직접 호출: update `system_prompt: null` | — | 변경 안 함 (기존 동작 유지) |
| create 도구 미지정 | — | 워커 0개 정상 생성 (`flow_hint=""`) |
| 0-worker 에이전트 run | supervisor FINISH+answer | 일반 LLM 답변으로 정상 응답 |
| interview 엔드포인트 호출 | — | 404 (라우트 삭제) |

프론트 API 에러(422)는 기존 `saveResult` 다이얼로그 경로로 표면화 (이중 안전망).

---

## 6. Security Considerations

- [x] 입력 검증 강화: 빈 지침 서버측 검증 추가 (클라이언트 우회 방지)
- [x] 인증: 기존 `get_current_user` 의존성 무변경
- [x] LLM 호출 표면 축소: 미인증 입력이 LLM 프롬프트로 흘러가는 경로 2곳(ToolSelector/PromptGenerator) 제거
- [ ] 신규 비밀정보/환경변수: 없음

---

## 7. Clean Architecture 배치

| 변경 | Layer | 파일 |
|------|-------|------|
| 빈 지침 검증 규칙 | Domain | `src/domain/agent_builder/policies.py` |
| 하한 정책 완화 | Domain | 동일 |
| 자동생성 분기 제거 (흐름 제어) | Application | `create_agent_use_case.py`, `workflow_compiler.py` |
| 파일 삭제 | Application | `prompt_generator.py` 외 4 |
| 엔드포인트 삭제·에러 매핑 | Interfaces | `agent_builder_router.py` |
| DI 배선 정리 | Interfaces | `api/main.py` |
| 요청 타입 | FE Domain | `src/types/agentBuilder.ts` |
| 저장 검증·1-call 통합 | FE Presentation | `pages/AgentBuilderPage/index.tsx` |
| 인라인 에러 UI | FE Presentation | `components/agent-builder/LeftConfigPanel.tsx`, `StudioLayout.tsx` |

금지사항 준수: domain은 외부 의존 없음(문자열 검증만), 라우터에 비즈니스 로직 추가 없음, print 없음(기존 logger 유지).

---

## 8. Test Plan

### 8.1 백엔드 (pytest — Red → Green)

**삭제** (대상 기능 소멸):
- `tests/application/agent_builder/test_prompt_generator.py`
- `tests/application/agent_builder/test_tool_selector.py`
- `tests/application/agent_builder/test_interview_use_case.py`
- `tests/application/agent_builder/test_interviewer.py`

**수정** (자동생성/자동선택 기대 제거, fixture에서 selector/generator 인자 제거):
- `tests/application/agent_builder/test_create_agent_use_case.py` (32 hits)
- `tests/application/agent_builder/test_create_agent_use_case_mcp.py` (9 hits)
- `tests/application/agent_builder/test_create_agent_prompt_prefill.py` (10 hits — "프리필 우선" 테스트는 "필수값" 테스트로 개편)
- `tests/application/agent_builder/test_create_agent_document_template.py` (2 hits)
- `tests/api/test_agent_builder_router.py` (30 hits — interview 라우트 테스트 삭제 포함)

**신규**:
- [ ] create: `system_prompt` 없음/공백/공백문자만 → ValueError("비어 있을 수 없습니다")
- [ ] create: `tool_ids` 없음 + `system_prompt` 있음 → 워커 0개·`flow_hint=""` 정상 생성
- [ ] update: `system_prompt=""`/`"   "` → ValueError, `None` → 통과(변경 안 함)
- [ ] policy: `validate_tool_count(0)`/`validate_worker_count([])` 통과, 상한 초과 여전히 에러
- [ ] router: create 빈 지침 → 422 + 메시지, interview 경로 → 404
- [ ] compiler: `compile(workers=[])` 성공 + `ainvoke` 시 supervisor FINISH-answer로 종료 (quality_gate 미등록 확인)

### 8.2 프론트 (vitest + RTL + MSW — 파일별 server.listen 3종 훅 필수)

**수정**:
- `LeftConfigPanel.test.tsx`: placeholder 통일 검증(자동생성 문구 부재), `systemPromptError` 표시/`role="alert"`
- AgentBuilderPage 관련 테스트: 지침 공백 저장 → mutation 미호출 + 에러 표시, 지침 입력 후 저장 → create 본문에 `system_prompt` 포함(1-call, update 미호출)

**회귀 보호**:
- Fix 초안 적용 → systemPrompt 프리필 → 저장 성공 (FixAgentPanel 흐름)
- 수정 모드: 기존 지침 로드 → 지우고 저장 → 차단

### 8.3 실행 주의 (환경 메모)

- 백엔드 pytest 교차 실행 시 Windows 이벤트 루프 teardown 산발 실패 → 모듈 격리 실행으로 검증
- 프론트 vitest는 `--pool=threads` 사용
- 사전 실패(pre-existing) 목록과 대조해 신규 회귀만 판정

---

## 9. Implementation Order

1. [ ] **BE-1 (TDD)**: `policies.py` — validate_system_prompt 빈 값 / 하한 완화 테스트 → 구현
2. [ ] **BE-2 (TDD)**: `create_agent_use_case.py` — 빈 지침 에러·0-tool 생성·자동생성 제거 테스트 수정/추가 → 구현 (생성자 시그니처 변경 포함)
3. [ ] **BE-3 (TDD)**: `workflow_compiler.py` — 0-worker compile/실행 테스트 → 조건부 quality_gate 구현
4. [ ] **BE-4**: interview·PromptGenerator·ToolSelector 파일 삭제 + `agent_builder_router.py`·`schemas.py`·`main.py` 배선 정리 + 관련 테스트 삭제
5. [ ] **BE-5**: `tests/api/test_agent_builder_router.py` 정리 + 백엔드 전체 회귀 확인
6. [ ] **FE-1 (TDD)**: `types/agentBuilder.ts` `system_prompt` 추가 → AgentBuilderPage 검증·1-call 테스트 → 구현
7. [ ] **FE-2 (TDD)**: StudioLayout·LeftConfigPanel `systemPromptError` 전달·표시 테스트 → 구현 (placeholder 문구 교체)
8. [ ] **FE-3**: type-check·lint·vitest 회귀 확인
9. [ ] 백엔드·프론트 **동일 PR** (breaking change 동시 배포 — Plan §5)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-06 | Initial draft — 0-worker 경로 사전 검증(supervisor FINISH-answer 확인, quality_gate 고아 노드 이슈 도출), 삭제 대상 테스트 5+5 파일 확정 | 배상규 |
