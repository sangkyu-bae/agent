# question-card Design Document

> **Summary**: 조합형 질문지 카드 공통 컴포넌트 4종(`common/question-card/`) 설계 — 질문당 카드 1장, 라디오 행 + 직접 입력, 질문별 "▷ 제출" 순차 플로우
>
> **Project**: idt_front (React 19 + TypeScript + Vite)
> **Version**: 0.0.0
> **Author**: 배상규
> **Date**: 2026-08-20
> **Status**: Draft
> **Planning Doc**: [question-card.plan.md](../../01-plan/features/question-card.plan.md)

---

## Context Anchor

> Plan 문서에서 복사. Design→Do 핸드오프에서 전략 컨텍스트 유지.

| Key | Value |
|-----|-------|
| **WHY** | HITL 질문 카드가 도메인 전용·구식 디자인이라 목표 UI(ask.png/card2.png)와 불일치하고 재사용 불가 |
| **WHO** | 에이전트 생성 진입 화면·Fix 탭에서 clarify 질문에 답하는 KB 운영자(P2) |
| **RISK** | 백엔드 HITL 계약(`ClarificationAnswer[]`, 부분 답변 허용) 파손 — 계약은 그대로 유지해야 함 |
| **SUCCESS** | 두 사용처가 새 카드로 교체되고 기존/신규 테스트 전부 통과, 공통 컴포넌트는 agentComposer 타입 비의존 |
| **SCOPE** | 공통 컴포넌트 4종 신설 → 어댑터 없이 사용처 인라인 매핑으로 두 사용처 교체 → 기존 ClarifyQuestionCard 제거 (백엔드·타입 계약 변경 없음) |

---

## 1. Overview

### 1.1 Design Goals

- 목표 디자인(ask.png/card2.png)의 카드 3단 구조(헤더/옵션 목록/푸터) 픽셀-근사 재현
- 질문 UI를 도메인 독립 조합 단위로 분해 — `agentComposer` 타입 import 0건
- 순차 제출 플로우(제출 → 잠금 → 다음 질문)를 `QuestionCardFlow` 하나에 캡슐화해 사용처는 매핑만 담당
- 기존 HITL 왕복 계약(부분 답변 `answer=''`, 질문 에코백) 무손실 유지

### 1.2 Design Principles

- **조합 우선**: 카드 셸(`QuestionCard`)은 옵션·푸터를 슬롯(children/footer)으로 받는다. 플로우 없이 단일 카드만 쓰는 화면도 지원.
- **제어 컴포넌트**: 옵션 행·직접 입력은 상태를 갖지 않는다. 상태는 `QuestionCardFlow`(또는 사용처)가 소유.
- **네이티브 시맨틱**: 라디오는 `<input type="radio">` 기반 — RTL `getByRole('radio')`로 테스트 가능, 키보드 접근성 무료 확보.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | 기존 위치에서 리스타일 | 공통 4종 + 타입 파일 + 도메인 어댑터 | 공통 4종 + 배럴, 사용처 인라인 매핑 |
| **New Files** | 0 | ~9 | ~6 |
| **Modified Files** | 3 | 3 | 3 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Low (도메인 결합) | High | High |
| **Effort** | Low | High | Medium |
| **Risk** | Plan 확정 사항과 불일치 | 과설계(어댑터 간접층) | Low (balanced) |
| **Recommendation** | — | 사용처 3곳 이상일 때 | **선택됨** |

**Selected**: **Option C** — **Rationale**: 사용자 확정(2026-08-20 Checkpoint 3). 사용처가 2곳뿐이라 어댑터 층 없이 사용처 인라인 매핑(약 5줄)으로 충분. 도메인 매핑이 3곳 이상으로 늘면 그때 어댑터 추출.

### 2.1 Component Diagram

```
사용처 (도메인)                          공통 (도메인 비의존)
┌──────────────────────────┐   매핑   ┌─────────────────────────────────┐
│ AgentCreateEntryPage     │ ───────▶ │ QuestionCardFlow                │
│  ClarifyingQuestion[]    │  Flow    │  · 순차 노출 (currentIndex)      │
│  → FlowQuestion[]        │  Question│  · 답변 수집 (Record<id,value>) │
│  answers → Clarification │  [] 로   │  · onComplete(FlowAnswer[])     │
│  Answer[] 역매핑          │          │        │ 조합                    │
├──────────────────────────┤          │        ▼                        │
│ FixAgentPanel            │ ───────▶ │ QuestionCard (셸)               │
│  FixChatMessage.questions│          │  ├ QuestionOptionItem × N       │
│  → FlowQuestion[]        │          │  └ QuestionFreeTextOption (0~1) │
└──────────────────────────┘          └─────────────────────────────────┘
```

### 2.2 Data Flow

```
compose API ─ needs_clarification ─▶ ClarifyingQuestion[]
  ─(사용처 매핑)─▶ FlowQuestion[] ─▶ QuestionCardFlow
  ─ 질문별 [▷ 제출]/[건너뛰기] 반복 ─▶ 마지막 제출 시 onComplete(FlowAnswer[])
  ─(사용처 역매핑)─▶ ClarificationAnswer[] ─▶ compose API 재호출
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| QuestionCardFlow | QuestionCard, QuestionOptionItem, QuestionFreeTextOption | 조합·오케스트레이션 |
| QuestionCard | (없음 — React만) | 카드 셸 |
| 사용처 2곳 | question-card 배럴, agentComposer 타입 | 도메인 ↔ 제네릭 매핑 |
| **금지** | question-card → `@/types/agentComposer` | 도메인 비의존 (Plan FR-10) |

---

## 3. Data Model (제네릭 Props 타입)

> 위치: `src/components/common/question-card/types.ts` (폴더 로컬 — `src/types/`가 아님, Option C)

```typescript
/** 질문 1건 — 도메인 비의존 제네릭 모델 */
export interface FlowQuestion {
  id: string;
  title: string;              // 카드 헤더에 표시되는 질문 텍스트
  options: string[];          // 선택지 (빈 배열 허용 — 직접 입력만 있는 질문)
  allowFreeText: boolean;     // true면 마지막 행에 직접 입력 라디오 추가
  freeTextLabel?: string;     // 기본: '직접 입력 (원하는 내용을 자유롭게 작성)'
}

/** 답변 1건 — value===''는 무응답(건너뛰기) */
export interface FlowAnswer {
  id: string;                 // FlowQuestion.id
  value: string;
}
```

**도메인 매핑 (사용처 인라인, 약 5줄):**

```typescript
// ClarifyingQuestion → FlowQuestion
{ id: q.id, title: q.question, options: q.options, allowFreeText: q.allow_free_text }
// FlowAnswer → ClarificationAnswer (question 에코백은 사용처가 원본에서 복원)
{ question_id: a.id, question: byId[a.id].question, answer: a.value }
```

---

## 4. API Specification

**N/A — 백엔드 계약 불변.** compose API(`POST /api/v1/agents/compose` 계열)의 요청/응답 스키마(`ClarifyingQuestion`, `ClarificationAnswer`, `clarification_round`)는 변경하지 않는다. 검증은 기존 MSW 핸들러 기반 통합 테스트로 수행 (§8).

---

## 5. UI/UX Design

### 5.1 Component API

#### `QuestionCard` — 카드 셸

```typescript
interface QuestionCardProps {
  title: string;              // 질문 텍스트 (헤더)
  locked?: boolean;           // true: 잠금 시각 상태 (opacity 감쇠 + 완료 배지)
  compact?: boolean;          // Fix 탭 좁은 폭용 축소 variant
  children: ReactNode;        // 옵션 행 목록
  footer?: ReactNode;         // 제출/건너뛰기 행 (없으면 푸터 미렌더)
}
```

#### `QuestionOptionItem` — 라디오 행 (제어)

```typescript
interface QuestionOptionItemProps {
  name: string;               // radio group name (질문 id)
  label: string;
  selected: boolean;
  disabled?: boolean;
  compact?: boolean;
  onSelect: () => void;
}
```

- 구현: `<label>` 래핑 + 시각적으로 숨긴 `<input type="radio">` + 커스텀 라디오 서클. `getByRole('radio', { name })` 쿼리 가능.

#### `QuestionFreeTextOption` — 직접 입력 라디오 행 (제어)

```typescript
interface QuestionFreeTextOptionProps {
  name: string;
  label?: string;             // 기본 '직접 입력 (원하는 내용을 자유롭게 작성)'
  selected: boolean;
  disabled?: boolean;
  compact?: boolean;
  value: string;              // 입력 텍스트
  inputAriaLabel?: string;    // 확장 입력 aria-label — 기본 '직접 입력' (Analysis G6)
  onSelect: () => void;
  onChange: (value: string) => void;
}
```

- `selected=true`일 때만 행 아래로 텍스트 입력이 확장(autoFocus), 해제 시 접힘. 입력값은 유지(재선택 시 복원).
- Flow는 `inputAriaLabel`에 `` `${title} 직접 입력` ``을 전달해 여러 카드 공존 시 접근성 이름 충돌을 피한다.

#### `QuestionCardFlow` — 순차 오케스트레이터

```typescript
interface QuestionCardFlowProps {
  questions: FlowQuestion[];
  disabled?: boolean;         // isPending — 전 카드 조작 불가
  completed?: boolean;        // 외부 완료 상태(answered) — 전체 잠금 + 완료 배지
  compact?: boolean;
  header?: ReactNode;         // planSummary 등 플로우 상단 슬롯
  onComplete: (answers: FlowAnswer[]) => void;  // 마지막 질문 제출 시 1회 호출
}
```

**내부 상태/동작 (Design §5.2 플로우 규칙):**

| 규칙 | 내용 |
|------|------|
| F1 | 로컬 상태: `currentIndex`, `answers: Record<id, string>`, `freeText: Record<id, string>` — 전역 스토어 미사용 |
| F2 | 카드 노출: `index ≤ currentIndex`인 질문만 렌더. 과거 카드는 `locked` (선택 결과 표시, 조작 불가) |
| F3 | 답변 값: 직접 입력 라디오 선택 시 `freeText[id].trim()`, 아니면 선택 옵션. 직접 입력 선택 + 빈 텍스트면 미답변 취급 |
| F4 | [▷ 제출] 활성 조건: 옵션 선택됨 또는 (직접 입력 선택 + 텍스트 비어있지 않음). 그 외 disabled |
| F5 | [건너뛰기] 클릭: `answers[id] = ''` 로 확정 후 전진 (Plan FR-07). 이때 라디오 선택도 해제해 잠금 카드에 오해 소지를 남기지 않는다 |
| F6 | 제출/건너뛰기 → `currentIndex`가 마지막이면 `onComplete(questions.map(q => ({id, value: answers[q.id] ?? ''})))`, 아니면 `currentIndex + 1` |
| F7 | `onComplete`는 1회만 발화 (제출 후 내부 `done` 플래그, `completed` prop과 별개) |
| F8 | `completed=true`로 마운트되면(Fix 탭 answered 메시지 재렌더) 모든 카드를 locked로 표시 — 로컬 답변 상태가 없으므로 선택 표시는 생략, "✓ 답변 완료" 배지만 |
| F9 | `disabled=true`(isPending) 동안 모든 조작 차단, 제출 버튼 스피너 없이 disabled 처리(사용처가 상위에서 pending 표시) |
| F10 | 사용처 책임: HITL 왕복이 폐기되면(예: Fix 탭에서 새 문장 전송으로 `pendingClarify=null`) 화면에 남은 미답변 질문 카드를 `disabled`로 비활성화한다 — 답해도 전송되지 않는데 내부 `done` 잠금이 "답변 완료"로 오표시하는 것을 차단 (Analysis G1) |

### 5.2 Screen Layout (card2.png 기준)

```
┌─ QuestionCard ──────────────────────────────────────┐
│ 💬 이 에이전트는 어떤 일을 하는 에이전트인가요?          │ ← 헤더 (아이콘+질문)
├─────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────┐ │
│ │ ○ 정보를 검색하고 요약해 주는 에이전트              │ │ ← QuestionOptionItem
│ └─────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────┐ │
│ │ ○ 질문에 직접 답변해 주는 에이전트                 │ │
│ └─────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────┐ │
│ │ ○ 직접 입력 (원하는 내용을 자유롭게 작성)          │ │ ← QuestionFreeTextOption
│ │ ┌─────────────────────────────────────────────┐ │ │
│ │ │ (선택 시 확장되는 텍스트 입력)                 │ │ │
│ │ └─────────────────────────────────────────────┘ │ │
│ └─────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────┤
│ 건너뛰기                                  [ ▷ 제출 ] │ ← 푸터
└─────────────────────────────────────────────────────┘
        (제출 → 카드 잠금, 아래에 다음 질문 카드 등장)
```

### 5.3 Visual Spec (CLAUDE.md 디자인 토큰 매핑)

| 요소 | 클래스/스타일 |
|------|--------------|
| 카드 컨테이너 | `rounded-2xl border border-zinc-200 bg-violet-50/30` (compact: `rounded-xl`) |
| 카드 헤더 | `flex items-center gap-2.5 px-5 py-4` / 질문 `text-[15px] font-semibold text-zinc-900` (compact: `px-4 py-3`, `text-[13.5px]`) |
| 말풍선 아이콘 | 연보라 채움 SVG `h-5 w-5 text-violet-300` (fill) |
| 헤더-본문 구분 | 헤더에 `border-b border-zinc-200/70` |
| 옵션 영역 | `space-y-2.5 px-5 py-4` (compact: `space-y-2 px-4 py-3`) |
| 옵션 행 (기본) | `flex w-full items-center gap-3 rounded-xl border border-zinc-200 bg-white px-4 py-3.5 text-[14px] text-zinc-700 transition-colors hover:border-violet-300 cursor-pointer` (compact: `px-3 py-2.5 text-[13px]`) |
| 옵션 행 (선택) | `border-violet-400 bg-violet-50/60 text-zinc-900` |
| 라디오 서클 | 기본 `h-[18px] w-[18px] rounded-full border-2 border-zinc-300 bg-white` / 선택 `border-violet-500` + 내부 dot `h-2 w-2 rounded-full bg-violet-500` |
| 직접 입력 확장 필드 | `mt-2 block w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-[13.5px] placeholder-zinc-400 outline-none focus:border-violet-400` |
| 푸터 | `flex items-center justify-between border-t border-zinc-200/70 px-5 py-3.5` |
| 제출 버튼 (활성) | `flex items-center gap-1.5 rounded-xl bg-violet-600 px-5 py-2.5 text-[13.5px] font-medium text-white transition-all hover:bg-violet-700 active:scale-95` + ▷(play) 아이콘 |
| 제출 버튼 (비활성) | `bg-violet-300 cursor-not-allowed` (card2.png의 연보라 = 미선택 비활성 상태로 해석) |
| 건너뛰기 | `text-[12.5px] text-zinc-400 transition-colors hover:text-violet-600` |
| 잠금 카드 | 컨테이너에 `opacity-70` + 푸터를 "✓ 답변 완료" 배지(`text-[12.5px] font-medium text-violet-500`)로 교체 |

> compact variant 공통 규칙: 표의 괄호 값이 없는 요소(푸터·제출 버튼·건너뛰기)는 기본 토큰을 그대로 쓰고, 카드 라운드는 `rounded-xl`, 패딩은 한 단계씩 축소(px-5→px-4, py-4→py-3, py-3.5→py-2.5)한다.

### 5.4 Page UI Checklist

#### 공통 — QuestionCardFlow (두 사용처 동일)

- [ ] 카드 헤더: 말풍선 아이콘 + 질문 텍스트
- [ ] 옵션: 질문의 `options` 전부 전체 폭 라디오 행으로 표시
- [ ] 직접 입력: `allowFreeText` 질문의 마지막 행에 "직접 입력 (원하는 내용을 자유롭게 작성)" 라디오, 선택 시 텍스트 입력 확장
- [ ] 라디오 단일 선택: 같은 카드에서 하나만 선택 가능 (`getByRole('radio')` 그룹)
- [ ] 푸터: [▷ 제출] 버튼(우측) + [건너뛰기](좌측)
- [ ] 제출 비활성: 미선택(또는 직접 입력 빈 텍스트) 시 연보라 비활성
- [ ] 순차 노출: 최초 질문 1개만 표시 → 제출/건너뛰기 시 다음 카드 추가 노출
- [ ] 잠금 카드: 제출된 카드는 선택 결과 유지 + "✓ 답변 완료" + 조작 불가
- [ ] 마지막 제출: `onComplete` 1회 호출, 미답변 질문은 `value=''`

#### AgentCreateEntryPage (/agent-builder/new)

- [ ] planSummary가 있으면 플로우 상단(header 슬롯)에 표시
- [ ] "건너뛰고 초안 만들기" 버튼 유지 — 클릭 시 전 질문 `answer=''` 즉시 제출 (플로우 외부, 기존 동작)
- [ ] isPending 중 카드 전체 + 건너뛰기 버튼 비활성
- [ ] MAX_CLARIFY_ROUNDS 초과 시 기존 실패 카드 동작 유지 (플로우와 무관)

#### FixAgentPanel (Fix 탭 채팅)

- [ ] `FixChatMessage.questions` 메시지가 compact 카드 플로우로 렌더
- [ ] `answered` 메시지는 `completed` 잠금 상태로 표시
- [ ] 새 문장 전송으로 왕복이 폐기된 스테일 질문 카드는 비활성 (F10)
- [ ] 채팅 폭에서 옵션 행 줄바꿈/오버플로 없음 (compact variant)

---

## 6. Error Handling

| 상황 | 처리 |
|------|------|
| `questions`가 빈 배열 | 플로우 미렌더 (null 반환) — 사용처 가드와 이중 방어 |
| 직접 입력 선택 후 텍스트 삭제 | 제출 버튼 비활성으로 회귀 (F4) |
| compose API 오류 | 사용처 기존 처리 유지 (`ComposeFailureCard` / 채팅 오류 메시지) — 플로우는 관여하지 않음 |
| 제출 중복 클릭 | `done` 플래그 + disabled로 `onComplete` 1회 보장 (F7) |

---

## 7. Security Considerations

- [x] 자유 입력 텍스트는 React 기본 이스케이프로 렌더 (`dangerouslySetInnerHTML` 미사용)
- [x] 입력값은 compose API로만 전달 — 로컬 저장/로깅 없음
- [ ] 그 외 인증/전송 보안: 기존 authClient 경로 그대로 (변경 없음)

---

## 8. Test Plan

> TDD: 컴포넌트 코드 + 테스트 = 1세트 (Do 단계에서 Red→Green→Refactor)

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| Unit | question-card 4종 컴포넌트 | Vitest + RTL | Do |
| Integration | AgentCreateEntryPage / FixAgentPanel HITL 왕복 | Vitest + RTL + MSW | Do |
| L1 API | N/A (백엔드 계약 불변) | — | — |

### 8.2 Unit Test Scenarios (`src/components/common/question-card/*.test.tsx`)

| # | 컴포넌트 | 시나리오 | 기대 결과 |
|---|----------|----------|-----------|
| 1 | QuestionOptionItem | 클릭 | `onSelect` 호출, `getByRole('radio')` checked 반영 |
| 2 | QuestionOptionItem | disabled 클릭 | `onSelect` 미호출 |
| 3 | QuestionFreeTextOption | 선택 | 텍스트 입력 확장 표시 |
| 4 | QuestionFreeTextOption | 미선택 | 텍스트 입력 미표시, 기존 value 보존 |
| 5 | QuestionCard | locked | "✓ 답변 완료" 배지, footer 미표시 |
| 6 | QuestionCardFlow | 초기 렌더 | 첫 질문 카드만 표시 |
| 7 | QuestionCardFlow | 미선택 상태 | 제출 버튼 disabled |
| 8 | QuestionCardFlow | 옵션 선택 → 제출 | 카드 잠금 + 다음 질문 노출 |
| 9 | QuestionCardFlow | 직접 입력 텍스트 → 제출 | 답변 값 = 입력 텍스트 |
| 10 | QuestionCardFlow | 건너뛰기 | 해당 답변 `''` + 다음 질문 노출 |
| 11 | QuestionCardFlow | 마지막 질문 제출 | `onComplete` 1회, 전체 답변 배열(무응답 `''` 포함) |
| 12 | QuestionCardFlow | `completed=true` | 전 카드 잠금 + 완료 배지, 조작 불가 |
| 13 | QuestionCardFlow | `disabled=true` | 라디오/버튼 전부 비활성 |
| 14 | QuestionCardFlow | 빈 questions | 미렌더 |

### 8.3 Integration Test Scenarios (MSW)

| # | 대상 | 시나리오 | 성공 기준 |
|---|------|----------|-----------|
| 1 | AgentCreateEntryPage | compose → needs_clarification → 질문별 제출 → 마지막 제출 | compose 재호출 request body의 `clarification_answers`가 `{question_id, question, answer}[]` 계약 일치, round 증가 |
| 2 | AgentCreateEntryPage | "건너뛰고 초안 만들기" | 전 질문 `answer=''`로 재호출 |
| 3 | AgentCreateEntryPage | planSummary 표시 | header 슬롯에 렌더 |
| 4 | FixAgentPanel | questions 메시지 렌더 + 답변 제출 | `handleAnswerSubmit` 호출, answered 후 잠금 표시 |
| 5 | 회귀 | MAX_CLARIFY_ROUNDS 초과 | clarify_exhausted 실패 카드 (기존 테스트 유지) |

### 8.4 Seed Data Requirements

MSW 핸들러 픽스처: 질문 2건(옵션 3개+직접입력 / 옵션 0개+직접입력만) needs_clarification 응답 — 순차 플로우와 free-text-only 케이스를 모두 커버.

---

## 9. Clean Architecture

### 9.1 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| QuestionCard / OptionItem / FreeTextOption / Flow + types.ts | Presentation (공통) | `src/components/common/question-card/` |
| 도메인 매핑 (인라인) | Presentation (도메인) | `src/pages/AgentCreateEntryPage/index.tsx`, `src/components/agent-builder/fix/FixAgentPanel.tsx` |
| ClarifyingQuestion / ClarificationAnswer | Domain | `src/types/agentComposer.ts` (불변) |
| compose 호출 | Application | `src/hooks/useAgentComposer.ts` (불변) |

### 9.2 Dependency Rules

```
사용처(도메인 Presentation) ──▶ common/question-card (제네릭 Presentation)
사용처 ──▶ types/agentComposer (Domain)
common/question-card ──X──▶ types/agentComposer   ← 금지 (FR-10, 리뷰 체크포인트)
```

---

## 10. Coding Convention Reference

| Item | Convention Applied |
|------|-------------------|
| 컴포넌트 | Arrow function + `export default` 하단 단독, Props `interface` 상단 |
| 파일 | PascalCase.tsx, 폴더 kebab-case (`question-card/`), 배럴 `index.ts` |
| 스타일 | Tailwind 클래스, CLAUDE.md violet 토큰 (§5.3) |
| 테스트 | 소스 옆 `*.test.tsx`, 통합은 기존 페이지 테스트 파일 갱신 |
| 상태 | 로컬 `useState` (전역 스토어 미사용 — 일시적 UI 상태) |
| 상수 export | `.tsx` 컴포넌트 파일에서 런타임 상수 export 금지 (`react-refresh/only-export-components`). 직접 입력 기본 레이블은 default parameter 또는 파일 내 비export const로 처리. 타입은 순수 타입 파일 `types.ts`(.ts)에서 export |

---

## 11. Implementation Guide

### 11.1 File Structure

```
src/components/common/question-card/        [신규]
├── types.ts                    # FlowQuestion, FlowAnswer
├── QuestionCard.tsx            # 셸 (헤더/children/footer, locked/compact)
├── QuestionOptionItem.tsx      # 라디오 행
├── QuestionFreeTextOption.tsx  # 직접 입력 라디오 행
├── QuestionCardFlow.tsx        # 순차 오케스트레이터
├── index.ts                    # 배럴 (Flow + 타입 + 개별 컴포넌트 export)
├── QuestionCardFlow.test.tsx   # §8.2 #6-14
└── QuestionCardParts.test.tsx  # §8.2 #1-5

수정:
├── src/pages/AgentCreateEntryPage/index.tsx       # ClarifyQuestionCard → QuestionCardFlow 매핑
├── src/pages/AgentCreateEntryPage/index.test.tsx  # 셀렉터 갱신 + §8.3 #1-3
├── src/components/agent-builder/fix/FixAgentPanel.tsx        # 교체 (compact)
└── src/components/agent-builder/fix/FixAgentPanel.test.tsx   # 셀렉터 갱신 + §8.3 #4

삭제:
├── src/components/agent-builder/fix/ClarifyQuestionCard.tsx
└── src/components/agent-builder/fix/ClarifyQuestionCard.test.tsx  # 시나리오는 §8.2로 이관
```

### 11.2 Implementation Order

1. [ ] `types.ts` + `QuestionOptionItem` / `QuestionFreeTextOption` / `QuestionCard` (TDD: §8.2 #1-5)
2. [ ] `QuestionCardFlow` 순차 로직 (TDD: §8.2 #6-14)
3. [ ] `AgentCreateEntryPage` 교체 + 통합 테스트 (§8.3 #1-3, 회귀 #5)
4. [ ] `FixAgentPanel` 교체(compact) + 통합 테스트 (§8.3 #4)
5. [ ] `ClarifyQuestionCard` 삭제 + 참조 0건 확인 + lint/type-check/전체 테스트

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| 공통 컴포넌트 | `module-1` | question-card 4종 + types + 배럴 + 단위 테스트 (11.2의 1-2) | 15-20 |
| 사용처 교체 | `module-2` | 두 사용처 교체 + 통합 테스트 + 구 컴포넌트 삭제 (11.2의 3-5) | 15-20 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Do | `--scope module-1` | 15-20 |
| Session 2 | Do | `--scope module-2` | 15-20 |
| Session 3 | Check + Report | 전체 | 20-30 |

> 규모가 작아 한 세션(`/pdca do question-card`)에 module-1+2를 함께 진행해도 무방.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-20 | 최초 작성 — Option C(실용 균형) 선택 반영, 플로우 규칙 F1-F9 정의 | 배상규 |
