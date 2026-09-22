# approval-gate-phase2-mcp-executor Gap Analysis

> **Feature**: approval-gate-phase2-mcp-executor
> **Date**: 2026-09-22
> **Author**: 배상규
> **Design Doc**: [approval-gate-phase2-mcp-executor.design.md](../02-design/features/approval-gate-phase2-mcp-executor.design.md) (v0.2)
> **Plan Doc**: [approval-gate-phase2-mcp-executor.plan.md](../01-plan/features/approval-gate-phase2-mcp-executor.plan.md) (v0.2)
> **Method**: 정적(gap-detector) + 런타임(pytest 493건, Vitest 24건, 라이브 서버 L1 6건, 실 MCP 서버 PoC 1건)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 승인해도 MCP 도구가 실행되지 않고 `executed`로 기록되는 가짜 성공 + 신규 MCP 도구가 게이트 없이 시작하는 fail-open. |
| **WHO** | P2 에이전트 소유자 + 관리자 |
| **RISK** | "발송됐는지 모르는" 상태에서의 이중 집행. |
| **SUCCESS** | 승인된 MCP 도구가 정확히 1회 호출, 집행기 없는 도구는 `executed` 0건, 플래그 서버의 신규 도구는 `requires_approval=true`. |
| **SCOPE** | McpActionExecutor + 집행기 체인 + Mock 제거 + 서버 플래그(V075)·sync 초기값·등록 폼. |

---

## Strategic Alignment Check

### Plan 정렬

| 항목 | 결과 |
|------|------|
| WHY(가짜 성공 제거) | ✅ Mock이 src·main.py에서 제거되고 정적 테스트로 재유입 차단. 집행기 없음/도구 에러/연결 실패 어느 경우도 `executed`로 가는 경로 없음 |
| WHY(fail-open 제거) | ✅ 서버 플래그가 신규 엔트리 초기값으로 복사됨 — 라이브 서버에서 등록(플래그 true) 직후 auto-sync 성공 확인 |
| 일반화 원칙 | ✅ 집행기에 메일 지식 없음. `mcp:` 형식이면 도구 종류 무관하게 동일 경로 |

### Success Criteria Status

| SC | 상태 | 근거 |
|:--:|:--:|------|
| SC-1 실서버 1회 호출 | ✅ | **런타임 PoC**: `main._build_approval_executor()` 프로덕션 조립 그대로 Rate MCP(`localhost:8004`) `list_products` 집행 → `ok=True`, `call_tool` 호출 **1회**, 41개 상품 반환 |
| SC-2 집행기 없음=failed | ✅ | `test_executor_wiring.py` I1·I2 (decide·scheduler 양쪽 `failed`, `executed` 전이 없음) |
| SC-3 불가 사유 구분·호출 0회 | ✅ | `test_mcp_executor.py` TestBlocked 8케이스 |
| SC-4 출력 재개 주입 | ⚠️ | 경로 존재(`decide_use_case.py:199 _resume`), Phase 1 G1 종결됨. 에이전트 전 구간 E2E는 미수행 — 게이트가 걸린 에이전트가 로컬에 없음(카탈로그 15건 전부 `requires_approval=0`) |
| SC-5 플래그 → 신규 엔트리 | ✅ | S1 + 라이브 L1 A1 (등록 시 `tool_sync.ok=true`) |
| SC-6 재-sync 보존 | ✅ | S3·S4 + Phase 1 repo SQL 테스트 |
| SC-7 타임아웃 재호출 없음 | ✅ | E8 |
| SC-8 main.py Mock 없음 | ✅ | I4 정적 검사 |
| SC-9 프론트 왕복 | ✅ | U1~U5 + 라이브 L1 A1~A6 |

**8/9 ✅, 1/9 ⚠️** (SC-4는 구조적으로 충족, 전 구간 런타임만 미확인)

### Decision Record Verification

| D | 준수 | 비고 |
|:-:|:--:|------|
| D-01 MCPCallClient | ✅ | |
| D-02 list_tools→call_tool | ✅ | PoC에서 두 단계 모두 실행 확인 |
| D-03 래퍼 해제 | ✅ | |
| D-04 문구 3분류 | ✅ | 단 **G1**: 한 경로에서 분류가 역전됨 |
| D-05 멱등키 스키마 조건부 | ✅ | PoC: `list_products` 스키마에 없어 미주입 (정상) |
| D-06 Mock → tests/support | ✅ | |
| D-07 플래그 INSERT 전용·UI 꺼짐 | ✅ | |
| D-08 소유자 등록 | ✅ | |
| D-09 레거시 fail-closed | ✅ | |
| D-10 retry 0 코드 고정 | ✅ | E17 |
| D-11 예외 타입명만 | ✅ | E14 + `_exception_name` |

---

## 1. Analysis Overview

### 1.1 Purpose
Design v0.2 대비 5개 모듈(도메인 정책·집행기·배선·서버 플래그 BE·FE) 구현 일치 여부와 런타임 동작 검증.

### 1.2 Scope
백엔드 신규 4파일·수정 12파일, 프론트 4파일, 테스트 10파일. 범위 밖: 메일 MCP 서버, OAuth, 메일 특화 정책.

---

## 2. Gap Analysis

### 2.1 API Endpoints (§4)

| Endpoint | Design | 구현 | 라이브 검증 |
|----------|--------|------|------------|
| POST /api/v1/mcp-registry | `default_requires_approval: bool = False` | `schemas.py:27` | A1 201·true / A2 생략→false / A6 `{}`→422 |
| PUT /{id} | `bool \| None` | `schemas.py:43` | A3 플래그만→다른 필드 보존 / A4 생략→기존 유지 |
| GET | 응답 필드 | `schemas.py:68,120` | A5 전 항목 포함 |

**100%**

### 2.2 Data Model (§3)

| 항목 | 결과 |
|------|------|
| V075 DDL + COMMENT | ✅ 로컬 DB 적용 완료(`DEFAULT 0, NOT NULL`, 코멘트 일치) |
| `MCPServerModel.comment=` == DDL | ✅ 테스트로 고정 |
| `ActionExecutorInterface.execute(+idempotency_key)` | ✅ |
| `ExecutionFailurePolicy` / `McpArgumentPolicy` | ✅ domain 순수 |

**100%**

### 2.3 Component Structure (§9.4/§11.1)
15/15 존재. Mock은 src에 없음. **100%**

### 2.4 Functional Depth (FR-01~18)

18/18 구현. 부분 이행 2건:
- FR-05 "예외를 밖으로 던지지 않는다" — `client_factory(registration)` 호출(`mcp_executor.py:145`)이 try 밖 → **G1**
- FR-09 로깅 — `elapsed_ms` 누락 → **G2**

플레이스홀더 0건. **97%**

### 2.5 Page UI Checklist (§5.4)
7/7 (체크박스 기본 꺼짐·안내 2줄·수정모드 초기화·등록/수정 payload·뱃지·JobsPage 무변경). **100%**

### 2.6 API Contract
Design §4 ↔ pydantic ↔ `mcpServer.ts` ↔ MSW 4자 일치. 라우터가 application 스키마를 `response_model`로 직접 씀. **100%**

### 2.7 Runtime Verification Results

| Level | 대상 | 결과 |
|-------|------|------|
| Unit/Integration (BE) | approval·mcp_registry·tool_catalog·db·router | **493 passed** |
| Unit (FE) | AdminMcpServersPage·useMcpServers | **24 passed** |
| L1 API (라이브 8000) | A1~A6 | **6/6** (임시 서버 2건 생성 후 DELETE 204로 정리) |
| PoC (실 MCP) | SC-1 | **1/1** — 호출 정확히 1회 |
| 회귀 | 전체 백엔드 | 9,668 passed / 53 failed — 실패 9파일은 이 기능과 무관(parser·retriever·ES·API DI override). 변경 전 기준선 미확보 |

**Runtime 96%** (SC-4 전 구간 E2E 미수행 감점)

### 2.8 Match Rate Summary

| 축 | 점수 | 가중 |
|----|:----:|:----:|
| Structural | 100 | 0.15 |
| Functional | 100 (Act-1 후) | 0.25 |
| Contract | 100 | 0.25 |
| Runtime | 96 | 0.35 |
| **Overall** | **98% → Act-1 후 99%** | |

---

## 3. Gap List

| # | 심각도 | 신뢰도 | 내용 | 수정 |
|:-:|:---:|:---:|------|------|
| **G1** | **Important** | **확인됨** | Design §6.2 최상위 예외 경계 미구현. `client_factory(registration)`(`mcp_executor.py:145`, `MCPToolLoader._build_config` → smithery URL 조립)가 try 밖. **재현**: factory가 `ValueError`를 던지면 `McpActionExecutor.execute`가 예외를 전파 → Composite가 `[집행 여부 불명]`으로 기록. 실제로는 호출 0회이므로 `[집행 불가]`가 맞다 — "미발송 확실/불명" 경계가 역전. FR-05 미충족 경로 | `_connect`의 try에 factory 호출 포함 + 테스트 E18(factory raises → blocked, 호출 0회, 시크릿 비노출) |
| G2 | Minor | 상 | §10.4 로깅 규약 `elapsed_ms` 누락 (`mcp_executor.py:175-196`). §6.3 잠금 유지 시간 관찰 지표 | `_call`에 `perf_counter` 1줄 |
| G3 | Minor | 상 | §8.3 A1~A6가 TestClient가 아닌 UseCase 레벨. 라우터 왕복은 이번 라이브 L1로 수동 확인됐으나 자동화 미고정 | `test_mcp_registry_router.py`에 A1·A3 2건 (선택) |
| G4 | Minor | 상 | SC-4 전 구간(게이트→승인→집행→재개→답변) 런타임 E2E 미수행 — 로컬에 게이트 대상 에이전트 없음 | 관리자 토글로 `list_products`에 `requires_approval=1` → 단독 워커 에이전트 → 실행·승인 (QA 단계) |

Critical 없음.

---

## 4. Code Quality / Architecture / Convention

| 항목 | 결과 |
|------|------|
| 함수 40줄 | ✅ (ast 검사) |
| domain 외부 import | ✅ 0건 |
| `print()` | ✅ 0건 |
| Repository commit/rollback | ✅ 없음 (session-scoped 어댑터 재사용) |
| 시크릿·PII 로깅 | ✅ E14·E15 |
| 프론트 상수 export 규칙 | ✅ 리터럴만 |
| DDL COMMENT | ✅ `test_migration_ddl_comments` |

---

## 5. Test Coverage

Design §8.2 테스트 ID 대응: P 9/9, E 17/17(+2), C 4/4, S 4/4(+1), I 4/4, U 5/5, DDL ✅, config ✅(보너스). A1~A6는 레벨 상이(G3). 이 기능 신규 테스트 **총 93건**.

---

## 6. Intentional Deviations (갭 아님)

Design v0.2 Version History에 기록: V074→V075, `build_execution_client` 모듈 함수화, `_exception_name`, `_build_approval_executor` 헬퍼.

---

## 7. Overall

**Match Rate: 98%** — 목표 90% 초과. 권고: G1은 안전 속성(불가/불명 경계)이라 iterate로 즉시 수정, G2 동반 수정, G3·G4는 QA 단계.

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-09-22 | 초판 — 정적 97% + 런타임(L1 6, PoC 1) → 98%. G1~G4 |
| 0.2 | 2026-09-22 | Act-1: **G1·G2 수정 완료** — `_connect`가 client 조립 예외를 `[집행 불가]`로 변환(`mcp_executor.py`), E18·elapsed_ms 테스트 추가(303 passed). 재현 스크립트로 `[집행 불가] MCP 접속 설정 조립 실패 (ValueError)` 확인. Functional 97→100, Overall **99%**. 잔여: G3·G4 (QA) |
