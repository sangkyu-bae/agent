# wizard-chat-layout Analysis Report

> **Analysis Type**: Gap Analysis
>
> **Project**: idt_front (sangplusbot)
> **Analyst**: gap-detector agent + Claude (runtime 검증)
> **Date**: 2026-08-20
> **Design Doc**: [wizard-chat-layout.design.md](../02-design/features/wizard-chat-layout.design.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 대화형 파이프라인인데 폼형 UI라 진행 맥락이 사라짐 + 긴 콘텐츠에서 화면 깨짐(오버플로) |
| **WHO** | P2 (KB 운영자 / 에이전트 소유자) |
| **RISK** | 교체형 → 누적형 전환 시 스테일 카드/잠금 로직 회귀 |
| **SUCCESS** | 기존 위저드 기능 전부 유지 + 신규 레이아웃 테스트 통과 |
| **SCOPE** | 프론트 단독 — AgentCreateEntryPage 재구성, 백엔드 무변경 |

---

## Strategic Alignment Check

### Success Criteria Status (Plan §4)

| # | Criteria | Status | Evidence |
|---|----------|:------:|----------|
| SC-1 | FR-01~15 구현 (FR-15 오버플로 수정 포함) | ✅ | 아래 §2.5 체크리스트 + Chrome 실측 (§2.7) |
| SC-2 | 테스트 Red→Green, 기존 통합 시나리오 유지 | ✅ | 위저드 관련 123/123 통과 (`npx vitest run` 2026-08-20) |
| SC-3 | type-check / lint 무오류 | ✅ | `tsc --noEmit` 통과, ESLint 무오류 |
| SC-4 | Gap 분석 ≥ 90% | ✅ | Overall 98% (§2.8) |
| SC-5 | 빌드 성공 | ⚠️ | HEAD 시점부터 실패 상태(AgentStorePage·vite.config 등 선행 오류) — 이번 변경분 기인 오류 0건 (stash 대조 검증) |

**Success Rate**: 4.5/5

### Decision Record Verification

| Source | Decision | Followed? | Deviation |
|--------|----------|:---------:|-----------|
| [Plan] | 헤더바 제거·카드 누적·중앙→하단 고정·취소/카드 정리 (질의 4건) | ✅ | 없음 |
| [Design] | C안: dispatch/applyResult 무변경 + rounds 이력 + WizardShell | ✅ | 없음 — 훅 diff 수준에서 계약 무변경 확인 |
| [Design §3.2] | mode 파생 + userRequest 즉시 커밋 | ✅ | 없음 |
| [Design FR-15] | justify-center 제거(my-auto) | ✅ + **원인 추가 발견** | sr-only 라디오 클리핑 탈출이 실측 주원인 — label `relative` 로 수정 (Design v0.2 반영 완료) |

---

## 2. Gap Analysis

### 2.1 API Contract — **100%**

Design §4 계약은 "변경 없음"이다. `useAgentPipelineStream` 훅·요청 바디 조립(stop_after / tools_confirmed / intent 에코백 / session_id 재사용)·응답 파싱이 diff 수준에서 무변경임을 확인. 신규 API 호출 없음.

### 2.3 Component Structure — Structural **96%**

| Design 컴포넌트 | 구현 | Status |
|----------------|------|--------|
| WizardShell (신규) | `components/WizardShell.tsx` + 테스트 | ✅ |
| index.tsx 재조립 (헤더 제거·rounds·트랜스크립트) | `index.tsx` | ✅ |
| DescriptionComposer variant | 구현 + 테스트 3건 | ✅ |
| ToolsStep locked | 구현 + 테스트 2건 | ✅ |
| IntentStep 이력 카드 헤더 숨김 | 구현 + 테스트 1건 | ✅ |
| EntryHero/EntryActionCards/WizardProgress/PromptStep 무변경 | 무변경 확인 | ✅ |
| (Design 외) question-card 2종 `relative` 추가 | FR-15 실측 원인 수정 — Design v0.2에 소급 기재 | ✅ |

감점: Design §11.1 파일 목록에 `index.test.tsx` 누락, `scrollKey` 타입 표기 차이(Design `unknown` vs 구현 `string`) — 문서 정정 대상.

### 2.5 Page UI Checklist (Design §5.4) — Functional **97%**

- centered 모드 6항목: 전부 ✅ (L2 테스트 + Chrome 확인)
- chat 모드 14항목: 13.5 ✅ — "긴 트랜스크립트 최상단 도달"은 jsdom 검증 불가였으나 **Chrome 실측으로 확인** (§2.7). 부분 감점: 접근성 NFR의 `aria-live` 미적용 (아래 Gap I-2).

### 2.7 Runtime Verification — **100%**

프로젝트 표준(Vitest + RTL + MSW)으로 수행 — Playwright 미도입, Design §8에 명시된 대체 계약.

| 구분 | 결과 |
|------|------|
| L2 컴포넌트 (WizardShell 6, Composer 9, ToolsStep 12, IntentStep 10, question-card 파츠 등) | 전부 통과 |
| L3 통합 (index.test.tsx 34 + agentCreateWizard 9) | 전부 통과 |
| **합계** | **123 / 123** |
| **Chrome 실브라우저 검증 (FR-15)** | 질문 카드 2개 누적 상태에서 `docScrollHeight 735 = viewport`(수정 전 1350), 윈도우 스크롤 0px(수정 전 614px), 라디오 offsetParent LABEL(수정 전 BODY), 트랜스크립트 내부 스크롤만 동작 |

### 2.8 Match Rate Summary

```
┌─────────────────────────────────────────────┐
│  Structural Match Rate:  96%                 │
│  Functional Match Rate:  97%                 │
│  Contract Match Rate:    100%                │
│  Runtime Match Rate:     100%                │
│  ─────────────────────────────────────────── │
│  Overall Match Rate:     98%                 │
│  = (96×0.15)+(97×0.25)+(100×0.25)+(100×0.35)│
└─────────────────────────────────────────────┘
```

---

## Gap List

**Critical: 0건**

| ID | 심각도 | 항목 | 조치 |
|----|--------|------|------|
| I-1 | Important | Design §8.3/§11.1 문서와 실제 테스트 배치 불일치 (L3 시나리오 상당수가 `index.test.tsx`에 구현됨) | **문서 정정** — 코드가 정상, Design을 코드에 맞춤 |
| I-2 | Important | 접근성 NFR: 트랜스크립트 `aria-live` 미적용 (Plan §3.2 "고려" 항목). 자동 스크롤의 포커스 탈취는 없음(scrollTo는 포커스 이동 아님) — 스크린리더 신규 카드 알림만 미비 | 소규모 코드 수정 또는 후속 백로그 |
| M-1 | Minor | Design §11.1 파일 목록에 `index.test.tsx` 누락, `scrollKey` 타입 표기 차이 | 문서 정정 |
| M-2 | Minor (저장소 위생) | 선행 기능(prompt-depth, agent-create-wizard)의 프론트 변경분이 미커밋 상태로 이번 변경과 한 트리에 혼재 | 커밋 분리 권고 |
| N-1 | 범위 밖 권고 | `MAX_ASSEMBLED_CHARS=8000` / `MAX_CLARIFY_ROUNDS=3`은 서버 값의 수동 미러 — `idt/` 실제 값과 대조 필요 (prompt-depth 잔여분 커밋 전) | 별건 확인 |

---

## 10. Design Document Updates Needed

- [ ] §8.3/§11.1 테스트 배치 현행화 (L3 시나리오 → index.test.tsx 반영)
- [ ] §5.3 WizardShell `scrollKey?: string` 표기 정정
- [x] FR-15 실측 원인(sr-only 라디오) — v0.2로 반영 완료

## 11. Next Steps

- [x] Checkpoint 5 결정 — **"그대로 진행"** (2026-08-20 사용자 확정): I-1(문서 정정)·I-2(aria-live)는 백로그로 이월, 98% 상태 수용
- [ ] `/pdca report wizard-chat-layout`

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-20 | Gap 분석 (gap-detector) + Vitest 123건 + Chrome 실측 반영 | 배상규 |
