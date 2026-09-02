# fix-mcp-tool-call-not-reaching-server Design Document

> **Summary**: MCP 도구 호출이 서버에 도달하지 않는 문제를, 3구간 계측으로 차단 지점을 확정한 뒤 도구 선택·도구명·DI 배선 3개 결함을 제거한다.
>
> **Project**: sangplusbot / idt (FastAPI + LangGraph, Thin DDD)
> **Author**: 배상규
> **Date**: 2026-09-02
> **Status**: Draft
> **Planning Doc**: [fix-mcp-tool-call-not-reaching-server.plan.md](../../01-plan/features/fix-mcp-tool-call-not-reaching-server.plan.md)

### Pipeline References

| Phase | Document | Status |
|-------|----------|--------|
| Phase 1 | Schema Definition | N/A — DB 스키마 변경 없음 |
| Phase 2 | `idt/CLAUDE.md` + `docs/rules/tool-and-mcp.md` | ✅ |
| Phase 3 | Mockup | N/A — UI 변경 없음 |
| Phase 4 | API Spec | N/A — 엔드포인트 변경 없음 |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | MCP 워커 도구 호출이 서버에 도달하지 않고, 실패가 조용해서 원인 추적이 불가능하다 |
| **WHO** | P2 — Agent Builder로 MCP 도구를 조립하는 에이전트 소유자 / KB 운영자 |
| **RISK** | 실제 차단 지점이 계측 전에는 미확정 — 추정만으로 고치면 증상이 그대로 남는다 |
| **SUCCESS** | 등록된 MCP 서버의 지정 도구가 실제 호출되고(서버 측 수신 확인), 3개 결함에 회귀 테스트가 붙는다 |
| **SCOPE** | Phase 1 계측·재현 → Phase 2 결함 수정 → Phase 3 회귀 가드. inputSchema 노출은 제외 |

---

## 1. Overview

### 1.1 Design Goals

1. **차단 지점이 로그 한 줄로 드러난다** — 도구 생성(①) / LLM 등록(②) / 도구 실행(③) 중 어디서 끊겼는지 `request_id`로 추적 가능
2. **지정한 MCP 도구가 실제로 바인딩된다** — `mcp:{srv}:{tool}`은 정확히, 레거시 `mcp_{uuid}`는 폴백 사실을 드러내며
3. **LLM에 노출되는 도구명이 OpenAI 제약(64자)을 만족하고 서버 내에서 유일하다**
4. **DI 배선 회귀가 테스트로 잡힌다** — 배선이 빠지면 CI에서 실패
5. **MCP 서버 1개의 장애가 에이전트 전체를 죽이지 않는다**

### 1.2 Design Principles

- **계측이 수정을 선행한다** — Phase 1의 실측 결과 없이 Phase 2에 착수하지 않는다 (Plan §5 최상위 리스크)
- **규칙은 domain에, 배선은 infrastructure에** — 도구명 규칙은 `MCPConnectionPolicy`(순수), 연결은 `tool_registry`/`tool_adapter`
- **단일 해석 지점** — tool_id 파싱은 `domain/tool_catalog/mcp_tool_id.py` 하나만 사용, 문자열 `startswith("mcp_")` 분기 금지
- **하위호환 우선** — 레거시 tool_id를 깨뜨리는 변경 금지 (DB 마이그레이션 없음)
- **과도한 추상화 금지** — 신규 프로덕션 모듈 0개 (`idt/CLAUDE.md` §6)

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| 기준 | Option A: 최소 변경 | Option B: 클린 분리 | Option C: 실용 균형 |
|------|:-:|:-:|:-:|
| **접근** | 기존 파일 국소 수정만 | 바인딩/진단 전용 컴포넌트 신설 | 규칙은 domain policy, 배선은 기존 구조 유지 |
| **신규 프로덕션 파일** | 0 | 3~4 | 0 |
| **신규 테스트 파일** | 1 | 4 | 2 |
| **수정 파일** | 5 | 6 | 5 |
| **도구명 64자 처리** | 상한만 64로 낮추고 단순 절단 | `McpToolNamePolicy` + 충돌 레지스트리 | policy에 해시 접미사 축약 (결정적) |
| **복잡도** | Low | High | Medium |
| **유지보수성** | Medium | High | High |
| **노력** | Low | High | Medium |
| **리스크** | 이름 충돌 잔존 | 과도한 추상화 (CLAUDE.md §6 위반) | Low |

**Selected**: **Option C — 실용 균형**

**Rationale**: A의 단순 절단은 접두부 `mcp_{uuid}_`가 41자로 고정이라 도구명이 길면 앞 64자가 전부 동일해져 **같은 서버 내 도구끼리 이름이 겹친다** — 겹치면 LangChain 도구 목록에서 하나가 가려져 "호출했는데 아무 일도 안 일어남"이라는 이번 증상을 오히려 재생산한다. B는 버그 수정 규모 대비 신규 모듈 3~4개로 `idt/CLAUDE.md` §6 "과도한 추상화 금지"에 정면 충돌한다. C는 이름 규칙을 이미 존재하는 domain policy에 함수 하나로 추가해 충돌을 결정적으로 회피하면서 신규 프로덕션 모듈을 만들지 않는다.

### 2.1 Component Diagram

```
┌──────────────────────── compile time ────────────────────────┐
│                                                              │
│  WorkflowCompiler.compile()          workflow_compiler.py    │
│    │  parse_mcp_tool_id(tool_id)  ── domain/tool_catalog     │
│    │                                                         │
│    ├─▶ ToolFactory.create_async()    tool_factory.py:176     │
│    │     └ _create_mcp_tool()        tool_factory.py:197     │
│    │         └ MCPToolLoader.load_by_tool_id()               │
│    │             └ MCPToolRegistry.get_tools()               │
│    │                 └ MCPClientFactory.create_session() ──────▶ ① MCP 서버
│    │                     session.list_tools()                │      (list_tools)
│    │                 └ MCPToolAdapter(name=…) 생성           │
│    │                     ▲ MCPConnectionPolicy.build_tool_name()
│    │                       (domain/mcp/policy.py — 64자·충돌회피)
│    │                                                         │
│    └─▶ create_agent(tools=[tool])    workflow_compiler.py:426 ─▶ ② LLM 도구 등록
│          (실패 격리: try/except → 워커 스킵)                  │      (OpenAI 400 지점)
└──────────────────────────────────────────────────────────────┘
┌──────────────────────── run time ────────────────────────────┐
│  MCPToolAdapter._arun()              tool_adapter.py:51 ───────▶ ③ MCP 서버
│    └ MCPClientFactory.create_session().call_tool()           │      (call_tool)
└──────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow — 진단 결정 트리 (Phase 1 산출물)

```
에이전트 실행 (request_id = R)
   │
   ├─ 로그 "MCP tool binding start" (tool_id=R) 없음
   │     → compile이 MCP 워커에 도달하지 못함
   │       (워커 정의/카테고리 라우팅 문제 — D1~D3 밖)
   │
   ├─ 있음 → "MCP session connecting"(①) 없음
   │     → 도구 생성 전 실패: loader/repository 미주입 = D3
   │
   ├─ ① 있음 → "MCP server tools loaded" tool_count=0
   │     → 서버 접속은 됐으나 도구 목록이 빔 (인증/엔드포인트)
   │
   ├─ tool_count>0 → "MCP tool bound"의 mcp_tool_name이 의도와 다름
   │     → D1 (레거시 서버 단위 ID 첫-도구 폴백)  ★ 유력
   │
   ├─ 바인딩 정상 → LLM 호출에서 400 / 도구명 길이 > 64
   │     → D2 (OpenAI function name 상한)
   │
   └─ 전부 정상 → "MCP tool execution started"(③) 없음
         → LLM이 도구를 호출하지 않음 (프롬프트/라우팅 문제 — 별도 사이클)
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `WorkflowCompiler` | `parse_mcp_tool_id`, `ToolFactory` | MCP 워커 판별 · 도구 생성 · 실패 격리 |
| `ToolFactory._create_mcp_tool` | `McpToolRef`, `MCPToolLoader`, `mcp_repository` | 서버 조회 → 도구 목록 → 지정 도구 선택 |
| `MCPToolRegistry` | `MCPConnectionPolicy.build_tool_name` | LLM 노출명 생성 (64자·유일성) |
| `MCPToolAdapter` | `MCPClientFactory` | 실제 `call_tool` 실행 |
| `api/main.py` DI | `MCPToolLoader`, `SessionScopedMcpServerRepository` | 런타임 ToolFactory 배선 |

---

## 3. Data Model

DB 스키마 변경 없음. 마이그레이션 없음.

### 3.1 도구 식별자 (기존, 변경 없음)

```python
@dataclass(frozen=True)
class McpToolRef:            # domain/tool_catalog/mcp_tool_id.py
    server_id: str
    tool_name: str | None    # None이면 서버만 특정 (레거시)

    @property
    def is_server_level(self) -> bool: ...
```

| 형식 | 예 | 해석 | 발급처 |
|------|-----|------|--------|
| `mcp:{server_id}:{tool}` | `mcp:081c6fe7-…:create_issue` | 개별 도구 확정 | `sync_mcp_tools_use_case.py:51` (카탈로그) |
| `mcp_{server_id}` | `mcp_081c6fe7-…` | 서버만 특정 → 첫 도구 폴백 | 레거시 저장 에이전트 |

### 3.2 LLM 노출 도구명 규칙 (신규)

```
raw   = f"{server_config.name}_{mcp_tool.name}"      # 예: mcp_081c6fe7-…-29b8bf073167_create_issue
step1 = 하이픈/공백 → "_", 소문자                     # 기존 sanitize_tool_name 동작
step2 = len ≤ 64 이면 그대로 반환
step3 = len > 64 이면  step1[:59] + "_" + sha1(step1).hexdigest()[:4]
                       └─ 59 + 1 + 4 = 64자 고정
```

- **결정적**: 같은 입력 → 항상 같은 출력. 재컴파일 시 이름이 흔들리지 않아 `ai_tool_call.tool_name` 관측 기록과 대조 가능
- **충돌 회피**: 앞 59자가 같아도 원본 전체의 해시가 달라 접미사로 갈린다
- **가독성**: 접미사는 도구명 뒤가 아니라 잘린 문자열 뒤에 붙어 `mcp_081c6fe7_…_create_iss_9f3a` 형태로 어떤 도구인지 남는다

---

## 4. API Specification

**엔드포인트 변경 없음.** 요청/응답 스키마 변경 없음 → `idt_front` 동기화 불필요 (루트 `CLAUDE.md` §4-1 해당 없음).

관측 가능한 외부 계약 변화는 **로그 필드**뿐:

| 로그 이벤트 | 위치 | 신규/변경 필드 |
|-------------|------|----------------|
| `MCP tool binding start` (신규) | `tool_factory._create_mcp_tool` | `request_id`, `tool_id`, `server_id`, `requested_tool` |
| `MCP session connecting` | `client_factory.create_session` | `request_id` (기존, 호출부에서 실제 전달되도록 보강) |
| `MCP server tools loaded` | `tool_registry._load_server_tools` | `tool_id`, `tool_names` 추가 |
| `MCP tool bound` (신규) | `tool_factory._create_mcp_tool` | `bound_tool`, `exposed_name`, `fallback` (bool), `available` |
| `Legacy server-level MCP worker` (기존 warning) | 동일 | 유지 |
| `MCP tool execution started/completed/failed` | `tool_adapter._arun` | `request_id`, `tool_id` 추가 |
| `MCP worker tool creation failed` (신규) | `workflow_compiler` | `worker_id`, `tool_id`, `exception` |

---

## 5. UI/UX Design

**해당 없음** — 프론트엔드 변경 없음. 사용자에게 드러나는 변화는 에이전트 실행 실패 시 서버 로그의 진단 가능성뿐이다.

---

## 6. Error Handling

### 6.1 실패 지점별 처리

| # | 실패 | 현재 동작 | 설계 동작 |
|---|------|-----------|-----------|
| E1 | `mcp_tool_loader` 미주입 | `ValueError` → compile 전체 실패 | 유지 (배선 오류는 즉시 드러나야 함) + DI 계약 테스트로 사전 차단 |
| E2 | `mcp_repository` 미주입 | `ValueError` → compile 전체 실패 | 유지 + 동일 테스트 |
| E3 | 서버 조회 실패 / 등록 없음 | `load_by_tool_id`가 `[]` → `ValueError` → compile 전체 실패 | **워커 단위 격리** — 해당 워커만 스킵, 사유 로그 (FR-07) |
| E4 | 서버 접속 실패 | `tool_registry`가 `[]` 반환(서버 단위 격리) → 위 E3 경로 | 동일 — E3로 흡수 |
| E5 | 지정 도구가 서버에 없음 | `ValueError: MCP tool not found` | **워커 단위 격리** + 서버가 실제로 제공하는 도구명 목록을 로그에 포함 |
| E6 | 레거시 ID로 도구 특정 불가 | `tools[0]` 폴백 + warning | ~~유지~~ → **서버 도구 전체 바인딩** (module-1 실측 후 변경, 아래 §6.3) |
| E7 | 도구 실행 중 서버 오류 | 예외 전파 (`tool_adapter`) | 유지 + `request_id`/`tool_id` 포함 |

### 6.2 워커 단위 격리 정책 (FR-07)

```
MCP 워커 도구 생성 실패
   → logger.error("MCP worker tool creation failed", worker_id, tool_id, exception=e)
   → 해당 worker를 worker_map에 등록하지 않음
   → supervisor에 넘기는 workers 목록에서도 제외
   → 나머지 워커로 그래프 컴파일 계속
```

**설계 근거**: `MCPToolRegistry._load_server_tools`가 이미 "서버 1개 실패는 건너뛰고 나머지 계속"이라는 격리 철학을 따른다(`tool_registry.py:104`). 워커 레벨에도 같은 규칙을 적용해 일관성을 맞춘다.

**주의**: E1/E2(배선 오류)는 격리하지 **않는다**. 배선 누락은 개발자 실수이고 조용히 넘어가면 이번 문제와 똑같은 "조용한 실패"가 재발한다.

> **구현 시 보강**: 워커가 **전부** 실패하면 빈 그래프를 만들지 않고 `ValueError`로 실패시킨다(U14). 도구 없는 supervisor가 라우팅할 대상이 없어 조용히 무의미한 응답을 내는 것을 막는다.

### 6.3 E6 변경 — 레거시 ID는 서버 도구 전체를 바인딩한다 (module-1 실측 후)

**변경 근거**: Plan §1.2.1 실측에서 대상 워커의 description이 3개 도구(`scrape_url`, `scrape_urls`, `extract_structured`)를 모두 안내하는데 `tools[0]` 하나만 바인딩되는 것이 확인됐다. 경고 로그만으로는 사용자의 증상(=요청이 서버에 안 옴)이 해결되지 않는다.

**설계**:

```python
# ToolFactory
async def create_all_async(tool_id, ...) -> list[BaseTool]:
    mcp:{srv}:{tool} → [지정 도구 1개]
    mcp_{srv}        → 서버가 노출하는 도구 전체
    비-MCP           → [create() 결과 1개]

# WorkflowCompiler
worker_tools = await self._tool_factory.create_all_async(...)
create_agent(model=llm, tools=worker_tools, ...)
```

- `create_async`(단수)는 **그대로 유지** — `run_middleware_agent_use_case.py:44` 경로 하위호환
- `search`/`wiki` 분기는 단일 도구 계약을 유지하므로 `tool = worker_tools[0]`로 기존 동작 보존
- 로그: `MCP tools bound`(`bound_tools`, `available`, `server_level=True`)가 기존 `fallback=True` 경고를 대체

**FR-04 대체**: Plan의 "첫 도구로 폴백하되 경고" 요구는 전체 바인딩으로 무의미해졌다. 폴백 자체가 사라졌으므로 경고할 대상도 없다.

**남는 한계**: `MCPToolAdapter.args_schema`가 도구 공통 `{arguments: dict}`이라, 도구가 노출돼도 LLM이 인수를 잘못 담을 여지는 남는다. 요청 **도달**과 인수 **정확성**은 별개 문제이며 후자는 별도 사이클(Out of Scope).

---

## 7. Security Considerations

- [x] MCP 인증정보(`auth_config`)는 `SecretCipher`로 암복호화 — 본 설계에서 변경 없음
- [x] **로그에 인증 헤더/토큰을 남기지 않는다** — 신규 로그 필드는 `tool_id`/`server_id`/`tool_name`/`exposed_name`만. `MCPServerConfig.streamable_http.headers`, `sse.headers`는 절대 로깅 금지
- [x] `server_id`는 내부 UUID로 외부 노출 없음 (서버 로그 한정)
- [x] 도구명 해시(sha1 4자)는 식별용이며 비밀값을 포함하지 않음
- [ ] Rate Limiting — 해당 없음 (외부 진입점 변경 없음)

---

## 8. Test Plan

> 본 기능은 백엔드 전용이라 표준 L1/L2/L3(API/UI/E2E) 대신 **U(단위) / I(통합) / M(수동 재현)** 3계층으로 정의한다.
> 테스트 코드는 Do 단계에서 구현과 한 세트로 작성한다 (TDD: Red → Green).

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| U: 단위 | 도구명 규칙, 도구 선택 분기, 실패 격리 | pytest + mock | Do |
| I: 통합 | DI 배선 계약 (main.py 팩토리) | pytest | Do |
| M: 수동 | 실제 MCP 서버 대상 재현·검증 | `/verify-mcp-connections` + 서버 로그 | Do (Phase 1 / 최종 검증) |

### 8.2 U: 단위 테스트 시나리오

| # | 대상 | 시나리오 | 기대 결과 | FR |
|---|------|----------|-----------|-----|
| U1 | `MCPConnectionPolicy.build_tool_name` | 64자 이하 입력 | 원본 그대로 (해시 미부착) | FR-05 |
| U2 | 〃 | 64자 초과 입력 | 정확히 64자, `[:59] + "_" + hash4` | FR-05 |
| U3 | 〃 | 앞 59자가 동일하고 뒤가 다른 두 입력 | **서로 다른** 결과 (충돌 없음) | FR-05 |
| U4 | 〃 | 동일 입력 2회 호출 | 동일 출력 (결정적) | FR-05 |
| U5 | 〃 | 하이픈/공백/대문자 포함 | `_` 치환 + 소문자 (기존 동작 보존) | FR-05 |
| U6 | `ToolFactory._create_mcp_tool` | `mcp:{srv}:create_issue`, 서버에 3개 도구 | `create_issue`에 정확히 바인딩 | FR-03 |
| U7 | 〃 | `mcp:{srv}:없는도구` | `ValueError`, 메시지에 실제 도구명 목록 포함 | FR-03/E5 |
| U8 | 〃 | 레거시 `mcp_{uuid}`, 서버에 3개 도구 | `tools[0]` 반환 + `fallback=True` warning 로그 | FR-04 |
| U9 | 〃 | 레거시, 서버에 1개 도구 | `tools[0]` 반환 (경고는 남되 모호성 없음 표기) | FR-04 |
| U10 | 〃 | loader 미주입 | `ValueError` (격리하지 않음) | E1 |
| U11 | 〃 | repository 미주입(생성자·인자 모두 None) | `ValueError` | E2 |
| U12 | 〃 | 생성자 주입 repository만 있음 (컴파일러 호출 형태) | 주입 repository로 폴백 성공 | FR-06 |
| U13 | `WorkflowCompiler` | MCP 워커 1개가 `ValueError`, 일반 워커 1개 정상 | 그래프 컴파일 성공, MCP 워커만 제외, error 로그 1건 | FR-07 |
| U14 | 〃 | 모든 워커가 MCP이고 전부 실패 | compile 실패 (빈 그래프 생성 금지) | FR-07 |
| U15 | `MCPToolAdapter` | `_arun` 호출 | `request_id`/`tool_id`가 실행 로그에 포함 | FR-01 |

### 8.3 I: 통합 테스트 시나리오

| # | 대상 | 시나리오 | 기대 결과 | FR |
|---|------|----------|-----------|-----|
| I1 | `main.py` 런타임 ToolFactory | 앱 팩토리 생성 후 인스턴스 검사 | `_mcp_tool_loader is not None` **and** `_mcp_repository is not None` | FR-06 |
| I2 | 〃 | `_mcp_repository` 타입 | `SessionScopedMcpServerRepository` (per-request 세션 확보) | FR-06 |
| I3 | 미들웨어 에이전트 경로 | `RunMiddlewareAgentUseCase`가 쓰는 ToolFactory | MCP tool_id 처리 가능 여부를 명시적으로 판정 (지원 or 명확한 실패) | Plan §6.2 |

> **I1의 의도**: Plan 수립 중 이 배선이 실제로 빠진 작업트리가 관측됐다. 이 테스트가 그 회귀를 CI에서 잡는 유일한 그물이다.

### 8.4 M: 수동 재현 시나리오

| # | 단계 | 확인 |
|---|------|------|
| M1 | `/verify-mcp-connections` 실행 | 대상 서버 `081c6fe7-…`가 `list_tools`에 응답하는가, 도구 목록은 무엇인가 |
| M2 | 문제 에이전트 실행, 서버 로그 수집 | §2.2 결정 트리를 따라 차단 지점 판정 → **Plan §1.2 결함표에 실측 결과 기록** |
| M3 | 수정 후 재실행 | MCP 서버 측에 **지정한 도구**의 `call_tool` 수신 (SC-01) |
| M4 | 레거시 tool_id 에이전트 재실행 | 기존과 동일하게 동작 (하위호환 회귀 없음) |

### 8.5 Seed Data Requirements

| Entity | Minimum Count | Key Fields Required |
|--------|:---:|---------------------|
| `mcp_server` (실서버, M 계층) | 1 | `id=081c6fe7-…`, `endpoint`, `transport`, `auth_config` |
| mock 도구 목록 (U 계층) | 3 | 이름이 서로 다르고, 최소 1개는 64자 초과를 유발할 만큼 긴 것 |

U/I 계층은 실제 MCP 서버 없이 mock으로 완결한다. 실서버 의존은 M 계층에만 둔다.

---

## 9. Clean Architecture

### 9.1 Layer Structure (본 프로젝트)

| Layer | 책임 | 위치 |
|-------|------|------|
| **domain** | 도구명 규칙, tool_id 해석, 연결 정책 | `src/domain/mcp/`, `src/domain/tool_catalog/` |
| **application** | 워커 컴파일 흐름, 실패 격리 | `src/application/agent_builder/` |
| **infrastructure** | 도구 생성, MCP 연결·실행, 저장소 | `src/infrastructure/mcp/`, `src/infrastructure/agent_builder/`, `src/infrastructure/mcp_registry/` |
| **interfaces/api** | DI 배선 | `src/api/main.py` |

### 9.2 Dependency Rules

```
      api/main.py  (DI 배선)
            │
            ▼
   application/workflow_compiler ──▶ domain/tool_catalog/mcp_tool_id
            │                              ▲
            ▼                              │
   infrastructure/tool_factory ────────────┤
   infrastructure/mcp/tool_registry ──▶ domain/mcp/policy
   infrastructure/mcp/tool_adapter  ──▶ domain/mcp/value_objects

   규칙: domain은 어떤 상위 레이어도 참조하지 않는다.
        policy.py는 hashlib(표준 라이브러리)만 추가로 import한다.
```

### 9.3 File Import Rules

| From | Can Import | Cannot Import |
|------|-----------|---------------|
| `domain/mcp/policy.py` | 표준 라이브러리(`hashlib`, `re`) | infrastructure, application, langchain |
| `application/workflow_compiler` | domain, infrastructure 인터페이스 | api |
| `infrastructure/tool_factory` | domain, infrastructure | application |
| `api/main.py` | 전부 | — |

> **검증**: `/verify-architecture` — `domain/mcp/policy.py`에 `langchain`/`mcp` 패키지 import가 들어가면 즉시 위반.

### 9.4 This Feature's Layer Assignment

| Component | Layer | Location | 변경 |
|-----------|-------|----------|------|
| `MCPConnectionPolicy.build_tool_name` | domain | `src/domain/mcp/policy.py` | 신규 메서드 |
| `MCPConnectionPolicy.MAX_TOOL_NAME_LENGTH` | domain | 〃 | 100 → 64 |
| `parse_mcp_tool_id` / `McpToolRef` | domain | `src/domain/tool_catalog/mcp_tool_id.py` | 변경 없음 (재사용) |
| MCP 워커 실패 격리 | application | `src/application/agent_builder/workflow_compiler.py` | 수정 |
| 도구 선택 + 바인딩 로그 | infrastructure | `src/infrastructure/agent_builder/tool_factory.py` | 수정 |
| 노출명 생성 + 로드 로그 | infrastructure | `src/infrastructure/mcp/tool_registry.py` | 수정 |
| 실행 로그 `request_id` | infrastructure | `src/infrastructure/mcp/tool_adapter.py` | 수정 |
| DI 배선 | api | `src/api/main.py` | 확인 전용 (테스트로 고정) |

---

## 10. Coding Convention Reference

### 10.1 Naming Conventions

| 대상 | 규칙 | 예 |
|------|------|-----|
| 클래스 | PascalCase | `MCPConnectionPolicy` |
| 함수/메서드 | snake_case | `build_tool_name()` |
| 상수 | UPPER_SNAKE_CASE | `MAX_TOOL_NAME_LENGTH`, `_HASH_SUFFIX_LEN` |
| 모듈 파일 | snake_case.py | `tool_factory.py` |
| 테스트 파일 | `test_*.py`, 미러 경로 | `tests/domain/mcp/test_policy.py` |

### 10.2 Import Order (Python)

```python
# 1. 표준 라이브러리
import hashlib

# 2. 서드파티
from langchain_core.tools import BaseTool

# 3. 프로젝트 내부 (domain → application → infrastructure 순)
from src.domain.mcp.policy import MCPConnectionPolicy
from src.infrastructure.mcp.client_factory import MCPClientFactory
```

### 10.3 Environment Variables

신규 없음. 기존 `MCP_SECRET_KEY`(`settings.mcp_secret_key`)만 사용.

### 10.4 This Feature's Conventions

| 항목 | 적용 규칙 |
|------|-----------|
| 로깅 | `logger.info/warning/error(msg, **fields)` 구조화. `print()` 금지. 에러는 `exception=e`로 스택 트레이스 필수 (`docs/rules/logging.md` LOG-001) |
| 함수 길이 | 40줄 이내. `_create_mcp_tool`이 초과하면 도구 선택 로직을 private 헬퍼로 분리 |
| if 중첩 | 2단계 이내. 결정 트리는 early return으로 평탄화 |
| 설계 추적 | 핵심 결정부에 `# Design Ref: §N — 근거` 주석 (SC-05) |
| 타입 | 명시적 타입 힌트 (`str`, `McpToolRef`, `BaseTool`) |
| 테스트 | 구현 전 Red 확인 (`docs/rules/testing.md`) |

---

## 11. Implementation Guide

### 11.1 File Structure

```
src/
├── domain/
│   ├── mcp/policy.py                          [수정] build_tool_name 신규, 상한 64
│   └── tool_catalog/mcp_tool_id.py            [변경 없음] 재사용
├── application/
│   └── agent_builder/workflow_compiler.py     [수정] MCP 워커 실패 격리
├── infrastructure/
│   ├── mcp/
│   │   ├── tool_registry.py                   [수정] build_tool_name 사용, 로드 로그
│   │   └── tool_adapter.py                    [수정] request_id/tool_id 로그
│   └── agent_builder/tool_factory.py          [수정] 바인딩 로그, 도구 목록 에러 메시지
└── api/main.py                                [확인] DI 배선 (변경 없을 수 있음)

tests/
├── domain/mcp/test_policy.py                  [신규] U1-U5
├── infrastructure/agent_builder/test_tool_factory.py  [수정] U6-U12
├── application/agent_builder/test_workflow_compiler.py [수정] U13-U14
├── infrastructure/mcp/test_tool_adapter.py    [신규 or 수정] U15
└── api/test_runtime_tool_factory_wiring.py    [신규] I1-I3
```

### 11.2 Implementation Order

**Phase 1 — 계측·재현 (게이트)**

1. [ ] `tool_factory._create_mcp_tool`에 `MCP tool binding start` / `MCP tool bound` 로그 추가
2. [ ] `tool_registry._load_server_tools` 로그에 `tool_id`·`tool_names` 추가
3. [ ] `tool_adapter._arun`에 `request_id`/`tool_id` 전달 경로 추가 (U15 Red → Green)
4. [ ] `/verify-mcp-connections`로 대상 서버 도구 목록 확보 (M1)
5. [ ] 문제 에이전트 실행 → §2.2 결정 트리로 차단 지점 판정 (M2)
6. [ ] **Plan §1.2 결함표에 실측 결과 기록** ← 여기까지 완료 전 Phase 2 착수 금지

**Phase 2 — 결함 수정**

7. [ ] `test_policy.py` U1-U5 작성 (Red) → `build_tool_name` 구현 + 상한 64 (Green)
8. [ ] `tool_registry`가 `build_tool_name` 사용하도록 교체
9. [ ] `test_tool_factory.py` U6-U12 보강 (Red) → 도구 선택·에러 메시지 수정 (Green)
10. [ ] `test_workflow_compiler.py` U13-U14 작성 (Red) → 워커 단위 실패 격리 구현 (Green)

**Phase 3 — 회귀 가드 + 검증**

11. [ ] `test_runtime_tool_factory_wiring.py` I1-I3 작성 → 배선 확인 (필요 시 main.py 보정)
12. [ ] 전체 테스트 실행 — 기존 MCP 테스트 회귀 없음 확인 (SC-04)
13. [ ] `/verify-architecture`, `/verify-logging`, `/verify-tdd`
14. [ ] 실서버 재검증 M3, M4 (SC-01)

> **착수 전 필수** (Plan §5 High/High 리스크): `git status` 확인 → `fix/mcp-tool-call-not-reaching-server` 브랜치 생성 → 현재 MCP 배선 수정본을 첫 커밋으로 고정. Plan 수립 중 대상 3파일이 수정본↔HEAD를 두 차례 오갔다.

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | 설명 | 예상 턴 |
|--------|-----------|------|:---:|
| 계측·재현 | `module-1` | 3구간 로그 추가 + 실서버 재현으로 차단 지점 확정 (Phase 1, 1-6) | 15-20 |
| 도구명·도구선택 | `module-2` | `build_tool_name` + 도구 선택 분기 + 단위 테스트 (Phase 2, 7-9) | 25-30 |
| 실패격리·배선가드 | `module-3` | 워커 단위 격리 + DI 계약 테스트 + 최종 검증 (Phase 2-3, 10-14) | 25-30 |

#### Recommended Session Plan

| Session | Phase | Scope | 턴 |
|---------|-------|-------|:---:|
| Session 1 | Plan + Design | 전체 | 완료 |
| Session 2 | Do | `--scope module-1` | 15-20 |
| Session 3 | Do | `--scope module-2,module-3` | 45-55 |
| Session 4 | Check + Report | 전체 | 30-40 |

> `module-1`은 실서버 재현이 포함돼 사용자 개입(서버 로그 확인)이 필요하다. 독립 세션으로 분리하고, 그 결과를 Plan §1.2에 기록한 뒤 `module-2` 착수를 권장한다.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-02 | 초안 — Option C 채택, 진단 결정 트리 / 도구명 규칙 / 실패 격리 정책 확정 | 배상규 |
| 0.2 | 2026-09-02 | §6.1 E6 변경 + §6.3 신설 — module-1 실측(D1 확정) 반영, 레거시 ID의 첫-도구 폴백을 서버 도구 전체 바인딩으로 대체 | 배상규 |
