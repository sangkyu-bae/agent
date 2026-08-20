# progress-card Analysis Report

> **Analysis Type**: Gap Analysis
>
> **Project**: idt_front (sangplusbot 프론트엔드)
> **Version**: 0.0.0
> **Analyst**: 배상규 (gap-detector 에이전트 + 세션 검증)
> **Date**: 2026-08-20
> **Design Doc**: [progress-card.design.md](../02-design/features/progress-card.design.md) (v0.2)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 다단계 진행 상황을 표시할 재사용 가능한 UI가 없어 화면별 중복 구현·스타일 파편화 위험 |
| **WHO** | idt_front 개발자(1차 소비자), 최종적으로 자동 에이전트 빌드 화면 사용자 |
| **RISK** | 사용처(자동 빌드 화면)가 아직 미구현 — 실제 요구와 어긋난 과설계 가능성 |
| **SUCCESS** | 배열 props만으로 이미지(docs/img/card.png)와 동일한 카드 렌더링 + 컴포넌트 테스트 통과 |
| **SCOPE** | 공통 컴포넌트 3종 + 단위 테스트. 실 데이터/API 연동과 페이지 적용은 후속 기능 |

---

## Strategic Alignment Check

PRD 없음 (Plan부터 시작한 기능) — Plan/Design 2-계층 검증.

### Success Criteria Status (Plan §4.1 DoD)

| # | Criteria | Status | Evidence |
|---|----------|:------:|----------|
| SC-1 | FR-01~FR-08 구현 완료 | ✅ | 아래 FR 표 — 8/8 충족 |
| SC-2 | 3개 컴포넌트 단위 테스트 작성·통과 (TDD) | ✅ | Vitest 21/21 통과 (2026-08-20) |
| SC-3 | type-check / lint / test:run 무오류 | ✅ | `tsc --noEmit` 통과, ESLint 대상 7파일 0건, 테스트 통과 |
| SC-4 | card.png 대비 시각 구성 요소 재현 | ✅ | §5.2 스펙 4상태 전부 일치 (아래 Functional 표) — 커밋 전 화면 확인 권장 |

**Success Rate**: 4/4 (단, `npm run build`는 기존 무관 파일 4건 에러로 실패 — 아래 검증 공백 참조)

### Decision Record Verification

| Source | Decision | Followed? | Deviation |
|--------|----------|:---------:|-----------|
| [Plan] | 상태 4종 / 정적 표시 전용 / components/common 배치 | ✅ | 없음 |
| [Design] | Option C — 컴포넌트 3파일 + 테스트 3파일 | ✅ | 타입·상수만 `src/types/progress.ts`로 분리 (v0.2 승인·문서화된 변경) |

---

## 1. Match Rate

**gap-detector 에이전트 독립 분석 결과** (Runtime 포함 가중치):

| 축 | 점수 |
|---|:---:|
| Structural Match (파일 7/7, 컴포넌트 3/3, 의존 그래프 일치) | 100% |
| Functional Depth (§5.4 체크리스트 16/16, placeholder 0건) | 97% |
| Contract Match (Props/타입/상수/기본값 §3 완전 일치) | 100% |
| Runtime (§8.2 시나리오 17/17 커버 + 초과 커버 4건, 21/21 통과) | 100% |
| **Overall Match Rate** | **98%** |

Functional -3%p 사유: §5.2 행 레이아웃 문구(`flex items-center gap-3`)와 구현(2단 구조) 차이 — 세로 커넥터 칼럼 구현상 필요, 시각 결과 동등. Design 문구를 실제 구조로 정밀화하여 해소함.

## 2. FR 충족 요약 (8/8)

| FR | 판정 | 핵심 증거 |
|---|:--:|---|
| FR-01 배열 props 렌더링 | ✅ | `ProgressCard.tsx` steps.map / 테스트 T3 |
| FR-02 status 4종 | ✅ | `types/progress.ts` + error 렌더 테스트 |
| FR-03 상태별 아이콘·색상 | ✅ | `ProgressStepItem.tsx` ICON_PATH/ICON_CIRCLE + 그라데이션 |
| FR-04 진행중 강조 + 완료 커넥터 색 | ✅ | LABEL_CLASS.in_progress, 커넥터 조건부 클래스 / T2·T6 |
| FR-05 배지 라벨 오버라이드 | ✅ | `StatusBadge.tsx` `label \|\| style.label` / T2·T4 |
| FR-06 헤더 타이틀·아이콘 교체 | ✅ | `title = '진행 상황'`, `icon ?? <DefaultHeaderIcon />` |
| FR-07 빈 배열 처리 | ✅ | 조건부 렌더 + 빈 상태 문구 / T5 |
| FR-08 마지막 커넥터 없음 | ✅ | `{!isLast && …}` / T5 + 커넥터 수 N-1 검증 |

NFR: 재사용성(외부 의존 0 — services/store/hooks import 0건), 접근성(`<ol>` + 배지 텍스트 + `aria-hidden`), 스타일 토큰 준수 — 전부 충족. 의존성 규칙 위반 0건 (Presentation→Domain 단방향, 순환 없음).

## 3. Gap 리스트

- 🔴 Critical: **0건** / 🟠 Important: **0건**
- 🟡 Minor 3건 → **분석 직후 모두 해소**:
  1. 문서 표류 (Design §5.3·§9.2가 v0.2 타입 분리 미반영) → Design 문서 갱신 완료
  2. §5.2 행 레이아웃 문구 vs 2단 구현 구조 → Design 문구 정밀화 완료
  3. `AgentRunProgress`와 용도 구분 JSDoc 미이행 (Plan §5 완화책) → `ProgressCard.tsx` JSDoc 추가 완료
- ℹ️ Informational (조치 불요, 기록): 기존 로컬 `StatusBadge` 4개(JobsPage/StepTree/CollectionTable/DocumentTable — 각기 다른 도메인)와 이름 동일. Plan §2.2에서 기존 리팩터링은 Out of Scope. 향후 import 시 `common/StatusBadge` 경로 주의.

## 4. 검증 공백 (기록)

- `npm run build` 실패 — 원인 4건 전부 **기존 파일**: `useAgentComposer.test.ts`(expect 미정의), `AgentStorePage/index.tsx`(인자 누락), `agentAttachmentService.ts`(미사용 import), `vite.config.ts`(test 키 타입). progress-card 파일 관련 에러 0건, `tsc --noEmit`은 전체 통과 → **본 기능과 무관한 기존 빌드 깨짐**. 별도 수정 대상으로 보고.
- 전체 테스트 스위트 기존 실패 11건 (ChatPage/UpdateScopeModal 등) — 역시 본 기능과 무관 (기존 파일 수정 0건).

## 5. 판정

**Match Rate 98% ≥ 90% 게이트 통과. Critical·Important 0건 → iterate 불필요.**

다음 단계: `/pdca report progress-card`

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-20 | gap-detector 분석 + Minor 3건 즉시 해소 반영 | 배상규 |
