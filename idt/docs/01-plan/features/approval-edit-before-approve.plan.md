# approval-edit-before-approve Planning Document

> **Summary**: 승인 게이트에 걸린 초안을 담당자가 **수정한 뒤 승인**할 수 있게 한다. 지금은 사소한 문구 하나가 틀려도 선택지가 "거절"밖에 없어 런을 다시 돌려야 한다. 집행은 DB의 `tool_args`를 그대로 쓰므로, 수정본을 승인 시점에 `tool_args`에 확정하고 원본은 감사용으로 보존한다. 프론트에는 지금 쓰이지 않는 상세 보기(전문·`tool_args`)와 수정 편집기를 붙인다.
>
> **Project**: sangplusbot (idt + idt_front)
> **Version**: —
> **Author**: 배상규
> **Date**: 2026-09-29
> **Status**: Draft (v0.1)
> **Depends on**: approval-gate, approval-gate-phase2-mcp-executor

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 승인 대기 건의 결정은 승인/거절 두 가지뿐이다. 에이전트 초안이 90% 맞고 한두 문장만 틀려도 담당자는 거절 → 에이전트 재실행 → 재승인을 거쳐야 한다. 게다가 작업함 카드는 `draft_preview`만 보여주고 **실제로 나갈 `tool_args`(수신자 등)는 화면에서 볼 수 없다** (`useApprovalDetail` 훅은 있으나 소비 컴포넌트 없음). |
| **Solution** | ① `POST /approvals/{id}/approve`에 선택 필드 `edited_args`(최상위 문자열 인자만)를 받아, 승인 전이와 **같은 조건부 UPDATE**로 `tool_args`·`draft`를 교체하고 원본을 `original_tool_args`에 보존. ② 재개 시 outcome에 "담당자가 수정해 집행함 + 최종 본문"을 덧붙여 이후 답변 정합성 확보. ③ 프론트 상세 드로어(전문·인자 표시) + 「수정 후 승인」 편집 모드. |
| **Function/UX Effect** | 카드에서 상세를 열면 초안 전문과 실제 호출 인자가 보이고, 「수정」을 누르면 문자열 인자(본문·제목·수신자 등)를 편집해 바로 승인할 수 있다. 변경된 필드는 원본 대비 하이라이트된다. 본문 키가 없는 건(인자 전체 JSON 초안)은 수정 불가 안내 후 승인/거절만. |
| **Core Value** | **사람은 '판정자'이자 '편집자'다.** AI 초안을 버리지 않고 고쳐 쓰게 해 승인 게이트의 운영 비용을 낮추고, "AI가 쓴 것 / 사람이 고쳐 내보낸 것"을 구분해 남겨 감사 추적과 향후 평가 데이터로 쓴다. |

---

## Context Anchor

> Auto-generated from Executive Summary. Propagated to Design/Do documents for context continuity.

| Key | Value |
|-----|-------|
| **WHY** | 초안이 조금만 틀려도 거절→재실행 외 방법이 없고, 실제 집행 인자를 화면에서 볼 수 없다. |
| **WHO** | P2 — 승인 게이트가 걸린 에이전트의 소유자(현재 유일한 승인자, `ApprovalPolicy.can_decide`). |
| **RISK** | 문자열 인자 전체 편집을 허용하므로 담당자가 수신자·대상을 바꿀 수 있다 → 변경 하이라이트 + 원본 보존 + 서버측 키/타입 불변 검증으로 통제. 예약(scheduled) 건은 승인 시점 확정값이 그대로 집행되어야 한다. |
| **SUCCESS** | 수정 승인 시 즉시·예약 집행 모두 수정본으로 MCP 호출 / 원본·편집자·시각이 DB에 남음 / 재개 답변에 수정 사실 반영 / 본문 키 없는 건은 서버가 수정 거부 / 기존 승인·거절 동작 회귀 0. |
| **SCOPE** | 백엔드(DB V078 + Domain 정책 + DecideUseCase + 라우터/스키마) → 프론트(타입·서비스·훅 + 상세 드로어 + 편집 모드). |

---

## 1. Overview

### 1.1 Purpose

승인 게이트의 결정지에 **「수정 후 승인」**을 추가해 "거의 맞는 초안"을 재실행 없이 내보낼 수 있게 하고, 승인자가 실제 집행될 인자를 보고 판단하게 한다.

### 1.2 Background

현재 흐름(코드 확인 결과):

- `ApprovalGateMiddleware._block` (`src/application/approval/gate_middleware.py`)이 도구 호출을 차단하고, `_extract_draft`가 `tool_args`에서 `draft`/`body`/`content`/`본문` 중 첫 비어있지 않은 문자열을 초안으로 뽑는다. 없으면 **인자 전체를 JSON 직렬화**해 초안으로 쓴다.
- 집행은 **`draft`가 아니라 `tool_args`**를 사용한다.
  - 즉시: `DecideApprovalUseCase._execute_now` → `executor.execute(tool_args=approval.tool_args)` (`decide_use_case.py:186`)
  - 예약: `execute_scheduler.py:96` — 며칠 뒤 DB에서 다시 읽은 `tool_args`로 집행
- 재개(`RunAgentUseCase.resume_from_snapshot`)에 주입되는 outcome은 MCP 응답(`result.output`)뿐이라, 사람이 내용을 바꿨다는 사실을 에이전트가 모른다.
- 프론트 `ApprovalCard`는 `draft_preview`만 표시하며, 상세 API(`GET /approvals/{id}` — `draft`, `tool_args` 포함)와 `useApprovalDetail` 훅은 존재하지만 **어떤 화면에서도 쓰이지 않는다.**

따라서 "초안만 고치는 UI"는 실제 발송 내용을 바꾸지 못한다. 수정 대상은 반드시 `tool_args`여야 하고, 예약 집행을 위해 **승인 시점에 DB에 확정**돼야 한다.

### 1.3 Related Documents

- 선행: `docs/01-plan/features/approval-gate.plan.md`, `docs/01-plan/features/approval-gate-phase2-mcp-executor.plan.md`
- 규칙: `docs/rules/db-session.md`, `docs/rules/tool-and-mcp.md`, `docs/rules/logging.md`
- 위키: `docs/wiki/_INDEX.md` (mcp-runtime-tool-shape 등)

---

## 2. Scope

### 2.1 In Scope

- [ ] **DB (V078)**: `approval_request`에 `original_tool_args`(JSON NULL), `edited_by`(VARCHAR(100) NULL), `edited_at`(DATETIME NULL) 추가 — 전 컬럼 COMMENT, 모델 `comment=` 동기화
- [ ] **Domain**: 수정 가능성 판정 + 수정본 검증 정책 (`ApprovalEditPolicy` — 순수 함수)
- [ ] **Application**: `DecideApprovalUseCase.approve(..., edited_args=None)` — 검증 → pending→approved 전이와 **동일 조건부 UPDATE**로 `tool_args`/`draft`/원본/편집자 기록 → 기존 즉시/예약 분기 그대로
- [ ] **재개 outcome 보강**: 수정된 건이면 outcome 앞에 "담당자가 초안을 수정해 집행함" + 최종 본문을 붙인다 (즉시·예약 두 경로 모두)
- [ ] **Interfaces**: `ApproveApprovalRequest { edited_args?: Record<string,string> }` 바디(선택) 추가, 상세 응답에 `editable`, `editable_keys`, `original_tool_args`, `edited_by`, `edited_at` 노출
- [ ] **Frontend**: 타입·서비스·훅 동기화, 승인 상세 드로어(전문·인자 표시), 편집 모드(문자열 인자 편집 + 원본 대비 변경 하이라이트 + 「수정 후 승인」), 본문 키 없는 건 수정 불가 안내
- [ ] **감사 로그**: 수정 승인 시 변경된 키 목록을 구조화 로그로 기록 (값은 남기지 않음 — PII)

### 2.2 Out of Scope

- 비문자열 인자(숫자·배열·객체) 편집, 키 추가/삭제
- 본문 키가 없는 건(인자 전체 JSON 초안)의 편집 — 승인/거절만 유지
- 역할 기반 승인자/다중 승인자 (`can_decide`는 소유자 1인 그대로)
- 도구별 "편집 금지 필드" 관리자 설정 (필요 시 후속)
- 수정 이력의 다중 버전 관리 (원본 1개 + 최종 1개만)
- `scheduled` 이후 상태에서의 재수정 (pending에서만 수정 가능)
- 수정본에 대한 PII 마스킹 등 미들웨어 재적용 (§5 리스크로 기록, 후속 판단)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 승인 요청은 **편집 가능 여부**를 가진다: 래퍼를 벗긴 `tool_args` 중 값이 저장된 `draft`와 같은 문자열 키(본문 키)가 있을 때만 editable (Design D-01 — action 워커의 사용자 지정 `draft_arg_key`·react 경로 MCP 래퍼 대응). 판정 로직은 Domain 정책 1곳에만 두고 `gate_middleware._extract_draft`도 이를 쓴다(래퍼 해제 포함, Design D-02). | High | Pending |
| FR-02 | editable 건의 **편집 가능 키 = `tool_args` 최상위의 문자열 값 키 전체**. 상세 응답에 `editable_keys`로 내려준다. | High | Pending |
| FR-03 | `POST /approvals/{id}/approve` 바디 `edited_args`(선택). 생략/빈 객체면 기존 승인과 완전히 동일하게 동작(하위 호환). | High | Pending |
| FR-04 | 서버 검증: (a) editable이 아니면 `APPROVAL_NOT_EDITABLE`(422), (b) `edited_args`의 키가 `editable_keys`의 부분집합이 아니면 `APPROVAL_EDIT_INVALID`(422), (c) 값은 문자열, (d) 본문 키는 공백만으로 비울 수 없음, (e) 필드당 길이 상한(config). | High | Pending |
| FR-05 | 원본과 동일한 값만 보냈으면 "수정 없음"으로 취급해 편집 필드를 기록하지 않는다. | Medium | Pending |
| FR-06 | 수정 승인은 `pending→approved` 조건부 UPDATE **한 번**에 `tool_args`(병합본), `draft`(재추출), `original_tool_args`(원본), `edited_by`, `edited_at`을 함께 기록한다 — 이중 클릭/동시 결정에서 수정본과 상태가 어긋나지 않게. | High | Pending |
| FR-07 | 즉시 집행·예약 집행 모두 **수정된 `tool_args`**로 MCP를 호출한다 (예약은 DB 재조회 경로가 자연히 보장 — 테스트로 고정). | High | Pending |
| FR-08 | 재개 outcome: 수정된 건이면 `"[담당자가 초안을 수정해 집행했습니다]\n최종 본문:\n{draft}\n\n도구 결과:\n{output}"` 형태로 에이전트에 주입 (형식은 Design에서 확정). 즉시/예약 두 경로 공통 헬퍼. | High | Pending |
| FR-09 | 상세 응답(`GET /approvals/{id}`)에 `editable`, `editable_keys`, `original_tool_args`, `edited_by`, `edited_at` 추가. 목록 응답에 `edited: bool` 추가(카드 배지용). | Medium | Pending |
| FR-10 | 프론트: 카드에서 「상세 보기」 → 드로어에 초안 전문 + `tool_args` 표(읽기 전용) + 상태/이력(편집자·편집 시각·원본 보기). | High | Pending |
| FR-11 | 프론트: editable & pending이면 「수정」 → `editable_keys` 필드를 입력창으로 전환(본문은 textarea), 원본 대비 변경된 필드 하이라이트, 「수정 후 승인」/「취소」. 확인 다이얼로그에 **변경된 필드 목록**(특히 본문 외 필드 변경 시 경고 톤) 표시. | High | Pending |
| FR-12 | 프론트: editable이 아니면 「수정」 비활성 + "이 도구는 본문 필드가 없어 수정할 수 없습니다. 승인 또는 거절해 주세요." 안내. | Medium | Pending |
| FR-13 | 새 에러 코드 문구를 `APPROVAL_ERROR_MESSAGES`에 추가 (`APPROVAL_NOT_EDITABLE`, `APPROVAL_EDIT_INVALID`). | Medium | Pending |
| FR-14 | 감사: 수정 승인 시 `approval edited` info 로그에 `approval_id`, `changed_keys`, `edited_by`만 기록 (값 미기록). | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 하위 호환 | 바디 없는 기존 승인 호출·기존 행(NULL 편집 컬럼) 동작 불변 | 기존 approval 테스트 전량 통과 |
| 정합성 | 수정본 기록과 상태 전이가 단일 조건부 UPDATE | 동시 승인 테스트(영향 행 0 → Conflict) |
| 보안 | 키 추가/타입 변경 불가, 권한은 기존 `can_decide` | 단위 테스트(검증 실패 케이스) |
| 개인정보 | 수정 값은 로그에 남기지 않음 | verify-logging + 로그 캡처 테스트 |
| 아키텍처 | 검증 규칙은 domain, 라우터엔 로직 없음 | verify-architecture |
| DDL | 신규 컬럼 COMMENT 필수 | `tests/db/test_migration_ddl_comments.py` |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] SC-1: 수정 후 **즉시 집행** 시 executor가 받은 `tool_args`가 병합 수정본과 일치 (단위 테스트)
- [ ] SC-2: 수정 후 **예약 집행** 시 스케줄러가 수정본으로 집행 (단위 테스트)
- [ ] SC-3: `original_tool_args`/`edited_by`/`edited_at`이 저장되고, 무수정 승인에서는 NULL 유지
- [ ] SC-4: 수정된 건의 재개 outcome에 수정 안내 + 최종 본문 포함 (즉시·예약)
- [ ] SC-5: 본문 키 없는 건 / 비허용 키 / 비문자열 / 빈 본문 → 422 + 상태 `pending` 유지
- [ ] SC-6: 프론트 드로어에서 전문·인자 확인, 편집→「수정 후 승인」 요청 바디가 변경 필드만 포함 (Vitest + MSW)
- [ ] SC-7: 기존 approval 백엔드/프론트 테스트 회귀 0

### 4.2 Quality Criteria

- [ ] 신규 코드 TDD (Red→Green→Refactor), 함수 40줄 / if 중첩 2단계 준수
- [ ] verify-architecture, verify-logging, verify-tdd 통과
- [ ] 프론트 `npm run lint`, `tsc` 무오류

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 문자열 인자 전체 편집으로 담당자가 **수신자·대상 식별자**를 바꿈 (오발송·권한 우회) | High | Medium | 서버는 키/타입 불변만 강제(대상 변경 자체는 소유자 권한 내 결정으로 허용), UI 확인 다이얼로그에서 본문 외 필드 변경을 경고 톤으로 명시, 원본 보존 + `changed_keys` 감사 로그. 도구별 편집 금지 필드는 후속 과제로 명시. |
| 예약 건: 승인 후 집행까지 수정본 유실 | High | Low | 수정본을 승인 전이와 같은 UPDATE로 `tool_args`에 확정 → 스케줄러는 기존대로 DB 재조회 (SC-2로 고정) |
| 재개된 에이전트가 원본 기준으로 답변 | Medium | High(현행) | FR-08 outcome 보강 |
| 수정본이 PII 마스킹 등 미들웨어를 우회 | Medium | Medium | 사람이 직접 쓴 내용이므로 1차는 비적용으로 결정, Design에서 재검토 항목으로 명시 |
| `idempotency_key`가 원본 기준이라 수정본 집행과 의미 불일치 | Low | Low | 키는 "이 승인 건의 1회 집행" 보장용이므로 유지 (Design에서 확인) |
| 편집 가능 판정 로직이 middleware와 이중화 | Medium | Medium | `_DRAFT_KEYS`와 추출 로직을 domain 정책으로 옮기고 middleware가 이를 호출 (동작 불변 리팩토링, 기존 테스트로 보호) |
| 거대 본문 입력 | Low | Low | 필드 길이 상한 config (FR-04e) |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `approval_request` 테이블 | DB | 컬럼 3개 추가 (NULL 허용) — V078 |
| `ApprovalRequestModel` / `ApprovalRequest` entity | Model/Entity | 필드 3개 추가 |
| `ApprovalRepository.compare_and_set_status` | Repository | 추가 필드(`tool_args`, `draft`, 편집 컬럼) 갱신 허용 — kwargs 화이트리스트 확인 |
| `_DRAFT_KEYS` / `_extract_draft` | Application → Domain | domain 정책으로 이동, middleware는 호출만 |
| `DecideApprovalUseCase.approve` | UseCase | `edited_args` 선택 인자 |
| `_resume` outcome 조립 (Decide + ExecuteScheduler) | UseCase | 수정 안내 접두 |
| `POST /approvals/{id}/approve` | API | 선택 바디 추가 (하위 호환) |
| `ApprovalDetail` / `ApprovalItem` 스키마 | API Schema | 필드 추가 |
| `idt_front/src/types/approval.ts`, `services/approvalService.ts`, `hooks/useApprovals.ts` | Front | 타입·요청 바디·훅 |
| `pages/JobsPage/ApprovalCard.tsx`, 신규 상세 드로어 | Front UI | 상세 보기·편집 모드 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `approval_request` | CREATE | `RunAgentUseCase` 게이트 적재 → `ApprovalRepository.save` | None (신규 컬럼 NULL) |
| `approval_request` | READ | `ListApprovalsUseCase.list`, `DecideApprovalUseCase.get`, `ExecuteDueApprovalsUseCase` | Needs verification (매퍼에 필드 추가) |
| `approval_request` | UPDATE | `compare_and_set_status` (approve/reject/schedule/execute/fail/expire) | Needs verification (추가 필드 전달 경로) |
| `tool_args` | READ | `decide_use_case.py:186`, `execute_scheduler.py:96` → `McpActionExecutor` | None (수정본이 들어있을 뿐 형태 동일) |
| `_extract_draft` | CALL | `ApprovalGateMiddleware._block` | Needs verification (이동 후 동작 동일) |
| approve API | CALL | `idt_front/src/services/approvalService.ts` approve | None (바디 선택) |
| `ApprovalItem` 타입 | READ | `ApprovalCard`, `ApprovalTable`, `JobsPage` 배지 | None (필드 추가만) |

### 6.3 Verification

- [ ] 위 consumer 전부 변경 후 동작 확인
- [ ] 권한 경로(`can_decide`) 변경 없음
- [ ] 필드 추가만 있고 제거·타입 변경 없음

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules | Web apps with backend | ☐ |
| **Enterprise** | Strict layer separation, DI | Complex architectures | ☑ (Thin DDD) |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 편집 대상 | draft만 / 문자열 인자 전체 / JSON 전체 | **문자열 인자 전체 (본문 키 있는 건만)** | 사용자 결정. 집행 진실은 `tool_args`이므로 draft만 수정은 무의미 |
| 저장 방식 | 별도 테이블 이력 / 원본 컬럼 보존 | **원본 컬럼 1개 + 편집자/시각** | 다중 버전 요구 없음, 과도한 추상화 금지 |
| API 형태 | 별도 `approve-with-edit` / 기존 approve 선택 바디 | **기존 approve 선택 바디** | 상태 기계·권한·만료·에이전트 변경 검사 경로 재사용 |
| 원자성 | 편집 UPDATE 후 전이 / 전이와 동시 기록 | **전이 UPDATE에 함께 기록** | 이중 클릭·동시 결정에서 수정본/상태 불일치 방지 |
| 재개 통지 | 미통지 / outcome 접두 | **outcome 접두 + 최종 본문** | 사용자 결정. 이후 답변 정합성 |
| 프론트 상태 | 로컬 state / Zustand | **컴포넌트 로컬 state + TanStack Query** | 편집은 드로어 내부 일시 상태 |

### 7.3 Layer Mapping

```
domain/approval/policies.py        ApprovalEditPolicy (editable 판정, editable_keys, 검증, 병합, 본문 재추출)
application/approval/decide_use_case.py   approve(edited_args) + outcome 조립 헬퍼
application/approval/execute_scheduler.py outcome 헬퍼 재사용
application/approval/gate_middleware.py   draft 추출을 domain 정책에 위임
infrastructure/approval/{models,repository}.py  컬럼·매핑
interfaces/schemas/approval.py, api/routes/approval_router.py  바디·응답
db/migration/V078__add_edit_columns_to_approval_request.sql
idt_front: types/approval.ts, services/approvalService.ts, hooks/useApprovals.ts,
           pages/JobsPage/ApprovalCard.tsx, pages/JobsPage/ApprovalDetailDrawer.tsx(신규)
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md` 3종 (root / idt / idt_front) 코딩 규칙
- [x] `idt/docs/rules/` 세부 규칙 (db-session, logging, testing, tool-and-mcp)
- [x] DDL COMMENT 검사 테스트 (V054 이후)
- [x] 프론트 규칙: 컴포넌트 파일 런타임 상수 export 금지 → 상수는 `src/types/approval.ts`
- [x] 프론트 에러: `ApiError(message, status)` 인터셉터 — `err.response` 아님

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| 에러 코드 | exists (`APPROVAL_*`) | `APPROVAL_NOT_EDITABLE`, `APPROVAL_EDIT_INVALID` 추가 | High |
| 설정값 | exists (`approval_execution_config`) | 편집 필드 길이 상한 | Medium |

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| (선택) `APPROVAL_EDIT_MAX_FIELD_CHARS` | 편집 필드 길이 상한 | Server | ☐ (Design에서 config 기본값으로 대체 가능 여부 결정) |

---

## 9. Next Steps

1. [ ] `/pdca design approval-edit-before-approve` — outcome 문구·에러 매핑·드로어 와이어프레임·V078 DDL 확정
2. [ ] 사용자 리뷰
3. [ ] TDD 구현 (백엔드 → API 계약 동기화 → 프론트)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-29 | Initial draft (편집 범위=본문 키 있는 건의 문자열 인자 전체, 재개 통지 포함, 풀스택) | 배상규 |
| 0.2 | 2026-09-29 | FR-01 본문 키 판정을 Design D-01/D-02에 맞춰 수정 (draft 값 일치 + MCP 래퍼 해제) | 배상규 |
