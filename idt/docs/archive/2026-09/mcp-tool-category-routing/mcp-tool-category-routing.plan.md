# mcp-tool-category-routing Planning Document

> **Summary**: MCP 도구에 카테고리를 부여해 수집형 도구는 단일샷 collect 노드로 라우팅하고, 미분류 도구의 react 루프에는 호출 상한을 둔다.
>
> **Project**: sangplusbot (idt)
> **Version**: —
> **Author**: 배상규
> **Date**: 2026-09-03
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | MCP 도구는 `_resolve_category()`에서 예외 없이 `"action"`으로 떨어져 전부 `create_agent` react 분기를 탄다. 결과적으로 스크랩 도구 1회 요청에 도구가 4~5회 호출되고, 산출물이 "수집한 근거"가 아니라 워커 LLM의 자체 분석문으로 나와 하류 analysis/final_answer 노드가 근거로 인식하지 못한다. |
| **Solution** | ① `tool_catalog`에 `category`·`max_tool_calls` 컬럼을 추가해 도구 단위로 분류를 저장한다. ② 수집형(`collect`)은 react 루프 없는 **단일샷 collect 노드**로 실행해 도구를 1회만 호출하고 결과를 기존 `[worker_id 검색결과]` 규약으로 반환한다. ③ 미분류 도구는 현행 react 경로를 유지하되 워커 1회 실행당 tool-call 상한(기본 2회)과 supervisor 재라우팅 상한을 둔다. |
| **Function/UX Effect** | 스크랩 요청의 MCP 호출 4~5회 → 1회. 워커 산출물이 근거 블록으로 표준화되어 분석·차트·문서생성 하류 노드가 정상 소비. 응답 지연·토큰 비용 감소. |
| **Core Value** | "노드 종류를 도구 자체의 성질로 결정한다" — 특화 로직을 코어에 하드코딩하지 않고 **데이터(카테고리)로 라우팅**한다. USER-SCENARIOS의 "특화는 데이터로" 원칙과 정합. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | MCP 도구가 구조적으로 분류 불가 → 전부 react 루프 → 중복 호출 + 근거/분석 경계 붕괴 |
| **WHO** | P2 (KB 운영자 / 에이전트 소유자) — MCP 도구를 붙여 에이전트를 만드는 사람. 및 도구 카탈로그 관리자 |
| **RISK** | 기존 저장 에이전트의 동작 변화(회귀). → category NULL = 현행과 100% 동일 경로로 방어 |
| **SUCCESS** | 스크랩 MCP 워커 1회 실행당 MCP 호출 1회, 산출물이 `is_search_result()` 판정 통과, 기존 에이전트 회귀 0건 |
| **SCOPE** | M1 스키마·카탈로그 / M2 collect 노드 / M3 컴파일러 라우팅·상한 / M4 Admin UI |

---

## 1. Overview

### 1.1 Purpose

MCP 도구를 실행할 노드 종류를 **도구의 성질(카테고리)** 로 결정하게 만든다.
현재는 내부 도구만 `TOOL_REGISTRY`에 카테고리를 갖고, MCP 도구는 전부 기본값 `action`으로 떨어져 단일 경로(react)로만 실행된다.

### 1.2 Background

**근거 코드**

| 사실 | 위치 |
|------|------|
| 카테고리 해석: DB 오버라이드 → `TOOL_REGISTRY` → `"action"` | `src/application/agent_builder/workflow_compiler.py:843-851` |
| `TOOL_REGISTRY`에는 내부 도구만 등재 (MCP tool_id는 항상 `ValueError`) | `src/domain/agent_builder/tool_registry.py` |
| MCP 워커 생성 시 `category`를 채우지 않음 | `src/application/agent_builder/create_agent_use_case.py:355-361` |
| `category == "search"` 분기 / 그 외 `create_agent` react 분기 | `workflow_compiler.py:517-579` |
| 레거시 `mcp_{server}` 워커는 서버 도구 **전체**를 한 워커에 바인딩 | `src/infrastructure/agent_builder/tool_factory.py:225-233` |
| search 노드는 `tool.ainvoke({"query": ...})` 로 인자 키가 하드코딩 | `src/application/agent_builder/search_pipeline.py:242` |
| 근거 메시지 규약 `[worker_id 검색결과]` 단일 출처 | `search_pipeline.py:40-56` |
| `agent_tool.category` 컬럼은 이미 존재(NULL) | `db/migration/V019__add_agent_tool_category.sql` |
| `is_builtin`은 "관리자 토글, sync 보존" 선례 | `src/domain/tool_catalog/entity.py:17` |

**두 증상의 인과**

1. **중복 호출** — react 루프에는 워커 단위 tool-call 예산이 없다. 게다가 서버 단위 워커는 도구 전체를 쥐고 있어 LLM이 추가 호출할 여지가 넓다.
2. **분석 혼입** — react 워커의 최종 산출은 LLM 종합문이다. search 노드처럼 `[… 검색결과]` 규약을 따르지 않으므로 `is_search_result()`가 false → analysis / final_answer 노드가 이를 "근거"가 아닌 일반 메시지로 취급한다.

**"스크랩 = search" 가 아닌 이유**

search 노드는 `rewrite(질문→검색어) → search → validate → compress` 파이프라인이다. 스크랩 도구에 필요한 것은 재작성된 검색어가 아니라 **맥락에서 확정된 URL**이며, rewrite 단계는 오히려 `ToolArgumentPolicy`가 막고 있는 URL 환각을 유발하는 방향으로 작동한다. 따라서 search 재사용이 아니라 **collect 라는 별도 분류·별도 노드**로 간다.

### 1.3 Related Documents

- 규칙: `idt/docs/rules/tool-and-mcp.md` (도구·MCP 개발 시 필수)
- 선행 사이클: `worker-context-injection` (§3.2 `ToolArgumentPolicy`, §6.2 차단 관측)
- 선행 사이클: `fix-mcp-tool-call-not-reaching-server` (§6.1 E6 서버 단위 전체 바인딩, §6.2 워커 격리)
- 선행 사이클: `search-node-query-pipeline` (§2-2 파이프라인, D2 메시지 규약 단일 출처)

---

## 2. Scope

### 2.1 In Scope

- [ ] M1. `tool_catalog`에 `category`(NULL 허용), `max_tool_calls`(NULL 허용) 컬럼 추가 — Flyway V069 + SQLAlchemy 모델 + 엔티티 + 리포지토리
- [ ] M1. MCP/내부 도구 sync 시 `category`·`max_tool_calls`를 **덮어쓰지 않고 보존** (`is_builtin` 선례 준수)
- [ ] M2. 단일샷 `collect` 노드 신설 — 도구 `args_schema` 기반 structured output 1회로 인자 생성 → `ToolArgumentPolicy` 검증 → 도구 1회 호출 → 길이 임계치 초과 시에만 압축 → `[worker_id 검색결과]` 반환
- [ ] M3. `_resolve_category()`가 `tool_catalog.category`를 조회 경로에 포함 (우선순위: `agent_tool.category` → `tool_catalog.category` → `TOOL_REGISTRY` → `"action"`)
- [ ] M3. `category == "collect"` 분기를 컴파일러에 추가
- [ ] M3. 미분류 react 경로에 워커 1회 실행당 tool-call 상한(기본 2회, `tool_catalog.max_tool_calls`로 오버라이드) 미들웨어 도입
- [ ] M3. supervisor의 동일 워커 재라우팅 상한 도입 (`search`/`collect` 워커는 런당 기본 1회)
- [ ] M4. `AdminToolsPage`에서 도구별 카테고리·호출 상한 조회/수정 UI + API 계약 동기화(`idt_front/src/types`, `services`, `hooks`, `constants/api.ts`)
- [ ] 회귀 검증: 기존 저장 에이전트(category NULL) 경로가 변경 전과 동일함을 테스트로 고정

### 2.2 Out of Scope

- MCP 동기화 시 카테고리 **자동 추론**(휴리스틱·LLM 분류) — 이번엔 전부 NULL, 관리자가 지정
- 마이그레이션으로 특정 스크랩 도구를 collect로 백필하는 것
- `generate` 카테고리 도입 및 `document_generator`/`excel_export` 등 tool_id 하드코딩 분기(`workflow_compiler.py:399-445`)의 카테고리 기반 리팩토링
- `search_pipeline`의 `{"query": ...}` 하드코딩 일반화 (collect 노드가 별도 경로이므로 불필요)
- deep_search 모드 및 sub_agent 워커 경로

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `tool_catalog`에 `category` VARCHAR(20) NULL, `max_tool_calls` INT NULL 컬럼을 추가하고 전 컬럼 COMMENT를 작성한다 | High | Pending |
| FR-02 | 카테고리 허용값은 `search` / `collect` / `analysis` / `action` 4종이며, 그 외 값은 저장 시점에 도메인 정책이 거부한다 | High | Pending |
| FR-03 | 내부·MCP 도구 sync는 기존 `category`·`max_tool_calls`를 덮어쓰지 않는다 | High | Pending |
| FR-04 | `_resolve_category()`는 `agent_tool.category` → `tool_catalog.category` → `TOOL_REGISTRY` → `"action"` 순으로 해석한다 | High | Pending |
| FR-05 | `category == "collect"` 워커는 react 루프 없이 도구를 **정확히 1회** 호출하는 collect 노드로 컴파일된다 | High | Pending |
| FR-06 | collect 노드는 도구 `args_schema`를 LLM에 제시해 structured output으로 인자를 1회 산출하고, `ToolArgumentPolicy.find_placeholder()` 통과 시에만 호출한다 | High | Pending |
| FR-07 | 인자 생성 실패 또는 플레이스홀더 차단 시, collect 노드는 예외 없이 "근거 부족" 취지의 메시지를 규약 형태로 남기고 그래프를 계속한다 | High | Pending |
| FR-08 | collect 노드 산출은 `format_search_result()` 규약을 따라 `is_search_result()` 판정을 통과한다 | High | Pending |
| FR-09 | collect 결과는 길이가 임계치를 초과할 때만 LLM 압축을 1회 수행하고, 이하이면 원본을 그대로 전달한다 | Medium | Pending |
| FR-10 | 미분류(react) 워커는 1회 실행당 tool-call을 기본 2회로 제한하며, `tool_catalog.max_tool_calls`가 있으면 그 값을 쓴다 | High | Pending |
| FR-11 | supervisor는 동일 **collect** 워커를 런당 1회만 라우팅한다 (Design D-12에서 search 제외로 개정 — FR-14 취지 보존) | Medium | Pending |
| FR-12 | 상한 도달·차단은 run step / 로그에 관측 가능한 형태로 기록된다 | Medium | Pending |
| FR-13 | `AdminToolsPage`에서 도구별 category·max_tool_calls를 조회·수정할 수 있다 | Medium | Pending |
| FR-14 | `category`가 NULL인 도구는 이 사이클 이전과 완전히 동일한 경로로 컴파일·실행된다 | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 정확성 | 스크랩 MCP 워커 1회 실행당 MCP 서버 호출 1회 | run step 기록 / MCP 어댑터 호출 카운트 |
| 호환성 | category NULL 에이전트 회귀 0건 | 기존 `tests/application/agent_builder/` 전량 통과 |
| 성능 | collect 경로 LLM 호출 ≤ 2회(인자 생성 1 + 조건부 압축 1) | 단위 테스트에서 fake LLM 호출 횟수 assert |
| 아키텍처 | domain → infrastructure 참조 없음, 노드에 비즈니스 규칙 미포함 | `/verify-architecture` |
| 로깅 | 차단·상한·실패 시 스택 트레이스 포함 구조화 로그 | `/verify-logging` |
| DDL | 테이블·전 컬럼 COMMENT 필수 | `tests/db/test_migration_ddl_comments.py` |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01 ~ FR-14 전부 구현
- [ ] TDD 준수 — 각 모듈 테스트 선작성 → Red 확인 → 구현 → Green
- [ ] 스크랩 MCP 도구를 `collect`로 지정한 에이전트에서 실제 호출 1회를 실측
- [ ] `category` NULL 에이전트의 기존 테스트 전량 통과
- [ ] API 계약 동기화 완료 (`idt/src/interfaces/schemas` ↔ `idt_front/src/types`)
- [ ] `/verify-architecture`, `/verify-logging`, `/verify-tdd` 통과

### 4.2 Quality Criteria

- [ ] 신규 모듈 함수 40줄 이하, if 중첩 2단계 이하
- [ ] lint 에러 0
- [ ] `pytest` 전량 통과
- [ ] 프론트 `npm run test` 통과

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 기존 에이전트 동작 변화(회귀) | High | Low | `category` NULL을 "미분류=현행 유지"로 정의(FR-14). 백필 마이그레이션 없음. NULL 경로 회귀 테스트를 명시적으로 고정 |
| react tool-call 상한이 멀티스텝 MCP(검색→상세조회 체인)를 끊음 | Medium | Medium | 기본 2회로 1차 교정 여지 확보. `tool_catalog.max_tool_calls`로 도구별 상향 가능(FR-10) |
| MCP 도구 `args_schema`가 없거나 빈약해 structured output 인자 생성이 실패 | Medium | Medium | FR-07 — 예외 대신 근거 부족 메시지로 graceful degrade. 스키마 부재 도구는 collect 지정을 권장하지 않음을 UI에 안내 |
| 서버 단위 레거시 워커(`mcp_{server}`)를 collect로 지정 — 도구가 여러 개라 "1회 호출" 정의가 모호 | Medium | Low | collect는 **단일 도구 워커**(`mcp:{srv}:{tool}`)에만 허용. 서버 단위 워커는 category 지정을 거부하고 react 유지 |
| supervisor 재라우팅 상한이 정당한 재시도(quality_gate 피드백 재검색)를 막음 | Medium | Medium | quality_gate 재시도 경로는 상한 계산에서 제외. 상한 도달 시 종료가 아니라 다음 단계 진행으로 처리(FR-11) |
| `tool_catalog` 조회가 컴파일 경로에 추가되어 지연 증가 | Low | Low | 컴파일 1회당 카탈로그를 배치 조회해 워커별 N+1을 만들지 않는다 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `tool_catalog` 테이블 | DB Model | `category`, `max_tool_calls` 컬럼 추가 (V069, NULL 허용, COMMENT 포함) |
| `ToolCatalogEntry` | Domain Entity | `category: str \| None`, `max_tool_calls: int \| None` 필드 추가 |
| `ToolCatalogRepositoryInterface` / 구현체 | Infrastructure | `upsert_by_tool_id`의 보존 규칙 확장, 카테고리 갱신 메서드 추가 |
| `SyncMcpToolsUseCase` / `SyncInternalToolsUseCase` | Application | sync 시 category·max_tool_calls 보존 |
| `WorkflowCompiler._resolve_category` | Application | 카탈로그 조회 단계 추가 |
| `WorkflowCompiler.compile` | Application | `collect` 분기 추가, react 분기에 상한 미들웨어 주입 |
| `supervisor_nodes` / `SupervisorState` | Application | 워커별 실행 횟수 카운터 및 상한 판정 |
| 신규 `collect_pipeline.py` | Application | 단일샷 collect 노드 팩토리 |
| `GET/PATCH /tool-catalog` | API | 응답에 category·max_tool_calls 추가, 수정 엔드포인트 |
| `AdminToolsPage`, `useToolCatalog`, `types`, `constants/api.ts` | Frontend | 카테고리·상한 표시·수정 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `tool_catalog` | READ | `ListToolCatalogUseCase` → `GET /tool-catalog` → `useToolCatalog` → `ToolPickerModal` / `AdminToolsPage` / `ToolsStep` | 필드 **추가**만 — 기존 소비자 무영향 (Needs verification: 프론트 타입 동기화) |
| `tool_catalog` | READ | `CreateAgentUseCase._build_builtin_workers` → `list_builtin()` | None (is_builtin 필터 불변) |
| `tool_catalog` | UPSERT | `SyncMcpToolsUseCase`, `SyncInternalToolsUseCase` | **Breaking 위험** — 보존 로직 미적용 시 관리자 지정 카테고리가 sync마다 초기화됨. FR-03로 방어 |
| `tool_catalog` | UPDATE | `SetBuiltinUseCase` | None (다른 컬럼) |
| `_resolve_category()` | READ | `compile()` 워커 루프(`:450`), docgen guidance(`:1467`), analysis 워커 집계(`:1471`) | Needs verification — 반환값 집합에 `collect`가 추가되므로 세 호출부 모두 재확인 |
| `create_agent` react 분기 | 실행 | 모든 미분류 도구 워커 (MCP 전체 + wiki 외 내부 도구) | Needs verification — tool-call 상한이 wiki_read 폴더 모드 체인(지도→list→read, 최소 2회)을 끊지 않는지 확인 필요 |
| `[worker_id 검색결과]` 규약 | READ | `is_search_result()` → `analysis_node`, `final_answer_node`, `quality_gate` | None — collect가 같은 규약을 재사용하므로 하류 수정 불필요 |
| `SupervisorState` | R/W | `supervisor_nodes`, `supervisor_hooks`, `workflow_compiler`, sub_agent 컴파일 | Needs verification — 카운터 필드 추가가 sub_agent(depth≥1) 상태 전파에 영향 없는지 |
| `agent_tool.category` | READ | `agent_definition_repository.py:378` → `WorkerDefinition.category` | None (우선순위 최상위 유지) |

### 6.3 Verification

- [ ] 위 소비자 전부가 제안 변경과 동작함을 확인
- [ ] sync 재실행 후 관리자 지정 category가 보존됨을 테스트로 고정
- [ ] `wiki_read` 폴더 모드(2회 호출 체인)가 기본 상한 2회 안에서 완결됨을 확인
- [ ] 필드 추가가 기존 프론트 쿼리·타입을 깨지 않음

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | 단순 구조 | 정적 사이트 | ☐ |
| **Dynamic** | 기능 모듈 + BaaS | 백엔드 있는 웹앱 | ☐ |
| **Enterprise** | 엄격한 레이어 분리, DI | 복잡한 아키텍처 | ☑ |

기존 Thin DDD(domain / application / infrastructure / interfaces) 구조를 그대로 따른다.

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 분류 저장소 | tool_catalog 컬럼 / agent_tool.category / 컴파일 시 휴리스틱 / LLM 분류 | **tool_catalog 컬럼** | 도구 단위로 한 번만 정리하면 모든 에이전트에 적용. agent_tool.category는 에이전트별 오버라이드로 존치 |
| 초기값 | 전부 NULL / 이름 휴리스틱 / 스키마 추론 | **전부 NULL** | NULL=현행 경로 → 회귀 위험 최소. 동작 변화는 관리자가 켠 도구에서만 발생 |
| 수집형 실행 노드 | 신규 단일샷 collect / search 노드 재사용 / react+상한 | **신규 단일샷 collect 노드** | search 노드는 `{"query":...}` 하드코딩 + rewrite 전제라 스크랩에 부적합. 별도 노드가 예외 분기보다 단순 |
| collect 인자 생성 | args_schema structured output / react 1턴 / tool_config 템플릿 | **args_schema structured output 1회** | 도구 스키마에 무관한 범용성 확보. 산출이 LLM 종합문이 아니라 도구 원본이라 "분석 혼입"이 구조적으로 불가 |
| collect 산출 규약 | 기존 `[… 검색결과]` 재사용 / 신규 `[… 수집결과]` | **기존 규약 재사용** | 하류 predicate 3곳(analysis / final_answer / quality_gate) 수정 불필요 |
| 압축 | 임계치 초과 시만 / 항상 / 없음 | **임계치 초과 시만** | 짧은 수집물은 무손실 보존, 긴 스크랩 본문만 비용 지불 |
| react 호출 상한 | 1회 / 2회+도구별 설정 / 3~5회 / 없음 | **기본 2회 + max_tool_calls** | 1차 호출 실패 시 `ToolArgumentPolicy` 차단 메시지로 자가교정하는 현행 설계와 정합 |
| 재라우팅 억제 | 워커별 실행 상한 도입 / react 상한만 | **워커별 실행 상한도 도입** | 4~5회의 원인이 react 루프인지 supervisor 재라우팅인지 확정 전이므로 양쪽 모두 봉쇄 |
| 카테고리 값 집합 | 4종 / 5종(+generate) / 자유문자열 | **search·collect·analysis·action 4종** | generate 도입은 tool_id 하드코딩 분기 리팩토링을 동반 — 범위 밖 |

### 7.3 Clean Architecture Approach

```
domain/
  tool_catalog/entity.py          ToolCatalogEntry + category/max_tool_calls
  tool_catalog/policies.py        ToolCategoryPolicy (허용값·collect 가능 여부 판정)
  mcp/tool_argument_policy.py     (기존) 플레이스홀더 차단 — collect 노드가 재사용
  agent_builder/policies.py       ToolCallBudgetPolicy (상한 기본값·해석 규칙)
application/
  agent_builder/collect_pipeline.py   신규 단일샷 collect 노드 팩토리
  agent_builder/workflow_compiler.py  category 해석 + collect 분기 + 상한 주입
  agent_builder/supervisor_nodes.py   워커 실행 횟수 상한 판정
  tool_catalog/*_use_case.py          sync 보존 + 카테고리 수정 유스케이스
infrastructure/
  tool_catalog/models.py, tool_catalog_repository.py
interfaces/
  schemas + router (GET/PATCH /tool-catalog)
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md` 코딩 컨벤션 (루트 + `idt/`)
- [x] `idt/docs/rules/tool-and-mcp.md` — 도구·MCP 변경 시 필수 확인
- [x] `idt/docs/rules/db-session.md` — Repository 내부 commit/rollback 금지
- [x] `idt/docs/rules/logging.md` — print 금지, 스택 트레이스 필수
- [x] `idt/docs/rules/testing.md` — TDD Red→Green→Refactor
- [x] `tests/db/test_migration_ddl_comments.py` — V054 이후 DDL COMMENT 검사

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| 카테고리 값 | 문자열 관례(`search`/`analysis`)만 존재, 검증 없음 | `ToolCategoryPolicy` 허용값 상수 + 검증 | High |
| 노드 팩토리 시그니처 | search / deep_search 두 팩토리가 동일 계약(AD-1) | collect 노드도 동일 계약을 따를지 확정 | High |
| sync 보존 필드 | `is_builtin`만 관례적으로 보존 | 보존 필드 목록을 한 곳에 명시 | Medium |
| 상한 관측 로그 키 | 미정 | run step / 로그 필드명 통일 | Medium |

### 8.3 Environment Variables Needed

신규 환경변수 없음. 상한 기본값은 도메인 정책 상수로 둔다(하드코딩 금지 규칙에 따라 config 값이 아닌 도메인 규칙으로 취급).

### 8.4 Pipeline Integration

9-phase Development Pipeline 미사용. PDCA 단독 사이클.

---

## 9. Next Steps

1. [ ] `/pdca design mcp-tool-category-routing` — 3가지 아키텍처 안 비교 후 선택
2. [ ] Design §11.3 Session Guide에서 M1~M4 모듈 분할 확정
3. [ ] `/pdca do mcp-tool-category-routing --scope module-1` 부터 TDD 착수
4. [ ] (설계 중 확인) 실제 런 step 기록으로 4~5회 호출의 react/재라우팅 비율 실측 — 상한 기본값 검증

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-03 | 최초 초안 (사용자 확인 3라운드 반영) | 배상규 |
