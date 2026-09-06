# fix-mcp-search-node-routing Planning Document

> **Summary**: MCP 도구가 `search`/`collect`로 분류돼 있어도 react 워커를 타는 두 가지 원인(레거시 서버 단위 워커, search 노드의 MCP 호출 규약 누락)을 제거한다.
>
> **Project**: sangplusbot (idt — FastAPI + LangGraph)
> **Version**: —
> **Author**: 배상규
> **Date**: 2026-09-04
> **Status**: Draft

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | MCP 도구를 쓰는 에이전트가 `search`/`collect` 분류를 무시하고 항상 react 워커(model→tools→model 루프)를 탄다. 실행 트레이스(`samples/tool_call.png`)에서 `mcp_081c6fe7-…_worker`가 react 루프로 `scrape_url`을 호출하는 것이 확인됐다. |
| **Solution** | ① 레거시 서버 단위 워커(`mcp_{server}`)를 개별 도구 워커(`mcp:{srv}:{tool}`)로 Flyway DML 마이그레이션해 카탈로그 category가 도달하게 한다. ② search 노드의 도구 호출을 MCP 어댑터 계약(`{"arguments": {...}}`)과 실제 입력 스키마 기반으로 일반화한다. ③ 분류 지정 시점에 검색어 파라미터 해석 가능 여부를 검증해 조용한 실패를 차단한다. |
| **Function/UX Effect** | 수집형 MCP 도구는 단일샷 collect 노드로 1회만 호출돼 반복 호출·토큰 낭비가 사라지고, 검색형 MCP 도구는 rewrite→search→validate→compress 파이프라인의 품질 검증을 받는다. |
| **Core Value** | `mcp-tool-category-routing` 사이클이 만든 분류 라우팅이 **실제 운영 에이전트에 처음으로 도달**한다. 지금은 코드만 있고 경로가 닿지 않는 상태다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 도구 분류(search/collect)가 MCP 워커에 도달하지 못해 라우팅이 무력화돼 있다 (Gap-06/07의 잔여분) |
| **WHO** | P2 — KB 운영자/에이전트 소유자. MCP 서버를 붙여 에이전트를 운영하는 사용자 |
| **RISK** | 운영 중인 에이전트 1건(`df9d0fd2-…`)의 워커 구성을 DB에서 바꾼다 — 잘못되면 해당 에이전트가 도구를 잃는다 |
| **SUCCESS** | 단위 테스트로 "tool_id → 생성되는 노드 종류"를 고정. 레거시/개별 도구/스키마 미상 3케이스 모두 검증 |
| **SCOPE** | module-1 마이그레이션 · module-2 search 노드 호출 규약 · module-3 지정 시점 검증 |

---

## 1. Overview

### 1.1 Purpose

MCP 도구의 `category`가 워커 노드 종류를 실제로 결정하게 만든다. 현재는 분류값이 있어도 무시되거나(레거시 워커), 반영돼도 호출이 깨진다(search 노드).

### 1.2 Background

`mcp-tool-category-routing` 사이클(2026-09-03 아카이브)에서 카탈로그 기반 분류 라우팅을 구현했고, 그 Act 단계 실측에서 두 건이 발견돼 **당시 "현 상태 수용"으로 남겨졌다**:

- **Gap-07 (Important)** — 운영 에이전트가 레거시 `mcp_{server}` 워커를 쓴다. 카탈로그 키(`mcp:{srv}:{tool}`)와 매칭되지 않아 `_resolve_category`가 `"action"`으로 폴백하고 react 경로가 유지된다. 당시 결정은 "react 호출 상한 2회 적용으로 충분, 재구성은 사용자 판단 영역".
- **Gap-06 (Critical, 조치됨)** — 스크랩 도구 3종이 `category='search'`로 설정돼 있어 `_safe_search`의 `{"query": …}` 호출과 어긋났다. 세 도구를 `collect`로 바꿔 회피했으나 **search 노드 쪽 결함 자체는 남아 있다**.

이번 트레이스는 Gap-07이 실제 사용자 체감 문제로 드러난 것이다. 사용자 결정에 따라 두 건을 모두 근본 해소한다.

### 1.3 근거 코드 (진단)

| 관찰 | 코드 위치 | 사실 |
|------|-----------|------|
| worker_id에 도구명이 없다 | `create_agent_use_case.py:513` `_make_worker_id` | `mcp_{srv}_worker` = 서버 단위 tool_id. 개별 도구면 `mcp_{srv}_{tool}_worker` |
| 카탈로그 조회가 빗나간다 | `workflow_compiler.py:957` `_catalog_key` | 카탈로그는 `mcp:{srv}:{tool}`(`sync_mcp_tools_use_case.py:57`), 워커 키는 `mcp_{srv}` |
| category가 `action`으로 떨어진다 | `workflow_compiler.py:966` `_resolve_category` | `agent_tool.category`는 생성 경로 어디서도 채우지 않아 항상 NULL |
| react 워커가 만들어진다 | `workflow_compiler.py:567` | `category in ("search","collect")`가 거짓 → `create_agent(...)` |
| search 노드는 MCP를 못 부른다 | `search_pipeline.py:239` `_safe_search` | `tool.ainvoke({"query": q})`. MCP 어댑터의 `args_schema`는 `MCPToolInput(arguments: dict)` 제네릭 래퍼(`tool_adapter.py:38`) — 검색어가 `arguments`에 실리지 않는다 |
| collect 노드는 이미 해결돼 있다 | `collect_pipeline.py:143` `_build_payload` | `{"arguments": {...}}`로 감싼다. search만 이 계약을 빠뜨렸다 |

### 1.4 Related Documents

- `docs/archive/2026-09/mcp-tool-category-routing/*` (plan/design/analysis/report) — §10 Gap-06/07
- `docs/rules/tool-and-mcp.md`
- 트레이스: `samples/tool_call.png`

---

## 2. Scope

### 2.1 In Scope

- [ ] **module-1** — 레거시 `mcp_{server}` 워커 → 개별 도구 워커 Flyway DML 마이그레이션 (`V071__migrate_legacy_mcp_workers.sql`)
- [ ] **module-1b** — `workflow_compiler` 레거시 분기 **유지 + 경고 로그** (재발·백업 복원 감지)
- [ ] **module-2** — `search_pipeline._safe_search`를 MCP 어댑터 계약 + 실제 입력 스키마 기반으로 일반화
- [ ] **module-3** — `PATCH /api/v1/tool-catalog/metadata`에서 `category='search'` 지정 시 검색어 파라미터 해석 가능 여부 검증(불가 시 거부)
- [ ] **module-3b** — 런타임에도 파라미터 미상이면 추측 인자로 호출하지 않고 근거 메시지 반환 (collect의 `_shortage_message` 동형)
- [ ] 위 전부에 대한 pytest 단위 테스트

### 2.2 Out of Scope

- `agent_tool.category`를 사용자가 직접 지정하는 UI/API — 분류의 단일 출처는 `tool_catalog`로 유지 (D-04 정책 보존)
- 실 MCP 서버 E2E 실측 — 사용자 결정에 따라 이번 사이클은 fake tool 단위 테스트로 판정
- collect 노드 로직 변경 — 이미 올바르며 이번 변경의 참조 구현으로만 쓴다
- 프론트엔드 변경 — `AdminToolsPage`의 분류 UI는 이미 존재하며 API 계약이 바뀌지 않는다 (module-3은 400 에러 케이스만 추가)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | 요구사항 | 우선순위 | 상태 |
|----|----------|:--------:|:----:|
| FR-01 | `agent_tool`의 `tool_id LIKE 'mcp\_%'`(레거시 서버 단위) 행을, 해당 서버의 활성 카탈로그 도구 수만큼 `mcp:{srv}:{tool}` 행으로 확장하고 원본 행을 제거한다 | High | Pending |
| FR-02 | 확장된 각 행의 `worker_id`는 `sanitize_tool_name(f"{tool_id}_worker")`와 동일한 결과(`mcp_{srv}_{tool}_worker`)여야 한다 — 런타임 노드명과 일치해야 라우팅이 성립 | High | Pending |
| FR-03 | 확장된 행의 `description`은 카탈로그의 도구 설명을, `sort_order`는 원본 행의 위치를 보존한 뒤 연속 부여한다. `category`는 NULL 유지(분류 출처는 카탈로그) | High | Pending |
| FR-04 | 마이그레이션은 카탈로그에 활성 도구가 하나도 없는 서버의 레거시 행은 **건드리지 않는다** — 도구를 0개로 만들어 에이전트를 죽이지 않는다 | High | Pending |
| FR-05 | `workflow_compiler`가 서버 단위 워커를 만나면 `legacy server-level MCP worker, category routing unavailable` 경고를 워커·서버 id와 함께 남긴다 | Medium | Pending |
| FR-06 | `_safe_search`는 MCP 어댑터에 대해 `{"arguments": {<검색어 파라미터>: query}}` 형태로 호출한다. 비-MCP 도구는 기존 `{"query": query}` 동작을 보존한다 | High | Pending |
| FR-07 | 검색어 파라미터는 도구의 `mcp_input_schema`에서 해석한다. 단일 문자열 required 파라미터가 있으면 그것, 없으면 알려진 이름(`query`/`q`/`search_query`/`keyword`) 매칭 순으로 결정한다 | High | Pending |
| FR-08 | `UpdateToolMetadataUseCase`가 `category='search'` 지정 시 FR-07 규칙으로 파라미터를 해석하지 못하면 `ValueError`로 거부한다(라우터는 400) | High | Pending |
| FR-09 | 런타임에 파라미터를 해석하지 못하면 도구를 호출하지 않고, 하류가 읽을 수 있는 사유 메시지를 검색 결과 자리에 남긴다(그래프 비중단) | Medium | Pending |
| FR-10 | FR-09 발생 시 `search_node argument unresolved` 경고를 워커·도구 id와 함께 남긴다 | Medium | Pending |

### 3.2 Non-Functional Requirements

| 항목 | 기준 | 측정 방법 |
|------|------|-----------|
| 하위호환 | 레거시 워커가 남아 있어도 컴파일이 실패하지 않는다 | 기존 컴파일러 테스트 그린 |
| 하위호환 | 내부 검색 도구(`tavily_search` 등)의 search 노드 동작 무변경 | `search_pipeline` 기존 테스트 그린 |
| 관측성 | 레거시 워커·인자 미해석이 로그로 즉시 드러난다 | 로그 assertion 테스트 |
| 코딩 규칙 | 함수 40줄 이하, if 중첩 2단계 이하, print 금지 | `/verify-architecture`, 리뷰 |
| 마이그레이션 안전 | 롤백 불가한 DELETE 전에 원본을 복구 가능한 형태로 남긴다 | 설계 단계에서 확정 (§5) |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01~FR-10 구현 완료
- [ ] **단위 테스트(fake tool)로 "tool_id → 생성 노드 종류" 고정**: 레거시 `mcp_{srv}` → react + 경고 / 개별 도구 `category='collect'` → collect 노드 / `category='search'` → search 노드
- [ ] search 노드가 MCP fake 어댑터를 `{"arguments": {...}}`로 호출하는 것을 카운터로 검증
- [ ] 스키마 미상 fake 도구에서 도구가 **호출되지 않고** 사유 메시지가 반환되는 것을 검증
- [ ] 마이그레이션 SQL을 로컬 MySQL에 적용해 대상 1건이 개별 도구 워커로 확장되는 것을 확인
- [ ] 마이그레이션 후 해당 에이전트를 컴파일해 collect 노드가 생성되는 것을 확인
- [ ] `docs/rules/tool-and-mcp.md`에 "레거시 서버 단위 워커는 분류 라우팅 대상이 아니다" 명시

### 4.2 Quality Criteria

- [ ] 신규/변경 모듈에 대응 테스트 존재 (`/verify-tdd`)
- [ ] DDD 레이어 규칙 위반 없음 (`/verify-architecture`) — 파라미터 해석 규칙은 domain policy에 둔다
- [ ] 로깅 규칙 준수 (`/verify-logging`)
- [ ] 기존 테스트 전량 그린

---

## 5. Risks and Mitigation

| 위험 | 영향 | 가능성 | 완화 |
|------|:----:|:------:|------|
| 마이그레이션이 운영 에이전트의 도구를 잃게 만든다 | High | Low | FR-04(활성 도구 0이면 미변경) + DELETE 전 원본 행 보존 방식을 Design에서 확정. 대상은 실측 1건뿐이라 검증 범위가 좁다 |
| `worker_id` 생성 규칙이 SQL과 Python 사이에서 어긋난다 | High | Medium | `sanitize_tool_name`의 실제 동작을 Design 단계에서 확인하고, 마이그레이션 후 컴파일 테스트로 노드명 일치를 검증 (FR-02) |
| 서버 단위 워커가 도구 3개를 한 워커에서 쓰던 것을 3개 워커로 쪼개면 supervisor 라우팅 동작이 바뀐다 | Medium | High | **의도된 변경**이다. 다만 supervisor 프롬프트의 워커 목록이 길어지므로 Design에서 flow_hint 영향 확인 |
| 카탈로그가 최신이 아니면(서버에 도구 추가/삭제 후 sync 미실행) 잘못된 도구 목록으로 확장된다 | Medium | Medium | 마이그레이션 전 `POST /api/v1/tool-catalog/sync` 실행을 Do 단계 절차에 명시 |
| MCP 서버가 `inputSchema`를 주지 않으면 search 지정이 불가능해진다 | Low | Medium | 설계된 동작이다(FR-08 거부). 해당 도구는 `collect`나 미분류(react)로 운영 |
| 실 MCP 서버 실측 없이 종료 — Gap-03과 동일한 한계 반복 | Medium | High | 사용자 결정으로 수용. Analysis 문서 §0에 한계로 명시하고 Check 단계 Match Rate 산정에서 static 공식 사용 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| 리소스 | 종류 | 변경 내용 |
|--------|------|-----------|
| `agent_tool` (테이블 데이터) | DB 데이터 | 레거시 `mcp_{srv}` 행 → `mcp:{srv}:{tool}` 행 N개로 확장. **스키마 변경 없음** |
| `db/migration/V071__migrate_legacy_mcp_workers.sql` | 신규 파일 | DML 마이그레이션 |
| `src/application/agent_builder/search_pipeline.py` | Application | `_safe_search` 호출 규약 일반화 + 인자 미해석 분기 |
| `src/domain/agent_builder/policies.py` (또는 신규 domain 모듈) | Domain | 검색어 파라미터 해석 규칙 (FR-07) |
| `src/domain/tool_catalog/policies.py` | Domain | `ToolCategoryPolicy`에 search 지정 검증 추가 (FR-08) |
| `src/application/tool_catalog/update_tool_metadata_use_case.py` | Application | 검증 호출 배선 |
| `src/application/agent_builder/workflow_compiler.py` | Application | 레거시 분기 경고 로그 (FR-05) |

### 6.2 Current Consumers

| 리소스 | 동작 | 코드 경로 | 영향 |
|--------|------|-----------|------|
| `agent_tool` | READ | `agent_definition_repository.py:378` → `WorkerDefinition` 복원 | **검증 필요** — 행이 늘어난다 |
| `agent_tool` | READ | `workflow_compiler.compile()` 워커 루프 | **의도된 변경** — 노드 종류가 바뀐다 |
| `agent_tool` | CREATE | `create_agent_use_case._build_skeleton_from_tool_ids` | 없음 — 이미 개별 도구를 저장 |
| `agent_tool` | UPDATE | `update_agent_use_case` / 에이전트 편집 화면 | **검증 필요** — 확장된 워커가 편집 화면에 정상 표시되는지 |
| `agent_tool` | READ | `fork_agent_use_case`, `auto_fork_service` | **검증 필요** — 워커 복제가 개별 도구로 이뤄지는지 |
| `_safe_search` | CALL | `search_pipeline.create_search_pipeline_node` | 유일 호출자 |
| search 노드 | CALL | `workflow_compiler._create_search_node` (legacy 모드) | 내부 도구 경로 무변경이어야 함 |
| deep search 노드 | CALL | `deep_search/workflow.create_deep_search_node` | **검증 필요** — 동일 인자 하드코딩이 있는지 확인 |
| `ToolCategoryPolicy.assert_assignable` | CALL | `update_tool_metadata_use_case` | 검증 추가로 400 케이스가 늘어난다 |
| `PATCH /tool-catalog/metadata` | API | `idt_front` `AdminToolsPage` | 계약 무변경. 400 응답 처리 확인 필요 |

### 6.3 Verification

- [ ] 확장된 워커가 에이전트 조회/편집/포크 경로에서 정상 동작
- [ ] 내부 검색 도구의 search 노드 동작 무변경
- [ ] deep_search 노드에 동일 결함이 있는지 확인하고 있으면 Design 스코프에 포함
- [ ] `AdminToolsPage`가 category 지정 거부(400)를 사용자에게 표시

---

## 7. Architecture Considerations

### 7.1 Project Level

| Level | 선택 |
|-------|:----:|
| Starter | ☐ |
| Dynamic | ☐ |
| **Enterprise** (Thin DDD: domain/application/infrastructure/interfaces) | ☑ |

### 7.2 Key Architectural Decisions

| 결정 | 선택지 | 선택 | 근거 |
|------|--------|------|------|
| 레거시 워커 처리 | 마이그레이션 / 런타임 분해 / 서버단위 category / 수동 재생성 | **Flyway DML 마이그레이션** | DB를 단일 형식으로 수렴시켜야 `_resolve_category`가 단순해진다. 런타임 분해는 노드 구성이 DB와 달라져 관측·디버깅이 어려워진다 |
| 마이그레이션 수단 | Flyway SQL / Python 스크립트 / 수동 | **Flyway SQL** | 기존 배포 파이프라인을 그대로 타고 적용 이력이 남는다 |
| 레거시 분기 존치 | 유지+경고 / 제거 | **유지 + 경고 로그** | 백업 복원·외부 DB에서 레거시 행이 다시 들어와도 에이전트가 죽지 않는다. 경고로 재발을 즉시 발견 |
| 검색어 파라미터 해석 | 스키마 기반 / 런타임 LLM 생성 / 이름 허용목록 | **스키마 기반 + 지정 시점 차단** | 조용한 실패(Gap-06)의 재발을 원천 차단. LLM 생성은 search 노드에 호출 1회를 더 붙이고 collect와 경계가 흐려진다 |
| 파라미터 해석 규칙 위치 | domain policy / application 헬퍼 | **domain policy** | 지정 시점 검증(application/tool_catalog)과 런타임(application/agent_builder) 두 곳이 같은 규칙을 써야 한다 — 단일 출처 |
| 판정 기준 | 단위 테스트 / 실서버 E2E | **단위 테스트(fake tool)** | 사용자 결정. CI에서 회귀를 막는 것이 우선 |

### 7.3 레이어 배치

```
domain/agent_builder/policies.py      SearchArgumentPolicy (FR-07) ← 신설
domain/tool_catalog/policies.py       ToolCategoryPolicy.assert_assignable 확장 (FR-08)
application/agent_builder/search_pipeline.py   _safe_search 규약 일반화 (FR-06/09/10)
application/agent_builder/workflow_compiler.py 레거시 경고 (FR-05)
application/tool_catalog/update_tool_metadata_use_case.py  검증 배선
db/migration/V071__migrate_legacy_mcp_workers.sql          FR-01~04
```

---

## 8. Convention Prerequisites

### 8.1 기존 프로젝트 컨벤션

- [x] `CLAUDE.md` 코딩 규칙 (함수 40줄, if 중첩 2단계, print 금지, logger 필수)
- [x] `idt/docs/rules/tool-and-mcp.md` — 도구/MCP 개발 규칙 (**필수 확인 대상**)
- [x] `idt/docs/rules/db-session.md` — Repository 내부 commit 금지
- [x] `idt/docs/rules/testing.md` — TDD 사이클
- [x] Flyway 마이그레이션 네이밍 `V0NN__snake_case.sql` (현재 최신 V070)

### 8.2 확인/정의할 컨벤션

| 항목 | 현재 상태 | 정의할 것 | 우선순위 |
|------|-----------|-----------|:--------:|
| DML 마이그레이션 | **관례 없음** — 기존 V001~V070은 전부 DDL | 데이터 마이그레이션의 롤백/보존 방식 | High |
| DDL COMMENT 규칙 | V054+ DDL에 필수 (`tests/db/test_migration_ddl_comments.py`) | **이번은 DML이라 해당 없음** — 테스트 통과 확인만 | Medium |
| MCP 도구 분류 운영 | 카탈로그 category를 관리자가 지정 | `docs/rules/tool-and-mcp.md`에 분류 가이드 추가 | Medium |

### 8.3 필요한 환경변수

없음. 기존 `MYSQL_*` 설정만 사용한다.

---

## 9. Next Steps

1. [ ] Design 문서 작성 — `/pdca design fix-mcp-search-node-routing`
   - 마이그레이션 SQL의 원본 보존/롤백 방식 확정 (§5 최상위 위험)
   - `sanitize_tool_name` 실동작 확인 후 SQL의 worker_id 생성식 확정
   - `deep_search/workflow.py`에 동일 인자 결함이 있는지 확인해 스코프 편입 여부 결정
   - `SearchArgumentPolicy` 해석 규칙 상세 (required 단일 문자열 → 이름 허용목록 → 실패)
2. [ ] 구현 — `/pdca do fix-mcp-search-node-routing --scope module-1` 부터 순차
3. [ ] Gap 분석 — `/pdca analyze fix-mcp-search-node-routing`

---

## Version History

| 버전 | 날짜 | 변경 | 작성자 |
|------|------|------|--------|
| 0.1 | 2026-09-04 | 최초 작성. 트레이스(`samples/tool_call.png`) 진단 + 사용자 결정 7건 반영 | 배상규 |
