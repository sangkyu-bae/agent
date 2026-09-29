# approval-edit-before-approve Gap Analysis

> **Date**: 2026-09-29 | **Phase**: Check (static) | **Match Rate**: 94.6%
> **Plan**: [plan](../01-plan/features/approval-edit-before-approve.plan.md) · **Design**: [design](../02-design/features/approval-edit-before-approve.design.md)
> 분석: bkit:gap-detector (정적) + 메인 세션 코드 재확인(G1·G2 사실 확인). 런타임 L1 은 백엔드 서버 미기동·로컬 DB V078 미적용으로 생략 → 정적 공식 적용.

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 초안이 조금만 틀려도 거절→재실행 외 방법이 없고, 실제 집행 인자를 화면에서 볼 수 없다. |
| **WHO** | P2 — 승인 게이트가 걸린 에이전트의 소유자(현재 유일한 승인자, `ApprovalPolicy.can_decide`). |
| **RISK** | 문자열 인자 전체 편집을 허용하므로 담당자가 수신자·대상을 바꿀 수 있다 → 변경 하이라이트 + 원본 보존 + 서버측 키/타입 불변 검증으로 통제. 예약(scheduled) 건은 승인 시점 확정값이 그대로 집행되어야 한다. |
| **SUCCESS** | 수정 승인 시 즉시·예약 집행 모두 수정본으로 MCP 호출 / 원본·편집자·시각이 DB에 남음 / 재개 답변에 수정 사실 반영 / 본문 키 없는 건은 서버가 수정 거부 / 기존 승인·거절 동작 회귀 0. |
| **SCOPE** | 백엔드(DB V078 + Domain 정책 + DecideUseCase + 라우터/스키마) → 프론트(타입·서비스·훅 + 상세 드로어 + 편집 모드). |

## Strategic Alignment

- 핵심 문제(거절 외 대안 부재 + 집행 인자 비가시)는 해결됨 — 드로어 보기/편집, 단일 CAS 확정, 예약 경로 반영.
- **예외(G1)**: "재개 답변에 수정 사실 반영"은 outcome 수준에서만 충족. action 워커 경로에서는 최종 답변이 원본 초안을 그대로 재현하도록 지시받는다 → 성공 의도와 어긋남(Important).
- Decision Record: Option C(도메인 정책 + 기존 approve 확장), D-01~D-03 모두 구현에 반영됨.

**메인 세션 재확인 (2026-09-29)**
- G1: `SnapshotSerializer.dumps_with_limit(state.final_state …)`(run_agent_use_case.py:942) → 스냅샷에 action 워커의 원본 초안 메시지 포함 확인. `_restore_state`(:865-881)는 outcome 만 덧붙임. `_draft_context`(workflow_compiler.py:417-438)가 원본을 `[작성된 초안]`으로 채택, `FinalAnswerDraftPolicy.instruction()`이 "한 글자도 고치지 말고" 지시 — 사실.
- G2: `authClient.ts:59-67` 가 항상 `ApiError(message, status)`로 reject(`code` 소실), `useApprovals.ts`는 `instanceof AxiosError` 판정 — 사실. 본 기능 이전부터 존재.


## Scores

| Axis | Score | Basis |
|------|:-----:|-------|
| Structural | 97% | §11.2: all BE new/modified files present (plus interfaces.py), FE new files + tests present, Card/Table/types/service/hooks modified. Only `src/__tests__/mocks/handlers.ts` untouched (intentional: vi.mock instead of MSW). |
| Functional | 93% | FR 13.25/14, §5.4 11.5/13, §7 7/7, B1–B22 22/22, F1–F8 8/8; deducted for resume draft-preservation conflict (G1) and dead front error-code mapping (G2). |
| Contract | 95% | 3/3 endpoints match Design §4 ↔ schema/router ↔ types/service. Error-code leg degraded: front cannot read `detail.code` (G2). |
| **Overall (static)** | **94.6%** | 97×0.2 + 93×0.4 + 95×0.4 |

## Plan Success Criteria

| SC | Status | Evidence |
|----|:------:|----------|
| SC-1 immediate exec uses merged edit | Met | tests/application/approval/test_decide_edit.py:37; decide_use_case.py:126-135, 250-251 |
| SC-2 scheduled exec uses edit | Met | test_decide_edit.py:76 (CAS stores edit), :199 (tick executes DB tool_args); repo round-trip tests/infrastructure/approval/test_repository.py:239-287 |
| SC-3 original/edited_by/edited_at stored, NULL when unedited | Met | test_decide_edit.py:48, :163 (None/{}/same-value); repository.py:137-162, 244-248; V078 |
| SC-4 resume outcome carries notice + final body (both paths) | Met (literal) — intent at risk | test_decide_edit.py:64, :199; policies.py:209-227. See G1: action-worker final answer is still told to reproduce the ORIGINAL draft verbatim. |
| SC-5 not-editable / disallowed key / non-string / blank body → 422, stays pending | Met | test_decide_edit.py:119, :132, :141 (CAS not awaited); test_edit_policy.py:110-137; router test_approval_router.py:157-158, :363 (StrictStr → 422) |
| SC-6 drawer shows full draft/args, edit → body with changed keys only | Met (with intentional deviation) | ApprovalDetailDrawer.test.tsx:82, :149-167 (mutateAsync gets {body} only). Hook-level mock, not MSW; service body-omission branch untested (M3). |
| SC-7 zero regressions | Met | Do 단계 전체 실행: 백엔드 10096 passed / 53 failed(=master 상시 실패 목록과 동일 파일·건수), 프론트 1305 passed / 9 failed(=상시 실패 4파일 9건), tsc 210(기준선 동일), 변경 파일 eslint 0 |

## Functional Requirements

| FR | Status | Evidence |
|----|:------:|----------|
| FR-01 editable via draft-value match + unwrap; middleware delegates | Done | edit_policy.py:41-71; gate_middleware.py:22, 64 |
| FR-02 editable_keys = string keys (idempotency excluded) | Done | edit_policy.py:73-82 |
| FR-03 optional body, back-compat | Done | approval_router.py:119, 129; edit_policy.py:89-90 |
| FR-04 a–e validation | Done | edit_policy.py:92-121; config.py:314; main.py:3284 |
| FR-05 same values = no edit | Done | edit_policy.py:98-100 |
| FR-06 single CAS with 5 fields | Done | decide_use_case.py:126-130, 302-315; repository.py:124-171 |
| FR-07 immediate + scheduled use edited tool_args | Done | decide_use_case.py:131-135, 173-182; execute_scheduler.py:95-96 |
| FR-08 outcome prefix, shared helper | Done (see G1) | policies.py:209-227; decide_use_case.py:267-270; execute_scheduler.py:150-157 |
| FR-09 detail + list fields | Done | schemas/approval.py:49-50, 69-76, 125, 129-149 |
| FR-10 drawer view | Done | ApprovalDetailDrawer.tsx:89-161; ApprovalCard.tsx:67-76 |
| FR-11 edit mode, highlight, confirm with changed keys + warning | Done | ApprovalDetailDrawer.tsx:32-35, 70-87, 171-181, 255-281 |
| FR-12 not-editable disabled + hint | Done | ApprovalDetailDrawer.tsx:188-196, 220-224 |
| FR-13 error messages in APPROVAL_ERROR_MESSAGES | Partial | types/approval.ts:53-55 added, but mapping is dead in production (G2) |
| FR-14 audit log keys only | Done | decide_use_case.py:183-187; test_decide_edit.py:99 |

## Design §5.4 Page UI Checklist

| Item | Status |
|------|:------:|
| Card: 상세 보기 (all states) | Done (ApprovalCard.tsx:67-76) |
| Card: 수정됨 badge | Done (ApprovalCard.tsx:59-63) |
| Card: existing approve/reject/preview kept | Done |
| Drawer header: agent, status, 수정됨, tool id, expiry (remaining time) | Partial — remaining time missing (M1) |
| Full draft pre-wrap + 본문 ({body_key}) label | Done (:89-105) |
| Args table, non-string JSON + 수정 불가 | Done (:107-136) |
| 원본 보기 toggle + editor/time | Done (:138-161); shows raw wrapped args (M2) |
| 수정 button (pending && editable) + hint | Done |
| Edit: textarea body / inputs / amber highlight | Done |
| 취소 / 수정 후 승인 (disabled when 0 changes) | Done (:171-181) |
| Confirm dialog: changed keys + non-body warning | Done (Modal instead of ConfirmDialog — intentional, acceptable) |
| 승인 / 거절 in view mode | Done |
| Error: 422/409/410 via APPROVAL_ERROR_MESSAGES | Partial (G2) |

## Security (§7)

All 7 items implemented: can_decide unchanged (decide_use_case.py:198); key/type immutability (edit_policy.py:110-121, schema StrictStr); idempotency key excluded (edit_policy.py:81); length cap config 20000 (config.py:314); log keys only (decide_use_case.py:184-187); non-body change warning + original preserved; no PII re-mask (decision — record in report).

## API Contract (3-way)

| # | Endpoint | Design | Server | Client | Contract |
|---|----------|:------:|:------:|:------:|:--------:|
| 1 | GET /api/v1/approvals (`edited`) | yes | schemas/approval.py:50,125 | types/approval.ts:76; ApprovalCard.tsx:59 | PASS |
| 2 | GET /api/v1/approvals/{id} (+7 fields) | yes | schemas/approval.py:70-76,142-148 | types/approval.ts:89-97 | PASS |
| 3 | POST /api/v1/approvals/{id}/approve {edited_args?} | yes | schemas/approval.py:95; router:119,129; message prefix router:190 | approvalService.ts:45-57 (body only when non-empty) | PASS |
| — | Error codes APPROVAL_NOT_EDITABLE / APPROVAL_EDIT_INVALID (422) | yes | errors.py:43-54 | code unreadable at runtime (G2) | PARTIAL |

Minor drift: Design §4.2 schema `dict[str, str]`; impl `dict[str, StrictStr]` (stricter; non-string → FastAPI list-detail 422 instead of APPROVAL_EDIT_INVALID). Update Design.

## Gaps (confidence >= 80%)

### Critical
None.

### Important

**G1 — Resumed final answer can reproduce the ORIGINAL draft for action-worker approvals (conf ~85%)**
- Where: run_agent_use_case.py:865-881 (`_restore_state` appends outcome only); workflow_compiler.py:417-438 (`_draft_context`); domain/agent_builder/policies.py:612-648 (`FinalAnswerDraftPolicy`).
- Why: the snapshot is the gated run's final_state (run_agent_use_case.py:942-944), which contains the action worker's draft message `format_draft_output(worker_id, ORIGINAL_draft, "승인 대기…")`. On resume `_draft_context` takes the draft from that message and uses the injected composed outcome only as `[집행 결과]`; `render_block` + `instruction()` tell the LLM "위 [작성된 초안]을 한 글자도 고치지 말고 그대로 답변에 포함". The edited body appears only inside the outcome → contradictory prompt; the user may be shown the pre-edit text. Undercuts Context Anchor SUCCESS "재개 답변에 수정 사실 반영" on exactly the path D-01 targets (draft_arg_key).
- Fix: in `_restore_state`, when `approval.is_edited`, replace the last draft message for `approval.worker_id` (detected via `split_draft_output`) with `format_draft_output(worker_id, approval.draft, <its outcome>)` before appending the outcome. Add a test: snapshot with draft message + edited approval → final_answer DraftContext.draft == edited draft.

**G2 — Front error-code mapping is dead: authApiClient rejects with ApiError, hooks check AxiosError (conf ~90%, pre-existing but breaks FR-13 / §5.4 Error)**
- Where: idt_front/src/hooks/useApprovals.ts:18-26 (`errorPayload` requires `instanceof AxiosError`), :46-47 (`isApprovalConflict`); idt_front/src/services/api/authClient.ts:59-67 (always `Promise.reject(new ApiError(message, status))`, code dropped).
- Effect in drawer (ApprovalDetailDrawer.tsx:61-63) and table: APPROVAL_ERROR_MESSAGES never applies. Raw server messages shown: 409 → "status=approved" or "<id>: expected=pending no longer holds"; 410 → bare approval UUID (`ApprovalExpiredError(approval_id)`); 403 → UUID. The newly added APPROVAL_NOT_EDITABLE entry is unreachable. Drawer test mocks `extractApprovalError`, so tests do not catch it.
- Fix: add `code?: string` to ApiError and set it from `detail?.code` in the interceptor; make `errorPayload` read `ApiError.code`/`message`, `isApprovalConflict` use `e instanceof ApiError && e.status === 409`; add a hook test that rejects with `ApiError`.

### Minor

- **M1** Drawer header omits remaining time "(N시간 남음)" (Design §5.1/§5.4). ApprovalDetailDrawer.tsx:217-219. Fix: move `remainingText` from ApprovalCard.tsx:22-30 to utils/formatters and reuse.
- **M2** 원본 보기 renders raw `original_tool_args` (wrapped `{"arguments":{...}}` for react MCP) while the table shows unwrapped display_args — hard to compare. ApprovalDetailDrawer.tsx:155-157. Fix: unwrap client-side (single key `arguments` with object value) or expose `original_display_args`.
- **M3** No test for approvalService.approve body omission (`edited_args` only when non-empty, else no body). approvalService.ts:53-55. Add service test (axios mock/MSW) — SC-6 is verified only at hook-call level.
- **M4** API-level non-string value returns FastAPI validation list (not `APPROVAL_EDIT_INVALID`); schemas/approval.py:95. Harmless (front sends strings only) — update Design §4.2/B21 wording.

## Intentional deviations reviewed (accepted)
- vi.mock hooks instead of MSW (no handlers.ts change): acceptable, but see M3 and G2 (mocking hid the ApiError issue).
- Modal with title instead of ConfirmDialog: fine; dialog is accessible by role/name (test :158).
- APPROVAL_EDIT_INVALID not mapped: fine by design (server message is user-facing Korean, no values leaked — edit_policy.py:113-121).
- Outcome composed inside scheduler `_resume`: fine; keeps `_process` short, same helper as immediate path.

## Edge cases checked (no defect)
- body_key/apply: wrapper detection shared (execution_policy.py:66-85); original tool_args not mutated (test_edit_policy.py:93); unchanged-only edits → None even on non-editable rows (:106); blank body rejected after merge (edit_policy.py:102-103); CAS failure → no execution (test_decide_edit.py:150).
- `original_tool_args` captured before in-memory mutation (decide_use_case.py:129 vs 132).
- Drawer state reset between items via `key={detailId}` (ApprovalTable.tsx:150-152).
- Detail cache invalidated on settle (queryKeys approvals.detail under approvals.all).
- Legacy react-MCP pending rows with JSON drafts stay non-editable (by design D-02: new rows only).

## Recommended actions
1. Fix G1 (resume draft section) — required for the "resumed answer reflects edit" success intent.
2. Fix G2 (ApiError code propagation) — restores FR-13 and all approval error copy.
3. Minor M1–M4; update Design §4.2 (StrictStr) and §11.2 (interfaces.py, no handlers.ts).
4. Run `uv run python -m pytest tests/domain/approval tests/application/approval tests/infrastructure/approval tests/db` and `npm run test -- approval` + `tsc`/lint to close SC-7.

## Runtime Verification Plan
L1: POST /api/v1/approvals/{id}/approve with no body → 200; with {"edited_args":{"<body_key>":"new"}} → 200, message starts "수정본으로"; with {"edited_args":{"bcc":"x"}} → 422 detail.code=APPROVAL_EDIT_INVALID and status stays pending; on JSON-fallback row → 422 APPROVAL_NOT_EDITABLE; GET detail → editable/body_key/editable_keys/display_args present; GET list → edited=true for edited row.
L2: Jobs › 승인 대기 → 상세 보기 → 수정 → change body → 수정 후 승인 → confirm → notice shown, card shows 수정됨.
L3: Action-worker agent with gate → run → edit body → approve → verify MCP received edited body AND resumed chat answer contains edited (not original) text (validates G1).

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-09-29 | 초기 정적 분석 (94.6%), G1·G2 Important |

## Act-1 (2026-09-29) — Important 수정

사용자 결정: "Important만 수정" (Minor 는 리포트 후속 과제).

| Gap | 조치 | 증거 |
|-----|------|------|
| **G1** 재개 답변 원본 초안 | `_restore_state` 가 수정된 건이면 해당 워커의 마지막 초안 메시지를 `format_draft_output(worker_id, approval.draft, <기존 집행결과 칸>)` 으로 교체 (`_replace_worker_draft`) | `src/application/agent_builder/run_agent_use_case.py` · `tests/application/approval/test_resume.py::TestRestoreEditedDraft` (4건: 교체 / `_draft_context` 가 수정본 채택 / 무수정 불변 / 타 워커 불변) |
| **G2** 오류 코드 매핑 사문화 | `ApiError` 에 `code` 추가, 인터셉터가 `detail.code` 보존, `errorPayload`·`isApprovalConflict` 가 `ApiError` 우선 판정 (AxiosError 분기 유지) | `idt_front/src/services/api/{ApiError,authClient}.ts`, `src/hooks/useApprovals.ts` · `src/hooks/useApprovals.test.ts` (실제 authApiClient + MSW 경유 6건) |
| **M3** (부수) service 바디 생략 미검증 | 테스트 추가 (구현 변경 없음 — 이미 올바름) | `src/hooks/useApprovals.test.ts` "approvalService.approve 바디" 3건 |

회귀: 백엔드 10100 passed / 53 failed (상시 목록 동일), 프론트 1314 passed / 9 failed (상시 목록 동일), tsc 210 (기준선), 변경 파일 eslint 0.

### 재산정

| Axis | Before | After | 근거 |
|------|:------:|:-----:|------|
| Structural | 97% | 97% | 변동 없음 |
| Functional | 93% | 97% | G1 해소(SC-4 의도 충족), FR-13·§5.4 Error 항목 충족. 잔여 M1(남은 시간)·M2(원본 unwrap) |
| Contract | 95% | 100% | 오류 코드 3-way 복구 |
| **Overall** | 94.6% | **98.2%** | 97×0.2 + 97×0.4 + 100×0.4 |

SC-4: Met (의도 포함). SC 7/7 Met.

### 잔여 (후속 과제)
- M1 드로어 헤더 남은 시간 표시
- M2 `원본 보기` 래퍼 해제 표시 (또는 `original_display_args` 제공)
- M4 Design §4.2 문구 — `dict[str, StrictStr]`, 비문자열은 FastAPI 기본 422
- 런타임 L1/L3: 로컬 DB V078 적용 + 본문 키 있는 부작용 MCP 등록 후 (Runtime Verification Plan 참조)
