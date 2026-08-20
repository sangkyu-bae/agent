# wizard-chat-layout Planning Document

> **Summary**: /agent-builder/new 위저드를 "단계 교체형 폼"에서 "채팅 트랜스크립트형" 레이아웃으로 전환 — 헤더바 제거, 입력창 첫 화면 중앙 → 이후 하단 고정, 단계 카드는 입력창 위로 누적
>
> **Project**: idt_front (sangplusbot)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-08-20
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 현재 위저드는 상단에 "에이전트 만들기" 헤더바가 화면을 차지하고, 질문 카드가 단계마다 아래에 붙었다 떨어졌다 하며 화면이 교체된다. 대화형 파이프라인인데 UI는 폼처럼 동작해 "지금까지 뭐라고 답했는지"의 맥락이 사라진다. |
| **Solution** | 헤더바를 제거해 전체를 채팅 영역으로 쓰고, 입력창을 첫 화면 중앙 → 첫 전송 후 하단 고정으로 전환(Claude/ChatGPT 방식). 요청 메시지·진행 상황·질문/도구/프롬프트 카드는 입력창 위 트랜스크립트에 순서대로 누적한다. |
| **Function/UX Effect** | 이전 라운드의 질문·답변이 잠긴 카드로 남아 대화 이력이 보존된다. 채팅 시작 후 직접만들기/가져오기 카드가 사라져 진행 중 화면이 파이프라인에만 집중된다. |
| **Core Value** | "설명하면 만들어진다"는 대화형 생성 경험을 UI 구조가 그대로 반영 — 학습 비용 없는 익숙한 채팅 멘탈 모델. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 대화형 파이프라인인데 폼형 UI라 진행 맥락(이전 질문·답변)이 화면에서 사라짐 |
| **WHO** | P2 (KB 운영자 / 에이전트 소유자) — 에이전트를 자연어로 생성하는 사용자 |
| **RISK** | 단계 교체형 상태 머신을 누적형 트랜스크립트로 바꿀 때 스테일 카드/잠금 로직 회귀 |
| **SUCCESS** | 기존 위저드 기능(4단계 전이·무저장 계약·스튜디오 핸드오프) 전부 유지 + 신규 레이아웃 테스트 통과 |
| **SCOPE** | 프론트 단독 — `AgentCreateEntryPage` 및 하위 컴포넌트 레이아웃 재구성. 백엔드/파이프라인 계약 변경 없음 |

---

## 1. Overview

### 1.1 Purpose

`/agent-builder/new` 에이전트 생성 위저드의 레이아웃을 채팅형으로 전환한다.

사용자 확정 요구사항 (2026-08-20 질의 확정):

1. **헤더바만 제거** — "에이전트 만들기" 타이틀 + [취소] 버튼이 있는 상단 고정 헤더바를 없애고 화면 전체를 채팅 영역으로 사용. EntryHero(아이콘 + 안내 문구)는 첫 화면에서 유지.
2. **질문 카드뷰는 채팅처럼 입력창 위로 쌓기** — 오버레이가 아니라, 요청 메시지 → 진행 상황 → 질문 카드 ① → 질문 카드 ② … 순으로 트랜스크립트에 누적.
3. **입력창: 첫 화면 중앙 → 첫 전송 후 하단 고정** — 진입 시에는 현재처럼 세로 중앙 배치(히어로 + 입력창 + 액션 카드), 첫 메시지 전송과 동시에 하단 고정 채팅 레이아웃으로 전환.
4. **[취소] 버튼과 직접만들기/가져오기 카드** — 취소 버튼은 완전히 제거(사이드바 네비게이션으로 대체 가능). 직접만들기/가져오기 카드는 첫 화면에서만 노출하고 채팅 시작 시 사라짐.

### 1.2 Background

- `agent-create-wizard` 기능(4단계 위저드, 커밋 fa8800f~d293415)으로 파이프라인 연동은 완료됐으나, 레이아웃은 "화면 중앙의 폼이 단계마다 교체되는" 방식이다.
- 직전 커밋 d293415에서 진행 상황을 입력창 아래로 이미 이동했다 — 이번 작업은 그 방향(대화 흐름 시각화)의 완성형이다.
- 질문 카드는 공통 `question-card` 컴포넌트(archived, Match 99.5%)를 그대로 재사용한다.

**확인된 버그 — 콘텐츠가 길어지면 화면이 깨짐 (2026-08-20 사용자 보고, 코드로 원인 확정):**

`index.tsx:360`의 스크롤 바디 내부 래퍼가
`flex min-h-full flex-col justify-center` 인데, 콘텐츠(질문 카드 + 도구 목록 +
프롬프트 편집기 등)가 뷰포트 높이를 초과하면 flexbox `justify-center` 가 넘친
분량을 스크롤 원점 **위쪽**으로 배치한다. 스크롤 컨테이너는 콘텐츠 시작점
위로는 스크롤할 수 없으므로 상단이 잘려 도달 불가 영역이 생기고, UI가 깨져
보인다(알려진 flexbox + overflow 함정). 안전한 패턴은 `justify-center` 대신
자식에 `my-auto`(auto 마진은 overflow 시 0으로 붕괴) 를 쓰거나, 이번 개편처럼
chat 모드에서 세로 중앙 정렬 자체를 제거하는 것이다. 이번 레이아웃 전환이
이 버그의 구조적 해결을 겸한다.

### 1.3 Related Documents

- 선행 기능: `docs/archive/` 내 agent-create-wizard Plan/Design (아카이브됨)
- 화면 총람: `docs/wiki/frontend/screens/agent-screens.md`
- 레이아웃 규칙: `idt_front/CLAUDE.md` — AgentChatLayout 내부 페이지 래퍼 규칙 (패턴 A)

---

## 2. Scope

### 2.1 In Scope

- [ ] 상단 헤더바("에이전트 만들기" + [취소]) 제거
- [ ] 2-모드 레이아웃: `centered`(첫 화면) ↔ `chat`(첫 전송 후 하단 고정 입력창 + 스크롤 트랜스크립트)
- [ ] 트랜스크립트 누적 렌더: 요청 메시지(유저 버블) → WizardProgress → IntentStep(라운드별 카드 누적, 답변 후 잠김 유지) → ToolsStep → PromptStep → 실패 카드
- [ ] 채팅 시작 시 EntryHero / EntryActionCards 숨김
- [ ] 새 카드 추가 시 트랜스크립트 하단 자동 스크롤
- [ ] 하단 입력창은 첫 전송 후 비활성(readonly 안내 또는 disabled) — 파이프라인은 카드 상호작용으로만 진행 (§3.1 FR-08 참조)
- [ ] 기존 단위/통합 테스트 갱신 + 신규 레이아웃 테스트 (TDD)

### 2.2 Out of Scope

- 파이프라인 API 계약·요청/응답 스키마 변경 (백엔드 무변경)
- `useAgentPipelineStream` 훅 로직 변경
- 무저장 계약(스튜디오 [저장]에서만 DB 반영) 변경
- 진행 상태 영속화(새로고침 유실은 정의된 동작 유지 — Design A-6)
- 자유 채팅(멀티턴 대화) 기능 — 입력창은 최초 설명 전송 전용
- 에이전트 가져오기 기능 활성화 (여전히 "준비 중" 비활성)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 상단 헤더바(타이틀+취소 버튼) 제거 — 페이지는 자체 스크롤 컨테이너만 가짐 | High | Pending |
| FR-02 | 첫 화면(`centered` 모드): EntryHero + 중앙 입력창 + EntryActionCards, 현재와 동일 구성 (헤더바만 없음) | High | Pending |
| FR-03 | 첫 전송 시 `chat` 모드 전환: 입력창 하단 고정, 트랜스크립트 영역 상단 스크롤 | High | Pending |
| FR-04 | `chat` 모드에서 EntryHero·EntryActionCards 미노출 | High | Pending |
| FR-05 | 요청 메시지를 유저 메시지 버블 스타일로 트랜스크립트 최상단에 표시 | High | Pending |
| FR-06 | WizardProgress + 안내 문구를 요청 메시지 다음 항목으로 표시 (d293415 동작 유지) | High | Pending |
| FR-07 | 질문 카드: 라운드별로 새 카드가 트랜스크립트에 **추가**되고, 답변 완료된 이전 라운드 카드는 잠긴 상태로 **남는다** (기존: 교체) | High | Pending |
| FR-08 | 하단 고정 입력창은 첫 전송 후 재전송 불가 상태 — 파이프라인 왕복은 카드(질문 답변/도구 확정/재생성)로만 발생. placeholder로 안내 | Medium | Pending |
| FR-09 | ToolsStep / PromptStep / WizardFailureCard / PipelineUnavailableCard 도 트랜스크립트 항목으로 렌더 | High | Pending |
| FR-10 | 새 트랜스크립트 항목 추가 시 하단으로 자동 스크롤 | Medium | Pending |
| FR-11 | [취소] 버튼 제거. `beforeunload` 이탈 경고(FR-F16)는 유지 | Medium | Pending |
| FR-12 | ToolsStep의 [처음부터] 재시작은 유지 — 실행 시 트랜스크립트 초기화 후 `centered` 모드 복귀 | Medium | Pending |
| FR-13 | 킬스위치(파이프라인 비활성) 시: `centered` 모드에서 EntryHero + PipelineUnavailableCard 표시 (현행 유지) | Medium | Pending |
| FR-14 | 스튜디오 핸드오프(PromptStep → [저장하러 가기])·프리필 동작 무변경 | High | Pending |
| FR-15 | **긴 콘텐츠 오버플로 수정**: 트랜스크립트가 뷰포트보다 길어져도 상단 잘림 없이 전체 스크롤 가능해야 한다. `centered` 모드도 `justify-center` 대신 overflow-safe 패턴(`my-auto` 등) 사용 — 콘텐츠가 짧으면 중앙, 길면 일반 스크롤로 자연 전환 | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 회귀 안전 | 기존 위저드 통합 테스트 시나리오(4단계 전이, 스테일 카드 가드, 에러 재시도) 전부 통과 | `npm run test:run` |
| 접근성 | 자동 스크롤이 스크린리더 포커스를 빼앗지 않음 (`aria-live` 고려), 입력창 disabled 시 사유 안내 | RTL 쿼리 + 수동 확인 |
| 성능 | 트랜스크립트 누적 렌더가 라운드 상한(2) + 단계 수(4) 내에서 항목 수 ≤ 10 — 가상화 불필요 | 코드 리뷰 |
| 레이아웃 | AgentChatLayout `<main>` overflow:hidden 규칙 준수 — 자체 스크롤 컨테이너 필수 | 수동 확인 |
| 레이아웃 | 뷰포트보다 긴 콘텐츠에서 상단/하단 잘림 없음 (FR-15) — 작은 뷰포트(예: 높이 600px)에서 4단계 전 구간 검증 | 수동 확인 + 통합 테스트(스크롤 컨테이너 구조 검증) |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01 ~ FR-15 구현 완료 (FR-15 오버플로 버그 수정 포함)
- [ ] 기존 테스트 갱신 + 신규 레이아웃 전환 테스트 작성·통과 (Red → Green → Refactor)
- [ ] `npm run type-check` / `npm run lint` 무오류
- [ ] Gap 분석(Match Rate) ≥ 90%

### 4.2 Quality Criteria

- [ ] 훅/유틸 커버리지 80% 이상 유지, 컴포넌트 60% 이상
- [ ] 빌드 성공 (`npm run build`)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 단계 교체형 → 누적형 전환 시 스테일 카드 가드(F10)·라운드 잠금 회귀 | High | Medium | 트랜스크립트를 "이력 배열"로 명시 모델링하고, 기존 `answered`/`completed` 잠금 테스트를 누적 시나리오로 확장 |
| 취소 버튼 제거로 명시적 이탈 경로 소실 → 사용자가 진행 중 상태에서 사이드바로 이탈 | Medium | Medium | `beforeunload` 유지 + ToolsStep [처음부터] 유지. 필요 시 Design 단계에서 라우터 이탈 확인 재검토 |
| 중앙 → 하단 고정 전환 애니메이션이 레이아웃 시프트/스크롤 튐 유발 | Medium | Medium | 전환은 모드 스위치(재배치)로 단순 처리, 애니메이션은 선택적 폴리시 — Design에서 결정 |
| 자동 스크롤이 사용자가 위로 스크롤해 이전 카드를 볼 때 강제로 끌어내림 | Low | Medium | "하단 근처일 때만 자동 스크롤" 가드 적용 (기존 채팅 패턴 재사용 검토) |
| 통합 테스트(agentCreateWizard.test.tsx)가 화면 교체 전제로 작성되어 대량 수정 필요 | Medium | High | 테스트를 먼저 누적형 시나리오로 수정(Red) 후 구현 — TDD 순서 준수 |
| 오버플로 수정 후에도 하단 고정 입력창 높이만큼 트랜스크립트 마지막 항목이 가려질 수 있음 | Medium | Medium | 입력창을 트랜스크립트 스크롤 영역 밖의 형제 요소(flex column)로 배치 — 겹침 자체가 발생하지 않는 구조로 설계 (Design에서 확정) |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `src/pages/AgentCreateEntryPage/index.tsx` | Page | 헤더바 제거, 2-모드 레이아웃, 트랜스크립트 누적 렌더로 재구성 |
| `src/pages/AgentCreateEntryPage/components/DescriptionComposer.tsx` | Component | 하단 고정 배치 대응 (chat 모드 스타일/disabled 상태) |
| `src/pages/AgentCreateEntryPage/components/IntentStep.tsx` | Component | 라운드별 누적 렌더 대응 (key 전략은 유지, 잠긴 카드 이력 표시) |
| `src/pages/AgentCreateEntryPage/components/EntryHero.tsx` | Component | 변경 없음 (노출 조건만 변경) |
| `src/pages/AgentCreateEntryPage/components/EntryActionCards.tsx` | Component | 변경 없음 (노출 조건만 변경) |
| `src/__tests__/integration/agentCreateWizard.test.tsx` | Test | 누적형 시나리오로 갱신 |
| 각 컴포넌트 단위 테스트 | Test | 레이아웃/노출 조건 변경분 갱신 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| AgentCreateEntryPage | ROUTE | `src/App.tsx` → `/agent-builder/new` | None (경로 무변경) |
| useAgentPipelineStream | READ | 페이지에서 호출 — 훅 계약 무변경 | None |
| useAgentDraftStore | WRITE | `goStudio()` — pendingIntent 핸드오프 | None (호출 시점 무변경) |
| question-card 공통 컴포넌트 | READ | IntentStep → QuestionCardFlow | Needs verification (`completed` 잠금 상태로 이력 표시가 가능한지 Design에서 확인) |
| AgentBuilderPage (스튜디오) | READ | 위저드 결과 프리필 | None |

### 6.3 Verification

- [ ] 위 소비자 전부 무변경 계약으로 동작 확인
- [ ] question-card `completed`/`disabled` 조합으로 잠긴 이력 카드 표현 가능 여부 확인
- [ ] 라우팅·핸드오프(스튜디오 프리필) 회귀 없음

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

기존 프로젝트(Dynamic — feature 단위 모듈, React 19 + TS) 유지. 신규 레벨 결정 없음.

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 트랜스크립트 모델 | ① step 조건부 렌더 유지+누적 플래그 / ② 이력 배열(transcript items) 도입 | Design에서 결정 | ①은 변경 최소, ②는 라운드 이력 표현이 자연스러움 — 트레이드오프는 Design 3안 비교로 |
| 모드 전환 | `mode: 'centered' \| 'chat'` 파생 상태 | step/제출 여부에서 파생 | 별도 상태 추가 없이 `step !== 'description' \|\| isPending`으로 파생 가능 |
| 자동 스크롤 | ref + scrollIntoView / 기존 채팅 패턴 재사용 | Design에서 결정 | ChatPage 스크롤 패턴 선례 확인 후 결정 |
| 스타일 | Tailwind (기존 디자인 토큰) | 유지 | CLAUDE.md 디자인 시스템 준수 |

### 7.3 Clean Architecture Approach

기존 폴더 구조 유지 — `pages/AgentCreateEntryPage/` 내부에서만 재구성. 상태/통신 레이어(훅·스토어·서비스)는 손대지 않는다.

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `idt_front/CLAUDE.md` 코딩 컨벤션 (컴포넌트/타입/상태관리/TDD)
- [x] ESLint / TypeScript 설정
- [x] 페이지 래퍼 규칙 (패턴 A: 고정 헤더 + 스크롤 바디 → 이번엔 헤더 없는 변형: 스크롤 바디 + 하단 고정 입력창)

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| 하단 고정 입력창 레이아웃 | ChatPage에 선례 있음 | 선례 재사용 여부 Design에서 확인 | High |
| 런타임 상수 export | 규칙 있음 (`as const`는 `src/types/*.ts`) | 신규 상수 추가 시 준수 | Medium |

### 8.3 Environment Variables Needed

없음 (프론트 레이아웃 변경만).

---

## 9. Next Steps

1. [ ] `/pdca design wizard-chat-layout` — 3안 비교(트랜스크립트 모델링) 후 설계 확정
2. [ ] 테스트 갱신(Red) → 구현(Green) → 리팩터
3. [ ] `/pdca analyze wizard-chat-layout` — Gap 분석

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-20 | Initial draft — 사용자 질의 4건 확정 반영 | 배상규 |
| 0.2 | 2026-08-20 | 긴 콘텐츠 오버플로 버그(FR-15) 추가 — `min-h-full`+`justify-center` 원인 확정, NFR·리스크 보강 | 배상규 |
