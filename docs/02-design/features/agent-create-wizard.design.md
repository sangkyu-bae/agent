# agent-create-wizard Design Document

> **Summary**: 파이프라인의 하드코딩 단계 순회를 **domain Policy가 계산하는 실행 단계 목록**으로 바꿔 정지 지점 2곳을 추가하고, `/agent-builder/new`를 4스텝 무상태 위저드로 교체한다.
>
> **Project**: sangplusbot (`idt` + `idt_front`)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-08-20
> **Status**: Draft
> **Planning Doc**: [agent-create-wizard.plan.md](../../01-plan/features/agent-create-wizard.plan.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 에이전트 자동 생성이 블랙박스여서 결과가 어긋나도 사용자가 어느 단계에서 틀렸는지 알 수 없고, 개입할 수도 없다 |
| **WHO** | P2 — KB 운영자 / 에이전트 소유자. 에이전트를 처음 만드는 비개발 실무자 |
| **RISK** | ① 정지 지점 추가로 파이프라인이 2개 모드를 갖게 되어 계약 복잡도 상승 ② 미커밋 코드 커밋 + V061~V063 마이그레이션이라는 배포 선행조건 ③ prompt_session이 스튜디오 저장까지 살아남아야 바인딩 성립 |
| **SUCCESS** | 설명 1문장 → 4스텝 완주 → 스튜디오 저장 → `GET /api/v1/agents/{id}`의 system_prompt·tool_ids가 위저드 확정값과 일치. 기존 5경로 회귀 0건 |
| **SCOPE** | 백엔드 확장(stop_after·human 프롬프트 버전·플래그/마이그레이션 활성화) + 프론트 위저드 전면 교체. R1 수렴은 범위 밖 |

---

## 1. Overview

### 1.1 Design Goals

1. **정지 지점을 규칙으로 표현한다** — `if` 분기를 UseCase 흐름에 흩뿌리지 않고, "어느 단계까지 실행할지"를 domain 순수 함수가 계산한다. LLM 목 없이 테스트되고 후속 R1 수렴에서 재사용된다.
2. **기존 논스톱 경로의 회귀를 구조적으로 0으로 만든다** — 신규 입력이 모두 no-op 기본값이면 실행 단계 목록이 기존 하드코딩 튜플과 **글자 그대로 동일**해진다.
3. **사용자가 확정한 것은 서버가 다시 뒤집지 않는다** — 도구를 확정한 뒤 재호출할 때 셀렉터를 다시 돌리면 사용자가 뺀 도구가 되살아난다. 확정 신호를 1급 입력으로 둔다.
4. **화면에 보이는 프롬프트 = 실제 저장될 프롬프트** — 4000자 clamp를 정지 응답 시점에 적용해 "보이는 것과 저장되는 것"의 어긋남을 없앤다.
5. **공통 컴포넌트를 소비만 한다** — `ProgressCard`·`question-card`·`ToolPickerModal`·`LoadingButton`을 재사용하고 새 진행/질문 UI를 만들지 않는다.

### 1.2 Design Principles

- **규칙은 domain, 흐름은 application** — `PipelinePolicy`는 순수 정적 함수만. UseCase는 Policy가 준 목록을 순회할 뿐.
- **계약 확장은 additive** — 신규 요청 필드는 전부 기본값 no-op, 신규 응답 필드는 optional, 신규 `status` 값은 구형 소비자가 없으므로 안전.
- **wire 문자열은 StrEnum value** — 신규 상태·정지 지점도 StrEnum으로 단일화하고 테스트로 고정.
- **try/except는 늘리지 않는다** — bind 1곳이 유일한 흡수 지점이라는 기존 계약 유지.
- **프론트 상태는 영속하지 않는다** — 핸드오프 `persist` 금지 계약(G1) 준수.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | **Option C: Pragmatic** |
|----------|:-:|:-:|:-:|
| **Approach** | `run()`에 `if stop_after` 분기 2개 직접 삽입 | 단계별 엔드포인트 3개 + UseCase 분해 | `stop_after`를 domain 개념으로 승격, Policy가 실행 목록 계산 |
| **New Files (BE)** | 2 | ~12 | ~5 |
| **Modified Files (BE)** | 6 | 8 | 7 |
| **Complexity** | Low | High | Medium |
| **`steps[]` 5개 고정 계약** | 유지 | **파손** (엔드포인트별로 달라짐) | 유지 |
| **FR-15 동기=SSE 동일성** | 유지 | 3배로 유지 필요 | 유지 |
| **규칙 테스트성** | UseCase에 분기 혼입 → LLM 목 필요 | 좋음 | **domain 순수 함수 — LLM 목 불필요** |
| **논스톱 경로 회귀 위험** | Low | **High** | Low |
| **Maintainability** | Medium | High | High |
| **Recommendation** | 핫픽스 | 장기 프로젝트 | **선택** |

**Selected**: **Option C — Pragmatic Balance**

**Rationale**: `policies.py` 모듈 docstring이 "흐름(UseCase)과 규칙을 분리한다 — 여기 있는 규칙은 LLM 목 없이 테스트되고, 후속 R1 수렴에서 재사용된다"를 이미 이 모듈의 설계 원칙으로 명시하고 있다. A안은 그 원칙을 깨고, B안은 진행바 고정 렌더의 근거인 `steps[]` 5개 고정 계약과 FR-15를 파괴한다. C안은 `use_case.py:130-139`의 하드코딩 튜플 한 곳만 Policy 호출로 교체하면서 두 계약을 모두 지킨다.

### 2.1 Component Diagram

```
┌───────────────────────── idt_front ─────────────────────────┐
│  /agent-builder/new  (단일 페이지, step: useState)          │
│  ┌────────────┐                                             │
│  │WizardProgr.│◀── pipelineStepsToProgress()  (매핑 어댑터) │
│  └────────────┘        ▲                                    │
│  ① Description ② Intent ③ Tools ④ Prompt                   │
│      │           │        │        │                        │
│      │      question-card  ToolPickerModal (재사용 3종)      │
│      └───────────┴────────┴────────┐                        │
│                 useAgentPipelineStream (SSE fetch-stream)   │
│                            │                                │
│                     agentPipelineService                    │
└────────────────────────────┼────────────────────────────────┘
                             │  POST /api/v1/agents/pipeline/stream
┌────────────────────────────▼──────── idt ───────────────────┐
│  agent_pipeline_router  (동기 POST + SSE, 공유 제너레이터)   │
│           │                                                 │
│  AgentCreatePipelineUseCase.run(stop_after, tools_confirmed)│
│           │  for stage in PipelinePolicy.stages_to_run(...) │
│           ├── intent   → AnalyzeIntentUseCase   (LLM)       │
│           ├── tools    → LLMToolSelector        (LLM)  ⟵ 확정 시 short-circuit
│           ├── prompt   → ComposePromptUseCase   (LLM, 버전 저장)
│           ├── create   ─┐ 위저드는 도달하지 않음             │
│           └── bind     ─┘ (스튜디오 저장 경로가 대신 수행)   │
│                                                             │
│  PipelinePolicy (domain, 순수)                              │
│    stages_to_run / decide_after_stage / stop_status         │
│    confirmed_selection / reuse_intent / clamp_prompt        │
└─────────────────────────────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│  스튜디오 저장 경로 (기존 + 신규 1콜)                        │
│  POST /api/v1/agents            (기존, 무변경)              │
│  POST /prompt-composer/sessions/{id}/versions  (신규, 편집시)│
│  PATCH /prompt-composer/sessions/{id}          (기존, 바인딩)│
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow — 3회 왕복 + 저장

```
[R1] POST /pipeline/stream { user_request, stop_after:"tools" }
       intent(LLM) → 미충족 → status:"need_input", questions[], round:1
                   → 충족   → tools(LLM) → status:"tools_proposed"

[R2] POST /pipeline/stream { user_request, answers[], round:1, stop_after:"tools" }
       intent(LLM, answers 반영) → tools(LLM) → status:"tools_proposed"
                                   recommended_tool_ids[], final_tool_ids[]
       ※ 되묻기가 여러 라운드면 R2가 반복된다 (서버 max_rounds=2로 clamp)

     ── 사용자가 도구 확정 (추천 토글 + 카탈로그 추가) ──

[R3] POST /pipeline/stream {
       user_request, answers[], round, intent(에코백),
       tool_ids: 확정목록, tools_confirmed: true, stop_after: "prompt" }
       intent(재사용, LLM 미호출) → tools(short-circuit, LLM 미호출)
         → prompt(LLM) → prompt_version 저장 → status:"prompt_ready"
            { session_id, version_id, assembled_prompt(clamp됨), suggested_name }

     ── 사용자가 프롬프트 검토·편집 → [스튜디오로 보내기] ──

[핸드오프] agentDraftStore.setPendingIntent({ kind:'wizard', ... })  (무저장)
[스튜디오] 폼 프리필 → 사용자 [저장]
       ① 편집됨? → POST /prompt-composer/sessions/{sid}/versions (source=human)
       ② POST /api/v1/agents                            → agent_id
       ③ PATCH /prompt-composer/sessions/{sid} {agent_id} → 바인딩 (실패 허용)
```

**핵심 설계 판단 3가지**

| # | 판단 | 근거 |
|---|------|------|
| D1 | **R3에서 tools 단계를 실행하지 않는다** (`tools_confirmed`) | `_run_tools`는 `required_ids=ctx.tool_ids`로 셀렉터를 호출한다. 재호출하면 `final_ids = 셀렉터출력 ∪ 확정목록` 이 되어 **사용자가 제거한 도구가 되살아난다**. 확정 신호 없이는 위저드가 성립하지 않는다 |
| D2 | **R3에서 intent를 에코백해 재사용한다** | 재호출마다 intent LLM이 다시 돌면 (a) LLM 비용 1회 추가 (b) **사용자가 도구를 고른 근거였던 의도와 프롬프트 생성에 쓰인 의도가 달라질 수 있다**. 에코백값은 서버가 spec 기준으로 재검증(허용 slot key만, 값 길이 clamp, label은 taxonomy 내)한 뒤에만 신뢰한다 — stateless-hitl의 "클라 신고값 재clamp" 2요소와 동일 계열 |
| D3 | **`prompt_ready`의 `assembled_prompt`는 clamp된 값** | `CreateAgentRequest.system_prompt`는 `max_length=4000`이라 초과하면 **저장 시 422**가 난다. 검토 화면에 원본을 보여주고 저장에서 실패하면 최악이다. 정지 시점에 `clamp_prompt`를 적용하고 사유를 `prompt_clamp_reason`으로 함께 준다 |

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `AgentCreatePipelineUseCase` | `PipelinePolicy` (domain) | 실행 단계 목록·정지 판정·확정 선택 결과 조립 |
| `PipelinePolicy` | `PipelineStage`/`PipelineStop`/`StageRecord`, `IntentResult`, `SelectionResult` | 순수 계산만 (domain → domain) |
| `ComposePromptUseCase` | `PromptVersionRepository` | 사람 버전 append 재사용 |
| `AppendHumanVersionUseCase` (신규) | `ComposePromptUseCase`의 세션 소유권 검사 + 버전 append | 편집본 저장 |
| `useAgentPipelineStream` (FE) | `utils/streamParser.ts` | SSE fetch-stream 파싱 (기존 재사용) |
| `pipelineStepsToProgress` (FE) | `types/progress.ts` | steps[] → `ProgressStep[]` |
| `AgentCreateEntryPage` | `ProgressCard`, `question-card`, `ToolPickerModal`, `LoadingButton` | 공통 컴포넌트 소비 |

---

## 3. Data Model

### 3.1 domain/agent_create_pipeline/stages.py — 신규 `PipelineStop`

```python
class PipelineStop(StrEnum):
    """위저드 정지 지점. .value 는 요청 wire 계약(`stop_after`)이다."""

    TOOLS = "tools"    # 도구 추천 직후 정지 → status: tools_proposed
    PROMPT = "prompt"  # 프롬프트 생성 직후 정지 → status: prompt_ready
```

`PipelineStage` / `StageStatus` / `StageRecord` / `STAGE_ORDER`는 **무변경**.

### 3.2 domain/agent_create_pipeline/policies.py — 신규 순수 함수 5종

```python
_STOP_STATUS = {
    PipelineStop.TOOLS: "tools_proposed",
    PipelineStop.PROMPT: "prompt_ready",
}

@staticmethod
def stages_to_run(stop: PipelineStop | None) -> tuple[PipelineStage, ...]:
    """intent 이후 실행할 단계 목록. stop 이 None 이면 기존 4단계 그대로."""
    after_intent = STAGE_ORDER[1:]                     # tools, prompt, create, bind
    if stop is None:
        return after_intent
    end = after_intent.index(PipelineStage(stop.value)) + 1
    return after_intent[:end]

@staticmethod
def decide_after_stage(
    stage: PipelineStage, stop: PipelineStop | None
) -> Literal["stop", "continue"]:
    """이 단계 직후 멈출지. stop 이 None 이면 항상 continue."""
    if stop is not None and stage.value == stop.value:
        return "stop"
    return "continue"

@staticmethod
def stop_status(stop: PipelineStop) -> str:
    """정지 지점 → 응답 status 문자열 (wire 계약)."""
    return _STOP_STATUS[stop]

@staticmethod
def confirmed_selection(user_ids: Sequence[str]) -> SelectionResult:
    """사용자가 확정한 도구 목록을 셀렉터 호출 없이 SelectionResult 로 (D1).

    empty_candidate_selection 과 달리 fallback=False 다 — 강하가 아니라
    '사람이 결정했으므로 추천이 불필요'한 정상 경로이기 때문이다.
    """
    deduped = tuple(dict.fromkeys(user_ids))
    return SelectionResult(
        selected_ids=deduped,
        required_ids=deduped,
        final_ids=deduped,
        candidate_count=len(deduped),
        fallback=False,
        reason="사용자 확정 도구 — 추천 생략",
    )

@staticmethod
def reuse_intent(echo: IntentResult | None, spec: IntentSpec) -> IntentResult | None:
    """클라이언트 에코백 의도를 spec 기준으로 재검증해 신뢰 여부를 판정 (D2).

    - spec 에 없는 slot key 는 버린다
    - 값은 SLOT_VALUE_MAX_CHARS 로 clamp
    - degraded=True 로 신고된 에코백은 무시(None) — 재판정이 낫다
    - complete/missing_slots 는 신고값을 쓰지 않고 서버가 재계산한다
    반환 None 이면 호출자는 intent LLM 을 정상 실행한다.
    """
```

> `reuse_intent`가 `complete`/`missing_slots`를 **재계산**하는 것은
> `llm-output-trust-boundary` / `declared-slot-elicitation` 위키의 "계산 필드는
> 외부 입력에서 받지 않는다" 규칙을 클라이언트 입력에도 동일 적용한 것이다.

### 3.3 application/agent_create_pipeline/events.py — `PipelineOutcome` 확장

```python
status: Literal[
    "need_input", "tools_proposed", "prompt_ready", "created"   # 2값 추가
]
...
suggested_name: str | None = None        # 신규 — 스튜디오 프리필용
prompt_clamp_reason: str | None = None   # 신규 — D3, prompt_ready 에서만
```

기존 필드는 전부 유지. `_Run` dataclass에 `stop: PipelineStop | None`, `tools_confirmed: bool`, `intent_echo: IntentResult | None` 3개 추가.

### 3.4 DB — `prompt_version.source` (V063)

| Column | Type | Null | Default | Comment |
|--------|------|:----:|---------|---------|
| `source` | `VARCHAR(10)` | NOT NULL | `'llm'` | 프롬프트 작성 주체 — llm(생성) 또는 human(사용자 편집본) |

- ENUM 대신 `VARCHAR(10)` + 애플리케이션 레이어 검증. MySQL ENUM은 값 추가 시 ALTER가 필요해 additive 확장을 막는다.
- 기존 행은 `DEFAULT 'llm'`으로 자동 채워진다 → 기존 CREATE/READ 경로 무영향.
- **COMMENT 안에 콤마 금지** — `test_migration_ddl_comments.py`의 `_split_top_level`이 따옴표를 추적하지 않아 허위 위반을 낸다 (`mysql-fk-collation` 위키).

```sql
-- V063__add_source_to_prompt_version.sql
ALTER TABLE prompt_version
  ADD COLUMN source VARCHAR(10) NOT NULL DEFAULT 'llm'
  COMMENT '프롬프트 작성 주체 — llm(생성) 또는 human(사용자 편집본)'
  AFTER schema_version;
```

SQLAlchemy 모델(`PromptVersionModel`)에 동일 `comment=` 반영 (CLAUDE.md §3).

### 3.5 Frontend Types — `src/types/agentPipeline.ts` (신규)

```typescript
export const PIPELINE_STAGE = {
  INTENT: 'intent', TOOLS: 'tools', PROMPT: 'prompt',
  CREATE: 'create', BIND: 'bind',
} as const;
export type PipelineStage = (typeof PIPELINE_STAGE)[keyof typeof PIPELINE_STAGE];

export const PIPELINE_STAGE_STATUS = {
  OK: 'ok', DEGRADED: 'degraded', FAILED: 'failed', SKIPPED: 'skipped',
} as const;
export type PipelineStageStatus =
  (typeof PIPELINE_STAGE_STATUS)[keyof typeof PIPELINE_STAGE_STATUS];

export type PipelineStatus =
  | 'need_input' | 'tools_proposed' | 'prompt_ready' | 'created' | 'failed';

export interface PipelineStepOut {
  stage: PipelineStage;
  status: PipelineStageStatus;
  reason: string | null;
  elapsed_ms: number;
}

export interface PipelineQuestion {
  slot_key: string;
  question: string;
  options: string[];
  allow_free_text: boolean;
}

export interface PipelineIntentSummary {
  label: string | null;
  filled_slots: Record<string, string>;
  missing_slots: string[];
  degraded: boolean;
}

export interface PipelineAnswer { slot_key: string; value: string }

export interface AgentPipelineRequest {
  user_request: string;
  history?: { role: 'user' | 'assistant'; content: string }[];
  answers?: PipelineAnswer[];
  round?: number;
  tool_ids?: string[];
  name?: string | null;
  llm_model_id?: string | null;
  session_id?: string | null;
  stop_after?: 'tools' | 'prompt' | null;   // 신규
  tools_confirmed?: boolean;                // 신규
  intent?: PipelineIntentSummary | null;    // 신규 (에코백)
}

export interface AgentPipelineResponse {
  status: PipelineStatus;
  round: number;
  steps: PipelineStepOut[];
  degraded_stages: string[];
  questions: PipelineQuestion[];
  intent: PipelineIntentSummary | null;
  recommended_tool_ids: string[];
  final_tool_ids: string[];
  unknown_tool_ids: string[];
  session_id: string | null;
  version_id: string | null;
  agent_id: string | null;
  agent_name: string | null;
  assembled_prompt: string | null;
  suggested_name: string | null;        // 신규
  prompt_clamp_reason: string | null;   // 신규
  bind_ok: boolean | null;
  error?: { message: string };          // status='failed' (SSE 합성) 시
}

export type PipelineSseEvent =
  | { event: 'stage_started'; data: { stage: PipelineStage } }
  | { event: 'stage_completed' | 'stage_failed'; data: PipelineStepOut }
  | { event: 'pipeline_result'; data: AgentPipelineResponse };
```

> 상수 객체(`PIPELINE_STAGE` 등)는 **반드시 `types/`에** 둔다 — 컴포넌트 파일의 런타임 export는 react-refresh 린트 위반이자 이 프로젝트의 확립된 함정이다 (`tsx-authoring-pitfalls` 위키).

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | Description | Auth | 변경 |
|--------|------|-------------|------|------|
| POST | `/api/v1/agents/pipeline` | 동기 실행 | Required | **확장** |
| POST | `/api/v1/agents/pipeline/stream` | SSE 실행 | Required | **확장** |
| POST | `/api/v1/prompt-composer/sessions/{session_id}/versions` | 사람 편집 프롬프트 버전 append | Required | **신규** |
| PATCH | `/api/v1/prompt-composer/sessions/{session_id}` | agent_id 바인딩 | Required | 기존 (프론트 신규 소비) |
| POST | `/api/v1/agents` | 에이전트 생성 | Required | 기존 무변경 |
| GET | `/api/v1/tool-catalog` | 도구 카탈로그 | Required | 기존 무변경 |

라우터 등록 순서 계약 유지 — `/api/v1/agents/pipeline`은 `agent_builder_router`의 `/agents/{agent_id}`보다 **먼저** include (`main.py` DI 블록).

### 4.2 Request 확장 (파이프라인 두 엔드포인트 공용)

```jsonc
{
  "user_request": "여신 심사 문서를 검색해서 요약해주는 에이전트 만들어줘",
  "history": [],
  "answers": [{"slot_key": "purpose", "value": "여신 심사 문서 Q&A"}],
  "round": 1,
  "tool_ids": ["internal:hybrid_search", "internal:doc_browse"],
  "name": null,
  "llm_model_id": null,
  "session_id": null,

  // ── 신규 (전부 기본값 no-op → 미지정 시 기존 동작 완전 동일) ──
  "stop_after": "prompt",        // "tools" | "prompt" | null(기본)
  "tools_confirmed": true,       // 기본 false
  "intent": {                    // 기본 null — 에코백 재사용 (D2)
    "label": "agent_build",
    "filled_slots": {"purpose": "여신 심사 문서 Q&A", "target_users": "심사팀"},
    "missing_slots": [],
    "degraded": false
  }
}
```

**추가 검증 (422)**: `stop_after`는 `"tools"|"prompt"` 외 값 거부 · `tools_confirmed=true`인데 `tool_ids`가 비면 허용(도구 없는 에이전트) · `intent.filled_slots` 값 길이 상한 clamp(서버, 거부 아님).

### 4.3 Response — 신규 status 2종

**`tools_proposed`** (`stop_after="tools"`, 의도 충족):
```json
{
  "status": "tools_proposed",
  "round": 1,
  "intent": {"label": "agent_build", "filled_slots": {"purpose": "여신 심사 문서 Q&A"}, "missing_slots": [], "degraded": false},
  "recommended_tool_ids": ["internal:hybrid_search", "internal:doc_browse"],
  "final_tool_ids": ["internal:hybrid_search", "internal:doc_browse"],
  "unknown_tool_ids": [],
  "suggested_name": "여신 심사 문서 Q&A",
  "degraded_stages": [],
  "steps": [
    {"stage": "intent", "status": "ok",      "reason": null,                  "elapsed_ms": 812},
    {"stage": "tools",  "status": "ok",      "reason": null,                  "elapsed_ms": 640},
    {"stage": "prompt", "status": "skipped", "reason": "stopped_for_review",  "elapsed_ms": 0},
    {"stage": "create", "status": "skipped", "reason": "stopped_for_review",  "elapsed_ms": 0},
    {"stage": "bind",   "status": "skipped", "reason": "stopped_for_review",  "elapsed_ms": 0}
  ]
}
```

**`prompt_ready`** (`stop_after="prompt"`, `tools_confirmed=true`):
```json
{
  "status": "prompt_ready",
  "round": 1,
  "intent": {"...": "..."},
  "recommended_tool_ids": ["internal:hybrid_search", "internal:doc_browse"],
  "final_tool_ids": ["internal:hybrid_search", "internal:doc_browse"],
  "unknown_tool_ids": ["internal:nope"],
  "session_id": "ps_...",
  "version_id": "pv_...",
  "assembled_prompt": "당신은 여신 심사 문서를 ...",
  "prompt_clamp_reason": null,
  "suggested_name": "여신 심사 문서 Q&A",
  "degraded_stages": [],
  "steps": [
    {"stage": "intent", "status": "ok",      "reason": "확정된 의도 재사용",   "elapsed_ms": 0},
    {"stage": "tools",  "status": "ok",      "reason": "사용자 확정 도구 — 추천 생략", "elapsed_ms": 0},
    {"stage": "prompt", "status": "ok",      "reason": null,                  "elapsed_ms": 7300},
    {"stage": "create", "status": "skipped", "reason": "stopped_for_review",  "elapsed_ms": 0},
    {"stage": "bind",   "status": "skipped", "reason": "stopped_for_review",  "elapsed_ms": 0}
  ]
}
```

`need_input` / `created` 응답은 **기존과 완전 동일**. `steps[]`는 여전히 항상 5개 (`finalize_steps`, skip_reason만 `stopped_for_review`로 분기).

### 4.4 SSE 이벤트

기존 4종(`stage_started`/`stage_completed`/`stage_failed`/`pipeline_result`)과 15초 heartbeat **무변경**. 정지 시에도 `pipeline_result`가 마지막에 정확히 1회 송출되고 제너레이터가 `return`하므로 `StopAsyncIteration`으로 스트림이 정상 종료된다 — `_sse_stream` 코드 변경 불필요.

### 4.5 `POST /api/v1/prompt-composer/sessions/{session_id}/versions` (신규)

**Request**
```json
{ "assembled": "당신은 여신 심사 문서를 ...", "tool_ids": ["internal:hybrid_search"] }
```
검증: `assembled` 1~4000자 (`PROMPT_MAX_CHARS`와 동일 상한) · `tool_ids` ≤ 50.

**Response 201**
```json
{ "session_id": "ps_...", "version_id": "pv_...", "version_no": 2, "source": "human" }
```

**동작**: 세션 소유권 검사(타인/부재 → 404) → `version_no = max+1` → `source='human'`, `sections={"purpose": "", "roles": [], "tool_guides": [], "principles": []}`(빈 구조 — 사람 편집본은 섹션 분해가 없음), `degraded=false`, `elapsed_ms=0`으로 append.

**Errors**: 401 인증 · 404 세션 없음/타인 소유(존재 비노출) · 422 검증 실패 · 500 저장 실패(전파).

### 4.6 Error Responses (파이프라인 동기 POST)

기존과 동일: 401 / 404(session_id) / 422(입력·생성 검증) / 500(저장 실패). 위저드는 `create`에 도달하지 않으므로 422·500 발생 지점이 `prompt` 버전 저장으로 한정된다.

---

## 5. UI/UX Design

### 5.1 Screen Layout

```
┌──────────────────────────────────────────────────────────────┐
│  에이전트 만들기                                    [취소]    │  고정 헤더
├───────────────────────────┬──────────────────────────────────┤
│                           │  ┌────────────────────────────┐  │
│   ① 설명 입력             │  │ 진행 상황                  │  │
│   ② 의도 질문 카드        │  │  ✔ 의도 파악        완료   │  │
│   ③ 도구 확인             │  │  ✔ 도구 추천        완료   │  │
│   ④ 프롬프트 검토         │  │  ● 프롬프트 생성    진행중 │  │
│                           │  │  ○ 에이전트 생성    대기   │  │
│   (단계별 본문 영역)      │  │  ○ 프롬프트 연결    대기   │  │
│    max-w-3xl              │  └────────────────────────────┘  │
│                           │   w-72, sticky                   │
└───────────────────────────┴──────────────────────────────────┘
        ↑ 스크롤 컨테이너 (패턴 A: 고정 헤더 + 스크롤 바디)
```

`AgentChatLayout`의 `<main>`이 `overflow: hidden`이므로 **패턴 A 스크롤 래퍼 필수** (idt_front CLAUDE.md).

### 5.2 User Flow

```
/agent-builder/new
  step=description ─[전송]→ SSE ─→ need_input      → step=intent
                                 → tools_proposed  → step=tools
  step=intent  ─[답변 제출]→ SSE ─→ need_input(재질문, 상한 도달까지)
                                 → tools_proposed  → step=tools
               ─[건너뛰기]→ 빈 answers 로 재호출
  step=tools   ─[이 도구로 진행]→ SSE(tools_confirmed, stop_after=prompt)
                                 → prompt_ready    → step=prompt
  step=prompt  ─[다시 생성]→ 동일 요청 재호출 (같은 session_id 재사용)
               ─[스튜디오로 보내기]→ 핸드오프 → navigate('/agent-builder')
  (any)        ─ 실패/끊김 → 해당 단계 error 표시 + [다시 시도]
  (플래그 off) ─ 404 → PipelineUnavailableCard + [에이전트 직접 만들기]
```

### 5.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `AgentCreateEntryPage` | `pages/AgentCreateEntryPage/index.tsx` | 위저드 셸 — step state, 단계 전이, 파이프라인 호출 오케스트레이션 |
| `WizardProgress` | `pages/AgentCreateEntryPage/components/` | `ProgressCard` 래퍼 — `pipelineStepsToProgress` 결과를 넘김 |
| `DescriptionStep` | 〃 | ① 설명 textarea(1~1000자) + `LoadingButton` |
| `IntentStep` | 〃 | ② `QuestionCardFlow` 렌더 + 건너뛰기 + 라운드 안내 |
| `ToolsStep` | 〃 | ③ 추천 도구 카드 토글 + `[도구 더 추가]`(ToolPickerModal) + `unknown_tool_ids` 안내 |
| `PromptStep` | 〃 | ④ 편집 textarea + 4000자 카운터 + `[다시 생성]`/`[스튜디오로 보내기]` |
| `WizardFailureCard` | 〃 | 단계 실패·SSE 끊김 안내 + `[다시 시도]`/`[처음부터]` |
| `PipelineUnavailableCard` | 〃 | 파이프라인 404 안내 + `[에이전트 직접 만들기]` |
| `EntryActionCards` | 〃 (기존) | 직접 만들기 / 가져오기(비활성) — 유지 |
| `ProgressCard` 외 2 | `components/common/` (기존) | 진행 표시 — **재사용, 신규 구현 금지** |
| `question-card/*` | `components/common/` (기존) | 질문 위저드 — **재사용, 신규 구현 금지** |
| `ToolPickerModal` | `components/agent-builder/` (기존) | 카탈로그 도구 선택 — 재사용 |

**제거**: `ComposeFailureCard.tsx`(→ `WizardFailureCard`로 대체), 페이지 내 compose 호출 로직 및 `toClarificationAnswers` 매퍼.

### 5.4 Page UI Checklist

#### `/agent-builder/new` — 공통 (모든 step)

- [ ] 진행바: `ProgressCard`, 항상 **5행** — 의도 파악 / 도구 추천 / 프롬프트 생성 / 에이전트 생성 / 프롬프트 연결
- [ ] 진행바 상태 배지: 완료 / 진행중 / 대기중 / 실패 (텍스트 병기, 색상 단독 금지)
- [ ] `degraded` 단계: 완료 표시 + `badgeLabel`에 사유 요약 (예: "규칙기반 폴백")
- [ ] 헤더: 타이틀 "에이전트 만들기" + `[취소]`(이탈 confirm)

#### step ① 설명 입력

- [ ] textarea: `aria-label` 지정, placeholder 예시 문장, 1~1000자, 실시간 글자수
- [ ] 버튼: `LoadingButton` "에이전트 만들기 시작" (`isPending` 필수, 공백 입력 차단)
- [ ] `EntryActionCards`: "에이전트 직접 만들기"(활성) / "에이전트 가져오기"(`aria-disabled="true"` + "준비 중")

#### step ② 의도 질문

- [ ] `QuestionCardFlow`: 질문당 카드 1장, 순차 제출, 선택지 + 직접입력
- [ ] 버튼: `[건너뛰고 계속]` (빈 answers 재호출)
- [ ] 안내: 남은 라운드 표시 (서버 `max_rounds` 정합)
- [ ] **스테일 카드 가드**: 새 응답 도착 시 이전 라운드 카드 잠금 해제/교체 (F10)

#### step ③ 도구 확인

- [ ] 추천 도구 카드 목록: 도구명 + 설명 + 체크박스(기본 전부 선택)
- [ ] 버튼: `[도구 더 추가]` → `ToolPickerModal` (카탈로그 전체)
- [ ] 사용자가 추가한 도구는 "직접 추가" 배지로 구분
- [ ] `unknown_tool_ids`가 있으면 안내 배너 ("N개 도구는 카탈로그에 없어 제외됨")
- [ ] 추천 0건이면 빈 상태 안내 + 카탈로그 추가 유도
- [ ] 버튼: `LoadingButton` "이 도구로 진행" / `[이전]`

#### step ④ 프롬프트 검토

- [ ] textarea: `assembled_prompt` 프리필, 편집 가능, `aria-label` 지정
- [ ] 글자수 카운터: `현재/4000`, 초과 시 경고색 + 진행 버튼 비활성
- [ ] `prompt_clamp_reason`이 있으면 절단 안내 배너
- [ ] `degraded_stages`에 `prompt` 포함 시 "규칙기반 폴백으로 생성됨" 안내
- [ ] 확정 도구 요약 칩 목록 (읽기 전용)
- [ ] 버튼: `[다시 생성]` (`LoadingButton`) / `LoadingButton` "스튜디오로 보내기" / `[이전]`

#### `/agent-builder` (스튜디오) — 위저드 프리필 시

- [ ] 이름: `suggested_name` 프리필 (편집 가능)
- [ ] 지침: 위저드 확정 프롬프트 프리필
- [ ] 도구 칩: 확정 `tool_ids` 프리필 (카탈로그 매핑 후)
- [ ] `[저장]` 성공 후: 프롬프트 세션 바인딩 수행, 실패 시 토스트 경고만(저장은 성공 유지)

### 5.5 진행 상태 매핑 어댑터

`src/utils/pipelineStepsToProgress.ts` — **단일 함수, 단일 소스**

| 백엔드 | 조건 | `ProgressStepStatus` | 비고 |
|--------|------|----------------------|------|
| `ok` | — | `completed` | |
| `degraded` | — | `completed` | `badgeLabel = reason 요약(≤12자)` |
| `failed` | — | `error` | `badgeLabel = "실패"` |
| `skipped` | — | `pending` | 미도달 |
| (steps에 없음) | SSE `stage_started` 수신 후 `stage_completed` 미수신 | `in_progress` | |

라벨 고정: `의도 파악` / `도구 추천` / `프롬프트 생성` / `에이전트 생성` / `프롬프트 연결`.

> `ProgressStepStatus`에 `degraded`를 새로 추가하지 **않는다** (Plan A-4 판정) — 공통 컴포넌트 계약을 이 사이클 요구로 바꾸면 다른 사용처가 생겼을 때 되돌리기 어렵다. `badgeLabel`이 이미 그 용도로 존재한다.

---

## 6. Error Handling

### 6.1 단계별 실패 매트릭스 (위저드 경로)

| 단계 | 실패 유형 | 처리 | 화면 |
|------|-----------|------|------|
| intent | LLM 실패 (`degraded=true`) | 되묻기 불능 → 의도 없이 진행 (기존 계약) | 진행바 완료+배지, step③으로 전진 |
| intent | 에코백 재검증 실패 | 에코백 폐기 후 LLM 재실행 (조용한 폴백) | 사용자에게 노출 안 함 |
| tools | 셀렉터 fallback | `final_ids` = 사용자 지정만. 빈 목록 허용 | 진행바 완료+배지, 빈 상태 안내 |
| tools | 후보 0건 | `empty_candidate_selection` (LLM 미호출) | "카탈로그에 활성 도구가 없습니다" |
| prompt | LLM 실패 → 규칙기반 폴백 | 폴백 프롬프트로 진행 | 진행바 완료+배지, "규칙기반으로 생성됨" |
| prompt | **버전 저장 실패 (DB)** | 예외 전파 → 500 (동기) / `stage_failed`+`pipeline_result(failed)` (SSE) | `WizardFailureCard` + `[다시 시도]` |
| — | SSE 연결 끊김 | 클라이언트가 감지 | 진행바 `error` + `[다시 시도]` (**중복 생성 없음** — create 미도달) |
| — | 파이프라인 404 (플래그 off) | 클라이언트가 감지 | `PipelineUnavailableCard` |
| 스튜디오 저장 | `POST /agents` 실패 | 기존 처리 그대로 | 기존 에러 표시 |
| 스튜디오 저장 | 사람 버전 append 실패 | **흡수** — 저장을 막지 않음 | 토스트 경고만 |
| 스튜디오 저장 | 바인딩 PATCH 실패(404/409) | **흡수** — 저장을 뒤집지 않음 | 토스트 경고만 |

### 6.2 UseCase try/except 정책 — 변경 없음

`bind`가 유일한 흡수 지점이라는 기존 계약을 유지한다. 정지 로직은 예외를 만들지 않으므로 새 `try/except`가 필요 없다. 프론트의 3개 흡수 지점(사람 버전 append / 바인딩 / 카탈로그 매핑 실패)은 **백엔드가 아니라 화면 계층**의 결정이며 각각 "이미 쓸 수 있는 결과(저장된 에이전트)가 존재한다"는 degraded 경계 기준을 만족한다.

### 6.3 중복 생성

위저드는 `create` 단계에 도달하지 않는다 → **`pipeline_result` 유실 후 재호출해도 에이전트가 중복 생성되지 않는다**. 기존 논스톱 경로의 R7 위험은 그대로 남지만 이 화면에는 해당 없음. 단, `prompt` 재호출 시 `session_id`를 재사용하지 않으면 세션이 늘어나므로 클라이언트가 반드시 에코백한다.

---

## 7. Security Considerations

- [x] 전 엔드포인트 `get_current_user` — 신규 `/sessions/{id}/versions` 포함. 무인증은 **401**(403 아님 — 실측으로 확정된 값)
- [x] `session_id` 소유권: 타인 세션 → **404**(존재 비노출). 신규 append 엔드포인트도 동일 규칙
- [x] 에코백 `intent`는 **재검증 후에만 신뢰** — spec 밖 slot key 폐기, 값 길이 clamp, 계산 필드(`complete`/`missing_slots`) 서버 재계산
- [x] `tool_ids`는 여전히 카탈로그 화이트리스트를 통과 — 위저드에서 임의 ID를 넣어도 `unknown_tool_ids`로 에코백되고 반영되지 않음
- [x] `visibility`는 파이프라인 요청에 노출하지 않음(private 고정). 위저드는 create를 안 하므로 스튜디오 기존 권한 규칙이 그대로 적용
- [x] 입력 상한 검증 422 · 프롬프트 4000자 clamp
- [x] 로그에 요청 원문·프롬프트 본문 미기록 (기존 PII 관례 승계). 신규 append 엔드포인트도 `assembled` 본문을 로그에 남기지 않음

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| Unit (domain) | `PipelinePolicy` 신규 5함수 | pytest | Do |
| Unit (application) | UseCase 정지 분기 · short-circuit | pytest + fake | Do |
| L1: API | 파이프라인 확장 · 신규 append 엔드포인트 | pytest TestClient | Do |
| Unit (FE) | 매핑 어댑터 · 단계 컴포넌트 | Vitest + RTL | Do |
| L2/L3 (FE) | 위저드 통합 시나리오 | Vitest + RTL + MSW | Do |
| 수동 E2E | 실서버 완주 + `GET /agents/{id}` 일치 | 브라우저 | Check |

### 8.2 L1: API Test Scenarios

| # | Endpoint | Test Description | Expected |
|---|----------|-----------------|----------|
| 1 | `POST /pipeline` | `stop_after` 미지정 → **기존 논스톱 동작과 응답 동일** (회귀 잠금) | 200, `status=created`, 기존 101케이스 전량 통과 |
| 2 | `POST /pipeline` | `stop_after="tools"`, 의도 충족 | 200, `status=tools_proposed`, `steps` 5개(prompt~bind = `skipped`/`stopped_for_review`), `recommended_tool_ids` 존재 |
| 3 | `POST /pipeline` | `stop_after="tools"`, 의도 미충족 | 200, `status=need_input`(정지 지점보다 되묻기가 우선), `questions` 존재 |
| 4 | `POST /pipeline` | `stop_after="prompt"` + `tools_confirmed=true` + `tool_ids=[A]` | 200, `status=prompt_ready`, `final_tool_ids == ["A"]`, **셀렉터 미호출**(스파이 단언), `session_id`/`version_id` 존재 |
| 5 | `POST /pipeline` | `tools_confirmed=true`인데 셀렉터가 B를 추천하도록 설정 | `final_tool_ids`에 **B가 없음** (D1 회귀 방지 — 사용자 제거 도구 부활 차단) |
| 6 | `POST /pipeline` | `stop_after="prompt"` + 유효한 `intent` 에코백 | intent LLM **미호출**(스파이), `steps.intent.reason == "확정된 의도 재사용"` |
| 7 | `POST /pipeline` | `intent` 에코백에 spec 밖 slot key / degraded=true | 에코백 폐기 → intent LLM 호출됨 |
| 8 | `POST /pipeline` | `assembled`가 4000자 초과하도록 설정 + `stop_after="prompt"` | `assembled_prompt` 길이 == 4000, `prompt_clamp_reason` 비어있지 않음 (D3) |
| 9 | `POST /pipeline` | `stop_after="bogus"` | 422 |
| 10 | `POST /pipeline/stream` | `stop_after="tools"` | `stage_started`×2, `stage_completed`×2, `pipeline_result`×1, 스트림 정상 종료, `id:` seq 단조 증가 |
| 11 | `POST /pipeline/stream` | 정지 응답의 `pipeline_result` payload | 동기 `POST` 응답과 **바이트 동일** (FR-15 확장 단언) |
| 12 | `POST /pipeline` (+`/stream`) | 무인증 | **401** (`== 401` 고정 단언) |
| 13 | `POST /sessions/{id}/versions` | 본인 세션 + 유효 `assembled` | 201, `version_no == 기존max+1`, `source == "human"` |
| 14 | `POST /sessions/{id}/versions` | 타인 세션 / 없는 세션 | **404** (403 아님) |
| 15 | `POST /sessions/{id}/versions` | `assembled` 0자 / 4001자 | 422 |
| 16 | `POST /sessions/{id}/versions` | 무인증 | 401 |
| 17 | `POST /compose` (기존) | 기존 LLM 버전 append | `source == "llm"` (기본값 회귀 확인) |
| 18 | `GET /sessions/{id}` (기존) | 버전 목록 조회 | 신규 컬럼 추가 후에도 기존 응답 필드 무변경 |

### 8.3 Unit 핵심 케이스 (domain — LLM 목 없이)

| # | 함수 | 케이스 |
|---|------|--------|
| 1 | `stages_to_run(None)` | `(tools, prompt, create, bind)` — 기존 하드코딩 튜플과 동일 |
| 2 | `stages_to_run(TOOLS)` | `(tools,)` |
| 3 | `stages_to_run(PROMPT)` | `(tools, prompt)` |
| 4 | `decide_after_stage` | 각 (stage, stop) 조합 10건 |
| 5 | `stop_status` | 2값 매핑 + wire 문자열 고정 |
| 6 | `confirmed_selection` | 순서 보존 dedupe · `fallback == False` · `final_ids == required_ids` |
| 7 | `confirmed_selection([])` | 빈 목록 허용, 예외 없음 |
| 8 | `reuse_intent` | 유효 에코백 통과 / spec 밖 key 폐기 / degraded 무시 / 값 clamp / `complete` 재계산 |
| 9 | `PipelineStop` / 신규 status | `.value` 문자열 고정 (프론트 계약 파손 방지) |

### 8.4 L2: UI Action Test Scenarios (Vitest + RTL + MSW)

| # | Step | Action | Expected |
|---|------|--------|----------|
| 1 | ① | 페이지 로드 | §5.4 공통 + step① 체크리스트 요소 전부 렌더, 진행바 5행 |
| 2 | ① | 공백 입력 후 전송 | 호출 없음, 버튼 비활성 |
| 3 | ① | 설명 입력 → 전송 (`need_input` 응답) | step②로 전환, `QuestionCardFlow` 렌더 |
| 4 | ② | 질문 순차 답변 완료 | 요청 body에 `answers[]`·`round`·`stop_after:"tools"` 포함 (**request body 단언**) |
| 5 | ② | 새 응답 도착 | 이전 라운드 카드가 남지 않음 (F10 스테일 가드) |
| 6 | ② | `[건너뛰고 계속]` | 빈 `answers`로 재호출 |
| 7 | ③ | `tools_proposed` 렌더 | 추천 도구 카드 N개, 기본 전부 체크 |
| 8 | ③ | 도구 1개 해제 → `[이 도구로 진행]` | 요청 body의 `tool_ids`에 해제된 ID **없음**, `tools_confirmed:true`, `stop_after:"prompt"` |
| 9 | ③ | `[도구 더 추가]` → 모달에서 선택 | `tool_ids`에 추가됨, "직접 추가" 배지 표시 |
| 10 | ③ | `unknown_tool_ids` 있는 응답 | 안내 배너 표시 |
| 11 | ④ | `prompt_ready` 렌더 | textarea에 `assembled_prompt` 프리필, 카운터 표시 |
| 12 | ④ | 4000자 초과 입력 | 경고색 + 진행 버튼 비활성 |
| 13 | ④ | `[다시 생성]` | 동일 `session_id`로 재호출 |
| 14 | ④ | `[스튜디오로 보내기]` | `agentDraftStore.pendingIntent`가 `kind:'wizard'`로 설정, `/agent-builder`로 이동 |
| 15 | any | 500 응답 | `WizardFailureCard` + `[다시 시도]` |
| 16 | any | 404 응답 (플래그 off) | `PipelineUnavailableCard` + `[직접 만들기]` |
| 17 | 진행바 | `degraded` 포함 응답 | 해당 행 완료 + 사유 배지 |
| 18 | 진행바 | `stage_started` 수신 중 | 해당 행 `진행중` |

### 8.5 L3: E2E Scenario Test Scenarios

| # | Scenario | Steps | Success Criteria |
|---|----------|-------|-----------------|
| 1 | 되묻기 완주 | 설명 → 질문 2개 답변 → 도구 확정 → 프롬프트 확인 → 스튜디오 | 스튜디오 폼에 이름·지침·도구 칩 프리필 |
| 2 | 되묻기 없음 | 상세한 설명 1문장 → 바로 도구 단계 | step② 건너뜀, 진행바 의도=완료 |
| 3 | 저장 + 바인딩 | 시나리오 1 이어서 `[저장]` | `POST /agents` 201 → `PATCH /sessions/{id}` 호출됨 |
| 4 | 프롬프트 편집 저장 | 프롬프트 수정 → 스튜디오 → `[저장]` | `POST /sessions/{id}/versions` 호출됨(`source=human`), 저장된 `system_prompt`=편집본 |
| 5 | 바인딩 실패 내성 | `PATCH`가 409 반환 | 저장은 성공 유지, 경고 토스트만 |
| 6 | 이탈 경고 | 진행 중 `[취소]` | confirm 표시, 확인 시 상태 소실 |
| 7 | 기존 경로 회귀 | 사이드바 외 3개 진입 버튼 · Fix 탭 compose | 전부 기존대로 동작 |
| 8 | 수동 실서버 | 완주 후 `GET /api/v1/agents/{id}` | `system_prompt`·`tool_ids`가 위저드 확정값과 일치 (**SC-2 + 파이프라인 이월 #15 동시 소화**) |

### 8.6 Seed Data Requirements

| Entity | Minimum Count | Key Fields |
|--------|:------------:|------------|
| `tool_catalog` 활성 도구 | 5 | `tool_id`, `name`, `description`(추천 품질에 필요) |
| `llm_model` | 1 | `id`(에이전트 생성 FK) |
| `prompt_session` + `prompt_version` | 1 + 1 | append 테스트용 (`version_no=1`, `source='llm'`) |

---

## 9. Clean Architecture

### 9.1 This Feature's Layer Assignment

**백엔드 (`idt/`)**

| Component | Layer | Location |
|-----------|-------|----------|
| `PipelineStop` | Domain | `src/domain/agent_create_pipeline/stages.py` |
| `PipelinePolicy` 신규 5함수 | Domain | `src/domain/agent_create_pipeline/policies.py` |
| `PipelineOutcome` 확장 | Application | `src/application/agent_create_pipeline/events.py` |
| UseCase 정지 순회 | Application | `src/application/agent_create_pipeline/use_case.py` |
| `AppendHumanVersionUseCase` | Application | `src/application/prompt_composer/append_human_version_use_case.py` |
| `PromptVersionModel.source` | Infrastructure | `src/infrastructure/prompt_composer/models.py` |
| V063 마이그레이션 | Infrastructure | `db/migration/V063__add_source_to_prompt_version.sql` |
| 요청/응답 스키마 | Interfaces | `src/interfaces/schemas/agent_pipeline.py`, `prompt_composer.py` |
| 라우터 확장/신설 | Interfaces | `src/api/routes/agent_pipeline_router.py`, `prompt_composer_router.py` |

**프론트엔드 (`idt_front/`)**

| Component | Layer | Location |
|-----------|-------|----------|
| 타입·상수 | Domain | `src/types/agentPipeline.ts` |
| 매핑 어댑터 | Domain(순수) | `src/utils/pipelineStepsToProgress.ts` |
| 폼 변환 | Domain(순수) | `src/utils/wizardResultToForm.ts` |
| SSE 훅 | Application | `src/hooks/useAgentPipelineStream.ts` |
| 핸드오프 스토어 | Application | `src/store/agentDraftStore.ts` |
| API 호출 | Infrastructure | `src/services/agentPipelineService.ts`, `promptComposerService.ts` |
| 위저드 화면 | Presentation | `src/pages/AgentCreateEntryPage/**` |

### 9.2 Dependency Rules 준수 확인

- [x] `domain/agent_create_pipeline` → `domain/intent`, `domain/tool_selection`만 참조 (domain → domain)
- [x] `PipelinePolicy`는 여전히 **정적 순수 함수만** — I/O·시간·랜덤 없음
- [x] `application` → `domain` + `application`(prompt_composer) — 기존 방향 유지
- [x] 프론트 컴포넌트는 `services/`를 직접 import하지 않고 훅 경유
- [x] 컴포넌트 파일에 런타임 상수 export 없음 (`types/`로 분리)
- [x] `tool_selection` 모듈 신규 import 없음 → `_DECLARED_CONSUMERS` **갱신 불필요**(기존 4파일 그대로. Do 단계에서 실측 확인)

---

## 10. Coding Convention Reference

### 10.1 This Feature's Conventions

| Item | Convention Applied |
|------|-------------------|
| wire 문자열 | StrEnum `.value` — `PipelineStop`, 신규 status 2값. 테스트로 고정 |
| 계약 확장 | additive — 신규 요청 필드 전부 no-op 기본값, 신규 응답 필드 optional |
| DDL | 테이블·전 컬럼 `COMMENT` + SQLAlchemy `comment=` 동일 문구, **COMMENT 내 콤마 금지** |
| 로깅 | `logger.warning(..., exception=e)` (문자열 `error=str(e)` 금지) |
| 컴포넌트 | 함수형 + arrow, `interface` props 상단, `export default` 하단 단독 |
| 상수 | `as const` 객체 + 타입 추출, `types/`에 배치 |
| 뮤테이션 버튼 | `LoadingButton` + `isPending` 필수 prop |
| 쿼리 키 | `lib/queryKeys.ts` 팩토리에서만 정의 |
| 스타일 | violet-600 계열 · `rounded-2xl` · 패턴 A 스크롤 래퍼 |
| 테스트 | 백엔드 pytest 4계층 / 프론트 Vitest+RTL+MSW, TDD Red→Green |

### 10.2 Plan FR → Design 절 매핑

> 파이프라인 사이클 교훈(G-04: Plan 요구가 Design에서 유실되어 구현도 함께 누락)의 재발 방지 장치.

| FR | Design 절 | FR | Design 절 |
|----|-----------|----|-----------|
| FR-B01 | §3.1, §3.2, §4.2 | FR-F01 | §5.2, §5.3 |
| FR-B02 | §3.3, §4.3 | FR-F02 | §5.1, §5.4 |
| FR-B03 | §4.3 (tools_proposed) | FR-F03 | §5.5 |
| FR-B04 | §4.3 (prompt_ready) | FR-F04 | §5.3, §5.4 step②, §8.4 #5 |
| FR-B05 | §2.2, §3.2 `reuse_intent` | FR-F05 | §5.4 step② |
| FR-B06 | §3.4, §4.5 | FR-F06 | §5.4 step③, §8.4 #8·#9 |
| FR-B07 | §4.4 | FR-F07 | §5.4 step③, §8.4 #10 |
| FR-B08 | §3.2 `confirmed_selection`, D1 | FR-F08 | §5.4 step④, §8.4 #12 |
| FR-B09 | §8.2 #1, §8.3 #1 | FR-F09 | §2.1, §9.1 |
| FR-B10 | §11.2 module-1 | FR-F10 | §6.1, §6.3 |
| FR-B11 | §9.2 (갱신 불필요 판정) | FR-F11 | §11.1 store, §2.2 핸드오프 |
| FR-B12 | §4.1 | FR-F12 | §9.1 `wizardResultToForm` |
| FR-B13 | §7 | FR-F13 | §2.2, §6.1, §8.5 #3·#5 |
| | | FR-F14 | §5.3 (제거 목록) |
| | | FR-F15 | §5.3, §8.4 #16 |
| | | FR-F16 | §5.2, §8.5 #6 |
| | | FR-F17 | §3.5, §9.1 |
| | | FR-F18 | §5.4, §10.1 |

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt/
├── db/migration/
│   └── V063__add_source_to_prompt_version.sql                    [신규]
├── src/domain/agent_create_pipeline/
│   ├── stages.py                          + PipelineStop         [수정]
│   └── policies.py                        + 5 함수               [수정]
├── src/application/agent_create_pipeline/
│   ├── events.py                          + status 2값·2필드     [수정]
│   └── use_case.py                        정지 순회로 교체       [수정]
├── src/application/prompt_composer/
│   └── append_human_version_use_case.py                          [신규]
├── src/infrastructure/prompt_composer/
│   ├── models.py                          + source               [수정]
│   └── repositories.py                    append(source=)        [수정]
├── src/interfaces/schemas/
│   ├── agent_pipeline.py                  요청 3·응답 2 필드     [수정]
│   └── prompt_composer.py                 + AppendVersion 2종    [수정]
├── src/api/routes/
│   ├── agent_pipeline_router.py           _run_kwargs 확장       [수정]
│   └── prompt_composer_router.py          + POST versions        [수정]
├── src/api/main.py                        DI 1개 추가            [수정]
├── .env                                   플래그 2개             [수정]
└── tests/
    ├── domain/agent_create_pipeline/test_policies.py             [수정]
    ├── application/agent_create_pipeline/test_use_case.py        [수정]
    ├── application/prompt_composer/test_append_human_version.py  [신규]
    ├── api/test_agent_pipeline_router.py                         [수정]
    ├── api/test_prompt_composer_router.py                        [수정]
    └── db/ (DDL COMMENT 검사는 기존 테스트가 자동 적용)

idt_front/
├── src/types/agentPipeline.ts                                    [신규]
├── src/constants/api.ts                   엔드포인트 3개          [수정]
├── src/services/
│   ├── agentPipelineService.ts            동기 + SSE             [신규]
│   └── promptComposerService.ts           append + bind          [신규]
├── src/hooks/useAgentPipelineStream.ts                           [신규]
├── src/utils/
│   ├── pipelineStepsToProgress.ts (+.test)                       [신규]
│   └── wizardResultToForm.ts (+.test)                            [신규]
├── src/store/agentDraftStore.ts           kind:'wizard' 추가     [수정]
├── src/pages/AgentCreateEntryPage/
│   ├── index.tsx                          전면 교체              [수정]
│   ├── index.test.tsx                     전면 교체              [수정]
│   └── components/
│       ├── WizardProgress.tsx (+.test)                           [신규]
│       ├── DescriptionStep.tsx (+.test)                          [신규]
│       ├── IntentStep.tsx (+.test)                               [신규]
│       ├── ToolsStep.tsx (+.test)                                [신규]
│       ├── PromptStep.tsx (+.test)                               [신규]
│       ├── WizardFailureCard.tsx                                 [신규]
│       ├── PipelineUnavailableCard.tsx                           [신규]
│       ├── ComposeFailureCard.tsx                                [제거]
│       └── EntryActionCards.tsx                                  [유지]
├── src/pages/AgentBuilderPage/index.tsx   프리필 분기 + 바인딩   [수정]
└── src/__tests__/
    ├── mocks/handlers.ts                  파이프라인 핸들러      [수정]
    └── integration/agentCreateWizard.test.tsx                    [신규]
        (기존 agentCreateEntry.test.tsx 는 [제거])
```

### 11.2 Implementation Order

1. [ ] **백엔드 활성화** — 미커밋 슬라이스 커밋, `.env` 플래그, V061/V062 적용 확인, `POST /api/v1/agents/pipeline` 200 스모크
2. [ ] V063 + `source` 컬럼 + `AppendHumanVersionUseCase` + 신규 엔드포인트 (테스트 선작성)
3. [ ] domain `PipelineStop` + Policy 5함수 (순수 테스트 선작성 → red → green)
4. [ ] application UseCase 정지 순회 교체 + `_stopped_outcome` 통합
5. [ ] 스키마·라우터 확장 + L1 테스트 18건
6. [ ] **회귀 확인** — 기존 101케이스 + 전체 스위트 `FAILED` 목록 diff
7. [ ] 프론트 타입·상수·서비스·SSE 훅
8. [ ] 매핑 어댑터 + `WizardProgress` (테스트 선작성)
9. [ ] 단계 컴포넌트 4종 + 실패/폴백 카드
10. [ ] 위저드 셸 오케스트레이션 + 핸드오프
11. [ ] 스튜디오 프리필 분기 + 저장 후 append/bind
12. [ ] 통합 테스트 + 프론트 회귀 확인

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Est. Turns |
|--------|-----------|-------------|:----------:|
| 백엔드 활성화 + 사람 버전 | `module-1` | 커밋·플래그·마이그레이션 + V063 + append 엔드포인트 (구현순서 1~2) | 25-35 |
| 백엔드 정지 지점 | `module-2` | domain Policy + UseCase + 스키마/라우터 + L1 18건 + 회귀 (3~6) | 40-50 |
| 프론트 기반 | `module-3` | 타입·상수·서비스·SSE 훅·매핑 어댑터·WizardProgress (7~8) | 35-45 |
| 프론트 위저드 UI | `module-4` | 단계 컴포넌트 4종 + 실패/폴백 + 셸 오케스트레이션 (9~10) | 45-55 |
| 핸드오프 + 저장 배선 | `module-5` | 스튜디오 프리필 분기 + append/bind + 통합 테스트 (11~12) | 30-40 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Plan + Design | 전체 | 완료 |
| Session 2 | Do | `--scope module-1` | 25-35 |
| Session 3 | Do | `--scope module-2` | 40-50 |
| Session 4 | Do | `--scope module-3,module-4` | 60-80 |
| Session 5 | Do | `--scope module-5` | 30-40 |
| Session 6 | Check + Report | 전체 | 30-40 |

> **module-1을 반드시 먼저** — 파이프라인이 404인 상태로는 module-2 이후의 어떤 것도 실동작 검증이 불가능하다.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-20 | 최초 작성 — Option C 선택. 설계 판단 D1(tools_confirmed)·D2(intent 에코백)·D3(정지 시 clamp) 추가. Plan 열린질문 A-1~A-7 전부 판정 | 배상규 |
