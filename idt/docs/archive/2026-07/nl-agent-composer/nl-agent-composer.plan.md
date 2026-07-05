# Plan: nl-agent-composer

> Created: 2026-07-04
> Phase: Plan
> Scope: `idt/` 백엔드 — 자연어 한 문장("~하는 에이전트가 필요해")을 받아 LLM이 우리 도구(내부 + DB 등록 MCP)를 조합해 **에이전트 초안(draft)** 을 반환하는 단발 API. DB 저장 없음. 저장은 기존 `POST /agents`(명시적 tool_ids)로 사용자가 확정 시 수행. 기존 생성 공통단(ToolSelector/PromptGenerator)과 실행부(workflow_compiler)는 재사용/수정하지 않는 **완전 신규 모듈**.

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 자연어로 에이전트를 만드는 경로가 둘 다 반쪽이다. ① `POST /agents`의 AI 자동 선택(`ToolSelector`)은 **내부 도구 6개(TOOL_REGISTRY)만** 후보로 쓰고 MCP 도구를 모르며, 초안 확인 없이 **즉시 DB 저장**된다. ② `/agents/interview` 플로우는 preview를 주지만 역시 MCP 미포함 + 다회 왕복 세션 방식이다. 또한 "요청한 작업이 우리 도구로 가능한지" 판정(역량 커버리지)이 어디에도 없다. |
| **Solution** | 신규 단발 API `POST /api/v1/agents/compose`. **완전 신규 `AgentComposer`** 가 tool_catalog(내부 도구 + MCP 개별 도구 메타, DB 동기화됨)를 후보로 LLM structured output 1~2회 호출 → 도구 조합·system_prompt·flow_hint를 담은 초안 + 커버리지 판정(`full/partial/none`)·`missing_capabilities`를 반환. DB 저장 없음(stateless). 프론트는 응답을 생성 폼에 프리필하고, 사용자가 저장 버튼을 누르면 기존 `POST /agents`(tool_ids 명시)로 생성한다. |
| **Function/UX Effect** | 사용자는 "OOO 하는 에이전트 필요해" 한 문장으로 MCP 도구까지 포함된 에이전트 구성을 즉시 미리보고, 화면에서 수정 후 저장 시점에만 실제 생성된다. 커버 불가 역량은 목록으로 안내되어 "왜 안 되는지/뭘 등록해야 하는지"가 보인다. |
| **Core Value** | "LLM이 즉시 저장" → "LLM은 제안, 사람이 확정"으로 전환해 안전성과 UX를 동시 확보. 기존 생성/실행 경로 무수정(무회귀)으로 신규 가치를 추가한다. |

---

## 1. 배경 / 현황 분석 (해당 기능 존재 여부 확인 결과)

### 1-1. 이미 있는 것

| 기능 | 위치 | 한계 |
|------|------|------|
| 자연어 → 도구 자동 선택 + 프롬프트 생성 | `ToolSelector`(`src/application/agent_builder/tool_selector.py`), `PromptGenerator` — `POST /agents` 생성 시 | 후보가 `TOOL_REGISTRY` 내부 6개뿐(MCP 미포함, `tool_selector.py:48-51`). 초안 없이 **즉시 DB 저장**. |
| 초안 미리보기(무저장) → 확정 시 저장 | `/agents/interview` 3단 플로우(`interview_use_case.py`) — `AgentDraftPreview` 반환, finalize 시 저장 | 동일 `ToolSelector` 사용이라 MCP 미포함. 인메모리 세션 필요(다회 왕복). |
| 도구 목록(내부+MCP) 조회 | `GET /agents/tools`(`agent_builder_router.py:112-154`) | 조회 전용. LLM 조합에 연결 안 됨. MCP는 **서버 단위** 메타(`mcp_{server_id}`)만. |
| MCP 개별 도구 메타 DB 카탈로그 | `tool_catalog`(`sync_mcp_tools_use_case.py`) — `mcp:{server_id}:{tool_name}` + description 저장, `ListToolCatalogUseCase` 존재 | 어떤 생성 경로에서도 LLM 후보로 미사용. |

→ **결론: 요청하신 기능(자연어 → MCP 포함 조합 → 무저장 초안 → 화면 프리필 → 저장 시 생성)은 현재 없다. 단, 조립에 필요한 부품(도구 메타 카탈로그, 명시적 tool_ids 생성 API)은 대부분 존재한다.**

### 1-2. 결정적 갭 2개

1. **MCP 후보 미포함**: 모든 기존 LLM 조합 경로가 내부 도구만 안다.
2. **저장 경로의 MCP 미지원**: `CreateAgentUseCase._build_skeleton_from_tool_ids`(`create_agent_use_case.py:242-274`)가 `get_tool_meta(tool_id)`를 무조건 호출 → `TOOL_REGISTRY`에 없는 `mcp_*` id는 `ValueError`. **즉 초안에 MCP 도구가 들어가도 현재는 저장이 불가능**하다. (런타임 실행부는 이미 지원: `workflow_compiler.py:225`, `tool_factory.py:132`가 `mcp_` 접두사 분기 처리.)

### 1-3. tool_id 이중 체계 (설계 시 주의)

| 형태 | 의미 | 사용처 |
|------|------|--------|
| `mcp_{server_id}` | MCP **서버 단위** worker tool_id | AgentDefinition worker, 런타임 로딩(`tool_factory`) |
| `mcp:{server_id}:{tool_name}` | MCP **개별 도구** 카탈로그 id | tool_catalog (LLM 후보/표시용) |

컴포저는 개별 도구(`mcp:…`) 수준에서 선택하되, 초안 worker로 내릴 때는 `mcp_{server_id}`로 **매핑·중복 제거**해야 런타임과 호환된다.

---

## 2. 목표 / 비목표

### 2-1. 목표

- **G1.** `POST /api/v1/agents/compose` 단발 API: 자연어 요청 → 에이전트 초안 JSON 반환. **DB 저장·세션 없음(stateless)**.
- **G2.** LLM 후보에 **내부 도구 + DB 등록 MCP 개별 도구**(tool_catalog 기반) 모두 포함.
- **G3.** 커버리지 판정: `coverage: full | partial | none` + `missing_capabilities[]`(커버 못 하는 역량과 사유). partial이면 가능한 범위의 부분 초안 반환, none이면 초안 없이 안내만.
- **G4.** 초안 응답은 기존 `POST /agents`(CreateAgentRequest) 프리필과 **필드 호환** — 프론트가 그대로 생성 폼에 세팅 가능.
- **G5.** 저장 연결 보장: `CreateAgentUseCase`의 명시적 `tool_ids` 경로가 `mcp_*` id를 수용하도록 **최소 확장**(내부 레지스트리 대신 MCP 레지스트리/카탈로그에서 메타 조회). 기존 내부 도구 경로 무회귀.
- **G6.** **완전 신규 모듈**: `src/application/agent_composer/`(가칭) + 신규 라우트. `ToolSelector`/`PromptGenerator`/`workflow_compiler`/interview 코드는 수정·재사용하지 않음.
- **G7.** 초안 단계에서 `AgentBuilderPolicy`(도구 수, 프롬프트 길이 등) 사전 검증 — 프리필 후 저장 시 검증 실패가 없도록.
- **G8.** TDD(테스트 선행) + 레이어 규칙 + LOG-001 로깅 준수.

### 2-2. 비목표 (이번 범위 제외)

- **N1.** 프론트엔드 화면(프리필 UI) — 후속 feature로 분리(사용자 결정: 백엔드 API 먼저).
- **N2.** 명확화 질문(hybrid interview) — 단발 API로 확정. 정보 부족 시엔 초안 + notes로 대응.
- **N3.** compose 단계의 DB 저장, 세션/이력 저장.
- **N4.** 서브에이전트·스킬 조합(초안 범위는 도구만). 후속 확장 여지만 응답 스키마에 남긴다.
- **N5.** `workflow_compiler` 및 기존 생성/인터뷰 경로 변경 (G5의 최소 확장 제외).
- **N6.** MCP 실시간 연결 검증(초안은 DB 메타만 사용, 연결 테스트는 기존 `/mcp` 기능 소관).

---

## 3. 해결 방안

### 3-1. 전체 흐름

```
사용자: "재무 데이터 긁어서 엑셀 보고서 만드는 에이전트 필요해"
   │
   ▼
POST /api/v1/agents/compose            ← 신규 (인증 필수)
   │  ComposeAgentUseCase (신규)
   │   1) 후보 수집: tool_catalog(내부+MCP 개별 도구, is_active)  ← DB만, MCP 연결 없음
   │   2) AgentComposer(LLM structured output):
   │        - 요청 역량 분해 → 후보 매칭 → coverage 판정
   │        - 도구 조합(worker 목록) + flow_hint + system_prompt + 이름 제안
   │   3) mcp:{server}:{tool} → mcp_{server_id} worker 매핑/중복 제거
   │   4) AgentBuilderPolicy 사전 검증 (초과 시 초안 조정 또는 notes)
   ▼
ComposeAgentDraftResponse (JSON, 무저장)
   │  프론트: 에이전트 생성 폼에 프리필 (후속 feature)
   ▼
사용자 수정 → 저장 버튼
   ▼
POST /api/v1/agents  (기존, tool_ids 명시 경로)   ← mcp_* 수용 최소 확장(G5)
```

### 3-2. 신규 모듈 구성 (Thin DDD 레이어 준수)

| 레이어 | 신규 파일(안) | 책임 |
|--------|--------------|------|
| domain | `src/domain/agent_composer/schemas.py` | `ComposedDraft`, `CandidateTool`, `MissingCapability` VO |
| domain | `src/domain/agent_composer/policies.py` | coverage 판정 규칙, 초안 검증(도구 수 상한 등 — `AgentBuilderPolicy` 호출은 application에서) |
| application | `src/application/agent_composer/composer.py` | `AgentComposer`: LLM structured output 프롬프트/파싱 (신규, ToolSelector 미재사용) |
| application | `src/application/agent_composer/compose_agent_use_case.py` | 후보 수집(tool_catalog repo) → composer → 매핑/검증 → 응답 조립 |
| application | `src/application/agent_composer/schemas.py` | `ComposeAgentRequest/Response` (Pydantic) |
| interfaces | `src/api/routes/agent_builder_router.py`에 엔드포인트 1개 추가 or 신규 `agent_composer_router.py` | 라우팅만 (비즈니스 로직 금지) |
| infrastructure | (기존 재사용) `ToolCatalogRepository`, `LlmModelRepository`, `LlmFactory` | 신규 인프라 없음 |

> 라우터 파일 신규 여부는 Design에서 확정. 기존 `agent_builder_router`가 이미 700줄이므로 신규 라우터 권장.

### 3-3. API 스펙 (초안)

**Request** — `POST /api/v1/agents/compose`

```json
{
  "user_request": "재무 데이터를 웹에서 수집하고 엑셀 보고서로 만드는 에이전트",  // max 1000
  "name": "재무 리포터",            // optional — 없으면 LLM이 제안
  "llm_model_id": null              // optional — 없으면 기본 모델
}
```

**Response** — `ComposeAgentDraftResponse`

```json
{
  "coverage": "partial",                         // full | partial | none
  "name_suggestion": "재무 리포트 에이전트",
  "system_prompt": "...",                        // LLM 생성, 화면에서 수정 가능
  "tool_ids": ["tavily_search", "mcp_abc123", "excel_export"],   // CreateAgentRequest.tool_ids 호환
  "workers": [ {"tool_id": "...", "worker_id": "...", "description": "...", "sort_order": 0} ],
  "flow_hint": "tavily_search → mcp_abc123 → excel_export",
  "llm_model_id": "resolved-model-id",
  "temperature": 0.7,
  "missing_capabilities": [
    {"capability": "사내 ERP 조회", "reason": "매칭되는 내부/MCP 도구 없음", "suggestion": "ERP MCP 서버 등록 필요"}
  ],
  "notes": "웹 수집은 Tavily로 대체했습니다. ..."   // LLM의 조합 근거/주의사항
}
```

- `coverage=none`이면 `tool_ids/workers/system_prompt`는 비우고 `missing_capabilities`+`notes`만 채운다.
- 응답의 `tool_ids`+`name`+`system_prompt`+`temperature`+`llm_model_id`가 그대로 `CreateAgentRequest`에 들어가는 것이 계약(G4). 단 `system_prompt`는 현 CreateAgentRequest에 없음 → **저장 시 반영 방법은 Design에서 확정** (옵션 A: 생성 후 PATCH로 프롬프트 교체 / 옵션 B: CreateAgentRequest에 `system_prompt` optional 필드 추가. B가 왕복 1회로 우세하나 기존 API 계약 변경이므로 Design에서 결정).

### 3-4. G5 — 저장 경로 최소 확장

`CreateAgentUseCase._build_skeleton_from_tool_ids`에 `mcp_` 접두사 분기 추가:

- `mcp_*` id → MCP 레지스트리(or tool_catalog)에서 name/description 조회해 `WorkerDefinition` 구성 (`get_tool_meta` 호출 회피).
- 내부 도구 경로는 바이트 단위 무변경. 미등록/비활성 `mcp_*` id는 기존과 동일하게 `ValueError`(→422).
- 이 확장은 compose와 무관하게 "화면에서 MCP 도구 선택해 생성" 자체를 고치는 것이기도 함(현재 잠재 버그).

### 3-5. LLM 호출 설계 (개요 — 상세는 Design)

- 호출 1회(structured output)로 [역량 분해 + coverage + 도구 선택 + flow_hint + system_prompt + 이름]을 한 번에 받는 것을 기본안으로 하되, 품질 미달 시 2회 분리(선택→프롬프트 생성)를 Design에서 벤치마크 후 확정.
- 후보 목록은 tool_catalog `is_active` 전체를 `tool_id: description` 라인으로 주입. 후보가 많아질 경우 대비 상한(예: 100개) + 초과 시 로그 — 상한값은 config(하드코딩 금지).
- 존재하지 않는 tool_id 환각 방어: 응답 파싱 후 카탈로그 대조, 미존재 id는 drop + `notes` 반영 + 경고 로그.

---

## 4. 요구사항 목록

| ID | 요구사항 | 우선순위 |
|----|----------|---------|
| FR-01 | `POST /api/v1/agents/compose` — 인증 필수, 자연어 요청으로 초안 JSON 반환, DB 무저장 | P0 |
| FR-02 | 후보 수집: tool_catalog(내부+MCP, is_active)에서 조회. MCP 실시간 연결 없음 | P0 |
| FR-03 | LLM 조합: 도구 선택, worker 구성, flow_hint, system_prompt, 이름 제안 (structured output) | P0 |
| FR-04 | coverage 판정(full/partial/none) + `missing_capabilities[]` 반환 | P0 |
| FR-05 | `mcp:{server}:{tool}` → `mcp_{server_id}` worker 매핑 + 중복 제거 | P0 |
| FR-06 | 환각 tool_id 방어(카탈로그 대조 후 drop + notes) | P0 |
| FR-07 | `AgentBuilderPolicy` 사전 검증(도구 수/프롬프트 길이) — 저장 시 실패 방지 | P1 |
| FR-08 | 저장 경로 확장: `_build_skeleton_from_tool_ids`의 `mcp_*` 수용 (기존 경로 무회귀) | P0 |
| FR-09 | system_prompt 저장 반영 방식 확정·구현 (3-3 옵션 A/B 중 Design 결정) | P1 |
| FR-10 | LOG-001 로깅(start/done/failed, request_id) + 스택 트레이스 포함 에러 처리 | P0 |
| NFR-01 | compose p95 응답 ≤ LLM 1~2회 호출 수준(추가 I/O는 DB 조회만) | P1 |
| NFR-02 | TDD — use case/composer/정책/라우터 테스트 선행 작성 | P0 |

---

## 5. 리스크 / 열린 질문

| # | 리스크/질문 | 대응 |
|---|------------|------|
| R1 | MCP 서버 단위 worker(`mcp_{server_id}`)는 해당 서버의 **모든 도구**를 에이전트에 노출 — 개별 도구 단위 제어 불가 | 현 런타임 구조의 제약. 초안 `notes`에 명시. 개별 도구 필터링은 후속(런타임 변경 필요라 이번 비목표) |
| R2 | tool_catalog가 비어있거나 stale(동기화 안 됨)이면 MCP 후보 누락 | compose 시 카탈로그 0건이면 `GET /agents/tools`와 동일한 서버 단위 메타로 폴백할지 Design에서 결정 |
| R3 | `system_prompt` 프리필 저장 방식(3-3 옵션 A/B) | Design에서 확정. B 선택 시 `/api-cotract` 스킬로 프론트 타입 동기화 필요 항목에 기록 |
| R4 | coverage 판정이 LLM 주관 — 과신/과소 판정 가능 | "후보에 매칭 tool_id를 반드시 인용" 형식 강제 + 인용 없으면 missing 처리하는 규칙을 policies에 둠 |
| R5 | 인터뷰 플로우와 기능 중복 인지 | 본 기능은 단발·MCP 포함·무세션으로 포지셔닝. 인터뷰 경로는 손대지 않음(공존) |

---

## 6. 성공 기준 (Check 단계 검증 항목)

1. 자연어 요청 1회 호출로 내부+MCP 혼합 초안이 반환된다 (DB에 agent_definition row 생성 0건).
2. 존재하지 않는 역량 요청 시 `coverage=none` + missing_capabilities가 반환된다.
3. 초안 응답의 tool_ids(내부+`mcp_*`)로 `POST /agents` 호출 시 201 생성 성공, 생성된 에이전트가 정상 실행(run)된다.
4. 환각 tool_id가 응답에 포함되지 않는다 (카탈로그 대조 테스트).
5. 기존 경로 무회귀: 내부 도구만으로의 생성/인터뷰/실행 관련 기존 테스트 전부 통과.
6. `/verify-architecture`, `/verify-logging`, `/verify-tdd` 통과.

---

## 7. 다음 단계

- `/pdca design nl-agent-composer` — LLM 프롬프트/스키마 상세, 라우터 분리 여부, R2·R3 결정, 테스트 목록 확정.
