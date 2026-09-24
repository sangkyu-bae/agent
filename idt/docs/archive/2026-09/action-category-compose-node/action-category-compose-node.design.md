# action-category-compose-node Design Document

> **Summary**: `action` 카테고리 워커를 collect와 동형인 함수형 노드로 구현한다. "compose(에이전트 모델) → 초안 → 인자 조립(본문 결정적 덮어쓰기 + 나머지 보조 LLM) → 게이트면 `approval_pending`, 아니면 도구 1회 호출". 폴백 카테고리를 `None`으로 정정하고, final_answer는 도메인 정책 한 곳이 결정하는 "초안 보존 모드"를 갖는다.
>
> **Project**: sangplusbot (idt)
> **Version**: —
> **Author**: 배상규
> **Date**: 2026-09-23
> **Status**: Draft (v0.1)
> **Plan**: `docs/01-plan/features/action-category-compose-node.plan.md` (v0.1)
> **Selected Architecture**: Option C — 실용 균형

### Pipeline References

- collect 노드 계약: `src/application/agent_builder/collect_pipeline.py` (`create_collect_node`, `CollectArguments`, `_resolve_input_schema`, `_build_payload`, `_invoke_once`)
- 산출 규약: `src/application/agent_builder/search_pipeline.py` (`SEARCH_RESULT_MARKER`, `format_search_result`, `is_search_result`, `latest_user_question`)
- 게이트 판정: `workflow_compiler._approval_gate_middleware` (`ApprovalPolicy.should_gate`), `GatedWorkerPolicy.collect_gated_tool_ids`
- 신호 규약: `src/domain/approval/policies.py` (`ApprovalSignalPolicy.render/extract`), `workflow_compiler._extract_approval_pending`
- 재개: `run_agent_use_case._restore_state` (outcome을 `AIMessage(name=worker_id)`로 주입)
- 런당 1회: `src/application/agent_builder/worker_run_cap_hooks.py`
- VO 선례: `src/domain/document_generator/tool_config.py`

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 부작용 도구의 본문을 react가 도구 인자로 지어내고, 게이트는 그걸 휴리스틱으로 추측하며, final_answer가 다시 쓴다 — 승인된 초안과 나간 본문과 보이는 답변이 서로 다를 수 있다. |
| **WHO** | P2 에이전트 소유자(부작용 도구를 붙이고 승인) + 최종 사용자(초안·집행 결과를 그대로 봄) + 관리자(카탈로그에서 action 지정) |
| **RISK** | ① final_answer가 프롬프트만으로는 초안을 100% 보존하지 못할 수 있음 → 정책 객체 격리. ② 재개 런 이중 실행 → run cap. ③ 폴백 계약 변경이 테스트 계약을 깸 → 기대값 갱신. |
| **SUCCESS** | 명시 action 워커 런에서 도구 호출 정확히 1회(게이트 시 0회), 승인 `draft` == 초안 원문 == 발송 인자 본문, 최종 답변에 초안 원문 포함, 미분류 워커 회귀 0. |
| **SCOPE** | In: action 노드·VO·폴백 정정·정책 확장·final_answer 정책·승인 신호 노드 직접 생성·관측. Out: 프론트 UI, 초안 전용 모드, 승인 화면 편집, 메일 특화, 내장 send. |

---

## 1. Overview

### 1.1 Design Goals

1. **한 문자열.** 초안이 노드에서 한 번 만들어지고, 승인 `draft`·발송 인자 본문·최종 답변 포함분이 모두 같은 문자열이다.
2. **collect 동형.** 시그니처·반환 계약(AD-1)·실패 분기 철학(예외를 올리지 않음)·산출 1 AIMessage 계약을 그대로 따른다. 리뷰·테스트 패턴 재사용.
3. **교체 지점 1곳.** final_answer 모드 결정과 블록 구성은 `FinalAnswerDraftPolicy` 하나가 소유한다(사용자 결정 "변경 용이하게").
4. **무회귀.** 미분류(`None`) 워커·search/collect/analysis·초안 없는 final_answer 프롬프트는 바이트 단위로 불변.
5. **코어에 메일 지식 없음.** 노드는 "본문 키·inputSchema·도구 1회 호출"만 안다.

### 1.2 Design Principles

- **fail-closed.** 게이트 대상인데 신호가 못 올라가는 경로, 본문 키가 없는데 발송되는 경로는 없어야 한다. 애매하면 실행하지 않고 드러낸다.
- **초안이 이긴다.** 인자 조립 LLM이 무엇을 채우든 본문 키는 초안 원문으로 마지막에 덮어쓴다.
- **재시도 없음.** dispatch는 1회. 비가역 작업의 재시도는 이중 집행(Phase 2 FR-04 계승).
- **값은 로그에 남기지 않는다.** 초안·수신자 등 인자 값은 로그·스텝 요약에서 제외, 키 목록·길이만.
- **domain은 문자열·dict만.** LangChain 메시지·MCP 어댑터 참조는 application에 가둔다.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| 항목 | A. 최소 변경 | B. 클린 분리 | **C. 실용 균형 (선택)** |
|---|---|---|---|
| 노드 위치 | 컴파일러 안 클로저 | `action_pipeline.py` + Composer/Dispatcher/Assembler 클래스 | `action_pipeline.py` 함수형 모듈(collect 동형) |
| 게이트 판정 | 컴파일러가 bool 캡처 | domain `GateDecision` 객체 신설 | `_should_gate_worker()` 추출, 미들웨어·노드 공유, 노드엔 bool |
| 초안 규약 | 컴파일러 상수 | 신규 markers 모듈 | `search_pipeline.py`에 동거(단일 출처) |
| final_answer | 노드 내 if + 문자열 | 정책 + 블록 빌더 클래스 | `FinalAnswerDraftPolicy`(domain) 1곳 |
| 신규 파일 | 1 | 6~7 | 3 |
| 변경 용이성 | 낮음 | 높음 | 높음 |
| 리스크 | 40줄 규칙·컴파일러 비대 | 두꺼운 DDD | collect 선례 동형 |

선택 사유: B의 이점(교체 지점 격리)을 정책 객체 2개로 얻으면서, 이 코드베이스가 이미 검증한 collect 함수형 패턴을 그대로 쓴다.

### 2.1 Component Diagram

```
WorkflowCompiler.compile()
 ├─ _resolve_category(worker) ──────────── None → react (변경: 폴백 "action"→None)
 │                                          "action" → ↓
 ├─ _should_gate_worker(worker_def, gate_settings, gated_tool_ids) → bool   [추출, 미들웨어와 공유]
 ├─ ActionToolConfig.from_tool_config(worker_def.tool_config)               [domain VO]
 ├─ ActionArgumentPolicy.resolve_draft_key(config.draft_arg_key, schema)    [domain] 실패 → failed_worker_ids
 └─ create_action_node(worker_id, tool, llm, pipeline_llm, draft_key, gated, tool_id, logger, blocks…)
        │
        ▼  (state) ─────────────────────────────────────────────────────────────
   action_node
     1. _compose(llm, state, blocks)              → draft:str            (에이전트 모델 1회)
     2. _assemble_arguments(pipeline_llm, tool, draft, ctx) → dict       (보조 LLM 1회, CollectArguments 재사용)
        ActionArgumentPolicy.merge(args, draft_key, draft)               (초안 마지막 덮어쓰기)
        ToolArgumentPolicy.find_placeholder(args)                        (환각 인자 차단)
     3a. gated → ApprovalSignalPolicy.render(...) → approval_pending dict (도구 미호출)
     3b. not gated → _dispatch_once(tool, args)  → result:str            (재시도 없음)
     4. AIMessage(name=worker_id, content=format_draft_output(worker_id, draft, outcome))
        return {messages, last_worker_id, token_usage, last_worker_error, STEP_OUTPUT_SUMMARY_KEY, [approval_pending]}
        │
        ▼
   quality_gate → supervisor ── WorkerRunCapHooks(capped = collect ∪ action) ── FINISH
        │
        ▼ route_to_worker_or_final
   approval_pending → END (§2.1 ③ 유지)      /      else → final_answer
                                                     │
                                                     ▼
   final_answer_node
     FinalAnswerDraftPolicy.detect(worker_outputs) → DraftContext | None
     None → 기존 프롬프트 바이트 동일
     else → blocks += policy.render_block(ctx) ; instruction = policy.instruction()
```

### 2.2 Data Flow

**즉시 집행(게이트 비대상)**

```
supervisor → action_node
  compose:   [system: datetime+worker_ctx+user_ctx+COMPOSE_SYSTEM_PROMPT] + [evidence block] + conversation → draft
  assemble:  [system: user_ctx+ARGUMENT_SYSTEM_PROMPT] + [tool, schema, draft, 최근 대화 6건, question] → args
             args[draft_key] = draft
  dispatch:  tool.ainvoke(_build_payload(tool, args)) → result
  emit:      AIMessage("[w 초안]\n<draft>\n[w 집행결과]\n<result>", name=w)
→ quality_gate → supervisor(FINISH; w는 skip_workers) → final_answer(초안 보존 모드) → END
```

**승인 대기(게이트 대상)**

```
supervisor → action_node
  compose / assemble 동일
  gate:      approval_pending = {tool_id, tool_args(본문=draft), draft, tool_call_id=uuid4, worker_id}
  emit:      AIMessage("[w 초안]\n<draft>\n[w 집행결과]\n승인 대기로 등록되었습니다.", name=w)
→ quality_gate → supervisor(FINISH) → route: approval_pending → END
→ RunAgentUseCase: approval_request 영속 + 스냅샷 (기존 코드, 변경 없음)
… 승인 → McpActionExecutor(tool_args) 1회 → outcome
→ _restore_state: messages += AIMessage(outcome, name=w); approval_pending={}
→ supervisor(w는 이미 실행 → skip) → FINISH → final_answer(초안 보존 모드: 초안 + outcome) → END
```

### 2.3 Dependencies

| 모듈 | 의존 | 비고 |
|------|------|------|
| `domain/agent_builder/action_tool_config.py` | dataclasses | 신규 |
| `domain/agent_builder/policies.py` (+`ActionArgumentPolicy`, `FinalAnswerDraftPolicy`) | 없음(순수) | 기존 파일에 클래스 추가 |
| `application/agent_builder/action_pipeline.py` | collect_pipeline(재사용 함수), search_pipeline(규약), domain 정책, ApprovalSignalPolicy, ToolArgumentPolicy, langchain AIMessage | 신규 |
| `application/agent_builder/search_pipeline.py` | — | `DRAFT_OUTPUT_MARKER`·`format_draft_output`·`is_draft_output`·`split_draft_output` 추가 |
| `application/agent_builder/workflow_compiler.py` | 위 전부 | 분기·추출·배선 |

---

## 3. Data Model

### 3.1 Entity Definition

```python
# domain/agent_builder/action_tool_config.py
@dataclass(frozen=True)
class ActionToolConfig:
    """action 워커 설정 VO. WorkerDefinition.tool_config(dict)에 asdict로 저장.

    draft_arg_key: 초안을 넣을 도구 인자 키. 빈 문자열이면 관례 키 자동 탐색
    (ActionArgumentPolicy.DRAFT_KEY_CANDIDATES 순서로 inputSchema에 있는 첫 키).
    """
    draft_arg_key: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.draft_arg_key, str):
            raise ValueError("draft_arg_key must be a string")

    @classmethod
    def from_tool_config(cls, tool_config: dict | None) -> "ActionToolConfig":
        # 알 수 없는 키는 무시 — 다른 도구 설정과 dict를 공유할 수 있게 (document_* 선례와 동형)
        cfg = tool_config or {}
        return cls(draft_arg_key=str(cfg.get("draft_arg_key", "") or ""))

    def model_dump(self) -> dict: return asdict(self)
```

```python
# domain/agent_builder/policies.py (추가)
class ActionArgumentPolicy:
    """action 인자 규칙 — 본문 키 해석·병합. 순수 dict/str."""
    DRAFT_KEY_CANDIDATES = ("draft", "body", "content", "본문")   # gate_middleware._DRAFT_KEYS 와 동일 순서

    @classmethod
    def resolve_draft_key(cls, configured: str, input_schema: dict) -> str:
        """설정 키가 있으면 스키마에 존재해야 한다. 없으면 후보 중 첫 존재 키.
        둘 다 실패 → ValueError (compile 시 워커 격리 사유)."""
    @staticmethod
    def merge(arguments: dict, draft_key: str, draft: str) -> dict:
        """복사본에 arguments[draft_key] = draft — 마지막 덮어쓰기(초안이 이긴다)."""
    @staticmethod
    def summarize_keys(arguments: dict) -> list[str]:
        """로그·스텝 요약용 키 목록(값 없음)."""

class FinalAnswerDraftPolicy:
    """final_answer 초안 보존 모드 — 감지·블록·지시를 한 곳이 소유 (Plan FR-18).
    교체 시나리오: 프로그램적 삽입(LLM 미경유)으로 바꾸려면 이 클래스만 교체."""
    @staticmethod
    def detect(draft_sections: list[tuple[str, str, str]]) -> "DraftContext | None":
        """(worker_id, draft, outcome) 목록 → 마지막 초안 컨텍스트. 없으면 None."""
    @staticmethod
    def render_block(ctx: "DraftContext") -> str:
        """'[작성된 초안 — 원문 그대로 포함]' + '[집행 결과]' 블록."""
    @staticmethod
    def instruction() -> str:
        """user tail 지시: 초안은 한 글자도 고치지 말고 그대로 포함, 집행 결과를 보고."""

@dataclass(frozen=True)
class DraftContext:
    worker_id: str
    draft: str
    outcome: str      # dispatch 결과 / 승인 대기 문구 / 재개 시 주입된 outcome(있으면 우선)
```

`DraftContext.outcome` 우선순위: 재개 런에서는 `_restore_state`가 `AIMessage(outcome, name=worker_id)`를 **초안 메시지 뒤에** 추가하므로, final_answer는 같은 `worker_id`의 후속 비초안 산출을 outcome으로 채택한다(초안 메시지 안의 "승인 대기" 문구보다 우선).

### 3.2 Entity Relationships

```
WorkerDefinition(category="action", tool_id="mcp:<srv>:<tool>", tool_config={"draft_arg_key": "body"})
   └─ ActionToolConfig ── resolve_draft_key ── tool.mcp_input_schema
approval_pending{tool_id, tool_args, draft, tool_call_id, worker_id}  ── RunAgentUseCase ─▶ approval_request(+snapshot)
AIMessage(name=worker_id, content=[초안][집행결과])                    ── FinalAnswerDraftPolicy
```

### 3.3 Database Schema

변경 없음. `tool_config`는 기존 `agent_tool.tool_config`(JSON) 재사용. 마이그레이션 없음.

### 3.4 산출 메시지 규약 (search_pipeline.py 추가)

```python
DRAFT_OUTPUT_MARKER = "초안"
DRAFT_OUTCOME_MARKER = "집행결과"

def format_draft_output(worker_id: str, draft: str, outcome: str) -> str:
    return f"[{worker_id} {DRAFT_OUTPUT_MARKER}]\n{draft}\n\n[{worker_id} {DRAFT_OUTCOME_MARKER}]\n{outcome}"

def is_draft_output(msg) -> bool:      # is_search_result 동형: name 있음 + 첫 줄이 "[<name> 초안]"
def split_draft_output(msg) -> tuple[str, str, str] | None:   # (worker_id, draft, outcome)
```

첫 줄 정확 일치로 판정한다(본문에 "초안" 단어가 있어도 오탐 없음). 초안 본문 안에 `[<worker_id> 집행결과]` 줄이 있을 가능성은 무시 가능하지만, 파서는 **마지막** 출현을 구획 경계로 쓴다.

---

## 4. API Specification

### 4.1 Endpoint List

신규 엔드포인트 없음. 설정은 기존 에이전트 생성/수정 요청의 워커 항목 `tool_config`로 전달한다.

### 4.2 Detailed Specification

```json
// PUT /api/v1/agents/{id}  (기존) — workers[] 항목 예시
{ "tool_id": "mcp:3f2a…:send_mail", "worker_id": "mail_sender",
  "description": "고객 문의에 대한 회신 메일을 정중한 존댓말로 작성해 발송한다",
  "category": "action",
  "tool_config": { "draft_arg_key": "body" } }
```

검증 지점:
- `ToolCategoryPolicy.assert_assignable("action", tool_id)` — 서버 단위 참조 `mcp_{uuid}`면 400 (기존 collect 경로와 동일 위치: 카탈로그 갱신 UseCase·agent_tool 오버라이드 UseCase).
- `draft_arg_key` 스키마 존재 여부는 저장 시점에 검증하지 않는다(도구 로드 필요). compile 시 검증·격리(§6).

---

## 5. UI/UX Design

해당 없음(백엔드 한정). 프론트 `TOOL_CATEGORIES`·라벨 `'실행'` 불변. 후속 UI 사이클 권고: 카테고리 설명 문구에 "작성 → 1회 호출"을 반영하고 `draft_arg_key` 입력 폼 추가.

---

## 6. Error Handling

### 6.1 실패 분기 매트릭스 (action 노드 — 예외를 올리지 않는다)

| # | 단계 | 상황 | 처리 | `last_worker_error` | 도구 호출 |
|---|------|------|------|---------------------|-----------|
| 1 | compile | inputSchema 없음 / `draft_arg_key` 미존재 / 관례 키 없음 | `ValueError` → `failed_worker_ids` 추가 + `logger.error` (에이전트는 살림, §6.2 격리) | — | — |
| 2 | compose | LLM 예외 | outcome="초안 작성 실패: …", 초안 빈 문자열, 인자 조립·dispatch **생략** | 있음 | 0회 |
| 3 | compose | 빈 초안(공백만) | #2와 동일 처리("초안이 비었습니다") | 있음 | 0회 |
| 4 | assemble | LLM 예외 / JSON 파싱 실패 | outcome="발송 인자 생성 실패: …" | 있음 | 0회 |
| 5 | assemble | `grounded=false` (수신자 등 확인 불가) | outcome="발송 대상을 확인하지 못했습니다: {missing}" — 초안은 산출에 남긴다(사용자가 볼 수 있게) | 있음 | 0회 |
| 6 | assemble | `ToolArgumentPolicy.find_placeholder` 차단 | outcome=`build_blocked_message` | 있음 | 0회 |
| 7 | gate | 게이트 대상 | `approval_pending` 반환, outcome="승인 대기로 등록되었습니다" | 없음 | 0회 |
| 8 | dispatch | 도구 예외 / isError | outcome="집행 실패: …" | 있음 | 1회 |
| 9 | dispatch | 성공 | outcome=결과 문자열(상한 절단) | 없음 | 1회 |

#5·#6에서 초안을 버리지 않는 이유: 사용자가 "왜 안 나갔는지"와 "무엇이 나갈 뻔했는지"를 함께 봐야 다음 턴에 수신자만 알려주고 재시도할 수 있다.

### 6.2 승인 신호 형식

`approval_pending`은 `_extract_approval_pending`이 만드는 dict와 **키·타입이 동일**해야 한다: `tool_id`(카탈로그 형식, 런타임 합성명 아님), `tool_args`(병합 완료 dict), `draft`(초안 원문), `tool_call_id`(`uuid4().hex`), `worker_id`. 노드는 `ApprovalSignalPolicy.render`로 마커 문자열을 만든 뒤 `ApprovalSignalPolicy.extract([ToolMessage-like])`로 **되읽어** dict를 채운다 — 형식이 두 벌로 갈라지는 것을 막는 가장 싼 방법.

### 6.3 관측

- 스텝 요약: `draft_len={n} arg_keys=[to,subject,body] gated={bool} invoked={bool} ok={bool}` (`_SUMMARY_MAX_CHARS` 절단)
- 로그: `action_node executing`(worker_id, tool_id, draft_len, arg_keys, gated, invoked, ok). 값 없음.
- 토큰: compose 응답 길이 + 인자 조립 산출 길이 + outcome 길이의 `//4` (collect와 동일 근사)

---

## 7. Security Considerations

- **PII**: 초안·인자 값은 로그·스텝 요약·예외 메시지에 넣지 않는다. 예외 문자열에 인자가 섞일 수 있는 도구 오류는 `[:_WORKER_ERROR_MAX_CHARS]` 절단 + 키만 로깅.
- **fail-closed**: `gated=True`인데 신호 생성에 실패하면(render 예외) 도구를 호출하지 않고 #2 계열 실패로 낙하한다. 게이트 대상이 무승인으로 나가는 경로는 없다.
- **인자 환각**: `ToolArgumentPolicy` 재사용. 본문은 LLM 산출이 아니라 초안 덮어쓰기.
- **권한**: 승인 권한·재개·집행은 Phase 1/2 코드 그대로. 변경 없음.

---

## 8. Test Plan

### 8.1 Test Scope

| Layer | 대상 | 파일 |
|-------|------|------|
| domain | `ActionToolConfig`, `ActionArgumentPolicy`, `FinalAnswerDraftPolicy`, `ToolCategoryPolicy` action 확장, `ToolMeta` 기본값 | `tests/domain/agent_builder/test_action_tool_config.py`, `test_action_argument_policy.py`, `test_final_answer_draft_policy.py`, `tests/domain/tool_catalog/test_tool_category_policy.py` |
| application | 산출 규약, action 노드 9분기, 컴파일러 배선, final_answer 모드, 신호 승격 | `tests/application/agent_builder/test_draft_output_markers.py`, `test_action_pipeline.py`, `test_workflow_compiler_category.py`(갱신+추가), `test_final_answer_node.py`(추가), `test_approval_signal_lift.py`(추가) |
| integration | 승인 대기 → 영속 → 재개 → final_answer | `tests/application/approval/test_resume.py`(추가) |

### 8.2 L0/L1 핵심 시나리오

| # | 대상 | 입력 | 기대 |
|---|------|------|------|
| 1 | `_resolve_category` | TOOL_REGISTRY 부재 MCP 워커 | `None` (TC-R03 갱신) |
| 2 | `_resolve_category` | `worker.category="action"` | `"action"` |
| 3 | `ToolCategoryPolicy.assert_assignable` | `("action", "mcp_srv1")` | `ValueError` |
| 4 | 〃 | `("action", "mcp:srv1:send")` | 통과 |
| 5 | `ActionArgumentPolicy.resolve_draft_key` | `("body", {"properties":{"body":…}})` | `"body"` |
| 6 | 〃 | `("", {"properties":{"content":…}})` | `"content"` (관례 탐색) |
| 7 | 〃 | `("body", {"properties":{"text":…}})` | `ValueError` |
| 8 | `ActionArgumentPolicy.merge` | LLM이 body="다른 문장" | 결과 body == 초안 |
| 9 | 산출 규약 | `format_draft_output` → `split_draft_output` | 왕복 동일, 초안에 줄바꿈·대괄호 포함 케이스 |
| 10 | 〃 | 일반 검색결과 메시지 | `is_draft_output` False |
| 11 | action 노드 | gated=False, 정상 | 도구 `ainvoke` 정확히 1회, 인자 본문 == 초안, 메시지 1건, `approval_pending` 키 없음 |
| 12 | 〃 | gated=True | `ainvoke` 0회, `approval_pending.draft` == 초안, `tool_args[key]` == 초안, `tool_call_id` 32자 hex |
| 13 | 〃 | compose 예외 | 도구 0회, `last_worker_error` 비어있지 않음, 초안 구획 빈 문자열 |
| 14 | 〃 | assemble `grounded=false` | 도구 0회, 초안은 산출에 존재 |
| 15 | 〃 | placeholder 인자 | 도구 0회, blocked 메시지 |
| 16 | 〃 | 도구 예외 | 1회 호출, 재호출 없음, 실패 outcome |
| 17 | 〃 | MCP 어댑터 | payload가 `{"arguments": {...}}` |
| 18 | 컴파일러 | action 워커 | `function_node_ids` 포함, `create_agent` 미호출, `empty_signal_worker_ids` 미포함 |
| 19 | 〃 | action 워커 + 스키마에 키 없음 | `failed_worker_ids` 포함, 에이전트 컴파일 성공 |
| 20 | 〃 | action 워커 존재 | `WorkerRunCapHooks` capped에 포함 |
| 21 | 〃 | `_should_gate_worker` | 미들웨어 부착 판정과 노드 gated 값이 항상 일치(동일 함수) |
| 22 | final_answer | 초안 메시지 없음 | 프롬프트 문자열 기존 테스트 픽스처와 바이트 동일 |
| 23 | 〃 | 초안 메시지 있음 | 시스템 프롬프트에 초안 원문·outcome 포함, instruction 교체 |
| 24 | 〃 | 초안 + 재개 outcome 메시지 | outcome이 재개분으로 채택 |
| 25 | 신호 승격 | 노드 반환 dict | `RunAgentUseCase`가 기존 코드로 approval_request 영속 (mock repo 호출 인자 검증) |
| 26 | 재개 | 스냅샷 복원 → 그래프 | action 워커 재실행 0회, final_answer에 초안 + outcome |

### 8.3 L2 / L3

L2(UI) 없음. L3는 로컬 실런: BYO 메일 MCP 워커에 `category="action"`, `tool_config.draft_arg_key` 설정 → `ai_run_step` 요약·`approval_request.draft`·`ai_tool_call.arguments_json` 본문 키 세 지점 문자열 대조(메모리 레시피: asyncmy 조회, 결과는 파일로).

### 8.4 Seed Data Requirements

없음(로컬 DB의 기존 MCP 서버·에이전트 재사용).

---

## 9. Clean Architecture

### 9.1 Layer Structure

```
src/domain/agent_builder/action_tool_config.py      (신규) VO
src/domain/agent_builder/policies.py                (+) ActionArgumentPolicy, FinalAnswerDraftPolicy, DraftContext
src/domain/agent_builder/schemas.py                 (수정) ToolCategory 확장, ToolMeta.category=None
src/domain/tool_catalog/policies.py                 (수정) assert_assignable action 확장
src/application/agent_builder/action_pipeline.py    (신규) create_action_node + 단계 함수
src/application/agent_builder/search_pipeline.py    (+) 초안 규약 3함수 + 상수 2개
src/application/agent_builder/workflow_compiler.py  (수정) 폴백·분기·_should_gate_worker·run cap·final_answer
```

### 9.2 Dependency Rules

- domain 신규 코드는 표준 라이브러리만 import. `input_schema`는 dict로 받는다.
- `action_pipeline.py`는 `collect_pipeline`의 **공개 가능한 헬퍼만** 재사용한다. 현재 `_resolve_input_schema`·`_build_payload`·`_invoke_once`·`_collect_context`가 private 이름이므로, Do에서 언더스코어를 떼어 공개 이름으로 바꾸고 collect 내부 호출도 갱신한다(동작 불변, 테스트 무회귀).
- `workflow_compiler`는 노드 팩토리에 bool·문자열·객체만 넘긴다. 정책 판단을 컴파일러가 대신하지 않는다(키 해석은 정책 호출).

### 9.3 File Import Rules

`action_pipeline.py` import 순서: stdlib → langchain_core → `src.application.agent_builder.*` → `src.domain.*` (기존 collect 파일과 동일).

### 9.4 This Feature's Layer Assignment

| 책임 | 레이어 | 근거 |
|------|--------|------|
| 본문 키 해석·병합·초안 보존 규칙 | domain | 문자열·dict 규칙, 외부 의존 없음 |
| LLM 호출·도구 호출·메시지 생성 | application | LangChain·MCP 어댑터 사용 |
| 게이트 판정 공유 함수 | application (컴파일러 모듈 함수) | `ApprovalPolicy.should_gate`(domain)를 호출하는 얇은 래퍼 |

---

## 10. Coding Convention Reference

### 10.1 Naming

- 노드 팩토리 `create_action_node`, 노드 함수 `action_node` (collect 동형)
- 단계 함수 `_compose_draft`, `_assemble_arguments`, `_dispatch_once`, `_render_outcome` — 각 40줄 이하
- 정책 클래스 `*Policy`, VO `*ToolConfig`, 컨텍스트 `DraftContext`

### 10.2 Design Ref 주석

- 모듈 헤더: `Design Ref: action-category-compose-node §2.1 / §6.1`
- 초안 덮어쓰기 지점: `# Plan SC: SC-2/SC-3 — 초안이 이긴다 (FR-10)`
- 폴백 변경 지점: `# Design Ref: §2.1 — 미분류는 None(react). "action"은 명시 지정만 (Plan FR-01)`

### 10.3 Config

- `ACTION_OUTCOME_MAX_CHARS`(dispatch 결과 상한, 기본 4000)·`ACTION_DRAFT_CONTEXT_MAX_MESSAGES`(기본 6)는 `Settings`에 추가하지 않고 모듈 상수로 둔다(collect의 `_CONTEXT_MAX_MESSAGES`와 동일 관례). 운영 조정 요구가 생기면 그때 config로 승격.

---

## 11. Implementation Guide

### 11.1 File Structure

```
신규
  src/domain/agent_builder/action_tool_config.py
  src/application/agent_builder/action_pipeline.py
  tests/domain/agent_builder/test_action_tool_config.py
  tests/domain/agent_builder/test_action_argument_policy.py
  tests/domain/agent_builder/test_final_answer_draft_policy.py
  tests/application/agent_builder/test_draft_output_markers.py
  tests/application/agent_builder/test_action_pipeline.py
수정
  src/domain/agent_builder/schemas.py
  src/domain/agent_builder/policies.py
  src/domain/tool_catalog/policies.py
  src/application/agent_builder/search_pipeline.py
  src/application/agent_builder/collect_pipeline.py        (헬퍼 공개 이름화)
  src/application/agent_builder/workflow_compiler.py
  tests/application/agent_builder/test_workflow_compiler.py            (TC-R03 등)
  tests/application/agent_builder/test_workflow_compiler_category.py   (폴백·action 배선)
  tests/application/agent_builder/test_final_answer_node.py
  tests/application/agent_builder/test_approval_signal_lift.py
  tests/domain/tool_catalog/test_tool_category_policy.py
  tests/application/approval/test_resume.py
```

### 11.2 Implementation Order (TDD)

1. **M1 계약 정정** — `ToolCategory`/`ToolMeta.category=None`, `_resolve_category` 폴백 `None`, `assert_assignable` action 확장. 테스트 #1~#4 먼저(Red) → 구현 → 기존 테스트 기대값 갱신 → 등가 테스트 통과 확인.
2. **M2 도메인** — `ActionToolConfig`, `ActionArgumentPolicy`, `FinalAnswerDraftPolicy`/`DraftContext`. 테스트 #5~#8.
3. **M3 규약** — `search_pipeline.py` 초안 규약 3함수. 테스트 #9~#10. collect 헬퍼 공개 이름화(무회귀 확인).
4. **M4 노드** — `action_pipeline.py`. 테스트 #11~#17 (도구·LLM은 fake).
5. **M5 배선** — `_should_gate_worker` 추출, action 분기, `failed_worker_ids` 격리, `function_node_ids`, run cap 목록 확장. 테스트 #18~#21.
6. **M6 final_answer** — 정책 호출 삽입. 테스트 #22~#24 (#22는 기존 픽스처 바이트 비교).
7. **M7 통합** — 신호 승격·재개. 테스트 #25~#26. L3 실런 대조.

### 11.3 Session Guide

| Module | 범위 | 예상 변경 | 세션 |
|--------|------|-----------|------|
| module-1 | M1 계약 정정 + M2 도메인 | ~200줄 (신규 120 / 수정 40 / 테스트 갱신 40) | 1 |
| module-2 | M3 규약 + M4 노드 | ~450줄 (신규 300 / 테스트 150) | 2 |
| module-3 | M5 배선 + M6 final_answer | ~180줄 (수정 80 / 테스트 100) | 3 |
| module-4 | M7 통합 + L3 실런 검증 | ~120줄 테스트 + 실런 | 4 |

권장: `/pdca do action-category-compose-node --scope module-1,module-2` → `--scope module-3,module-4`. module-2는 module-1의 정책에 의존하므로 순서 고정.

---

## 12. Key Design Decisions

| ID | 결정 | 대안 | 근거 |
|----|------|------|------|
| D-01 | 명시 `action`만 새 노드, 폴백 `None` | 새 카테고리 값 | 명시 action 데이터 0건(로컬 DB 실측), 정책 주석("None=미분류")과 코드 폴백의 불일치 해소 |
| D-02 | 함수형 `action_pipeline.py`(collect 동형) | 컴파일러 클로저 / 클래스 분리 | 선례 재사용, 40줄 규칙, 교체 지점 격리 |
| D-03 | 게이트 판정을 `_should_gate_worker()`로 추출해 미들웨어·노드 공유 | 두 벌 판정 | 판정 불일치 = 무승인 발송 위험(R-8) |
| D-04 | 본문은 `ActionArgumentPolicy.merge`로 **마지막** 덮어쓰기 | LLM 지시로만 | LLM 지시는 보장이 아니다(R-3) |
| D-05 | 인자 조립은 `CollectArguments` 구조화 출력 재사용, 맥락 = 초안 + 최근 대화 6건 | 새 스키마 | 스키마 고정·provider 독립 이점 그대로 |
| D-06 | 산출 = AIMessage 1건, `[w 초안]`/`[w 집행결과]` 구획 | 메시지 2건 | 재개 스냅샷 "워커 산출 1건" 계약 |
| D-07 | 재개 outcome은 같은 worker_id의 후속 비초안 산출을 우선 채택 | 초안 메시지 재작성 | `_restore_state` 무변경 |
| D-08 | `tool_call_id = uuid4().hex` | 결정적 id | 노드에는 LLM tool_call이 없고, 재개 경로가 id에 의존하지 않음(`_restore_state` 확인) |
| D-09 | 스키마·본문 키 검증은 compile 시, 실패는 워커 격리 | 첫 실행 시 오류 | 도구는 compile에서 이미 로드됨. 조용한 오동작보다 즉시 격리 |
| D-10 | `fixed_args` 제외 | 포함 | YAGNI. VO가 알 수 없는 키를 무시하므로 후속 추가 시 하위호환 |
| D-11 | run cap 목록을 `collect ∪ action`으로 확장 | 신규 훅 | D-07(mcp-tool-category-routing) 재사용, supervisor 코어 미수정 |
| D-12 | action 워커는 `empty_signal_worker_ids` 제외 | 포함 | 작성은 수집이 아니다. 실패 처리는 `last_worker_error`가 담당 |
| D-13 | 승인 대기 런은 final_answer 미경유 유지 | 경유 | approval-gate §2.1 ③ 근거 그대로 |
| D-14 | 모듈 상수(outcome 상한·맥락 건수), `Settings` 미추가 | config 승격 | collect 관례. 운영 요구 시 승격 |

---

## Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1 | 2026-09-23 | 배상규 | 초안. Option C 선택, Plan §9 열린 질문 6건 제안값 확정(D-05·D-06·D-08·D-09·D-10) |
| 0.2 | 2026-09-24 | 배상규 | Do 반영 3건. ① D-11 보강: `WorkerRunCapHooks._executed_worker_ids`가 검색결과 규약만 세어 초안 규약을 추가(SC-8 성립 조건). ② FR-17 정정: 재작성 금지 지시는 user tail이 아니라 system prompt에 싣는다 — `ensure_user_tail`은 마지막이 assistant일 때만 붙어 항상 도달하지 않음. ③ §6.1 #1 보강: 기존 불변식 "워커 전부 실패면 컴파일 불가"는 유지 — action 워커 단독 에이전트의 키 미해석은 컴파일 실패로 드러난다. ④ 인자 조립 실패(#4·#5·#6) 시 게이트 대상이라도 승인 요청을 만들지 않는다(빈 수신자 승인 방지). L3 실런은 로컬에 본문 키를 가진 부작용 도구(메일 MCP)가 없어 미수행 — 그래프 수준 통합 테스트(`test_action_graph_integration.py`)로 대체 |
