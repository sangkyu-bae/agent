# agent-settings-tab Design Document

> **Feature**: 에이전트 빌더 설정 탭 활성화 — Recursion Limit 실기능 + 연동 3종 스텁
> **Plan**: `docs/01-plan/features/agent-settings-tab.plan.md`
> **Project**: idt_front 전용 (백엔드 diff 0)
> **Author**: 배상규
> **Date**: 2026-08-07
> **Status**: Draft

---

## 1. 설계 요약

`AgentTestPanel`의 비활성 `settings` 탭을 활성화하고 `SettingsPanel` 컴포넌트를 신설한다.
Recursion Limit 입력은 신규 폼 필드 `maxIterations`에 바인딩되어 기존 StudioHeader 저장
버튼으로 create/update 페이로드(`max_iterations`)에 실린다. MCP 서버·Webhook·Telegram
섹션은 정적 스텁(토글 disabled + "준비중")으로만 그린다.

### 코드 확인으로 확정된 사실 (2026-08-07)

| 사실 | 위치 |
|------|------|
| 설정 탭 비활성 정의 + 삼항 분기 체인 | `AgentTestPanel.tsx:53-61, 88-111` |
| `RightTabId`에 `'settings'` 기존재 (타입 확장 불필요) | `types/agentBuilder.ts:143` |
| `AgentDetail` 타입에 `max_iterations` **선언 누락** (서버 응답에는 존재 — 페이지 테스트 픽스처 3곳에서 확인) | `types/agentStore.ts:42-65` |
| `mapDetailToForm`이 detail의 max_iterations를 버림 | `utils/agentDetailMapping.ts:55-73` |
| create/update 페이로드에 max_iterations 미포함 | `AgentBuilderPage/index.tsx:144-256` |
| 백엔드 create ge=10 le=1000 기본 25 / update optional / repo 화이트리스트 포함 | `idt/src/application/agent_builder/schemas.py:71,115` 외 |
| 패널 전달 체인: AgentBuilderPage → StudioLayout → AgentTestPanel (전용 핸들러 패턴: onSkillToggle 등) | `StudioLayout.tsx:83-124` |

---

## 2. 설계 결정 (Decisions)

| # | 결정 | 선택 | 근거 |
|---|------|------|------|
| D1 | Recursion Limit 값 배선 | `form.maxIterations` ↔ API `max_iterations` (기존 컬럼 재사용) | Plan 결정 1 — 백엔드 완비, 미들웨어 config는 별개 후속 |
| D2 | 범위 검증 UX | **blur/Enter 시 clamp** (인라인 에러 없음) | 저장 버튼이 StudioHeader(탭 밖)에 있어 에러 상태를 페이지로 끌어올려 저장 차단하는 배선(systemPromptError류)이 필요해짐 — clamp는 "페이로드는 항상 유효"를 컴포넌트 로컬에서 보장. 시안에도 에러 UI 없음 |
| D3 | 입력 중간 상태 | 로컬 문자열 state로 자유 입력 허용, 확정 시점(blur/Enter)에 파싱→clamp→`onChange`. 빈 값·비숫자는 **기존 값 복원 + onChange 미호출** | 타이핑 중 "1"(→10 미만) 같은 과도기 값을 즉시 clamp하면 입력 불가. 폼 요소/submit 미사용이라 jsdom constraint validation 함정(noValidate) 자체가 발생하지 않음 |
| D4 | 상수 위치 | `constants/agentSettings.ts` 신설: `MAX_ITERATIONS = { DEFAULT: 25, MIN: 10, MAX: 1000 }` | `constants/agentSkill.ts`(MAX_ATTACHED_SKILLS) 선례. 백엔드 `IterationLimitPolicy`와 수동 동기 — 주석으로 명기 |
| D5 | edit 프라임·전송 | `mapDetailToForm`: `maxIterations: detail.max_iterations ?? MAX_ITERATIONS.DEFAULT`. create/update 모두 **항상 전송** | detail이 항상 값을 반환하므로 폴백은 방어용. edit 저장은 name/systemPrompt 비어있으면 이미 차단되므로 프라임 전 저장으로 25가 새어나갈 실질 경로 없음. dirty 추적은 폼 전반에 없는 관례 — 미도입 (Plan 6.2) |
| D6 | 핸들러 배선 | 전용 콜백 `onMaxIterationsChange(value: number)` — Page → StudioLayout → AgentTestPanel → SettingsPanel | 기존 전용 핸들러 패턴(onSkillToggle/onMiddlewareToggle) 일관. 범용 onChange(form) 전달은 AgentTestPanel에 폼 전체 변경 권한을 줘 반경 과대 |
| D7 | 탭 분기 구조 | 기존 삼항 체인에 `tab === 'settings'` 분기 1개 추가 (구조 개편 없음) | 최소 diff — 체인 개편은 기능과 무관한 회귀 반경. Plan 리스크의 "switch 전환 검토"는 기각 |
| D8 | 스텁 렌더링 | 스텁 3종은 정적 설정 배열 + 공용 `StubSection` 렌더러. 토글은 `<button role="switch" aria-checked={false} disabled title="준비중">` | 반복 마크업 제거, 후속 실기능 전환 시 섹션 단위 교체 용이. disabled로 동작 착시 차단 (Plan 결정 3) |
| D9 | 파일 구성 | `settings/SettingsPanel.tsx` 단일 파일 (RecursionLimitSection + StubSection 내부 분리) | 페이지 아님 — 200줄 초과 시에만 파일 분리 (프로젝트 규칙) |

---

## 3. 파일 구조 (신규/수정)

```
idt_front/src/
├── constants/
│   └── agentSettings.ts                          [신규] MAX_ITERATIONS 상수 (백엔드 정책 미러 — 주석 명기)
├── components/agent-builder/
│   ├── AgentTestPanel.tsx                        [수정] settings enabled:true + 분기 + onMaxIterationsChange prop
│   └── settings/
│       ├── SettingsPanel.tsx                     [신규] 4개 섹션 (아래 §4)
│       └── SettingsPanel.test.tsx                [신규] TDD — §5-1
├── types/
│   ├── agentBuilder.ts                           [수정] FormData.maxIterations / Create·UpdateRequest.max_iterations?
│   └── agentStore.ts                             [수정] AgentDetail.max_iterations?: number (additive)
├── utils/
│   ├── agentDetailMapping.ts                     [수정] maxIterations 프라임 (?? DEFAULT)
│   └── agentDetailMapping.test.ts                [수정] 프라임·폴백 케이스 추가 — §5-2
├── components/agent-builder/StudioLayout.tsx     [수정] onMaxIterationsChange 관통
└── pages/AgentBuilderPage/
    ├── index.tsx                                 [수정] DEFAULT_FORM.maxIterations:25 + 핸들러 + 페이로드 2곳
    └── index.test.tsx                            [수정] 통합 단언 — §5-3
```

### 3-1. SettingsPanel Props (계약)

```typescript
interface SettingsPanelProps {
  /** 현재 반복 한도 (form.maxIterations — 단일 진실원) */
  maxIterations: number;
  /** 확정된(clamp 완료) 값만 올라온다 — 상위는 검증 불필요 */
  onMaxIterationsChange: (value: number) => void;
}
```

### 3-2. 타입 변경 (additive — 기존 소비자 무변경)

```typescript
// types/agentBuilder.ts
CreateBuilderAgentRequest { …, max_iterations?: number }   // 백엔드 기본 25라 optional
UpdateBuilderAgentRequest { …, max_iterations?: number }   // undefined = 변경 안 함 계약 유지
AgentBuilderFormData      { …, maxIterations: number }     // DEFAULT_FORM에서 25

// types/agentStore.ts
AgentDetail               { …, max_iterations?: number }   // 응답 기존재 필드의 선언 보강
```

---

## 4. UI 설계 (시안: docs/img/setting.png)

패널 골격 — 자체 스크롤 (AgentChatLayout overflow:hidden 대응, 스킬 탭 래퍼와 동일):

```
<div style={{height:'100%', overflowY:'auto'}} className="px-4 py-4">
  헤더행: "에이전트 실행 설정을 관리합니다" (text-[12px] text-zinc-400)
          ※ 시안의 [저장] 버튼은 그리지 않음 — StudioHeader 저장 통합 (Plan 결정 4)
  ── 섹션 1. Recursion Limit (실기능) ──
     ⚙ 제목 / ⓘ 안내 카드(bg-zinc-50 rounded-xl):
       "에이전트가 반복적으로 실행될 수 있는 최대 횟수입니다. …무한 루프를 방지합니다."
     라벨 "최대 반복 횟수" + number 입력(w-24) + ↺ 복원 버튼 + "(범위: 10 - 1000)"
     힌트: "기본값: 25. 복잡한 작업은 더 높은 값이 필요할 수 있습니다."
  ── 섹션 2. MCP 서버 (스텁) ──
     안내문 + "MCP 서버 활성화" 라벨 + disabled 토글
  ── 섹션 3. Webhook (스텁) ──
     안내문(Bearer dbuilder_xxx 문구 포함) + "Webhook 활성화" 라벨 + disabled 토글
  ── 섹션 4. Telegram 연동 (스텁) ──
     안내문 + "⊗ 연결되지 않음" + "비활성화됨" 라벨 + disabled 토글
</div>
```

- 스타일 토큰: 섹션 제목 `text-[15px] font-semibold text-zinc-900`, 안내 카드 `rounded-xl bg-zinc-50 p-4 text-[12.5px] text-zinc-500`, 토글 트랙 `disabled` 시 `bg-zinc-200 cursor-not-allowed opacity-60`.
- 입력 동작 (D2·D3): `<input type="number">` + 로컬 문자열 state. `onBlur`/Enter →
  `parseInt` → NaN·빈값이면 `String(maxIterations)`로 복원(onChange 미호출), 유효하면
  `Math.min(MAX, Math.max(MIN, n))` clamp 후 `onChange`. prop 변경(↺·프라임) 시 로컬 state 동기화.
- ↺ 버튼: `onChange(MAX_ITERATIONS.DEFAULT)` — aria-label "기본값으로 복원".

---

## 5. 테스트 설계 (TDD — 구현 전 작성)

### 5-1. `SettingsPanel.test.tsx` (신규)

| # | 케이스 | 단언 |
|---|--------|------|
| 1 | 렌더 | 섹션 제목 4종(Recursion Limit/MCP 서버/Webhook/Telegram 연동) 노출, 저장 버튼 부재 |
| 2 | 값 표시 | maxIterations=25 → 입력값 "25", 안내문에 "10 - 1000"·"기본값: 25" 포함 |
| 3 | 정상 확정 | 입력 "500" + blur → onMaxIterationsChange(500) 1회 |
| 4 | 상한 clamp | "1001" + blur → onChange(1000) / 하한 "9" + blur → onChange(10) |
| 5 | 무효 입력 복원 | "" 또는 "abc" + blur → onChange 미호출, 입력이 기존 값으로 복원 |
| 6 | 복원 버튼 | maxIterations=500에서 ↺ 클릭 → onChange(25) |
| 7 | 스텁 비활성 | role="switch" 3개 모두 disabled + title "준비중", aria-checked=false |

※ 값 주입은 `fireEvent.change` (음수·범위 이탈 — jsdom 관례), 확정은 `fireEvent.blur`.

### 5-2. `agentDetailMapping.test.ts` (추가)

| # | 케이스 | 단언 |
|---|--------|------|
| 1 | 프라임 | detail.max_iterations=500 → form.maxIterations=500 |
| 2 | 결측 폴백 | max_iterations 없는 detail → form.maxIterations=25 |

### 5-3. `AgentBuilderPage/index.test.tsx` (추가)

| # | 케이스 | 단언 |
|---|--------|------|
| 1 | create 페이로드 | 새 에이전트 저장 시 요청 body `max_iterations: 25` 포함 (MSW 캡처) |
| 2 | edit 프라임→수정→저장 | detail(max_iterations:500) 프라임 → 설정 탭 입력 "500" 표시 → "300" 변경+blur → 저장 시 update body `max_iterations: 300` |
| 3 | 기존 페이로드 무회귀 | 기존 필드(skill_ids/middleware_types 등) 단언 테스트 통과 유지 (FR-08) |

※ MSW per-file listen 3종 훅, `--pool=threads` 실행 관례 준수.

---

## 6. 구현 순서

1. **타입·상수** — `agentSettings.ts` 신설, `agentBuilder.ts`/`agentStore.ts` 필드 추가 (컴파일 기준선)
2. **매핑 (Red→Green)** — 5-2 테스트 작성 → `mapDetailToForm` 프라임 구현
3. **SettingsPanel (Red→Green)** — 5-1 테스트 작성 → 컴포넌트 구현 (D2·D3·D8)
4. **배선** — `AgentTestPanel`(enabled + 분기 + prop 관통), `StudioLayout`, `AgentBuilderPage`
   (DEFAULT_FORM, `handleMaxIterationsChange`, create/update 페이로드 2곳)
5. **통합 (Red→Green)** — 5-3 테스트 작성 → 페이로드·프라임 검증
6. **전체 회귀** — `npm run test:run -- --pool=threads` + `npm run type-check` (사전 실패 8건 제외 기준)

---

## 7. 영향 범위 / 주의사항

- **백엔드 무변경** — 기존 optional 계약 소비만. api-contract-sync 불필요.
- **update 항상 전송** (D5): 기존 update 요청에 `max_iterations` 필드가 새로 실리지만 백엔드
  optional(None=무변경)이라 additive. 프라임 실패 시 25가 전송될 수 있는 경로는 name/systemPrompt
  필수 검증이 선행 차단 — 통합 테스트 5-3-2가 프라임→저장 경로를 고정.
- **스텁 3종은 상태·페이로드 제로** — form/요청에 어떤 필드도 추가하지 않는다 (FR-07).
  후속 실기능 PDCA에서 섹션 단위로 교체.
- **탭 노출 모드**: create/edit 공통 활성 (FR-01). SchedulePanel처럼 mode 분기할 상태가 없어
  mode prop 불필요.
- **상수 이중화 주의**: `MAX_ITERATIONS`는 백엔드 `IterationLimitPolicy`의 프론트 미러 —
  백엔드 범위 변경 시 함께 수정해야 함을 상수 파일 주석에 명기.
- 오프너·파일 탭은 여전히 비활성 placeholder — 이번 diff에서 건드리지 않는다.
