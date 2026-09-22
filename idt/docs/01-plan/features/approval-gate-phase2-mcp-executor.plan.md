# approval-gate-phase2-mcp-executor Planning Document

> **Summary**: approval-gate Phase 1이 mock으로 남긴 집행 구간을 실제로 채운다. 승인된 MCP 도구를 재로드해 1회 호출하는 `McpActionExecutor`, "가짜 성공"을 만드는 Mock 폴백 제거, 그리고 새로 등록된 MCP 서버의 도구가 게이트 없이 시작하는 구멍(fail-open)을 서버 등록 플래그로 막는다. BYO 메일(자체 호스팅 MCP)이 첫 소비자지만 코어에는 메일 지식이 들어가지 않는다.
>
> **Project**: sangplusbot (idt)
> **Version**: —
> **Author**: 배상규
> **Date**: 2026-09-21
> **Status**: Draft (v0.1)

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 승인 게이트는 MCP 도구에도 걸리지만 집행기가 `MockActionExecutor` 하나뿐이라, 사람이 승인해도 **실제 도구는 호출되지 않은 채 `executed`로 기록된다**(조용한 가짜 성공). 또 MCP 서버는 사용자별로 등록되는데 sync가 만드는 카탈로그 엔트리는 `requires_approval=False`로 시작해, 새 BYO 사용자의 발송 도구는 관리자가 찾아서 켜기 전까지 **승인 없이 실행된다**. |
| **Solution** | ① `McpActionExecutor` — 승인된 `tool_id`·`tool_args`로 MCP 도구를 재로드해 **재시도 없이 1회** `ainvoke`하고 결과를 `ExecutionResult`로 정규화. ② 집행기 체인 — 지원 집행기가 없으면 `failed`(Mock은 프로덕션 배선에서 제거). ③ `mcp_server_registry`에 "이 서버 도구는 기본 승인 필요" 플래그를 두고 sync가 **신규 INSERT 때만** 초기값으로 사용(UPDATE는 관리자 값 보존). |
| **Function/UX Effect** | 승인 버튼이 실제 집행으로 이어진다 — 승인 → (예약 시각) → MCP 호출 → 결과가 런에 주입되어 재개. 집행 불가·실패는 작업함에 `failed` + 사유로 보인다. MCP 서버 등록 폼에 "기본 승인 필요" 체크박스 1개가 생기고, 켜 두면 그 서버의 새 도구는 처음부터 게이트 대상이다. |
| **Core Value** | **"승인됨"과 "실행됨"이 같은 뜻이 되게 한다.** 부작용 도구는 등록 순간부터 통제 아래 두고(fail-closed), 집행 경로는 도구 종류를 모르는 범용 구조로 유지한다 — 메일·슬랙·사내 시스템이 같은 길을 탄다. |

---

## Context Anchor

> Auto-generated from Executive Summary. Propagated to Design/Do documents for context continuity.

| Key | Value |
|-----|-------|
| **WHY** | 승인해도 MCP 도구가 실행되지 않고 `executed`로 기록되는 가짜 성공 + 신규 MCP 도구가 게이트 없이 시작하는 fail-open. |
| **WHO** | P2 에이전트 소유자(자기 MCP 서버 등록·자기 에이전트 승인) + 관리자(카탈로그 `requires_approval` 최종 통제) |
| **RISK** | 타임아웃·연결 끊김 시 **"발송됐는지 모르는" 상태에서의 이중 집행**. 그리고 Phase 1 미해결 Critical 갭(G1 재개 저장 실패, G5 tick 호출자 없음, G13 KST 9시간 오차) 위에 쌓는 위험. |
| **SUCCESS** | 승인된 MCP 도구가 **정확히 1회** 실제 호출되고, 집행기 없는 도구는 `executed`가 **0건**, 플래그를 켠 서버의 신규 도구는 sync 직후 `requires_approval=true`. |
| **SCOPE** | In: McpActionExecutor + 집행기 체인 + Mock 배선 제거 + 서버 등록 플래그(V075)·sync 초기값·등록 폼 필드. Out: 메일 MCP 서버 자체, OAuth, 메일 특화 정책, 내장 send_email, 승인 화면 발신 계정 표시, Phase 3 자동 승인. |

---

## 1. Overview

### 1.1 Purpose

approval-gate의 **"승인 → 집행"** 구간을 MCP 도구에 대해 실제로 동작시킨다. 동시에 부작용 MCP 도구가 등록 직후 게이트 밖에 놓이는 시간 창을 없앤다.

### 1.2 Background

- **요구의 출발점은 BYO 메일 발송**이다. 에이전트가 사용자 본인의 Gmail/Outlook 계정으로 메일을 보내야 하고, 이를 위해 자체 호스팅 메일 MCP 서버를 별도로 구축한다(이 Plan의 범위 밖). idt는 "MCP 도구를 승인 후 집행한다"까지만 알면 된다 — USER-SCENARIOS의 "일반화가 이긴다" 원칙.
- **MCP 구조는 이미 BYO에 맞다.** `mcp_server_registry`는 `user_id` + 암호화된 `auth_config_enc`를 가진 사용자별 테이블이고, 게이트 판정(`GatedWorkerPolicy.collect_gated_tool_ids` → `_catalog_key`)은 internal/MCP를 구분하지 않는다.
- **빠진 것은 집행이다.** `decide_use_case.py:181`과 `execute_scheduler.py:95`는 원래 도구가 아니라 `executor.execute()`를 부르고, `main.py:3110`의 executor는 `MockActionExecutor`(`supports()` 항상 True, 로그만 남기고 성공 반환)다. Phase 1 Plan FR-09가 "실도구는 Phase 2에서 구현체만 추가"로 미뤄둔 지점.
- **초기값 구멍.** `SyncMcpToolsUseCase`는 서버 등록 건마다 `mcp:{server.id}:{tool}` 엔트리를 만들고 `requires_approval`은 엔티티 기본값 `False`다. 이 값은 "관리자 지정값, sync가 덮지 않음"(FR-02)이라 BYO 사용자 N명이면 관리자가 N번 찾아 켜야 하고, 그 사이는 무승인 실행이다.

### 1.3 Related Documents

- Phase 1 Plan: `docs/01-plan/features/approval-gate.plan.md` (FR-02, FR-09, FR-10, FR-25)
- Phase 1 Design: `docs/02-design/features/approval-gate.design.md` (§2.3 집행기, §3.3 requires_approval)
- Phase 1 Analysis: `docs/03-analysis/approval-gate.analysis.md` (Match 83%, Critical G1·G2·G3·G13 + G5)
- 규칙: `docs/rules/tool-and-mcp.md` §3 (MCP 소비·session-scoped 어댑터), `docs/rules/db-session.md`, `docs/rules/logging.md`
- 위키: `docs/wiki/backend/patterns/mcp-runtime-tool-shape.md` (📝 draft — MCP 도구 런타임 이름 형태)

### 1.4 Prerequisites (선행 조건)

Phase 1은 아직 **check 단계(83%)·미커밋** 상태다. 이 사이클이 의미를 가지려면 아래가 먼저 닫혀야 한다.

| Phase 1 갭 | 이 사이클과의 관계 |
|-----------|-------------------|
| **G1** 재개 저장 실패(`SessionId("")`) | 집행 결과가 런에 주입돼도 최종 답변이 유실된다 → SC-4 검증 불가. **선행 필수** |
| **G5** tick 호출자 없음 / **G13** KST 9시간 오차 | 예약 집행 경로로는 MCP 집행기가 호출되지 않는다. 즉시 집행(`execute_after=null`)만으로도 이 사이클은 검증 가능 → **병행 가능, 단 예약 경로 SC는 G5·G13 종결 후 확인** |
| **G2** 관리자 `requires_approval` 토글 API 없음 | 이 사이클의 서버 플래그가 "켜는 길"을 하나 열지만, **끄기·개별 조정은 여전히 G2 필요**. 병행 가능 |
| **G3** 에이전트별 게이트 config 입구 없음 | 게이트 부착 자체는 `is_enforced` 또는 기존 적용 경로로 가능. 무관 |

> 권고: `/pdca iterate approval-gate`로 G1을 먼저 닫고 Phase 1을 커밋한 뒤 이 사이클의 Do에 들어간다.

---

## 2. Scope

### 2.1 In Scope

- [ ] `McpActionExecutor` (infrastructure/approval) — `ActionExecutorInterface` 구현. MCP tool_id 해석 → 서버 등록 조회 → 도구 로드 → 1회 `ainvoke` → `ExecutionResult`
- [ ] 집행기 체인(합성 집행기) — 등록된 집행기 중 `supports()` 첫 매치에 위임, 없으면 `ExecutionResult(ok=False)`
- [ ] `main.py` 배선 교체 — Mock을 프로덕션 DI에서 제거
- [ ] `mcp_server_registry.default_requires_approval` 컬럼 (Flyway V075 + 모델 `comment=`)
- [ ] MCP 서버 등록/수정 API에 필드 추가 + 프론트 타입·서비스·등록 폼 체크박스 (API 계약 동기화)
- [ ] `SyncMcpToolsUseCase` — 신규 엔트리 INSERT 시 서버 플래그를 `requires_approval` 초기값으로 사용
- [ ] 도구 특정 불가·서버 비활성·등록 삭제 등 집행 불가 상황의 fail-closed 처리

### 2.2 Out of Scope

- **메일 MCP 서버 자체** (Gmail/Outlook OAuth, 토큰 갱신, 발송 구현) — 별도 저장소에서 구축
- **OAuth를 idt 코어에 도입** — 자격증명은 MCP 서버가 소유, idt는 고정 헤더만 전달(`smithery_url.py:59`)
- **메일 특화 정책** (수신자 도메인 화이트리스트, 발송 상한, 인자 매핑 메타) — 사람 승인으로 시작, 필요 시 별도 사이클
- **내장 `send_email` 도구 / `EmailActionExecutor`** — 플랫폼 명의 발송 요구가 생기면 같은 체인에 추가
- **승인 화면에 발신 계정·MCP 서버명 표시** — 이번엔 제외(프론트 범위 최소화). Risk R-5로 기록
- **MCP annotation(`destructiveHint`) 기반 초기값** — 로더가 annotation을 전달하지 않음. 서버 플래그로 충분하다고 판단
- **Phase 1 갭 수정** (G1·G2·G3·G5·G13) — `approval-gate` 사이클의 iterate에서 처리
- **자동 승인 조건식** — Phase 3

---

## 3. Requirements

### 3.1 Functional Requirements

**A. MCP 집행기**

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `McpActionExecutor.supports(tool_id)` — `parse_mcp_tool_id(tool_id)`가 `None`이 아니면 True. internal 도구는 False | High | Pending |
| FR-02 | `execute()` — tool_id에서 `server_id`를 얻어 서버 등록을 조회하고 `MCPToolLoader.load()`로 도구 목록을 받은 뒤, `McpToolRef.tool_name`과 `tool.mcp_tool_name`이 일치하는 도구를 `ainvoke(tool_args)` 한다 | High | Pending |
| FR-03 | **도구 특정 불가 = 실패.** 레거시 `mcp_{uuid}`(tool_name 없음)인데 서버 도구가 2개 이상이거나, 이름이 일치하는 도구가 없으면 호출하지 않고 `ok=False`. 추측 호출 금지 (fail-closed) | High | Pending |
| FR-04 | **재시도 없음.** 집행 경로의 MCP 호출은 자동 재시도를 타지 않는다(`call_client`의 retry 등 우회 또는 0회 설정). Phase 1 FR-25와 동일 근거 — 비가역 작업의 재시도는 이중 집행 | High | Pending |
| FR-05 | 서버 등록 없음 / `is_active=False` / 연결 실패 / 타임아웃 / 도구가 에러 반환 → 전부 `ExecutionResult(ok=False, error_message=…)`. 예외를 밖으로 던지지 않는다(`decide_use_case._execute_now`는 예외를 가두지 않음) | High | Pending |
| FR-06 | 타임아웃·연결 끊김은 사유에 **"집행 여부 불명 — 대상 시스템 확인 후 재승인"**을 명시해 일반 실패와 구분한다 | High | Pending |
| FR-07 | 서버 등록 조회는 HTTP 요청 컨텍스트 없이 동작해야 한다(스케줄러 tick). `SessionScopedMcpServerRepository` 패턴 사용 — `get_session_factory()()` 직접 생성 금지 | High | Pending |
| FR-08 | 성공 시 `output`은 도구 반환값의 문자열화. 재개 주입용이므로 과대 출력은 상한으로 절단(상한은 config) | Medium | Pending |
| FR-09 | 집행 시작·성공·실패를 `request_id`·`tool_id`·`server_id`와 함께 구조화 로깅. **`tool_args` 본문은 로그에 남기지 않는다**(메일 본문 등 PII) — 키 목록만 | High | Pending |

**B. 집행기 체인**

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-10 | 합성 집행기 — 생성자에 집행기 목록을 받아 `supports()` 첫 매치에 위임. `ActionExecutorInterface`를 구현해 UseCase 쪽 코드는 변경 없음 | High | Pending |
| FR-11 | 매치되는 집행기가 없으면 `ExecutionResult(ok=False, error_message="지원 집행기 없음: {tool_id}")` → 상태 `failed`. **`executed`로 기록되는 경로가 없어야 한다** | High | Pending |
| FR-12 | `main.py` 프로덕션 배선에서 `MockActionExecutor` 제거. 클래스는 테스트 더블로만 유지(위치는 Design에서 결정) | High | Pending |

**C. 신규 MCP 도구 초기값**

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-13 | `mcp_server_registry.default_requires_approval BOOLEAN NOT NULL DEFAULT 0` 추가 — V075, 컬럼 COMMENT 필수, SQLAlchemy 모델 `comment=` 동일 반영. 기존 행은 0(무회귀) | High | Pending |
| FR-14 | `MCPServerRegistration` 도메인 스키마 + 등록/수정 UseCase + 라우터 요청·응답 스키마에 필드 추가. 미지정 시 False | High | Pending |
| FR-15 | `SyncMcpToolsUseCase` — 엔트리가 **신규 INSERT될 때만** `requires_approval = server.default_requires_approval`. 기존 엔트리 UPDATE는 현행대로 이 컬럼을 건드리지 않음(FR-02 관리자 값 보존) | High | Pending |
| FR-16 | 서버 플래그를 나중에 바꿔도 **이미 있는 엔트리는 소급 변경하지 않는다.** 소급이 필요하면 관리자 토글(G2) 경로 | Medium | Pending |
| FR-17 | 프론트: `types/mcpServer.ts`·`mcpServerService.ts`·`AdminMcpServersPage` 등록/수정 폼에 "이 서버의 도구는 기본으로 승인 필요" 체크박스. 안내 문구에 "이미 동기화된 도구에는 적용되지 않음" 명시 | High | Pending |

**D. 정책 명문화 (코드 변경 없음)**

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-18 | **발신 계정 = tool_id가 가리키는 서버 등록(에이전트 소유자의 것).** 실행자가 누구든 집행은 그 등록의 자격증명으로 나간다. 승인권자도 소유자뿐(`ApprovalPolicy.can_decide`)이라 "본인 계정 발송을 본인이 승인"하는 구조 — Design·위키에 결정으로 기록 | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 안전성 | 승인 1건당 MCP 도구 호출 **최대 1회** (재시도 0) | 집행기 단위 테스트: 실패·타임아웃 시 `ainvoke` 호출 횟수 == 1 |
| 안전성 | 집행기 없는 tool_id의 `executed` 전이 **0건** | 체인 단위 테스트 + decide/scheduler 통합 테스트 |
| 보안 | 로그·에러 메시지에 `tool_args` 값, `auth_config` 미노출 | `/verify-logging` + 로그 캡처 테스트 |
| 아키텍처 | domain → infrastructure 참조 0, Repository 내 commit/rollback 0 | `/verify-architecture` |
| 성능 | 집행 1건당 MCP 호출 타임아웃은 config 값(하드코딩 금지), 스케줄러 tick 한 건의 지연이 배치 전체를 막지 않음 | 기존 `execute_scheduler` 예외 격리 테스트 재사용 |
| 무회귀 | 기존 approval 테스트 전부 통과, 기존 MCP 서버·카탈로그 엔트리의 `requires_approval` 불변 | pytest FAILED diff 비교 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] **SC-1** 게이트된 MCP 도구를 승인(즉시 집행)하면 실제 MCP 서버에 호출이 **정확히 1회** 도달한다 — 실등록 MCP 도구로 PoC(`/verify-mcp-connections` + 승인 E2E)
- [ ] **SC-2** 지원 집행기가 없는 tool_id(예: 미구현 internal 도구)를 승인하면 `failed` + 사유가 기록되고 `executed`는 생기지 않는다
- [ ] **SC-3** 서버 비활성·등록 삭제·도구명 불일치·레거시 id 다중 도구 — 각 경우 호출 0회 + `failed` + 구분 가능한 사유
- [ ] **SC-4** 집행 성공 시 도구 출력이 재개 런에 주입되어 최종 답변까지 도달한다 *(Phase 1 G1 종결 전제)*
- [ ] **SC-5** `default_requires_approval=true`로 등록한 서버를 sync하면 새 엔트리 전부 `requires_approval=true`, 그 도구를 단독 워커로 가진 에이전트는 게이트가 부착된다
- [ ] **SC-6** 기존 엔트리에 대해 재-sync해도 관리자가 정한 `requires_approval` 값이 바뀌지 않는다 (플래그 true/false 양쪽)
- [ ] **SC-7** 타임아웃 시 재호출이 일어나지 않고, 사유에 "집행 여부 불명" 문구가 들어간다
- [ ] **SC-8** `main.py` 프로덕션 DI에 `MockActionExecutor` 참조가 없다
- [ ] **SC-9** 프론트 등록 폼에서 체크박스를 켜고 저장 → 재조회 시 값 유지 (타입·서비스·MSW 핸들러 동기화)
- [ ] TDD: 모든 신규 모듈에 테스트 선행 (`/verify-tdd`)

### 4.2 Quality Criteria

- [ ] 신규 모듈 테스트 커버리지 80% 이상
- [ ] `/verify-architecture`, `/verify-logging`, `/verify-tdd` 통과
- [ ] `tests/db/test_migration_ddl_comments.py` 통과 (V075 COMMENT)
- [ ] 함수 40줄·if 중첩 2단계 제한 준수
- [ ] 프론트 `npm run build`·Vitest 통과

---

## 5. Risks and Mitigation

| # | Risk | Impact | Likelihood | Mitigation |
|---|------|--------|------------|------------|
| R-1 | **집행 여부 불명 상태의 이중 집행** — 메일은 나갔는데 응답이 타임아웃 → `failed` → 사람이 재승인 → 2통 발송 | High | Medium | 자동 재시도 0(FR-04). 사유에 "불명" 명시(FR-06)로 사람이 대상 시스템을 먼저 확인하게 유도. 근본 해법은 MCP 서버의 멱등키 지원 — 서버 구축 시 계약으로 권고(§7.4), idt 쪽 전달은 Open Question Q-2 |
| R-2 | **Phase 1 미해결 갭 위에 쌓기** — G1 때문에 집행은 되는데 답변이 유실, G5 때문에 예약 집행이 영영 안 돎 | High | High | §1.4 선행 조건. Do 진입 전 G1 종결 확인. SC-4는 G1 의존으로 명시 |
| R-3 | **`call_client`·langchain MCP 어댑터 내부 재시도** — 우리가 모르는 층에서 재호출 | High | Medium | Design에서 호출 경로의 retry 설정을 코드로 확인하고, 집행 경로 전용으로 retry=0 구성. 호출 횟수 단위 테스트(NFR) |
| R-4 | **레거시 `mcp_{uuid}` tool_id** — 도구 이름이 없어 다중 도구 서버에서 집행 불가 | Medium | Medium | fail-closed(FR-03) + 사유에 "에이전트의 도구를 카탈로그 형식으로 다시 선택" 안내. 기존 에이전트에 레거시 id가 얼마나 남았는지 Design에서 DB 조회로 계량 |
| R-5 | **실행자 ≠ 발신자** — 공유·스토어 에이전트를 남이 실행해도 소유자 계정으로 발송 | Medium | Low | 승인권자가 소유자뿐이라 본인이 초안을 보고 승인(FR-18). 승인 화면 발신 계정 표시는 후속 사이클 후보로 기록 |
| R-6 | **사용자가 플래그를 끄고 등록** — BYO 사용자가 자기 발송 도구를 게이트 밖에 둠 | Medium | Medium | 최종 통제는 관리자 카탈로그 토글 + `is_enforced`(G2 종결 후). UI 기본값은 Open Question Q-1 |
| R-7 | **플래그 true 서버의 읽기 도구까지 게이트** — 단독 워커 제약(FR-05, Phase 1) 때문에 조회 도구 구성이 불편해짐 | Low | Medium | 서버 단위 초기값일 뿐, 관리자가 도구별로 해제 가능. MCP 서버 구축 시 읽기/쓰기 서버 분리 또는 도구 분리 권고(§7.4) |
| R-8 | **승인~집행 사이 서버 등록 변경** — 예약 대기 중 endpoint·토큰이 바뀌거나 삭제 | Medium | Low | 집행 시점의 등록을 그대로 사용(스냅샷 안 함 — 자격증명을 approval에 복제하지 않기 위함). 삭제·비활성은 FR-05로 failed |
| R-9 | **errno 3780 콜레이션** | Low | Low | 이번엔 FK·신규 테이블 없음(컬럼 추가만). 해당 없음 확인만 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `ActionExecutorInterface` 구현체 집합 | Infrastructure | `McpActionExecutor`, 합성 집행기 신규. 인터페이스 시그니처는 **변경 없음** |
| `main.py` approval DI (`:3100-3110`) | Wiring | `MockActionExecutor` → 합성 집행기(`[McpActionExecutor]`) |
| `mcp_server_registry` | DB Table | `default_requires_approval` 컬럼 추가 (V075) |
| `MCPServerModel` / `MCPServerRegistration` | Model / Domain Schema | 필드 추가 |
| MCP 레지스트리 등록·수정 API | API Schema | 요청·응답에 필드 추가 (선택, 기본 False) |
| `SyncMcpToolsUseCase` | Application | 신규 엔트리 초기값 로직 |
| `ToolCatalogRepository.upsert_by_tool_id` | Infrastructure | INSERT 분기에서 `requires_approval` 반영 여부 확인(UPDATE 분기는 불변) |
| `idt_front` `types/mcpServer.ts`, `services/mcpServerService.ts`, `AdminMcpServersPage` | Frontend | 필드·체크박스 추가 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| executor | EXECUTE | `application/approval/decide_use_case.py:181` `_execute_now` — **예외를 가두지 않음** | Needs verification — 집행기가 예외를 던지면 승인 API가 500. FR-05로 값 반환 강제 |
| executor | EXECUTE | `application/approval/execute_scheduler.py:95` — 예외 격리 있음 | None |
| executor | WIRING | `api/main.py:3100-3110` | Breaking(의도) — Mock 제거 |
| `MockActionExecutor` | TEST | `tests/infrastructure/approval/test_mock_executor.py`, approval 통합 테스트들의 픽스처 | Needs verification — 테스트 더블로 유지 시 import 경로 |
| `mcp_server_registry` | CREATE | `application/mcp_registry/register_mcp_server_use_case.py` | Needs verification — 새 필드 기본값 |
| `mcp_server_registry` | READ | `infrastructure/mcp_registry/mcp_server_repository.py` (모델↔도메인 매핑), `session_scoped_repository.py`, `load_mcp_tools_use_case.py`, `mcp_tool_loader.py` | Needs verification — 매핑 누락 시 항상 False |
| `mcp_server_registry` | READ | `document_extractor`의 `DocumentConversionAdapter`(session-scoped 조회) | None — 새 필드 미사용 |
| `SyncMcpToolsUseCase` | CALL | 부팅 sync + 서버별 재동기화 API(mcp-tool-auto-sync FR-11) | Needs verification — 두 경로 모두 신규 INSERT 초기값 적용 |
| `tool_catalog.requires_approval` | READ | `workflow_compiler.py:505`, `create_agent_use_case.py:328` (`GatedWorkerPolicy.validate`) | Needs verification — 플래그 true 서버의 도구를 **다른 도구와 같은 워커에 둔 기존 에이전트**는 없음(신규 엔트리만 영향)이나, 이후 그 도구를 추가하는 에이전트 생성은 단독 워커 제약에 걸림 → 에러 메시지 확인 |
| MCP 레지스트리 API | READ/WRITE | `idt_front/src/hooks/useMcpServers.ts`, `AdminMcpServersPage`, MSW 핸들러 | Needs verification — 선택 필드라 하위 호환 |

### 6.3 Verification

- [ ] 위 소비자 전부 변경 후 동작 확인
- [ ] `decide_use_case._execute_now` 경로에서 집행기 예외가 새지 않음을 테스트로 고정
- [ ] 기존 MCP 서버 행·기존 카탈로그 엔트리의 값 불변 확인 (마이그레이션 전후 조회)
- [ ] API 계약: 백엔드 스키마 ↔ `idt_front/src/types/mcpServer.ts` 동기화 (`/api-contract-sync`)

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules, BaaS | Web apps with backend | ☐ |
| **Enterprise** | Strict layer separation, DI | Complex architectures | ☑ |

기존 Thin DDD(domain → application → infrastructure → interfaces) 그대로. 아키텍처·레이어 변경 없음.

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 메일 발송 구현 위치 | 내장 도구+전용 노드 / 내장 도구+집행기 / **MCP** | **MCP (BYO, 자체 호스팅)** | 요구가 "사용자 본인 계정 발송". 사용자별 자격증명·프로바이더 분기·OAuth를 코어에 넣지 않는다. `mcp_server_registry`가 이미 사용자별 |
| 집행 경로 | 도구별 전용 집행기 / **범용 MCP 집행기** | **범용** | 메일 지식 없이 모든 승인 대상 MCP 도구가 공유. "일반화가 이긴다" |
| 집행기 없음 처리 | Mock 폴백 유지 / config로 dev만 / **failed** | **failed** | 가짜 성공 제거. 비가역 작업에서 "안 됐는데 됐다고 기록"이 최악 |
| 초기값 결정 | **서버 등록 플래그** / MCP annotation / 둘 다 | **서버 등록 플래그** | 규칙 1개. 로더 변경 불필요. 외부 서버에도 동일 적용 |
| 초기값 적용 시점 | 매 sync 덮어쓰기 / **신규 INSERT만** | **신규 INSERT만** | Phase 1 FR-02 "sync는 관리자 값을 덮지 않는다" 보존 |
| 발신 계정 | **소유자 등록** / 실행자≠소유자 거부 / 실행자 등록으로 치환 | **소유자 등록** | 승인권자=소유자. 추가 코드 없음. 공유 에이전트의 부작용 도구를 막지 않음 |
| 자격증명 스냅샷 | 승인 시 복제 / **집행 시 조회** | **집행 시 조회** | 암호화 자격증명을 approval 행에 복제하지 않는다 |
| 재시도 | 자동 / **없음** | **없음** | Phase 1 FR-25 동일 근거 |

### 7.3 Clean Architecture Approach

```
Selected Level: Enterprise (Thin DDD, 기존 구조)

domain/approval/interfaces.py          ActionExecutorInterface (변경 없음)
domain/tool_catalog/mcp_tool_id.py     parse_mcp_tool_id (재사용)
domain/mcp_registry/schemas.py         MCPServerRegistration + default_requires_approval

application/tool_catalog/
  sync_mcp_tools_use_case.py           신규 엔트리 초기값
application/mcp_registry/
  register_mcp_server_use_case.py      필드 전달

infrastructure/approval/
  mcp_executor.py          [신규]      McpActionExecutor
  composite_executor.py    [신규]      합성 집행기 (이름은 Design에서 확정)
  mock_executor.py                     프로덕션 배선에서 제거 (테스트 더블)
infrastructure/mcp_registry/
  models.py                            컬럼 + comment=
  mcp_server_repository.py             매핑
  session_scoped_repository.py         집행기가 재사용

api/main.py                            approval DI 교체
api/routes (mcp-registry)              요청·응답 스키마

db/migration/V075__add_default_requires_approval_to_mcp_server_registry.sql
```

의존 방향: `McpActionExecutor`(infra) → `MCPToolLoader`(infra) + `parse_mcp_tool_id`(domain) + `ActionExecutorInterface`(domain). domain → infra 참조 없음.

### 7.4 MCP 서버 구축 측 권고 계약 (참고 — 범위 밖)

별도 구축할 메일 MCP 서버가 아래를 지키면 idt 쪽 통합이 매끄럽다.

- **인증은 만료 없는 고정 헤더.** idt는 `auth_config.headers`를 그대로 싣기만 한다. OAuth 갱신은 서버 내부에서
- **읽기/쓰기 도구 분리.** `send_email`은 단독 도구로. 단독 워커 제약 때문에 `manage_mail(action=…)` 식으로 합치면 읽기까지 승인 대상이 된다
- **평평한 인자**(`to`, `cc`, `subject`, `body`) — 승인 화면이 `tool_args`를 그대로 보여준다
- **멱등키 인자 수용**(선택적 파라미터) — R-1의 근본 해법
- **구조화된 에러** — "재연결 필요(동의 철회·토큰 폐기)"와 일반 실패 구분

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md` 3종 (루트 / idt / idt_front)
- [x] `idt/docs/rules/` — db-session, logging, tool-and-mcp, testing
- [x] DDL COMMENT 규칙 + `tests/db/test_migration_ddl_comments.py`
- [x] 프론트: 컴포넌트 파일에서 런타임 상수 export 금지, `as const`는 `src/types/*.ts`

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| 집행 경로 MCP 호출의 retry 정책 | 미정의 (`call_client`에 retry 존재) | 집행 경로는 retry 0 — Design에서 실제 호출 층 확인 후 규칙화 | High |
| 집행 로그의 PII | logging 규칙은 있으나 `tool_args` 언급 없음 | 값 미기록, 키 목록만 | High |
| 실패 사유 문구 | Phase 1은 자유 문자열 | 최소한 "불명/불가/실패" 3분류 접두 — Design에서 확정 | Medium |

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| (집행 MCP 호출 타임아웃) | 집행 1건 상한 | Server | Design에서 결정 — 기존 `MCPTimeoutConfig` 재사용 가능하면 신설 안 함 |
| (집행 출력 절단 상한) | 재개 주입 크기 제한 | Server | Design에서 결정 — Phase 1 `MAX_SNAPSHOT_BYTES` 계열과 정렬 |

신규 시크릿 없음. `.env.example` 변경은 위 두 값이 신설될 때만.

### 8.4 Pipeline Integration

해당 없음 (9-phase 파이프라인 미사용, PDCA 단독).

---

## 9. Open Questions (Design에서 결정)

| # | 질문 | 메모 |
|---|------|------|
| Q-1 | 등록 폼 체크박스의 **UI 기본값** — 꺼짐(무회귀) vs 켜짐(fail-closed) | API/DB 기본은 False로 확정. UI만 켜짐으로 두면 새 등록은 안전 쪽에서 시작하지만, 검색용 MCP 서버까지 단독 워커 제약에 걸린다(R-7) |
| Q-2 | `idempotency_key`를 MCP 도구에 **전달할 것인가** | `ActionExecutorInterface.execute` 시그니처에 키가 없다 → 전달하려면 Phase 1 인터페이스 변경. 그리고 도구 input schema에 없는 인자를 넣으면 검증 실패 가능 → "스키마에 해당 파라미터가 있을 때만 주입" 방식 검토 |
| Q-3 | 레거시 `mcp_{uuid}` id의 **호출 도구명 복원** | 게이트 미들웨어가 `request.tool_call["name"]`(UUID 접두 합성명)을 추가로 기록하면 복원 가능. 이번엔 fail-closed로 두고 잔존량 계량 후 판단 |
| Q-4 | `MockActionExecutor`의 거처 | `infrastructure/approval`에 남기되 미배선 vs `tests/` 픽스처로 이동. CLAUDE.md "spec에 없는 기능 금지"·dead code 관점 |
| Q-5 | 집행 경로가 `MCPToolLoader.load()`를 쓸지 `call_client`를 직접 쓸지 | 재시도 통제(R-3)와 호출 횟수 검증 용이성 기준으로 선택 |

---

## 10. Next Steps

1. [ ] **선행**: `/pdca iterate approval-gate` — 최소 G1 종결, Phase 1 커밋
2. [ ] `/pdca design approval-gate-phase2-mcp-executor` — 3안 비교, Q-1~Q-5 결정
3. [ ] 실등록 MCP 도구로 집행 PoC (`/verify-mcp-connections`)
4. [ ] TDD로 구현 (domain 스키마 → 집행기 → 체인 → sync → API → 프론트)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-21 | Initial draft — 범위(집행기+폴백+초기값), 서버 등록 플래그, 집행기 없음=failed, 발신 계정=소유자 등록 확정 | 배상규 |
| 0.2 | 2026-09-21 | 마이그레이션 번호 V074→V075 (V074 는 approval-gate iterate 가 선점). §1.4 선행 조건 G1·G2·G3·G5·G13 종결 확인 | 배상규 |
