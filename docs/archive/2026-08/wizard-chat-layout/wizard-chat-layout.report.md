# wizard-chat-layout Completion Report

> **Status**: Complete
>
> **Project**: idt_front (sangplusbot)
> **Author**: 배상규
> **Completion Date**: 2026-08-20
> **PDCA Cycle**: #1 (iterate 없이 1회 통과)

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | wizard-chat-layout — /agent-builder/new 위저드 채팅 트랜스크립트형 전환 |
| Start Date | 2026-08-20 |
| End Date | 2026-08-20 (단일 세션 Plan→Report 완주) |
| Match Rate | **98%** (목표 90%) |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Completion Rate: 100% (FR 15/15)            │
├─────────────────────────────────────────────┤
│  ✅ Complete:     15 / 15 FR                 │
│  ⏳ Backlog:       2 건 (I-1 문서, I-2 aria) │
│  ❌ Cancelled:     0                         │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 대화형 파이프라인인데 폼형 UI라 이전 질문·답변 맥락이 화면에서 사라지고, 콘텐츠가 길어지면(질문 카드 2개+) 화면이 깨지며 하단에 흰 영역이 노출 |
| **Solution** | 2-모드 레이아웃(WizardShell: centered↔chat) + 라운드 이력 누적(rounds) + 하단 고정 입력창. 오버플로는 이중 원인 제거 — ①`justify-center`→`my-auto` ②sr-only 라디오의 클리핑 탈출을 label `relative`로 차단 |
| **Function/UX Effect** | 요청 버블→진행바→질문/도구/프롬프트 카드가 대화 이력으로 보존. Chrome 실측: 문서 오버플로 615px → **0px**, 흰 영역 소멸. 테스트 123/123 통과 |
| **Core Value** | 학습 비용 없는 채팅 멘탈 모델 + 공통 question-card를 쓰는 모든 화면의 잠재 오버플로 버그 동시 해결 |

---

## 1.4 Success Criteria Final Status

| # | Criteria | Status | Evidence |
|---|---------|:------:|----------|
| SC-1 | FR-01~15 구현 | ✅ Met | Analysis §2.5 체크리스트 19.5/20 + Chrome 실측 |
| SC-2 | 테스트 Red→Green, 기존 시나리오 유지 | ✅ Met | 위저드 관련 123/123 (컴포넌트 7파일 + 통합 2파일) |
| SC-3 | type-check / lint 무오류 | ✅ Met | `tsc --noEmit`·ESLint 통과 |
| SC-4 | Gap 분석 ≥ 90% | ✅ Met | 98% (Structural 96 / Functional 97 / Contract 100 / Runtime 100) |
| SC-5 | 빌드 성공 | ⚠️ Partial | 선행 오류로 HEAD부터 빌드 실패 상태 — 본 변경 기인 오류 0건 (stash 대조 검증) |

**Success Rate**: 4.5/5 (90%)

## 1.5 Decision Record Summary

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan] | 헤더바만 제거·카드 위로 누적·중앙→하단 고정·취소/액션카드 정리 (사용자 질의 4건 확정) | ✅ | 전 항목 구현, L2/L3 테스트로 고정 |
| [Plan v0.2] | FR-15 오버플로 — `justify-center` 원인 가설 | ✅ + 보강 | 가설 수정은 유효했으나 **실측 주원인은 sr-only 라디오 클리핑 탈출** — Chrome 계측으로 확정 후 추가 수정 |
| [Design] | C안: dispatch/applyResult 무변경 + rounds 이력 + WizardShell 분리 | ✅ | API Contract 100% — 회귀 0건으로 검증됨 |
| [Design §3.2] | userRequest 즉시 커밋 → mode 파생 | ✅ | 첫 요청 실패 시에도 chat 모드 유지되는 부수 개선 확보 |
| [Check] | Checkpoint 5 "그대로 진행" (사용자) | ✅ | I-1/I-2 백로그 이월, 98% 수용 |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [wizard-chat-layout.plan.md](../01-plan/features/wizard-chat-layout.plan.md) v0.2 | ✅ |
| Design | [wizard-chat-layout.design.md](../02-design/features/wizard-chat-layout.design.md) v0.2 | ✅ |
| Check | [wizard-chat-layout.analysis.md](../03-analysis/wizard-chat-layout.analysis.md) | ✅ |
| Act | 본 문서 | ✅ |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-01/11 | 헤더바·[취소] 제거, beforeunload 유지 | ✅ |
| FR-02 | centered 첫 화면 (히어로+입력창+액션카드) | ✅ |
| FR-03/04 | 첫 전송 시 chat 전환, 히어로·카드 숨김 | ✅ |
| FR-05/06 | 요청 버블 + 진행바 트랜스크립트 표시 | ✅ |
| FR-07 | 질문 라운드 누적 — 잠긴 이력 카드 유지 | ✅ |
| FR-08 | 하단 고정 입력창 잠금 + 안내 placeholder | ✅ |
| FR-09 | 도구/프롬프트/실패 카드 트랜스크립트 렌더, ToolsStep locked | ✅ |
| FR-10 | near-bottom 가드 자동 스크롤 | ✅ |
| FR-12 | [처음부터] → centered 복귀 | ✅ |
| FR-13 | 킬스위치 centered 안내 | ✅ |
| FR-14 | 스튜디오 핸드오프 무변경 | ✅ |
| FR-15 | **긴 콘텐츠 오버플로 수정** (my-auto + label relative) | ✅ Chrome 실측 |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|--------|
| 회귀 안전 | 기존 통합 시나리오 전부 통과 | 123/123 | ✅ |
| 레이아웃 | 뷰포트 초과 콘텐츠 잘림 없음 | 문서 오버플로 0px (실측) | ✅ |
| 성능 | 항목 ≤10, 가상화 불필요 | 최대 ~10 항목 | ✅ |
| 접근성 | 포커스 탈취 없음 / aria-live 고려 | 포커스 ✅ / aria-live 백로그 | ⚠️ |

### 3.3 Deliverables

| Deliverable | Location | Status |
|-------------|----------|--------|
| WizardShell (신규) + 테스트 6건 | `src/pages/AgentCreateEntryPage/components/` | ✅ |
| 페이지 재조립 (rounds·트랜스크립트) | `index.tsx` | ✅ |
| Composer variant / ToolsStep locked / IntentStep 이력 헤더 | 각 컴포넌트 + 테스트 | ✅ |
| question-card 오버플로 수정 + 회귀 가드 2건 | `src/components/common/question-card/` | ✅ |
| L2/L3 테스트 갱신 (신규 시나리오 9건+) | `index.test.tsx`, `agentCreateWizard.test.tsx` | ✅ |

---

## 4. Incomplete Items

### 4.1 Carried Over (Checkpoint 5 사용자 결정)

| Item | Reason | Priority |
|------|--------|----------|
| I-1: Design §8.3/§11.1 테스트 배치 표기 정정 | 문서-코드 표기 차이 (코드가 정상) | Low |
| I-2: 트랜스크립트 aria-live | 스크린리더 신규 카드 알림 | Medium |
| N-1: `MAX_ASSEMBLED_CHARS`/`MAX_CLARIFY_ROUNDS` 서버 값 대조 | prompt-depth 잔여분 — 본 기능 범위 밖 | Medium |
| M-2: 선행 기능 미커밋 변경분 커밋 분리 | 저장소 위생 | Medium |

---

## 5. Quality Metrics

| Metric | Target | Final |
|--------|--------|-------|
| Match Rate | 90% | **98%** |
| 테스트 (위저드 관련) | 통과 | 123/123 |
| Critical Gap | 0 | 0 |
| API 계약 회귀 | 0 | 0 (diff 수준 검증) |

### 5.2 Resolved Issues

| Issue | Resolution | Result |
|-------|------------|--------|
| 질문 카드 2개+ 시 화면 깨짐·하단 흰 영역 | sr-only 라디오 클리핑 탈출 → label `relative` | ✅ Chrome 실측으로 해결 확인 |
| `justify-center` 상단 잘림 | `my-auto` 패턴 교체 | ✅ 구조 테스트로 회귀 가드 |
| 첫 요청 실패 시 화면 튕김 가능성 | userRequest 즉시 커밋 | ✅ 실패 카드+버블 공존 |

---

## 6. Lessons Learned

### 6.1 Keep

- **실브라우저 계측이 결정적이었다**: jsdom 테스트 전부 그린이어도 오버플로 버그는 못 잡았다. Chrome에서 `scrollHeight`/`offsetParent` 계측으로 5분 만에 원인 확정.
- 파이프라인 로직 무변경(C안) 원칙 덕에 회귀 0건 — 검증된 코드를 안 건드리는 선택이 옳았다.
- 공통 컴포넌트 재사용(QuestionCardFlow `completed`)으로 이력 카드를 신규 구현 없이 해결.

### 6.2 Problem

- Plan 단계의 오버플로 원인 가설(`justify-center`)이 **주원인이 아니었다** — 가설을 코드 리딩만으로 확정하고 실측을 Do 이후로 미룬 것이 원인. sr-only(absolute) 요소의 overflow 클리핑 탈출은 정적 분석으로 놓치기 쉽다.
- 선행 기능들의 미커밋 변경이 트리에 섞여 있어 귀속 판정에 stash/diff 대조 비용이 들었다.

### 6.3 Try

- 레이아웃 버그는 Plan 단계에서 **브라우저 계측을 먼저** 수행해 원인을 확정한 뒤 요구사항화한다.
- `position: absolute` 숨김 패턴(sr-only)을 쓰는 공통 컴포넌트는 positioned 부모를 기본 규약으로 — 위키 등재 후보.

---

## 8. Next Steps

- [ ] `/pdca archive wizard-chat-layout`
- [ ] 백로그: aria-live(I-2), 서버 미러 상수 대조(N-1), 선행 변경분 커밋 분리(M-2)
- [ ] 위키 후보: "sr-only(absolute)와 스크롤 컨테이너 클리핑 탈출" 패턴 문서화 (`/wiki update` 시)

---

## 9. Changelog

### wizard-chat-layout (2026-08-20)

**Added:** WizardShell 2-모드 레이아웃, 라운드 이력 누적, 요청 버블, near-bottom 자동 스크롤, 회귀 가드 테스트 12건+
**Changed:** 헤더바·취소 제거, 입력창 하단 고정(chat), ToolsStep locked, IntentStep 이력 헤더 숨김
**Fixed:** 긴 콘텐츠 오버플로(문서 스크롤 615px→0) — `justify-center` 제거 + question-card label `relative`

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-08-20 | Completion report | 배상규 |
