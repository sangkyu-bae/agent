# agent-create-pipeline Design Document

> **Summary**: intent → 도구 추천 → 프롬프트 생성 → 에이전트 생성 → 세션 바인딩을 조합하는 오케스트레이션 파이프라인의 상세 설계. Option C(Pragmatic) — domain에 단계 상태 VO·Policy·스펙 상수만 신설하고, 실행은 기존 UseCase 3종 + `ToolSelectorPort` 직접 주입으로 조합한다.
>
> **Project**: sangplusbot (idt — 백엔드)
> **Author**: 배상규
> **Date**: 2026-08-18
> **Status**: Draft
> **Planning Doc**: [agent-create-pipeline.plan.md](../../01-plan/features/agent-create-pipeline.plan.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | intent·tool_selection·prompt_composer가 배선 없이 각자 떠 있어, 에이전트 자동 생성의 end-to-end 가치가 한 번도 증명된 적 없다 |
| **WHO** | P2(에이전트 소유자). 이번 사이클 1차 소비자는 API 호출자(백엔드) — 프론트 배선은 후속 사이클 |
| **RISK** | 도구선택+프롬프트 규칙 3벌 공존(AgentComposer / v3 auto / 신규). 수렴 계획 없이 방치되면 규칙이 벌어진다 |
| **SUCCESS** | 기존 경로 회귀 0건 · 되묻기 왕복 후 재호출로 생성 완주 · LLM 단계별 실패는 200+degraded, 저장 실패는 5xx · 생성된 agent_id 조회 가능 + 세션 바인딩 확인 · SSE 이벤트 순서가 단계 정의와 일치 |
| **SCOPE** | 오케스트레이션 UseCase + 신규 라우터(POST + SSE) + 단계 상태 모델 + intent 스펙 서버 소유 + 도구 추천 어댑터. **밖**: 프론트 UI, 기존 경로 수정, 신규 테이블 |

---

## 1. Overview

### 1.1 Design Goals

1. **조합만 한다** — 판정·추천·생성·저장의 실제 일은 전부 기존 모듈이 하고, 파이프라인은 순서·데이터 전달·실패 정책만 소유한다. 신규 LLM 호출 로직 0.
2. **단계 상태는 1급 계약** (Plan D8) — 모든 단계 결과가 `StageRecord`로 남고, 동기 응답과 SSE가 같은 기록을 공유한다.
3. **규칙은 domain, 흐름은 application** — 단계 전이·병합·폴백 판정은 순수 함수(Policy)로 두어 LLM 목 없이 테스트한다. 후속 R1 수렴 시 이 Policy를 재사용한다.

### 1.2 Design Principles

- 기존 5개 경로 물리적 무변경 (Plan D1 / FR-11)
- degraded 경계: "쓸 수 있는 결과가 존재하는가" — LLM 실패는 폴백, 저장 실패는 전파 (위키 `degradation-vs-failure-boundary`)
- stateless: 서버는 왕복 사이에 아무것도 기억하지 않는다 (위키 `stateless-hitl-clarification`, v3 세션 루프와 구분)
- LLM 출력 신뢰 경계: 파이프라인은 LLM을 직접 부르지 않으므로 신규 노출면 없음 — 각 모듈의 Draft/Result 분리를 그대로 신뢰

---

## 2. Architecture

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | UseCase 1개 직조합, 신규 domain 없음 | 파이프라인 전용 포트 4종 + 어댑터 랩핑 | domain VO/Policy/스펙만 신설, 기존 UseCase 직접 주입 |
| **New Files** | ~7 | ~18 | ~12 |
| **Modified Files** | 1 | 1 | 1 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Medium | High (이중 추상화 대가) | High |
| **Effort** | Low | High | Medium |
| **Risk** | 규칙이 흐름 코드에 묻힘 — R1 수렴 시 재사용 불가 | 과도한 추상화(금지 규칙 긴장) | Low |

**Selected**: **Option C** — Plan §7.2에서 "UseCase 직접 주입" 기확정. 규칙만 domain으로 분리해 순수 테스트 + R1 수렴 재사용성 확보. (Checkpoint 3 사용자 확정)

### 2.1 Component Diagram

```
POST /api/v1/agents/pipeline          POST /api/v1/agents/pipeline/stream
        │ (최종 결과만)                        │ (이벤트 실시간 송출)
        ▼                                     ▼
  ┌──────────────────── interfaces: pipeline_router ────────────────────┐
  │  동기 핸들러: 제너레이터 소진 → 최종 응답    SSE 핸들러: 이벤트 → wire │
  └──────────────────────────────┬──────────────────────────────────────┘
                                 ▼
  application/agent_create_pipeline/AgentCreatePipelineUseCase.run()
  = async generator — 단계마다 StageEvent yield, 마지막에 PipelineOutcome
        │
        ├─① intent    → application/intent.AnalyzeIntentUseCase (재사용)
        │               spec = domain/agent_create_pipeline/spec.py (서버 소유)
        │               └─ complete=false → questions 반환, 이후 단계 중단
        ├─② tools     → domain/tool_selection.ToolSelectorPort (기존 포트)
        │               구현: infrastructure/tool_selection.LLMToolSelector (재사용)
        │               후보: ToolCandidateReaderPort ← tool_catalog 어댑터 (신규·얇음)
        ├─③ prompt    → application/prompt_composer.ComposePromptUseCase (재사용)
        │               → prompt_session/version 저장 (기존 테이블)
        ├─④ create    → application/agent_builder.CreateAgentUseCase (재사용)
        │               → agent_definition 생성
        └─⑤ bind      → ComposePromptUseCase.bind_agent (재사용, 실패해도 진행)

  단계 전이·병합·steps 판정: domain/agent_create_pipeline/policies.PipelinePolicy (순수)
```

### 2.2 Data Flow

```
[1차 호출] user_request(+history, tool_ids?)
  → intent 판정 (spec 주입)
     ├─ complete=false → {status:"need_input", questions, steps[intent]} 반환 ── 화면이 질문 렌더
     └─ complete=true 또는 degraded → 계속
  → 도구 추천: query = user_request + filled_slots 요약
     required_ids = 사용자 tool_ids (포트 계약이 항상 포함 보장)
  → 프롬프트 생성: intent + final_ids → sections + assembled + version 저장
  → 에이전트 생성: assembled(≤4000 clamp) + final_ids + name → agent_id
  → 세션 바인딩: session_id ← agent_id
  → {status:"created", agent_id, session_id, steps[...]} 반환

[재호출(되묻기 답변)] user_request + answers[] + round + questions 에코백
  → 같은 흐름. round는 Policy가 재clamp (클라이언트 신고값 불신)
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `AgentCreatePipelineUseCase` | `AnalyzeIntentUseCase` | 의도 판정 + 되묻기 (재사용) |
| 〃 | `ToolSelectorPort` + `ToolCandidateReaderPort` | 도구 추천 (기존 셀렉터 + 신규 후보 로더) |
| 〃 | `ComposePromptUseCase` | 프롬프트 생성 + 세션/버전 저장 + bind (재사용) |
| 〃 | `CreateAgentUseCase` | agent_definition 생성 (재사용) |
| 〃 | `PipelinePolicy` | 단계 전이·병합·steps 판정 (신규, 순수) |
| `ToolCandidateReaderPort` 어댑터 | tool_catalog Repository | 전체 활성 도구 → `ToolCandidate` 변환 |
| `NullToolSelector` (infra) | — | 셀렉터 LLM 미구성·조립 실패 시 강하 구현 — required만 통과, `fallback=true`. 라우터 미등록 낙하가 아니라 degraded 진행 (v0.2 — Do에서 추가, D-04) |

---

## 3. Data Model

> 신규 DB 테이블 **없음** (Plan O3). 아래는 전부 in-memory VO다.

### 3.1 domain/agent_create_pipeline/stages.py

```python
class PipelineStage(str, Enum):
    INTENT = "intent"; TOOLS = "tools"; PROMPT = "prompt"
    CREATE = "create"; BIND = "bind"

class StageStatus(str, Enum):
    OK = "ok"; DEGRADED = "degraded"; FAILED = "failed"; SKIPPED = "skipped"

@dataclass(frozen=True)
class StageRecord:            # 응답 steps[]의 원소이자 SSE 이벤트 payload
    stage: PipelineStage
    status: StageStatus
    reason: str | None = None      # degraded/failed 사유 (사람이 읽는 한국어)
    elapsed_ms: int = 0
```

```python
# application 레이어 이벤트 (async generator가 yield)
@dataclass(frozen=True)
class StageEvent:
    kind: Literal["stage_started", "stage_completed", "stage_failed"]
    record: StageRecord            # started 시 status는 의미 없음(진행 표시용)

@dataclass(frozen=True)
class PipelineOutcome:             # 제너레이터의 마지막 yield
    status: Literal["need_input", "created"]
    steps: tuple[StageRecord, ...]
    questions: tuple[SlotQuestion, ...] = ()    # need_input일 때
    round: int = 0
    intent: IntentResult | None = None
    recommended_tool_ids: tuple[str, ...] = ()
    final_tool_ids: tuple[str, ...] = ()
    session_id: str | None = None
    version_id: str | None = None
    agent_id: str | None = None                 # created일 때
    agent_name: str | None = None
    assembled_prompt: str | None = None
    bind_ok: bool | None = None
```

### 3.2 domain/agent_create_pipeline/spec.py — intent 스펙 (서버 소유, Plan D5)

슬롯만 있는 `IntentSpec` (labels 없음 — `IntentSpec` docstring이 예정한 "에이전트 생성이 쓰는 형태"):

| slot key | required | description | options (앵커링 예시) |
|----------|:--------:|-------------|------------------------|
| `purpose` | **✓** | 에이전트가 해결할 핵심 업무/목적 | — |
| `target_users` | ✗ | 누가 쓰는 에이전트인지 | 팀 내부, 전사, 고객 응대 |
| `data_sources` | ✗ | 참조할 자료·지식 출처 | 사내 문서, 웹 검색, DB |
| `tone` | ✗ | 응답 말투·형식 | 격식체, 간결한 요약, 상세 설명 |

- `SlotLimits`는 intent 기본값(max_rounds=2, max_questions=3)을 그대로 쓰되 config로 오버라이드 가능하게 어댑터에서 주입.
- 스펙은 상수지만 **domain이 env를 읽지 않는다** — config 오버라이드는 infrastructure/config가 조립 시 반영.

### 3.3 domain/agent_create_pipeline/policies.py — PipelinePolicy (순수 함수)

| 함수 | 규칙 |
|------|------|
| `decide_after_intent(result) -> "ask" \| "proceed"` | `complete=false`이고 `degraded=false`이고 questions 있음 → `ask`. **degraded면 무조건 proceed** (의도 모름 = 되묻기 불능, FR-07) |
| `build_selector_query(user_request, result) -> str` | user_request + filled_slots를 "축: 값" 줄로 요약 결합 (degraded/None이면 user_request만) |
| `resolve_tool_ids(selection, user_ids) -> tuple` | selection.final_ids 그대로 (포트 계약이 required ⊆ final 보장). selection 자체가 실패 산출물(fallback)이면 final_ids는 required만 남는다 — 추가 처리 없음 |
| `resolve_agent_name(explicit, result, user_request) -> str` | 명시 name > `purpose` 슬롯 값 요약 > user_request 앞 30자. 200자 clamp |
| `clamp_prompt(assembled) -> str` | `CreateAgentRequest.system_prompt` 상한 4000자 clamp (초과 시 절단 + 로그 — 절단 여부를 StageRecord.reason에 기록) |
| `finalize_steps(records, halted_at) -> tuple` | 미도달 단계를 `SKIPPED`로 채워 항상 5단계 전체를 반환 (화면이 단계 목록을 고정 렌더 가능) |
| `clamp_round(round_) -> int` | 0 ≤ round ≤ max_rounds 재clamp (클라이언트 신고값 불신) |

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/api/v1/agents/pipeline` | 동기 실행 — 최종 결과 JSON | Required (header) |
| POST | `/api/v1/agents/pipeline/stream` | SSE 실행 — 단계 이벤트 + 최종 결과 | Required (header) |

라우터 prefix는 `/api/v1/agents`(기존 태그와 분리된 신규 라우터 파일) — v3 auto와 경로·태그로 명확히 구분 (Plan R6). **`/pipeline`이 `/{agent_id}` 와일드카드보다 먼저 매칭되도록 신규 라우터를 agent_builder_router보다 앞서 include** (라우터 등록 순서 테스트 필수 — 위키 router-map 관례).

> **SSE가 GET이 아닌 이유**: 입력이 본문(history, answers 등)이라 query로 못 싣는다. EventSource 대신 fetch-stream 소비를 전제하며, 덕분에 인증도 query-token 특례 없이 표준 헤더로 통일한다. (기존 `run/stream`의 GET+query-token은 EventSource 제약 때문이었음 — 본 설계는 그 제약을 갖지 않는다)

### 4.2 Request (두 엔드포인트 동일)

```json
{
  "user_request": "여신 심사 문서를 검색해서 요약해주는 에이전트 만들어줘",
  "history": [{"role": "user", "content": "..."}],
  "answers": [{"slot_key": "purpose", "value": "여신 심사 문서 Q&A"}],
  "round": 1,
  "questions": [{"slot_key": "...", "question": "...", "options": []}],
  "tool_ids": ["internal:hybrid_search"],
  "name": "여신 도우미",
  "llm_model_id": null,
  "session_id": null
}
```

검증(422): `user_request` 1~1000자 · `history` 최대 20턴(초과 최신 우선 절단) · `tool_ids` 최대 50개 · `round` ≥ 0 · `name` ≤ 200자. `questions`/`answers`는 되묻기 에코백 (1차 호출엔 없음). `session_id`는 재생성 시 기존 프롬프트 세션 재사용(선택 — prompt_composer FR-08 그대로).

### 4.3 Response — 동기 POST 200

**되묻기 (need_input)**:
```json
{
  "status": "need_input",
  "round": 1,
  "questions": [
    {"slot_key": "purpose", "question": "이 에이전트의 핵심 용도는 무엇인가요?",
     "options": ["문서 Q&A", "보고서 작성"], "allow_free_text": true}
  ],
  "intent": {"filled_slots": {"target_users": "심사팀"}, "missing_slots": ["purpose"], "degraded": false},
  "steps": [
    {"stage": "intent", "status": "ok", "reason": null, "elapsed_ms": 812},
    {"stage": "tools",  "status": "skipped", "reason": "need_input", "elapsed_ms": 0},
    {"stage": "prompt", "status": "skipped", "reason": "need_input", "elapsed_ms": 0},
    {"stage": "create", "status": "skipped", "reason": "need_input", "elapsed_ms": 0},
    {"stage": "bind",   "status": "skipped", "reason": "need_input", "elapsed_ms": 0}
  ]
}
```

**완료 (created)**:
```json
{
  "status": "created",
  "agent_id": "agt_...",
  "agent_name": "여신 도우미",
  "session_id": "ps_...",
  "version_id": "pv_...",
  "recommended_tool_ids": ["internal:hybrid_search", "internal:doc_browse"],
  "final_tool_ids": ["internal:hybrid_search", "internal:doc_browse"],
  "assembled_prompt": "...",
  "bind_ok": true,
  "degraded_stages": [],
  "steps": [
    {"stage": "intent", "status": "ok", "reason": null, "elapsed_ms": 812},
    {"stage": "tools",  "status": "ok", "reason": null, "elapsed_ms": 640},
    {"stage": "prompt", "status": "degraded", "reason": "LLM 시간 초과 — 규칙기반 폴백", "elapsed_ms": 8000},
    {"stage": "create", "status": "ok", "reason": null, "elapsed_ms": 120},
    {"stage": "bind",   "status": "ok", "reason": null, "elapsed_ms": 15}
  ]
}
```

`degraded_stages`는 `steps`에서 파생되는 편의 필드(`status=="degraded"`인 stage 목록). `steps`는 **항상 5개 전 단계**를 담는다 (`finalize_steps`). 응답에는 `unknown_tool_ids`(카탈로그에 없거나 비활성이라 반영되지 않은 tool_id 에코백 — Plan FR-03, v0.2 추가)도 포함된다.

### 4.4 SSE 이벤트 (stream 엔드포인트)

wire 포맷은 기존 `AgentRunEventSseFormatter` 라인 규칙(event/id/data + blank)을 따른다. 이벤트 타입:

| event | data | 시점 |
|-------|------|------|
| `stage_started` | `{"stage": "intent"}` | 각 단계 시작 |
| `stage_completed` | StageRecord JSON | 단계 정상/degraded 종료 |
| `stage_failed` | StageRecord JSON (`status:"failed"`) | 전파성 실패 (저장 실패 등) — 직후 `pipeline_result`로 종료 |
| `pipeline_result` | §4.3의 응답 전문 (need_input 또는 created). 실패 종료 시 `{"status":"failed", "error": {...}, "steps": [...]}` | 스트림 마지막 이벤트 (항상 1회) |

`id:`는 0부터 증가하는 seq. heartbeat는 SSE 주석 라인(`: heartbeat`)으로, 단계 대기가 15초(run/stream 관례와 동일 주기)를 넘길 때마다 송출한다 — LLM 순차 대기 중 프록시 idle 절단 방지(R2·R7). 구현 주의: `wait_for`로 `__anext__`를 취소하면 파이프라인 제너레이터가 중단되므로 task 유지 + `asyncio.wait(timeout)`을 쓴다 (v0.2). **FR-15 보장 구조**: 동기 핸들러는 같은 제너레이터를 소진해 `pipeline_result`와 동일한 객체를 JSON으로 반환한다 — 두 라우트의 결과 의미 동일성이 코드 구조로 강제된다.

### 4.5 Error Responses (동기 POST)

| Status | 조건 |
|--------|------|
| 401 | 인증 실패 |
| 404 | `session_id`가 없거나 타인 소유 (prompt_composer 계약) |
| 422 | 입력 검증 실패 (§4.2), CreateAgent 검증 실패(모델 없음 등 ValueError 계열) |
| 500 | 프롬프트 버전 저장 실패 · 에이전트 저장 실패 (FR-08 — 200으로 위장 금지) |

SSE에서는 위 4xx는 스트림 시작 전 일반 HTTP 에러로, 시작 후 실패는 `stage_failed`+`pipeline_result(status=failed)`로 표현한다.

---

## 5. 화면 계약 (UI는 스코프 밖 — 후속 사이클용 참고)

프론트가 구현할 때 기대하는 렌더 계약만 남긴다 (Plan D8의 존재 이유):

- 단계 진행 바: `steps`/SSE 이벤트의 stage 순서는 항상 `intent → tools → prompt → create → bind` 고정 5개
- 상태 매핑: `ok` ✅ / `degraded` ⚠️(reason 툴팁) / `failed` ❌(reason) / `skipped` ─
- `need_input`이면 `questions`를 폼으로 렌더 → `answers`+`round`+`questions` 에코백 재호출
- SSE 끊김 시 재호출 안내 문구 필요 — **재호출은 에이전트를 중복 생성할 수 있다** (§6.3)

---

## 6. Error Handling

### 6.1 단계별 실패 매트릭스 (FR-07/08 구체화)

| 단계 | 실패 유형 | 처리 | StageRecord |
|------|-----------|------|-------------|
| intent | LLM 실패/스키마 위반 (`degraded=true`) | 되묻기 불능 → **의도 없이 진행** (compose의 `_usable_intent`가 degraded intent를 알아서 배제) | `degraded`, reason |
| tools | 셀렉터 fallback (`fallback=true`) | `final_ids` = 사용자 `tool_ids`만 (required 보존은 포트 계약). 빈 목록이면 도구 없는 에이전트로 진행 | `degraded`, reason=selection.reason |
| prompt | LLM 실패 → 규칙기반 폴백 (`prompt.degraded=true`) | 폴백 프롬프트로 진행 (prompt_composer FR-06 그대로) | `degraded`, reason=prompt.reason |
| prompt | **버전 저장 실패 (DB 예외)** | 전파 → 500. create/bind는 `skipped` | `failed` + 이후 `skipped` |
| create | 검증 실패 (ValueError 계열) | 전파 → 422 | `failed` + bind `skipped` |
| create | **저장 실패 (DB 예외)** | 전파 → 500 | `failed` + bind `skipped` |
| bind | 404/409/DB 예외 | **삼키고 진행** — 생성 성공을 뒤집지 않는다 (FR-06). warning 로그 (`exception=e` 관례) | `failed`, `bind_ok=false`, 응답은 `created` 유지 |

> bind만 예외 흡수가 허용되는 이유: bind는 부가 백필이고 이미 `agent_id`라는 "쓸 수 있는 결과"가 존재한다 — degraded 경계 기준과 일치. 단, 파이프라인 UseCase 본문에 try/except를 두는 유일한 지점이므로 주석으로 계약을 명시한다.

### 6.2 UseCase 내 try/except 정책

intent·tools·prompt LLM 실패는 **각 모듈 어댑터가 이미 흡수**한다(예외 안 던짐이 포트 계약) — 파이프라인에 방어 try/except를 두지 않는다 (기존 관례 P5). 예외가 오면 그것은 저장 실패이거나 계약 위반이며, 드러나야 한다.

### 6.3 중복 생성 (Plan R7)

멱등성 저장소는 두지 않는다(신규 테이블 0, stateless). 완화: ① create를 LLM 단계들 뒤(4번째)에 배치 — 끊김 확률이 높은 구간(LLM 대기)은 생성 전이다 ② `pipeline_result` 유실 후 재호출은 중복 생성 가능함을 API 문서·§5 화면 계약에 명시 ③ 클라이언트는 `GET /api/v1/agents/my`로 직전 생성 여부를 확인할 수 있다. 멱등 키 도입은 실사용 데이터 확인 후 후속 판단.

---

## 7. Security Considerations

- [x] 전 엔드포인트 `get_current_user` (SSE 포함 — POST이므로 헤더 인증, query-token 특례 불필요)
- [x] `session_id` 소유권: prompt_composer가 검사 (타인 세션 → 404, 존재 비노출)
- [x] 생성 에이전트 `user_id` = 인증 사용자 (요청 본문 user_id 무시)
- [x] `visibility`는 이번 사이클 `private` 고정 (파이프라인 요청에 노출하지 않음 — 공개 범위 승격은 기존 PATCH 경로로)
- [x] 입력 상한 검증 422 (§4.2) · 프롬프트 4000자 clamp
- [x] 로그에 요청 원문·프롬프트 본문 미기록 (prompt_composer PII 관례 승계)

---

## 8. Test Plan

> 이 프로젝트는 pytest + TestClient (Playwright 아님). 테스트 코드는 Do에서 구현과 1세트로 작성.

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| Unit (domain) | PipelinePolicy 7함수 · spec 검증 | pytest | Do |
| Unit (application) | UseCase 단계 전이·이벤트 순서 (협력자 전부 fake) | pytest + fake | Do |
| L1: API | 동기 POST + SSE 라우트 (DI override, LLM fake) | TestClient | Do |
| 회귀 | 기존 5개 경로 라우트 등록·계약 무변경 | TestClient 실요청 (위키 `ast-source-contract-tests` — `app.routes` 순회 금지) | Do |

### 8.2 L1: API Test Scenarios

| # | Endpoint | 시나리오 | 기대 |
|---|----------|----------|------|
| 1 | POST /pipeline | 슬롯 충족 요청 1차 호출 | 200 `status=created`, `agent_id` 존재, steps 5개 전부, ok |
| 2 | POST /pipeline | purpose 미충족 → 되묻기 | 200 `status=need_input`, questions ≥ 1, tools 이하 `skipped` |
| 3 | POST /pipeline | #2 이어 answers+round 재호출 | 200 `status=created` (왕복 완주) |
| 4 | POST /pipeline | intent LLM 실패 주입 | 200 created, steps.intent=`degraded`, 되묻기 없음 |
| 5 | POST /pipeline | 셀렉터 fallback 주입 + tool_ids 지정 | 200 created, final=지정 도구만, steps.tools=`degraded` |
| 6 | POST /pipeline | 프롬프트 LLM 실패 주입 | 200 created, steps.prompt=`degraded`, 폴백 프롬프트로 생성됨 |
| 7 | POST /pipeline | 버전 저장 실패 주입 | **500**, create/bind 미실행 |
| 8 | POST /pipeline | 에이전트 저장 실패 주입 | **500** |
| 9 | POST /pipeline | bind 409 주입 | 200 created, `bind_ok=false`, steps.bind=`failed` |
| 10 | POST /pipeline | 무인증 | 401 |
| 11 | POST /pipeline | user_request 1001자 / tool_ids 51개 / round=-1 | 422 |
| 12 | POST /pipeline/stream | 정상 완주 | 이벤트 순서 = started/completed ×5 + `pipeline_result` 1회, seq 단조 증가 |
| 13 | POST /pipeline/stream | 저장 실패 주입 | `stage_failed` 후 `pipeline_result(status=failed)`로 종료 |
| 14 | 기존 경로 5종 | 등록·계약 회귀 | 변경 없음 (FAILED 목록 diff 기준) |
| 15 | POST /pipeline | 생성 후 GET /api/v1/agents/{id} | 프롬프트·도구 일치 (DoD) |

### 8.3 Unit 핵심 케이스 (domain)

- `decide_after_intent`: complete / incomplete+questions / **degraded+incomplete → proceed** / incomplete+questions 없음 → proceed
- `finalize_steps`: 중단 지점별 skipped 채움, 항상 길이 5, 순서 고정
- `clamp_prompt`: 4000 경계 (3999/4000/4001), 절단 시 reason 기록
- `resolve_agent_name`: 명시 > purpose 슬롯 > user_request 절단, 200자 clamp
- `clamp_round`: 음수/상한 초과 재clamp
- fake 협력자 UseCase 테스트: 이벤트 kind 순서, 예외 전파 시 이후 단계 미호출, bind 예외만 흡수

### 8.4 Seed Data

없음 — 전부 fake/override. 회귀 테스트만 기존 픽스처 재사용.

---

## 9. Clean Architecture

### 9.1 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `PipelineStage`/`StageStatus`/`StageRecord` | domain | `src/domain/agent_create_pipeline/stages.py` |
| `PipelinePolicy` | domain | `src/domain/agent_create_pipeline/policies.py` |
| intent 스펙 상수 | domain | `src/domain/agent_create_pipeline/spec.py` |
| `ToolCandidateReaderPort` | domain | `src/domain/agent_create_pipeline/interfaces.py` |
| `AgentCreatePipelineUseCase` + `StageEvent`/`PipelineOutcome` | application | `src/application/agent_create_pipeline/` |
| tool_catalog → `ToolCandidate` 어댑터 | infrastructure | `src/infrastructure/agent_create_pipeline/catalog_candidate_reader.py` |
| config (활성화·셀렉터 파라미터·타임아웃) | infrastructure | `src/infrastructure/config/agent_create_pipeline_config.py` |
| 라우터 + 요청/응답 스키마 | interfaces/api | `src/api/routes/agent_pipeline_router.py`, `src/interfaces/schemas/agent_pipeline.py` |
| DI 조립 | — | `src/api/main.py` (조립 실패 시 라우터 미등록 낙하, 기존 관례) |

### 9.2 Dependency Rules 준수 확인

- domain은 domain만 참조 (`intent.schemas`, `tool_selection.schemas` — 동일 레이어 참조 허용)
- application → application 조합은 Plan §7.2 기확정 (main.py 단일 조립)
- SSE wire 직렬화는 라우터에서 경량 처리(이벤트→dict→포맷 라인) — 비즈니스 로직 아님

### 9.3 Config (하드코딩 금지)

| 설정 | 기본값 | 용도 |
|------|--------|------|
| `agent_pipeline_enabled` | False | 라우터 등록 여부 (탈착형 관례) |
| `agent_pipeline_selector_top_k` | 8 | 빌더 문맥 셀렉터 top_k (General Chat 설정과 독립) |
| `agent_pipeline_selector_timeout_sec` | 5.0 | 추천 타임아웃 — 대화 필터(3.0)보다 여유: 후보가 카탈로그 전체라 프롬프트가 길고, 생성 1회 대기라 지연 민감도가 낮다 (v0.2 근거 명시) |
| ~~SlotLimits 계열~~ | — | **없음** (v0.2, Analysis G-02/G-03) — 되묻기 상한의 단일 출처는 intent의 `INTENT_MAX_*` config. main.py가 `IntentConfig.slot_limits()`를 파이프라인에 주입해 어댑터 프롬프트의 "남은 라운드"와 서버 재clamp가 같은 값을 본다 |

---

## 10. Coding Convention Reference

| Item | Convention |
|------|-----------|
| 파일/모듈 | snake_case, 기능 디렉터리 `agent_create_pipeline` 4계층 대칭 |
| 로깅 | LoggerInterface 주입, `exception=e`, 요청 원문 미기록 |
| 에러 | bind 외 try/except 금지 (§6.2), 스택 트레이스 보존 |
| DI | main.py 단일 조립, 라우터 placeholder `NotImplementedError` override 패턴 |
| 함수 40줄·if 중첩 2단계 준수 — UseCase run은 단계별 private 메서드 분리 |

---

## 11. Implementation Guide

### 11.1 File Structure

```
src/domain/agent_create_pipeline/
├── __init__.py
├── stages.py            # PipelineStage, StageStatus, StageRecord
├── policies.py          # PipelinePolicy (순수 함수 7종)
├── spec.py              # AGENT_CREATE_INTENT_SPEC (+ SlotLimits 기본)
└── interfaces.py        # ToolCandidateReaderPort
src/application/agent_create_pipeline/
├── __init__.py
├── events.py            # StageEvent, PipelineOutcome
└── use_case.py          # AgentCreatePipelineUseCase (async generator run)
src/infrastructure/agent_create_pipeline/
├── __init__.py
└── adapters.py          # CatalogCandidateReader + NullToolSelector (v0.2 — 파일명 갱신)
src/infrastructure/config/agent_create_pipeline_config.py
src/interfaces/schemas/agent_pipeline.py
src/api/routes/agent_pipeline_router.py
tests/domain/agent_create_pipeline/  (+ application/api 대칭)
```

### 11.2 Implementation Order

1. [ ] domain: stages → policies → spec → interfaces (+ 테스트 선행)
2. [ ] application: events → use_case (fake 협력자 테스트 선행)
3. [ ] infrastructure: candidate reader + config
4. [ ] interfaces: 스키마 → 라우터 (동기 → SSE)
5. [ ] main.py DI 조립 + 등록 순서(와일드카드보다 앞) + 회귀 테스트
6. [ ] 통합 시나리오 (§8.2 #1~#15)

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| domain 계층 (stages/policies/spec/port) | `module-1` | 순수 규칙 + 테스트 | 20-25 |
| application UseCase + events | `module-2` | 조합 흐름 + fake 테스트 | 25-30 |
| infrastructure + interfaces + DI | `module-3` | 어댑터·config·라우터 2종·main.py·회귀 | 30-40 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Do | `--scope module-1,module-2` | 45-55 |
| Session 2 | Do | `--scope module-3` | 30-40 |
| Session 3 | Check + Report | 전체 | 30-40 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-18 | Option C 확정 (Checkpoint 3) — 단계 상태 모델·SSE 계약·실패 매트릭스·스펙 상수 상세화 | 배상규 |
| 0.2 | 2026-08-19 | Act-1 반영 (코드가 진실) — heartbeat 주기·구현 주의, unknown_tool_ids 응답 추가, SlotLimits 단일 출처화(§9.3), adapters.py 파일명·NullToolSelector(§2.3), timeout 5.0 근거 | 배상규 |
