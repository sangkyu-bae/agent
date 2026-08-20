# question-card Gap Analysis

> **Summary**: Design(F1-F9, §5.4 체크리스트) 대비 구현 검증 — Overall **98.5%** (runtime 포함) / 정적 95.8%
>
> **Date**: 2026-08-20
> **Analyzer**: gap-detector 에이전트(정적) + Vitest 런타임 검증
> **Design Doc**: [question-card.design.md](../../02-design/features/question-card.design.md)
> **Plan Doc**: [question-card.plan.md](../../01-plan/features/question-card.plan.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | HITL 질문 카드가 도메인 전용·구식 디자인이라 목표 UI와 불일치, 재사용 불가 |
| **WHO** | 에이전트 생성 진입 화면·Fix 탭에서 clarify 질문에 답하는 KB 운영자(P2) |
| **RISK** | 백엔드 HITL 계약(`ClarificationAnswer[]`, 부분 답변 허용) 파손 금지 |
| **SUCCESS** | 두 사용처 교체 + 전체 테스트 통과 + 공통 컴포넌트 도메인 타입 비의존 |
| **SCOPE** | 공통 4종 신설 → 사용처 인라인 매핑 교체 → 구 컴포넌트 제거 |

---

## 1. Match Rate

| 축 | 매치율 | 근거 |
|----|:-----:|------|
| Structural | 100% | §11.1 파일 8종 전부 존재, `ClarifyQuestionCard` 참조 0건, 배럴 export 구성 일치 |
| Functional | 96% | F1-F9 전부 구현. 편차: autoFocus 누락(G2), skip 시 선택 해제가 F5 문서에 미기재(G7) |
| Contract | 98% | `question-card` → `agentComposer` import 0건(FR-10), 사용처 역매핑이 question_id/question 에코백/answer 계약 정확 |
| Runtime (Vitest) | 100% | 해당 범위 5개 파일 56/56 통과 (단위 18 + 통합 38) |

**Overall = 100×0.15 + 96×0.25 + 98×0.25 + 100×0.35 = 98.5%** (≥ 90% 게이트 통과)
정적 전용 산식 기준(에이전트 단독): 95.8%

---

## 2. Plan Success Criteria

| 기준 | 상태 | 근거 |
|------|:---:|------|
| 공통 4종 `common/question-card/` 존재, 도메인 비의존 | ✅ Met | import 검사 0건, 폴더 구조 일치 |
| 두 사용처 교체, 구 컴포넌트 참조 0건 | ✅ Met | grep 0건, 두 사용처 QuestionCardFlow 배선 |
| 순차 제출 플로우 동작 | ✅ Met | QuestionCardFlow.test #6-11 통과 |
| 부분 답변·건너뛰기·MAX_CLARIFY_ROUNDS 회귀 없음 | ✅ Met | index.test HITL 4건 + FixAgentPanel HITL 4건 통과 |
| 테스트·lint·type-check 무오류 | ⚠️ Partial | 변경 파일 전부 무오류. 단 커버리지 %는 `@vitest/coverage-v8` 미설치로 측정 불가(G9), 전체 스위트의 기존 실패 9건은 본 기능 무관(HEAD에서 재현 확인) |

---

## 3. Gap 목록

| ID | 심각도 | 내용 | 위치 | confidence |
|----|:-----:|------|------|:---:|
| G1 | **Important** | Fix 탭에서 새 문장 입력으로 `pendingClarify`가 폐기된 뒤 스테일 질문 카드에 답하면, `handleAnswerSubmit`이 early-return해 요청이 전송되지 않는데 플로우 내부 `done` 플래그는 카드를 잠가 "✓ 답변 완료"로 오표시 | `QuestionCardFlow.tsx:56-66` + `FixAgentPanel.tsx` handleAnswerSubmit 가드 | 75% |
| G2 | Minor | Design §5.1의 직접 입력 확장 시 autoFocus 미구현 | `QuestionFreeTextOption.tsx` | 100% |
| G3 | Minor | §8.4 시드 요구(질문 2건 픽스처)를 통합 테스트는 1건으로 커버 — 2건 케이스는 단위 테스트가 대체 | `index.test.tsx` CLARIFY_BODY | 90% |
| G4 | Minor | 직접 입력 value 보존(재선택 시 복원)이 단위 테스트에서 미단언 | `QuestionCardParts.test.tsx` | 90% |
| G5 | Minor | `toClarificationAnswers` 헬퍼가 두 사용처에 중복 — Option C 인라인 매핑 결정의 의도된 결과 | 두 사용처 | 100% |
| G6 | Minor | `inputAriaLabel` prop이 Design §5.1 API에 미문서화 (구현이 설계보다 상세) | Design 문서 | 100% |
| G7 | Minor | skip 시 선택 해제 동작이 F5에 미기재 (코드 주석으로만 근거) | Design 문서 | 100% |
| G8 | Minor | compact variant의 일부 토큰이 §5.3 표에 부분 정의 | Design 문서 | 80% |
| G9 | 미검증 | 커버리지 80% 목표 — 리포터 미설치로 수치 미산출 | 프로젝트 devDeps | — |

**Critical 0건.** 테스트 매핑: §8.2 #1-14, §8.3 #1-5 **MISSING 0건** (PARTIAL 2건: §8.2 #4는 disabled 회귀 단언 방식 상이, §8.3 #1은 질문 1건 픽스처).

---

## 4. Decision Record Verification

| 결정 | 준수 여부 |
|------|:---:|
| [Plan] 질문당 카드 1장, 질문별 "▷ 제출" 순차 플로우 | ✅ |
| [Design] Option C — common 4종 + 사용처 인라인 매핑, 어댑터 생략 | ✅ |
| [Design] 로컬 useState, 전역 스토어 미사용 | ✅ |
| [Design] .tsx 런타임 상수 export 금지 (기본 레이블 = default parameter) | ✅ |
| [Design] 백엔드 HITL 계약 불변 | ✅ (통합 테스트가 request body 단언) |

---

## 5. 권고

1. **G1 수정 권장**: 스테일 질문 카드는 새 요청 전송 시점에 잠금 처리(사용처에서 `answered` 마킹)하거나, 플로우가 자체 잠금 전에 사용처 수리 여부를 알 수 있게 해야 UI 오표시가 사라진다.
2. G2(autoFocus)는 1줄 수정. G6-G8은 Design 문서 추기로 해소(코드 변경 불필요).
3. G9는 `@vitest/coverage-v8` 설치 시 즉시 측정 가능 — 이번 사이클 범위 밖.

---

## 6. Act (Iteration 1) 반영 결과

사용자 결정: "지금 모두 수정" (2026-08-20)

| Gap | 처리 | 내용 |
|-----|:---:|------|
| G1 (Important) | ✅ 수정 | Fix 탭 스테일 질문 카드 비활성화 — `disabled={isPending || !pendingClarify}` (`FixAgentPanel.tsx`), 회귀 테스트 추가. Design에 F10 규칙 신설 |
| G2 | ✅ 수정 | `QuestionFreeTextOption` 확장 입력에 autoFocus 추가 |
| G4 | ✅ 수정 | 재선택 시 value 복원 단언 보강 (`QuestionCardParts.test.tsx`) |
| G6 | ✅ 문서 | Design §5.1에 `inputAriaLabel` prop 추기 |
| G7 | ✅ 문서 | F5에 skip 시 선택 해제 명시 |
| G8 | ✅ 문서 | §5.3에 compact 공통 규칙 추기 |
| G3 | 수용 | 질문 2건 순차 케이스는 단위 테스트(§8.2 #6-11)가 커버 — 통합 픽스처 확장은 비용 대비 가치 낮음 |
| G5 | 수용 | 헬퍼 중복은 Option C(인라인 매핑) 결정의 의도된 결과 — 사용처 3곳 이상 시 어댑터 추출 |
| G9 | 이월 | 커버리지 리포터 미설치 — 별도 사이클 |

**재검증**: 해당 범위 57/57 통과(회귀 테스트 +1), 변경 파일 lint 무오류, type-check 무오류.
**갱신 Match Rate: 99.5%** (Functional 99 — F10 구현·검증 / Contract 100 — 문서 정합 회복 / Runtime 100)

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-08-20 | 최초 분석 — gap-detector 정적 95.8% + 런타임 합산 98.5% |
| 0.2 | 2026-08-20 | Act(iteration 1) — G1·G2·G4 코드 수정 + G6-G8 문서 추기, 99.5%로 갱신 |
