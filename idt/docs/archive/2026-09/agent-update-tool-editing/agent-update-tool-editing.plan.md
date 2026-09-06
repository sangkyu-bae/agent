# Agent Update Tool Editing Planning Document

> **Summary**: 에이전트 수정(PATCH) API 가 도구 구성을 바꾸지 못해 수정 화면의 도구 추가/삭제가 조용히 무시되고 `presentation_generator` 설정만 422 로 실패하는 결함을, `UpdateAgentRequest` 에 `tool_ids`/`tool_configs` 를 추가하고 워커 스켈레톤을 재구성하는 방식으로 근본 해결
>
> **Project**: sangplusbot (idt 백엔드 + idt_front)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-09-05
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | `UpdateAgentRequest` 에 `tool_ids`/`tool_configs` 필드가 아예 없어(`schemas.py:143-172`) 수정 경로에서 도구 워커를 추가·삭제할 방법이 없다. 그런데 프론트 수정 폼은 도구 토글을 허용하고(`AgentBuilderPage/index.tsx:399`) 저장 시 도구 목록 없이 `presentation_generator` 설정만 전송한다(`:255-290`). 결과적으로 ① 도구 변경은 **성공 메시지와 함께 조용히 유실**되고 ② 발표자료 설정만 워커 부재로 `ValueError` → 422 (`presentation_generator_binding.py:35`) |
| **Solution** | 수정 요청에 `tool_ids`/`tool_configs` 를 추가하고, UseCase 가 목표 상태 기준으로 도구 워커를 재구성한 뒤 문서/발표자료 바인딩을 실행한다. 워커 영속은 이미 `_sync_workers` 가 전량 재구성하므로(`agent_definition_repository.py:135-159`) **DB 마이그레이션 0**. 생성 경로의 스켈레톤 빌더를 공용 모듈로 추출해 내부·MCP·빌트인 규칙을 생성/수정이 한 벌로 공유한다 |
| **Function/UX Effect** | 수정 화면에서 도구를 추가·삭제하면 실제로 반영된다. 발표자료생성기를 나중에 붙여도 양식 설정이 정상 저장된다. RAG 설정 등 유지 도구의 기존 설정은 보존되고, 제거된 도구의 종속 데이터(템플릿·문서유형)는 soft-delete 되어 고아가 남지 않는다 |
| **Core Value** | "생성 시점에 고정된 도구 구성"이라는 숨은 제약 제거 — 에이전트를 다시 만들지 않고 진화시킬 수 있게 되어 agent-builder 의 편집 계약이 생성 계약과 대칭을 이룬다. 조용한 실패(도구 유실)를 관측 가능한 성공/실패로 바꾼다 |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 수정 API 가 도구 구성을 못 바꿔 도구 변경이 조용히 유실되고, 발표자료 설정은 422 로 실패한다 |
| **WHO** | P2 — KB 운영자 / 에이전트 소유자 (기존 에이전트에 도구를 붙였다 떼며 운영하는 사용자) |
| **RISK** | 워커 전량 재구성이 종속 데이터(document_template, document_generation_type, RAG kb_id)와 visibility scope 를 깨뜨릴 수 있음 |
| **SUCCESS** | 도구 추가/삭제가 PATCH 한 번으로 반영되고, 유지 도구의 tool_config 는 보존되며, 제거 시 종속 레코드가 soft-delete 된다 |
| **SCOPE** | M1 공용 스켈레톤 빌더 추출 → M2 UpdateAgentUseCase 워커 재구성 + 정책 재검증 → M3 DI 배선 → M4 프론트 payload/프리필 정합 |

---

## 1. Overview

### 1.1 Purpose

`PATCH /agents/{agent_id}` 가 도구 워커를 목표 상태로 재구성할 수 있게 하여, 에이전트 생성 이후에도
도구 구성을 편집할 수 있게 한다. 부수적으로 `presentation_generator` 설정 422 결함을 해소한다.

### 1.2 Background (2026-09-05 코드 추적으로 원인 확정)

**증상** (request_id `602385da-807d-4a1c-b4c5-77413332084b`):

```
ValueError: presentation_generator 도구 워커가 없어 발표자료 설정을 적용할 수 없습니다.
  update_agent_use_case.py:172 → presentation_generator_binding.py:35
```

**원인 사슬**:

1. `presentation_generator_binding.py:26-38` — `agent.workers` 에서 `tool_id == "presentation_generator"` 인
   워커를 찾아 `tool_config` 를 **주입만** 한다. 워커를 생성하지 않으므로 부재 시 `ValueError`.
2. `schemas.py:143-172` `UpdateAgentRequest` 에 `tool_ids`/`tool_configs` 가 **없다**
   (`CreateAgentRequest` `schemas.py:94-99` 에만 존재).
3. `update_agent_use_case.py:129-174` — 워커를 건드리는 경로는 `sub_agent_configs` 뿐. 도구 워커
   추가/삭제 코드가 없다.
4. 프론트 수정 분기(`AgentBuilderPage/index.tsx:255-290`)는 `tool_ids` 를 보내지 않으면서
   `presentation_generator` 는 보낸다. 생성 분기(`:315-347`)는 `tool_ids` 를 함께 보내므로 정상.
5. UI 는 수정 모드에서도 도구 추가를 허용(`handleToolToggle` `:399`)하고, 도구 칩이 생기면 설정 패널이
   열려 draft 가 채워진다 → 서버에 없는 워커에 대한 설정이 전송된다.

**재현**: 발표자료생성기 미보유 에이전트 수정 진입 → 도구 추가 → 양식 선택 → 저장 = 항상 422.
반대로 이미 워커를 보유한 에이전트의 설정 변경은 정상(`agentDetailMapping.ts:81-83` 프리필 경로).

**더 큰 문제**: 발표자료생성기는 후속 검증 때문에 에러로 드러났을 뿐, **다른 모든 도구의 추가/삭제는
저장 성공 메시지와 함께 조용히 무시된다.** 위키의 선례 *"수정 가능 필드 추가는 스키마+apply_update+
repo update()+DI 4곳 세트 — repo 누락 시 조용히 미저장"* ([[agent-screens]])의 변종이다.

### 1.3 Related Documents

- 위키: `docs/wiki/frontend/screens/agent-screens.md` (도구 ID 이중 네임스페이스, update 화이트리스트 함정)
- 위키: `docs/wiki/backend/patterns/builtin-tools-optout-channel.md` (빌트인 opt-out 채널 분리)
- 위키: `docs/wiki/backend/db/erd-agent.md` (agent_tool 테이블 / tool_id 저장 표기)
- 규칙: `idt/docs/rules/tool-and-mcp.md` (도구·MCP 추가/변경 시 필수 확인)

---

## 2. Scope

### 2.1 In Scope

- [ ] `UpdateAgentRequest` 에 `tool_ids: list[str] | None`, `tool_configs: dict[str, RagToolConfigRequest] | None` 추가
- [ ] 생성 경로의 스켈레톤 빌더(`_build_skeleton_from_tool_ids`, `_normalize_tool_id`, `_make_worker_id`,
      `_build_builtin_workers`, MCP description 해석)를 공용 모듈로 추출해 create/update 공유
- [ ] `UpdateAgentUseCase` 에서 도구 워커 재구성 + 기존 `tool_config` 보존 머지 + 서브에이전트 워커 재배치
- [ ] 제거된 도구의 종속 레코드 soft-delete (document_template / document_generation_type)
- [ ] 도구 변경 시 KB/컬렉션 scope 재검증 + visibility clamp (생성 경로 `_resolve_kbs` 와 동일 정책)
- [ ] 워커 개수 정책 재검증 (`AgentBuilderPolicy.validate_worker_count`)
- [ ] MCP 도구(`mcp_*`) 추가/삭제 지원 — `mcp_server_repo` 주입
- [ ] 빌트인 도구 재주입 (생성과 동일 규칙, `tool_catalog_repo` 주입)
- [ ] `main.py` DI 배선 (`_build_update_agent_uc` 에 `tool_catalog_repo`, `mcp_server_repo` 추가)
- [ ] 프론트 수정 payload 에 `tool_ids`/`tool_configs` 포함 + 빌트인 매핑 정합
- [ ] TDD: 유닛 테스트 선작성 (백엔드 pytest / 프론트 Vitest)

### 2.2 Out of Scope

- 워커 실행 순서(`sort_order`) 수동 편집 UI — 현행 "선택 순서 = 실행 순서" 유지
- 서브에이전트 구성 로직 변경 (`sub_agent_configs` 계약은 그대로)
- DB 스키마 변경 / 마이그레이션 (`_sync_workers` 가 이미 전량 재구성)
- `agent_composer`(Fix 탭) 초안 적용 경로의 계약 변경
- 도구별 설정 UI 자체의 개선 (발표자료/문서생성기 모달 UX)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `UpdateAgentRequest.tool_ids` 가 `None` 이면 도구 구성 **무변경** (기존 워커 그대로 유지) | High | Pending |
| FR-02 | `tool_ids` 가 값이면 **목표 상태 전체 교체** — 목록에 없는 도구 워커는 제거, 새 도구는 추가 | High | Pending |
| FR-03 | 유지되는 도구는 기존 워커의 `tool_config` 를 승계하고, 요청 `tool_configs` 에 온 항목만 덮어쓴다 | High | Pending |
| FR-04 | 도구 제거 시 해당 워커의 `document_template` / `document_generation_type` active 레코드를 soft-delete | High | Pending |
| FR-05 | 서브에이전트 워커는 도구 워커 뒤로 `sort_order` 재배치되며 구성 자체는 보존 | High | Pending |
| FR-06 | 도구 변경 시 KB/컬렉션 scope 를 재검증하고 visibility 를 clamp (생성과 동일 정책) | High | Pending |
| FR-07 | 재구성 후 `AgentBuilderPolicy.validate_worker_count` 로 워커 개수 정책 재검증 | High | Pending |
| FR-08 | MCP 도구(`mcp_*`)를 내부 도구와 동등하게 추가/삭제 가능 (description 은 레지스트리에서 해석) | High | Pending |
| FR-09 | 빌트인 도구는 생성과 동일 규칙으로 재주입 (`is_builtin AND is_active`, 사용자 선택과 중복 미주입) | Medium | Pending |
| FR-10 | 도구 재구성은 문서/발표자료 바인딩 **이전**에 수행되어 새로 추가된 워커에 설정이 주입된다 | High | Pending |
| FR-11 | `worker_id` 는 `{tool_id}_worker` 결정론 규칙을 유지해 종속 테이블의 `worker_id` 참조가 깨지지 않는다 | High | Pending |
| FR-12 | 프론트 수정 payload 에 `tool_ids`/`tool_configs` 를 포함하고, 저장 표기↔카탈로그 표기 변환을 지킨다 | High | Pending |
| FR-13 | `UpdateAgentResponse` 에 clamp 결과(`visibility`, `visibility_clamped`)를 담아 사용자에게 안내 | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 무회귀 | `tool_ids` 미전송 요청의 동작이 현행과 100% 동일 | 기존 update 테스트 전량 통과 |
| 트랜잭션 | 워커 재구성·종속 soft-delete·에이전트 저장이 단일 세션 원자성 (R6) | Repository 내부 commit 금지 규칙 준수 확인 |
| 아키텍처 | domain → infrastructure 역참조 없음, 스켈레톤 빌더는 application 계층 | `/verify-architecture` |
| 로깅 | 워커 재구성 시 추가/제거된 tool_id 를 request_id 와 함께 구조화 로깅 | `/verify-logging` |
| 계약 정합 | 백엔드 스키마 변경 시 `idt_front/src/types/agentBuilder.ts` 동기 수정 | `/api-contract-sync` |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] SC-1: 발표자료생성기 미보유 에이전트에 도구 추가 + 양식 선택 저장이 **성공**한다 (원 결함 해소)
- [ ] SC-2: 수정으로 도구를 제거하면 `agent_tool` 행이 사라지고 실행 그래프에서도 빠진다
- [ ] SC-3: RAG 도구를 유지한 채 다른 도구만 바꿔도 기존 RAG `tool_config`(kb_id 포함)가 보존된다
- [ ] SC-4: 문서생성기를 제거하면 해당 `document_generation_type` 이 soft-delete 되고 고아 행이 남지 않는다
- [ ] SC-5: `tool_ids` 를 보내지 않는 기존 클라이언트 요청은 도구 구성을 전혀 바꾸지 않는다
- [ ] SC-6: public 에이전트에 private KB 도구를 추가하면 visibility 가 clamp 되고 응답에 표시된다
- [ ] SC-7: MCP 도구 추가/삭제가 내부 도구와 동일하게 동작한다
- [ ] 모든 FR 에 대응하는 유닛 테스트가 Red → Green 순으로 작성됨

### 4.2 Quality Criteria

- [ ] 함수 40줄 / if 중첩 2단계 규칙 준수 (CLAUDE.md §3)
- [ ] `/verify-architecture`, `/verify-logging`, `/verify-tdd` 통과
- [ ] 프론트 Vitest + MSW 로 수정 payload 계약 검증
- [ ] 기존 agent_builder 테스트 스위트 무회귀

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 워커 전량 재구성으로 유지 도구의 `tool_config` 유실 | High | Medium | FR-03 보존 머지를 최우선 테스트로 작성 (기존 워커 config 승계) |
| `worker_id` 변경으로 `document_generation_type.worker_id` 참조 고아화 | High | Low | `_make_worker_id` 가 `{tool_id}_worker` 결정론 — FR-11 로 회귀 테스트 고정 |
| 프론트가 `tool_ids` 를 부분 전송해 도구가 대량 삭제됨 | High | Medium | 목표 상태 계약을 문서화 + 프론트는 항상 폼 전량 전송, 빈 배열/undefined 구분 테스트 |
| 빌트인 재주입 규칙 불일치로 칩 중복 또는 빌트인 소실 | Medium | Medium | 생성 경로 `_build_builtin_workers` 를 그대로 공유(별도 구현 금지) + `mapDetailToForm` 빌트인 매핑 정리 |
| visibility clamp 가 사용자 모르게 공개 범위를 축소 | Medium | Medium | FR-13 으로 응답에 clamp 사실을 담고 UI 안내 |
| 스켈레톤 빌더 추출 리팩토링이 생성 경로를 깨뜨림 | High | Low | 추출은 순수 이동(behavior-preserving)으로 한정, 생성 경로 테스트 선통과 후 update 배선 |
| MCP 레지스트리 미배선 상태에서 `mcp_*` 요청 시 500 | Medium | Low | `mcp_server_repo` 미주입 시 명시적 ValueError(422) — `ensure_*_wiring` 동형 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `UpdateAgentRequest` | Schema | `tool_ids`, `tool_configs` 필드 추가 (둘 다 optional, None=무변경) |
| `UpdateAgentResponse` | Schema | `visibility`, `visibility_clamped` 추가 (FR-13) |
| `UpdateAgentUseCase` | Application | 워커 재구성 단계 + 종속 soft-delete + scope 재검증 추가, 생성자에 repo 2종 주입 |
| `CreateAgentUseCase` | Application | 스켈레톤 빌더 private 메서드를 공용 모듈로 추출 (동작 불변) |
| 신규 `worker_skeleton_builder.py` (가칭) | Application | create/update 공유 워커 빌드 로직 |
| `main.py` `_build_update_agent_uc` | DI | `tool_catalog_repo`, `mcp_server_repo` 배선 추가 |
| `idt_front` `UpdateAgentRequest` 타입 + 수정 payload | Frontend | `tool_ids`/`tool_configs` 전송, 빌트인 매핑 정합 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `PATCH /agents/{id}` | UPDATE | `agent_builder_router.py:240` → `UpdateAgentUseCase` | Needs verification — 필드 추가는 하위호환(optional) |
| `agent.workers` | UPDATE | `agent_definition_repository.py:120` `_sync_workers` | None — 이미 전량 재구성 구조 |
| `agent_tool` 행 | READ | `workflow_compiler.py:405-547` (실행 그래프 컴파일) | Needs verification — 워커 변경이 다음 실행부터 반영 |
| `document_generation_type.worker_id` | READ | `_replace_document_generation_type` / 실행 노드 | Needs verification — worker_id 결정론 유지로 무영향 |
| `document_template` (agent_id, worker_id) | READ | `document_extractor` interfaces:24-26 | Needs verification — 도구 제거 시 soft-delete 필요 |
| 프론트 수정 저장 | UPDATE | `AgentBuilderPage/index.tsx:255-290` | Breaking(의도적) — payload 확장 필요 |
| 프론트 수정 프리필 | READ | `agentDetailMapping.ts:63` `mapDraftToolIdsToCatalog` | Needs verification — 빌트인 포함 매핑 규칙 확인 |
| Fix 탭 초안 적용 | UPDATE | `agentFormPrefill.ts` `applyToolsToForm` | None — 폼 상태만 다루며 저장 계약 불변 |
| 포크(`ForkAgentUseCase`) | CREATE | `fork_agent_use_case.py` | None — 생성 경로 재사용, 빌더 추출 후 회귀 확인 |

### 6.3 Verification

- [ ] `tool_ids` 미전송 기존 요청 경로 무회귀 확인
- [ ] 워커 변경이 다음 실행의 `workflow_compiler` 그래프에 정확히 반영되는지 확인
- [ ] 종속 테이블(`document_template`, `document_generation_type`) 참조 무결성 확인
- [ ] 권한/visibility 변경이 기존 구독자·공개 범위를 예기치 않게 축소하지 않는지 확인

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | 단순 구조 | 정적 사이트 | ☐ |
| **Dynamic** | 기능 모듈 + BaaS | 웹앱 MVP | ☐ |
| **Enterprise** | Thin DDD 레이어 분리, DI | 본 프로젝트 (FastAPI + LangGraph) | ☑ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 수정 API 도구 계약 | 전체 교체 / 델타(add·remove) | **전체 교체 (목표 상태)** | `skill_ids`·`middleware_types` 와 동일 의미론이라 클라이언트 규칙이 일관됨 |
| 유지 도구 config | 기존 보존 머지 / 요청 전량 교체 | **기존 보존, 전달분만 덮어쓰기** | 프론트가 RAG 설정을 매번 전량 전송하지 않아도 설정이 유실되지 않음 |
| 도구 제거 시 종속 데이터 | soft-delete / 422 차단 / 방치 | **워커 제거 + 종속 soft-delete** | `_replace_*` 교체 로직과 동형, 고아 행 및 유령 설정 부활 차단 |
| 빌트인 처리 | 생성과 동일 규칙 / 저장 워커 유지 | **생성과 동일 규칙 재주입** | 카탈로그 토글이 기존 에이전트에도 반영, 규칙 이중화 방지 |
| MCP 도구 | 지원 / 422 거부 | **지원 (내부와 동등)** | 프론트가 이미 MCP 필터 없이 전송 — 제외 시 또 다른 조용한 무시 발생 |
| 빌더 코드 공유 | 공용 모듈 추출 / update 에 재구현 | **공용 모듈 추출** | 두 벌 구현은 한쪽만 고쳐져 어긋난다(위키 선례). 정규화·MCP 해석·빌트인 규칙이 모두 동일해야 함 |
| DB 스키마 | 마이그레이션 필요 / 불필요 | **불필요** | `_sync_workers` 가 이미 워커 row 전량 재구성 |

### 7.3 Clean Architecture Approach

```
Selected Level: Enterprise (Thin DDD)

application/agent_builder/
  worker_skeleton_builder.py   (신규 — create/update 공용 워커 빌드)
  create_agent_use_case.py     (빌더 호출로 치환)
  update_agent_use_case.py     (워커 재구성 단계 추가)
  presentation_generator_binding.py  (변경 없음 — 재구성 후 호출되므로 워커가 존재)
domain/agent_builder/
  policies.py  (validate_worker_count 재사용 — 변경 없음)
infrastructure/agent_builder/
  agent_definition_repository.py  (_sync_workers 변경 없음)
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md` (루트 + idt) 코딩 규칙 존재
- [x] `idt/docs/rules/tool-and-mcp.md` — 도구/MCP 변경 시 필수 확인
- [x] `idt/docs/rules/db-session.md` — Repository 내부 commit 금지, 단일 세션 규칙
- [x] `idt/docs/rules/testing.md` — TDD 절차
- [x] `docs/wiki/_INDEX.md` — 관련 위키 4건 확인 완료

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| 도구 ID 표기 | exists (카탈로그 `internal:x` ↔ 저장 `x`) | update 경로에서도 `_normalize_tool_id` 일괄 적용 | High |
| optional 필드 의미론 | exists (`None`=무변경, `[]`=전부 해제) | `tool_ids` 에 동일 규칙 명문화 | High |
| 종속 데이터 정리 | partial (`_replace_*` 만 존재) | "워커 제거 시 종속 soft-delete" 규칙 추가 | High |
| 에러 처리 | exists (ValueError → 422) | 도구 검증 실패 메시지 문구 규칙 | Medium |

### 8.3 Environment Variables Needed

없음 — 신규 환경변수 불필요.

### 8.4 Pipeline Integration

해당 없음 (기존 기능 수정 — 9-phase 파이프라인 신규 진입 아님).

---

## 9. Next Steps

1. [ ] `/pdca design agent-update-tool-editing` — 3가지 아키텍처 안 비교 후 선택
2. [ ] 모듈 분할 및 세션 계획 수립 (M1 빌더 추출 → M2 UseCase → M3 DI → M4 프론트)
3. [ ] TDD 로 구현 (`/pdca do agent-update-tool-editing --scope module-1`)
4. [ ] `/pdca analyze` 로 Gap 분석

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-05 | 초안 — 원인 분석(코드 추적) + A안 확정 + 체크포인트 6문항 반영 | 배상규 |
