# approval-gate-phase2-mcp-executor Completion Report

> **Status**: Complete
>
> **Project**: sangplusbot (idt + idt_front)
> **Version**: —
> **Author**: 배상규
> **Completion Date**: 2026-09-22
> **PDCA Cycle**: #1 (Act-1 iteration 1회)

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | approval-gate-phase2-mcp-executor — 승인 게이트 Phase 2: MCP 집행기 + 서버 등록 플래그 |
| Start Date | 2026-09-21 |
| End Date | 2026-09-22 |
| Duration | 2일 (Plan·Design·Do 5모듈·Check·Act-1) |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Completion Rate: 100% (FR) / 99% (Match)    │
├─────────────────────────────────────────────┤
│  ✅ Complete:     18 / 18 FR                 │
│  ✅ Success Criteria: 8 / 9 Met, 1 Partial   │
│  ⏳ Carried over:  2 Minor gaps (G3·G4)      │
│  ❌ Cancelled:     0                         │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 승인 게이트가 MCP 도구에 걸려도 집행기가 `MockActionExecutor` 하나뿐이라 승인 후 **실제 호출 없이 `executed`로 기록**됐다. 또 사용자별로 등록되는 MCP 서버의 새 도구는 `requires_approval=0`으로 시작해 관리자가 켜기 전까지 **승인 없이 실행**됐다. |
| **Solution** | `McpActionExecutor`(list_tools 검증 → call_tool 1회, 재시도 0) + `CompositeActionExecutor`(집행기 없으면 `failed`) + Mock을 `tests/support`로 추방. `mcp_server_registry.default_requires_approval`(V075)를 sync가 **신규 INSERT 초기값**으로만 사용. |
| **Function/UX Effect** | 실 MCP 서버 PoC에서 승인 집행이 **정확히 1회** 도달(Rate MCP `list_products`, 41건 반환). 실패는 `[집행 불가]`/`[집행 여부 불명]`/`[도구 실패]` 3분류로 작업함에 노출. MCP 서버 등록 폼에 "기본 승인 필요" 체크박스 + 목록 뱃지. 신규 테스트 95건. |
| **Core Value** | **"승인됨 = 실행됨."** 부작용 도구는 등록 순간부터 통제(fail-closed)되고, 집행 경로는 도구 종류(메일·슬랙·사내시스템)를 모르는 범용 구조로 유지된다 — 자체 호스팅 BYO 메일 MCP 서버가 첫 소비자. |

---

## 1.4 Success Criteria Final Status

| # | Criteria | Status | Evidence |
|---|---------|:------:|----------|
| SC-1 | 승인된 MCP 도구가 실제 서버에 정확히 1회 도달 | ✅ Met | PoC: `main._build_approval_executor()` 프로덕션 조립으로 Rate MCP(`localhost:8004`) `list_products` 집행 → `call_tool` 1회, `ok=True` |
| SC-2 | 지원 집행기 없는 tool_id 승인 → `failed`, `executed` 0건 | ✅ Met | `tests/application/approval/test_executor_wiring.py` I1·I2 |
| SC-3 | 비활성·삭제·도구명 불일치·레거시 id → 호출 0회 + 구분 사유 | ✅ Met | `test_mcp_executor.py` TestBlocked 9케이스 (E18 포함) |
| SC-4 | 집행 출력이 재개 런에 주입되어 최종 답변 도달 | ⚠️ Partial | 경로 존재(`decide_use_case.py` `_resume`), Phase 1 G1 종결. 전 구간 E2E는 게이트 대상 에이전트 부재로 미수행 → G4 |
| SC-5 | 플래그 서버의 신규 엔트리 `requires_approval=true` | ✅ Met | S1 + 라이브 L1 A1(등록 직후 auto-sync ok) |
| SC-6 | 재-sync 후 관리자 값 보존 | ✅ Met | S3·S4·소급금지 + Phase 1 repo SQL 테스트 |
| SC-7 | 타임아웃 시 재호출 없음 + "불명" 문구 | ✅ Met | E8 |
| SC-8 | `main.py`에 Mock 참조 없음 | ✅ Met | I4 정적 검사(src 전역 포함) |
| SC-9 | 프론트 체크박스 저장·재조회 유지 | ✅ Met | U1~U5 + 라이브 L1 A1~A6 |

**Success Rate**: 8/9 Met, 1/9 Partial (94%)

## 1.5 Decision Record Summary

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan] | 메일은 MCP(BYO, 자체 호스팅). 코어에 메일 지식 없음 | ✅ | 집행기·정책 어디에도 도구별 분기 없음. `mcp:` 형식이면 동일 경로 |
| [Plan] | 집행기 없음 → `failed`, 재시도 0, 발신 계정=소유자 등록 | ✅ | Composite·`MCPRetryPolicy(max_retries=0)` 코드 고정(E17)·`SessionScopedMcpServerRepository` |
| [Design D-01] | `MCPCallClient` 직접 사용 (어댑터 경로 배제) | ✅ | 도구 `isError`가 `[도구 실패]`로 기록됨(E10). 어댑터였다면 거짓 성공 |
| [Design D-02] | list_tools 검증 → call_tool 2단계 | ✅ | "미발송 확실 / 불명" 경계가 호출 구조로 성립. Act-1에서 client 조립까지 경계 안으로(G1) |
| [Design D-04] | 실패 3분류는 문구 접두(스키마 무변경) | ✅ | approval API·테이블 변경 0. 후속에 `failure_kind` 컬럼 승격 가능 |
| [Design D-05] | 멱등키는 도구 스키마에 있을 때만 주입 | ✅ | PoC에서 스키마 없는 도구엔 미주입 확인. 메일 MCP 서버가 받으면 R-1 근본 해소 |
| [Design D-06] | Mock → `tests/support` | ✅ | src에서 제거, 재유입 정적 차단 |
| [Design D-07] | 플래그 INSERT 전용·UI 기본 꺼짐 | ✅ | 기존 서버 5개·엔트리 15건 무영향 확인 |
| [Design D-09] | 레거시 `mcp_{uuid}` fail-closed, 복원 로직 없음 | ✅ | 로컬 DB 계량 레거시 0건 |
| [Design D-11] | 에러 문구에 예외 타입명만 | ✅ | E14·E18로 `api_key` 비노출 고정. `_exception_name`으로 ExceptionGroup 내부까지 |

**이탈(문서화됨)**: V074→V075(Phase 1 iterate 선점), `build_execution_client` 모듈 함수화, `_exception_name`, `_build_approval_executor` 헬퍼 — Design v0.2 Version History.

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [approval-gate-phase2-mcp-executor.plan.md](../01-plan/features/approval-gate-phase2-mcp-executor.plan.md) v0.2 | ✅ Finalized |
| Design | [approval-gate-phase2-mcp-executor.design.md](../02-design/features/approval-gate-phase2-mcp-executor.design.md) v0.2 | ✅ Finalized |
| Check | [approval-gate-phase2-mcp-executor.analysis.md](../03-analysis/approval-gate-phase2-mcp-executor.analysis.md) v0.2 | ✅ Complete (99%) |
| 선행 | [approval-gate.report.md](./approval-gate.report.md) (Phase 1, 94%) | ✅ |
| Act | 본 문서 | ✅ |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| FR-01~03 | MCP tool_id 해석·supports·fail-closed | ✅ | |
| FR-04 | 재시도 0 | ✅ | config 비노출, 코드 고정 |
| FR-05 | 예외를 값으로 반환 | ✅ | Act-1에서 client 조립 예외까지 포함 |
| FR-06 | "집행 여부 불명 — 확인 후 재승인" 문구 | ✅ | |
| FR-07 | 요청 컨텍스트 없는 등록 조회 | ✅ | session-scoped 어댑터 |
| FR-08 | 출력 절단(config) | ✅ | `APPROVAL_EXEC_OUTPUT_MAX_CHARS` |
| FR-09 | 구조화 로깅, `tool_args` 값 미기록 | ✅ | Act-1에서 `elapsed_ms` 추가 |
| FR-10~12 | 합성 집행기·집행기 없음=failed·Mock 제거 | ✅ | |
| FR-13~16 | V075·도메인/앱 스키마·sync 초기값·소급 금지 | ✅ | 로컬 DB 적용 완료 |
| FR-17 | 프론트 체크박스 + 안내 | ✅ | + 목록 뱃지 |
| FR-18 | 발신 계정 정책 명문화 | ✅ | 집행기 도크스트링 D-08 |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|--------|
| 승인 1건당 MCP 호출 ≤ 1 | 1 | 1 (E2·E8·PoC) | ✅ |
| 집행기 없는 도구 `executed` | 0 | 0 (I1·I2) | ✅ |
| 시크릿·PII 비로깅 | 0건 | E14·E15·E18 | ✅ |
| domain→infra 참조 / repo commit | 0 | 0 | ✅ |
| 함수 40줄·중첩 2단계 | 준수 | ast 검사 통과 | ✅ |
| 신규 모듈 테스트 | 80%+ | 신규 95건, 관련 스위트 493 passed | ✅ |
| 기존 approval·MCP 테스트 무회귀 | 전부 통과 | 통과 | ✅ |

### 3.3 Deliverables

| Deliverable | Location | Status |
|-------------|----------|--------|
| 도메인 정책 | `src/domain/approval/execution_policy.py` | ✅ |
| 집행기 | `src/infrastructure/approval/{mcp_executor,composite_executor}.py` | ✅ |
| 설정 | `src/infrastructure/config/approval_execution_config.py`, `.env.example` | ✅ |
| DI | `src/api/main.py::_build_approval_executor` | ✅ |
| 마이그레이션 | `db/migration/V075__add_default_requires_approval_to_mcp_server_registry.sql` | ✅ 로컬 적용 |
| 서버 플래그 BE | mcp_registry models/repo/schemas/usecases, `sync_mcp_tools_use_case.py` | ✅ |
| 프론트 | `idt_front/src/types/mcpServer.ts`, `pages/AdminMcpServersPage/`, MSW | ✅ |
| 테스트 더블 | `tests/support/approval/mock_executor.py` (src에서 이동) | ✅ |
| 테스트 | domain 18 · infra 30 · config 3 · wiring 7 · sync 5 · registry 12 · mapping 6 · FE 5 · (Act-1 +2) | ✅ |

---

## 4. Incomplete Items

### 4.1 Carried Over

| Item | Reason | Priority | Estimated Effort |
|------|--------|----------|------------------|
| G4 — SC-4 전 구간 E2E(게이트→승인→집행→재개→답변) | 로컬에 게이트 대상 에이전트 없음. 라이브 L1·PoC로 구간별 검증은 완료 | Medium | 0.5일 (관리자 토글로 `list_products` 게이트 → 단독 워커 에이전트 → 승인) |
| G3 — mcp-registry 라우터 레벨(TestClient) 자동 테스트 | UseCase 레벨 + 라이브 수동 검증으로 대체됨 | Low | 0.2일 |
| `docs/rules/tool-and-mcp.md` §3에 서버 플래그·집행 경로 한 단락 | 규칙 문서는 요청 범위 밖 | Low | 0.1일 |

### 4.2 Cancelled / On Hold

| Item | Reason | Alternative |
|------|--------|-------------|
| 승인 화면 발신 계정·MCP 서버명 표시 (Plan R-5) | 프론트 범위 최소화 | 후속 사이클 |
| `failure_kind` 컬럼(Design Option B) | Phase 1 미커밋 상태에서 스키마 변경 회피 | 문구 접두가 정책 1곳이라 승격 용이 |
| `_extract_draft`의 MCP 래퍼 해제 (Phase 1 관찰) | approval-gate 소관 | `McpArgumentPolicy.unwrap` 재사용 1줄 |

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Target | Final | Change |
|--------|--------|-------|--------|
| Design Match Rate | 90% | **99%** | 98 → 99 (Act-1) |
| Structural / Functional / Contract | — | 100 / 100 / 100 | Functional 97 → 100 |
| Runtime | — | 96 | SC-4 E2E 미수행 감점 |
| Critical / Important gaps | 0 | 0 / 0 | Important 1 → 0 |
| Security (시크릿 노출·PII 로깅) | 0 | 0 | ✅ |

### 5.2 Resolved Issues

| Issue | Resolution | Result |
|-------|------------|--------|
| G1 — client 조립 예외가 `[집행 여부 불명]`으로 분류(경계 역전) | `_connect` try 범위에 factory 호출 포함 → `[집행 불가]` | ✅ E18 + 재현 스크립트 확인 |
| G2 — `elapsed_ms` 로깅 누락 | `_call`에 `perf_counter` | ✅ |
| 스모크에서 실패 사유가 `(ExceptionGroup)`으로만 표기 | `_exception_name`으로 안쪽 예외 타입까지 | ✅ `(McpError)` |
| 어댑터 경로 `isError` 무시(Design 조사 중 발견) | `MCPCallClient` 직접 사용(D-01) | ✅ E10 |
| V074 번호 충돌 | V075 + 문서 갱신 | ✅ |
| 라이브 서버가 새 코드인데 컬럼 없음(Unknown column 위험) | 사용자 승인 후 V075 로컬 적용 | ✅ |

---

## 6. Lessons Learned & Retrospective

### 6.1 Keep
- **Plan 전에 코드부터 읽기**: `MockActionExecutor` 도크스트링·`decide_use_case` 예외 경계·`MCPToolAdapter`의 `isError` 무시를 사전에 찾아 설계안 A를 결격 처리했다. 안 읽었으면 거짓 성공이 형태만 바꿔 남았다.
- **호출 구조로 안전 속성 확보**: "미발송 확실/불명"을 예외 타입 분류가 아니라 list_tools→call_tool 두 단계로 갈라, 테스트가 호출 횟수만 세면 된다.
- **실서버 스모크를 Do 중에**: 단위 테스트가 다 통과한 뒤 스모크에서 `(ExceptionGroup)` 표기 문제를 잡았다.
- **정적 갭 분석 결과를 재현으로 확인**: G1은 에이전트 보고를 실제 스크립트로 재현한 뒤 수정했다.

### 6.2 Problem
- **G1은 Design §6.2에 명시돼 있었는데 구현이 빠뜨렸다** — 단계별 try에 집중하다 "최상위 경계"를 놓쳤다. 테스트 표(E1~E17)에도 factory 예외 케이스가 없어 TDD가 못 잡았다.
- **마이그레이션 번호가 다른 사이클과 충돌** — 병행 사이클(Phase 1 iterate)이 V074를 선점.
- **전체 회귀 기준선 미확보** — 미커밋 변경이 많아 stash 비교를 못 해, 53건 실패가 기존 것인지 "무관 파일"로만 판단했다.
- **셸 heredoc 파싱 실패로 파일 3개가 생성 안 됨** — Write 도구로 재작성.

### 6.3 Try
- Design §6(에러 처리)의 각 문장을 테스트 ID로 1:1 매핑하는 관행 — "최상위 경계"처럼 구현 위치가 없는 규정도 테스트로 강제.
- 마이그레이션 번호는 Do 진입 시점에 `ls db/migration | tail -1`로 재확인.
- 큰 파일 생성은 heredoc 대신 Write 도구.
- 사이클 시작 전 회귀 기준선을 파일로 저장(`pytest -q > baseline.txt`).

---

## 7. Process Improvement Suggestions

| Phase | Current | Suggestion |
|-------|---------|------------|
| Plan | 선행 조건(Phase 1 갭)을 문서에 적었으나 Do 시점에 이미 해소돼 있었다 | 병행 사이클 상태를 Do 진입 시 자동 재확인 |
| Design | §8 테스트 표가 FR 기준 | §6 에러 처리 규정도 테스트 ID 부여 |
| Check | gap-detector 보고 + 수동 재현 | 유지 — Important 이상은 재현 필수 |
| 환경 | 라이브 dev 서버가 코드는 새것·DB는 옛것 | 마이그레이션 파일 생성 시 "적용 필요" 경고를 Do 요약에 고정 |

---

## 8. Next Steps

### 8.1 Immediate
- [ ] 커밋 — Phase 1(approval-gate)과 Phase 2 변경이 작업 트리에 섞여 있음. 분리/통합 결정 후 `/commit`
- [ ] 운영 DB V075 적용 후 앱 재시작 (적용 전 재시작 시 `mcp_server_registry` 조회 실패)
- [ ] `docs/rules/tool-and-mcp.md` §3 갱신 (서버 플래그, 집행 경로, 재시도 0)

### 8.2 Next PDCA Cycle

| Item | Priority | Note |
|------|----------|------|
| 메일 MCP 서버 구축 (별도 저장소) | High | Plan §7.4 계약: 고정 헤더 인증, 읽기/쓰기 도구 분리, 평평한 인자, `idempotency_key` 파라미터, 구조화 에러 |
| G4 — 전 구간 E2E (QA) | Medium | `list_products` 게이트 → 단독 워커 에이전트 → 승인 → 재개 답변 확인 |
| 승인 화면 발신 계정 표시 | Medium | Plan R-5 |
| `_extract_draft` MCP 래퍼 해제 | Low | approval-gate 소관, 1줄 |
| 자동 승인 조건식 (Phase 3) | Low | |

---

## 9. Changelog

### approval-gate-phase2-mcp-executor (2026-09-22)

**Added**
- `McpActionExecutor` — 승인된 MCP 도구를 list_tools 검증 후 call_tool 1회(재시도 0) 집행, 실패 3분류
- `CompositeActionExecutor` — 집행기 디스패치, 미지원 도구는 `failed`
- `ExecutionFailurePolicy`, `McpArgumentPolicy` (domain)
- `ApprovalExecutionConfig` + `APPROVAL_EXEC_{CONNECT_TIMEOUT,TOTAL_TIMEOUT,OUTPUT_MAX_CHARS}`
- `mcp_server_registry.default_requires_approval` (V075) + 등록/수정 API 필드 + 프론트 체크박스·뱃지
- `ActionExecutorInterface.execute(idempotency_key=)` 선택 kwarg

**Changed**
- `main.py` approval DI: Mock → `CompositeActionExecutor([McpActionExecutor])`
- `SyncMcpToolsUseCase`: 신규 엔트리 `requires_approval` 초기값 = 서버 플래그
- decide/scheduler: 멱등키를 집행기에 전달

**Removed**
- `src/infrastructure/approval/mock_executor.py` → `tests/support/approval/`

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-09-22 | Completion report | 배상규 |
