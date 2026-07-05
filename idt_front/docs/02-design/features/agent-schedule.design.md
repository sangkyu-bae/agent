# Design: Agent Schedule (에이전트 자동 실행 스케줄 탭)

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | agent-schedule |
| Plan 참조 | `docs/01-plan/features/agent-schedule.plan.md` |
| API 참조 | `docs/api/agent-schedule.md` |
| 작성일 | 2026-07-03 |

### Value Delivered

| 관점 | 설명 |
|------|------|
| **Problem** | 백엔드 스케줄 API 완성에도 `/agent-builder` 스케줄 탭이 비활성 placeholder라 자동 실행 등록 불가 |
| **Solution** | 스케줄 탭 활성화 + `schedule.png` UI. 생성 모드 staged→일괄 등록, 수정 모드 즉시 CRUD |
| **Function UX Effect** | 폼 클릭 몇 번으로 "매일 09:00 자동 실행" 등록, 토글·실행 이력까지 한 탭에서 관리 |
| **Core Value** | 에이전트를 정기 자동 실행 워크플로우로 확장 |

---

## 1. 아키텍처 개요

### 1.1 현재 (문제 상태)

```
AgentTestPanel (우측 패널)
├─ 탭바: Fix(비활성) 테스트 오프너(비활성) 파일(비활성) 스킬 [스케줄(비활성)] 설정(비활성)
└─ 콘텐츠: tab === 'skill' ? AgentSkillPanel : TestChatView   ← 2분기뿐
```

### 1.2 변경 후 (목표)

```
AgentTestPanel
├─ 탭바: … [스케줄(활성)] …
└─ 콘텐츠 3분기:
   ├─ 'skill'    → AgentSkillPanel
   ├─ 'schedule' → SchedulePanel ────────────────┐
   └─ 그 외      → TestChatView                  │
                                                 │
SchedulePanel (mode 분기)                        │
├─ [edit]   useAgentSchedules(agentId) ──▶ 서버 목록
│           추가=POST · 수정=PUT · 토글=PATCH 즉시 / 삭제=ConfirmDialog→DELETE
│           카드 확장 ──▶ useScheduleRuns (실행 이력)
└─ [create] form.schedules (StagedSchedule[]) 로컬 배열
            추가/삭제 로컬만 → 에이전트 생성 성공 후 AgentBuilderPage가 순차 POST
```

### 1.3 신규 모듈 의존 구조

```
types/agentSchedule.ts ◀── services/agentScheduleService.ts ◀── hooks/useAgentSchedules.ts
        ▲                        (constants/api.ts)                (lib/queryKeys.ts)
        │                                                                ▲
utils/scheduleCron.ts ◀── components/agent-builder/schedule/ScheduleForm.tsx
                      ◀── components/agent-builder/schedule/SchedulePanel.tsx ──▶ ConfirmDialog(재사용)
                                                  ▲
                          AgentTestPanel ──▶ StudioLayout ──▶ AgentBuilderPage (staged 핸들러 + 일괄 POST)
```

---

## 2. 데이터 계층 설계

### 2.1 타입 — `src/types/agentSchedule.ts` (신규)

```ts
export const SCHEDULE_TYPE = {
  ONCE: 'once', DAILY: 'daily', WEEKLY: 'weekly', CRON: 'cron',
} as const;
export type ScheduleType = (typeof SCHEDULE_TYPE)[keyof typeof SCHEDULE_TYPE];

export const SCHEDULE_RUN_STATUS = {
  RUNNING: 'running', SUCCESS: 'success', FAILED: 'failed',
} as const;
export type ScheduleRunStatus = (typeof SCHEDULE_RUN_STATUS)[keyof typeof SCHEDULE_RUN_STATUS];

export interface ScheduleSpecPayload {
  schedule_type: ScheduleType;
  run_date?: string | null;      // once 전용 (YYYY-MM-DD, 미래)
  time_of_day?: string | null;   // once/daily/weekly ("HH:MM")
  days_of_week?: number[] | null; // weekly 전용 (0=월..6=일) — 조회 표시용
  cron_expr?: string | null;     // cron 전용 (5필드, 최소 간격 10분)
}

export interface ScheduleCreateRequest {
  name: string;                  // 1~200자, 자동 생성
  spec: ScheduleSpecPayload;
  instruction: string;           // 1~1,900자
  timezone: string;              // 항상 'Asia/Seoul' 명시 전송
  enabled: boolean;
}
export type ScheduleUpdateRequest = ScheduleCreateRequest; // PUT 동일 스키마

export interface ScheduleResponse {
  id: string;
  agent_id: string;
  name: string;
  spec: ScheduleSpecPayload;
  instruction: string;
  enabled: boolean;
  timezone: string;
  next_run_at: string | null;    // UTC ISO8601
  last_run_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ScheduleRunResponse {
  id: string;
  schedule_id: string;
  status: ScheduleRunStatus;
  scheduled_for: string;
  started_at: string | null;
  finished_at: string | null;
  session_id: string | null;
  run_id: string | null;
  error_message: string | null;
}

/** 생성 모드 전용 — 서버 미등록 로컬 항목 */
export interface StagedSchedule {
  localId: string;               // crypto.randomUUID()
  name: string;
  spec: ScheduleSpecPayload;
  instruction: string;
  timezone: string;
  enabled: boolean;
}

export const MAX_SCHEDULES_PER_AGENT = 10;
export const MAX_INSTRUCTION_LENGTH = 1900;
export const DEFAULT_SCHEDULE_TIMEZONE = 'Asia/Seoul';
```

### 2.2 엔드포인트 상수 — `src/constants/api.ts` (추가)

```ts
// ── Agent Schedule (agent-schedule) ──
AGENT_SCHEDULES: (agentId: string) => `/api/v1/agents/${agentId}/schedules`,
AGENT_SCHEDULE_DETAIL: (agentId: string, scheduleId: string) =>
  `/api/v1/agents/${agentId}/schedules/${scheduleId}`,
AGENT_SCHEDULE_ENABLED: (agentId: string, scheduleId: string) =>
  `/api/v1/agents/${agentId}/schedules/${scheduleId}/enabled`,
AGENT_SCHEDULE_RUNS: (agentId: string, scheduleId: string) =>
  `/api/v1/agents/${agentId}/schedules/${scheduleId}/runs`,
```

### 2.3 서비스 — `src/services/agentScheduleService.ts` (신규, authClient 사용)

```ts
export const agentScheduleService = {
  list: (agentId) => authClient.get<ScheduleResponse[]>(API_ENDPOINTS.AGENT_SCHEDULES(agentId)),
  create: (agentId, data: ScheduleCreateRequest) =>
    authClient.post<ScheduleResponse>(API_ENDPOINTS.AGENT_SCHEDULES(agentId), data),
  update: (agentId, scheduleId, data: ScheduleUpdateRequest) =>
    authClient.put<ScheduleResponse>(API_ENDPOINTS.AGENT_SCHEDULE_DETAIL(agentId, scheduleId), data),
  remove: (agentId, scheduleId) =>
    authClient.delete<void>(API_ENDPOINTS.AGENT_SCHEDULE_DETAIL(agentId, scheduleId)),
  setEnabled: (agentId, scheduleId, enabled: boolean) =>
    authClient.patch<ScheduleResponse>(API_ENDPOINTS.AGENT_SCHEDULE_ENABLED(agentId, scheduleId), { enabled }),
  listRuns: (agentId, scheduleId, params?: { limit?: number; offset?: number }) =>
    authClient.get<ScheduleRunResponse[]>(API_ENDPOINTS.AGENT_SCHEDULE_RUNS(agentId, scheduleId), { params }),
};
```

> 단건 GET은 목록 응답으로 충분하여 미구현 (Plan §2.3).

### 2.4 쿼리 키 — `src/lib/queryKeys.ts` (추가)

```ts
// ── Agent Schedules (agent-schedule) ──
agentSchedules: {
  all: ['agentSchedules'] as const,
  list: (agentId: string) => [...queryKeys.agentSchedules.all, 'list', agentId] as const,
  runs: (agentId: string, scheduleId: string) =>
    [...queryKeys.agentSchedules.all, 'runs', agentId, scheduleId] as const,
},
```

### 2.5 훅 — `src/hooks/useAgentSchedules.ts` (신규)

`useAgentBuilder.ts`와 동일 패턴 (`queryClient` 싱글톤 import, mutation 성공 시 invalidate).

| 훅 | 시그니처 | 비고 |
|----|----------|------|
| `useAgentSchedules` | `(agentId: string \| null)` → `useQuery<ScheduleResponse[]>` | `enabled: !!agentId`, key `agentSchedules.list(agentId)` |
| `useCreateSchedule` | `useMutation<ScheduleResponse, Error, { agentId; data }>` | onSuccess: `invalidate(list(agentId))` |
| `useUpdateSchedule` | `useMutation<ScheduleResponse, Error, { agentId; scheduleId; data }>` | 〃 |
| `useDeleteSchedule` | `useMutation<void, Error, { agentId; scheduleId }>` | 〃 + `invalidate(runs(agentId, scheduleId))` |
| `useToggleScheduleEnabled` | `useMutation<ScheduleResponse, Error, { agentId; scheduleId; enabled }>` | 〃 |
| `useScheduleRuns` | `(agentId, scheduleId, opts: { enabled: boolean })` → `useQuery<ScheduleRunResponse[]>` | `limit: 20` 고정, 확장 시에만 fetch |

에러 메시지: axios 에러의 `response.data.detail`을 우선 추출하는 로컬 헬퍼 `extractScheduleError(e): string` 제공 (400 검증 메시지를 폼에 그대로 표출 — Plan §5).

---

## 3. cron 유틸 설계 — `src/utils/scheduleCron.ts` (신규)

### 3.1 폼 값 모델

```ts
export interface CronFormValue {
  minute: string;     // '0'~'59' (폼 기본 '0' — '*' 불허: 10분 규칙)
  hour: string;       // '*'(매시) | '0'~'23'
  dayOfMonth: string; // '*'(매일) | '1'~'31'
  month: string;      // '*'(매월) | '1'~'12'
  dayOfWeek: string;  // '*'(매일) | '0'~'6' (cron 표준: 0=일요일)
}
export const DEFAULT_CRON_FORM: CronFormValue =
  { minute: '0', hour: '9', dayOfMonth: '*', month: '*', dayOfWeek: '*' };
```

> 주의: `spec.days_of_week`(weekly, 0=월)와 cron 표현식 요일(0=일)은 **기수가 다르다**. 폼 요일 드롭다운 표시는 일~토 순서로 cron 기준을 따른다.

### 3.2 함수 시그니처

| 함수 | 동작 |
|------|------|
| `buildCronExpr(form: CronFormValue): string` | 5필드 공백 결합 → `'0 9 * * *'` |
| `parseCronExpr(expr: string): CronFormValue \| null` | 각 필드가 `*` 또는 범위 내 단일 정수일 때만 성공(분은 정수 필수). `*/5`, `1,3`, `1-5` 등 복합식은 `null` → 표현식 모드 폴백 |
| `validateCronExpr(expr: string): { valid: boolean; error?: string }` | ① 공백 분리 5필드 ② 허용 문자 `[0-9*,\-/]` ③ 단일 정수 범위 검사 ④ 10분 휴리스틱: 분 필드가 `*` 또는 스텝 `*/n (n<10)` 또는 리스트의 최소 간격(순환 포함) < 10 → 거부 |
| `generateScheduleName(spec: ScheduleSpecPayload): string` | `describeSpec` 결과 사용, 200자 절단 |
| `describeSpec(spec: ScheduleSpecPayload): string` | 카드 요약 라벨 (§3.3) — 4개 유형 전부 커버 |

### 3.3 이름/요약 생성 규칙 (`describeSpec`)

| spec | 결과 |
|------|------|
| once | `1회 {run_date} {time_of_day}` → `1회 2026-07-10 09:00` |
| daily | `매일 {time_of_day} 실행` |
| weekly | `매주 {요일,요일} {time_of_day} 실행` (days_of_week 0=월 매핑) |
| cron — 폼 파싱 성공 & 일/월/요일 전부 `*` | `매일 {HH:MM} 실행` |
| cron — 요일 지정 | `매주 {요일} {HH:MM} 실행` |
| cron — 일 지정 | `매월 {n}일 {HH:MM} 실행` |
| cron — 시가 `*` | `매시 {m}분 실행` |
| cron — 파싱 불가(복합식) | `크론 {cron_expr}` |

### 3.4 표시용 시각 변환

`next_run_at`/`last_run_at`/runs 시각(UTC)은 `utils/formatters.ts`의 날짜 포맷 유틸을 재사용해 로컬(KST) 표시. 스케줄 전용 포맷이 필요하면 `formatters.ts`에 `formatDateTimeKST` 추가(기존 파일 컨벤션 준수) — 신규 파일 생성 금지.

---

## 4. 컴포넌트 설계

### 4.1 ScheduleForm — `src/components/agent-builder/schedule/ScheduleForm.tsx` (신규)

이미지(`docs/img/schedule.png`) 레이아웃 그대로. 신규/수정 겸용.

```ts
interface ScheduleFormProps {
  initial?: ScheduleResponse | null;  // null/undefined = 신규
  isSubmitting: boolean;
  submitError: string | null;         // 서버 400 detail 표출
  onSubmit: (payload: ScheduleCreateRequest) => void;
  onCancel: () => void;
}
```

**내부 상태**

| 상태 | 타입 | 초기값 |
|------|------|--------|
| `kind` | `'recurring' \| 'once'` | initial.spec.schedule_type === 'once' ? 'once' : 'recurring' |
| `inputMode` | `'form' \| 'expr'` | initial cron_expr 파싱 성공 → 'form', 실패 → 'expr' |
| `cronForm` | `CronFormValue` | 파싱 결과 or `DEFAULT_CRON_FORM` |
| `cronExprInput` | `string` | initial.spec.cron_expr ?? `buildCronExpr(DEFAULT_CRON_FORM)` |
| `runDate` / `timeOfDay` | `string` | initial(once) 값 or `''` / `'09:00'` |
| `instruction` | `string` | initial.instruction ?? `''` |
| `clientError` | `string \| null` | 클라 검증 실패 메시지 |

**UI 구성 (위→아래, 이미지 순서)**

1. `스케줄 유형` — 토글 버튼 2개: `반복`(활성=zinc-900 배경) / `1회`
2. **반복일 때** `스케줄 표현식` — 세그먼트 토글: `폼` / `스케줄 표현식`
   - 폼 모드: `분`(0~59 select, 기본 0) · `시`(매시/0~23) · `일`(매일/1~31) · `월`(매월/1~12) · `요일`(매일/일~토) — 좌측 라벨 + 우측 select 행 5개
   - 표현식 모드: 5필드 텍스트 입력 1개
   - `미리보기: {expr}` 박스 — 폼 모드는 `buildCronExpr(cronForm)`, 표현식 모드는 입력값 실시간 반영
3. **1회일 때** — `실행 날짜`(date input, min=내일) + `실행 시각`(time input)
4. `타임존` — `Asia/Seoul` 읽기 전용 박스
5. `실행 메시지` — textarea, placeholder "에이전트에게 보낼 메시지를 입력하세요", 하단에 `{n}/1900` 카운터 + 변수 힌트(`{today}` `{now}` `{weekday}` 사용 가능)
6. 하단 우측: `취소`(ghost) / `생성`(신규) 또는 `저장`(수정) — violet primary, 미충족 시 disabled

**제출 검증 → payload**

```
반복: validateCronExpr(preview) 통과 필수
  → spec = { schedule_type: 'cron', cron_expr: preview }
1회: runDate 필수 & 오늘(KST) 이후, timeOfDay 필수
  → spec = { schedule_type: 'once', run_date: runDate, time_of_day: timeOfDay }
공통: instruction 1~1900자 (trim 후 비어있으면 차단)
payload = {
  name: generateScheduleName(spec),
  spec, instruction,
  timezone: DEFAULT_SCHEDULE_TIMEZONE,
  enabled: initial?.enabled ?? true,   // 수정 시 기존 활성 상태 유지
}
```

### 4.2 SchedulePanel — `src/components/agent-builder/schedule/SchedulePanel.tsx` (신규)

```ts
interface SchedulePanelProps {
  mode: 'create' | 'edit';
  agentId: string | null;                    // edit에서 non-null
  stagedSchedules: StagedSchedule[];         // create 전용
  onStagedAdd: (item: StagedSchedule) => void;
  onStagedRemove: (localId: string) => void;
}
```

**공통 레이아웃** (패턴 A — 고정 헤더 + 스크롤 바디)

```
┌ 헤더: 🕐 "에이전트 자동 실행 스케줄을 관리합니다"      [+ 스케줄 추가] ┐
├ (폼 열림 시) ScheduleForm 카드 (bg-zinc-50 rounded-2xl)              │
├ 목록: ScheduleCard[]  /  빈 상태: "등록된 스케줄이 없습니다"          │
└──────────────────────────────────────────────────────────────────────┘
```

**edit 모드 동작**

| 액션 | 처리 |
|------|------|
| 목록 | `useAgentSchedules(agentId)` — 로딩 스켈레톤 / 에러 + 재시도 |
| 추가 | 폼 제출 → `useCreateSchedule.mutate` → 성공 시 폼 닫기 / 400은 `submitError`로 폼에 표출 |
| 수정 | 카드 `수정` 클릭 → `editingSchedule` 상태에 로드 → 폼 열림(initial 주입) → `useUpdateSchedule` |
| 토글 | 카드 스위치 → `useToggleScheduleEnabled.mutate` 즉시 (optimistic 없이 invalidate) |
| 삭제 | 카드 삭제 → `deleteTarget` 상태 → `ConfirmDialog`(variant="danger", "실행 이력도 함께 삭제됩니다") → `useDeleteSchedule` |
| 이력 | 카드 `이력` 클릭 → `expandedRunsId` 토글 → 확장 영역에서 `useScheduleRuns(agentId, id, { enabled: expanded })` |

**create 모드 동작**

- 목록 = `stagedSchedules` 렌더 (요약 라벨 + `등록 대기` 배지 + 삭제 버튼만. 토글/수정/이력 없음 — 서버 리소스 부재)
- 추가 = 폼 제출 → 클라 검증만 수행 후 `onStagedAdd({ localId: crypto.randomUUID(), ...payload })`
- 삭제 = 즉시 `onStagedRemove(localId)` (ConfirmDialog 불필요 — 서버 삭제 아님, 사용자 확정 사항)
- 안내 문구: "에이전트 생성 시 함께 등록됩니다"

**10개 제한**: `count = mode === 'edit' ? (data?.length ?? 0) : stagedSchedules.length` — `count >= MAX_SCHEDULES_PER_AGENT`면 추가 버튼 disabled + "에이전트당 최대 10개" 툴팁.

### 4.3 ScheduleCard (SchedulePanel 내부 컴포넌트)

```
┌───────────────────────────────────────────────────────┐
│ {describeSpec(spec)}                    [토글] [수정] [삭제] │
│ 다음 실행: {next_run_at → KST} · 최근: {last_run_at → KST}  │
│ 실행 메시지 1줄 요약 (line-clamp-1, zinc-400)               │
│ [이력 보기 ▾] ─ 확장 시 RunsList                            │
└───────────────────────────────────────────────────────┘
```

- enabled=false 카드: 좌측 라벨 `text-zinc-400` + `일시중지` 배지
- `spec.schedule_type`이 `daily`/`weekly`(백엔드 직접 생성분): 수정 버튼 disabled + title "이 유형은 화면에서 편집할 수 없습니다" (표시/토글/삭제/이력은 정상)

**RunsList (확장 영역)**

| status | 배지 |
|--------|------|
| running | amber + `animate-pulse` |
| success | emerald |
| failed | red + 하단에 `error_message` (text-[12px] text-red-500) |

행: `[배지] scheduled_for(KST) → finished_at(KST)` 최신순 20건, 없으면 "실행 이력이 없습니다".

### 4.4 AgentTestPanel 변경 — `src/components/agent-builder/AgentTestPanel.tsx`

1. 탭 정의: `{ id: 'schedule', label: '스케줄', enabled: true }`
2. Props 확장: `stagedSchedules`, `onStagedAdd`, `onStagedRemove` 추가 (StudioLayout이 그대로 pass-through)
3. 콘텐츠 3분기:

```tsx
{tab === 'skill' ? (
  <AgentSkillPanel ... />
) : tab === 'schedule' ? (
  <SchedulePanel mode={mode} agentId={agentId}
    stagedSchedules={stagedSchedules}
    onStagedAdd={onStagedAdd} onStagedRemove={onStagedRemove} />
) : (
  <TestChatView ... />
)}
```

주석의 "나머지(…스케줄…)는 비활성 placeholder" 문구에서 스케줄 제외로 갱신.

---

## 5. 페이지 통합 — `AgentBuilderPage` / `agentBuilder.ts`

### 5.1 폼 데이터 확장 — `src/types/agentBuilder.ts`

```ts
export interface AgentBuilderFormData {
  ...기존,
  // agent-schedule: 생성 모드 전용 staged 스케줄 (생성 성공 후 순차 POST)
  schedules: StagedSchedule[];
}
```

`DEFAULT_FORM`에 `schedules: []` 추가. **edit 모드에서는 사용하지 않음**(SchedulePanel이 서버 직결) — `editDetail` 로드 effect에서 `schedules: []` 유지.

### 5.2 staged 핸들러 (AgentBuilderPage)

```ts
const handleStagedScheduleAdd = (item: StagedSchedule) =>
  setForm((prev) => ({ ...prev, schedules: [...prev.schedules, item] }));
const handleStagedScheduleRemove = (localId: string) =>
  setForm((prev) => ({ ...prev, schedules: prev.schedules.filter(s => s.localId !== localId) }));
```

StudioLayout → AgentTestPanel로 props 전달 (기존 onSkillToggle과 동일 경로).

### 5.3 생성 성공 후 일괄 등록

`createMutation` onSuccess 콜백에서 async IIFE로 순차 등록 (`useCreateSchedule().mutateAsync` 사용):

```ts
onSuccess: async (response) => {
  if (form.systemPrompt.trim()) { ...기존 system_prompt 후속 update... }

  let failed = 0;
  for (const s of form.schedules) {
    try {
      await createScheduleMutation.mutateAsync({
        agentId: response.agent_id,
        data: { name: s.name, spec: s.spec, instruction: s.instruction,
                timezone: s.timezone, enabled: s.enabled },
      });
    } catch { failed += 1; }
  }
  const base = '에이전트가 성공적으로 등록되었습니다.';
  const suffix = form.schedules.length === 0 ? ''
    : failed === 0 ? ` 스케줄 ${form.schedules.length}건이 함께 등록되었습니다.`
    : ` 스케줄 ${form.schedules.length}건 중 ${failed}건 등록에 실패했습니다. 수정 화면의 스케줄 탭에서 다시 등록해주세요.`;
  setSaveResult({ type: 'success', message: base + suffix });
},
```

- **순차 실행** (병렬 금지): 실패 지점 명확화 + 백엔드 10개 제한 경합 방지 (Plan §5)
- 에이전트 생성 자체는 성공 처리 (스케줄 실패는 경고 문구로만)

---

## 6. 테스트 설계 (TDD)

### 6.1 MSW 핸들러 — `src/__tests__/mocks/handlers.ts` (추가)

in-memory `Map<agentId, ScheduleResponse[]>` 기반:

| 핸들러 | 동작 |
|--------|------|
| `GET */agents/:agentId/schedules` | 배열 반환 |
| `POST 〃` | 201 + 생성 항목 (11개째는 400 `{detail: '에이전트당 스케줄은 최대 10개…'}`) |
| `PUT/DELETE 〃/:scheduleId` | 200 / 204, 미존재 404 |
| `PATCH 〃/enabled` | enabled 반영 |
| `GET 〃/runs` | 고정 mock 2건 (success 1 + failed 1 with error_message) |

### 6.2 테스트 케이스

| 파일 | 케이스 |
|------|--------|
| `utils/scheduleCron.test.ts` | build 5필드 결합 / parse 왕복(`0 9 * * *`→폼→동일 expr) / 복합식 parse null / validate: 4필드·허용외문자·범위초과·분`*`·`*/5` 거부, `*/10` `0,30` 허용 / describeSpec 유형별 8케이스 / generateScheduleName 200자 절단 |
| `hooks/useAgentSchedules.test.ts` | 목록 조회 성공 / agentId null이면 미조회 / create 후 list invalidate(재조회) / toggle PATCH payload / delete 204 / runs enabled 제어 |
| `schedule/ScheduleForm.test.tsx` | 기본 렌더(반복+폼 모드, 미리보기 `0 9 * * *`) / 드롭다운 변경→미리보기 갱신 / 표현식 모드 전환·입력 반영 / 잘못된 표현식 제출 차단+에러 / 1회 모드: 과거 날짜 차단 / 실행 메시지 빈값·1900자 초과 차단 / 제출 payload 검증(cron·once 각 1건, name 자동 생성 포함) / initial 주입: cron 파싱→폼 모드, `*/5`→표현식 모드, 저장 라벨 |
| `schedule/SchedulePanel.test.tsx` | [edit] 빈 상태 / 목록 카드 렌더(요약·next_run_at) / 추가 폼→POST 호출 / 수정 진입→PUT / 토글→PATCH / 삭제→ConfirmDialog→DELETE / 이력 확장→runs 렌더(failed error_message) / 10개 도달 시 추가 버튼 disabled / daily 카드 수정 버튼 disabled · [create] staged 렌더+`등록 대기` 배지 / 추가·삭제 로컬 콜백만(서버 미호출 검증) |
| `AgentBuilderPage` 통합 (기존 테스트 파일 확장) | 생성 모드: staged 2건 → 생성 성공 → 스케줄 POST 2회 / 1건 실패 시 결과 메시지에 실패 문구 |

> 실행: `npm run test:run -- --pool=threads` (Windows forks 타임아웃 회피). 사전 실패 8건은 회귀 아님.

---

## 7. 구현 순서

| 단계 | 산출물 | 의존 |
|------|--------|------|
| 1 | `types/agentSchedule.ts` + `constants/api.ts` + `agentScheduleService.ts` + MSW 핸들러 | - |
| 2 | `utils/scheduleCron.ts` (+test, Red→Green) | 1 |
| 3 | `lib/queryKeys.ts` + `hooks/useAgentSchedules.ts` (+test) | 1 |
| 4 | `ScheduleForm.tsx` (+test) | 2 |
| 5 | `SchedulePanel.tsx` (+test) | 3, 4 |
| 6 | `AgentTestPanel`/`StudioLayout` props + `agentBuilder.ts` 폼 확장 + `AgentBuilderPage` staged/일괄 POST (+통합 test) | 5 |
| 7 | 전체 검증: test:run + type-check + lint | 6 |

---

## 8. 완료 기준 매핑 (Plan §6)

| AC | 검증 방법 |
|----|-----------|
| 1. 탭 활성화 + 이미지 동일 폼 | SchedulePanel/ScheduleForm 테스트 + 수동 확인 |
| 2. 수정 모드 즉시 CRUD + ConfirmDialog | SchedulePanel edit 테스트 6종 |
| 3. 생성 모드 staged → 일괄 POST + 부분 실패 문구 | AgentBuilderPage 통합 테스트 2종 |
| 4. 폼↔미리보기 실시간, cron/once payload | ScheduleForm payload 테스트 |
| 5. name 자동 생성, 1900자 차단, 10개 제한 | scheduleCron + Form + Panel 테스트 |
| 6. 실행 이력 표시 | SchedulePanel runs 테스트 |
| 7. 전체 그린 | Step 7 |
