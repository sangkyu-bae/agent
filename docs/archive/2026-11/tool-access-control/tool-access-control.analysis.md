# tool-access-control Analysis Report

> **Feature**: tool-access-control (부서·사용자별 도구 권한)
> **Date**: 2026-11-04
> **Analyzer**: gap-detector(정적 대조, 독립 실행) + 메인 세션(성공 기준·런타임·지적 사항 재확인)
> **Design**: [tool-access-control.design.md](../02-design/features/tool-access-control.design.md) v0.5
> **Plan**: [tool-access-control.plan.md](../01-plan/features/tool-access-control.plan.md) v0.2
> **Code**: worktree `wt/tool-access-control` (브랜치 `feature/tool-access-control`, 미커밋)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 도구 선택·실행에 부서·사용자 조건이 없어 권한과 관계없이 누구나 도구를 통해 자료에 접근한다. |
| **WHO** | P3 시스템 관리자(권한 지정), P2 에이전트 소유자(허용된 도구로 구성·배포), P1·P4 실행 사용자(허용된 도구만 사용). |
| **RISK** | 기본 차단 전환으로 기존 에이전트 도구가 일제히 막히는 회귀, 실행 경로 중 판정이 빠진 우회로(서브에이전트·빌트인 주입·서버 단위 MCP 참조·포크), 도구 ID 이중 네임스페이스로 인한 판정 불일치. |
| **SUCCESS** | 배포 직후 기존 에이전트 동작 변화 0건(기본 세트 시드), 권한 없는 도구가 목록·저장·실행 어느 경로로도 쓰이지 않음(실행 경로 전수 테스트), MCP 레지스트리 무인증 호출 401. |
| **SCOPE** | M1 판정 기반 → M2 관리 API·인증 → M3 목록·저장·포크 → M4 실행 필터 → M5 관리자 화면 → M6 빌더·채팅 표시 (6모듈 전부 구현) |

---

## Strategic Alignment Check

### 핵심 문제 대비 (PRD 없음 — Plan Executive Summary 기준)

| 요소 | 기대 | 상태 |
|------|------|:----:|
| WHY: 권한과 무관한 도구 접근 차단 | 목록·저장·실행 모든 경로에서 실행자 기준 판정 | ⚠️ **일반 채팅 경로 누락** (G-01) |
| WHO: 관리자가 화면에서 부서·사용자 권한 지정 | `/admin/tool-access` 3탭 | ✅ 브라우저 확인 |
| 가치: 전 부서 배포 시에도 데이터로 운영 | 기본 세트 + 부서 + 사용자, 코드 수정 없음 | ✅ |

> **전략적 불일치 1건(Critical)**: Design §0 은 실행 경로를 `RunAgentUseCase` 호출자 기준으로만 전수 조사했다. 에이전트를 거치지 않는 **일반 채팅(General Chat)** 은 별도 UseCase 로 Tavily·내부 문서 검색·**등록된 모든 MCP 도구**를 바인딩하며 도구 권한 판정이 없다. 메인 채팅("SUPER AI 에이전트")이 이 경로라 일반 사용자 노출 범위가 가장 넓다.

### Success Criteria Status (Plan §4)

| # | 기준 | 상태 | 근거 |
|---|------|:----:|------|
| SC-1 | FR-01~17 구현 + 테스트 | ✅ | gap-detector FR 대조, 신규 테스트(백엔드 tool_access·agent_builder·api, 프론트 hooks·components·pages) |
| SC-2 | 실행 경로 5종 + 서브에이전트에서 미바인딩 (컴파일 그래프 기준) | ⚠️ | 에이전트 실행 8경로는 단일 조립점 주입(`main.py:3323`) + AST 계약 테스트 + 컴파일 그래프 테스트 11건 + 실런(REST·WS). **일반 채팅 경로 미적용(G-01)**. 웹훅·잡·스케줄·RAGAS 는 공통 `_prepare_graph` 단위 테스트로만 검증 |
| SC-3 | 시드 후 기존 에이전트 바인딩 변화 0건 | ⚠️ | 로컬 MySQL: 카탈로그 37 = 기본 세트 37, 시드 직후 일반 사용자 카탈로그 37건(스모크). 전용 동치 테스트(R13)는 없음 |
| SC-4 | 백엔드↔프론트 타입 동기화 | ✅ | `types/toolAccess.ts`·`agentStore.ts`·`websocket.ts`·`chat.ts` (Contract 97) |
| SC-5 | 배포 의존성 문서 반영 대상 기록 | ⚠️ | V082/V083 을 `ops/migration-deploy-deps.md` 에 넣을 항목으로만 기록 — 위키 갱신은 `/wiki update` 호출 시 |
| SC-6 | 수동 E2E 1회 (부서 허용→노출, 해제→실행 제외) | ✅ | 브라우저: 관리자 화면·빌더 "권한 없음" 칩·채팅 안내 실런. API 스모크: 기본 세트 제외→카탈로그 36건, 사용자 허용→재노출, 생성·수정 403, 포크 제외 |
| QC-1 | 신규 코드 커버리지 80% | ❓ | 미측정 |
| QC-2 | 신규 실패 0건 (FAILED diff), 프론트 tsc·lint·vitest | ✅ | 백엔드 53건 = master 상시 실패 동일. 프론트 vitest 9건 동일(1,614→1,655 통과), tsc 49종 동일, eslint 34건 동일(줄 이동만). `tsc -b` 는 미실행(`-p tsconfig.app.json --noEmit`만) |
| QC-3 | DDL 검사 통과 | ✅ | `tests/db` 10건 + 로컬 MySQL 적용(errno 3780 없음, FK·CASCADE 확인) |

**Success Rate**: 5/9 ✅, 3/9 ⚠️, 1/9 ❓ (Critical 위반 1건 — SC-2)

### Decision Record Verification

| 출처 | 결정 | 준수 | 비고 |
|------|------|:----:|------|
| Plan | 부서 + 사용자 합집합, deny 없음 | ✅ | `ToolAccessPolicy.build` |
| Plan | 기본 차단 + 살아있는 기본 세트, 현재 도구 전부 시드 | ✅ | V083 |
| Plan | 목록·저장·실행 3지점 판정 | ⚠️ | 일반 채팅 실행 경로 누락 (G-01) |
| Plan | 권한 없는 도구는 빼고 실행 + 안내 | ✅ | compile 필터 + 안내 블록 + `excluded_tools` |
| Plan | 저장은 신규 추가 도구만 검증 | ✅ | `update_agent_use_case.py:339-356` |
| Plan | 포크는 제외 복제 | ✅ | `fork_agent_use_case.py` |
| Design | 설계안 C (정책 1 + Resolver 1, compile 첫머리 필터) | ✅ | `workflow_compiler.py:653-667` |
| Design | 테이블 3개 + FK CASCADE, tool_catalog 컬럼 추가 없음 | ✅ | V082, 로컬 CASCADE 확인 |
| Design | auth_ctx 없는 경로는 user_id 로 판정 | ✅ | `_resolve_tool_access` |
| Design | 승인 집행 직전 재확인 | ✅ | `composite_executor.py:54` |
| Do | MCP 레지스트리 조회도 admin (사용자 결정) | ✅ | 라우터 단위 의존성 |

---

## 1. Analysis Overview

- 정적 대조: gap-detector 가 Design §3~§12 와 worktree 코드를 독립적으로 읽어 판정(메인 세션의 결론을 주지 않음).
- 런타임: Do 단계에서 실행한 인프로세스 스모크 3회(관리 API, 목록·저장·포크, 실런 REST/WS) + 브라우저 확인 1회를 런타임 근거로 쓴다. 이번 Check 에서 새로 서버를 띄우지는 않았다.
- 메인 세션 재확인: gap-detector 지적 중 Critical·Important 2건을 코드로 직접 확인함(아래 ✔).

## 2. Gap Analysis

### 2.1 점수

| 축 | 점수 | 근거 |
|----|:----:|------|
| Structural | 96 | Design §3.3·§4.1·§5.3·§9.1·§11.1 항목 존재 (마이너: `_catalog_tool_id` 미위임) |
| Functional | 80 | 에이전트 경로 FR 전부 구현. 일반 채팅 경로 판정 없음(Critical)으로 감점 |
| Contract | 97 | 백엔드 스키마 ↔ 프론트 타입 ↔ 서비스 호출 일치 (마이너: 표시 이름에 카탈로그 이름 미사용) |
| Runtime | 90 | 실행한 스모크·실런·브라우저 시나리오 전부 통과. 일반 채팅·스케줄·승인 재개·RAGAS 는 실런 미실시 |

**Match Rate (runtime 포함 공식)** = 96×0.15 + 80×0.25 + 97×0.25 + 90×0.35 = **90.2%**

> 수치는 90% 기준을 넘지만, SC-2 위반(일반 채팅 우회로)은 전략적 불일치라 수치와 무관하게 Critical 로 다룬다.

### 2.2 Gap 목록

| ID | 심각도 | 확신 | 내용 | 근거 | 재확인 |
|----|--------|:----:|------|------|:------:|
| G-01 | **Critical** | 90% | 일반 채팅(REST `/api/v1/chat`, WS `/ws/chat`)이 Tavily·내부 문서 검색·등록된 모든 MCP 도구를 권한 판정 없이 바인딩. `_tool_filter` 는 질의 관련도 추천기일 뿐 권한 필터가 아님 | `idt/src/application/general_chat/tools.py:103-109`, `general_chat/use_case.py:444-456` | ✔ |
| G-02 | Important | 80% | 자동 빌더 `/api/v3/agents/auto` 무인증 + `tool_ids` 권한 판정 없이 레거시 v2 에이전트 저장. 실행 경로(`/api/v2/agents`)는 admin 잠금이라 도구 실행은 막히지만, 무인증 LLM 호출·데이터 저장이 가능 | `idt/src/api/routes/auto_agent_builder_router.py:16,36-60` | ✔ |
| G-03 | Minor | 85% | 반복 한도 강등 답변(degraded) payload 에 `excluded_tools` 누락 | `run_agent_use_case.py:740` vs `:469` | |
| G-04 | Minor | 90% | `update_agent_use_case._catalog_tool_id` 가 도메인 정규화(`to_catalog_tool_id`)에 위임하지 않고 규칙 사본 유지 (Design §3.2) | `update_agent_use_case.py:85-89` | |
| G-05 | Minor | 85% | 제외·상세 표시 이름에 카탈로그 이름을 쓰지 않음(MCP 는 원 도구명). Design §4.2 는 카탈로그 우선 | `run_agent_use_case.py:470`, `get_agent_use_case.py:186`, `fork_agent_use_case.py:148` | |
| G-06 | Minor(문서) | 95% | V082 는 위키 규칙대로 CHARSET 생략, Design §3.3 DDL 예시는 `DEFAULT CHARSET=utf8mb4` 포함 — Design 문구 정정 대상 | `V082__create_tool_access_tables.sql` | |
| G-07 | Minor | 70% | 승인 재개 답변은 `excluded_sink` 를 넘기지 않아 제외 안내 없음(필터 자체는 적용) | `run_agent_use_case.py:1335` | |

수용된 차이(Version History 기록, Gap 아님): "미지정(차단)"→"기본 세트 아님" 배지, 채팅 안내는 실시간 답변만, FR-11 실행 기록은 구조화 로그, 빌더 테스트 패널(TestChatView) 안내 미표시.

### 2.3 미검증·테스트 공백

- R2 웹훅·R3 잡·R4 스케줄·R6 RAGAS: 경로별 전용 테스트 없음 — 공통 `_prepare_graph` 단위 테스트 + 단일 조립점 배선 테스트로 대신함.
- R13 시드 동치 전용 테스트 없음 (로컬 DB 수치 확인만).
- R12 승인 거부 시 `blocked` 종류·failed 전이 단언 없음.
- L1-6·7 `/tool-catalog` 라우터 수준 테스트 없음 (UseCase·스모크만). L1-10·12 라우터 수준 없음.
- FR-17 CASCADE: 로컬 MySQL 스크립트로 확인, 자동 테스트 없음 (SQLite 는 FK 미강제).
- 커버리지 미측정, `tsc -b` 미실행.

## 3. 권장 조치

| 우선 | 조치 | 크기 |
|------|------|------|
| 1 | **G-01** 일반 채팅 도구 바인딩에 실행자 `ToolAccessSet` 적용 (`ChatToolBuilder.build` 에서 Tavily·내부 문서·MCP 각각 `allows` 판정, `general_chat` DI 에 Resolver 주입, 배선 계약 테스트) | 소형 |
| 2 | **G-02** `/api/v3/agents/auto` 라우터 admin 잠금 (v2 와 동일 방식) | 매우 작음 |
| 3 | G-03·G-05·G-07 표시 보강 (degraded payload, 카탈로그 이름, 재개 안내) | 소형 |
| 4 | G-04 위임 1줄, G-06 Design 문구 정정 | 매우 작음 |
| 5 | 테스트 공백 보강 (R13 시드 동치, R12 단언, 카탈로그 라우터) | 선택 |

## 4. Act-1 결과 (2026-11-04, 사용자 결정: Critical·Important·Minor 모두 수정)

| ID | 결과 | 근거 |
|----|:----:|------|
| G-01 | ✅ 수정 | `GeneralChatUseCase._permitted_tools` — 도구 빌드 직후·관련도 선별 전에 실행자 `ToolAccessSet` 판정(auth_ctx → for_auth_ctx, 없으면 user_id, 실패 시 도구 0개). 도구 id 는 tool-recommender `DefaultToolIdResolver` 재사용. `main.py` 생성 호출부 AST 계약 테스트 + REST·WS 공용 팩토리 확인. 실런: 기본 세트에서 서버 도구를 뺀 뒤 일반 사용자 21개·관리자 25개 바인딩 |
| G-02 | ✅ 수정 | `/api/v3/agents/auto` 라우터 단위 admin 잠금, 인증 계약 테스트(`test_admin_only_routers_auth.py`) 대상에 추가 |
| G-03 | ✅ 수정 | `_StreamState.excluded_workers` 로 정상·강등 답변이 같은 목록 사용 (`_excluded_payload`) |
| G-04 | ✅ 수정 | `_catalog_tool_id` → `to_catalog_tool_id` 위임 |
| G-05 | ➖ 변경 불필요 | 카탈로그 이름 = MCP 도구명(`sync_mcp_tools_use_case.py:59`), 내부 도구 = 레지스트리 이름, 이름 변경 API 없음 → 표시 차이 0 |
| G-06 | ✅ 수정 | Design §3.3 DDL 예시를 CHARSET 생략으로 정정 |
| G-07 | ⏸ 보류 | 승인 재개 답변은 저장만 되는 경로라 안내를 실을 응답이 없음 (Design v0.6 기록) |

### 4.1 Act-1 중 새로 발견 — G-08 (Important, 운영)

일반 채팅 실런에서 관리자에게만 Doc Convert MCP 도구 4개가 바인딩됐다. 원인: **MCP 서버는 등록됐지만 카탈로그 동기화가 한 번도 안 된 서버**(Doc Convert MCP 0건, Naver Search 0건)는 V083 시드에 포함되지 않는다. 일반 채팅은 카탈로그와 무관하게 서버에서 도구를 바로 불러오므로 배포 직후 일반 사용자가 이 도구들을 잃는다(SC-3 "동작 변화 0" 위반 가능). 카탈로그에 없으면 관리자 화면에서 권한을 줄 수도 없다.

- **결정(사용자)**: 배포 절차로 해결 — **배포 전 MCP 서버 전체 동기화 → 배포(V083 시드)** 순서. 코드 변경 없음.
- **로컬 DB 조치**: 두 서버 동기화(Doc Convert 4건, Naver Search 0건 — 서버가 도구를 돌려주지 않음) 후 Doc Convert 4건을 기본 세트에 추가(관리자 API). 기본 세트 37 → 41.
- **Report·배포 체크리스트에 반드시 기재**.

### 4.2 재측정

| 축 | Act-1 전 | Act-1 후 | 근거 |
|----|:----:|:----:|------|
| Structural | 96 | 97 | G-04 |
| Functional | 80 | 95 | G-01·G-02·G-03 수정, G-07 보류 |
| Contract | 97 | 98 | G-03 payload 일관 |
| Runtime | 90 | 92 | 일반 채팅 실런 추가 통과, G-08 은 운영 절차로 처리 |

**Match Rate** = 97×0.15 + 95×0.25 + 98×0.25 + 92×0.35 = **95.0%**

회귀: 백엔드 53건 실패 = 상시 실패 목록 동일(통과 11,441). 프론트는 Act-1 변경 없음(이전 회귀 그대로).

SC-2 → ✅ (에이전트 8경로 + 일반 채팅 REST·WS), SC-3 → ⚠️ 유지(배포 절차 G-08 이행 전제, 전용 동치 테스트 없음).

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-11-04 | 최초 분석 — Match 90.2%, Critical 1 (일반 채팅 경로), Important 1 (자동 빌더 무인증) |
| 0.2 | 2026-11-04 | Act-1 — G-01~G-04·G-06 수정, G-05 변경 불필요, G-07 보류, 신규 G-08(미동기화 MCP 서버 → 배포 절차) — Match 95.0% |
