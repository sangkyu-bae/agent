# question-card Planning Document

> **Summary**: HITL 질문지 카드를 목표 디자인(ask.png/card2.png)의 라디오 행 카드로 재설계하고, 조합 가능한 공통 컴포넌트(`components/common/question-card/`)로 분리한다.
>
> **Project**: idt_front (React 19 + TypeScript + Vite)
> **Version**: 0.0.0
> **Author**: 배상규
> **Date**: 2026-08-20
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | HITL 질문 UI(`ClarifyQuestionCard`)가 agent-builder/fix 전용으로 하드코딩된 칩 토글 카드라 목표 디자인과 다르고, 다른 화면에서 재사용할 수 없다. |
| **Solution** | 질문 1개 = 카드 1장(말풍선 아이콘 헤더 + 전체 폭 라디오 행 + 하단 "▷ 제출" 버튼) 디자인의 조합형 공통 컴포넌트를 `components/common/question-card/`에 신설하고, 순차 제출 플로우(제출 → 다음 질문 노출)로 두 사용처를 모두 교체한다. |
| **Function/UX Effect** | 선택지가 칩에서 전체 폭 라디오 행으로 커져 가독성·터치 타깃이 개선되고, 질문을 한 번에 하나씩 처리하는 위저드 흐름으로 인지 부하가 줄어든다. |
| **Core Value** | 질문·선택지·직접입력·제출을 조합 단위로 분리해 에이전트 빌더 외 화면(설문, 온보딩 등)에서도 재사용 가능한 질문 UI 기반을 확보한다. |

---

## Context Anchor

> Design/Do 문서로 전파되는 컨텍스트 앵커.

| Key | Value |
|-----|-------|
| **WHY** | HITL 질문 카드가 도메인 전용·구식 디자인이라 목표 UI(ask.png/card2.png)와 불일치하고 재사용 불가 |
| **WHO** | 에이전트 생성 진입 화면·Fix 탭에서 clarify 질문에 답하는 KB 운영자(P2) |
| **RISK** | 백엔드 HITL 계약(`ClarificationAnswer[]`, 부분 답변 허용) 파손 — 계약은 그대로 유지해야 함 |
| **SUCCESS** | 두 사용처가 새 카드로 교체되고 기존/신규 테스트 전부 통과, 공통 컴포넌트는 agentComposer 타입 비의존 |
| **SCOPE** | 공통 컴포넌트 4종 신설 → 어댑터로 두 사용처 교체 → 기존 ClarifyQuestionCard 제거 (백엔드·타입 계약 변경 없음) |

---

## 1. Overview

### 1.1 Purpose

compose API가 `needs_clarification`을 반환할 때 표시되는 질문지 카드를 목표 디자인으로 교체하고, 질문 UI를 도메인 독립적인 조합형 공통 컴포넌트로 재구성한다.

### 1.2 Background

- 현재 `src/components/agent-builder/fix/ClarifyQuestionCard.tsx` 하나가 질문 N개를 한 카드에 담아 칩 토글 + 상시 노출 자유입력 + 단일 "답변 제출" 버튼으로 처리한다.
- 목표 디자인(`docs/img/ask.png`, `docs/img/card2.png`):
  - 카드 헤더: 말풍선 아이콘(연보라) + 질문 텍스트(굵게)
  - 본문: 전체 폭 라디오 행 목록. 마지막 행은 "직접 입력 (원하는 내용을 자유롭게 작성)"
  - 푸터: 상단 구분선 + 우측 정렬 연보라 "▷ 제출" 버튼
- 사용자 확정 요구사항 (2026-08-20 질의응답):
  1. **적용 범위**: 두 사용처 모두 (`AgentCreateEntryPage`, `FixAgentPanel`)
  2. **카드 구성**: 질문당 카드 1장
  3. **제출 방식**: 질문마다 제출 버튼 1개. 제출하면 다음 질문 카드가 나타나고, 마지막 질문 제출 시 전체 답변 전송
  4. **배치**: `src/components/common/` 아래 조합형 컴포넌트로 분리

### 1.3 Related Documents

- 목표 디자인: `docs/img/ask.png`, `docs/img/card2.png`
- 기존 HITL 설계: `docs/archive/2026-08/intent-slot-elicitation/` (백엔드), FIX-COMPOSER-001 아카이브
- 데이터 계약: `src/types/agentComposer.ts` — `ClarifyingQuestion`, `ClarificationAnswer`

---

## 2. Scope

### 2.1 In Scope

- [ ] `src/components/common/question-card/` 조합형 컴포넌트 신설
  - `QuestionCard` — 카드 셸 (아이콘+질문 헤더 / 본문 슬롯 / 푸터 슬롯)
  - `QuestionOptionItem` — 전체 폭 라디오 행 (단일 선택, 선택 시 보라 강조)
  - `QuestionFreeTextOption` — "직접 입력" 라디오 행, 선택 시 인라인 텍스트 입력 확장
  - `QuestionCardFlow` — 질문 배열의 순차 노출·답변 수집·질문별 제출·완료 콜백 오케스트레이션
- [ ] 답변 완료된 카드의 read-only(잠금) 표시 상태
- [ ] `AgentCreateEntryPage` 교체 — 기존 planSummary·"건너뛰고 초안 만들기" 동작 유지
- [ ] `FixAgentPanel` 교체 — 채팅 메시지 폭에 맞는 반응형 스타일
- [ ] 기존 `ClarifyQuestionCard` 제거(또는 어댑터로 축소) 및 테스트 이관
- [ ] 공통 컴포넌트 단위 테스트 + 두 사용처 통합 테스트 (TDD)

### 2.2 Out of Scope

- 백엔드 API/스키마 변경 (`ClarifyingQuestion`, `ClarificationAnswer` 계약 그대로)
- 다중 선택(multi-select) 지원 — 현재 계약이 단일 답변이므로 향후 확장으로 남김
- ChatPage 등 다른 도메인으로의 실제 적용 (재사용 "가능"하게만 설계)
- 질문 생성 로직·clarify 라운드 정책(MAX_CLARIFY_ROUNDS) 변경

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `QuestionCard`: 말풍선 아이콘 + 질문 헤더, 본문/푸터 슬롯을 가진 카드 셸. card2.png의 헤더-본문-푸터 3단 구조와 구분선 재현 | High | Pending |
| FR-02 | `QuestionOptionItem`: 전체 폭 라디오 행. 라디오 서클 + 레이블, 선택 시 보라 강조(border-violet + 채워진 라디오), hover 피드백 | High | Pending |
| FR-03 | `QuestionFreeTextOption`: `allow_free_text=true`인 질문의 마지막 행에 "직접 입력 (원하는 내용을 자유롭게 작성)" 라디오 표시. 선택 시 해당 행 아래로 텍스트 입력 확장, 선택 해제 시 접힘 | High | Pending |
| FR-04 | `QuestionCardFlow`: 질문 배열을 받아 **한 번에 한 카드씩** 노출. 카드의 "▷ 제출" 클릭 → 해당 답변 잠금 → 다음 질문 카드 노출. 마지막 질문 제출 시 `onComplete(answers)` 호출 (전체 답변 일괄 전달) | High | Pending |
| FR-05 | 제출된 카드는 화면에 남고 read-only로 잠긴다 (선택 결과 표시, 재수정 불가) | Medium | Pending |
| FR-06 | 백엔드 계약 유지: 완료 시 `ClarificationAnswer[]`(question_id/question/answer) 형태로 전달, 무응답 질문은 `answer=''` (부분 답변 허용) | High | Pending |
| FR-07 | 질문별 "건너뛰기" 보조 액션: 선택 없이 다음 질문으로 진행(`answer=''`). 제출 버튼은 선택(또는 직접 입력 텍스트) 전 비활성 | Medium | Pending |
| FR-08 | `AgentCreateEntryPage` 교체: planSummary 표시, 전체 "건너뛰고 초안 만들기"(모든 질문 무응답 강제 제출), isPending 중 비활성 유지 | High | Pending |
| FR-09 | `FixAgentPanel` 교체: 채팅 메시지 단위(`FixChatMessage.questions`)로 렌더, `answered` 메시지는 전체 잠금 표시 | High | Pending |
| FR-10 | 공통 컴포넌트는 `agentComposer` 타입에 의존하지 않는 제네릭 props를 갖고, 도메인 매핑은 사용처(또는 얇은 어댑터)에서 수행 | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 접근성 | 라디오 그룹 시맨틱(role="radio"/radiogroup 또는 native input) + 키보드 선택 가능, aria-label 유지 | RTL 쿼리(getByRole)로 테스트 |
| 테스트 | 공통 컴포넌트 커버리지 80% 이상, 기존 통합 테스트 회귀 없음 | `npm run coverage` |
| 일관성 | CLAUDE.md 디자인 토큰 준수 (violet 계열 Primary, rounded-2xl 카드, active:scale-95 버튼) | 코드 리뷰 |
| 반응형 | Fix 탭 채팅 폭(좁은 컨테이너)에서도 행 레이아웃 깨짐 없음 | 수동 확인 + 스냅샷 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] 공통 컴포넌트 4종이 `src/components/common/question-card/`에 존재하고 도메인 타입 비의존
- [ ] 두 사용처 모두 새 카드로 교체, 기존 `ClarifyQuestionCard` 참조 0건
- [ ] 순차 제출 플로우 동작: 제출 → 다음 질문, 마지막 제출 → compose 재호출
- [ ] 기존 HITL 왕복(부분 답변, 건너뛰기, MAX_CLARIFY_ROUNDS) 회귀 없음
- [ ] 단위 + 통합 테스트 작성·통과 (TDD Red→Green→Refactor)

### 4.2 Quality Criteria

- [ ] `npm run test:run` 전체 통과
- [ ] `npm run type-check` / `npm run lint` 무오류
- [ ] 공통 컴포넌트 커버리지 80% 이상

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 백엔드 HITL 계약 파손 (answer 에코백, 부분 답변) | High | Low | 계약 타입(`ClarificationAnswer`)을 그대로 사용, MSW 핸들러 기반 통합 테스트로 왕복 검증 |
| Fix 탭 채팅 폭에서 전체 폭 라디오 행이 답답함 | Medium | Medium | 카드 패딩·행 높이를 컨테이너 쿼리 없이 축소형 variant로 대응 (compact prop 또는 부모 폭 기반) |
| 순차 노출로 질문이 많을 때 왕복 피로 | Medium | Low | 질문 수는 서버가 제어(현재 소수). 질문별 건너뛰기 + 전체 건너뛰기 유지 |
| 기존 테스트 대량 수정 (ClarifyQuestionCard.test 등 3파일+) | Medium | High | 사용처 props 인터페이스(questions/planSummary/answered/isPending/onSubmit)를 유지하는 어댑터로 통합 테스트 수정 최소화 |
| 제출 버튼 비활성 조건과 "부분 답변 허용" UX 충돌 | Low | Medium | 제출은 선택 시 활성, 무응답 통과는 명시적 "건너뛰기"로 분리해 의도 없는 빈 답변 방지 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `src/components/agent-builder/fix/ClarifyQuestionCard.tsx` | UI Component | 제거 또는 공통 컴포넌트를 감싸는 얇은 어댑터로 대체 |
| `src/components/common/question-card/*` | UI Component | 신규 4종 (QuestionCard, QuestionOptionItem, QuestionFreeTextOption, QuestionCardFlow) |
| `src/pages/AgentCreateEntryPage/index.tsx` | Page | 질문 카드 렌더 블록 교체 (179–198행 부근) |
| `src/components/agent-builder/fix/FixAgentPanel.tsx` | UI Component | 질문 메시지 렌더 블록 교체 (246행 부근) |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| ClarifyQuestionCard | RENDER | `AgentCreateEntryPage/index.tsx` → clarify 질문 표시 + 건너뛰기 | Needs verification (교체 대상) |
| ClarifyQuestionCard | RENDER | `FixAgentPanel.tsx` → `FixChatMessage.questions` 메시지 렌더 | Needs verification (교체 대상) |
| ClarifyQuestionCard | TEST | `ClarifyQuestionCard.test.tsx` | Breaking → 신규 컴포넌트 테스트로 이관 |
| ClarifyQuestionCard | TEST | `FixAgentPanel.test.tsx`, `AgentCreateEntryPage/index.test.tsx` | Needs verification (셀렉터 수정 가능성) |
| `ClarifyingQuestion`/`ClarificationAnswer` 타입 | READ | `types/agentComposer.ts`, `hooks/useAgentComposer`, MSW handlers | None (계약 불변) |

### 6.3 Verification

- [ ] 위 소비자 전부 새 컴포넌트에서 동작 확인
- [ ] compose HITL 왕복(질문 수신 → 답변 제출 → 초안 수신) 통합 테스트 통과
- [ ] 타입/계약 변경 없음 확인 (`git diff src/types/agentComposer.ts` 공백)

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Selected |
|-------|:--------:|
| Starter | ☐ |
| **Dynamic** | ☑ |
| Enterprise | ☐ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 컴포넌트 배치 | agent-builder/fix 유지 / **common/question-card 분리** | common/question-card | 사용자 확정 — 도메인 독립 재사용 |
| 카드 구성 | 한 카드 다질문 / **질문당 카드 1장** | 질문당 카드 1장 | 사용자 확정 — 목표 이미지와 일치, 조합 단위 명확 |
| 제출 UX | 일괄 제출 / 즉시 자동 제출 / **질문별 제출 → 순차 노출** | 질문별 제출(순차) | 사용자 확정 — card2.png의 "▷ 제출" 버튼 |
| 상태 관리 | 전역(Zustand) / **로컬 useState (QuestionCardFlow 내부)** | 로컬 상태 | 일시적 UI 상태, 페이지 이탈 시 보존 불필요 |
| 도메인 결합 | 도메인 타입 직접 사용 / **제네릭 props + 사용처 매핑** | 제네릭 props | 공통화 목적 — agentComposer 비의존 |
| 스타일 | **Tailwind (CLAUDE.md 토큰)** | Tailwind | 프로젝트 표준 |
| 테스트 | **Vitest + RTL + MSW** | 좌동 | 프로젝트 표준, TDD |

### 7.3 Component Composition Preview

```
src/components/common/question-card/
├── QuestionCard.tsx          # 셸: 헤더(아이콘+질문) / children / footer
├── QuestionOptionItem.tsx    # 라디오 행 1개 (제어 컴포넌트)
├── QuestionFreeTextOption.tsx# 직접 입력 라디오 행 + 인라인 입력
├── QuestionCardFlow.tsx      # 순차 노출 + 답변 수집 + onComplete
└── index.ts                  # 배럴 export

조합 예 (도메인 어댑터에서):
<QuestionCardFlow
  questions={[{ id, title, options: string[], allowFreeText }]}
  onComplete={(answers) => ...}   // { id, value }[]
  disabled={isPending}
/>
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md` 코딩 컨벤션 + UI 디자인 시스템 (violet 토큰, 카드/버튼 패턴)
- [x] ESLint / TypeScript 설정
- [x] 테스트 컨벤션 (소스 옆 단위 테스트, `__tests__/` 통합)

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| common/ 하위 디렉토리 그룹 | 파일 단위 평면 배치 (`ConfirmDialog.tsx` 등) | `common/question-card/` 디렉토리 그룹 + 배럴 export 허용 여부 → Design에서 확정 | Medium |
| 라디오 행 시맨틱 | 없음 | native `<input type="radio">` vs button+aria — Design에서 확정 | Medium |

### 8.3 Environment Variables Needed

없음 (순수 UI 변경).

---

## 9. Next Steps

1. [ ] `/pdca design question-card` — 컴포넌트 API·시각 스펙·어댑터 경계 설계 (아키텍처 3안 비교)
2. [ ] TDD로 구현 (`/pdca do question-card`)
3. [ ] Gap 분석 (`/pdca analyze question-card`)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-20 | 최초 작성 — 사용자 질의응답 4건 반영 (적용 범위/카드 구성/제출 방식/배치) | 배상규 |
