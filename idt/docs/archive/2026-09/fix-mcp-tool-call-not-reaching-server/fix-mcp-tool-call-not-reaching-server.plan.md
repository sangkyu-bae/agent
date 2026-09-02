# fix-mcp-tool-call-not-reaching-server Planning Document

> **Summary**: 에이전트가 MCP 워커 도구를 호출해도 실제 MCP 서버에 요청이 도달하지 않는 문제를, 차단 지점 계측 → 결함 수정 → 회귀 가드 순으로 해결한다.
>
> **Project**: sangplusbot / idt (FastAPI + LangGraph)
> **Author**: 배상규
> **Date**: 2026-09-02
> **Status**: Draft

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 에이전트에서 `mcp_081c6fe7-e0bd-4aad-9a42-29b8bf073167` 도구를 호출해도 MCP 서버 쪽에 요청 로그가 남지 않는다. 도구 호출이 서버까지 도달하기 전 3개 구간(도구 생성 / LLM 도구 등록 / 도구 실행) 중 어디서 끊기는지 코드상 후보가 복수라 단정할 수 없다. |
| **Solution** | (1) 세 구간에 request_id·tool_id를 실은 계측 로그를 넣어 차단 지점을 확정하고, (2) 코드 리딩으로 확인된 3개 결함(레거시 서버 단위 ID의 임의 첫-도구 바인딩 / OpenAI 64자 도구명 상한 미반영 / 런타임 DI 배선 회귀 무방비)을 수정하며, (3) 각 결함을 고정하는 회귀 테스트를 남긴다. |
| **Function/UX Effect** | Agent Builder로 MCP 도구를 붙인 워커가 의도한 도구를 실제로 호출하고, 실패 시 "어디서 끊겼는지"가 로그 한 줄로 드러난다. |
| **Core Value** | MCP 도구 연동이 "붙였는데 조용히 아무 일도 안 일어남" 상태에서 벗어나 관측 가능하고 재현 가능한 기능이 된다. |

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

### 1.1 Purpose

에이전트 실행 중 MCP 도구 호출이 실제 MCP 서버에 도달하지 않는 문제의 차단 지점을 확정하고 제거한다.

### 1.2 Background

**관측된 증상**: 실제 에이전트에서 `mcp_081c6fe7-e0bd-4aad-9a42-29b8bf073167` 도구를 호출했는데 MCP 서버 쪽에 요청이 들어오지 않았다.

**코드 경로** (현재 작업트리 기준):

```
WorkflowCompiler.compile()                       workflow_compiler.py:366
  └ parse_mcp_tool_id(tool_id) → McpToolRef
  └ ToolFactory.create_async()                   tool_factory.py:176
      └ _create_mcp_tool()                       tool_factory.py:196
          └ MCPToolLoader.load_by_tool_id()      mcp_tool_loader.py:74
              └ MCPToolRegistry.get_tools()      tool_registry.py:42   ← ① list_tools (서버 접속)
                  └ MCPToolAdapter 생성
  └ create_agent(model=llm, tools=[tool])        workflow_compiler.py:424 ← ② LLM에 도구 등록
       ... 런타임 ...
  └ MCPToolAdapter._arun()                       tool_adapter.py:51    ← ③ call_tool (서버 접속)
```

서버로 나가는 요청은 ①(도구 목록 조회)과 ③(도구 실행) 두 번뿐이다. **①의 로그(`MCP session connecting` / `MCP server tools loaded`)가 남았는지 여부만으로 "컴파일 단계에서 죽었는가 / 실행 단계에서 죽었는가"가 갈린다.** 지금은 이 판별을 위한 tool_id 단위 로그가 부족하다.

**코드 리딩으로 확인된 결함**:

| # | 결함 | 근거 | 증상 설명력 |
|---|------|------|------------|
| D1 | 레거시 서버 단위 ID `mcp_{uuid}`는 도구를 특정하지 못해 **서버의 첫 번째 도구**에 임의 바인딩된다 | `tool_factory.py:_create_mcp_tool` → `is_server_level` → `return tools[0]` | 높음 — 의도한 도구는 영원히 호출되지 않는다. 서버 로그를 도구 단위로 보고 있었다면 "요청이 안 온다"로 보인다 |
| D2 | MCP 도구명 상한이 100자(`MCPConnectionPolicy.MAX_TOOL_NAME_LENGTH`)인데 **OpenAI function name 상한은 64자**다. 도구명은 `mcp_{uuid}_{tool}` 형태로 접두부만 41자 | `policy.py:22`, `tool_registry.py:82` | 조건부 — MCP 도구명이 24자 이상이면 LLM 등록 단계에서 400. 선례 있음(`fix-tool-name-openai-validation.plan.md`) |
| D3 | 런타임 `ToolFactory`(main.py:2683)에 `mcp_tool_loader`/`mcp_repository`가 빠지면 MCP 워커가 있는 에이전트의 **compile 전체가 ValueError로 실패**하는데, 이 배선을 고정하는 테스트가 없다 | `tool_factory.py:_create_mcp_tool`의 두 가드, `test_mcp_registry_di_wiring.py`는 registry sync 전용 | 높음 — 본 계획 수립 중 실제로 이 배선이 빠진 상태의 작업트리가 관측되었다 |

### 1.2.1 Phase 1 실측 결과 (2026-09-02, module-1)

**대상 확정** — `mcp_081c6fe7-…` = **Scrap MCP** (SSE, `http://localhost:8002/sse`, `is_active=1`)

| 구간 | 측정 | 결과 |
|------|------|------|
| ① `list_tools` | `/verify-mcp-connections` + 직접 로드 | **정상** — 520ms, 도구 3개 수신 |
| 서버 노출 도구 | `MCP server tools loaded` 로그 | `scrape_url`, `scrape_urls`, `extract_structured` |
| 노출명 길이 | `exposed_name_len` | 51 / 52 / **59**자 — 전부 64 이하 |
| 워커 정의 | `agent_tool` 행 1건 | `tool_id = mcp_081c6fe7-…` (**레거시 서버 단위**), `worker_type=tool`, `tool_config=null` |
| 워커 description | 동일 행 | **3개 도구를 모두 안내** — "scrape_url … / scrape_urls … / extract_structured …" |
| 실제 바인딩 | `is_server_level` → `tools[0]` | **`scrape_url` 하나만** |
| 소속 에이전트 | `agent_definition` | "bis 비율 3개사와 하위3개사 뽑아서 분석리포트 작성" (`status=active`) |

**판정: D1 확정.** 워커의 description은 LLM에게 3개 도구를 사용 가능하다고 안내하지만, `create_agent(tools=[tool])`에는 첫 도구 `scrape_url` **하나만** 전달된다. LLM이 `scrape_urls` 또는 `extract_structured`를 호출하려 하면 그 이름의 도구가 목록에 없어 호출이 성립하지 않고, **MCP 서버에는 아무 요청도 나가지 않는다** — 관측된 증상과 일치한다.

**D2 재평가: 이 서버에서는 미발생.** 최장 노출명이 59자로 64자 상한 이하다. 다만 접두부가 41자로 고정이라 **여유가 5자뿐**이며, 도구명이 24자 이상인 MCP 서버를 등록하면 즉시 발생한다. 우선순위를 High → Medium으로 낮추되 범위에는 유지한다.

**D3 미발생 확인.** 측정 시점의 런타임 `ToolFactory`에 `mcp_tool_loader`·`mcp_repository`가 모두 주입돼 있었다. 다만 계획 수립 중 배선이 빠진 작업트리가 실제로 관측됐으므로 회귀 가드(FR-06)는 유지한다.

**남은 미확정**: LLM이 실제로 `scrape_urls`/`extract_structured`를 호출하려 했는지는 실행 트레이스로만 확증된다. 바인딩 사실만으로 3개 중 2개가 도달 불가인 것은 이미 확정이므로, 수정 착수의 근거로는 충분하다.

### 1.3 Related Documents

- 규칙: `docs/rules/tool-and-mcp.md` (도구/MCP 개발 시 필수)
- 선례: `docs/01-plan/features/fix-tool-name-openai-validation.plan.md`
- 선행 사이클: `mcp-http-call-module`, `mcp-tool-auto-sync`
- 진단 스킬: `/verify-mcp-connections`

---

## 2. Scope

### 2.1 In Scope

- [ ] **P1 계측**: 도구 생성(①) / LLM 등록(②) / 도구 실행(③) 3구간에 `request_id` + `tool_id` + `mcp_tool_name`을 실은 구조화 로그 추가
- [ ] **P1 재현**: 문제 에이전트(`mcp_081c6fe7-…`)를 실행해 차단 지점 확정 후 본 문서 §1.2 결함표에 실측 결과 기록
- [ ] **P2-D1**: 레거시 서버 단위 ID의 도구 선택 결함 수정 — 첫-도구 폴백은 유지하되 선택 사실이 드러나는 경고 경로 확보, 신규 형식(`mcp:{server}:{tool}`) 정확 바인딩 보장
- [ ] **P2-D2**: MCP 도구명 생성 규칙을 OpenAI 상한(64자)에 맞게 조정 + 충돌 없는 축약
- [ ] **P2-D3**: 런타임 `ToolFactory`의 MCP DI 배선 계약 테스트 추가
- [ ] **P3**: 위 3건 각각에 대한 회귀 테스트 (TDD: Red → Green)
- [ ] 두 tool_id 형식(`mcp:{server}:{tool}` 신규 / `mcp_{uuid}` 레거시) 동시 지원 유지

### 2.2 Out of Scope

- MCP 도구별 실제 `inputSchema` → pydantic 모델 동적 생성 (현재 모든 MCP 도구가 공통 `{arguments: dict}` 스키마를 쓰는 문제). **별도 사이클로 분리** — 연결 도달 문제와 독립
- DB에 저장된 레거시 `mcp_{uuid}` tool_id의 일괄 마이그레이션 (하위호환 유지로 대체)
- MCP 서버 등록/인증/암호화(`mcp_registry`) 로직 변경
- 프론트엔드 변경 (API 계약 변화 없음)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 도구 생성(①)·LLM 등록(②)·도구 실행(③) 각 구간에서 `request_id`/`tool_id`/`mcp_tool_name`이 포함된 로그가 남는다 | High | Pending |
| FR-02 | 문제 에이전트 재현으로 차단 구간이 ①/②/③ 중 하나로 확정된다 | High | Pending |
| FR-03 | `mcp:{server_id}:{tool_name}` 형식은 서버의 해당 도구에 **정확히** 바인딩된다 | High | Pending |
| FR-04 | 레거시 `mcp_{uuid}` 형식은 첫 도구로 폴백하되, 어떤 도구가 선택됐고 후보가 몇 개였는지 경고 로그로 남는다 | High | Pending |
| FR-05 | LLM에 노출되는 MCP 도구명이 64자를 넘지 않고, 같은 서버 내 도구 간 이름 충돌이 없다 | High | Pending |
| FR-06 | 런타임 `ToolFactory`에 `mcp_tool_loader`/`mcp_repository`가 주입되어 있음을 테스트가 고정한다 | High | Pending |
| FR-07 | MCP 도구 생성 실패 시 compile 전체를 죽이지 않고, 해당 워커의 실패 사유가 로그로 식별 가능하다 | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 관측성 | 실패 시 스택 트레이스 + `request_id` 포함 (`docs/rules/logging.md` LOG-001) | `/verify-logging` |
| 아키텍처 | domain → infrastructure 역참조 없음, 도구명 규칙은 domain policy에 유지 | `/verify-architecture` |
| 테스트 | 신규/변경 모듈에 테스트 선행 (Red 확인 후 구현) | `/verify-tdd`, pytest |
| 하위호환 | 기존 레거시 tool_id 에이전트가 계속 동작 | 회귀 테스트 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] SC-01 — 문제 에이전트 실행 시 MCP 서버 측에 **지정한 도구**의 요청이 실제로 수신된다 (서버 로그로 확인)
- [ ] SC-02 — 차단 지점이 로그로 특정 가능하다: ① 실패면 `MCP session connecting` 부재, ③ 실패면 `MCP tool execution started` 이후 예외
- [ ] SC-03 — FR-03/FR-04/FR-05/FR-06 각각에 대응하는 테스트가 존재하고 통과한다
- [ ] SC-04 — 기존 MCP 관련 테스트(`test_tool_factory.py`, `test_workflow_compiler.py::test_mcp_tool_uses_create_async`)가 모두 통과한다
- [ ] SC-05 — Design 문서의 결정 사항이 코드 주석(`# Design Ref: §N`)으로 역추적 가능하다

### 4.2 Quality Criteria

- [ ] `/verify-architecture`, `/verify-logging`, `/verify-tdd` 통과
- [ ] 함수 40줄 / if 중첩 2단계 규칙 준수
- [ ] `print()` 미사용, 모든 에러 경로에 스택 트레이스

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **실제 차단 지점이 D1~D3 어디도 아님** — 추정 수정 후 증상 잔존 | High | Medium | Phase 1 계측·재현을 Phase 2의 **선행 게이트**로 둔다. 계측 결과가 나오기 전에는 수정 착수 금지 |
| **작업트리 상태 불안정** — 본 계획 수립 중 `tool_factory.py`/`workflow_compiler.py`/`main.py`가 수정본↔HEAD 사이를 두 차례 오갔다 | High | High | 착수 직전 `git status` + 대상 3파일 해시 기록, 작업 브랜치 분리(`fix/mcp-tool-call-not-reaching-server`), 첫 커밋으로 현재 수정본을 고정 |
| 도구명 축약으로 기존 관측 기록(`ai_tool_call.tool_name`)과 이름이 달라짐 | Medium | Medium | 축약 규칙을 결정적(deterministic)으로 두고, Design에서 기존 기록과의 대조 방법을 명시 |
| 레거시 첫-도구 폴백을 제거하면 기존 에이전트가 깨짐 | High | Low | 폴백 유지 + 경고. 제거는 Out of Scope |
| MCP 서버가 외부 SaaS(Smithery 등)라 재현 시 rate limit/인증 문제 | Medium | Medium | `/verify-mcp-connections`로 연결만 먼저 분리 검증 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `src/infrastructure/agent_builder/tool_factory.py` | Infrastructure | `_create_mcp_tool` 도구 선택/경고 경로 보강 |
| `src/infrastructure/mcp/tool_registry.py` | Infrastructure | 도구명 생성 시 길이 규칙 적용, 로드 로그에 tool_id 추가 |
| `src/infrastructure/mcp/tool_adapter.py` | Infrastructure | 실행 로그에 `request_id` 전달 경로 추가 |
| `src/domain/mcp/policy.py` | Domain | `MAX_TOOL_NAME_LENGTH` 정책 조정(100 → OpenAI 상한 정합) + 충돌 회피 규칙 |
| `src/application/agent_builder/workflow_compiler.py` | Application | MCP 워커 도구 생성 실패 처리(FR-07) |
| `src/api/main.py` | DI wiring | 런타임 `ToolFactory` MCP 배선 유지 확인 (변경 없을 수 있음, 테스트로 고정) |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `ToolFactory.create_async` | 도구 생성 | `workflow_compiler.py:367` (에이전트 실행) | Needs verification |
| `ToolFactory.create_async` | 도구 생성 | `run_middleware_agent_use_case.py:44` (미들웨어 에이전트, 저장소 미전달) | Needs verification — 주입된 기본 repository로 폴백되는지 확인 |
| `MCPToolLoader.load_by_tool_id` | 도구 로드 | `tool_factory._create_mcp_tool` | Needs verification |
| `MCPToolLoader.load` | 도구 로드 | `DocumentConversionAdapter` (main.py:2696), 문서 변환 경로 | Needs verification — 도구명 규칙 변경 시 영향 |
| `MCPConnectionPolicy.sanitize_tool_name` | 도구명 정규화 | `tool_registry.py:82` | Breaking 가능 — 축약 규칙 변경 시 노출 이름 변동 |
| `mcp:{srv}:{tool}` tool_id 발급 | 카탈로그 동기화 | `sync_mcp_tools_use_case.py:51` | None — 형식 유지 |
| 저장된 에이전트의 `worker.tool_id` | DB 읽기 | `agent_definition_repository` → `WorkflowCompiler` | None — 두 형식 모두 지원 유지 |

### 6.3 Verification

- [ ] 위 소비자 전부가 변경 후에도 동작함을 테스트/실행으로 확인
- [ ] 미들웨어 에이전트 경로(`run_middleware_agent_use_case`)가 MCP tool_id로도 동작하는지 확인
- [ ] 문서 변환(`DocumentConversionAdapter`)의 MCP 도구 조회가 도구명 규칙 변경에 영향받지 않는지 확인

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Selected |
|-------|-----------------|:--------:|
| Starter | 단순 구조 | ☐ |
| Dynamic | 기능 모듈 + BaaS | ☐ |
| **Enterprise** | 레이어 분리 + DI (본 프로젝트: Thin DDD) | ☑ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| tool_id 형식 지원 | 레거시만 / 신규만+마이그레이션 / **둘 다** | 둘 다 | 카탈로그는 이미 `mcp:{srv}:{tool}`을 발급하고 DB에는 레거시 `mcp_{uuid}` 에이전트가 남아 있다. 마이그레이션 실패 시 기존 에이전트 전멸 위험 회피 |
| inputSchema 노출 | 이번 포함 / **별도 사이클** | 별도 사이클 | "요청이 서버에 도달한다"와 "올바른 인수를 넘긴다"는 독립 문제. 범위·리스크 분리 |
| 도구명 규칙 위치 | infrastructure / **domain policy** | domain policy | 이름 규칙은 외부 의존 없는 순수 규칙 — 기존 `MCPConnectionPolicy` 유지 |
| 실패 처리 | compile 전체 실패 / **워커 단위 실패 격리** | 워커 단위 (FR-07) | MCP 서버 1개 장애가 에이전트 전체를 죽이지 않도록. `tool_registry`의 서버 단위 격리와 동일 철학 |
| 진단 방식 | 추정 후 수정 / **계측 후 수정** | 계측 후 수정 | 후보 결함이 3개이고 증상 설명력이 갈린다 |

### 7.3 Clean Architecture Approach

```
domain/mcp/policy.py                  ← 도구명 규칙 (순수)
domain/tool_catalog/mcp_tool_id.py    ← tool_id 파싱 (순수, 단일 해석 지점)
        ↑
application/agent_builder/workflow_compiler.py   ← 흐름 제어 · 실패 격리
        ↑
infrastructure/agent_builder/tool_factory.py     ← 도구 선택
infrastructure/mcp/{tool_registry,tool_adapter,client_factory}.py  ← 연결·실행
        ↑
api/main.py                           ← DI 배선 (테스트로 고정)
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `idt/CLAUDE.md` — 레이어 책임, 금지 사항
- [x] `docs/rules/tool-and-mcp.md` — 도구/MCP 개발 규칙 (**착수 전 필독**)
- [x] `docs/rules/logging.md` — LOG-001
- [x] `docs/rules/testing.md` — TDD 절차

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| MCP 도구 노출명 | `{server_tool_id}_{mcp_tool}` 소문자, 100자 컷 | OpenAI 64자 상한 정합 + 충돌 회피 축약 규칙 | High |
| MCP 실패 로그 필드 | `server`/`tool`만 존재 | `request_id`·`tool_id`·`mcp_tool_name` 필수화 | High |
| DI 배선 계약 | registry sync만 테스트 | 런타임 ToolFactory MCP 배선 테스트 | High |

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| `MCP_SECRET_KEY` | MCP 인증정보 암복호화 (`settings.mcp_secret_key`) | Server | 기존 |

신규 환경변수 없음.

---

## 9. Next Steps

1. [ ] **착수 전**: `git status`로 대상 3파일 상태 고정, 작업 브랜치 생성 (§5 리스크 대응)
2. [ ] `docs/rules/tool-and-mcp.md` 정독
3. [ ] Design 문서 작성 — `/pdca design fix-mcp-tool-call-not-reaching-server`
4. [ ] Phase 1(계측·재현) 실행 후 §1.2 결함표에 실측 결과 반영
5. [ ] Phase 2/3 구현 — `/pdca do`
6. [ ] Gap 분석 — `/pdca analyze`

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-02 | 초안 — 코드 리딩 기반 결함 후보 3건(D1~D3) 및 계측 선행 전략 정의 | 배상규 |
