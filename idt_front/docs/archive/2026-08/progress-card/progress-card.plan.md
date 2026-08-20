# progress-card Planning Document

> **Summary**: 배열 props로 단계를 조합하는 공통 진행 상황(Phase Stepper) 카드 컴포넌트 3종 (ProgressCard / ProgressStepItem / StatusBadge)
>
> **Project**: idt_front (sangplusbot 프론트엔드)
> **Version**: 0.0.0
> **Author**: 배상규
> **Date**: 2026-08-19
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 자동 에이전트 빌드(AGENT-006 v3 auto) 등 다단계 진행 흐름을 표시할 UI가 없고, 기존 `AgentRunProgress`는 WebSocket 실행 로그 전용이라 재사용이 불가능하다. 화면마다 진행 표시를 개별 구현하면 스타일·상태 표기가 파편화된다. |
| **Solution** | `{ label, status }[]` 배열만 넘기면 렌더링되는 정적 표시 전용 공통 카드를 `components/common`에 3-계층(카드 / 스텝 아이템 / 상태 배지)으로 분리 구현한다. |
| **Function/UX Effect** | 어떤 화면에서든 동일한 시각 언어(보라 체크=완료, 파랑 화살표=진행중, 회색 시계=대기중, 빨강=실패)로 다단계 진행 상황을 즉시 표시할 수 있다. |
| **Core Value** | 진행 표시 UI의 단일 소스 — 조합은 배열 변수 하나로, 스타일 변경은 컴포넌트 한 곳에서. |

---

## Context Anchor

> Design/Do 문서로 전파되는 컨텍스트 요약.

| Key | Value |
|-----|-------|
| **WHY** | 다단계 진행 상황을 표시할 재사용 가능한 UI가 없어 화면별 중복 구현·스타일 파편화 위험 |
| **WHO** | idt_front 개발자(1차 소비자), 최종적으로 자동 에이전트 빌드 화면 사용자 |
| **RISK** | 사용처(자동 빌드 화면)가 아직 미구현 — 실제 요구와 어긋난 과설계 가능성 |
| **SUCCESS** | 배열 props만으로 이미지(docs/img/card.png)와 동일한 카드 렌더링 + 컴포넌트 테스트 통과 |
| **SCOPE** | 공통 컴포넌트 3종 + 단위 테스트. 실 데이터/API 연동과 페이지 적용은 후속 기능 |

---

## 1. Overview

### 1.1 Purpose

`docs/img/card.png`와 같은 "진행 상황" 카드를 어떤 화면에서든 배열 변수 하나로 조합해 쓸 수 있는 공통 컴포넌트로 만든다.

```
┌──────────────────────────────────────────────┐
│ 📋 진행 상황                    ← 카드 헤더    │
├──────────────────────────────────────────────┤
│ ✔ Phase 1: 프로젝트 초기화          [완료]    │ ← ProgressStepItem
│ │                                            │   (세로 커넥터 라인)
│ → Phase 2: 의도 수집               [진행중]   │ ← 진행중: 강조(bold)
│ │                                            │
│ ◷ Phase 3: 도구 추천               [대기중]   │
│ ...                                          │
└──────────────────────────────────────────────┘
```

### 1.2 Background

- 백엔드 AGENT-006(`POST /api/v3/agents/auto`) 자동 에이전트 빌더는 Phase 1~7 단계로 진행되며, 프론트에서 이 진행 상황을 보여줄 화면이 필요해질 예정 (현재 프론트 미연동).
- 기존 `src/components/agent/AgentRunProgress.tsx`는 WebSocket 스트림(`useAgentRunStream`)에 강결합된 실행 로그 뷰로, "정해진 단계 목록 + 상태" 표시 용도로 재사용할 수 없다.
- 사용자 결정 사항 (2026-08-19 질의응답):
  - 사용처: 자동 에이전트 빌드 화면(향후) + 범용 공통 컴포넌트
  - 상태 종류: 완료/진행중/대기중 + **에러** 4종
  - 인터랙션: **정적 표시만** (상태 변경은 부모가 배열 갱신으로 처리)
  - 배치: `src/components/common/`

### 1.3 Related Documents

- 참고 이미지: `docs/img/card.png`
- 디자인 시스템: `CLAUDE.md` § UI 디자인 시스템 (색상 토큰·카드·타이포그래피)
- 향후 연동 대상: 백엔드 AGENT-006 (`idt/src/api/` v3 auto builder)

---

## 2. Scope

### 2.1 In Scope

- [ ] `ProgressStepStatus` 타입 및 상태 상수 (`as const` 객체 + 타입 추출, Enum 금지 컨벤션 준수)
- [ ] `StatusBadge` — 상태별 색상 배지 (완료/진행중/대기중/실패), 라벨 오버라이드 가능
- [ ] `ProgressStepItem` — 상태 아이콘 + 세로 커넥터 + 단계 라벨 + `StatusBadge` 1행
- [ ] `ProgressCard` — 헤더(아이콘 + 타이틀, 기본값 "진행 상황") + `steps: ProgressStep[]` 배열 렌더링
- [ ] 컴포넌트 3종 단위 테스트 (Vitest + RTL, TDD Red→Green→Refactor)
- [ ] 빈 배열 등 엣지 케이스 처리 (빈 상태 안내 문구)

### 2.2 Out of Scope

- 자동 에이전트 빌드 화면 자체 구현 및 API(v3 auto)/WebSocket 실 데이터 연동 — 후속 기능
- 단계 클릭·접기/펼치기·서브 콘텐츠 슬롯 등 인터랙션 (정적 표시만으로 확정)
- 진행률(%) 바, 애니메이션 전환 효과
- 기존 `AgentRunProgress.tsx` 리팩터링/교체

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `ProgressCard`는 `steps: ProgressStep[]` 배열 props만으로 전체 단계 목록을 렌더링한다 | High | Pending |
| FR-02 | `ProgressStep`은 최소 `{ label, status }`로 구성되며 `status`는 `completed \| in_progress \| pending \| error` 4종이다 | High | Pending |
| FR-03 | 상태별 아이콘·색상: 완료=보라 그라데이션 원+체크, 진행중=파랑/인디고 원+화살표, 대기중=회색 테두리 원+시계, 실패=빨강 원+X | High | Pending |
| FR-04 | 진행중 단계의 라벨은 굵게(강조) 표시되고, 완료→다음 단계 사이 커넥터 라인은 완료 색으로 채워진다 | Medium | Pending |
| FR-05 | `StatusBadge`는 상태별 기본 한글 라벨(완료/진행중/대기중/실패)을 가지며 `label` prop으로 오버라이드할 수 있다 | Medium | Pending |
| FR-06 | 카드 헤더 타이틀(기본 "진행 상황")과 헤더 아이콘은 props로 교체 가능하다 | Medium | Pending |
| FR-07 | `steps`가 빈 배열이면 레이아웃 깨짐 없이 빈 상태 문구를 표시한다 | Low | Pending |
| FR-08 | 마지막 단계 아래에는 커넥터 라인을 그리지 않는다 | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 재사용성 | 외부 스토어·훅 의존 없음 (props 순수 컴포넌트) | 코드 리뷰 — import 검사 |
| 접근성 | 상태를 색상만으로 전달하지 않음 (배지 텍스트 병행), 목록은 `<ol>` 시맨틱 사용 | RTL 쿼리(getByRole) 기반 테스트 |
| 스타일 일관성 | CLAUDE.md 디자인 토큰 준수 (violet primary, zinc border, rounded-2xl 카드) | 코드 리뷰 |
| 테스트 | 컴포넌트 커버리지 60% 이상 (프로젝트 기준) | `npm run coverage` |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01 ~ FR-08 구현 완료
- [ ] 3개 컴포넌트 각각 단위 테스트 작성·통과 (TDD 사이클 준수)
- [ ] `npm run type-check`, `npm run lint`, `npm run test:run` 무오류
- [ ] `docs/img/card.png` 대비 시각 구성 요소(헤더/타임라인/배지) 재현 확인

### 4.2 Quality Criteria

- [ ] 컴포넌트 테스트 커버리지 60% 이상
- [ ] Lint 에러 0건
- [ ] 빌드 성공 (`npm run build`)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 사용처(자동 빌드 화면) 미구현 상태에서 props 설계가 실제 요구와 어긋남 | Medium | Medium | props를 최소(`label`, `status`)로 유지하고 확장은 optional prop으로만 — YAGNI 준수 |
| 인터랙션 요구(클릭·슬롯)가 뒤늦게 추가되어 구조 변경 발생 | Low | Medium | ProgressStepItem을 독립 컴포넌트로 분리해 두어 확장 지점 확보 (이번 스코프에선 미구현) |
| 기존 `AgentRunProgress`와 역할 혼동 | Low | Low | JSDoc으로 용도 구분 명시 (정적 단계 표시 vs WS 실행 로그) |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `src/components/common/ProgressCard.tsx` | Component | 신규 생성 |
| `src/components/common/ProgressStepItem.tsx` | Component | 신규 생성 |
| `src/components/common/StatusBadge.tsx` | Component | 신규 생성 |

### 6.2 Current Consumers

신규 파일만 추가하며 기존 리소스 변경 없음 — 기존 코드 경로에 영향 없음.

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| (신규 3종) | CREATE | 소비자 없음 (후속 기능에서 연결 예정) | None |

### 6.3 Verification

- [x] 기존 소비자 없음 확인 (신규 파일만 추가)
- [x] 인증/권한 변경 없음
- [x] 기존 쿼리/뮤테이션 영향 없음

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Selected |
|-------|:--------:|
| **Starter** | ☐ |
| **Dynamic** | ☑ (기존 프로젝트 레벨 유지) |
| **Enterprise** | ☐ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 컴포넌트 분리 | 단일 파일 / 3-계층 분리 | **3-계층 분리** (Card / StepItem / Badge) | 사용자 요구 — 상태 배지·단계 아이템도 컴포넌트 단위 재사용 |
| 배치 위치 | common / agent | **`components/common/`** | 범용 공통 컴포넌트로 확정 (질의응답) |
| 상태 모델 | 3종 / 4종 | **4종** (`completed`/`in_progress`/`pending`/`error`) | 실패 표시 필요 가능성 — `as const` 객체 + 타입 추출 |
| 상태 관리 | 내부 상태 / props 순수 | **props 순수 (stateless)** | 정적 표시만 — 상태 전이는 부모 책임 |
| 아이콘 | 라이브러리 / 인라인 SVG | **인라인 SVG** | 프로젝트 기존 패턴 (외부 아이콘 라이브러리 미사용) |
| 스타일 | Tailwind 유틸리티 | **Tailwind v4 + 인라인 그라데이션** | CLAUDE.md 디자인 토큰 (violet primary gradient) |

### 7.3 Props 인터페이스 초안 (Design에서 확정)

```tsx
const PROGRESS_STEP_STATUS = {
  COMPLETED: 'completed',
  IN_PROGRESS: 'in_progress',
  PENDING: 'pending',
  ERROR: 'error',
} as const;
type ProgressStepStatus = (typeof PROGRESS_STEP_STATUS)[keyof typeof PROGRESS_STEP_STATUS];

interface ProgressStep {
  id?: string;               // 미지정 시 index key
  label: string;             // "Phase 1: 프로젝트 초기화"
  status: ProgressStepStatus;
  badgeLabel?: string;       // 배지 기본 라벨 오버라이드
}

interface ProgressCardProps {
  steps: ProgressStep[];
  title?: string;            // 기본 "진행 상황"
  icon?: ReactNode;          // 헤더 아이콘 교체
  className?: string;
}
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md` 코딩 컨벤션 존재 (컴포넌트/타입/스타일/TDD 규칙)
- [x] ESLint / TypeScript 설정 존재
- [x] 테스트 컨벤션 존재 (소스 옆 `*.test.tsx` 배치)

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| Naming | 존재 (PascalCase 컴포넌트) | 추가 정의 불필요 | - |
| 상태 상수 | 존재 (Enum 금지, `as const`) | `PROGRESS_STEP_STATUS` 위치 — ProgressCard.tsx 내 export | Low |

### 8.3 Environment Variables Needed

없음 (순수 UI 컴포넌트).

---

## 9. Next Steps

1. [ ] `/pdca design progress-card` — Design 문서 작성 (아이콘 SVG·색상 클래스·테스트 케이스 확정)
2. [ ] `/pdca do progress-card` — TDD 구현 (StatusBadge → ProgressStepItem → ProgressCard 순)
3. [ ] `/pdca analyze progress-card` — Gap 분석
4. [ ] (후속 기능) 자동 에이전트 빌드 화면에서 실사용 연결

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-19 | Initial draft — 질의응답 4건 반영 (사용처/상태 4종/정적 표시/common 배치) | 배상규 |
