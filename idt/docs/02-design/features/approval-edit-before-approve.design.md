# approval-edit-before-approve Design Document

> **Summary**: 승인 대기 건을 담당자가 **수정한 뒤 승인**하는 경로. 본문 키는 "래퍼를 벗긴 인자 중 값이 저장된 draft와 같은 문자열 키"로 판정하고, 수정본은 `pending→approved` 조건부 UPDATE 한 문장에 원본·편집자와 함께 확정한다. 재개 outcome에 수정 사실을 싣고, 프론트는 상세 드로어(보기/편집)를 추가한다.
>
> **Project**: sangplusbot (idt + idt_front)
> **Version**: —
> **Author**: 배상규
> **Date**: 2026-09-29
> **Status**: Draft (v0.1)
> **Planning Doc**: [approval-edit-before-approve.plan.md](../../01-plan/features/approval-edit-before-approve.plan.md)
> **Architecture**: Option C — Pragmatic Balance

---

## Context Anchor

> Copied from Plan document. Ensures strategic context survives Design→Do handoff.

| Key | Value |
|-----|-------|
| **WHY** | 초안이 조금만 틀려도 거절→재실행 외 방법이 없고, 실제 집행 인자를 화면에서 볼 수 없다. |
| **WHO** | P2 — 승인 게이트가 걸린 에이전트의 소유자(현재 유일한 승인자, `ApprovalPolicy.can_decide`). |
| **RISK** | 문자열 인자 전체 편집을 허용하므로 담당자가 수신자·대상을 바꿀 수 있다 → 변경 하이라이트 + 원본 보존 + 서버측 키/타입 불변 검증으로 통제. 예약(scheduled) 건은 승인 시점 확정값이 그대로 집행되어야 한다. |
| **SUCCESS** | 수정 승인 시 즉시·예약 집행 모두 수정본으로 MCP 호출 / 원본·편집자·시각이 DB에 남음 / 재개 답변에 수정 사실 반영 / 본문 키 없는 건은 서버가 수정 거부 / 기존 승인·거절 동작 회귀 0. |
| **SCOPE** | 백엔드(DB V078 + Domain 정책 + DecideUseCase + 라우터/스키마) → 프론트(타입·서비스·훅 + 상세 드로어 + 편집 모드). |

---

## 0. Plan 대비 변경 (Design 단계에서 발견)

| # | Plan 가정 | 코드 사실 | Design 결정 |
|---|-----------|-----------|-------------|
| D-01 | editable = `tool_args`에 `_DRAFT_KEYS` 문자열 키 존재 | 게이트 경로가 둘이다. **action 워커**(`action_pipeline.py:253`)는 평탄 인자 + 워커 설정 `draft_arg_key`(관례 키가 아닐 수 있음). **react 워커**(`gate_middleware._block`)의 MCP 도구는 `{"arguments": {...}}` 래퍼(`McpArgumentPolicy.unwrap` D-03). | **본문 키 = 래퍼를 벗긴 인자 중 값이 저장된 `draft`와 정확히 같은 문자열 키**. 두 경로·사용자 지정 키 모두 커버, 신규 컬럼 불필요. |
| D-02 | (없음) | react 경로 MCP는 `_extract_draft`가 최상위만 봐서 초안이 **인자 전체 JSON**이 된다 → 승인 화면에서 본문이 안 보이고 D-01 판정으로도 편집 불가. | `extract_draft`가 **unwrap 후** 관례 키를 찾도록 수정(사용자 승인). 신규 적재분부터 적용, 기존 행 불변. |
| D-03 | 편집 키 = `tool_args` 최상위 문자열 키 | 래퍼가 있으면 최상위는 `arguments` 하나뿐 | 편집 키·`edited_args` 키는 **unwrap된 레벨** 기준. 저장 시 원래 래퍼 모양으로 재포장. |

---

## 1. Overview

### 1.1 Design Goals

1. 수정본이 **집행의 진실(`tool_args`)**에 확정된다 — 즉시·예약 경로 모두 추가 분기 없이 수정본을 집행.
2. 수정 기록과 상태 전이가 **원자적**이다 — 이중 클릭·동시 결정에서 "수정본 없이 승인" 또는 "수정만 되고 pending"이 생기지 않는다.
3. 판정·검증은 **domain 순수 함수 1곳** — 미들웨어·UseCase·응답 매핑이 같은 규칙을 본다.
4. 기존 호출(바디 없는 approve)·기존 행(편집 컬럼 NULL)은 **완전히 동일하게** 동작한다.

### 1.2 Design Principles

- 집행기(`McpActionExecutor`)는 수정 여부를 모른다 — 범용 집행 경로 유지.
- 값은 로그에 남기지 않는다(키 목록만) — 기존 `ActionArgumentPolicy.summarize_keys` 원칙과 동일.
- Thin DDD: 새 UseCase·테이블을 만들지 않고 기존 `approve`와 `approval_request`를 확장.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | 판정·검증을 UseCase private 함수로, 카드 인라인 편집 | `PATCH /draft` 별도 단계 + 편집 이력 테이블 | domain 정책 + 기존 approve 확장 + 상세 드로어 |
| **New Files** | ~1 | ~8 | ~4 |
| **Modified Files** | ~12 | ~16 | ~14 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Medium (규칙이 application에 섞임) | High | High |
| **Effort** | Low | High | Medium |
| **Risk** | 카드 비대화, 규칙 중복 | 편집~승인 사이 경합, 스키마 증가 | Low |

**Selected**: **Option C** — 규칙을 domain에 모아 미들웨어(D-02)와 공유하고, 단일 CAS로 원자성을 얻으며, 편집 이력은 원본 1개로 충분(Plan §2.2).

### 2.1 Component Diagram

```
[ApprovalTable] ─open─▶ [ApprovalDetailDrawer] ──GET detail──▶ approval_router.get
                               │ (편집 모드)                         │
                               └──POST approve {edited_args}──▶ approval_router.approve
                                                                     │
                                                    DecideApprovalUseCase.approve
                                                      ├─ ApprovalEditPolicy.apply   (domain)
                                                      ├─ repo.compare_and_set_status  (1 UPDATE)
                                                      └─ _execute_now / _schedule
                                                              │
                                                    McpActionExecutor (불변)
                                                              │
                                  ApprovalOutcomePolicy.compose ─▶ resumer.resume_from_snapshot
ExecuteDueApprovalsUseCase._process ──(DB의 수정본 tool_args)──▶ 동일 compose ─▶ resume
```

### 2.2 Data Flow (수정 후 승인)

```
edited_args(unwrapped 키) ─▶ load_and_authorize(권한·만료·pending·정의변경)
  ─▶ ApprovalEditPolicy.apply(tool_args, draft, edited_args, max_chars)
        ├ body_key 없음 → NotEditable
        ├ 키 ⊄ editable_keys / 비문자열 / 본문 공백 / 길이 초과 → EditInvalid
        └ 변경 0건 → None (일반 승인과 동일)
  ─▶ gate 해석 + 예약 창 검증 (기존)
  ─▶ CAS pending→approved + {tool_args, draft, original_tool_args, edited_by, edited_at}
  ─▶ 즉시 집행(수정본) 또는 scheduled (스케줄러가 DB 수정본 재조회)
  ─▶ resume outcome = compose(output, edited=True, draft=최종 본문)
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `ApprovalEditPolicy` | `McpArgumentPolicy` (unwrap/rewrap) | 래퍼 처리 일원화 |
| `ApprovalGateMiddleware` | `ApprovalEditPolicy.extract_draft` | D-02 초안 추출 공유 |
| `DecideApprovalUseCase` | `ApprovalEditPolicy`, `ApprovalOutcomePolicy`, `edit_max_field_chars` | 편집 확정·outcome |
| `ExecuteDueApprovalsUseCase` | `ApprovalOutcomePolicy` | 예약 경로 outcome |

---

## 3. Data Model

### 3.1 Entity (`src/domain/approval/entity.py`)

```python
@dataclass
class ApprovalRequest:
    ...  # 기존 필드
    # approval-edit-before-approve: 담당자 수정 (V078). 무수정이면 모두 None.
    original_tool_args: dict | None = None  # 수정 전 원본 (감사용)
    edited_by: str | None = None
    edited_at: datetime | None = None

    @property
    def is_edited(self) -> bool:
        return self.edited_at is not None


@dataclass(frozen=True)
class ApprovalEdit:
    """ApprovalEditPolicy.apply 결과 — CAS 에 그대로 실린다."""
    tool_args: dict        # 재포장된 최종 인자
    draft: str             # 최종 본문 (tool_args[body_key])
    changed_keys: tuple[str, ...]
```

### 3.2 Domain Policy (`src/domain/approval/edit_policy.py` 신규)

```python
class ApprovalEditError(ValueError):
    """reason: 'not_editable' | 'invalid'. UseCase 가 application 오류로 번역."""
    def __init__(self, reason: str, message: str): ...

class ApprovalEditPolicy:
    DRAFT_KEYS: tuple[str, ...] = ("draft", "body", "content", "본문")

    @classmethod
    def extract_draft(cls, tool_args: dict) -> str:
        """D-02: unwrap 후 관례 키 탐색, 없으면 원본 전체 JSON (기존 폴백 유지)."""

    @classmethod
    def body_key(cls, tool_args: dict, draft: str) -> str | None:
        """D-01: unwrap 인자 중 값 == draft 인 문자열 키. DRAFT_KEYS 순서 우선,
        그다음 dict 순서. draft 가 공백이면 None."""

    @classmethod
    def editable_keys(cls, tool_args: dict, draft: str) -> list[str]:
        """body_key 가 있을 때만 unwrap 인자의 문자열 값 키 전체.
        McpArgumentPolicy.IDEMPOTENCY_PARAM 은 제외."""

    @classmethod
    def display_args(cls, tool_args: dict) -> dict:
        """화면 표시용 unwrap 인자."""

    @classmethod
    def apply(cls, tool_args: dict, draft: str, edits: dict | None,
              *, max_chars: int) -> ApprovalEdit | None:
        """검증 → 병합 → 재포장. 변경 0건이면 None.
        실패: body_key None → not_editable / 키 불허·비문자열·본문 공백·
        길이 초과 → invalid."""
```

`McpArgumentPolicy`에 `is_wrapped(tool_args) -> bool`, `rewrap(original, inner) -> dict` 두 classmethod 추가(unwrap과 같은 판정식 공유).

`ActionArgumentPolicy.DRAFT_KEY_CANDIDATES`는 `ApprovalEditPolicy.DRAFT_KEYS`를 참조하도록 바꿔 순서 동기화 주석을 코드로 대체한다(domain→domain 참조, 동작 불변).

### 3.3 Outcome Policy (`src/domain/approval/policies.py`에 추가)

```python
class ApprovalOutcomePolicy:
    DRAFT_MAX_CHARS = 4000  # 재개 컨텍스트 폭주 방지

    @classmethod
    def compose(cls, output: str, *, edited: bool, draft: str) -> str:
        if not edited:
            return output                      # 기존과 바이트 동일
        body = draft[:cls.DRAFT_MAX_CHARS]
        return (
            "[담당자가 초안을 수정해 집행했습니다. 아래 최종 본문을 기준으로 답하세요]\n"
            f"최종 본문:\n{body}\n\n도구 결과:\n{output}"
        )
```

### 3.4 Database Schema — `db/migration/V078__add_edit_columns_to_approval_request.sql`

```sql
ALTER TABLE approval_request
    ADD COLUMN original_tool_args JSON NULL
        COMMENT '담당자 수정 전 원본 도구 인자. NULL=무수정 (approval-edit-before-approve)' AFTER draft,
    ADD COLUMN edited_by VARCHAR(100) NULL
        COMMENT '초안을 수정해 승인한 사용자 ID. NULL=무수정' AFTER original_tool_args,
    ADD COLUMN edited_at DATETIME NULL
        COMMENT '초안 수정 확정 시각(UTC). NULL=무수정' AFTER edited_by;
```

`ApprovalRequestModel`에 같은 3컬럼 + 동일 `comment=`. 인덱스 없음(조회 조건 아님).

### 3.5 Repository

- `compare_and_set_status(..., tool_args=None, draft=None, original_tool_args=None, edited_by=None, edited_at=None)` — `_changed_values`가 None을 SET에서 제외하므로 기존 호출 불변.
- `_to_model` / `_to_entity`에 3필드 매핑.

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | Change | Auth |
|--------|------|--------|------|
| GET | `/api/v1/approvals` | 항목에 `edited: bool` 추가 | Required |
| GET | `/api/v1/approvals/{id}` | `editable`, `body_key`, `editable_keys`, `display_args`, `original_tool_args`, `edited_by`, `edited_at` 추가 | Required |
| POST | `/api/v1/approvals/{id}/approve` | 선택 바디 `{edited_args}` | Required |

### 4.2 Detailed Specification

#### `POST /api/v1/approvals/{id}/approve?execute_only=false`

**Request (선택 — 생략 시 기존과 동일):**
```json
{ "edited_args": { "body": "수정된 본문", "subject": "제목 수정" } }
```
- 키는 `display_args`(unwrap) 레벨. 값은 문자열만. 변경된 키만 보내도 되고 전체를 보내도 된다(동일 값은 무시).

**Response (200):** 기존 `ApprovalDecisionResponse` 불변. `message`는 수정 시 앞에 "수정본으로 " 접두(예: "수정본으로 집행되었습니다.").

**Schema:**
```python
class ApproveApprovalRequest(BaseModel):
    edited_args: dict[str, str] | None = Field(default=None, max_length=50)
```
라우터: `body: ApproveApprovalRequest | None = None` → `use_case.approve(..., edited_args=body.edited_args if body else None)`.

#### `GET /api/v1/approvals/{id}` 추가 필드

```json
{
  "...": "기존 필드",
  "editable": true,
  "body_key": "body",
  "editable_keys": ["body", "subject", "to"],
  "display_args": { "to": "a@x.com", "subject": "...", "body": "...", "priority": 1 },
  "original_tool_args": null,
  "edited_by": null,
  "edited_at": null
}
```

계산 위치: `DecideApprovalUseCase.get`이 `ApprovalDetailView(approval, agent_name, body_key, editable_keys, display_args)`를 반환(application DTO). 라우터는 매핑만 한다.

---

## 5. UI/UX Design

### 5.1 Screen Layout — ApprovalDetailDrawer (우측 슬라이드, 모바일 전체폭)

```
┌──────────────────────────────── 승인 상세 ──[×]┐
│ {에이전트명}  [승인 대기] [수정됨]               │
│ 도구: mcp:mail:send_mail   만료: …(3시간 남음)   │
├────────────────────────────────────────────────┤
│ 본문 (body)                          [보기 모드] │
│ ┌────────────────────────────────────────────┐ │
│ │ 초안 전문 (whitespace-pre-wrap, 스크롤)      │ │
│ └────────────────────────────────────────────┘ │
│ 호출 인자                                       │
│  to        a@x.com                              │
│  subject   9월 정산 안내                         │
│  priority  1            (문자열 아님 · 수정 불가) │
│ ▸ 원본 보기 (수정된 건만)                         │
├────────────────────────────────────────────────┤
│ [거절]                        [수정]  [승인]     │
└────────────────────────────────────────────────┘
편집 모드: 본문=textarea, 다른 editable 키=input, 변경 필드는 amber 테두리
           하단 버튼 → [취소] [수정 후 승인]
확인 다이얼로그: "다음 필드를 수정해 승인합니다: body, to"
           본문 외 필드 변경 시 경고 문구(빨강): "수신자·대상 등 본문 외 값이 바뀌었습니다."
```

### 5.2 User Flow

```
작업함 › 승인 대기 탭 › 카드 [상세 보기] → 드로어(보기)
  → [승인] (기존과 동일)
  → [수정] → 편집 → [수정 후 승인] → 확인 다이얼로그 → POST approve {edited_args}
       → 성공: 드로어 닫힘 + notice / 409: 안내 + 목록 새로고침 / 422: 드로어 유지 + 오류 표시
  → [거절] → RejectReasonDialog (기존)
editable=false: [수정] 비활성 + 툴팁/안내 "이 도구는 본문 필드를 찾을 수 없어 수정할 수 없습니다. 승인 또는 거절해 주세요."
```

### 5.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `ApprovalDetailDrawer` (신규) | `src/pages/JobsPage/ApprovalDetailDrawer.tsx` | 상세 조회·보기/편집 모드·확인 다이얼로그 |
| `ApprovalCard` (수정) | `src/pages/JobsPage/ApprovalCard.tsx` | [상세 보기] 버튼, `수정됨` 배지 |
| `ApprovalTable` (수정) | `src/pages/JobsPage/ApprovalTable.tsx` | `detailTarget` 상태, 승인 핸들러에 `editedArgs` 전달 |
| `approvalEdit` utils (신규) | `src/utils/approvalEdit.ts` | `diffEditedArgs(display, form)` → 변경 키만, `hasNonBodyChange` |
| types/service/hooks (수정) | `src/types/approval.ts`, `src/services/approvalService.ts`, `src/hooks/useApprovals.ts` | 계약 동기화 |

### 5.4 Page UI Checklist

#### 작업함 › 승인 대기 탭 (ApprovalCard)
- [ ] Button: `상세 보기` (모든 상태에서 노출)
- [ ] Badge: `수정됨` (`item.edited === true`일 때)
- [ ] 기존 승인/거절 버튼·초안 미리보기 유지

#### ApprovalDetailDrawer
- [ ] Header: 에이전트명, 상태 배지, `수정됨` 배지(조건부), 도구 ID, 만료(남은 시간)
- [ ] Section: 초안 전문 (`draft`, pre-wrap, 본문 키 라벨 `본문 ({body_key})`)
- [ ] Table: `display_args` 키/값 — 문자열 아닌 값은 JSON 표시 + "수정 불가" 표기
- [ ] Toggle: `원본 보기` (`original_tool_args`가 있을 때) + 편집자·편집 시각
- [ ] Button: `수정` (pending && editable), 비활성 시 안내 문구
- [ ] Edit: 본문 textarea, 기타 editable 키 input, 변경 필드 amber 강조
- [ ] Button: `취소`, `수정 후 승인` (변경 0건이면 비활성)
- [ ] ConfirmDialog: 변경 키 목록, 본문 외 변경 시 경고 문구
- [ ] Button: `승인`, `거절` (pending일 때, 보기 모드)
- [ ] Error: 422/409/410 문구(`APPROVAL_ERROR_MESSAGES`)

---

## 6. Error Handling

### 6.1 Error Code Definition

| Code | HTTP | Cause | Front 문구 |
|------|:----:|-------|-----------|
| `APPROVAL_NOT_EDITABLE` | 422 | body_key 판정 불가 건에 `edited_args` | 이 요청은 본문을 찾을 수 없어 수정할 수 없습니다. 승인 또는 거절해 주세요. |
| `APPROVAL_EDIT_INVALID` | 422 | 불허 키·비문자열·본문 공백·길이 초과 | 수정 내용이 올바르지 않습니다. {서버 message} |
| 기존 `APPROVAL_NOT_PENDING`/`EXPIRED`/`FORBIDDEN`/`AGENT_CHANGED`/`INVALID_WINDOW` | 기존 | 기존 | 기존 |

`src/application/approval/errors.py`에 `ApprovalNotEditableError`, `ApprovalEditInvalidError` 추가. UseCase가 `ApprovalEditError.reason`으로 분기해 번역하며 `raise ... from e`로 원인 보존.

**검증 순서**: 권한 → 만료 → pending → 정의변경 → **편집 검증** → 예약 창 → CAS. 편집 검증이 CAS 앞이므로 실패 시 상태는 `pending` 그대로.

### 6.2 Error Response Format

기존 `_http(error)` 그대로: `{"detail": {"code": "...", "message": "..."}}`.

---

## 7. Security Considerations

- [ ] 권한: 기존 `can_decide`(소유자) 불변 — 편집은 승인 권한에 포함
- [ ] 키 추가 불가·타입 변경 불가(서버 강제) — 인젝션으로 새 파라미터 주입 차단
- [ ] 멱등키(`idempotency_key` 파라미터) 편집 불가 — `editable_keys`에서 제외
- [ ] 길이 상한 `approval_edit_max_field_chars`(config, 기본 20000)
- [ ] 로그: `approval edited` info — `approval_id`, `changed_keys`, `edited_by`만. 값 금지
- [ ] 본문 외 필드 변경은 UI 경고 + 원본 보존으로 사후 추적
- [ ] 수정본의 PII 마스킹 재적용은 **하지 않음**(사람이 직접 작성) — 리포트에 결정 기록

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit (domain) | `ApprovalEditPolicy`, `ApprovalOutcomePolicy`, `McpArgumentPolicy.rewrap` | pytest |
| Unit (application) | `DecideApprovalUseCase.approve/get`, `ExecuteDueApprovalsUseCase`, 미들웨어 초안 | pytest + fake repo |
| Infra | repository CAS 확장·매핑, V078 DDL COMMENT | pytest (sqlite) + `test_migration_ddl_comments.py` |
| API | approval_router | TestClient |
| Front | utils/drawer/table | Vitest + RTL + MSW |

### 8.2 Backend Scenarios

| # | Target | Scenario | Expected |
|---|--------|----------|----------|
| B1 | EditPolicy.body_key | action 경로(평탄, `message` 키 = draft) | `"message"` |
| B2 | EditPolicy.body_key | react 경로 래퍼 `{"arguments":{"body":d}}` | `"body"` |
| B3 | EditPolicy.body_key | draft가 JSON 폴백(일치 키 없음) | `None` |
| B4 | EditPolicy.editable_keys | 문자열/숫자/멱등키 혼합 | 문자열 키만, `idempotency_key` 제외 |
| B5 | EditPolicy.apply | 래퍼 건 수정 | 결과 `tool_args`가 래퍼 모양 유지, `draft` = 새 본문 |
| B6 | EditPolicy.apply | 동일 값만 전송 / 빈 dict / None | `None` |
| B7 | EditPolicy.apply | 불허 키, 비문자열, 본문 공백, 길이 초과 | `ApprovalEditError(invalid)` |
| B8 | EditPolicy.apply | body_key 없음 + edits 있음 | `ApprovalEditError(not_editable)` |
| B9 | EditPolicy.extract_draft | 래퍼 안 `body` | 본문 문자열 (D-02) |
| B10 | OutcomePolicy.compose | edited False | 입력 output 그대로 |
| B11 | OutcomePolicy.compose | edited True, 긴 draft | 접두 + 4000자 절단 본문 + output |
| B12 | Decide.approve | edited_args → 즉시 집행 | executor 인자 = 수정본, CAS에 5필드, resume outcome에 접두 (SC-1, SC-4) |
| B13 | Decide.approve | edited_args + execute_after 있음 | `scheduled`, CAS에 수정본 저장 (SC-2 전반부) |
| B14 | Scheduler._process | 수정된 scheduled 건 | executor 인자 = DB 수정본, outcome 접두 (SC-2, SC-4) |
| B15 | Decide.approve | 편집 검증 실패 | 422 오류, `compare_and_set_status` 미호출 (SC-5) |
| B16 | Decide.approve | edited_args 없음 | 기존 테스트 전량 통과, CAS에 편집 필드 없음 (SC-3, SC-7) |
| B17 | Decide.approve | CAS 영향 0 (동시 결정) | `ApprovalConflictError`, 집행 없음 |
| B18 | Decide.get | 상세 뷰 | `body_key`, `editable_keys`, `display_args` 계산 |
| B19 | Middleware | react MCP 래퍼 호출 | 마커 draft = 본문 (D-02) |
| B20 | Repository | CAS 확장 + 왕복 매핑 | 3필드 저장·복원, None 미SET |
| B21 | Router | 바디 없음 / 바디 있음 / 422 매핑 | 200 / 200 / `{"detail":{"code":"APPROVAL_EDIT_INVALID"}}` |
| B22 | Logging | 수정 승인 | 로그에 값 없음, `changed_keys`만 |

### 8.3 Frontend Scenarios

| # | Target | Action | Expected |
|---|--------|--------|----------|
| F1 | `diffEditedArgs` | 일부 변경 | 변경 키만 반환, 동일값 제외 |
| F2 | ApprovalCard | 렌더 | `상세 보기` 버튼, `edited`면 `수정됨` 배지 |
| F3 | Drawer | 열기 | 초안 전문·인자 표 렌더 (MSW detail) |
| F4 | Drawer | editable=false | `수정` 비활성 + 안내 문구 |
| F5 | Drawer | 편집→수정 후 승인→확인 | POST 바디에 변경 키만 (SC-6) |
| F6 | Drawer | 본문 외 필드 변경 | 확인 다이얼로그에 경고 문구 |
| F7 | Drawer | 422 응답 | 드로어 유지 + 오류 문구 |
| F8 | ApprovalTable | 기존 승인/거절 | 기존 테스트 회귀 0 (SC-7) |

### 8.4 Seed Data

| Entity | Count | Key Fields |
|--------|:-----:|-----------|
| approval_request (fixture) | 3 | 평탄 body 건 / 래퍼 body 건 / JSON 폴백 건 |

---

## 9. Clean Architecture — Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `ApprovalEditPolicy`, `ApprovalEdit`, `ApprovalEditError` | Domain | `src/domain/approval/edit_policy.py`, `entity.py` |
| `ApprovalOutcomePolicy` | Domain | `src/domain/approval/policies.py` |
| `McpArgumentPolicy.is_wrapped/rewrap` | Domain | `src/domain/approval/execution_policy.py` |
| `DecideApprovalUseCase` 확장, `ApprovalDetailView` | Application | `src/application/approval/decide_use_case.py` |
| `ExecuteDueApprovalsUseCase` outcome | Application | `src/application/approval/execute_scheduler.py` |
| 미들웨어 초안 위임 | Application | `src/application/approval/gate_middleware.py` |
| 오류 2종 | Application | `src/application/approval/errors.py` |
| 모델·리포지토리 | Infrastructure | `src/infrastructure/approval/{models,repository}.py` |
| 스키마·라우터·DI | Interfaces | `src/interfaces/schemas/approval.py`, `src/api/routes/approval_router.py`, `src/api/main.py` |
| 설정 | Config | `src/config.py` `approval_edit_max_field_chars: int = 20000` |

의존 방향: interfaces → application → domain ← infrastructure. domain은 langchain·DB를 모른다.

---

## 10. Coding Convention Reference

- 함수 40줄 / if 중첩 2단계 — `approve`는 `_prepare_edit`, `_edit_fields`로 분리
- 모든 except는 `logger.error(..., exception=e)` 또는 `raise ... from e`
- 프론트: 런타임 상수는 `src/types/approval.ts`, 컴포넌트 파일 export 금지
- Design Ref 주석: `# Design Ref: approval-edit-before-approve §N — ...`

---

## 11. Implementation Guide

### 11.1 Implementation Order

1. Domain 정책 + 테스트 (B1–B11)
2. DB/Infra (V078, 모델, 엔티티, 리포지토리) + 테스트 (B20, DDL)
3. Application (Decide, Scheduler, 미들웨어, 오류, config) + 테스트 (B12–B19, B22)
4. Interfaces (스키마, 라우터, DI) + API 테스트 (B21)
5. `/api-contract-sync` → 프론트 타입·서비스·훅 → utils → Drawer → Card/Table + 테스트 (F1–F8)

### 11.2 File Change Summary

| 구분 | 파일 |
|------|------|
| 신규 (BE) | `src/domain/approval/edit_policy.py`, `db/migration/V078__add_edit_columns_to_approval_request.sql`, `tests/domain/approval/test_edit_policy.py` |
| 수정 (BE) | `domain/approval/{entity,policies,execution_policy}.py`, `domain/agent_builder/policies.py`(상수 참조), `application/approval/{decide_use_case,execute_scheduler,gate_middleware,errors}.py`, `infrastructure/approval/{models,repository}.py`, `interfaces/schemas/approval.py`, `api/routes/approval_router.py`, `api/main.py`, `config.py` |
| 신규 (FE) | `src/pages/JobsPage/ApprovalDetailDrawer.tsx`(+test), `src/utils/approvalEdit.ts`(+test) |
| 수정 (FE) | `src/types/approval.ts`, `src/services/approvalService.ts`, `src/hooks/useApprovals.ts`, `src/pages/JobsPage/{ApprovalCard,ApprovalTable}.tsx`, `src/__tests__/mocks/handlers.ts` |

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | 내용 | 테스트 | 예상 |
|--------|-----------|------|--------|------|
| 도메인 정책 | `module-1` | EditPolicy, OutcomePolicy, rewrap, DRAFT_KEYS 단일화 | B1–B11 | ~250 LOC |
| 영속 계층 | `module-2` | V078, 모델, 엔티티, 리포지토리 CAS/매핑 | B20, DDL | ~120 LOC |
| 유스케이스 | `module-3` | Decide approve/get, Scheduler, 미들웨어 D-02, 오류, config | B12–B19, B22 | ~300 LOC |
| API 계약 | `module-4` | 스키마, 라우터, DI | B21 | ~120 LOC |
| 프론트 | `module-5` | 타입·서비스·훅·utils·Drawer·Card·Table | F1–F8 | ~500 LOC |

#### Recommended Session Plan

| Session | Scope | 비고 |
|---------|-------|------|
| 1 | `--scope module-1,module-2` | 순수 규칙 + 스키마. DB 로컬 적용 확인 |
| 2 | `--scope module-3,module-4` | 백엔드 완결, 기존 approval 테스트 전량 회귀 |
| 3 | `--scope module-5` | 계약 동기화 후 UI |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-29 | Initial draft — Option C, D-01~D-03(본문 키 판정 변경, 래퍼 대응) | 배상규 |
