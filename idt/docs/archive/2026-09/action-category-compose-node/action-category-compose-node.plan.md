# action-category-compose-node Planning Document

> **Summary**: `action` 카테고리 도구(메일 발송·티켓 갱신 등 부작용 도구)를 react 워커에서 떼어내 **"LLM 작성 1회 → 초안 산출 → 인자 조립 → 도구 1회 호출"** 함수 노드로 만든다. 나가는 글의 작성 주체를 노드로 고정하고, 승인 게이트가 보는 초안과 실제로 나가는 본문과 사용자에게 보이는 최종 답변을 **같은 문자열**로 만든다. 동시에 "미분류 = action" 이던 폴백 계약을 "미분류 = None(react)" 으로 정정한다. 메일 지식은 코어에 들어가지 않는다.
>
> **Project**: sangplusbot (idt)
> **Version**: —
> **Author**: 배상규
> **Date**: 2026-09-22
> **Status**: Draft (v0.1)

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | `action` 카테고리는 정책(`ToolCategoryPolicy.ACTION`)·프론트 타입(`TOOL_CATEGORIES`)에 선언만 있고 노드 팩토리가 없어 react 경로로 떨어진다. react LLM이 "어떤 도구를 부를지"와 "본문 작성"을 동시에 하며 본문은 도구 호출 JSON 인자 안에 묻힌다. 승인 게이트는 그 인자에서 `draft/body/content/본문` 키를 **휴리스틱으로 추측**해 초안을 보여주고, final_answer는 그 초안을 재료 삼아 **다시 쓴다**. 작성과 발송이 한 스텝으로 뭉개져 단계별 추적·비용 집계도 되지 않는다. 더해서 `_resolve_category`는 미분류 도구(MCP 대부분)에 `"action"`을 돌려줘, "action"이 사실상 미분류 버킷이다. |
| **Solution** | ① `action` 함수 노드 — collect의 거울상. 에이전트 모델로 초안 1회 작성 → 초안을 워커 산출(규약 마커)로 남김 → 발송 인자 조립(**본문은 `tool_config`의 키에 결정적 주입**, 나머지 필드는 보조 LLM이 MCP inputSchema 기준 structured output) → 게이트 대상이면 `approval_pending` 신호를 남기고 종료, 아니면 도구 **정확히 1회** 호출. ② 카테고리 폴백 정정 — `_resolve_category`·`ToolMeta.category` 기본값을 `None`으로. **명시적으로 action을 지정한 워커만** 새 노드. ③ final_answer 초안 보존 — 초안 워커 산출이 있으면 "초안 원문 보존 + 집행/승인 상태 보고" 모드로 전환. 규칙은 도메인 정책 객체 한 곳에 두어 교체가 쉽다. |
| **Function/UX Effect** | 승인 화면의 초안 = 노드가 만든 초안 원문. 발송 본문 = 같은 문자열. 최종 답변 = 초안 원문 + 집행 결과. 실행 이력에 action 워커 스텝이 작성·집행 요약과 함께 따로 남는다. 미분류 워커는 전과 완전히 같게 동작한다. |
| **Core Value** | **승인된 것·나간 것·보이는 것이 같다.** 작성 주체가 노드로 고정되어 프롬프트·모델·비용·추적을 플랫폼이 통제한다. 메일 특화는 에이전트 프롬프트·워커 설명·`tool_config` 데이터로만 들어가고 코어는 "부작용 도구 1회 호출"만 안다 — 슬랙·티켓·사내 시스템이 같은 노드를 탄다. |

---

## Context Anchor

> Auto-generated from Executive Summary. Propagated to Design/Do documents for context continuity.

| Key | Value |
|-----|-------|
| **WHY** | 부작용 도구의 본문을 react가 도구 인자로 지어내고, 게이트는 그걸 휴리스틱으로 추측하며, final_answer가 다시 쓴다 — 승인된 초안과 나간 본문과 보이는 답변이 서로 다를 수 있다. |
| **WHO** | P2 에이전트 소유자(메일·티켓 등 부작용 도구를 에이전트에 붙이고 승인하는 사람) + 최종 사용자(초안과 집행 결과를 그대로 보는 사람) + 관리자(카탈로그에서 action 카테고리를 지정하는 사람) |
| **RISK** | ① final_answer가 프롬프트만으로는 초안을 100% 보존하지 못할 수 있다 → 정책 객체로 격리해 프로그램적 삽입으로 교체 가능하게. ② 재개 런에서 supervisor가 같은 action 워커를 다시 태워 이중 작성·이중 발송. ③ 폴백 계약 변경이 기존 테스트 계약(TC-R03)을 깬다 — 라우팅은 동일하나 기대값 갱신 필요. |
| **SUCCESS** | 명시 action 워커 런에서 도구 호출이 **정확히 1회**(게이트 시 0회), 승인 요청 `draft` == 초안 원문, 발송 인자 본문 키 == 초안 원문, 최종 답변에 초안 원문 포함, 미분류 워커 회귀 0. |
| **SCOPE** | In: action 노드 팩토리 + `ActionToolConfig` VO + 카테고리 폴백 정정 + 정책 확장(단일 도구 참조) + final_answer 초안 보존 정책 + 승인 신호 노드 직접 생성 + 관측. Out: 프론트 UI(설정은 API/JSON), 도구 없는 초안 전용 모드, 승인 화면 초안 편집, 메일 특화 정책, 내장 send 도구. |

---

## 1. Overview

### 1.1 Purpose

부작용 도구(action)를 쓰는 워커에서 **"글을 쓰는 일"** 을 react 루프 밖의 함수 노드로 꺼낸다. 노드가 초안을 산출하고, 그 초안이 그대로 승인 화면·발송 인자·최종 답변으로 흐르게 한다.

### 1.2 Background

- **현재 경로.** `workflow_compiler.py` 워커 분기에서 `category in ("search", "collect")`만 함수 노드이고, 나머지(analysis·generator 계열 제외)는 `create_agent`(react)로 간다. MCP 발송 도구는 카탈로그에 category가 없으면 `_resolve_category`가 `"action"`을 돌려주고, 그 값은 react 분기로 떨어진다. react LLM의 system prompt는 날짜 블록 + 워커 컨텍스트 블록뿐이고, 본문은 tool_call JSON 인자에 들어간다.
- **승인 게이트의 초안 추출.** `ApprovalGateMiddleware._extract_draft`는 인자에서 `("draft", "body", "content", "본문")` 키를 순서대로 찾고, 없으면 인자 전체를 직렬화한다. 게이트는 "무엇을 승인하는지"를 **도구 인자 형태에 의존**한다.
- **final_answer 재작성.** depth 0에서 워커가 하나라도 돌면 `route_to_worker_or_final`이 `final_answer`를 구조적으로 경유시키고(D1), final_answer는 워커 산출을 재료로 답변을 새로 쓴다. sub_agent가 final_answer를 건너뛰는 이유가 "토큰 이중 정제 방지"라고 주석에 적혀 있다 — 초안에도 같은 문제가 있다.
- **선례.** 이 코드베이스는 react에서 꺼낸 노드를 세 번 만들었다. collect(§5 D-03: "react 워커의 최종 산출은 LLM 종합문이라 하류가 소비할 근거가 사라진다"), analysis(도구 없는 노드), document/excel/presentation generator(소싱·저장·링크까지 노드가 완결). worker-context-injection은 "react 워커가 도구 인자를 지어냈다"를 이유로 컨텍스트 블록을 넣었다. 작성 노드는 같은 계보다.
- **폴백 실측.** 로컬 DB(2026-09-22): `tool_catalog` 25건(mcp 15, internal 10)·`agent_tool` 62건 전부 `category = NULL`. 명시적 `"action"` 은 0건. 즉 "action = 새 노드"로 바꿔도 데이터 회귀는 없고, 코드 폴백(`_resolve_category:1168`, `ToolMeta.category` 기본값)만 정정하면 된다.
- **첫 소비자.** approval-gate Phase 2가 만든 BYO 메일 MCP 경로(승인 → `McpActionExecutor` 1회 호출). 이 사이클은 그 앞단 "무엇을 승인·발송하는가"를 노드로 고정한다. Phase 2와 마찬가지로 코어에 메일 지식은 넣지 않는다.

### 1.3 Related Documents

- 카테고리 라우팅: `docs/archive/2026-09/mcp-tool-category-routing/` (Design §5 D-03 collect 단일샷, D-04 단일 도구 참조, D-07 `WorkerRunCapHooks`)
- 최종 답변 노드: `docs/archive/2026-06/final-answer-node/` (Design §3-1 라우팅 보장, §3-3 노드)
- 승인 게이트: `docs/01-plan/features/approval-gate.plan.md`, `docs/02-design/features/approval-gate.design.md` (§2.1 신호·스냅샷·재개), `docs/01-plan/features/approval-gate-phase2-mcp-executor.plan.md` (FR-04 재시도 없음, FR-09 본문 로그 금지)
- 규칙: `docs/rules/tool-and-mcp.md`, `docs/rules/logging.md`, `docs/rules/testing.md`
- 위키: `docs/wiki/backend/patterns/mcp-runtime-tool-shape.md` (📝 draft — MCP 도구명은 UUID 접두 합성명)
- 시나리오: `docs/USER-SCENARIOS.md` — P2 주인공, "일반화가 이긴다"

### 1.4 Prerequisites (선행 조건)

| 선행 | 상태 | 이 사이클과의 관계 |
|------|------|-------------------|
| approval-gate Phase 1 (신호 승격·스냅샷·재개) | completed | 노드가 남기는 `approval_pending` 형태를 그대로 쓴다. `RunAgentUseCase` 변경 없음 |
| approval-gate Phase 2 (`McpActionExecutor`) | completed (99%) | 승인 후 집행은 Phase 2 경로. 이 사이클은 `tool_args`를 "초안 원문이 본문 키에 들어간 인자"로 만든다 |
| mcp-tool-category-routing (카테고리 컬럼·collect 노드·정책) | archived | `ToolCategoryPolicy`, `collect_pipeline.py`, `_resolve_category`를 직접 확장한다 |

---

## 2. Scope

### 2.1 In Scope

- [ ] **카테고리 계약 정정** — `_resolve_category` 폴백 `"action"` → `None`, `ToolMeta.category` 기본값 `None`, `ToolCategory` 리터럴에 `collect` 추가·`None` 허용. 기존 테스트(TC-R03 등) 기대값 갱신
- [ ] **정책 확장** — `ToolCategoryPolicy.assert_assignable`: `action`도 collect와 동일하게 **단일 도구 참조만** 허용(서버 단위 `mcp_{server}` 거부)
- [ ] **`ActionToolConfig` VO** (domain/agent_builder 또는 domain/tool_catalog) — `draft_arg_key`(초안을 넣을 인자 키) 등. `DocumentGeneratorToolConfig` 패턴(frozen dataclass + `__post_init__` 검증). `WorkerDefinition.tool_config` dict로 저장, API/JSON으로 설정
- [ ] **action 노드 팩토리** (`application/agent_builder/action_pipeline.py`) — compose → 초안 산출 → 인자 조립 → 게이트 판정 → 도구 1회 호출/신호. 시그니처·반환 계약은 collect와 동형(AD-1)
- [ ] **초안 산출 규약** — search의 `SEARCH_RESULT_MARKER`/`is_search_result`와 같은 계열의 `format_draft_output`/`is_draft_output` 단일 출처
- [ ] **컴파일러 배선** — `_create_worker_node_for_category`에 `action` 분기, `function_node_ids` 등록, 게이트 적용 여부(`gated_tool_ids` + `gate_settings`)를 노드에 전달, `WorkerRunCapHooks`(런당 1회) 적용
- [ ] **승인 신호 노드 직접 생성** — `ApprovalSignalPolicy.render`로 마커를 만들고 `approval_pending`을 반환 dict에 직접 실음(미들웨어 경유 없음). `draft` = 초안 원문
- [ ] **final_answer 초안 보존** — 초안 워커 산출 감지 시 "원문 보존 + 집행/승인 상태 보고" 프롬프트 모드. 규칙은 도메인 정책 객체(가칭 `FinalAnswerDraftPolicy`) 한 곳에서 결정
- [ ] **관측** — 스텝 요약(`STEP_OUTPUT_SUMMARY_KEY`)에 작성/집행/게이트 여부, 토큰 집계, 실패 시 `last_worker_error`. 로그에 초안 본문 미기록
- [ ] **테스트** — 정책·VO·노드·컴파일러 배선·final_answer 모드·승인 신호 승격 (TDD)

### 2.2 Out of Scope

- **프론트엔드** — 에이전트 빌더의 `tool_config` 편집 폼, 카테고리 라벨 변경. 이번엔 API/JSON으로 설정. `TOOL_CATEGORIES`·라벨 `'실행'` 은 그대로
- **도구 없는 초안 전용 모드** (예: 고객문의 답변을 채팅으로만 돌려줌) — 기존 final_answer + 에이전트 프롬프트로 충분. 단, 노드를 compose/dispatch 두 단계로 나눠 **후속 사이클에서 dispatch 없는 변형을 붙일 수 있는 구조**로 만든다(사용자 결정: "추후 변경 가능하게")
- **승인 화면에서 초안 편집** — Phase 3
- **메일 특화 정책** (수신자 도메인·발송 상한·서명) — 프롬프트/데이터로. 코어 금지
- **내장 send 도구 / 플랫폼 명의 발송** — Phase 2 Out 유지
- **react 미분류 워커의 동작 변경** — 무회귀 대상
- **서버 단위 레거시 참조(`mcp_{server}`)의 action 지정** — 정책에서 거부(collect D-04 확장)
- **approval-gate Phase 1 잔여 갭**(G2·G3·G5·G13) — 해당 사이클에서 처리

---

## 3. Requirements

### 3.1 Functional Requirements

**A. 카테고리 계약 정정**

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `WorkflowCompiler._resolve_category`의 최종 폴백(TOOL_REGISTRY 부재)을 `"action"` → `None` 으로. `None` = 미분류 = react 경로(`ToolCategoryPolicy` FR-14 계약과 일치). 우선순위(agent_tool → tool_catalog → TOOL_REGISTRY)는 불변 | High | Pending |
| FR-02 | `ToolMeta.category` 기본값 `"action"` → `None`. `ToolCategory` 리터럴에 `"collect"` 추가, `None` 허용. 현재 TOOL_REGISTRY에서 category를 명시하지 않은 도구(python_code_executor·document_extractor 등)는 react 경로 그대로 | High | Pending |
| FR-03 | `ToolCategoryPolicy.assert_assignable(category="action", tool_id)` — 서버 단위 MCP 참조면 `ValueError`(collect D-04와 같은 사유: `create_all_async`가 도구 전체를 바인딩해 "1회 호출"이 정의되지 않음). 관리자 카탈로그 갱신·agent_tool 오버라이드 양쪽에서 걸린다 | High | Pending |
| FR-04 | 기존 테스트 계약 갱신 — `test_workflow_compiler.py` TC-R03("TOOL_REGISTRY에 없는 도구는 action")·`test_workflow_compiler_category.py` 동류를 `None` 기대로. 라우팅 결과(react)는 동일함을 등가 테스트(`test_create_agent_equivalence.py`)로 확인 | High | Pending |

**B. `ActionToolConfig`**

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-05 | `ActionToolConfig(draft_arg_key: str)` frozen dataclass. `draft_arg_key` 비어 있으면 **관례 키 자동 탐색 모드**(`draft`·`body`·`content`·`본문` 중 inputSchema에 존재하는 첫 키). `model_dump()`로 `WorkerDefinition.tool_config`에 저장 | High | Pending |
| FR-06 | 컴파일 시 도구 inputSchema(`mcp_input_schema` 또는 `args_schema`)에 `draft_arg_key`(또는 관례 키)가 존재하는지 검증. 없으면 워커를 격리(`failed_worker_ids`)하고 에러 로그 — 에이전트 전체는 살린다(fix-mcp-tool-call-not-reaching-server §6.2 격리 철학). 조용한 오동작 금지 | High | Pending |
| FR-07 | 설정은 기존 에이전트 생성/수정 API의 워커 `tool_config` dict로 받는다. 신규 엔드포인트·DB 컬럼 없음 | Medium | Pending |

**C. action 노드**

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-08 | **compose 단계** — 에이전트 모델(`llm`)로 초안 1회 작성. 재료: 날짜 블록·워커 컨텍스트 블록(에이전트 프롬프트 + 워커 설명)·사용자 컨텍스트 블록·대화 이력·선행 워커 산출(검색/수집/분석 결과). 새 지침 필드 없음 — 작성 지침은 `supervisor_prompt` + `WorkerDefinition.description` | High | Pending |
| FR-09 | **초안 산출** — `AIMessage(name=<worker_id>, content=format_draft_output(worker_id, draft))`를 `messages`에 추가. `is_draft_output(msg)`가 이 메시지를 식별한다(단일 출처, search 규약과 동형) | High | Pending |
| FR-10 | **인자 조립** — 보조(pipeline) LLM이 MCP inputSchema 기준으로 초안 이외 필드(수신자·제목 등)를 structured output으로 채운다(`CollectArguments` 재사용 가능). 그 뒤 `draft_arg_key`에 **초안 원문을 마지막에 덮어쓴다**(LLM이 본문 키를 채워도 초안이 이긴다). `ToolArgumentPolicy` 검증 통과 필수 | High | Pending |
| FR-11 | **게이트 판정** — 컴파일러가 넘긴 "이 워커는 게이트 대상"(`tool_id in gated_tool_ids` × `gate_settings` 합성, 기존 `_approval_gate_middleware` 판정과 같은 식)이면 도구를 호출하지 않고 `ApprovalSignalPolicy.render(tool_id, tool_args, draft=초안 원문, tool_call_id)` 마커를 만들어 `approval_pending`(`_extract_approval_pending`과 같은 형태)을 반환 dict에 직접 싣는다. `tool_call_id` 생성 규칙은 Design에서 확정 | High | Pending |
| FR-12 | **dispatch 단계** — 게이트 비대상이면 도구를 **정확히 1회** `ainvoke`. 자동 재시도 없음(Phase 2 FR-04와 같은 근거: 비가역 작업의 재시도는 이중 집행). 결과는 워커 산출 메시지로 남기고, 오류는 `ToolErrorPolicy` 계열로 `last_worker_error`에 요약 | High | Pending |
| FR-13 | compose와 dispatch는 노드 내부에서 **분리된 단계**로 구현한다(각각 함수). 후속 사이클에서 "dispatch 없는 초안 전용 변형"을 붙일 때 compose를 재사용할 수 있어야 한다 | Medium | Pending |
| FR-14 | 반환 계약은 collect와 동형: `messages`, `last_worker_id`, `token_usage`, `last_worker_error`, `STEP_OUTPUT_SUMMARY_KEY`, (게이트 시) `approval_pending`. `charts`·`analysis_source` 등 다른 state 키는 건드리지 않는다 | High | Pending |
| FR-15 | 컴파일러 — `WorkerRunCapHooks`(mcp-tool-category-routing D-07 `skip_workers`)로 action 워커를 **런당 1회**로 제한. 재개 런(outcome 주입 후 supervisor 재진입)에서 같은 워커가 다시 초안을 쓰고 발송을 시도하는 경로를 막는다 | High | Pending |
| FR-16 | 컴파일러 — action 워커를 `function_node_ids`에 등록해 `_wrap_worker`(react 래퍼)를 타지 않게 하고, `empty_signal_worker_ids`에는 **넣지 않는다**(작성은 수집이 아니다 — supervisor-early-finish-fix D-06 판정 대상 아님) | High | Pending |

**D. final_answer 초안 보존**

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-17 | final_answer가 `is_draft_output` 메시지를 감지하면 프롬프트를 "초안 보존 모드"로 바꾼다: 초안 원문을 **그대로** 답변에 포함하고, 집행 결과(dispatch 산출 또는 재개 시 주입된 outcome)를 함께 보고하며, 초안을 고쳐 쓰지 않는다 | High | Pending |
| FR-18 | 모드 결정·프롬프트 블록 구성은 도메인 정책 객체(가칭 `FinalAnswerDraftPolicy`) 한 곳에 둔다. final_answer 노드는 정책이 준 블록만 붙인다 — 후속에 "프로그램적 삽입(LLM 미경유)" 등으로 바꿀 때 교체 지점이 하나여야 한다(사용자 결정: "1번으로 하되 변경에 용이하게") | High | Pending |
| FR-19 | 승인 대기 런은 기존대로 final_answer를 **경유하지 않는다**(approval-gate §2.1 ③ — 초안은 승인 화면이 보여준다). 초안 보존 모드는 게이트 비대상 즉시 집행 런과 재개 런에서 동작한다 | High | Pending |
| FR-20 | 초안이 없는 런(search/collect/analysis만)은 프롬프트가 **바이트 단위로 동일**해야 한다(`test_final_answer_node.py` 무회귀) | High | Pending |

**E. 승인 연동 (기존 경로 재사용)**

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-21 | `approval_pending` 형태는 react 래퍼가 올리는 것과 동일. `RunAgentUseCase`의 영속·스냅샷·재개 코드는 **변경하지 않는다**. `tool_args`의 본문 키 값 == 초안 원문, `draft` == 초안 원문 | High | Pending |
| FR-22 | 승인 후 집행은 Phase 2 `McpActionExecutor`가 `tool_args`로 그대로 호출. 집행기 변경 없음 | High | Pending |
| FR-23 | 재개 시 주입되는 outcome(집행 결과/거절 사유)은 워커 산출로 들어온다(기존 계약). final_answer 초안 보존 모드가 이를 "집행 결과"로 보고한다 | High | Pending |

**F. 관측·보안**

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-24 | 스텝 요약: "초안 N자 작성 / 인자 키 [..] / 게이트 대기" 또는 "초안 N자 작성 / 도구 1회 호출 성공·실패". 인자 **키 목록만** 남기고 값은 남기지 않는다 | High | Pending |
| FR-25 | 로그에 초안 본문·수신자 등 인자 값을 남기지 않는다(Phase 2 FR-09와 동일 — PII). `request_id`·`worker_id`·`tool_id`·길이·키 목록만 | High | Pending |
| FR-26 | compose LLM·인자 조립 LLM 호출이 각각 LangSmith 추적·`ai_llm_call` 토큰 집계에 잡힌다(pipeline-langsmith-tracing 계승). `token_usage` 델타는 두 호출 합 | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 정확성 | 명시 action 워커 런에서 도구 호출 횟수 = 1(게이트 시 0). 이중 호출 0건 | 노드 단위 테스트(도구 mock 호출 카운트) + `ai_tool_call` 실런 조회 |
| 일관성 | 승인 `draft` == 발송 인자 본문 == 최종 답변에 포함된 초안 (문자열 동일) | 통합 테스트에서 세 지점 문자열 비교 |
| 무회귀 | 미분류(None) 워커·search/collect/analysis 워커의 컴파일 결과·프롬프트 불변 | 기존 `tests/application/agent_builder/*` 전부 통과(master 상시 실패 목록 제외) |
| 지연 | compose 1회 + 인자 조립 1회. react 평균(도구 호출 4~5회 관측)보다 LLM 호출 수가 적어야 한다 | 실런 `ai_llm_call` 건수 비교 |
| 보안 | 초안·인자 값 로그 금지, 재시도 금지 | `verify-logging` 스킬 + 코드 리뷰 |
| 아키텍처 | domain에 LangChain·MCP 참조 금지. 노드는 application, 정책·VO는 domain | `verify-architecture` 스킬 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] SC-1 명시 `action` 워커가 있는 에이전트를 컴파일하면 그 워커는 `create_agent`를 거치지 않고 `function_node_ids`에 있다. 미분류 워커는 전과 같이 react
- [ ] SC-2 게이트 대상 action 워커 실행 시 도구 호출 0회, `approval_pending.draft` == 초안 원문, `tool_args[draft_arg_key]` == 초안 원문
- [ ] SC-3 게이트 비대상 action 워커 실행 시 도구 호출 정확히 1회, 인자 본문 키 == 초안 원문, 재시도 0회
- [ ] SC-4 final_answer 출력에 초안 원문이 포함된다(즉시 집행 런·재개 런 모두). 초안 없는 런의 프롬프트는 불변
- [ ] SC-5 `_resolve_category` 폴백이 `None`이고, 카탈로그·레지스트리 어디에도 없는 MCP 워커는 react로 컴파일된다(등가 테스트)
- [ ] SC-6 서버 단위 참조에 action 지정 시 정책이 거부한다
- [ ] SC-7 실행 이력(`ai_run_step`)에 action 워커 스텝이 작성/집행 요약과 함께 남고, 로그·요약에 본문 값이 없다
- [ ] SC-8 재개 런에서 action 워커가 두 번째로 실행되지 않는다(`skip_workers`)
- [ ] 위 항목이 단위·통합 테스트로 고정되고 전부 통과

### 4.2 Quality Criteria

- [ ] TDD: 각 FR에 대응하는 테스트가 구현보다 먼저 존재(Red → Green)
- [ ] 함수 40줄·if 중첩 2단계 준수, config 하드코딩 없음
- [ ] `verify-architecture`·`verify-logging`·`verify-tdd` 통과
- [ ] master 대비 신규 실패 0건(상시 실패 목록은 메모리 기준 대조)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| R-1 final_answer가 프롬프트 지시만으로는 초안을 완전히 보존하지 않음(문장 다듬기·요약) | High | Medium | 정책 객체 한 곳에 격리(FR-18). SC-4를 "초안 문자열 포함"으로 테스트. 실런에서 변형이 관측되면 정책을 "프로그램적 삽입(초안은 LLM 미경유, 상태 보고만 LLM)"으로 교체 — 교체 지점 1곳 |
| R-2 재개 런에서 supervisor가 같은 action 워커를 다시 라우팅 → 이중 초안·이중 발송 | High | Medium | `WorkerRunCapHooks` 런당 1회(FR-15). 재개 시 outcome이 워커 산출로 들어가므로 supervisor는 "완료"로 본다. 통합 테스트 SC-8 |
| R-3 인자 조립 LLM이 본문 키에 자기 문장을 넣음 | Medium | High | 초안을 **마지막에 덮어쓰기**(FR-10). 테스트에서 LLM이 본문 키를 채워도 결과가 초안인지 확인 |
| R-4 도구 inputSchema가 없거나(내부 도구·스키마 미전달 MCP) 본문 키가 없음 | Medium | Medium | 컴파일 시 검증·워커 격리(FR-06). 관례 키 자동 탐색은 보조일 뿐, 없으면 실패를 드러낸다 |
| R-5 폴백 변경이 숨은 소비자를 깨뜨림 | Medium | Low | `"action"` 리터럴 소비자는 라우팅 판정·테스트뿐(grep 실측). 로컬 DB 명시 action 0건. 등가 테스트로 react 결과 불변 확인 |
| R-6 승인 신호 형태가 미들웨어 경로와 미세하게 어긋나 `RunAgentUseCase`가 영속 실패 | High | Low | `ApprovalSignalPolicy.render/extract` 단일 출처 사용. `test_approval_signal_lift.py`를 노드 경로로 확장 |
| R-7 compose에 선행 워커 산출 전체를 넣어 프롬프트 폭주 | Medium | Medium | collect와 같은 직렬화 상한(`_CONTEXT_MAX_MESSAGES`·슬라이스) 재사용. 상한은 config |
| R-8 게이트 판정 로직이 미들웨어 부착 판정과 두 벌이 됨 | Medium | Medium | 판정 함수를 공유(`_approval_gate_middleware`의 판정부를 분리해 노드와 미들웨어가 같은 함수를 부름) — Design에서 위치 확정 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `WorkflowCompiler._resolve_category` | Application | 최종 폴백 `"action"` → `None` |
| `ToolMeta.category` / `ToolCategory` | Domain schema | 기본값 `None`, 리터럴 확장 |
| `ToolCategoryPolicy.assert_assignable` | Domain policy | action에도 단일 도구 참조 강제 |
| `ActionToolConfig` (신규) | Domain VO | `draft_arg_key` 등 |
| `action_pipeline.py` (신규) | Application node | compose/dispatch 노드 |
| `format_draft_output` / `is_draft_output` (신규) | Application 규약 | search 규약과 동형 |
| `WorkflowCompiler` 워커 분기·`_create_worker_node_for_category` | Application | action 분기·함수 노드 등록·게이트 판정 전달·run cap |
| `_create_final_answer_node` | Application | 초안 보존 모드 블록 삽입 |
| `FinalAnswerDraftPolicy` (신규) | Domain policy | 모드 결정·블록 구성 |
| `ApprovalSignalPolicy` | Domain policy | 변경 없음(노드가 `render` 호출). 필요 시 `tool_call_id` 생성 헬퍼 추가 |
| 테스트 `test_workflow_compiler.py`·`test_workflow_compiler_category.py` | Test | 폴백 기대값 갱신 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `_resolve_category` | READ | `workflow_compiler.py` 워커 분기(`category in ("search","collect")` 판정) | **None** — `"action"`과 `None` 모두 react 분기. 결과 불변 |
| `_resolve_category` | READ | `tests/application/agent_builder/test_workflow_compiler.py:220-240`, `test_workflow_compiler_category.py:148-158` | **Breaking(테스트 계약)** — 기대값 `None`으로 갱신 |
| `ToolMeta.category` | READ | `_resolve_category` TOOL_REGISTRY 단계, `tool_catalog` 시드(`builtin_default`·`requires_approval_default`와 같은 계열인지 Design에서 확인) | Needs verification — 시드가 category를 카탈로그에 복사한다면 기존 행 불변(관리자 값 보존 D-02) |
| `ToolCategoryPolicy.assert_assignable` | CALL | `application/tool_catalog/update_metadata_use_case.py`, agent_tool 카테고리 오버라이드 경로 | Needs verification — action + 서버 단위 참조 조합이 새로 거부됨. 로컬 DB 해당 데이터 0건 |
| `_create_worker_node_for_category` | CALL | 컴파일러 워커 분기 1곳 | None — 분기 추가 |
| `function_node_ids` / `empty_signal_worker_ids` / `worker_run_limits` | READ | `_wrap_step`·`_with_empty_signal`·`WorkerRunCapHooks` 배선 | None — action은 function에 넣고 empty_signal에는 넣지 않음(FR-16) |
| `approval_pending` state | READ | `run_agent_use_case.py:1027` 캡처, `:918` 영속, `route_to_worker_or_final` 종료 판정 | None — 같은 형태로 채움 |
| `_create_final_answer_node` | CALL | depth 0 모든 런 | Needs verification — 초안 없는 런 프롬프트 불변(FR-20, `test_final_answer_node.py`) |
| `ApprovalGateMiddleware` | ATTACH | react 워커·wiki 워커 | None — react 경로는 그대로 미들웨어 |
| `McpActionExecutor` | CALL | `decide_use_case._execute_now`, `execute_scheduler` | None — `tool_args` 형태 동일 |
| 프론트 `TOOL_CATEGORIES`·`AdminToolsPage` | READ | 카테고리 선택 UI | None — 값 집합 불변. 라벨 의미가 "react"에서 "작성→1회 호출"로 바뀌므로 후속 UI 사이클에서 설명 문구 갱신 권고 |

### 6.3 Verification

- [ ] 위 소비자 전부 테스트 또는 grep으로 확인
- [ ] 권한·승인 경로 변경 없음(`ApprovalPolicy.can_decide` 불변)
- [ ] DB 스키마·마이그레이션 변경 없음(`tool_config` dict 재사용)

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules, BaaS | Web apps, SaaS MVPs | ☐ |
| **Enterprise** | Strict layer separation, DI | High-traffic, complex architectures | ☑ (Thin DDD, 기존) |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 노드 위치 | react 미들웨어로 compose 선행 / 별도 함수 노드 | **함수 노드** | collect·analysis·generator 선례. react 안에서는 초안이 인자로만 존재해 승인·final_answer가 원문을 못 본다 |
| 카테고리 값 | 기존 `action` 재사용 + 폴백 정정 / 새 값 `compose` | **`action` 재사용, 폴백 `None`** | 명시 action 데이터 0건, 폴백 계약이 정책 주석과 어긋나 있던 것을 바로잡는다. 프론트 타입 변경 없음 (사용자 결정) |
| 발송 인자 조립 | 전부 결정적 매핑 / 전부 보조 LLM / **본문 결정적 + 나머지 보조 LLM** | **혼합** | 본문 변조 불가 + 설정 부담 최소. 도구마다 다른 필드는 inputSchema로 일반화 (사용자 결정) |
| compose 모델 | 에이전트 모델 / 보조 모델 | **에이전트 모델** | 고객에게 나가는 본문 품질이 핵심 (사용자 결정) |
| 작성 지침 출처 | 새 `tool_config` 필드 / 기존 프롬프트·워커 설명 | **기존** | 설정 항목 증가 없이 데이터로 특화 (사용자 결정) |
| final_answer 처리 | 재작성 금지 모드 / END 직행 / 현행 | **재작성 금지 모드, 정책 객체로 격리** | D1 라우팅 불변, 변경 지점 1곳 (사용자 결정 "변경 용이하게") |
| 초안 전용 모드 | 포함 / 제외 | **제외, 단 compose/dispatch 분리** | 스코프 최소화, 후속 확장 가능 (사용자 결정) |
| 즉시 집행 시 최종 답변 | 초안 원문 + 결과 / 결과만 | **초안 원문 + 결과** | 승인 경로와 출력 형태 통일 (사용자 결정) |
| 게이트 신호 | 미들웨어 재사용 / 노드 직접 생성 | **노드 직접 생성** | 함수 노드에는 미들웨어가 없다. `ApprovalSignalPolicy`가 단일 출처라 형태는 동일 |
| 재개 이중 실행 방지 | 신규 카운터 / `WorkerRunCapHooks` | **`WorkerRunCapHooks`** | D-07 선례, supervisor 코어 미수정 |

### 7.3 Clean Architecture Approach

```
Selected Level: Enterprise (Thin DDD)

domain/
  agent_builder/schemas.py          ToolMeta.category 기본값 None, ToolCategory 확장
  agent_builder/action_tool_config.py   ActionToolConfig VO (신규)
  agent_builder/policies.py         FinalAnswerDraftPolicy (신규) — LangChain 참조 금지
  tool_catalog/policies.py          ToolCategoryPolicy.assert_assignable action 확장
  approval/policies.py              ApprovalSignalPolicy (재사용)
application/
  agent_builder/action_pipeline.py  create_action_node (신규): compose → draft → assemble → gate|dispatch
  agent_builder/search_pipeline.py  (또는 신규 모듈) format_draft_output / is_draft_output
  agent_builder/workflow_compiler.py  action 분기, function_node 등록, 게이트 판정 전달, run cap
infrastructure/
  (변경 없음 — MCPToolAdapter·McpActionExecutor 재사용)
interfaces/
  (변경 없음 — tool_config dict 경유)
```

의존 방향: `action_pipeline` → domain 정책/VO, LangChain 메시지(application 허용). domain은 dict·str만 다룬다.

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- 노드 팩토리 시그니처·반환 계약: `create_collect_node` / `create_search_pipeline_node` (AD-1)
- 산출 메시지 규약: `format_search_result` / `is_search_result` 단일 출처 (D2)
- 트레이스 → state 승격: `ToolErrorPolicy.summarize`, `ApprovalSignalPolicy.extract` 계열
- VO 패턴: `DocumentGeneratorToolConfig` (frozen dataclass + `__post_init__` + `model_dump`)
- 로깅: `docs/rules/logging.md` — 구조화 로그, PII 값 금지, `request_id` 자동 주입
- 테스트: `uv run python -m pytest` (메모리: `uv run pytest`는 차단)

### 8.2 Conventions to Define/Verify

- 초안 마커 문자열과 `is_draft_output` 위치(`search_pipeline.py` 동거 vs 신규 `worker_output_markers.py`) — Design
- 게이트 판정 함수의 공유 위치(미들웨어 부착 판정과 노드 판정이 같은 함수) — Design
- `tool_call_id` 생성 규칙(노드에는 LLM tool_call이 없다) — Design
- compose 프롬프트의 선행 워커 산출 직렬화 상한 — config 키 이름

### 8.3 Environment Variables Needed

- 없음(신규). 상한 값은 기존 `Settings` 패턴으로 추가 시 Design에서 명명

### 8.4 Pipeline Integration

- 이 사이클은 approval-gate Phase 2의 "무엇을 승인하는가"를 고정하는 앞단. Phase 2 코드는 변경하지 않는다
- 후속 후보: (a) 초안 전용 모드(dispatch 없음), (b) 에이전트 빌더 `tool_config` 편집 UI + 카테고리 설명 문구, (c) 승인 화면 초안 편집(Phase 3), (d) final_answer 프로그램적 삽입 전환(R-1 관측 후)

---

## 9. Open Questions (Design에서 결정)

| # | 질문 | 후보 |
|---|------|------|
| Q-1 | 게이트 판정을 노드에 어떻게 넘기나 | 컴파일러가 bool을 계산해 팩토리에 전달 / 판정 객체(`GatedWorkerPolicy`)를 노드가 직접 호출 |
| Q-2 | `tool_call_id` 값 | `f"{worker_id}:{run_id}"` 결정적 / uuid4 / 빈 문자열 허용 여부(재개 주입 경로가 id를 쓰는지 확인) |
| Q-3 | 인자 조립 LLM 입력에 대화 이력을 얼마나 넣나 | collect와 동일 상한 / 초안 + 최근 사용자 질문만 |
| Q-4 | `ActionToolConfig`에 고정 인자(`fixed_args: dict`, 예: 발신 표시명)를 둘 것인가 | 이번 포함(일반적 요구) / 제외(YAGNI) |
| Q-5 | dispatch 결과 메시지가 초안 메시지와 별도인가 하나인가 | 별도 AIMessage 2개(초안·결과) / 초안 메시지 하나에 결과 덧붙임 |
| Q-6 | FR-06 검증 시점 | compile 시 격리 / 첫 실행 시 `last_worker_error` |

---

## 10. Next Steps

1. `/pdca design action-category-compose-node` — 3안 비교 후 Q-1~Q-6 확정
2. Design 확정 후 Do는 TDD 순서: 정책·VO(domain) → 초안 규약 → 노드 → 컴파일러 배선 → final_answer 정책 → 통합(승인 신호 승격·재개)
3. 실런 검증: 로컬 BYO 메일 MCP 워커에 `category="action"` + `tool_config.draft_arg_key` 설정 → `ai_run_step`·`ai_tool_call`·`approval_request.draft` 세 지점 문자열 대조

---

## Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1 | 2026-09-22 | 배상규 | 초안. Checkpoint 1·2 결정 반영(인자 혼합 조립, final_answer 보존 모드+정책 격리, 백엔드 한정, 에이전트 모델, action 재사용+폴백 None, 초안 전용 모드 제외+분리 구조, 즉시 집행 시 초안 원문 포함) |
