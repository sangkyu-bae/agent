# approval-edit-before-approve Completion Report

> **Status**: Complete (런타임 L1/L3 검증은 환경 준비 후 — §4.1)
>
> **Project**: sangplusbot (idt + idt_front)
> **Version**: —
> **Author**: 배상규
> **Completion Date**: 2026-09-29
> **PDCA Cycle**: #1 (Act 1회)

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | approval-edit-before-approve — 담당자 수정 후 승인 |
| Start Date | 2026-09-29 |
| End Date | 2026-09-29 |
| Duration | 1일 (Plan → Design → Do 5모듈 → Check → Act-1) |
| Depends on | approval-gate, approval-gate-phase2-mcp-executor |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Match Rate: 98.2%  (94.6% → Act-1 → 98.2%) │
├─────────────────────────────────────────────┤
│  ✅ FR Complete:   14 / 14                   │
│  ✅ SC Met:         7 / 7                    │
│  ⏳ Minor carry:    3 (M1, M2, M4)           │
│  ❌ Cancelled:      0                        │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 승인 결정지가 승인/거절 둘뿐이라 초안이 한두 문장만 틀려도 거절→재실행→재승인을 거쳐야 했고, 실제 집행될 `tool_args`(수신자 등)는 화면에서 볼 수 없었다. |
| **Solution** | 기존 `POST /approve` 에 선택 바디 `edited_args` 를 추가하고, 도메인 정책(`ApprovalEditPolicy`)으로 검증·병합·MCP 래퍼 재포장한 수정본을 `pending→approved` **조건부 UPDATE 한 문장**에 원본·편집자·시각과 함께 확정. 재개 시 최종 답변도 수정본 기준이 되도록 스냅샷 초안을 교체. |
| **Function/UX Effect** | 작업함 › 승인 대기 카드에 `상세 보기` → 드로어에서 초안 전문·호출 인자 확인, `수정` → 문자열 인자 편집(변경 필드 amber 하이라이트) → 변경 키 목록·본문 외 변경 경고 확인창 → `수정 후 승인`. 즉시·예약 집행 모두 수정본으로 MCP 호출. 신규 테스트: 백엔드 66건(도메인·유스케이스 50, 재개 4, 리포지토리 4, 라우터 8), 프론트 32건(유틸 7, 드로어 12, 훅·서비스 9, 테이블 4). |
| **Core Value** | 사람이 판정자이자 편집자가 되어 AI 초안을 버리지 않고 고쳐 쓴다. "AI 원본 / 사람 수정본" 이 구분되어 남아 감사 추적·향후 평가 데이터가 된다. 부수 효과로 오래 사문화돼 있던 승인 오류 문구 매핑(G2)이 복구됐다. |

---

## 1.4 Success Criteria Final Status

| # | Criteria | Status | Evidence |
|---|---------|:------:|----------|
| SC-1 | 수정 후 즉시 집행 시 executor 인자 = 병합 수정본 | ✅ Met | `tests/application/approval/test_decide_edit.py::TestApproveWithEdit::test_즉시_집행은_수정본으로_호출된다` |
| SC-2 | 수정 후 예약 집행도 수정본 | ✅ Met | `test_decide_edit.py::test_예약건도_수정본이_확정된다`, `TestScheduledEdited` (스케줄러가 DB 수정본 집행) |
| SC-3 | 원본·편집자·시각 저장, 무수정은 NULL | ✅ Met | `test_decide_edit.py::test_승인_전이에_수정본과_원본이_함께_실린다`, `TestApproveWithoutEdit`, `tests/infrastructure/approval/test_repository.py::TestEditColumns` |
| SC-4 | 재개 outcome·답변에 수정 사실 반영 (즉시·예약) | ✅ Met | outcome: `test_재개_outcome에_수정_사실이_실린다`; 최종 답변 초안: `tests/application/approval/test_resume.py::TestRestoreEditedDraft` (Act-1 G1) |
| SC-5 | 편집 불가/불허 키/비문자열/빈 본문 → 422, pending 유지 | ✅ Met | `TestApproveEditRejected` (CAS 미호출), `tests/domain/approval/test_edit_policy.py::TestApply`, router 422 매핑 |
| SC-6 | 드로어 전문·인자 확인, 요청 바디에 변경 키만 | ✅ Met | `ApprovalDetailDrawer.test.tsx` "바뀐 키만 담아 승인한다", `useApprovals.test.ts` 바디 3건(실제 HTTP 바디) |
| SC-7 | 기존 동작 회귀 0 | ✅ Met | 백엔드 10100 passed / 53 failed, 프론트 1314 passed / 9 failed — 실패는 master 상시 목록과 파일·건수 동일. tsc 210(기준선), 변경 파일 eslint 0 |

**Success Rate**: 7/7 (100%)

## 1.5 Decision Record Summary

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan] | 수정 범위 = 본문 키 있는 건의 **문자열 인자 전체** (사용자 결정) | ✅ | `editable_keys` = unwrap 인자의 문자열 키(멱등키 제외). 수신자 변경 가능성은 UI 경고 + 원본 보존 + `changed_keys` 감사 로그로 통제 |
| [Plan] | 본문 키 없는 건은 수정 불가, 승인/거절만 | ✅ | 422 `APPROVAL_NOT_EDITABLE`, UI `수정` 비활성 + 안내 |
| [Plan] | 재개 시 수정 사실 통지 | ✅ | `ApprovalOutcomePolicy.compose` + (Act-1) 스냅샷 초안 교체 |
| [Plan] | 풀스택 | ✅ | module-1~5 전부 |
| [Design] | Option C — 도메인 순수 정책 + 기존 approve 확장 + 단일 CAS | ✅ | 새 UseCase·테이블 없음. `compare_and_set_status` 에 편집 5필드 추가(None 은 SET 제외 → 기존 호출 불변) |
| [Design] | D-01 본문 키 = draft 값 일치 키 (관례 키 존재 판정 대체) | ✅ | action 워커의 사용자 지정 `draft_arg_key` 와 react 경로 MCP 래퍼를 새 컬럼 없이 커버 |
| [Design] | D-02 `extract_draft` 가 MCP 래퍼 해제 후 탐색 (사용자 승인) | ✅ | react 경로 MCP 초안이 JSON 전체로 저장되던 문제 해소 (신규 적재분부터) |
| [Design] | D-03 편집 키는 unwrap 레벨, 저장은 재포장 | ✅ | `McpArgumentPolicy.is_wrapped/rewrap` — 집행기 unwrap 계약 유지 |
| [Design] | 수정본 PII 재마스킹 미적용 | ✅ | 사람이 직접 작성한 값이므로 비적용. 필요 시 후속 판단 |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [approval-edit-before-approve.plan.md](../01-plan/features/approval-edit-before-approve.plan.md) | ✅ v0.2 |
| Design | [approval-edit-before-approve.design.md](../02-design/features/approval-edit-before-approve.design.md) | ✅ v0.1 |
| Check | [approval-edit-before-approve.analysis.md](../03-analysis/approval-edit-before-approve.analysis.md) | ✅ 94.6% → Act-1 98.2% |
| Act | Current document | ✅ |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| FR-01 | 편집 가능 판정 (draft 값 일치 + 래퍼 해제), 미들웨어 공유 | ✅ | Design D-01/D-02 로 Plan v0.2 갱신 |
| FR-02 | 편집 키 = 문자열 인자 전체 | ✅ | 멱등키 제외 |
| FR-03 | 선택 바디 `edited_args`, 하위 호환 | ✅ | 바디 없음/빈 객체 = 일반 승인 |
| FR-04 | 서버 검증 (a–e) | ✅ | 길이 상한 `approval_edit_max_field_chars`=20000 |
| FR-05 | 동일 값만 = 수정 없음 | ✅ | |
| FR-06 | 단일 CAS 에 5필드 | ✅ | |
| FR-07 | 즉시·예약 모두 수정본 집행 | ✅ | |
| FR-08 | 재개 outcome 접두 + 최종 본문 | ✅ | Act-1 에서 final_answer 초안까지 교체 |
| FR-09 | 상세 7필드 + 목록 `edited` | ✅ | |
| FR-10 | 상세 드로어 (전문·인자·이력) | ✅ | |
| FR-11 | 편집 모드·하이라이트·확인창(변경 키, 본문 외 경고) | ✅ | 확인창은 `ConfirmDialog` 대신 제목 있는 `Modal`(aria 이름 필요) |
| FR-12 | 편집 불가 안내 | ✅ | |
| FR-13 | 에러 문구 매핑 | ✅ | Act-1 G2 로 실제 동작 복구 |
| FR-14 | 감사 로그 키만 | ✅ | `approval edited` — `changed_keys`, `edited_by` |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|--------|
| 하위 호환 | 바디 없는 승인·기존 행 동작 불변 | 기존 approval 테스트 전량 통과, 편집 컬럼 NULL 허용 | ✅ |
| 정합성 | 수정 기록·상태 전이 단일 UPDATE | CAS 실패 시 집행 0 (B17) | ✅ |
| 보안 | 키 추가·타입 변경 불가, 권한 불변 | 도메인 검증 + `StrictStr` | ✅ |
| 개인정보 | 수정 값 로그 미기록 | B22 로그 캡처 테스트 | ✅ |
| 아키텍처 | 규칙은 domain, 라우터 로직 없음 | domain→infra/langchain 참조 0 | ✅ |
| DDL | COMMENT 필수 | `test_migration_ddl_comments.py` 통과 | ✅ |
| 코딩 규칙 | 함수 40줄 | 신규/변경 함수 준수 (스케줄러 `_process` 는 기존 45줄 — 증가 없음) | ✅ |

### 3.3 Deliverables

| Deliverable | Location | Status |
|-------------|----------|--------|
| 도메인 정책 | `idt/src/domain/approval/edit_policy.py` (신규), `policies.py`(`ApprovalOutcomePolicy`), `execution_policy.py`(`is_wrapped/rewrap`), `entity.py` | ✅ |
| 영속 | `idt/db/migration/V078__add_edit_columns_to_approval_request.sql`, `infrastructure/approval/{models,repository}.py` | ✅ |
| 유스케이스 | `application/approval/{decide_use_case,execute_scheduler,gate_middleware,errors}.py`, `agent_builder/run_agent_use_case.py`(`_replace_worker_draft`) | ✅ |
| API | `interfaces/schemas/approval.py`, `api/routes/approval_router.py`, `api/main.py`, `config.py` | ✅ |
| 프론트 | `types/approval.ts`, `services/approvalService.ts`, `services/api/{ApiError,authClient}.ts`, `hooks/useApprovals.ts`, `utils/approvalEdit.ts`, `pages/JobsPage/{ApprovalDetailDrawer,ApprovalCard,ApprovalTable}.tsx` | ✅ |
| 테스트 | BE: `test_edit_policy.py`, `test_decide_edit.py`, `test_resume.py`(+4), `test_repository.py`(+4), `test_approval_router.py`(+8) / FE: `approvalEdit.test.ts`, `ApprovalDetailDrawer.test.tsx`, `useApprovals.test.ts`, `ApprovalTable.test.tsx`(+4) | ✅ |
| 문서 | Plan v0.2, Design v0.1, Analysis (Act-1 포함), 본 리포트 | ✅ |

---

## 4. Incomplete Items

### 4.1 Carried Over to Next Cycle

| Item | Reason | Priority | Estimated Effort |
|------|--------|----------|------------------|
| 런타임 L1 (실서버 API) / L3 (action 워커 실런: 수정 → MCP 수신본 → 재개 답변) | 로컬 DB V078 미적용, 백엔드 미기동, 본문 키를 받는 부작용 MCP(예: 메일) 미등록 | High | 0.5일 (환경 준비 후) |
| M1 드로어 헤더 남은 시간 표시 | Minor — 사용자 결정으로 보류 | Low | 0.5h (`remainingText` utils 이동) |
| M2 `원본 보기` 래퍼 해제 표시 | Minor | Low | 1h (클라이언트 unwrap 또는 `original_display_args`) |
| M4 Design §4.2 문구 (`dict[str, StrictStr]`, 비문자열은 FastAPI 기본 422) | 문서 정합 | Low | 10m |
| 도구별 편집 금지 필드 (관리자 설정) | Plan Out of Scope — 수신자 변경 리스크의 근본 통제 | Medium | 별도 PDCA |

### 4.2 Cancelled/On Hold Items

| Item | Reason | Alternative |
|------|--------|-------------|
| 기존 react 경로 MCP 적재 행의 draft 재추출 | D-02 는 신규 적재분부터 — 기존 pending 행은 JSON 초안이라 편집 불가로 남음 | 만료(최대 720h) 후 자연 소멸 |

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Target | Final | Change |
|--------|--------|-------|--------|
| Design Match Rate | 90% | 98.2% | +3.6 (Act-1) |
| Structural / Functional / Contract | — | 97 / 97 / 100 | Functional +4, Contract +5 |
| Success Criteria | 7/7 | 7/7 | SC-4 의도 충족(Act-1) |
| Critical Issues | 0 | 0 | ✅ |
| 회귀 | 0 | 0 | 상시 실패 목록 동일 |

### 5.2 Resolved Issues

| Issue | Resolution | Result |
|-------|------------|--------|
| **G1** 재개 final_answer 가 원본 초안을 "한 글자도 고치지 말고" 재현 | `_restore_state` 에서 수정된 건의 워커 초안 메시지를 수정본으로 교체 | ✅ `TestRestoreEditedDraft` 4건 |
| **G2** `authApiClient` 가 `ApiError` 로 재포장해 `AxiosError` 기반 오류 코드 매핑이 한 번도 동작하지 않음 (기존 결함) | `ApiError.code` 추가 + 인터셉터 보존 + 훅 `ApiError` 우선 판정 | ✅ 실제 인터셉터 + MSW 6건 |
| react 경로 MCP 초안이 JSON 전체로 저장 (Design 중 발견, D-02) | `extract_draft` 래퍼 해제 | ✅ B19 |
| Plan 의 편집 판정(관례 키 존재)이 action 워커 사용자 지정 키·MCP 래퍼를 놓침 (Design 중 발견, D-01) | draft 값 일치 판정으로 교체 | ✅ B1–B3 |

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- **Design 단계의 코드 실측이 Plan 가정을 두 번 교정했다** (D-01 본문 키 판정, D-02 래퍼). 문서만으로 설계했다면 action 워커 경로(현재 MCP 발송 주경로)에서 기능이 작동하지 않았을 것.
- **단일 CAS 에 편집을 싣는 결정**으로 이중 클릭·동시 결정 방어를 새 코드 없이 상속했다.
- TDD Red→Green 을 모듈마다 지켜, 전체 회귀가 매번 상시 실패 목록과 동일하게 유지됐다.
- gap-detector 가 "문구상 충족, 의도 미충족"(SC-4/G1)을 잡았다 — 성공 기준을 Context Anchor 의 의도로 재검한 효과.

### 6.2 What Needs Improvement (Problem)

- **훅 `vi.mock` 테스트가 실제 오류 경로를 가렸다(G2)**. 컴포넌트 테스트 편의가 계약 결함을 숨겼고, 그 결함은 이 기능 이전부터 존재했다.
- 재개 경로의 **다른 소비자(FinalAnswerDraftPolicy)** 를 Design Impact Analysis(§6.2)에서 누락 — outcome 만 보고 스냅샷 안의 원본 초안을 보지 못했다(G1).
- 런타임 L1/L3 를 이번 사이클에 수행하지 못했다(환경 의존).

### 6.3 What to Try Next (Try)

- 에러 매핑이 있는 훅은 **실제 authApiClient + MSW** 테스트를 최소 1건 둔다 (메모리 `idt-front-apierror-interceptor` 에 반영).
- 재개·스냅샷을 건드리는 기능은 Impact Analysis 에 "스냅샷 안의 기존 메시지를 읽는 소비자" 항목을 추가한다.
- 부작용 MCP 테스트용 로컬 스텁(본문 키 보유 도구)을 마련해 L3 를 상시 가능하게 한다.

---

## 7. Process Improvement Suggestions

### 7.1 PDCA Process

| Phase | Current | Improvement Suggestion |
|-------|---------|------------------------|
| Plan | 기존 코드 가정(관례 키)으로 FR 작성 | 게이트·집행처럼 경로가 둘 이상인 영역은 Plan 에서 경로 목록부터 실측 |
| Design | Impact Analysis 가 "쓰는 곳" 위주 | 재개/스냅샷 계열은 "읽어서 재해석하는 곳" 도 열거 |
| Do | 훅 목 중심 프론트 테스트 | 계약 경계(인터셉터) 테스트 1건 의무화 |
| Check | 정적 분석 위주 | L3 가능한 로컬 MCP 스텁 확보 |

### 7.2 Tools/Environment

| Area | Improvement Suggestion | Expected Benefit |
|------|------------------------|------------------|
| 로컬 MCP | 본문 키(`body`) 받는 부작용 스텁 서버 | 승인 게이트 L3 상시 검증 |
| 마이그레이션 | 로컬 DB Flyway 적용 절차를 Do 체크리스트에 | 실서버 검증 누락 방지 |

---

## 8. Next Steps

### 8.1 Immediate

- [ ] 로컬 DB 에 V078 적용 (미적용 시 승인 목록·상세 조회 실패)
- [ ] 커밋·PR (현재 master 워킹트리 미커밋 — 브랜치 생성 권장)
- [ ] 런타임 L1: approve 바디 없음/수정/불허 키/편집 불가 행, 상세·목록 필드
- [ ] 런타임 L3: action 워커 → 수정 → MCP 수신본·재개 답변이 수정본인지

### 8.2 Next PDCA Cycle

| Item | Priority | Expected Start |
|------|----------|----------------|
| 도구별 편집 금지 필드 (관리자 설정) | Medium | 운영 피드백 후 |
| M1·M2 드로어 UX 보완 | Low | 다음 승인 UI 작업 시 |
| 역할 기반 승인자 (`can_decide` 확장) | Medium | 별도 |

---

## 9. Changelog

### v1.0.0 (2026-09-29)

**Added:**
- 승인 대기 건 **수정 후 승인** — `POST /api/v1/approvals/{id}/approve` 선택 바디 `edited_args`
- 상세 응답 `editable`/`body_key`/`editable_keys`/`display_args`/`original_tool_args`/`edited_by`/`edited_at`, 목록 `edited`
- 오류 코드 `APPROVAL_NOT_EDITABLE`, `APPROVAL_EDIT_INVALID` (422)
- `approval_request` 컬럼 3종 (V078), 설정 `approval_edit_max_field_chars`
- 작업함 승인 상세 드로어(보기/편집/확인창), 카드 `상세 보기`·`수정됨` 배지

**Changed:**
- 초안 추출이 MCP 래퍼를 해제한 뒤 관례 키를 탐색 (`ApprovalEditPolicy.extract_draft`, 단일 출처)
- 재개 outcome 에 수정 안내 + 최종 본문, 재개 스냅샷 초안을 수정본으로 교체
- `ApiError` 에 `code` 추가, 인터셉터가 `detail.code` 보존

**Fixed:**
- 승인 오류 문구 매핑이 동작하지 않던 문제 (409 가 `status=approved`, 410 이 UUID 로 노출)
- react 경로 MCP 도구의 승인 초안이 인자 JSON 전체로 표시되던 문제 (신규 적재분)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-09-29 | Completion report created | 배상규 |
