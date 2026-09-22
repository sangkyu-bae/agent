# 자연어 에이전트 생성 — 진입점부터 실행 그래프까지

> 작성일: 2026-09-20
> 대상: `/agent-builder/new` 채팅 위저드 + 인접 생성 경로 + 생성된 에이전트의 런타임 LangGraph
> 모든 내용은 코드 정적 추적으로 검증했다. 파일:라인은 작성 시점 기준.

---

## 0. 결론 3줄

1. **`/agent-builder/new` 채팅이 보내는 곳은 `POST /api/v1/agents/pipeline/stream` (SSE) 하나다.**
   `/compose`가 아니다 — `/compose`는 스튜디오의 "Fix 에이전트" 패널 전용이다.
2. **생성(빌드) 과정에는 LangGraph가 없다.** 5단계 async generator + 순수 도메인 Policy다.
   LangGraph `StateGraph`는 *만들어진 에이전트를 실행할 때* `WorkflowCompiler`가 동적 컴파일한다.
3. **위저드는 아무것도 저장하지 않는다.** 프롬프트까지만 만들고 스튜디오로 넘기며,
   실제 저장은 사용자가 스튜디오에서 누르는 `POST /api/v1/agents`가 한다.

---

## 1. 자연어 → 에이전트 경로는 3개다

| | **A. 생성 위저드** | **B. Fix 에이전트** | **C. Auto Builder** |
|---|---|---|---|
| 화면 | `/agent-builder/new` | `/agent-builder` 우측 탭 | (없음) |
| 엔드포인트 | `POST /api/v1/agents/pipeline/stream` | `POST /api/v1/agents/compose` | `POST /api/v3/agents/auto` |
| 전송 방식 | **SSE** (fetch + ReadableStream) | 단일 axios POST | 단일 POST |
| 라우터 | `src/api/routes/agent_pipeline_router.py:98` | `src/api/routes/agent_composer_router.py:29` | `src/api/routes/auto_agent_builder_router.py:36` |
| 되물음 상태값 | `need_input` | `needs_clarification` | `needs_clarification` |
| 라운드 필드 | `round` (서버가 부여) | `clarification_round` (프론트가 +1) | 세션 `attempt_count` |
| 저장 | 안 함 (`stop_after='prompt'`) | 안 함 (초안만) | **즉시 생성** |
| 대상 테이블 | — → 이후 `agent_definition` | — → 이후 `agent_definition` | `middleware_agent` |
| 프론트 연동 | ✅ | ✅ | ❌ **호출 코드 0건** |
| 킬스위치 | `AGENT_PIPELINE_ENABLED` (기본 `False`) | 없음 | 없음 |

> C 경로는 `CLAUDE.md`의 API 표(AGENT-006)와 `docs/archive/2026-08/progress-card/progress-card.plan.md:59`
> ("현재 프론트 미연동")에만 등장한다. 백엔드에는 살아 있으나 UI에서 도달할 수 없다.

---

## 2. A 경로 — `/agent-builder/new` 채팅 위저드 (주 경로)

### 2-1. 프론트 호출 체인

```
사용자가 채팅창에 입력 + Enter
  DescriptionComposer.tsx:41,72         onSubmit (Enter 전송 / Shift+Enter 줄바꿈 :38-43)
→ AgentCreateEntryPage/index.tsx:217    handleSubmitDescription()
→ index.tsx:211                         sendDescription()   // chat 모드 전환
→ index.tsx:203                         dispatch(body, next)
→ hooks/useAgentPipelineStream.ts:95    send(body)
→ services/agentPipelineService.ts:63   stream(body, handlers, signal)
→ utils/streamParser.ts:98              createEventFetchStream → fetch()
⇒ POST {VITE_API_BASE_URL}/api/v1/agents/pipeline/stream
```

- 라우트 매핑: `idt_front/src/App.tsx:67` → `AgentCreateEntryPage`
- 엔드포인트 상수: `idt_front/src/constants/api.ts:231` `AGENT_PIPELINE_STREAM`
- 헤더: `agentPipelineService.ts:30-38` (`Authorization: Bearer`, `X-User-Id`) +
  `streamParser.ts:106` (`Accept: text/event-stream`)

**EventSource를 안 쓰는 이유** (`streamParser.ts:91-92`, `agentPipelineService.ts:6-9` 주석):
입력이 body라 query로 못 보내고, EventSource는 커스텀 헤더를 못 붙인다.
→ `fetch` + `ReadableStream` 수동 파싱.

> ⚠️ 이 경로는 axios 인터셉터를 타지 않는다 (`agentPipelineService.ts:11-12`).
> **401 자동 토큰 갱신이 없다.**

### 2-2. 백엔드 진입점

`src/api/routes/agent_pipeline_router.py`

| 라인 | 내용 |
|---|---|
| `:50` | `APIRouter(prefix="/api/v1/agents/pipeline")` |
| `:63` | `POST ""` — 동기 변형. generator를 소진해 마지막 `PipelineOutcome`만 반환 |
| `:98` | `POST "/stream"` — **위저드가 쓰는 SSE 변형** |
| `:118` | `_sse_stream()` — generator → SSE wire 변환 |
| `:278` | `_sse()` — `event:`/`data:`/`id:` 직렬화 |

**등록 자체가 조건부다.** `src/api/main.py:5228`
```python
if _pipeline_cfg.AGENT_PIPELINE_ENABLED and _prompt_f is not None:
    app.include_router(agent_pipeline_router)
else:
    logger.info("Agent pipeline disabled — router not registered", ...)
```
기본값은 `False` (`src/infrastructure/config/agent_create_pipeline_config.py:19`).
현재 `.env:92`에 `AGENT_PIPELINE_ENABLED=true`로 켜져 있다.
off면 라우터 미등록 → **404** → 프론트가 `PipelineUnavailableCard`로 화면 전체를 대체한다
(`useAgentPipelineStream.ts:40`, `index.tsx:357-366`).

**heartbeat** (`agent_pipeline_router.py:118-135`):
15초마다 `: heartbeat\n\n` 주석 라인. LLM 대기 중 프록시 idle 절단 방지.
`asyncio.wait_for`를 안 쓴 이유가 주석에 있다 — timeout 시 `__anext__`를 취소하면
`CancelledError`가 파이프라인 generator 내부 LLM await 지점으로 주입되어
**실행 자체가 죽는다.** task를 살려둔 채 `asyncio.wait(timeout)`으로 기다려야 한다.

### 2-3. 백엔드 5단계 파이프라인

`src/application/agent_create_pipeline/use_case.py:102` `AgentCreatePipelineUseCase.run()`
— `StageEvent`를 yield하다가 `PipelineOutcome`으로 끝나는 **async generator**다.

```
run()
 │
 ├─ _stage(INTENT, _run_intent)                          use_case.py:196
 │    · intent_echo 있으면 PipelinePolicy.reuse_intent() → LLM 재호출 안 함 (D2)
 │      (재판정하면 사용자가 도구를 고른 근거였던 의도와 달라진다)
 │    · 없으면 IntentUseCase.execute(message, spec, history, answers, round_)
 │    · result.degraded → StageStatus.DEGRADED, "의도 없이 진행"
 │
 ├─ PipelinePolicy.decide_after_intent(intent, round_, max_rounds)   policies.py:57
 │    ├ degraded            → proceed   (판정 실패는 되묻기 불능)
 │    ├ questions 없음      → proceed   (물을 게 없는 왕복 = 무한 루프)
 │    ├ round 0 이고 complete → proceed (상세히 쓴 요청을 심문하지 않음, SC-4)
 │    └ 그 외               → ask  ⇒ yield _need_input_outcome() 후 return
 │                                     status="need_input" + questions[]
 │
 └─ for stage in PipelinePolicy.stages_to_run(stop):      policies.py:91
        stages_to_run(None)     → (TOOLS, PROMPT, CREATE, BIND)
        stages_to_run('tools')  → (TOOLS,)
        stages_to_run('prompt') → (TOOLS, PROMPT)

      ├─ TOOLS   _run_tools()                             use_case.py:224
      │    · tools_confirmed=True → PipelinePolicy.confirmed_selection()
      │      **셀렉터를 다시 돌리지 않는다** — required_ids로 넘기면
      │      final = 추천 ∪ 확정 이 되어 사용자가 지운 도구가 되살아난다 (D1)
      │    · 아니면 CatalogCandidateReader.list_active() → ToolSelector.select()
      │    · 후보 0건이면 LLM 호출 없이 empty_candidate_selection()으로 강하
      │    · selection.fallback → DEGRADED
      │
      ├─ PROMPT  _run_prompt()                            use_case.py:254
      │    · PromptComposeUseCase.compose(user_request, intent, tool_ids, session_id)
      │    · degraded → 규칙기반 폴백 프롬프트
      │
      ├─ CREATE  _run_create()                            use_case.py:279
      │    · PipelinePolicy.clamp_prompt()  상한 8000자
      │    · CreateAgentRequest(visibility="private" 고정) → CreateAgentUseCase.execute()
      │
      └─ BIND    _run_bind()                              use_case.py:298
           · PromptComposeUseCase.bind_agent(session_id, user_id, agent_id)
           · **유일한 예외 흡수 지점** — 실패해도 생성 성공을 뒤집지 않고
             StageStatus.FAILED만 기록

      각 stage 직후 decide_after_stage(stage, stop) == "stop" 이면
        ⇒ yield _stopped_outcome()  → status = tools_proposed | prompt_ready
      전부 돌면
        ⇒ yield _created_outcome()  → status = "created", agent_id 존재
```

**`_stage()` 공통 실행기** (`use_case.py:178`):
`stage_started` 이벤트 → 실행 → `elapsed_ms` 채워 `stage_completed`.
예외는 흡수하지 않고 전파하는 것이 계약(§6.2)이며,
라우터의 `_sse_stream`이 마지막 `stage_started` 기록으로 "어디서 죽었는지"를 복원해
`stage_failed` + `pipeline_result(status=failed)`를 합성한다.

### 2-4. 단계·상태 VO (wire 계약)

`src/domain/agent_create_pipeline/stages.py` — **Enum `.value`가 그대로 wire에 실린다. 변경 = 프론트 계약 파괴.**

| 타입 | 값 | 라인 |
|---|---|---|
| `PipelineStage` | `intent` `tools` `prompt` `create` `bind` | `:11` |
| `PipelineStop` | `tools` `prompt` — create/bind는 정지 지점이 될 수 없다 | `:30` |
| `StageStatus` | `ok` `degraded` `failed` `skipped` | `:47` |
| `StageRecord` | `stage` / `status` / `reason` / `elapsed_ms` | `:54` |

`PipelineStop`의 값이 `PipelineStage`와 **의도적으로 같은 문자열**이다 (`:35-37`) —
"어느 단계 직후에 멈출 것인가"라는 의미라 별도 이름 체계를 두면 매핑 표가 하나 더 생긴다.

### 2-5. 화면 단계별 왕복 (전부 같은 URL)

`AgentCreateEntryPage/index.tsx`

| 사용자 행동 | 핸들러 | 요청 추가 필드 | 응답 status |
|---|---|---|---|
| 첫 입력 | `:217` `handleSubmitDescription` | `user_request` | `need_input` 또는 `tools_proposed` |
| 질문 답변 | `:232` `handleAnswers` | `answers`(누적), `round`, `stop_after:'tools'` | 〃 |
| 질문 건너뛰기 | `:262` `handleSkipQuestions` = `handleAnswers([])` | | 〃 |
| 도구 확정 | `:273` `handleConfirmTools` | `tools_confirmed:true`, `intent`, `stop_after:'prompt'` | `prompt_ready` |
| 프롬프트 재생성 | `:291` `handleRegeneratePrompt` | 위 + `session_id` | `prompt_ready` |
| 스튜디오로 보내기 | `:309` `handleSendToStudio` | **HTTP 호출 없음** | — |

> 위저드는 `stop_after`를 항상 `'tools'` 또는 `'prompt'`로 보낸다.
> 따라서 **CREATE/BIND 단계는 위저드 흐름에서 실행되지 않는다.**
> 파이프라인 자체는 `stop_after` 없이 호출하면 `status="created"`까지 갈 수 있지만, UI가 그렇게 쓰지 않는다.

### 2-6. 되물음 UI

- 라운드는 **push 누적**: `index.tsx:131-150` `applyResult()`에서
  `rounds: [...sent.rounds, {round, questions, answered:false}]` — 교체가 아니다.
  지난 질문 카드가 잠긴 채 트랜스크립트에 남는다.
- **라운드 번호는 서버 응답값을 그대로 받는다** (`round: result.round`). 프론트가 +1 하지 않는다.
  ↔ B 경로(Fix)는 반대로 프론트가 `(clarify?.round ?? 0) + 1`로 직접 올린다 (`FixAgentPanel.tsx:110-126`).
- 답변은 `slot_key` 기준 dedupe 후 **전량 에코백** (`index.tsx:235-240`) — 서버가 무상태이기 때문.
- 빈 답변(`value.trim() === ''`)은 전송에서 제외 (`IntentStep.tsx:27-30`) — 서버 `min_length=1` 422 회피.
- 되묻기 상한의 단일 출처는 **intent 모듈의 `IntentConfig.slot_limits()`** 다.
  `AgentPipelineConfig`에 두지 않은 이유가 `agent_create_pipeline_config.py:6-10`에 있다 —
  파이프라인이 별도 값을 가지면 어댑터 프롬프트의 "남은 라운드" 안내와 서버 재clamp가 어긋난다.
  `main.py:5232`가 `IntentConfig().slot_limits()`를 파이프라인에 주입한다.
- 프론트 표시용 상수는 `types/agentPipeline.ts:204` `MAX_CLARIFY_ROUNDS = 3`.

### 2-7. 위저드 → 스튜디오 인계 (무저장)

```
PromptStep.tsx:137 "스튜디오로 보내기"
→ index.tsx:124 goStudio({kind:'wizard', result:{systemPrompt, promptEdited,
                                                 toolIds, suggestedName, sessionId, versionId}})
→ store/agentDraftStore.ts:47 setPendingIntent()   // persist 미들웨어 의도적 미사용
→ navigate('/agent-builder')
→ AgentBuilderPage/index.tsx:184-207 useEffect
→ agentDraftStore.ts:51 consumePendingIntent()      // 읽기+비우기 원자적 1회
→ index.tsx:116 prefillFromIntent() → :124 wizardResultToForm()
→ utils/wizardResultToForm.ts:22-31  name / systemPrompt / 도구만 채움
                                     (모델·온도는 건드리지 않음)
```

- 위저드 상태는 **영속되지 않는다** (`agentDraftStore.ts:41-43`). 새로고침 시 유실은 정의된 동작.
- 이탈 경고: `index.tsx:117-122` `beforeunload` (chat 모드에서만).
- 진입 시 `clearPendingIntent()` (`index.tsx:111-113`) — 유령 초안 방지.

---

## 3. B 경로 — Fix 에이전트 (`/compose`)

스튜디오에서 **이미 만든 에이전트를 자연어로 고칠 때** 쓴다.

```
POST /api/v1/agents/compose
→ agent_composer_router.py:29 compose_agent()        // request_id 발급 + ValueError→422 만
→ ComposeAgentUseCase.execute()                      compose_agent_use_case.py:52
   ① _resolve_llm_model_id()
   ② _collect_candidates()                    :183   내부 도구 get_all_tools()
                                                     + ToolCatalogRepository.list_active() 중 source=="mcp"
      └ MCP 항목 0건이면 _fallback_server_candidates() :211
        → MCPServerRepository.find_all_active()로 "서버 단위" 폴백 + warning (D2)
   ③ ComposePolicy.clamp_history()                   최근 6턴 / 턴당 500자
   ④ PlannerPolicy.clamp_round()                     0..2로 clamp (클라 신고값 불신)
   ⑤ _try_plan()                              :105   ← LLM #1
      AgentPlanner.plan()   planner.py:102, with_structured_output(_PlanOutput)
      실패 시 warning 후 None 폴백 → 단발 compose로 계속 (FR-08)
   ⑥ _maybe_clarification()                   :140
      PlannerPolicy.should_ask(confidence, question_count, round)   policies.py:81
        질문>0 AND confidence < 0.8 AND round < 2
        → status="needs_clarification", questions 최대 3개
   ⑦ AgentComposer.compose()                  composer.py:143  ← LLM #2
      출력 _ComposeOutput: capabilities / workers / flow_hint / system_prompt / agent_name / notes
   ⑧ _assemble_draft()                        :238   ★ 서버 보정
   ⑨ _to_response()                           :365   status="draft"
```

### ⑧ 서버 보정이 이 설계의 핵심

`src/domain/agent_composer/policies.py` — *"LLM 출력을 신뢰하지 않고 서버가 최종 결정한다"* (D7)

| 함수 | 라인 | 역할 |
|---|---|---|
| `drop_unknown_tools()` | `:30` | 후보에 없는 `tool_id` 워커 제거 (환각 방어) |
| `clamp_tool_count()` | `:39` | `sort_order` 순 상위 N개 (상한은 `AgentBuilderPolicy` 단일 출처) |
| `clamp_system_prompt()` | `:49` | 길이 초과 절단 + notes에 사유 |
| `derive_coverage()` | `:56` | **LLM이 뭐라 하든 서버 재산정**: 워커 0 → `none` / 미커버 역량 → `partial` / 그 외 `full` |

보정이 일어나면 `flow_hint`도 실제 워커 순서로 덮어쓴다 (`compose_agent_use_case.py:274`).

- 프론트 history 누적: `FixAgentPanel.tsx:73-80` `buildHistory()` — 초안 턴은
  `summarizeDraft()`로 텍스트 요약(카드 JSON 미전송), 최근 6턴만(`MAX_HISTORY_TURNS=6`).

---

## 4. C 경로 — Auto Builder (`/api/v3/agents/auto`, 프론트 미연동)

```
POST /api/v3/agents/auto  → AutoBuildUseCase.execute()        auto_build_use_case.py:28
  → AgentSpecInferenceService.infer()   agent_spec_inference_service.py:63  (LLM, JSON)
  → AutoAgentBuilderPolicy.validate_tool_ids()
  → is_confident_enough():  confidence >= 0.8 AND 질문 없음
      ├ True  → CreateMiddlewareAgentUseCase  ⇒ middleware_agent / _tool / middleware_config
      └ False → AutoBuildSessionRepository.save(status="pending")  ⇒ Redis, TTL 86400s

POST /api/v3/agents/auto/{session_id}/reply → AutoBuildReplyUseCase   auto_build_reply_use_case.py:25
  → should_force_create(): attempt_count >= 3 이면 질문을 강제 제거하고 생성
                           (무한 되물음 방지)
```

A·B와 **저장 테이블이 다르다** (`middleware_agent` vs `agent_definition`).
같은 "에이전트"라는 말을 쓰지만 별개 모델이다.

---

## 5. 공통 종착지 — `POST /api/v1/agents` (실제 저장)

```
AgentBuilderPage/index.tsx:613 onSave → :245 handleSave() → :331 createMutation
→ hooks/useAgentBuilder.ts:41 → services/agentBuilderService.ts:21
→ constants/api.ts:220 AGENT_BUILDER_CREATE = '/api/v1/agents'   (axios authApiClient)

⇒ agent_builder_router.py:168 create_agent()
→ CreateAgentUseCase.execute()                      create_agent_use_case.py:108
   Step 0    :118  LLM 모델 ID 결정
   Step 1    :123  WorkerSkeletonBuilder — 도구 선택 + 플로우
   Step 1.5  :138  SubAgentWorkerBuilder
   Step 1.75 :154  확정 템플릿 검증 (document-template-extractor)
   Step 1.8  :167  문서 유형 검증 + tool_config 주입 (doc-generator)
   Step 1.9  :178  발표자료 워커 tool_config (golden-sample-blueprint)
   Step 2    :184  AgentBuilderPolicy 검증
   Step 2.5  :191  컬렉션/KB scope 기반 visibility 자동 조정
   Step 2.7  :201  빌트인 도구 주입
   Step 2.8  :210  빌트인 미들웨어 스냅샷
   Step 3    :216  system_prompt 필수 검증 (agent-instruction-required)
   Step 4    :221  ★ AgentDefinitionRepository.save()  ⇒ agent_definition / agent_tool
   Step 4.5  :243  부착 스킬 동기화
   Step 4.6  :251  원본 승격
   Step 4.7  :260  document_generation_type 저장
```

> `create_agent_use_case.py:125` 주석 — `agent-instruction-required` 변경 이후
> **이 엔드포인트의 LLM 자동 도구선택은 제거**되었다.
> 도구 선택·프롬프트 생성은 전적으로 파이프라인(A) 또는 Composer(B)가 담당하고,
> `POST /agents`는 명시된 `tool_ids` / `system_prompt`만 받는다.

**저장 성공 후 부수 호출** (`AgentBuilderPage/index.tsx:395-401`, 실패해도 저장은 유지):
1. `promptEdited === true`일 때만 → `POST /api/v1/prompt-composer/sessions/{sessionId}/versions`
2. 항상 → `PATCH /api/v1/prompt-composer/sessions/{sessionId}` body `{agent_id}`
3. `wizardRef.current = null` — 1회성, 재저장 시 409 방지

---

## 6. 런타임 — 생성된 에이전트의 LangGraph 그래프

### 6-1. 실행 진입점

| 방식 | 경로 | 파일:라인 |
|---|---|---|
| 동기 | `POST /api/v1/agents/{agent_id}/run` | `agent_builder_router.py:270` |
| SSE | `GET /api/v1/agents/{agent_id}/run/stream` | `agent_builder_router.py:299` (heartbeat 15초) |
| WS | `/ws/agent/{run_id}` | `ws_router.py:193` |

```
RunAgentUseCase.execute()                  run_agent_use_case.py:367
→ agent.to_workflow_definition()
→ _inject_attached_skills()
→ SupervisorConfig(max_iterations=agent.max_iterations)
→ WorkflowCompiler.compile(depth=0, visited={agent.id}, ...)   run_agent_use_case.py:585
```

`SupervisorConfig` 기본값 (`src/domain/agent_builder/schemas.py:13`):
`max_iterations = IterationLimitPolicy.DEFAULT = 25` / `token_limit = 8000` /
`quality_gate_enabled = False` / `max_retries_per_worker = 2`

### 6-2. 그래프 조립

`src/application/agent_builder/workflow_compiler.py:823` `graph = StateGraph(SupervisorState)`

**노드 (등록 조건이 전부 다르다)**

| 노드 | 라인 | 등록 조건 |
|---|---|---|
| `supervisor` | `:824` | 항상 |
| `quality_gate` | `:831` | `if worker_map` — 워커 0개(순수 대화형)면 진입 간선이 없어 고아 노드가 된다 |
| `<worker_id>` ×N | `:860` | `worker_map` 순회 |
| `final_answer` | `:878` | `if depth == 0` — sub_agent는 원시 결과를 부모에 그대로 반환(토큰 이중 정제 방지) |
| `chart_router` | `:891` | `if analysis_worker_ids` |
| `chart_builder` | `:898` | `if analysis_worker_ids and chart_max_count > 0` |

entry point: `graph.set_entry_point("supervisor")` (`:905`)

**워커 컴파일 분기** (`:481~:720`) — `worker_map`에 들어가는 노드는 6종류다:

| 조건 | 결과 |
|---|---|
| `worker_type == "sub_agent"` | `_compile_sub_agent()` → 재귀 컴파일 후 `_wrap_sub_agent()` |
| `tool_id == "document_extractor"` | `_create_document_extractor_node()` (ToolFactory 미경유) |
| `tool_id == "document_generator"` | `_create_document_generator_node()` |
| `tool_id == "presentation_generator"` | `_create_presentation_generator_node()` |
| `tool_id == "excel_export"` | `_create_excel_generator_node()` |
| `category == "analysis"` | `_create_analysis_node()` → `analysis_worker_ids`에 추가 |
| `category in ("search","collect")` | 단일샷 노드 (react 루프 없음 — 산출이 도구 원본이라 하류가 근거로 쓴다) |
| 그 외 | react agent + 도구 호출 예산(`tool_call_limit`) |

**엣지**

```
supervisor ─conditional─▶  (depth 0) route_to_worker_or_final   workflow_compiler.py:911
                           route_map = {wid:wid} ∪ {"__end__":END,
                                                    "final_answer":"final_answer",
                                                    "supervisor":"supervisor"}
           ─conditional─▶  (depth>0) route_to_worker            :915
                           route_map = {wid:wid} ∪ {"__end__":END}

worker_i ──▶ chart_router      (analysis 워커일 때만)            :920
         ──▶ quality_gate      (그 외)                           :922

chart_router ─conditional─▶ route_after_chart_router             :927
               {"visualize": "chart_builder", "text": "quality_gate"}
             ──▶ quality_gate  (chart_max_count == 0인 하위호환)  :935

chart_builder ──▶ quality_gate                                   :932
final_answer  ──▶ END          (depth 0)                         :939

quality_gate ─conditional─▶ route_after_quality                  :946
               qg_route_map = {"supervisor":"supervisor"} ∪ {wid:wid}
```

### 6-3. 조건부 분기 함수 (정확한 조건)

`src/application/agent_builder/supervisor_nodes.py`

**`route_to_worker_or_final(state)` — `:520`, depth=0 전용. 우선순위 순서대로:**
1. `next_worker == "__end__"` **and** `finish_challenge_pending` **and not** `limit_reached`
   → `"supervisor"` — 빈 결과 미해소 상태의 첫 FINISH를 **1회만** 되돌린다.
   특정 워커를 강제하지 않고 재결정 기회만 준다. (`supervisor-early-finish-fix` D-05)
   한도 도달이 되물음보다 우선한다 (D-09) — 종료를 막지 않는다.
2. `next_worker == "__end__"` **and** (`last_worker_id` **or** `limit_reached`)
   → `"final_answer"` — 워커 실행 이력이 있으면 최종 답변 노드를 **구조적으로 강제 경유**.
   반복 한도 도달 시에도 우회해 "답변 없이 END 직행"을 차단한다 (`agent-recursion-limit` D6).
3. 그 외 → `next_worker`

**`route_to_worker(state)` — `:516`, depth>0**: `return state["next_worker"]` (그게 전부)

**`route_after_quality(state)` — `:547`**:
`next_worker`가 있고 `!= "__end__"` → `next_worker` (재시도), 아니면 `"supervisor"`

**`route_after_chart_router(state)` — `chart_router.py:70`**:
`viz_decision == "visualize"` → `"visualize"`, 아니면 `"text"`

### 6-4. `SupervisorState`

`src/application/agent_builder/supervisor_state.py:8` (TypedDict)

| 필드 | 라인 | 의미 |
|---|---|---|
| `messages` | `:9` | `Annotated[list, add_messages]` |
| `iteration_count` / `max_iterations` | `:11-12` | 반복 가드 |
| `token_usage` / `token_limit` | `:13-14` | 토큰 가드 |
| `next_worker` / `last_worker_id` / `available_workers` | `:16-18` | 라우팅 |
| `quality_gate_enabled` / `retry_counts` / `max_retries_per_worker` | `:20-22` | 게이트 |
| `forced_worker` / `skipped_workers` | `:24-25` | 강제·제외 |
| `worker_task` | `:30` | supervisor → 워커 작업 지시. 워커는 `supervisor_prompt`를 못 본다 |
| `limit_reached` | `:35` | 한도 도달 플래그 → `final_answer` 우회 신호 |
| `last_worker_error` | `:40` | 직전 도구 오류 요약. supervisor가 1회 렌더 후 `""`로 리셋 |
| `last_worker_empty` | `:46` | 직전 **빈 결과** 요약. 도구는 성공했으나 유효 데이터 없음 — 오류와 구분 |
| `finish_challenge_pending` | `:53` | FINISH 되물음 1회 기회. **카운터가 아니라 플래그** — 신호 리셋과 짝지어 1회 상한이 구조적으로 보장됨 |
| `quality_gate_result` | `:55` | `passed` / `failed` / `skipped` / `max_retries` |
| `attachments` | `:59` | 분석 노드 입력 (엑셀 경로 등) |
| `viz_decision` / `charts` / `visualization_done` | `:63-71` | 시각화 |
| `analysis_source` | `:76` | 엑셀 원천 데이터 전달 채널 |

### 6-5. 노드 내부 동작

**`supervisor` (`supervisor_nodes.py:268` `create_supervisor_node`)** — 가드 순서:
1. `iteration_count >= max_iterations` → `next_worker="__end__"`, `limit_reached=True`, pending 소진
2. `token_usage >= token_limit` → `__end__`
   ⚠️ 이 경로는 `limit_reached`를 세우지 않고(테스트로 고정) `iteration_count`도 안 올린다
3. `forced_worker` 있으면 LLM 없이 그 워커로
4. 아니면 LLM structured output `SupervisorDecision` (`:249`) — `next` / `reasoning` / `answer` / `task`
   - `_render_worker_error_block` / `_render_empty_result_block` 등으로 프롬프트 조립
   - `finish_challenge_pending = bool(empty_block)` (`:449`)

**`quality_gate` (`:455`)**:
- 비활성 → `skipped`
- `QualityGatePolicy.check_response()` (`domain/agent_builder/policies.py:196`)
  — 10자 미만이거나 `["모르겠습니다","답변할 수 없습니다","정보를 찾을 수 없"]`로 시작하면 실패
- 통과 → `passed` / 재시도 상한 도달 → `max_retries`(강제 통과)
- 실패 → 피드백 메시지 주입 + `next_worker = last_worker` 로 **같은 워커 재호출**

**`final_answer` (`workflow_compiler.py:1127`)**:
- 워커 산출물(`AIMessage(name=<worker_id>)`)은 system prompt 컨텍스트 블록과 중복이라 messages 본체에서 제외
- `tool` 역할 메시지도 제외 — 선행 `tool_calls` 짝이 깨지면 OpenAI가 400 반환 (`worker-toolmessage-leak-fix` D2)
- `state["charts"]`는 **읽기만** 하고 반환 dict에 넣지 않는다 (프론트 차트 페이로드 보존)

---

## 7. 주의사항 / 발견한 불일치

### 7-1. ⚠️ `docs/ex/workflow_compiler.md`가 코드와 어긋나 있다

해당 문서는 `answer_agent` **가상 워커**(`tool_id="__virtual__"`, `sort_order=9999`)가
supervisor 목록에 추가되고 LLM이 그것을 선택한다고 기술한다
(`workflow_compiler.md:28, 39, 86, 102, 135, 148, 155, 268-275`).

코드에서는 `workflow_compiler.py:726` 주석대로 **`final-answer-node` D2에서 그 방식이 제거**되었다.
현재는 `final_answer` 노드를 라우팅 함수 `route_to_worker_or_final`이 **구조적으로 강제 경유**시킨다 —
LLM의 선택이 아니다. 코드 전체에 `answer_agent` 식별자는 그 주석 한 줄 외에 존재하지 않는다.

> CLAUDE.md §6 SoT 규칙(코드가 진실)에 따라 **보고만 하고 수정하지 않았다.**

### 7-2. `route_after_chart_router` docstring도 낡았다

`src/application/visualization/chart_router.py:72-75`는
"현재 그래프 배선에서는 미사용"이라고 적혀 있으나,
`workflow_compiler.py:927`이 `add_conditional_edges`에 실제로 부착해 쓰고 있다.

### 7-3. 그 외

- A 경로 SSE는 **401 자동 갱신이 없다** (`agentPipelineService.ts:11-12`).
- `AGENT_PIPELINE_ENABLED` 기본값이 `False`다 — 새 환경에서 `.env` 설정을 빠뜨리면
  위저드가 통째로 `PipelineUnavailableCard`로 대체된다.
- `PROMPT_MAX_CHARS = 8000`은 4곳(파이프라인 Policy / 응답 스키마 `MAX_ASSEMBLED_CHARS` /
  Create 요청 스키마 / Update 요청 스키마)이 일치해야 한다.
  어긋나면 사용자는 **마지막 저장 단계에서** 422를 만난다 (`policies.py:36-41`, 테스트가 강제).
- B 경로의 `docs/ex` 문서는 없다 — 이 문서가 처음이다.

---

## 부록: 파일 색인

### 백엔드 (`idt/src/`)
```
api/routes/agent_pipeline_router.py        A 진입점 (SSE)
api/routes/agent_composer_router.py        B 진입점
api/routes/auto_agent_builder_router.py    C 진입점
api/routes/agent_builder_router.py         저장·실행 CRUD
api/main.py:5228                           A 라우터 조건부 등록

application/agent_create_pipeline/use_case.py    A 5단계 오케스트레이션
application/agent_composer/{planner,composer,compose_agent_use_case}.py   B
application/auto_agent_builder/{auto_build_use_case,auto_build_reply_use_case}.py  C
application/agent_builder/create_agent_use_case.py    공통 저장
application/agent_builder/workflow_compiler.py        런타임 그래프 컴파일
application/agent_builder/supervisor_nodes.py         supervisor / quality_gate / 라우팅
application/agent_builder/supervisor_state.py         SupervisorState
application/agent_builder/run_agent_use_case.py       실행
application/visualization/{chart_router,chart_builder_node}.py

domain/agent_create_pipeline/{stages,policies,spec,interfaces}.py
domain/agent_composer/policies.py          ComposePolicy / PlannerPolicy
domain/auto_agent_builder/{policies,schemas}.py
domain/agent_builder/{policies,schemas}.py QualityGatePolicy / IterationLimitPolicy / SupervisorConfig

infrastructure/config/agent_create_pipeline_config.py  킬스위치
infrastructure/agent_create_pipeline/adapters.py
```

### 프론트 (`idt_front/src/`)
```
App.tsx:67                                 /agent-builder/new 라우트
pages/AgentCreateEntryPage/index.tsx       A 위저드 본체
pages/AgentCreateEntryPage/components/     WizardShell / DescriptionComposer /
                                           IntentStep / ToolsStep / PromptStep
hooks/useAgentPipelineStream.ts            A SSE 훅
services/agentPipelineService.ts           A 서비스
utils/streamParser.ts                      SSE 수동 파서
types/agentPipeline.ts                     A 요청/응답 타입
components/agent-builder/fix/FixAgentPanel.tsx   B 패널
types/agentComposer.ts                     B 타입
pages/AgentBuilderPage/index.tsx           스튜디오 (프리필 + 저장)
store/agentDraftStore.ts                   위저드→스튜디오 인계 (비영속)
utils/wizardResultToForm.ts                A 프리필
utils/composeDraftToForm.ts                B 프리필
constants/api.ts:220,226,231               엔드포인트 상수
```
