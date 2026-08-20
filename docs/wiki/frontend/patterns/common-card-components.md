---
title: 공통 카드 컴포넌트 — 진행 표시(ProgressCard)·질문 위저드(question-card)는 재사용 우선
status: approved
reviewer: 배상규
source_type: conversation
source_refs:
  - idt_front/src/components/common/ProgressCard.tsx · ProgressStepItem.tsx · StatusBadge.tsx (⚠️ 미커밋)
  - idt_front/src/types/progress.ts (ProgressStep 계약)
  - idt_front/src/components/common/question-card/ (QuestionCard/Flow/OptionItem/FreeTextOption 4종 + types.ts, ⚠️ 미커밋)
  - idt_front/src/components/common/question-card/QuestionCardFlow.tsx:25-56 (F1~F9 순차 위저드 + done 잠금)
  - idt_front/docs/archive/2026-08/progress-card/progress-card.report.md
  - idt_front/docs/archive/2026-08/question-card/question-card.report.md (§1.3 · SC-1/SC-2 · F10)
confidence: 0.85
version: 1
created: 2026-08-20
updated: 2026-08-20
verified_at: 7c3ffdd
---

# 공통 카드 컴포넌트 — 진행 표시·질문 위저드는 재사용 우선

## 문제

다단계 진행 표시 UI와 HITL 질문 UI가 화면마다 따로 구현될 위험이 있었다. 특히 질문
UI는 `ClarifyQuestionCard`가 agent-builder/fix 전용 칩 토글로 하드코딩되어 재사용이
불가능했다. 두 사이클(progress-card, question-card)이 이를 `components/common/` 아래
도메인 비의존 공통 컴포넌트로 확립했다 — **이제 이 두 종류의 UI를 새로 만들면 중복
구현이다.**

## 검증된 사실

### 1. 진행 표시 = `ProgressCard` 3-계층 (stateless)

`ProgressCard` / `ProgressStepItem` / `StatusBadge` — `steps: ProgressStep[]` 배열
하나로 렌더링되고 외부 의존이 0건이다. 4상태(진행중/완료/대기/실패)의 시각 언어는
이 컴포넌트가 단일 소스다. 신규 화면은 배열 변수만 조합하고, 스타일 변경은 한 곳만
고친다. 타입 계약은 `src/types/progress.ts`.

백엔드 대응물: [[sync-sse-dual-exposure]]의 "고정 steps + skipped" 계약. 사용처(자동
빌드 화면 등) 연동 시 **백엔드 이벤트 스키마 → `ProgressStep` 매핑 어댑터부터
설계**한다 (이월 항목 — 아직 실사용처 배선 전).

### 2. 질문 UI = `question-card` 조합형 4종 (구 `ClarifyQuestionCard`는 삭제됨)

`QuestionCard` / `QuestionOptionItem` / `QuestionFreeTextOption` / `QuestionCardFlow` —
`@/types/agentComposer` import 0건(도메인 비의존, grep으로 잠금). 질문당 카드 1장 +
질문별 순차 제출 위저드(F1~F9)이며, 부분 답변·건너뛰기를 지원한다. 두 사용처
(AgentCreateEntryPage, FixAgentPanel)가 이미 교체 완료 — **`ClarifyQuestionCard`는
컴포넌트·테스트 모두 삭제**됐으므로 옛 문서·설계의 그 이름은 이 폴더로 읽는다.

**F10 — 스테일 카드 차단**: 제출 완료 후 카드가 잠기는 것은 Flow 내부 `done` 잠금
(`allLocked = completed || done`)과 **사용처 가드의 2중**이다. gap-detector가 발견한
G1(이전 라운드 질문 카드가 새 응답 위에 남아 오표시)의 재발 방지 규칙이므로, 새
사용처를 붙일 때 사용처 쪽 가드(응답 갱신 시 카드 해제)를 빼먹으면 안 된다.

### 3. 어댑터 추출은 세 번째 사용처부터 (rule of three)

두 사용처가 각자 compose 재호출 로직을 갖는 현재 구조는 의도된 것이다. 질문 카드가
**3번째 사용처를 얻으면** 그때 `ClarifyQuestionFlow` 어댑터(HITL 계약 ↔ Flow props
매핑)를 추출하기로 결정돼 있다 (question-card report §6.3). 그 전에 미리 추상화하지
않는다.

## 다음에 적용하는 법

1. 다단계 진행 표시가 필요하면 `ProgressCard`에 `ProgressStep[]`을 만들어 넘긴다 —
   새 진행 UI 구현 금지. 질문/선택지/직접입력 UI가 필요하면 `common/question-card/`
   조합 — 설문·온보딩류도 이걸로.
2. question-card 새 사용처는 (a) 사용처 쪽 스테일 카드 가드, (b) 제출 payload가
   백엔드 HITL 계약(질문 에코백+라운드, [[stateless-hitl-clarification]])을 지키는지
   request body 단언 테스트를 세트로 붙인다.
3. 세 번째 사용처가 생기면 어댑터 추출을 먼저 검토한다.
