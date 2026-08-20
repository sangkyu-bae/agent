# progress-card Design Document

> **Summary**: 배열 props로 단계를 조합하는 공통 진행 상황 카드 — ProgressCard / ProgressStepItem / StatusBadge 3-계층 설계
>
> **Project**: idt_front (sangplusbot 프론트엔드)
> **Version**: 0.0.0
> **Author**: 배상규
> **Date**: 2026-08-19
> **Status**: Draft
> **Planning Doc**: [progress-card.plan.md](../../01-plan/features/progress-card.plan.md)

---

## Context Anchor

> Plan 문서에서 복사. Design→Do 핸드오프 시 전략 컨텍스트 유지용.

| Key | Value |
|-----|-------|
| **WHY** | 다단계 진행 상황을 표시할 재사용 가능한 UI가 없어 화면별 중복 구현·스타일 파편화 위험 |
| **WHO** | idt_front 개발자(1차 소비자), 최종적으로 자동 에이전트 빌드 화면 사용자 |
| **RISK** | 사용처(자동 빌드 화면)가 아직 미구현 — 실제 요구와 어긋난 과설계 가능성 |
| **SUCCESS** | 배열 props만으로 이미지(docs/img/card.png)와 동일한 카드 렌더링 + 컴포넌트 테스트 통과 |
| **SCOPE** | 공통 컴포넌트 3종 + 단위 테스트. 실 데이터/API 연동과 페이지 적용은 후속 기능 |

---

## 1. Overview

### 1.1 Design Goals

- `steps: ProgressStep[]` 배열 하나로 `docs/img/card.png`와 동일한 세로 타임라인 카드를 렌더링한다.
- 상태 배지(`StatusBadge`)와 단계 아이템(`ProgressStepItem`)을 독립 컴포넌트로 분리해 단독 재사용을 허용한다.
- 외부 스토어·훅·API 의존이 전혀 없는 순수 presentational 컴포넌트로 만든다.

### 1.2 Design Principles

- **Stateless**: 내부 상태 없음. 상태 전이는 부모가 배열을 갱신해서 표현한다.
- **YAGNI**: props는 최소로 유지, 확장은 optional prop으로만 (Plan §5 리스크 완화).
- **디자인 토큰 준수**: CLAUDE.md UI 디자인 시스템 (violet primary gradient, zinc border, rounded-2xl 카드).
- **접근성**: 상태를 색상만으로 전달하지 않음 — 배지 텍스트 병행, `<ol>` 시맨틱 목록.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | 단일 파일, 내부 비공개 컴포넌트 | 타입/상수 파일 분리 + barrel export | 컴포넌트 3파일, 타입·상수는 ProgressCard.tsx에서 export |
| **New Files** | 2 | 8 | **6** |
| **Modified Files** | 0 | 0 | 0 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Medium | High | High |
| **Effort** | Low | High | Medium |
| **Risk** | Plan 요구(컴포넌트 단위 재사용)와 어긋남 | 소비자 없는 상태의 과설계 | Low (balanced) |

**Selected**: **Option C** — **Rationale**: Plan에서 확정한 3-계층 분리·배지 독립 재사용을 만족하면서, 프로젝트 컨벤션(Props interface는 컴포넌트 파일 상단)을 따르고 소비자 없는 별도 타입/상수 파일을 만들지 않는다. (Checkpoint 3 사용자 선택, 2026-08-19)

### 2.1 Component Diagram

```
┌──────────────────────────────────────────────┐
│ ProgressCard                                 │
│  ├─ 헤더 (icon + title)                       │
│  └─ <ol>                                     │
│      └─ ProgressStepItem × N  (steps.map)    │
│          ├─ StepIcon (상태별 원형 아이콘)        │
│          ├─ 커넥터 라인 (isLast가 아닐 때)       │
│          ├─ label 텍스트                       │
│          └─ StatusBadge (상태 배지)            │
└──────────────────────────────────────────────┘
        ▲ props만 (steps 배열)
   부모 컴포넌트 (자동 빌드 화면 등 — 후속 기능)
```

### 2.2 Data Flow

```
부모: ProgressStep[] 배열 구성/갱신
  → ProgressCard(steps) → steps.map → ProgressStepItem(step, isLast)
  → 상태별 아이콘/커넥터/라벨 강조 + StatusBadge(status, label?)
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| ProgressCard | ProgressStepItem | 단계 행 렌더링 |
| ProgressStepItem | StatusBadge | 상태 배지 표시 |
| StatusBadge | (없음) | 순수 배지 |

> 세 파일 모두 React 외 외부 의존 없음 (아이콘은 인라인 SVG).

---

## 3. Data Model

### 3.1 Entity Definition

> **구현 시 변경 (v0.2)**: `react-refresh/only-export-components` 린트 규칙이 컴포넌트 파일의
> 런타임 상수 export를 금지하고, 프로젝트 컨벤션상 `as const` 상수는 `src/types/*.ts`에 위치하므로
> (`WORKFLOW_STEP_TYPE` 등 선례) 아래 정의는 **`src/types/progress.ts`** 로 분리했다.
> `ProgressCard.tsx`는 타입만 re-export (`export type { ProgressStep, ProgressStepStatus }`).

```tsx
// src/types/progress.ts (Option C 변형 — 상수·타입 분리)
export const PROGRESS_STEP_STATUS = {
  COMPLETED: 'completed',
  IN_PROGRESS: 'in_progress',
  PENDING: 'pending',
  ERROR: 'error',
} as const;

export type ProgressStepStatus =
  (typeof PROGRESS_STEP_STATUS)[keyof typeof PROGRESS_STEP_STATUS];

export interface ProgressStep {
  id?: string;               // 미지정 시 index를 key로 사용
  label: string;             // 예: "Phase 1: 프로젝트 초기화"
  status: ProgressStepStatus;
  badgeLabel?: string;       // 배지 기본 라벨 오버라이드
}
```

### 3.2 컴포넌트 Props

```tsx
// StatusBadge.tsx
interface StatusBadgeProps {
  status: ProgressStepStatus;
  label?: string;            // 미지정 시 상태별 기본 라벨 (완료/진행중/대기중/실패)
}

// ProgressStepItem.tsx
interface ProgressStepItemProps {
  step: ProgressStep;
  isLast?: boolean;          // true면 커넥터 라인 미표시 (FR-08)
}

// ProgressCard.tsx
interface ProgressCardProps {
  steps: ProgressStep[];
  title?: string;            // 기본 "진행 상황" (FR-06)
  icon?: ReactNode;          // 헤더 아이콘 교체 (기본: 클립보드 목록 SVG)
  className?: string;        // 외부 여백 조정용
}
```

### 3.3 Database Schema

N/A — 순수 UI 컴포넌트, 저장소 없음.

---

## 4. API Specification

N/A — API 호출 없음. (자동 에이전트 빌드 v3 auto 연동은 후속 기능 스코프)

---

## 5. UI/UX Design

### 5.1 Screen Layout

```
┌─ ProgressCard (rounded-2xl border border-zinc-200 bg-white shadow-sm) ─┐
│ ┌ 헤더 (px-5 py-4, border-b border-zinc-100) ────────────────────────┐ │
│ │ [📋 icon]  진행 상황 (text-[15px] font-semibold text-zinc-900)     │ │
│ └───────────────────────────────────────────────────────────────────┘ │
│ ┌ 바디 (px-5 py-4) ──────────────────────────────────────────────────┐ │
│ │ (✔)──  Phase 1: 프로젝트 초기화                          [완료]     │ │
│ │  │   ← 커넥터: 완료 단계 아래 = violet, 그 외 = zinc-200            │ │
│ │ (→)    Phase 2: 사용자 의도 분석...  ← font-semibold    [진행중]    │ │
│ │  │                                                                │ │
│ │ (◷)    Phase 3: 도구 추천...                            [대기중]   │ │
│ │  ⋮                                                               │ │
│ │ (◷)    Phase 7: 에이전트 빌드         ← 마지막: 커넥터 없음 [대기중]  │ │
│ └───────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────┘
```

### 5.2 상태별 시각 스펙

| 상태 | 원형 아이콘 (h-8 w-8 rounded-full) | 라벨 텍스트 | 배지 |
|------|-----------------------------------|------------|------|
| `completed` | 배경 `linear-gradient(135deg,#7c3aed,#4f46e5)` + 흰색 체크 SVG | `text-[14px] text-zinc-700` | `bg-violet-100 text-violet-600` "완료" |
| `in_progress` | `bg-indigo-600` + 흰색 화살표(→) SVG | `text-[14px] font-semibold text-zinc-900` | `border border-indigo-200 bg-white text-indigo-600` "진행중" |
| `pending` | `border border-zinc-200 bg-white` + 시계 SVG `text-zinc-400` | `text-[14px] text-zinc-500` | `border border-zinc-200 bg-white text-zinc-500` "대기중" |
| `error` | `bg-red-500` + 흰색 X SVG | `text-[14px] text-red-600` | `bg-red-50 border border-red-200 text-red-600` "실패" |

공통 스펙:
- 배지: `rounded-full px-2.5 py-0.5 text-[12px] font-medium whitespace-nowrap`
- 커넥터: 아이콘 중앙 아래 세로선 `w-px h-5` — 해당 단계가 `completed`면 `bg-violet-400`, 아니면 `bg-zinc-200`. 마지막 단계는 미표시 (FR-08)
- 행 레이아웃 (2단 구조 — 세로 커넥터 칼럼 때문에 li 자체는 `items-center` 미적용): `<li class="flex gap-3">` 안에 [아이콘+커넥터 세로 칼럼] + [`flex h-8 items-center gap-3` 콘텐츠 행]. 라벨 `flex-1 min-w-0 truncate`, 배지 우측 고정
- 빈 배열: 바디에 `text-[12px] text-zinc-400` "표시할 단계가 없습니다" (FR-07)
- 애니메이션·클릭 인터랙션 없음 (정적 표시 전용 — Plan 확정)

### 5.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| ProgressCard | `src/components/common/ProgressCard.tsx` | 카드 프레임 + 헤더 + steps 배열 → `<ol>` 렌더링. 타입 re-export (정의는 `src/types/progress.ts` — v0.2) |
| ProgressStepItem | `src/components/common/ProgressStepItem.tsx` | 단계 1행: 상태 아이콘 + 커넥터 + 라벨 + StatusBadge |
| StatusBadge | `src/components/common/StatusBadge.tsx` | 상태별 색상 배지 (라벨 오버라이드 가능) |

### 5.4 Page UI Checklist

> 페이지가 아닌 공통 컴포넌트이므로 컴포넌트 단위 체크리스트로 대체. Gap Detector는 아래 항목을 검증한다.

#### ProgressCard

- [ ] 카드 프레임: `rounded-2xl border border-zinc-200 bg-white shadow-sm`
- [ ] 헤더: 아이콘 슬롯(기본 클립보드 SVG) + 타이틀(기본 "진행 상황", `title` prop 오버라이드)
- [ ] 목록: `<ol>` 시맨틱, `steps` 배열 순서 그대로 렌더링
- [ ] 각 항목 key: `step.id` 우선, 없으면 index
- [ ] 마지막 항목에 `isLast` 전달 (커넥터 미표시)
- [ ] 빈 배열: "표시할 단계가 없습니다" 문구, 레이아웃 깨짐 없음
- [ ] `className` prop 외부 병합

#### ProgressStepItem

- [ ] 상태 4종별 원형 아이콘 (§5.2 스펙: completed=보라 그라데이션 체크 / in_progress=인디고 화살표 / pending=회색 시계 / error=빨강 X)
- [ ] 아이콘 SVG는 `aria-hidden="true"` (상태 의미는 배지 텍스트가 전달)
- [ ] `in_progress` 라벨 `font-semibold` 강조 (FR-04)
- [ ] 커넥터: `isLast=false`일 때만 표시, completed 단계는 violet / 그 외 zinc
- [ ] 긴 라벨 `truncate` 처리
- [ ] StatusBadge 우측 배치, `step.badgeLabel` 전달

#### StatusBadge

- [ ] 상태별 기본 한글 라벨: 완료 / 진행중 / 대기중 / 실패
- [ ] `label` prop으로 오버라이드 가능 (FR-05)
- [ ] 상태별 색상 클래스 (§5.2 배지 열)

---

## 6. Error Handling

> 런타임 API 에러 없음 — props 엣지 케이스만 처리.

| Case | Handling |
|------|----------|
| `steps` 빈 배열 | 빈 상태 문구 표시 (FR-07) |
| `step.id` 미지정 | index를 key로 폴백 |
| 라벨이 카드 폭 초과 | `truncate` (min-w-0) |
| `badgeLabel` 빈 문자열 | 빈 문자열 그대로 렌더링하지 않고 기본 라벨 사용 (`label || DEFAULT`) |

---

## 7. Security Considerations

- 사용자 입력·API·저장소 없음. `label`은 React 텍스트 노드로만 렌더링 (`dangerouslySetInnerHTML` 미사용) — XSS 해당 없음.

---

## 8. Test Plan

> 순수 UI 컴포넌트 — L1(API)/L3(E2E)는 해당 없음. Vitest + RTL 단위 테스트가 전부이며 Do 단계에서 TDD(Red→Green→Refactor)로 코드와 1세트 작성한다.

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| Unit (컴포넌트) | StatusBadge / ProgressStepItem / ProgressCard | Vitest + RTL | Do |
| L1 API | N/A (API 없음) | - | - |
| L3 E2E | N/A (페이지 없음 — 후속 기능에서) | - | - |

### 8.2 Unit Test Scenarios

#### StatusBadge.test.tsx

| # | Test | Expected |
|---|------|----------|
| 1 | status별 기본 라벨 렌더링 (4종) | "완료"/"진행중"/"대기중"/"실패" 텍스트 존재 |
| 2 | `label="Phase 완료"` 오버라이드 | 기본 라벨 대신 해당 텍스트 표시 |
| 3 | status별 색상 클래스 | completed→`text-violet-600` 포함, error→`text-red-600` 포함 등 |

#### ProgressStepItem.test.tsx

| # | Test | Expected |
|---|------|----------|
| 1 | 라벨 텍스트 렌더링 | `step.label` 표시 |
| 2 | in_progress 라벨 강조 | 라벨 요소에 `font-semibold` 클래스 |
| 3 | pending 라벨 비강조 | `font-semibold` 없음 |
| 4 | `isLast=false` 커넥터 존재 | connector 요소(data-testid="step-connector") 존재 |
| 5 | `isLast=true` 커넥터 없음 | connector 요소 부재 (FR-08) |
| 6 | completed 커넥터 색 | `bg-violet-400` 클래스 |
| 7 | badgeLabel 전달 | 배지에 오버라이드 라벨 표시 |

#### ProgressCard.test.tsx

| # | Test | Expected |
|---|------|----------|
| 1 | 기본 타이틀 | "진행 상황" 텍스트 존재 (FR-06) |
| 2 | `title` 오버라이드 | 커스텀 타이틀 표시 |
| 3 | steps 7개 배열 렌더링 | `getAllByRole('listitem')` 길이 7, 순서 일치 (FR-01) |
| 4 | 상태 혼합 배열 | 각 단계의 배지 라벨(완료/진행중/대기중) 동시 표시 |
| 5 | 빈 배열 | "표시할 단계가 없습니다" 표시, list 부재 (FR-07) |
| 6 | 목록 시맨틱 | `getByRole('list')` 존재 (`<ol>`) |
| 7 | error 상태 포함 | "실패" 배지 렌더링 (FR-02) |

### 8.3 Seed Data Requirements

테스트 픽스처는 각 테스트 파일 내 상수로 정의 (별도 seed 불필요):

```tsx
const AUTO_BUILD_STEPS: ProgressStep[] = [
  { label: 'Phase 1: 프로젝트 초기화', status: 'completed' },
  { label: 'Phase 2: 사용자 의도 분석 에이전트가 의도 수집', status: 'in_progress' },
  { label: 'Phase 3: 도구 추천 에이전트가 도구 추천', status: 'pending' },
  // ... Phase 7까지 — docs/img/card.png 재현 케이스
];
```

---

## 9. Clean Architecture

### 9.1 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| ProgressCard / ProgressStepItem / StatusBadge | Presentation | `src/components/common/` |
| ProgressStep 타입·상수 | Domain | `src/types/progress.ts` (v0.2 — 린트 규칙·types/ 컨벤션에 따라 분리) |

### 9.2 Dependency Rules

- 세 컴포넌트 모두 `services/`, `store/`, `hooks/`를 import하지 않는다 (NFR: 재사용성 — 코드 리뷰 검증 항목).
- import 방향: `ProgressStepItem` → `StatusBadge`, `ProgressCard` → `ProgressStepItem`. 역방향 금지.
- 타입·상수는 `src/types/progress.ts`에 정의하고 세 컴포넌트가 `import type`으로 가져온다 (v0.2). `ProgressCard.tsx`는 소비자 편의를 위해 타입을 re-export한다.

> 순환 참조 없음: Presentation(`components/common/`) → Domain(`types/progress.ts`) 단방향. Domain은 외부 import 0건.

---

## 10. Coding Convention Reference

| Item | Convention Applied |
|------|-------------------|
| 컴포넌트 | 함수형 + Arrow function, Props interface 파일 상단, `export default` 하단 단독 |
| 상태 상수 | Enum 금지 — `as const` 객체 + 타입 추출 |
| 파일명 | PascalCase.tsx, 테스트는 소스 옆 `*.test.tsx` |
| 스타일 | Tailwind v4 유틸리티 + 그라데이션만 인라인 style (CLAUDE.md 토큰) |
| import | 절대 경로 `@/components/common/...` |

---

## 11. Implementation Guide

### 11.1 File Structure

```
src/types/
└── progress.ts                (신규, ~25줄 — PROGRESS_STEP_STATUS, ProgressStep) ← v0.2 분리
src/components/common/
├── StatusBadge.tsx            (신규, ~30줄)
├── StatusBadge.test.tsx       (신규, ~50줄)
├── ProgressStepItem.tsx       (신규, ~80줄 — 상태별 SVG 포함)
├── ProgressStepItem.test.tsx  (신규, ~80줄)
├── ProgressCard.tsx           (신규, ~75줄 — 타입 re-export)
└── ProgressCard.test.tsx      (신규, ~85줄)
```

### 11.2 Implementation Order (TDD)

1. [ ] `ProgressCard.tsx`에 타입·상수 골격 정의 (`PROGRESS_STEP_STATUS`, `ProgressStep`)
2. [ ] StatusBadge: 테스트(Red) → 구현(Green) → 리팩터
3. [ ] ProgressStepItem: 테스트(Red) → 구현(Green) → 리팩터
4. [ ] ProgressCard: 테스트(Red) → 구현(Green) → 리팩터
5. [ ] `npm run type-check && npm run lint && npm run test:run` 전체 통과 확인

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| 전체 (컴포넌트 3종 + 테스트) | `module-1` | 소규모 기능 — 단일 세션 구현 권장 | 15-25 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Do + Check | 전체 (`module-1`) | 20-30 |

> 신규 파일 6개·기존 코드 수정 0건의 소규모 기능이므로 세션 분할 불필요.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-19 | Initial draft — Option C (Pragmatic) 선택 반영 | 배상규 |
| 0.2 | 2026-08-20 | Do 단계 변경: 타입·상수를 `src/types/progress.ts`로 분리 (react-refresh 린트 규칙 + types/ 컨벤션) | 배상규 |
