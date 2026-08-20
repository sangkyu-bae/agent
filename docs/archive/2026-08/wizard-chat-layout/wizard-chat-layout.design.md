# wizard-chat-layout Design Document

> **Summary**: /agent-builder/new 위저드를 채팅 트랜스크립트형 레이아웃으로 전환 — C안(실용 절충): 파이프라인 상태 머신 유지 + 라운드 이력 배열 + 2-모드 레이아웃 셸
>
> **Project**: idt_front (sangplusbot)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-08-20
> **Status**: Draft
> **Planning Doc**: [wizard-chat-layout.plan.md](../../01-plan/features/wizard-chat-layout.plan.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 대화형 파이프라인인데 폼형 UI라 진행 맥락(이전 질문·답변)이 화면에서 사라짐 + 콘텐츠가 길어지면 `justify-center` 오버플로로 화면이 깨짐 |
| **WHO** | P2 (KB 운영자 / 에이전트 소유자) — 에이전트를 자연어로 생성하는 사용자 |
| **RISK** | 단계 교체형 상태 머신을 누적형 트랜스크립트로 바꿀 때 스테일 카드/잠금 로직 회귀 |
| **SUCCESS** | 기존 위저드 기능(4단계 전이·무저장 계약·스튜디오 핸드오프) 전부 유지 + 신규 레이아웃 테스트 통과 |
| **SCOPE** | 프론트 단독 — `AgentCreateEntryPage` 및 하위 컴포넌트 레이아웃 재구성. 백엔드/파이프라인 계약 변경 없음 |

---

## 1. Overview

### 1.1 Design Goals

1. **채팅 멘탈 모델**: 요청 → 진행 → 질문 → 도구 → 프롬프트가 하나의 트랜스크립트에 시간순으로 누적된다. 이전 라운드 질문·답변은 잠긴 카드로 남는다.
2. **2-모드 레이아웃**: 첫 화면은 세로 중앙(`centered`), 첫 전송 즉시 하단 고정 입력창(`chat`)으로 전환.
3. **오버플로 버그 구조적 해결 (FR-15)**: `justify-center`를 제거하고 overflow-safe 패턴으로 교체. 입력창은 스크롤 영역 밖 형제 요소 — 겹침·잘림이 구조적으로 불가능하게.
4. **회귀 최소화**: `useAgentPipelineStream` 훅, `dispatch`/`applyResult` 전이 로직, 무저장 계약, 스튜디오 핸드오프는 손대지 않는다.

### 1.2 Design Principles

- **검증된 로직 불변**: 파이프라인 왕복(요청 바디 조립·상태 전이)은 기존 코드 그대로. 변경은 "무엇을 어디에 렌더하는가"에 국한.
- **재사용 우선**: 질문 카드는 공통 `QuestionCardFlow`의 `completed` 잠금을 그대로 활용(신규 카드 구현 금지 — common-card-components 위키).
- **파생 상태 우선**: `mode`는 별도 state가 아니라 기존 상태에서 파생. 새 상태는 라운드 이력(`rounds`) 하나만 추가.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | index.tsx 내부 재배치만 | 트랜스크립트 아이템 모델 + 전용 리듀서 훅 | 상태 머신 유지 + rounds 이력 + 레이아웃 셸 분리 |
| **New Files** | 0 | 4~5 | 2 (WizardShell + 테스트) |
| **Modified Files** | 3 | 6+ | 5 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Medium (index.tsx ~500줄) | High | High |
| **Effort** | Low | High | Medium |
| **Risk** | Low | Medium (전이 로직 재작성) | Low |
| **Recommendation** | 핫픽스 | 자유 채팅(멀티턴) 확장 확정 시 | **Default choice** |

**Selected**: **Option C** — **Rationale**: 검증된 dispatch/applyResult를 보존해 회귀 면적을 최소화하면서, 라운드 이력과 레이아웃 셸만 추가해 FR 전부(특히 FR-07 이력 누적, FR-15 오버플로)를 충족한다. (Checkpoint 3 사용자 확정, 2026-08-20)

### 2.1 Component Diagram

```
AgentCreateEntryPage (index.tsx)
│  상태: WizardState(+rounds), step, input, pendingState
│  로직: dispatch / applyResult / handle* (기존 유지)
│
├─ WizardShell (신규)                      ← 2-모드 레이아웃 + 스크롤 + 자동 스크롤
│   ├─ mode='centered': 스크롤 바디 > my-auto 래퍼 > {children}
│   └─ mode='chat':     스크롤 바디(트랜스크립트) + 하단 고정 {composer}
│
├─ [centered children]
│   ├─ EntryHero                           (무변경)
│   ├─ DescriptionComposer variant=centered (소폭 수정)
│   ├─ EntryActionCards                    (무변경)
│   └─ PipelineUnavailableCard             (무변경, 킬스위치 시)
│
└─ [chat transcript children — 시간순 누적]
    ├─ RequestBubble (index.tsx 내 인라인 — 유저 메시지 버블)
    ├─ WizardProgress + 안내 문구           (무변경)
    ├─ IntentStep × rounds.length          (라운드별 1개, 지난 라운드 잠김)
    ├─ ToolsStep (+locked prop)            (소폭 수정)
    ├─ PromptStep                          (무변경)
    └─ WizardFailureCard                   (무변경)
```

### 2.2 Data Flow

```
[centered] 입력 → handleSubmitDescription
  → setState(next: userRequest 확정)          ← 신규: 즉시 커밋 (버블 즉시 렌더 + chat 모드 전환)
  → dispatch(stop_after=tools) → isPending
  → applyResult:
      need_input      → rounds.push({round, questions, answered:false}) → 카드 추가
      tools_proposed  → 최종 rounds 잠금 → ToolsStep 추가
      prompt_ready    → ToolsStep locked → PromptStep 추가
  → 각 응답/카드 추가 시 하단 자동 스크롤 (near-bottom 가드)
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| WizardShell | 없음 (레이아웃 전용, ReactNode 슬롯) | 2-모드 레이아웃·스크롤·자동 스크롤 소유 |
| index.tsx | WizardShell, 기존 하위 컴포넌트 전부 | 전이 로직 + 트랜스크립트 조립 |
| IntentStep | QuestionCardFlow (`completed`/`disabled`) | 라운드별 잠금 카드 — **공통 컴포넌트 무수정** |
| ToolsStep | (신규 `locked` prop) | prompt 단계 진입 후 읽기 전용 이력 표시 |

---

## 3. Data Model

### 3.1 Entity Definition

```typescript
// index.tsx 로컬 — 라운드 이력 (FR-07). 런타임 상수 아님(타입만)이므로 페이지 로컬 허용.
interface WizardRound {
  round: number;                  // 서버 echo 라운드 번호 — IntentStep key 재사용
  questions: PipelineQuestion[];  // 이 라운드에 받은 질문들
  answered: boolean;              // 답변/건너뛰기 완료 → 카드 잠금
}

// WizardState 변경분 (기존 필드 유지)
interface WizardState {
  // ... 기존 필드 전부 유지 ...
  rounds: WizardRound[];          // 신규 — 교체가 아닌 누적
  // questions / answered 필드는 rounds 로 대체·제거
  //   questions → rounds[last].questions
  //   answered  → rounds[last].answered
}
```

### 3.2 파생 상태 — 모드 결정

```typescript
// 별도 useState 금지 — 파생으로만.
// handleSubmitDescription 이 state.userRequest 를 즉시 커밋하므로,
// 첫 전송 직후(응답 전)에도 chat 모드로 전환되고 요청 버블이 바로 보인다.
// 첫 요청이 에러로 끝나도 userRequest 가 남아 chat 모드에서 실패 카드를 보여준다.
const mode: 'centered' | 'chat' =
  state.userRequest !== '' ? 'chat' : 'centered';
```

`handleRestart`(및 ToolsStep [처음부터])는 `state = EMPTY`로 되돌리므로 자동으로 `centered` 복귀 (FR-12).

### 3.3 applyResult 변경분

| status | 기존 | 변경 |
|--------|------|------|
| `need_input` | `questions` 교체, `answered=false` | `rounds: [...prev.rounds, { round, questions, answered: false }]` — **push** |
| `tools_proposed` | `questions=[]`, `answered=true` | `rounds`의 마지막 항목 `answered=true` 잠금 (이력 유지) |
| `prompt_ready` | (변경 없음) | (변경 없음 — ToolsStep 은 `step==='prompt'` 파생으로 잠금) |

`handleAnswers`: 답변 병합 로직(누적 에코백) 무변경. 추가로 마지막 라운드 `answered=true` 마킹.

---

## 4. API Specification

**변경 없음.** `POST /api/v1/agent-pipeline` 요청/응답 계약, `useAgentPipelineStream` 훅, 무저장 계약(스튜디오 [저장]에서만 DB 반영) 전부 그대로. (Plan §2.2 Out of Scope)

---

## 5. UI/UX Design

### 5.1 Screen Layout

#### centered 모드 (첫 화면 / 킬스위치)

```
┌──────────────────────────────────────┐
│ (헤더바 없음 — FR-01)                  │
│ ┌─ 스크롤 바디 (flex-1, overflowY) ──┐ │
│ │  ┌─ my-auto 래퍼 ← FR-15 핵심 ──┐ │ │
│ │  │  EntryHero (아이콘+안내)      │ │ │
│ │  │  DescriptionComposer (중앙)  │ │ │
│ │  │  EntryActionCards (2카드)    │ │ │
│ │  └─────────────────────────────┘ │ │
│ └──────────────────────────────────┘ │
└──────────────────────────────────────┘
```

> **FR-15**: `justify-center` 대신 내부 래퍼에 `my-auto`. auto 마진은 콘텐츠가
> 컨테이너보다 커지면 0으로 붕괴 → 짧으면 중앙, 길면 일반 스크롤로 자연 전환.
> 킬스위치(unavailable)도 이 모드에서 EntryHero + PipelineUnavailableCard (FR-13).

#### chat 모드 (첫 전송 이후)

```
┌──────────────────────────────────────┐
│ ┌─ 트랜스크립트 스크롤 (flex-1) ──────┐ │
│ │            ┌──────────────────┐   │ │
│ │            │ 요청 메시지 (버블)  │   │ │  ← 우측 정렬, 다크 그라데이션
│ │  ┌ 진행 상황 (WizardProgress) ┐   │ │
│ │  ┌ 질문 카드 라운드 1 (잠김) ──┐   │ │
│ │  ┌ 질문 카드 라운드 2 (활성) ──┐   │ │  ← 아래로 append = 위로 쌓임
│ │  ┌ 도구 카드 / 프롬프트 카드 ──┐   │ │
│ │  ┌ 실패 카드 (에러 시) ───────┐   │ │
│ │  (bottomAnchor — 자동 스크롤)     │ │
│ ├──────────────────────────────────┤ │
│ │ DescriptionComposer (하단 고정,   │ │  ← 스크롤 영역 밖 형제 요소
│ │  disabled + 안내 placeholder)     │ │     → 겹침 구조적 불가
│ └──────────────────────────────────┘ │
└──────────────────────────────────────┘
```

콘텐츠 최대 폭: 두 모드 모두 `max-w-[760px] mx-auto` 유지 (채팅/폼 기준 max-w-3xl 계열).

### 5.2 User Flow

```
진입(centered) ─ 설명 입력 → 전송
  → chat 전환: 요청 버블 + 진행바 표시
  → [need_input] 질문 카드 라운드 1 → 답변 → (라운드 2 …최대 2회, 지난 카드 잠긴 채 유지)
  → [tools_proposed] 도구 카드 → 선택 조정 → 확정
  → [prompt_ready] 도구 카드 잠김 + 프롬프트 카드 → 편집/재생성 → [저장하러 가기] → 스튜디오
  분기: 에러 → 실패 카드(재시도/직접 만들기) · [처음부터] → centered 복귀
```

### 5.3 Component List

| Component | Location | Responsibility | 변경 |
|-----------|----------|----------------|------|
| WizardShell | `src/pages/AgentCreateEntryPage/components/WizardShell.tsx` | 2-모드 레이아웃, 스크롤 컨테이너, near-bottom 자동 스크롤 | **신규** |
| AgentCreateEntryPage | `index.tsx` | 헤더바 제거, rounds 이력, 트랜스크립트 조립, 요청 버블 인라인 렌더 | 수정 |
| DescriptionComposer | 동일 | `variant: 'centered' \| 'chat'` — chat: disabled + placeholder "질문 카드에 답하면 다음 단계로 진행됩니다" (FR-08) | 수정 |
| IntentStep | 동일 | props 의미 유지 — 라운드별 인스턴스로 렌더, 지난 라운드 `answered=true`·skip 버튼 숨김 | 소폭 수정 |
| ToolsStep | 동일 | `locked?: boolean` 추가 — 토글 disabled + 하단 버튼 숨김 + "선택 완료" 배지 | 수정 |
| EntryHero / EntryActionCards / WizardProgress / PromptStep / WizardFailureCard / PipelineUnavailableCard | 동일 | 무변경 (노출 조건만 index.tsx 에서 변경) | — |

#### WizardShell 계약

```typescript
interface WizardShellProps {
  mode: 'centered' | 'chat';
  /** chat 모드에서 하단 고정 슬롯. centered 모드에서는 렌더하지 않는다. */
  composer?: ReactNode;
  /** 자동 스크롤 트리거 — 트랜스크립트 항목 수 등 파생값. 바뀔 때 하단 근처(<120px)면 스크롤. */
  scrollKey?: unknown;
  children: ReactNode;
}
```

- 루트: `display:flex; flexDirection:column; height:100%; overflow:hidden` (인라인 스타일 — CLAUDE.md 레이아웃 규칙)
- 스크롤 바디: `flex:1; overflowY:auto` — centered 는 내부 `min-h-full flex` + 자식 `my-auto`, chat 은 일반 상단 정렬
- 자동 스크롤: 컨테이너 `scrollTop` 기준 near-bottom(≤120px)일 때만 `scrollTo(bottom)` — 사용자가 위를 보는 중이면 끌어내리지 않는다 (Plan 리스크 대응)

#### 요청 버블 (FR-05, index.tsx 인라인)

```tsx
<div className="flex justify-end">
  <div className="max-w-[85%] rounded-2xl rounded-br-sm px-5 py-3.5 text-[15px] leading-[1.65] text-white"
       style={{ background: 'linear-gradient(135deg, #2d2d2d 0%, #1a1a1a 100%)' }}>
    <p className="whitespace-pre-wrap">{state.userRequest}</p>
  </div>
</div>
```

### 5.4 Page UI Checklist

#### /agent-builder/new — centered 모드

- [ ] 헤더바 부재: "에이전트 만들기" 타이틀·[취소] 버튼이 DOM에 없음 (FR-01, FR-11)
- [ ] EntryHero: 보라 그라데이션 아이콘 + "생성하려는 에이전트에 대해 알려주세요" + 보조 문구 (FR-02)
- [ ] DescriptionComposer(centered): textarea(1000자 제한), Enter 전송/Shift+Enter 줄바꿈 안내, 전송(▷) 버튼
- [ ] EntryActionCards: [에이전트 직접 만들기](활성, 클릭 → 스튜디오 blank), [에이전트 가져오기](disabled, "준비 중") (FR-02)
- [ ] 세로 중앙 정렬이되 `justify-center` 미사용 — `my-auto` 패턴 (FR-15)
- [ ] 킬스위치: EntryHero + PipelineUnavailableCard, 입력창·액션카드 미노출 (FR-13)

#### /agent-builder/new — chat 모드

- [ ] 첫 전송 즉시 전환: 요청 버블(우측 정렬, 다크 그라데이션, 원문 유지) (FR-03, FR-05)
- [ ] EntryHero·EntryActionCards 미노출 (FR-04)
- [ ] WizardProgress: 5단계 고정 + "마지막 두 단계는 스튜디오에서 [저장]을 누르면 완료됩니다" 문구 (FR-06)
- [ ] 질문 카드: 라운드별 누적 — 라운드 2 진행 중에도 라운드 1 카드가 잠긴 상태로 DOM에 존재 (FR-07)
- [ ] 라운드 안내: "남은 질문 라운드 N회" 표기, [건너뛰고 계속하기]는 활성 라운드에만
- [ ] ToolsStep: 추천 도구 체크 목록, [이 도구로 확정], [처음부터] — prompt 단계 진입 후 locked(토글 disabled·버튼 숨김·"선택 완료" 배지) (FR-09)
- [ ] PromptStep: 프롬프트 편집 textarea, [다시 생성], [이전 단계], [저장하러 가기] (FR-09, FR-14)
- [ ] WizardFailureCard: 에러 시 트랜스크립트 하단 — [재시도], [직접 만들기] (FR-09)
- [ ] 하단 고정 입력창: 스크롤 영역 밖 형제, disabled, placeholder "질문 카드에 답하면 다음 단계로 진행됩니다" (FR-08)
- [ ] 새 항목 추가 시 near-bottom 조건부 자동 스크롤 (FR-10)
- [ ] 긴 트랜스크립트(작은 뷰포트)에서 최상단 요청 버블까지 스크롤 도달 가능 (FR-15)
- [ ] [처음부터] → 확인 다이얼로그 → centered 복귀 + 트랜스크립트 초기화 (FR-12)
- [ ] `beforeunload` 이탈 경고 유지 — description 단계 제외 (FR-11)

---

## 6. Error Handling

| 상황 | 처리 | 변경 여부 |
|------|------|----------|
| 파이프라인 HTTP/스트림 오류 | WizardFailureCard 를 트랜스크립트 마지막 항목으로 렌더 — [재시도]는 기존 handleRetry 분기 재사용 | 위치만 변경 |
| 첫 요청부터 실패 | userRequest 즉시 커밋 덕분에 chat 모드 유지 — 요청 버블 + 실패 카드가 함께 보임 (centered 로 튕기지 않음) | **신규 보장** |
| 킬스위치(DISABLED) | centered 모드에서 PipelineUnavailableCard (chat 진행 중 발생 시에도 handleRetry 경로는 기존과 동일) | 무변경 |
| 라운드 상한 도달 | 서버가 질문을 내리지 않음 → rounds push 없이 tools 로 진행 (기존 동작) | 무변경 |

---

## 7. Security Considerations

- [x] 사용자 입력은 React 텍스트 노드로만 렌더 (요청 버블 `whitespace-pre-wrap` — innerHTML 미사용)
- [x] 신규 네트워크 호출·저장 없음 — 공격 면적 불변
- [ ] 그 외 해당 없음 (프론트 레이아웃 변경)

---

## 8. Test Plan

> 프로젝트 표준 도구: Vitest + RTL + MSW (Playwright 미도입 — L2/L3는 RTL 통합 테스트로 수행).
> Do 단계 규칙: 코드 + 테스트 = 1세트, Red → Green → Refactor.

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| L1: API | 해당 없음 (계약 무변경 — 기존 MSW 핸들러 재사용) | — | — |
| L2: 컴포넌트 | WizardShell, DescriptionComposer(variant), ToolsStep(locked), IntentStep | Vitest + RTL | Do |
| L3: 통합 | agentCreateWizard.test.tsx — 전 시나리오 누적형으로 갱신 | Vitest + RTL + MSW | Do |

### 8.2 L2: 컴포넌트 테스트 시나리오

| # | 대상 | 시나리오 | 기대 결과 |
|---|------|----------|----------|
| 1 | WizardShell | mode='centered' 렌더 | 하단 composer 슬롯 미렌더, 자식이 `my-auto` 래퍼 안에 있음 |
| 2 | WizardShell | mode='chat' 렌더 | composer 가 스크롤 컨테이너의 **형제**로 렌더 (겹침 구조 불가 검증) |
| 3 | WizardShell | 스크롤 구조 | 어떤 조상에도 `justify-center` 클래스 없음 (FR-15 회귀 가드) |
| 4 | WizardShell | scrollKey 변경 + near-bottom | scrollTo 호출됨 / 위로 스크롤된 상태면 호출 안 됨 |
| 5 | DescriptionComposer | variant='chat' | textarea disabled + 안내 placeholder, 전송 버튼 disabled |
| 6 | ToolsStep | locked=true | 체크박스 전부 disabled, [확정]·[처음부터] 미렌더, "선택 완료" 배지 표시 |
| 7 | IntentStep | 잠긴 라운드 (answered=true) | 카드 잠김 표시 + [건너뛰고 계속하기] 미렌더 |

### 8.3 L3: 통합 테스트 시나리오 (agentCreateWizard.test.tsx 갱신)

| # | 시나리오 | 단계 | 성공 기준 |
|---|----------|------|----------|
| 1 | centered → chat 전환 | 진입 → 설명 입력 → 전송 | 전송 전: 히어로+액션카드 보임 / 전송 직후: 요청 버블 렌더, 히어로·액션카드 사라짐, 하단 입력창 disabled |
| 2 | 헤더바 부재 | 진입 | "에이전트 만들기" 헤딩·[취소] 버튼 없음 |
| 3 | 라운드 이력 누적 | need_input 라운드1 답변 → need_input 라운드2 | 라운드1 질문 텍스트가 여전히 DOM에 있고 잠김, 라운드2 카드 활성 |
| 4 | 도구 → 프롬프트 이력 | 도구 확정 → prompt_ready | ToolsStep 잠김 상태로 잔존 + PromptStep 렌더 |
| 5 | 이전 단계 복귀 | PromptStep [이전 단계] | ToolsStep 잠금 해제, 재확정 시 프롬프트 재생성 |
| 6 | 첫 요청 실패 | 전송 → 500 응답 | chat 모드 유지: 요청 버블 + 실패 카드, [재시도] 동작 |
| 7 | 처음부터 | ToolsStep [처음부터] → confirm | centered 복귀, 트랜스크립트·입력 초기화 |
| 8 | 스튜디오 핸드오프 | 프롬프트 [저장하러 가기] | pendingIntent 셋 + /agent-builder 이동 (기존 시나리오 유지) |
| 9 | 킬스위치 | DISABLED 에러 | centered: 히어로 + UnavailableCard, [직접 만들기] 동작 |

### 8.4 Seed Data Requirements

MSW 핸들러 기존 것 재사용: need_input(2라운드) / tools_proposed / prompt_ready / 오류 응답 픽스처. 신규 시드 불필요.

---

## 9. Clean Architecture

### 9.4 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| WizardShell, index.tsx, 각 Step | Presentation | `src/pages/AgentCreateEntryPage/` |
| useAgentPipelineStream (무변경) | Application | `src/hooks/` |
| PipelineQuestion 등 타입 (무변경) | Domain | `src/types/agentPipeline.ts` |
| agentPipelineService (무변경) | Infrastructure | `src/services/` |

의존 방향 준수: WizardShell 은 순수 레이아웃(도메인 의존 0), index.tsx 만 훅·스토어에 의존.

---

## 10. Coding Convention Reference

| Item | Convention Applied |
|------|-------------------|
| 컴포넌트 | Arrow function + `export default` 하단, Props interface 상단 |
| 상수 | 런타임 상수는 컴포넌트 파일 export 금지 — `WizardRound` 는 타입이므로 로컬 허용 |
| 스타일 | Tailwind 디자인 토큰 (유저 버블·버튼·카드 패턴은 CLAUDE.md 정의 재사용) |
| 레이아웃 | `h-screen` 금지 — 루트 인라인 `height:'100%'`, 자체 스크롤 컨테이너 |
| 테스트 | 소스 옆 단위 테스트, `__tests__/integration/` 통합 테스트 |

---

## 11. Implementation Guide

### 11.1 File Structure

```
src/pages/AgentCreateEntryPage/
├── index.tsx                      (수정 — 헤더 제거·rounds·트랜스크립트 조립)
└── components/
    ├── WizardShell.tsx            (신규)
    ├── WizardShell.test.tsx       (신규)
    ├── DescriptionComposer.tsx    (수정 — variant)
    ├── DescriptionComposer.test.tsx (갱신)
    ├── IntentStep.tsx             (소폭 수정 — 잠긴 라운드 skip 숨김)
    ├── IntentStep.test.tsx        (갱신)
    ├── ToolsStep.tsx              (수정 — locked)
    ├── ToolsStep.test.tsx         (갱신)
    └── (나머지 무변경)
src/__tests__/integration/agentCreateWizard.test.tsx (갱신)
```

### 11.2 Implementation Order

1. [ ] **WizardShell** (테스트 먼저): 2-모드 + my-auto + 형제 composer + near-bottom 자동 스크롤
2. [ ] **DescriptionComposer variant** (테스트 먼저): chat variant disabled + placeholder
3. [ ] **ToolsStep locked / IntentStep skip 숨김** (테스트 먼저)
4. [ ] **index.tsx 재조립**: 헤더바 제거 → WizardShell 적용 → `rounds` 이력 + applyResult push → userRequest 즉시 커밋 → 트랜스크립트 순서 렌더
5. [ ] **통합 테스트 갱신** (§8.3 시나리오 1~9) → 전체 그린
6. [ ] type-check / lint / build

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| 레이아웃 셸 + 하위 컴포넌트 | `module-1` | WizardShell 신규, DescriptionComposer variant, ToolsStep locked, IntentStep skip 숨김 (각 테스트 포함) | 15-20 |
| 페이지 재조립 + 통합 | `module-2` | index.tsx 트랜스크립트 전환, rounds 이력, 통합 테스트 갱신 | 20-25 |

#### Recommended Session Plan

| Session | Phase | Scope | 비고 |
|---------|-------|-------|------|
| Session 1 | Do | `--scope module-1` | 하위 컴포넌트는 독립 검증 가능 |
| Session 2 | Do | `--scope module-2` | module-1 완료 전제 |
| Session 3 | Check + Report | 전체 | Gap 분석 ≥ 90% |

(규모가 크지 않아 한 세션에 module-1+2 연속 진행도 가능.)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-20 | Initial draft — C안(실용 절충) 확정, FR-15 오버플로 해법 포함 | 배상규 |
| 0.2 | 2026-08-20 | **FR-15 실측 추가 원인**: `justify-center` 외에 `QuestionOptionItem`/`QuestionFreeTextOption`의 sr-only(absolute) 라디오가 positioned 조상이 없어 body 기준 배치 → 스크롤 컨테이너 overflow 클리핑 탈출 → 문서 스크롤바 + 하단 흰 영역 (Chrome 실측: docScrollHeight 1350 vs viewport 735). label에 `relative` 추가로 해결, 회귀 가드 테스트 2건 추가 | 배상규 |
