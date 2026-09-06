# Agent Update Tool Editing Design Document

> **Summary**: 생성 경로의 워커 스켈레톤 빌더를 공용 모듈로 행위보존 추출하고, `UpdateAgentUseCase` 가 목표 상태 기준으로 도구 워커를 재구성한 뒤 종속 정리 → scope clamp → 정책 검증 → 문서/발표자료 바인딩 순으로 처리한다 (Option C — Pragmatic Balance)
>
> **Project**: sangplusbot (idt 백엔드 + idt_front)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-09-06
> **Status**: Draft
> **Planning Doc**: [agent-update-tool-editing.plan.md](../../01-plan/features/agent-update-tool-editing.plan.md)

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

### 1.1 Design Goals

1. **규칙 단일화** — 도구 ID 정규화, MCP description 해석, 빌트인 주입, worker_id 생성 규칙이 생성/수정 경로에서 **한 벌**로 존재한다.
2. **무회귀** — `tool_ids` 를 보내지 않는 기존 요청의 동작이 바이트 단위로 동일하다.
3. **원자성** — 워커 재구성·종속 soft-delete·에이전트 저장이 단일 세션 트랜잭션에 편승한다 (R6).
4. **설정 보존** — 유지되는 도구의 `tool_config`(RAG kb_id·발표자료 blueprint 등)가 요청에 없어도 살아남는다.
5. **조용한 실패 제거** — 도구 변경은 반영되거나 명시적 에러가 나거나 둘 중 하나다.

### 1.2 Design Principles

- **행위보존 추출 우선**: 빌더 추출은 순수 이동(pure move). 로직 변경은 추출 완료·테스트 통과 후 별도 단계.
- **도메인 대칭**: `replace_sub_agents`(`domain/agent_builder/schemas.py:159-168`)의 대칭으로 `replace_tool_workers` 를 둔다. 워커 컬렉션 불변식은 도메인이 지킨다.
- **목표 상태 계약**: `skill_ids`·`middleware_types` 와 동일한 `None`=무변경 / `[]`=전부 해제 / `[...]`=목표 상태.
- **정책 재사용**: 검증(`AgentBuilderPolicy`)·clamp(`VisibilityPolicy`)는 기존 정책 객체를 그대로 호출한다.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | UpdateUseCase 내부 직접 구현 | WorkerComposition 서비스 + 종속정리 포트 신설 | 빌더 공용 모듈 추출 + 도메인 `replace_tool_workers` |
| **New Files** | 0 | 3~4 | 1~2 |
| **Modified Files** | 4 | 9+ | 6 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Low (규칙 두 벌) | High | High |
| **Effort** | Low | High | Medium |
| **Risk** | Medium (규칙 표류) | Medium (생성 경로 회귀) | Low |
| **Recommendation** | 핫픽스 | 장기 리팩토링 | **선택** |

**Selected**: **Option C — Pragmatic Balance**

**Rationale**: A는 위키가 명시적으로 경고한 함정(*"두 벌로 구현하면 한쪽만 고쳐져 조용히 어긋난다"* — `agentFormPrefill.ts` 주석, [[agent-screens]])을 그대로 재현한다. B는 이번 결함 범위를 넘어 생성 경로 전체를 재작성해 회귀 위험이 결함 자체보다 크다. C는 규칙 단일화라는 핵심 이득을 얻으면서 변경을 "이동 + 한 단계 추가"로 묶는다.

### 2.1 Component Diagram

```
┌──────────────────────────┐
│ AgentBuilderPage (React) │  tool_ids / tool_configs 를 수정 payload 에 포함
└────────────┬─────────────┘
             │ PATCH /agents/{id}
┌────────────▼─────────────────────────────────────────────┐
│ agent_builder_router.update_agent                        │  ValueError→422 / PermissionError→403
└────────────┬─────────────────────────────────────────────┘
┌────────────▼─────────────────────────────────────────────┐
│ UpdateAgentUseCase.execute                               │
│   ①워커 재구성 ②종속정리 ③scope clamp ④정책검증          │
│   ⑤문서/발표자료 바인딩 ⑥save                             │
└──────┬───────────────────────────┬───────────────────────┘
       │                           │
┌──────▼──────────────────┐  ┌─────▼──────────────────────┐
│ worker_skeleton_builder │  │ *_binding 모듈 (기존)       │
│  (create 와 공유)        │  │  document_template /        │
│  build_tool_workers      │  │  document_generation_type / │
│  build_builtin_workers   │  │  presentation_generator     │
└──────┬──────────────────┘  └────────────────────────────┘
       │
┌──────▼──────────────────────────────────────────────────┐
│ AgentDefinition.replace_tool_workers  (domain)           │
└──────┬──────────────────────────────────────────────────┘
┌──────▼──────────────────────────────────────────────────┐
│ AgentDefinitionRepository.update → _sync_workers (기존)  │  워커 row 전량 재구성
└─────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

```
요청 tool_ids (카탈로그 표기: internal:x / mcp:srv:tool)
  → normalize_tool_id            → 저장 표기 (x / mcp:srv:tool)
  → 기존 워커 tool_config 승계 머지 (요청 tool_configs 가 우선)
  → build_tool_workers           → 도구 워커 목록 (sort_order 0..N)
  → build_builtin_workers        → 빌트인 재주입 (중복·exclude 제외)
  → replace_tool_workers()       → 도구 워커 교체 + 서브에이전트 sort_order 재배치
  → 제거된 tool_id 집합 산출     → document_template / generation_type soft-delete
  → KB scope 재해석 → clamp      → visibility 조정 + clamped 플래그
  → validate_worker_count        → 정책 위반 시 422
  → *_binding                    → 새 워커에 tool_config 주입
  → repository.update            → _sync_workers 가 row 전량 재구성 (동일 세션)
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `worker_skeleton_builder` | `tool_registry`, `mcp_tool_id` 파서, `sanitize_tool_name` | 도구 메타·MCP 참조 해석, worker_id 생성 |
| `worker_skeleton_builder` | `mcp_server_repo` (주입) | MCP 서버 활성 검증 + description 해석 |
| `worker_skeleton_builder` | `tool_catalog_repo` (주입) | 빌트인 도구 목록 |
| `UpdateAgentUseCase` | `worker_skeleton_builder` | 워커 재구성 |
| `UpdateAgentUseCase` | `document_template_repo`, `document_generation_type_repo` | 제거 도구 종속 soft-delete (이미 주입됨) |
| `UpdateAgentUseCase` | `kb_repo`, `perm_repo`, `VisibilityPolicy` | scope 재검증 + clamp (이미 주입됨) |
| `CreateAgentUseCase` | `worker_skeleton_builder` | 기존 private 메서드 대체 (동작 불변) |

---

## 3. Data Model

### 3.1 Entity Definition

DB 스키마 변경 없음. 영향 받는 도메인 구조는 아래 두 가지다.

```python
# domain/agent_builder/schemas.py — 기존 구조 (변경 없음)
@dataclass
class WorkerDefinition:
    tool_id: str              # 저장 표기: "presentation_generator" / "mcp:srv:tool"
    worker_id: str            # "{tool_id}_worker" (sanitize 적용)
    description: str
    sort_order: int
    tool_config: dict | None  # 도구별 설정 (RAG / 문서 / 발표자료)
    worker_type: str          # "tool" | "sub_agent"
    ref_agent_id: str | None
    category: str | None

# 신규 도메인 메서드 (replace_sub_agents 대칭)
class AgentDefinition:
    def replace_tool_workers(self, tool_workers: list[WorkerDefinition]) -> None:
        """sub_agent 워커는 보존하고 tool 워커만 교체. sort_order를 재정렬한다."""
        sub_workers = [w for w in self.workers if w.worker_type == "sub_agent"]
        for i, worker in enumerate(tool_workers):
            worker.sort_order = i
        for j, worker in enumerate(sub_workers):
            worker.sort_order = len(tool_workers) + j
        self.workers = tool_workers + sub_workers
```

### 3.2 Entity Relationships

```
agent_definition 1 ──── N agent_tool            (워커 — update 시 전량 재구성)
                              │
                              ├── 1 ──── 0..1 document_template          (agent_id, worker_id)
                              └── 1 ──── 0..1 document_generation_type    (agent_id, worker_id)

worker_id = "{tool_id}_worker" 결정론 → 도구가 유지되는 한 재구성해도 참조 유지 (FR-11)
```

### 3.3 Database Schema

**변경 없음.** `_sync_workers`(`agent_definition_repository.py:135-159`)가 이미 `model.tools.clear()` → flush → 재삽입으로 워커 row 를 전량 재구성한다. `document_template` / `document_generation_type` 은 기존 `soft_delete` API 를 그대로 사용한다.

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | 변경 | 설명 |
|--------|------|------|------|
| PATCH | `/agents/{agent_id}` | **필드 추가** | `tool_ids`, `tool_configs` 수용 / 응답에 clamp 결과 추가 |

### 4.2 Detailed Specification

**Request — `UpdateAgentRequest` 추가 필드**

```python
# application/agent_builder/schemas.py
class UpdateAgentRequest(BaseModel):
    ...
    # agent-update-tool-editing D-1: None = 도구 변경 안 함,
    # [] = 사용자 선택 도구 전부 해제(빌트인은 규칙에 따라 재주입),
    # [...] = 목표 상태 전체 교체. 카탈로그 표기(internal:x / mcp:srv:tool) 수용.
    tool_ids: list[str] | None = None
    # None = 설정 변경 안 함. 전달된 도구만 tool_config 를 덮어쓰고,
    # 나머지 유지 도구는 기존 워커의 tool_config 를 승계한다 (D-2).
    tool_configs: dict[str, RagToolConfigRequest] | None = None
```

**Response — `UpdateAgentResponse` 추가 필드**

```python
class UpdateAgentResponse(BaseModel):
    agent_id: str
    name: str
    system_prompt: str
    updated_at: str
    # D-5: 도구 변경으로 scope clamp 가 발생했는지 사용자에게 알린다
    visibility: str = "private"
    visibility_clamped: bool = False
    max_visibility: str | None = None
```

**의미론 매트릭스**

| `tool_ids` | `tool_configs` | 동작 |
|---|---|---|
| `None` | `None` | 도구 구성 완전 무변경 (현행) |
| `None` | 값 | 무시 대신 **422** — 도구 목록 없이 설정만 오는 요청은 계약 위반 (원 결함의 재발 방지) |
| `[]` | 무관 | 사용자 선택 도구 전부 해제. 빌트인은 규칙대로 재주입 |
| `[...]` | `None` | 목표 상태 교체 + 유지 도구 설정 전량 승계 |
| `[...]` | 값 | 목표 상태 교체 + 전달된 도구만 설정 덮어쓰기 |

---

## 5. UI/UX Design

### 5.1 화면 변경 (AgentBuilderPage — 수정 모드)

기존 화면 구조 변경 없음. 저장 payload 와 프리필 정합만 손본다.

| 위치 | 변경 |
|---|---|
| `AgentBuilderPage/index.tsx:255-290` (수정 분기) | `tool_ids: mapCatalogToolIdsForSave(form.tools)`, `tool_configs` 추가 전송 |
| `agentDetailMapping.ts:63` | `mapDraftToolIdsToCatalog(detail.tool_ids, catalogTools)` 결과에서 빌트인을 제외해 `form.tools` 를 사용자 선택분만 담게 정리 (생성 폼과 동일 의미) |
| `LeftConfigPanel.tsx` | 변경 없음 — 빌트인 칩은 카탈로그 기반 렌더 유지 |
| 저장 결과 안내 | `visibility_clamped === true` 이면 "지식 범위 제한으로 공개 범위가 {visibility}로 조정되었습니다" 안내 추가 |

### 5.2 User Flow

```
수정 진입 → 상세 프리필(도구 칩 = 사용자 선택 도구)
  → 도구함에서 발표자료생성기 추가 → 양식(blueprint) 선택
  → 저장
     → PATCH { tool_ids: [...+internal:presentation_generator],
               presentation_generator: {...} }
     → 워커 재구성으로 presentation_generator 워커 생성
     → 바인딩이 그 워커에 tool_config 주입 → 200
  → "에이전트가 성공적으로 수정되었습니다"
```

### 5.3 Page UI Checklist

- [ ] 수정 모드에서 도구 추가 → 저장 → 재진입 시 칩이 유지된다
- [ ] 수정 모드에서 도구 삭제 → 저장 → 재진입 시 칩이 사라진다
- [ ] RAG 도구를 유지한 채 다른 도구만 바꿔도 RAG 설정 배지가 그대로다
- [ ] 발표자료생성기 신규 추가 + 양식 선택 저장이 성공한다
- [ ] clamp 발생 시 안내 메시지가 노출된다

---

## 6. Error Handling

### 6.1 Error Code Definition

| 상황 | 예외 | HTTP | 메시지 |
|---|---|---|---|
| 알 수 없는 tool_id | `ValueError` | 422 | `Unknown tool_id: '{id}'` |
| MCP 미등록·비활성 | `ValueError` | 422 | `등록되지 않았거나 비활성화된 MCP 도구입니다: {id}` |
| `mcp_server_repo` 미주입 상태에서 mcp_* 요청 | `ValueError` | 422 | `MCP 도구 수정 구성이 초기화되지 않았습니다 (mcp_server_repo 미주입).` |
| `tool_configs` 만 단독 전송 | `ValueError` | 422 | `tool_configs 는 tool_ids 와 함께 전달해야 합니다.` |
| 워커 개수 초과 | `ValueError` | 409 | 기존 `AgentBuilderPolicy` 메시지 (`"최대"` 포함 → 409 매핑) |
| KB 미존재 | `ValueError` | 422 | 기존 kb-rag-filter 메시지 |
| KB 읽기권한 없음 | `PermissionError` | 403 | 기존 메시지 |
| 발표자료 워커 부재 | `ValueError` | 422 | 기존 메시지 — **재구성 이후에도 부재하면** 진짜 계약 위반이므로 유지 |

### 6.2 Error Response Format

```json
{ "detail": "등록되지 않았거나 비활성화된 MCP 도구입니다: mcp:srv:tool" }
```

기존 `agent_builder_router.py:262-267` 매핑을 그대로 사용한다 (`찾을 수 없`→404, `이미 부착`/`최대`→409, 그 외 ValueError→422).

---

## 7. Security Considerations

| 항목 | 설계 |
|---|---|
| 권한 우회 | 도구 변경으로 KB/컬렉션 scope 가 바뀌므로 **매번 재해석 후 clamp**. 수정이 공개 범위를 우회해 넓히는 경로를 차단 |
| clamp 정책 | 명시적 `visibility` 요청은 기존대로 위반 시 **422 거부**(`_validate_visibility_scope`). `visibility` 미요청 + 도구 변경으로 인한 축소는 **자동 clamp + 응답 통지** (사용자가 의도치 않은 실패를 겪지 않게) |
| KB 읽기권한 | `_lookup_kb_scopes` 재사용 — 미존재 422 / 무권한 403 |
| 빌트인 우회 | 빌트인은 `exclude_builtin_tool_ids` 전용 채널로만 해제 가능. 수정 요청은 이 필드를 갖지 않으므로 **빌트인 강제 해제 불가** ([[builtin-tools-optout-channel]] 계약 유지) |
| 소유권 | 기존 `VisibilityPolicy.can_edit` 검사 유지 — 변경 없음 |

---

## 8. Test Plan

### 8.1 Test Scope

TDD 필수 (Red → Green → Refactor). 백엔드 pytest / 프론트 Vitest.

### 8.2 L1: API Test Scenarios (pytest, UseCase 단위 + 라우터)

| ID | 시나리오 | 기대 |
|---|---|---|
| T-01 | `tool_ids` 미전송 update | 워커 목록 변화 없음 (무회귀) |
| T-02 | 기존 도구 + 신규 `presentation_generator` 전송 + `presentation_generator` 설정 | 200, 새 워커에 tool_config 주입 |
| T-03 | 도구 1개 제거 | 해당 워커 소멸, 나머지 sort_order 0..N-1 재배치 |
| T-04 | RAG 유지 + 다른 도구 변경, `tool_configs` 미전송 | RAG `tool_config`(kb_id 포함) 승계 |
| T-05 | `tool_configs` 에 RAG 전달 | 전달값으로 교체 |
| T-06 | 문서생성기 제거 | `document_generation_type` soft_delete 1회 호출 |
| T-07 | 문서추출기 제거 | `document_template` soft_delete 1회 호출 |
| T-08 | 서브에이전트 보유 상태에서 도구 변경 | sub_agent 워커 보존 + sort_order 도구 뒤로 재배치 |
| T-09 | `tool_ids=[]` | 사용자 도구 0 + 빌트인만 재주입 |
| T-10 | 미지 tool_id | ValueError → 422 |
| T-11 | mcp:* 도구 추가 (활성 서버) | 워커 생성 + description 해석 |
| T-12 | mcp:* 도구 추가 (비활성 서버) | ValueError → 422 |
| T-13 | `mcp_server_repo` 미주입 + mcp_* | ValueError → 422 (500 아님) |
| T-14 | `tool_configs` 만 단독 전송 | ValueError → 422 |
| T-15 | 워커 상한 초과 | ValueError → 409 |
| T-16 | public 에이전트에 private KB 도구 추가 | visibility clamp + `visibility_clamped=true` |
| T-17 | worker_id 결정론 | 재구성 후에도 `{tool_id}_worker` 동일 |
| T-18 | 빌트인 재주입 | 사용자 선택과 중복 없이 1회만 |
| T-19 | 생성 경로 무회귀 | 빌더 추출 후 기존 create 테스트 전량 통과 |

### 8.3 L2: UI Action Test Scenarios (Vitest + MSW)

| ID | 시나리오 | 기대 |
|---|---|---|
| F-01 | 수정 모드 저장 payload | `tool_ids` 포함, 카탈로그→저장 표기 변환 확인 |
| F-02 | `tool_configs` 동봉 | RAG 설정 변경 시 함께 전송 |
| F-03 | 프리필 | `mapDetailToForm` 결과의 `form.tools` 에 빌트인 미포함 |
| F-04 | clamp 안내 | 응답 `visibility_clamped=true` 시 메시지 렌더 |

### 8.4 L3: E2E Scenario

수동 시나리오 (서버 기동 시): 발표자료생성기 미보유 에이전트 → 도구 추가 → 양식 선택 → 저장 성공 → 재진입 프리필 확인 → 실행 시 발표자료 노드 동작.

### 8.5 Seed Data Requirements

- 도구 워커 2개 + 서브에이전트 1개를 가진 기존 에이전트
- `document_generation_type` active 레코드를 가진 에이전트
- 활성/비활성 MCP 서버 각 1
- PERSONAL scope KB 1 + public 에이전트 1

---

## 9. Clean Architecture

### 9.1 Layer Structure

```
interfaces/  src/api/routes/agent_builder_router.py        (변경 없음)
application/ src/application/agent_builder/
               worker_skeleton_builder.py   [신규]
               create_agent_use_case.py     [빌더 호출로 치환]
               update_agent_use_case.py     [재구성 단계 추가]
               schemas.py                   [요청/응답 필드 추가]
domain/      src/domain/agent_builder/
               schemas.py                   [replace_tool_workers 추가]
               policies.py                  (재사용 — 변경 없음)
infrastructure/ agent_definition_repository.py             (변경 없음)
```

### 9.2 Dependency Rules

- `worker_skeleton_builder` 는 application 계층 — repository는 **인터페이스로 주입**받고 구현체를 import 하지 않는다.
- domain(`replace_tool_workers`)은 외부 의존 0 — 순수 리스트 조작.
- 도구 메타(`tool_registry`)는 domain 이므로 application 이 참조해도 방향 위반이 아니다.

### 9.4 This Feature's Layer Assignment

| 책임 | 계층 | 위치 |
|---|---|---|
| 도구 ID 정규화 / worker_id 생성 | application | `worker_skeleton_builder` |
| MCP·빌트인 description 해석 | application | `worker_skeleton_builder` (repo 주입) |
| 워커 컬렉션 불변식(순서·타입 분리) | domain | `AgentDefinition.replace_tool_workers` |
| 워커 개수 정책 | domain | `AgentBuilderPolicy.validate_worker_count` |
| visibility clamp 규칙 | domain | `VisibilityPolicy` |
| 종속 레코드 soft-delete 흐름 | application | `UpdateAgentUseCase._cleanup_removed_tool_deps` |
| 워커 row 영속 | infrastructure | `_sync_workers` (기존) |

---

## 10. Coding Convention Reference

### 10.4 This Feature's Conventions

- 함수 40줄 / if 중첩 2단계 준수 — 재구성 로직은 `_rebuild_tool_workers`, `_merge_tool_configs`, `_cleanup_removed_tool_deps` 로 분할한다.
- `print()` 금지, 구조화 로깅 필수 — 재구성 시 `added_tool_ids` / `removed_tool_ids` 를 `request_id` 와 함께 info 로깅.
- Repository 내부 commit 금지 — 종속 soft-delete 는 동일 세션 편승.
- 도구 ID 이중 네임스페이스 규칙 준수 (카탈로그 `internal:x` ↔ 저장 `x`) — [[agent-screens]].
- **추출 시 정합 정리 1건**: 현재 `_build_skeleton_from_configs`(`:311`)와 `_build_builtin_workers`(`:399`)는 `f"{tool_id}_worker"` 를 직접 쓰고 `_build_skeleton_from_tool_ids` 만 `sanitize_tool_name` 을 거친다. 공용 빌더에서는 `make_worker_id` 하나로 통일한다 (MCP 콜론 포함 ID 안전).

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt/
  src/application/agent_builder/
    worker_skeleton_builder.py         [신규 ~180줄]
    create_agent_use_case.py           [수정 — private 메서드 제거 + 빌더 위임]
    update_agent_use_case.py           [수정 — 재구성/종속정리/clamp 단계 추가]
    schemas.py                         [수정 — 요청 2필드 / 응답 3필드]
  src/domain/agent_builder/
    schemas.py                         [수정 — replace_tool_workers]
  src/api/main.py                      [수정 — DI 2종 추가]
  tests/application/agent_builder/
    test_worker_skeleton_builder.py    [신규]
    test_update_agent_tool_editing.py  [신규]
idt_front/
  src/types/agentBuilder.ts            [수정 — 요청/응답 타입]
  src/pages/AgentBuilderPage/index.tsx [수정 — 수정 payload]
  src/utils/agentDetailMapping.ts      [수정 — 빌트인 제외 프리필]
  src/pages/AgentBuilderPage/*.test.tsx [수정/신규]
```

### 11.2 Implementation Order

1. `worker_skeleton_builder.py` 추출 (행위보존) + 생성 경로 위임 → 기존 create 테스트 전량 통과 확인
2. `AgentDefinition.replace_tool_workers` + 유닛 테스트
3. `UpdateAgentRequest/Response` 필드 추가
4. `UpdateAgentUseCase` 재구성 단계 (재구성 → 종속정리 → clamp → 정책검증 → 바인딩)
5. `main.py` DI 배선
6. 프론트 타입 + payload + 프리필 + 테스트

### 11.3 Session Guide

**Module Map**

| Key | 모듈 | 파일 | 선행 | 예상 |
|---|---|---|---|---|
| `module-1` | 공용 빌더 추출 | `worker_skeleton_builder.py`, `create_agent_use_case.py` | — | ~250줄 |
| `module-2` | 도메인 + 스키마 | `domain/.../schemas.py`, `application/.../schemas.py` | — | ~60줄 |
| `module-3` | Update 재구성 파이프라인 | `update_agent_use_case.py` | m1, m2 | ~200줄 |
| `module-4` | DI 배선 | `api/main.py` | m3 | ~10줄 |
| `module-5` | 프론트 정합 | `agentBuilder.ts`, `index.tsx`, `agentDetailMapping.ts` | m3 | ~120줄 |

**Recommended Session Plan**

| 세션 | 스코프 | 명령 |
|---|---|---|
| S1 | 리팩토링 기반 | `/pdca do agent-update-tool-editing --scope module-1,module-2` |
| S2 | 핵심 로직 | `/pdca do agent-update-tool-editing --scope module-3,module-4` |
| S3 | 프론트 정합 | `/pdca do agent-update-tool-editing --scope module-5` |

**커밋 경계**: S1 은 동작 불변 리팩토링이므로 단독 커밋(`refactor`), S2 는 기능 추가(`feat`), S3 는 계약 동기화(`feat`).

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-06 | 초안 — Option C 선택, 6단계 파이프라인·의미론 매트릭스·19개 L1 시나리오 확정 | 배상규 |
