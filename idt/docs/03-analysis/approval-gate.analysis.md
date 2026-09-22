# approval-gate Analysis Report

> **Analysis Type**: Gap Analysis (Static + Runtime)
>
> **Project**: sangplusbot (idt / idt_front)
> **Analyst**: 배상규 (with bkit:gap-detector)
> **Date**: 2026-09-21
> **Design Doc**: [approval-gate.design.md](../02-design/features/approval-gate.design.md) (v0.2)
> **Plan Doc**: [approval-gate.plan.md](../01-plan/features/approval-gate.plan.md) (v0.2)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 에이전트의 비가역 부작용이 사람 검증 없이 실행된다. 동시에 새벽 집행 작업 때문에 사람을 그 시각에 묶어두는 것도 비효율이다. |
| **WHO** | P2 KB 운영자/에이전트 소유자(설정·승인) + 관리자(강제 정책) |
| **RISK** | 승인 중복 클릭에 의한 이중 집행. 예약 집행 시각까지 대기하는 동안 스냅샷·초안이 낡음. |
| **SUCCESS** | 게이트 도구는 승인 없이 0회 실행되고, 승인 후 지정 시각에 정확히 1회 집행되며, 런이 멈춘 지점부터 이어져 최종 답변까지 도달한다. |
| **SCOPE** | Phase 1: 게이트 골격 + 미들웨어 편입 + 승인 API + 예약 집행 + 재개 + 작업함 탭(집행기 mock) |

---

## Executive Summary

| 축 | 점수 |
|---|:-:|
| Structural Match | **95%** |
| Functional Depth | **79%** |
| API Contract | **83%** |
| Runtime | **80%** |
| **Overall** | **≈ 83%** — 목표 90% 미달 → Act(iterate) 필요 |

`Overall = 95×0.15 + 79×0.25 + 83×0.25 + 80×0.35 = 82.75`

**핵심 판정**: 안전 속성(게이트는 승인 없이 실도구를 호출하지 않는다)은 구조적으로 성립하고 테스트로 고정됐다. 그러나 **SUCCESS 3개 중 2개가 실제 운영에서 성립하지 않는다** — 재개 저장이 항상 실패하고(G1), 예약 집행을 호출하는 주체가 없으며(G5), 집행 시각이 KST 기준 9시간 어긋난다(G13). 또 게이트를 켜는 관리자 경로(G2)와 에이전트별 설정 입구(G3)가 없다.

Do 단계 보고에서 "금리 시나리오가 코드로 성립합니다"라고 했으나, 이는 **단위 테스트 기준으로는 맞고 실제 실행 경로 기준으로는 틀렸다.** 재개 테스트가 `_save_assistant_message`를 모킹해 G1을 가렸고, 예약 계산 테스트는 시각을 UTC로만 비교해 G13을 드러내지 못했다.

---

## Strategic Alignment Check

### Success Criteria Status

| # | Criteria (Plan §4.1) | Status | Evidence |
|---|---|:-:|---|
| SC-1 | 게이트 도구는 승인 없이 **0회** 실행 | ✅ | `gate_middleware.py:43-70` handler 미호출. `test_gate_middleware.py` `_boom` handler로 sync·async 양쪽 고정 |
| SC-2 | 승인 후 **지정 시각에 정확히 1회** 집행 | ❌ | "정확히 1회"는 3중 방어로 성립. 그러나 **지정 시각**이 틀리고(G13, KST +9h) **tick 주기 호출자가 없어**(G5) 외부 cron 없이는 영원히 집행되지 않음 |
| SC-3 | 런이 멈춘 지점부터 이어져 **최종 답변까지 도달** | ❌ | 재개 그래프는 돌지만 저장 단계에서 `SessionId("")` → `ValueError` → 삼켜짐. 최종 답변 유실(G1) |
| SC-4 | 즉시 집행 E2E | ⚠️ | 적재→승인→집행은 성립. 재개가 G1로 실패 |
| SC-5 | 거절 시나리오 | ⚠️ | 거절 전이 성립. 사유 주입 재개가 G1로 실패 |
| SC-6 | 우회 차단 회귀 테스트 | ✅ | SC-1과 동일 |
| SC-7 | 강제 정책 (`is_enforced` + `mode=off` → 발동) | ✅ | `policies.py:51`, `test_policies.py::test_enforced는_mode_off를_무시하고_발동` |
| SC-8 | 멱등 (동시 승인 10회 → 1회) | ✅ | UNIQUE + 조건부 UPDATE + SKIP LOCKED. SQL 컴파일 테스트로 고정 |
| SC-9 | V071~V073 + 전 컬럼 COMMENT | ✅ | `test_migration_ddl_comments.py` 통과, 로컬 DB 적용 확인 |
| SC-10 | 프론트 탭 + 설정 노출 | ⚠️ | 승인 탭 ✅. **설정 폼은 만들었으나 어디에도 마운트되지 않음**(FR-22) |

**Success Rate**: 5/10 ✅, 3/10 ⚠️, 2/10 ❌

### Decision Record Verification

| Source | Decision | Followed? | Note |
|---|---|:-:|---|
| Plan | 집행 모델 A + Protocol | ⚠️ | A는 성립. Protocol(`ApprovalGateInterface`)은 구현체 없음 — dead interface(G9) |
| Plan | 기존 미들웨어 카탈로그 편입 | ⚠️ | 편입·병합 로직 ✅. **에이전트별 config를 쓸 입구가 없음**(G3) |
| Plan | `execute_after` 예약 집행 | ❌ | 로직 ✅. 타임존 누락(G13) + tick 호출자 없음(G5) |
| Plan | `is_enforced` 관리자 강제 | ✅ | |
| Plan | 단독 워커 제약 | ⚠️ | 생성 경로만. Update 경로 미검증(G10) |
| Design | Option C 순수 미들웨어 + 래퍼 리프트 | ✅ | |
| Design | per-agent config 오버라이드 전체 구현 | ⚠️ | `MergePolicy` 병합은 구현. 데이터 입구 없음(G3) |
| Design | 게이트 fail-closed | ✅ | `middleware_builder.py:43-48` |

---

## 1. 축별 상세

### 1.1 Structural Match — 95%

Design §11.1 파일은 백엔드·프론트 모두 존재한다. `resume_use_case.py` 대신 `resume_interface.py` + `RunAgentUseCase.resume_from_snapshot()`은 승인된 이탈이다. 감점은 FR-17 Protocol의 구현체 부재(G9).

### 1.2 Functional Depth — 79%

26개 FR 중 ✅ 16 / ⚠️ 9 / ❌ 1 → `(16 + 9×0.5) / 26 = 78.8%`

| FR | 판정 | 근거 |
|---|:-:|---|
| FR-01 상태 기계 | ✅ | `entity.py:35-45` 전이표 |
| FR-02 requires_approval 이원화 | ⚠️ | 컬럼·upsert 보존 ✅. **관리자 토글 경로 없음**(G2), `requires_approval_default` 시드 미연결(G10) |
| FR-03 게이트 차단 | ✅ | |
| FR-04 스냅샷 | ✅ | 승인된 이탈(런 최종 상태) |
| FR-05 단독 워커 | ⚠️ | 생성만. Update 미적용(G10) |
| FR-06 런당 1건 | ⚠️ | 라우팅 종료 + 첫 마커 채택으로 사실상 성립. `find_active_by_run` 미호출 |
| FR-07 API | ✅ | |
| FR-08 can_decide | ✅ | |
| FR-09 Executor + Mock | ✅ | |
| FR-10 멱등 | ✅ | |
| FR-11 재개(결과 주입) | ⚠️ | 로직 ✅, 저장 실패(G1) |
| FR-12 거절 재개 | ⚠️ | G1과 동일 |
| FR-13 만료 | ⚠️ | 판정·전이 ✅. **`expires_hours`가 항상 168h**(G4) |
| FR-14 정의 변경 대조 | ⚠️ | 승인 시 ✅. 집행 시점 미대조(G8) |
| FR-15 탭 + unseen 합산 | ✅ | 탭·배지 ✅, `{count,jobs,approvals}` 라이브 L1-09 통과 |
| FR-16 감사 필드 | ✅ | |
| FR-17 ApprovalGateInterface | ⚠️ | Protocol만, 구현체 없음(G9) |
| FR-18 APPROVAL_GATE + 시드 | ✅ | |
| FR-19 config 검증 | ✅ | |
| FR-20 is_enforced 우선 | ✅ | |
| FR-21 합성 규칙 | ✅ | |
| FR-22 설정 화면 노출 | ❌ | **컴포넌트 미마운트 + 저장 API 없음**(G3) |
| FR-23 execute_after cron | ⚠️ | **타임존 누락(G13)** + 전역 default만 적용(G3) |
| FR-24 claim_due 선점 | ✅ | 선점 ✅. 호출자 부재는 G5로 별도 |
| FR-25 실패·재시도 없음 | ✅ | |
| FR-26 window 검증 | ✅ | |

### 1.3 API Contract — 83%

| # | 엔드포인트 | Design↔서버 | 서버↔클라이언트 | 판정 |
|---|---|:-:|:-:|---|
| 1 | GET /approvals | ⚠️ | ✅ | `agent_name` 항상 null(G6), `agent_id` 필터 없음 |
| 2 | GET /approvals/{id} | ✅ | ✅ | `agent_name` null |
| 3 | POST /{id}/approve | ✅ | ✅ | |
| 4 | POST /{id}/reject | ✅ | ✅ | |
| 5 | POST /{id}/seen | ⚠️ | ✅ | **권한 검사 없음**(G7) |
| 6 | POST /internal/approvals/tick | ✅ | n/a | |

datetime이 `Z` 없이 직렬화되어 프론트 `new Date()`가 로컬 시각으로 해석한다(G12). G13과 겹쳐 **화면 표시 시각도 어긋난다.**

### 1.4 Runtime — 80%

| 층위 | 결과 |
|---|---|
| 백엔드 approval 관련 테스트 | 340 passed |
| 프론트 approval 관련 테스트 | 60 passed |
| **L1 라이브 API** (localhost:8000, 실 DB) | **9/9 PASS** |
| 백엔드 전체 회귀 | 53 failed = 베이스라인 동일, 신규 0 |
| 프론트 전체 회귀 | 신규 실패 0 (베이스라인 부분집합) |

테스트는 전부 통과하지만, **재개 저장(G1)과 예약 시각(G13)은 테스트가 실제 경로를 타지 않아 가려진 결함**이다. 통과율이 아니라 "핵심 경로를 실제로 검증했는가"로 감점했다.

---

## 2. Page UI Checklist (Design §5.4)

### 작업함 — 승인 대기 탭 (13)

| 항목 | 판정 | 근거 |
|---|:-:|---|
| Tab + 건수 배지 | ✅ | `JobsPage/index.tsx` |
| 상태 배지 | ✅ | `APPROVAL_STATUS_TONES` |
| 미확인 점 | ✅ | `aria-label="미확인"` |
| 에이전트명 + 도구 ID | ⚠️ | 도구 ✅. 서버가 `agent_name` null → `agent_id`로 폴백(G6) |
| 초안 미리보기 3줄 클램프·펼침 | ✅ | `line-clamp-3` |
| 집행 예정 시각 | ⚠️ | 표시 ✅. **시각이 틀림**(G12+G13) |
| 만료 + 잔여 시간 | ⚠️ | 표시 ✅. 9시간 어긋남(G12) |
| [승인] 처리 중 disabled | ✅ | |
| [거절] 다이얼로그 | ✅ | |
| 사유 필수·미입력 disabled | ✅ | |
| 빈 상태 문구 | ✅ | |
| 409 토스트 + 목록 갱신 | ✅ | `onSettled` 무효화 |
| 상태 필터 4종 | ✅ | |

**10/13 ✅, 3/13 ⚠️**

### 에이전트 설정 — 미들웨어 섹션 (4)

| 항목 | 판정 |
|---|:-:|
| 토글 (enforced 읽기 전용 + 뱃지) | ❌ 미마운트 |
| cron 입력 | ❌ 미마운트 |
| 만료 시간 입력 | ❌ 미마운트 |
| 안내 문구 | ❌ 미마운트 |

**0/4** — 컴포넌트와 테스트(11건)는 있으나 사용자에게 보이지 않는다.

---

## 3. Gap 목록

> 확신도 80% 이상, 전부 코드로 직접 재확인함 (G13은 Check 단계에서 추가 발견).

| ID | 심각도 | Gap | 근거 | 권장 조치 |
|---|---|---|---|---|
| **G1** | **Critical** | 재개 저장이 항상 실패해 최종 답변 유실 | `run_agent_use_case.py:805` session_id=`""` → `SessionId.__post_init__` ValueError → `decide_use_case`/`execute_scheduler`가 삼킴. 테스트가 `_save_assistant_message`를 모킹해 은폐 | 원래 런의 `session_id`를 승인 요청에 영속(스냅샷 또는 컬럼)해 재개 저장에 사용. 모킹 없는 재개 저장 테스트 추가 |
| **G13** | **Critical** | 예약 집행 시각이 KST 기준 **9시간 어긋남** (`0 0 * * *` → 오전 9시) | `decide_use_case.py:230-240` croniter를 UTC naive로 계산. `agent_schedule/policies.py:21-27`은 `tz` + `_to_local`로 해결되어 있음 | config에 `timezone`(기본 `Asia/Seoul`) 추가, `agent_schedule`의 `to_local` 재사용. KST 경계 테스트 추가 |
| **G2** | **Critical** | 관리자가 `requires_approval`을 켤 API·UI가 없어 **운영에서 게이트를 켤 수 없음** | `update_metadata_use_case.py:73-76`이 category·max_tool_calls만 전달 | UseCase·라우터 스키마·관리자 도구 화면에 `requires_approval` 추가 |
| **G3** | **Critical** | 에이전트별 게이트 config 입구가 없어 FR-19/22/23의 에이전트별 제어가 무효 | `agent_definition_repository.py:170-175`가 항상 `config=None`. 설정 폼 미마운트 | 에이전트 미들웨어 config 저장 API(`MiddlewareConfigPolicy` 검증) + 설정 페이지에 폼 마운트 |
| G5 | Important | 예약 tick 주기 호출자 없음 → 외부 cron 없이는 영원히 미집행 | `background_job/worker.py` 내장 tick은 스케줄만 | 워커 내장 tick에 approval tick 합류 + `APPROVAL_EXECUTOR_TICK_SECONDS` |
| G4 | Important | `expires_hours`가 항상 168h | `main.py` `_build_run_agent_uc`가 `approval_gate_config` 미전달, 생성자 상수라 에이전트별 불가 | 적재 시 해당 에이전트 게이트 config를 해석해 사용 |
| G7 | Important | `/seen` 권한 검사 없음 — 타인 건 확인 처리 가능 | `repository.py` mark_seen이 user_id 미사용 | 소유 agent_ids 범위로 제한 |
| G6 | Important | `agent_name` 항상 null | `approval_router.py:83,101` | ListUseCase의 소유 에이전트 목록에서 이름 매핑 |
| G8 | Important | 집행 시점 정의 변경 재검증 없음 | `execute_scheduler.py:81-121` | 집행 전 `updated_at` 대조, 정책 명시 |
| G12 | Important | datetime `Z` 누락 → 프론트 시각 해석 오류 | `schemas/approval.py` | 응답에 UTC tz 부착 (G13과 함께) |
| G9 | Minor | `ApprovalGateInterface` 구현체 없음 | `gate_interface.py` | StatelessGate 어댑터 또는 Design을 "예약 자리"로 갱신 |
| G10 | Minor | 단독워커 제약 Update 미적용, `requires_approval_default` 시드 미연결 | `update_agent_use_case.py`, `schemas.py:37` | Update에도 검증, sync INSERT에 default 반영 |
| G11 | Minor | 승인 즉시 집행·재개가 HTTP 요청 안에서 동기 실행 | `decide_use_case.py` | background_job 위임 검토 |

**승인된 이탈 (Gap 아님, 6건 모두 코드 확인)**: 워커별 `build_approval_gate()` / 스냅샷=런 최종 상태 / `resume_from_snapshot` + Protocol / 집행 후 정산 / repo가 agent_ids 수신 / ORM FK 제거

---

## 4. 교훈 — 왜 테스트가 통과했는데 핵심이 깨졌나

1. **모킹이 결함 지점을 정확히 덮었다 (G1)**: `test_재개_답변이_대화에_저장된다`가 `_save_assistant_message`를 `AsyncMock`으로 바꿔 "호출됐다"만 확인했다. 실패는 바로 그 함수 안의 `SessionId("")`에서 났다.
2. **시각 테스트가 한 기준계 안에서만 비교했다 (G13)**: `test_cron이_있으면_scheduled로_예약된다`는 UTC 입력 → UTC 기대값이라 통과했다. 사용자가 원한 건 "KST 00시"였고, 이 요구가 테스트 어디에도 문장으로 없었다. `agent_schedule`이 이미 타임존을 다뤘는데 재사용 대상으로 보지 못했다.
3. **"만들었다"와 "쓸 수 있다"를 구분하지 않았다 (G2·G3·FR-22)**: 컬럼·파라미터·컴포넌트를 추가하고 테스트했지만, 그걸 **켜는 입구**(관리자 API, 설정 저장 API, 페이지 마운트)를 Do 범위에 넣지 않았다.

---

## 5. Next Steps

- `/pdca iterate approval-gate` — 우선순위 **G1 → G13 → G2 → G3(+FR-22) → G5 → G4 → G7**
- 각 수정마다 **모킹 없이 실제 경로를 타는 회귀 테스트**를 함께 추가 (교훈 1·2)
- 재측정 후 90% 이상이면 `/pdca report`

---

## 6. Act-1 결과 (2026-09-21)

Checkpoint 5 에서 "지금 모두 수정" 선택 → G1~G10·G12·G13 수정. G11 은 선택지 범위 밖(아키텍처 변경)이라 제외.

### 6.1 재측정

| 축 | Check | **Act-1** | 근거 |
|---|:-:|:-:|---|
| Structural | 95% | **98%** | FR-17 구현체(StatelessGate) 추가 |
| Functional | 79% | **98%** | ✅ 25 / ⚠️ 1(FR-06) / ❌ 0 → (25+0.5)/26 |
| Contract | 83% | **95%** | agent_name·/seen 권한·UTC 직렬화 수정, 게이트 설정 API 프론트 연결. `agent_id` 목록 필터는 미구현(잔여) |
| Runtime | 80% | **85%** | 인프로세스 전량 통과 + 실제 경로 테스트 추가(G1 비모킹 저장, G13 KST 벽시계). **라이브 L1 재검증은 V074 적용 대기**로 감점 |
| **Overall** | ≈83% | **≈ 93%** | `98×0.15 + 98×0.25 + 95×0.25 + 85×0.35 = 92.7` |

### 6.2 Gap 처리

| ID | 결과 | 수정 요지 |
|---|:-:|---|
| G1 | ✅ | V074 `session_id` 컬럼. 재개 답변을 원래 세션에 저장, 세션·요청자 없으면 저장만 건너뛰고 답변 반환. **모킹 없이 실제 `_save_assistant_message` 를 타는 테스트**로 교체 |
| G13 | ✅ | `ApprovalPolicy.next_execute_after(cron, now_utc, tz)` — agent_schedule 과 같은 `to_local → croniter → UTC` 절차. config `timezone`(기본 Asia/Seoul) + ZoneInfo 검증. **결함을 정답으로 인코딩하던 기존 테스트 기대값 교정** |
| G2 | ✅ | `PATCH /tool-catalog/metadata` 에 `requires_approval` (부분 갱신·null 거부) + 관리자 도구 화면 스위치 |
| G3 | ✅ | `GET/PUT /agents/{id}/approval-gate` + `upsert_config`. 에이전트 편집 화면에 `ApprovalGateSettingsPanel` **마운트** |
| G5 | ✅ | 백그라운드 워커 루프에 승인 tick 합류(single-flight), `APPROVAL_EXECUTOR_TICK_SECONDS` |
| G4 | ✅ | 적재 시 해당 에이전트 게이트 config 해석. 승인 쪽과 **같은 해석 함수 공유**, 같은 세션·트랜잭션 |
| G7 | ✅ | `mark_seen` 을 소유 agent_ids 범위로 제한 |
| G6 | ✅ | 목록·상세에 에이전트명(이미 조회한 소유 에이전트에서 매핑, 추가 쿼리 없음) |
| G8 | ✅ | FR-14 원문과 대조 결과 **현재 동작이 요구사항과 일치**(집행은 진행·재개만 거부). 동작 변경 없이 테스트 고정 + Design §6.2b 명시 |
| G12 | ✅ | 응답 datetime 에 UTC 명시. 시각 문구는 로캘을 아는 프론트가 생성 |
| G9 | ✅ | `StatelessGate` 구현, 컴파일러가 Protocol 경유 — 교체 시 컴파일러가 따라감을 테스트로 입증 |
| G10 | ✅ | 수정 경로에도 단독워커 검증(공용 함수 추출), `requires_approval_default` 시드 연결 |
| G11 | ⏸ 제외 | 승인 즉시 집행·재개의 동기 실행 → background_job 위임은 아키텍처 변경 |

### 6.3 수정 중 추가로 발견·처리한 결함 4건

| 결함 | 원인 | 처리 |
|---|---|---|
| **에이전트 수정 시 미들웨어 config 전부 소실** | `_sync_middleware` 가 delete 후 `config=None` 재삽입 | 유지 타입 config 보존 계약 |
| **게이트 설정 행을 두 경로가 두고 다툼** | 전용 PUT 이 만든 행을, 에이전트 폼 저장이 "목록에 없다"며 삭제 | `SEPARATELY_MANAGED_MIDDLEWARE_TYPES` — 전용 API 가 소유, 폼 동기화 제외 |
| **인터페이스 추상 메서드 추가로 앱 기동 실패** | `SessionScopedAgentMiddlewareRepository` 미구현 | 읽기 전용 규약대로 `NotImplementedError` + 전 구현체 인스턴스화 회귀 테스트 |
| **UI 에서 cron 에 공백 입력 불가** | 폼이 키 입력마다 `trim()` → `'30 23 * * *'` 가 `'3023***'` | 입력 중 trim 제거, 저장 시점 정리. 기존 테스트는 한 글자만 입력해 못 잡음 |

### 6.4 회귀

| | 결과 |
|---|---|
| 백엔드 전체 | 53 failed(선행, 목록 동일) / **9,586 passed** (Do 종료 9,478 → +108) |
| 프론트 전체 | 9 failed(선행 부분집합) / **1,248 passed**, 신규 실패 0 |
| 프론트 타입체크 | 변경 파일 0건 (보인 3건은 HEAD 에서도 존재 확인) |
| lint | 변경 파일 0건 |

### 6.5 잔여 · 운영 조치 필요

1. **로컬 DB 에 V074 미적용** — 적용 전까지 로컬 서버 `GET /approvals` 가 500. 사용자가 직접 적용 예정. 적용 후 라이브 L1 재검증 필요. **배포 시 V071~V074 선행 필수**(`ops/migration-deploy-deps` 등재 대상).
2. **`.env.example`** — bkit 스코프 정책으로 편집 차단됨. `APPROVAL_EXECUTOR_TICK_SECONDS=60` 항목을 수동 추가 필요(미설정 시 기본 60초로 동작).
3. **G11** 동기 실행, **FR-06** `find_active_by_run` 미사용(라우팅 종료로 사실상 성립), **목록 `agent_id` 필터** 미구현.

---

## Version History

| Version | Date | Changes | Author |
|---|---|---|---|
| 0.1 | 2026-09-21 | 초안 — gap-detector 정적 분석 + 직접 Runtime 측정(L1 9/9) + G13 추가 발견. Overall ≈ 83% | 배상규 |
| 0.2 | 2026-09-21 | Act-1 — G1~G10·G12·G13 수정, 수정 중 결함 4건 추가 처리. Overall ≈ 93%. 라이브 L1 재검증은 V074 적용 대기 | 배상규 |
