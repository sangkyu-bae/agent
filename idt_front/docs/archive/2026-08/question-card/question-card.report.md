# question-card Completion Report

> **Status**: Complete
>
> **Project**: idt_front (React 19 + TypeScript + Vite)
> **Version**: 0.0.0
> **Author**: 배상규
> **Completion Date**: 2026-08-20
> **PDCA Cycle**: #1

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | question-card — 조합형 질문지 카드 공통 컴포넌트 |
| Start Date | 2026-08-20 |
| End Date | 2026-08-20 |
| Duration | 1일 (단일 세션: Plan → Design → Do → Check → Act → Report) |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Completion Rate: 100% (FR 10/10)            │
├─────────────────────────────────────────────┤
│  ✅ Complete:     10 / 10 FR                 │
│  ⏳ Carried:       1 건 (커버리지 수치 측정) │
│  ❌ Cancelled:     0 건                      │
│  Match Rate: 99.5% (iteration 1회)           │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | HITL 질문 UI(`ClarifyQuestionCard`)가 agent-builder/fix 전용 칩 토글 카드로 하드코딩되어 목표 디자인(ask.png/card2.png)과 다르고 재사용 불가했던 문제를 해소 |
| **Solution** | `components/common/question-card/`에 도메인 비의존 조합형 4종(QuestionCard/OptionItem/FreeTextOption/Flow)을 신설하고 두 사용처를 순차 제출 위저드로 교체 — agentComposer import 0건으로 검증됨 |
| **Function/UX Effect** | 칩 → 전체 폭 라디오 행으로 가독성·터치 타깃 개선, 질문당 카드 1장 + 질문별 "▷ 제출" 순차 흐름으로 인지 부하 감소. 부수 효과로 기존에 없던 스테일 카드 오표시 리스크(G1)를 설계 규칙(F10)으로 차단 |
| **Core Value** | 질문·선택지·직접입력·제출이 조합 단위로 분리되어 설문/온보딩 등 다른 화면에서 재사용 가능한 질문 UI 기반 확보. 백엔드 HITL 계약은 무손실 유지(통합 테스트로 request body 단언) |

### 1.4 Success Criteria Final Status

| # | Criteria | Status | Evidence |
|---|---------|:------:|----------|
| SC-1 | 공통 4종이 `common/question-card/`에 존재, 도메인 타입 비의존 | ✅ Met | 폴더 8파일, `@/types/agentComposer` import 0건 (grep 검증) |
| SC-2 | 두 사용처 교체, `ClarifyQuestionCard` 참조 0건 | ✅ Met | grep 0건, 구 컴포넌트+테스트 삭제 |
| SC-3 | 순차 제출 플로우 동작 (제출→다음, 마지막→compose 재호출) | ✅ Met | QuestionCardFlow.test #6-11 + index.test HITL round=1 재호출 단언 |
| SC-4 | 부분 답변·건너뛰기·MAX_CLARIFY_ROUNDS 회귀 없음 | ✅ Met | 진입 화면 HITL 4건 + Fix 탭 HITL 5건(스테일 카드 회귀 포함) 통과 |
| SC-5 | 테스트·lint·type-check 무오류 | ✅ Met | 범위 내 57/57, 변경 파일 eslint 0건, tsc 무오류 (커버리지 %만 리포터 미설치로 이월) |

**Success Rate**: 5/5 criteria met (100%) — 단, SC-5의 커버리지 수치화는 G9로 이월

### 1.5 Decision Record Summary

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan] 사용자 확정 | 두 사용처 모두 적용, 질문당 카드 1장, 질문별 "▷ 제출" 순차 노출, common/ 분리 | ✅ | 4개 결정 전부 구현·테스트로 검증 |
| [Design] Checkpoint 3 | Option C 실용 균형 — 어댑터 없이 사용처 인라인 매핑 | ✅ | 매핑 헬퍼 중복 2곳(의도된 트레이드오프), 사용처 3곳 이상 시 어댑터 추출 예정 |
| [Design] | 로컬 useState + 내부 done 잠금 (F1-F9) | ✅ | done 자체 잠금이 스테일 카드 오표시(G1)를 유발 → F10 규칙 신설로 사용처 책임 명문화 후 수정 |
| [Design] | 네이티브 radio + sr-only (접근성) | ✅ | `getByRole('radio')` 기반 테스트 성립, 키보드 조작 유지 |
| [프로젝트 규칙] | .tsx 런타임 상수 export 금지 | ✅ | 기본 레이블 default parameter 처리 — 린트 재작업 0회 |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [question-card.plan.md](../../01-plan/features/question-card.plan.md) | ✅ Finalized |
| Design | [question-card.design.md](../../02-design/features/question-card.design.md) | ✅ Finalized (Act 추기 반영 v0.2) |
| Check | [question-card.analysis.md](../../03-analysis/features/question-card.analysis.md) | ✅ Complete |
| Act | 본 문서 | ✅ |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| FR-01 | QuestionCard 셸 (헤더/옵션/푸터 3단) | ✅ Complete | |
| FR-02 | 전체 폭 라디오 행 (선택 강조) | ✅ Complete | 네이티브 radio |
| FR-03 | 직접 입력 라디오 + 인라인 확장 | ✅ Complete | autoFocus 포함 (Act에서 보강) |
| FR-04 | 순차 노출 + 질문별 제출 + onComplete 1회 | ✅ Complete | |
| FR-05 | 제출 카드 read-only 잠금 | ✅ Complete | |
| FR-06 | ClarificationAnswer 계약 유지 (부분 답변) | ✅ Complete | MSW 통합 테스트 단언 |
| FR-07 | 질문별 건너뛰기 + 제출 버튼 선택 전 비활성 | ✅ Complete | |
| FR-08 | 진입 화면 교체 (planSummary·전체 건너뛰기 유지) | ✅ Complete | |
| FR-09 | Fix 탭 교체 (compact, answered 잠금) | ✅ Complete | + F10 스테일 카드 비활성 |
| FR-10 | 공통 컴포넌트 도메인 비의존 | ✅ Complete | import 검사 0건 |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|--------|
| 접근성 (radio 시맨틱·키보드) | getByRole 테스트 성립 | 성립 | ✅ |
| 디자인 토큰 일관성 | CLAUDE.md violet 계열 | §5.3 스펙 반영 | ✅ |
| 커버리지 80% | 80% | 측정 불가 (리포터 미설치) | ⏳ 이월 |
| 반응형 (채팅 폭) | compact variant | 구현 | ✅ |

### 3.3 Deliverables

| Deliverable | Location | Status |
|-------------|----------|--------|
| 공통 컴포넌트 4종 + types + 배럴 | `src/components/common/question-card/` | ✅ |
| 단위 테스트 (18+1건) | 동일 폴더 `*.test.tsx` | ✅ |
| 사용처 교체 | `AgentCreateEntryPage/index.tsx`, `FixAgentPanel.tsx` | ✅ |
| 통합 테스트 갱신 (+스테일 카드 회귀) | 각 `*.test.tsx` | ✅ |
| PDCA 문서 4종 | `docs/01~04` | ✅ |

---

## 4. Incomplete Items

### 4.1 Carried Over to Next Cycle

| Item | Reason | Priority | Estimated Effort |
|------|--------|----------|------------------|
| 커버리지 수치 측정 (G9) | `@vitest/coverage-v8` devDep 미설치 | Low | 0.5h (설치 + `npm run coverage`) |

### 4.2 Cancelled/On Hold Items

없음.

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Target | Final | Change |
|--------|--------|-------|--------|
| Design Match Rate | 90% | **99.5%** | 정적 95.8% → 런타임 합산 98.5% → Act 후 99.5% |
| 범위 내 테스트 | 전체 통과 | 57/57 | Act에서 회귀 테스트 +1 |
| Critical/Important 이슈 | 0 | 0 | G1(Important) 수정 완료 |
| 변경 파일 lint/type | 0 오류 | 0 | ✅ |

### 5.2 Resolved Issues

| Issue | Resolution | Result |
|-------|------------|--------|
| G1: Fix 탭 스테일 질문 카드가 "답변 완료" 오표시 (새 문장 전송 후 폐기된 왕복) | `disabled={isPending || !pendingClarify}` + F10 규칙 신설 + 회귀 테스트 | ✅ Resolved |
| G2: 직접 입력 확장 시 autoFocus 누락 | autoFocus 추가 | ✅ Resolved |
| G4: 입력값 보존·복원 미단언 | 단위 테스트 보강 | ✅ Resolved |
| G6-G8: 설계 문서-구현 표기 불일치 | Design 문서 추기 (inputAriaLabel/F5 선택 해제/compact 규칙) | ✅ Resolved |
| NUL 바이트 센티널이 파일을 바이너리로 만든 사고 | `' '` 이스케이프 표기로 교체 | ✅ Resolved |

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- Plan 단계의 AskUserQuestion 4건(적용 범위/카드 구성/제출 방식/배치)이 구현 중 방향 전환을 0회로 만듦 — card2.png 추가 제공으로 제출 UX가 조기에 확정됨
- 플로우 규칙 F1-F9를 Design에 표로 고정한 것이 단위 테스트 시나리오(#6-14)와 1:1로 이어져 TDD 마찰이 없었음
- 세션 메모리의 ".tsx 상수 export 금지" 규칙을 설계 시점에 반영해 과거(progress-card)와 같은 린트 재작업을 예방
- gap-detector 독립 검증이 자체 리뷰가 놓친 G1(스테일 카드 오표시)을 발견 — 내부 자체 잠금(done)과 사용처 가드의 상호작용은 작성자 시점에서 보이지 않았음

### 6.2 What Needs Improvement (Problem)

- 유니코드 제어 문자를 소스에 직접 쓰면 파일이 바이너리로 인식됨 — 이스케이프 표기(`' '`)를 처음부터 썼어야 함
- 전체 테스트 스위트에 기존 실패 9건이 방치되어 있어 회귀 판별에 stash 검증이라는 추가 비용 발생 (별도 정리 필요: UpdateScopeModal 6건 등)
- gap-detector 에이전트가 결과를 요약으로만 반환해 상세 회수에 왕복 2회 소요

### 6.3 What to Try Next (Try)

- `@vitest/coverage-v8` 설치로 커버리지 게이트 상시화
- 기존 실패 9건을 별도 기능(`test-suite-repair` 등)으로 등록해 전체 스위트 그린 회복
- 질문 카드가 3번째 사용처를 얻으면 `ClarifyQuestionFlow` 어댑터 추출 (Option B로 승격)

---

## 7. Process Improvement Suggestions

| Phase | Current | Improvement Suggestion |
|-------|---------|------------------------|
| Check | gap-detector가 요약만 반환 | 에이전트 프롬프트에 "최종 텍스트 = 상세 원시 데이터" 계약을 더 강하게 명시 |
| Check | 커버리지 미측정 | coverage 리포터를 프로젝트 devDeps에 포함 |
| 전체 | 기존 실패 테스트 누적 | CI 게이트 또는 주기적 /pdca 사이클로 스위트 그린 유지 |

---

## 8. Next Steps

### 8.1 Immediate

- [ ] `/pdca archive question-card` — 문서 아카이브
- [ ] 커밋/PR (요청 시 `/git-workflow`)

### 8.2 Next PDCA Cycle 후보

| Item | Priority | 비고 |
|------|----------|------|
| 기존 실패 테스트 9건 정리 | High | UpdateScopeModal 6건 포함, 본 기능과 무관 확인됨 |
| 커버리지 리포터 도입 (G9) | Low | 0.5h |

---

## 9. Changelog

### question-card v1.0 (2026-08-20)

**Added:**
- `src/components/common/question-card/` — QuestionCard, QuestionOptionItem, QuestionFreeTextOption, QuestionCardFlow, types, 배럴 + 단위 테스트 19건

**Changed:**
- `AgentCreateEntryPage`, `FixAgentPanel` — 질문 카드를 순차 제출 위저드로 교체 (HITL 계약 불변)
- Fix 탭: 폐기된 HITL 왕복의 스테일 질문 카드 비활성화 (F10)

**Removed:**
- `ClarifyQuestionCard.tsx` + 테스트 (공통 컴포넌트로 대체)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-08-20 | 완료 보고서 작성 | 배상규 |
