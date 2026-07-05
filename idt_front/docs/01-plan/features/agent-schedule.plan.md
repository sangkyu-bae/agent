# Plan: Agent Schedule (에이전트 자동 실행 스케줄 탭)

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | agent-schedule |
| 작성일 | 2026-07-03 |
| 예상 소요 | 8~10시간 (타입/서비스/훅 2h + cron 유틸 1.5h + 폼 UI 3h + 목록/이력 UI 2h + 페이지 통합 1.5h) |
| API 기준 문서 | `docs/api/agent-schedule.md` (백엔드 구현 완료) |

### Value Delivered

| 관점 | 설명 |
|------|------|
| **Problem** | 백엔드에 에이전트 스케줄 API(생성/조회/수정/삭제/토글/실행이력)가 완성되어 있으나, 프론트 `/agent-builder` 우측 패널의 '스케줄' 탭은 비활성 placeholder(`AgentTestPanel.tsx:40`)라 사용자가 자동 실행 스케줄을 등록할 방법이 없음 |
| **Solution** | 스케줄 탭을 활성화하고 `docs/img/schedule.png` UI(반복/1회 유형, 폼/표현식 입력, cron 미리보기, 실행 메시지)를 구현. 생성 모드는 로컬 staged 후 에이전트 생성 성공 시 일괄 등록, 수정 모드는 즉시 API CRUD |
| **Function UX Effect** | 에이전트 편집 화면에서 "매일 09:00에 {today} 뉴스 요약" 같은 자동 실행을 폼 몇 번 클릭으로 등록하고, 활성 토글·실행 이력(success/failed)까지 한 화면에서 관리 |
| **Core Value** | 에이전트가 대화형 도구를 넘어 정기 자동 실행 워크플로우(일일 리포트, 모니터링)로 확장 — 플랫폼의 실사용 가치 상승 |

---

## 1. 현재 상황 분석

### 1.1 프론트엔드 현황

- `src/components/agent-builder/AgentTestPanel.tsx:40` — `{ id: 'schedule', label: '스케줄', enabled: false }` 비활성 placeholder. 활성 탭은 `test`/`skill` 두 개뿐이며, 콘텐츠 분기도 `skill ? AgentSkillPanel : TestChatView` 이분 구조.
- 스케줄 관련 타입/서비스/훅/컴포넌트 전무 (`grep 'schedule'` → 탭 id 선언 2곳뿐).
- 스킬 탭이 유사 선례: 생성·수정 모두 `form.skills`에 staged 후 저장 시 `skill_ids`로 일괄 전송. **단, 스케줄은 에이전트 생성/수정 요청 본문에 포함되지 않는 독립 리소스**(`/agents/{agent_id}/schedules`)이므로 생성 모드에서는 에이전트 생성 성공 후 별도 POST가 필요.

### 1.2 백엔드 API 현황 (구현 완료 — `docs/api/agent-schedule.md`)

| Method | Path | 용도 |
|--------|------|------|
| POST | `/api/v1/agents/{agent_id}/schedules` | 생성 (201) |
| GET | `/api/v1/agents/{agent_id}/schedules` | 목록 (배열 응답) |
| GET | `/api/v1/agents/{agent_id}/schedules/{schedule_id}` | 단건 |
| PUT | `/api/v1/agents/{agent_id}/schedules/{schedule_id}` | 수정 (생성과 동일 스키마) |
| DELETE | `/api/v1/agents/{agent_id}/schedules/{schedule_id}` | 삭제 (204, 실행 이력 CASCADE) |
| PATCH | `/api/v1/agents/{agent_id}/schedules/{schedule_id}/enabled` | 활성 토글 |
| GET | `/api/v1/agents/{agent_id}/schedules/{schedule_id}/runs` | 실행 이력 (limit≤100, offset) |

핵심 제약 (백엔드 검증, 프론트는 UX 차원에서 선반영):

- 에이전트당 스케줄 최대 **10개** / 지침(instruction) **1~1,900자** / name **1~200자** / cron 최소 간격 **10분**
- `spec.schedule_type`: `once | daily | weekly | cron` — 유형별 필수 필드 외 값 오면 400
- 지침 플레이스홀더 `{today}` `{now}` `{weekday}` — 실행 시점 치환
- 응답 datetime은 **UTC ISO8601**, `timezone`(IANA, 기본 `Asia/Seoul`)은 스케줄 계산 전용
- 인증: JWT Bearer → `authClient` 사용. 403(소유자 아님)/404(미존재) 처리
- 트리거 계열(`/internal/schedules/*`)은 외부 스케줄러 전용 — **프론트 범위 아님**

### 1.3 사용자 결정 사항 (Q&A 확정)

| 항목 | 결정 |
|------|------|
| '반복' 유형 매핑 | **항상 `cron`으로 전송** — 폼(분/시/일/월/요일)에서 조합하거나 표현식 직접 입력 모두 `cron_expr`. '1회'는 `once`(run_date + time_of_day). `daily`/`weekly` 타입은 이번 UI에서 미사용 |
| 수정 모드 반영 시점 | **즉시 API 호출** — 추가=POST, 수정=PUT, 토글=PATCH 즉시 실행. 삭제는 ConfirmDialog 확인 후 DELETE |
| 생성 모드 | **staged** — 로컬 배열에 추가/삭제만 (서버 호출 없음). 에이전트 생성 성공 시 순차 POST로 일괄 등록 |
| 구현 범위 | 생성 + 목록 + 삭제 + **enabled 토글** + **스케줄 수정(PUT)** + **실행 이력(runs)** 전부 포함 |
| 스케줄 name | 폼에 입력란 없이 **스펙 요약으로 자동 생성** (예: `매일 09:00 실행`, `1회 2026-07-10 09:00`, `크론 */30 * * * *`) |

---

## 2. 구현 범위

### 2.1 In-Scope

| # | 항목 | 설명 |
|---|------|------|
| 1 | 타입 정의 | `src/types/agentSchedule.ts` — `ScheduleType`(as const), `ScheduleSpecPayload`, `ScheduleCreateRequest`, `ScheduleResponse`, `ScheduleRunResponse`, staged용 `StagedSchedule`(로컬 id 포함) |
| 2 | 엔드포인트 상수 | `src/constants/api.ts` — `AGENT_SCHEDULES(agentId)`, `AGENT_SCHEDULE_DETAIL(agentId, scheduleId)`, `AGENT_SCHEDULE_ENABLED(...)`, `AGENT_SCHEDULE_RUNS(...)` |
| 3 | 서비스 레이어 | `src/services/agentScheduleService.ts` — authClient 기반 7개 메서드 (list/get/create/update/remove/setEnabled/listRuns) |
| 4 | 쿼리 키 + 훅 | `lib/queryKeys.ts`에 `agentSchedules` 팩토리 추가. `src/hooks/useAgentSchedules.ts` — `useAgentSchedules(agentId)`, `useCreateSchedule`, `useUpdateSchedule`, `useDeleteSchedule`, `useToggleScheduleEnabled`, `useScheduleRuns` (mutation 성공 시 목록 invalidate) |
| 5 | cron 유틸 | `src/utils/scheduleCron.ts` — 폼 값(분/시/일/월/요일) → `cron_expr` 조합, `cron_expr` → 폼 값 역파싱(불가하면 표현식 모드 폴백), 표현식 기본 형식 검증(5필드), **최소 간격 10분 사전 검증**(분 필드 휴리스틱), name 자동 생성, 사람이 읽는 요약 라벨 |
| 6 | 스케줄 폼 | `src/components/agent-builder/schedule/ScheduleForm.tsx` — 이미지 사양: 유형 토글(반복/1회), 입력 방식 토글(폼/스케줄 표현식), 분·시·일·월·요일 드롭다운, `미리보기: {cron_expr}`, 1회 모드는 날짜+시각 입력, 타임존 `Asia/Seoul` 고정 표시, 실행 메시지 textarea(1,900자 카운터 + 플레이스홀더 변수 안내), 취소/생성(수정 시 저장) 버튼 |
| 7 | 스케줄 패널 | `src/components/agent-builder/schedule/SchedulePanel.tsx` — 상단 설명 + "스케줄 추가" 버튼, 폼 열림/닫힘, 목록 카드(요약 라벨·next_run_at·enabled 토글·수정/삭제 버튼·최근 실행 상태), 빈 상태("등록된 스케줄이 없습니다"), 10개 도달 시 추가 버튼 비활성 |
| 8 | 실행 이력 | 카드 확장(또는 모달)으로 `runs` 조회 — status 배지(running/success/failed), scheduled_for/finished_at, 실패 시 error_message 표시 |
| 9 | 모드 분기 | **edit**: 훅 기반 즉시 CRUD (삭제는 ConfirmDialog). **create**: `AgentBuilderFormData.schedules: StagedSchedule[]`에 로컬 추가/삭제, 목록은 staged 배열 렌더 (토글/이력 없음 — 서버 리소스 부재) |
| 10 | 생성 후 일괄 등록 | `AgentBuilderPage.handleSave` create 성공 콜백에서 staged 스케줄을 순차 POST. 부분 실패 시 결과 다이얼로그에 "스케줄 n건 중 m건 등록 실패" 명시 (에이전트 생성 자체는 성공 처리) |
| 11 | 탭 활성화 | `AgentTestPanel.tsx` — schedule 탭 `enabled: true`, 콘텐츠 분기를 skill/schedule/test 3분기로 확장, SchedulePanel에 mode/agentId/staged props 전달 |
| 12 | 테스트 (TDD) | cron 유틸 단위 테스트, 훅 테스트(MSW 핸들러 추가), ScheduleForm·SchedulePanel 컴포넌트 테스트, 생성 모드 staged→일괄 등록 통합 테스트 |

### 2.2 이미지(schedule.png) ↔ API 매핑

| UI 요소 | 값/동작 | API 필드 |
|---------|---------|----------|
| 유형 토글 `반복` | 폼 or 표현식으로 cron 구성 | `spec.schedule_type: "cron"`, `spec.cron_expr` |
| 유형 토글 `1회` | 날짜 + 시각 입력 (미래만) | `spec.schedule_type: "once"`, `spec.run_date`, `spec.time_of_day` |
| 입력 방식 `폼` | 분/시/일/월/요일 드롭다운 (분 기본 `0`, 나머지 기본 `매일`/`매월`=`*`) | 조합 → `cron_expr` |
| 입력 방식 `스케줄 표현식` | 5필드 cron 직접 입력 | `cron_expr` 그대로 |
| 미리보기 | `분 시 일 월 요일` 실시간 표시 (예: `0 9 * * *`) | — |
| 타임존 | `Asia/Seoul` 고정(읽기 전용) | `timezone` |
| 실행 메시지 | 에이전트에게 보낼 질문 (1~1,900자) | `instruction` |
| 생성 버튼 | edit=즉시 POST / create=staged push | — |
| 빈 상태 | "등록된 스케줄이 없습니다 / 첫 번째 스케줄을 추가해보세요" | — |

### 2.3 Out-of-Scope

- 백엔드 변경 없음 (API 구현 완료 상태 사용)
- `daily`/`weekly` 유형 전용 UI (반복=cron으로 통일 — 기존 daily/weekly 스케줄 조회 시 요약 라벨만 표시하고 편집 시 스펙 유지 불가하면 안내)
- `/internal/schedules/trigger*` (외부 스케줄러 전용)
- 타임존 선택 UI (Asia/Seoul 고정, 필드는 요청에 명시 전송)
- 스케줄 단건 조회(GET detail) 화면 — 목록 응답으로 충분
- 실행 이력 페이지네이션 고도화 (최근 20건 고정 조회)

---

## 3. 구현 순서 (TDD)

### Step 1: 타입 + 상수 + 서비스 + MSW

`types/agentSchedule.ts`, `constants/api.ts`, `services/agentScheduleService.ts`, `__tests__/mocks/handlers.ts`(스케줄 CRUD 핸들러).

### Step 2: cron 유틸 (Red → Green)

`utils/scheduleCron.ts` + 테스트:
- `buildCronExpr({minute, hour, dayOfMonth, month, dayOfWeek})` → `"0 9 * * *"`
- `parseCronExpr("0 9 * * *")` → 폼 값 / 복합 표현식(`*/5`, `1,3`)은 `null` 반환(표현식 모드 폴백)
- `validateCronExpr` — 5필드/허용 문자/10분 간격 휴리스틱(`* * ...` 분 필드 거부 등)
- `generateScheduleName(spec)` — `매일 09:00 실행` / `1회 2026-07-10 09:00` / `크론 */30 * * * *`
- `describeSpec(spec)` — 카드용 요약 라벨 (daily/weekly 응답도 커버)

### Step 3: TanStack Query 훅 (Red → Green)

`lib/queryKeys.ts` + `hooks/useAgentSchedules.ts` + 훅 테스트 (`renderHook` + MSW). mutation onSuccess에서 `queryKeys.agentSchedules.list(agentId)` invalidate.

### Step 4: ScheduleForm (Red → Green)

신규/수정 겸용 (initial 값 주입 시 수정 모드). 테스트: 유형/입력방식 토글, 미리보기 갱신, 1회 과거 날짜 검증, 실행 메시지 필수/1900자, 제출 시 payload 형태 확인.

### Step 5: SchedulePanel + 실행 이력 (Red → Green)

edit 모드: 목록 조회/토글/삭제(ConfirmDialog)/수정 진입/이력 확장. create 모드: staged 배열 렌더 + 로컬 추가/삭제. 테스트: 빈 상태, 카드 렌더, 토글 PATCH 호출, 삭제 확인 흐름, 10개 제한.

### Step 6: 페이지 통합

`AgentTestPanel.tsx` 탭 활성화 + 3분기. `AgentBuilderFormData.schedules` 추가(DEFAULT_FORM 포함). `AgentBuilderPage.handleSave` create onSuccess에서 순차 POST + 결과 메시지 합성. 통합 테스트: staged 2건 → 생성 성공 → POST 2회 호출 검증.

### Step 7: 전체 검증

`npm run test:run -- --pool=threads` + `npm run type-check` + `npm run lint`. 사전 실패 8건(기존 이슈)은 회귀로 오인하지 않음.

---

## 4. 영향 파일 목록

### 신규

| 파일 | 내용 |
|------|------|
| `src/types/agentSchedule.ts` | 스케줄 도메인/요청/응답 타입 |
| `src/services/agentScheduleService.ts` | CRUD + 토글 + runs API |
| `src/hooks/useAgentSchedules.ts` (+test) | TanStack Query 훅 6종 |
| `src/utils/scheduleCron.ts` (+test) | cron 조합/파싱/검증/이름 생성 |
| `src/components/agent-builder/schedule/ScheduleForm.tsx` (+test) | 스케줄 입력 폼 |
| `src/components/agent-builder/schedule/SchedulePanel.tsx` (+test) | 탭 콘텐츠 (목록/빈 상태/이력) |

### 수정

| 파일 | 변경 |
|------|------|
| `src/constants/api.ts` | 스케줄 엔드포인트 4종 추가 |
| `src/lib/queryKeys.ts` | `agentSchedules` 키 팩토리 |
| `src/components/agent-builder/AgentTestPanel.tsx` | 스케줄 탭 활성화 + 콘텐츠 3분기 + props 전달 |
| `src/types/agentBuilder.ts` | `AgentBuilderFormData.schedules: StagedSchedule[]` |
| `src/pages/AgentBuilderPage/index.tsx` | DEFAULT_FORM, 스케줄 staged 핸들러, 생성 성공 후 일괄 POST, 결과 메시지 |
| `src/__tests__/mocks/handlers.ts` | 스케줄 API MSW 핸들러 |

---

## 5. 리스크

| 리스크 | 대응 |
|--------|------|
| 생성 성공 후 스케줄 일괄 POST 부분 실패 (에이전트는 생성됨) | 실패 건수를 결과 다이얼로그에 명시, 사용자는 수정 모드 진입 후 재등록 가능. 순차 실행으로 실패 지점 명확화 |
| cron 10분 간격 검증의 서버/클라 불일치 | 클라 검증은 휴리스틱(UX용)에 그치고, 400 응답 메시지를 폼 에러로 그대로 표출 |
| 표현식 → 폼 역파싱 불가 케이스 (`*/5`, 리스트 등) | parse 실패 시 표현식 모드로 열어 원문 유지 (데이터 손실 없음) |
| 기존에 백엔드로 직접 생성된 daily/weekly 스케줄 표시 | `describeSpec`이 4개 유형 모두 요약 렌더. 편집은 cron/once만 지원, daily/weekly 카드는 수정 버튼 비활성 + 안내 툴팁 |
| UTC ↔ Asia/Seoul 표시 혼동 (`next_run_at` 등) | 표시 시 로컬 변환 유틸(`formatters.ts` 재사용) 일원화, 테스트로 고정 |
| create 모드에서 staged 스케줄의 검증 시점 부재 | 폼 제출 시점에 클라 검증(형식/과거 날짜/글자수) 수행 — 등록 실패율 최소화 |

---

## 6. 완료 기준 (Acceptance Criteria)

1. `/agent-builder` 생성·수정 화면에서 스케줄 탭이 활성화되고 `schedule.png`와 동일한 폼(유형 토글, 폼/표현식, 미리보기, 타임존, 실행 메시지)이 렌더된다.
2. **수정 모드**: 스케줄 추가/수정/삭제/활성 토글이 즉시 API에 반영되고(POST/PUT/DELETE/PATCH), 삭제는 ConfirmDialog를 거친다. 목록에 `next_run_at`(Asia/Seoul 표시)과 enabled 상태가 나타난다.
3. **생성 모드**: 스케줄 추가/삭제가 서버 호출 없이 로컬에서만 동작하고, 에이전트 생성 성공 시 staged 스케줄이 모두 POST 등록된다. 부분 실패 시 결과 메시지에 실패 건수가 표시된다.
4. 폼 모드에서 분/시/일/월/요일 조합이 미리보기에 실시간 반영되고(`0 9 * * *`), 표현식 모드 입력도 동일 payload(`spec.schedule_type: "cron"`)로 전송된다. 1회 모드는 `once`(run_date+time_of_day)로 전송된다.
5. 스케줄 name은 자동 생성 규칙대로 전송되고, 실행 메시지는 1,900자 초과 시 제출이 차단된다. 에이전트당 10개 도달 시 추가 버튼이 비활성화된다.
6. 실행 이력 확장 시 최근 실행의 status/시각/에러 메시지가 표시된다.
7. 신규 테스트 전부 통과 + 기존 스위트 그린 (`--pool=threads`, 사전 실패 8건 제외) + type-check/lint 통과.
