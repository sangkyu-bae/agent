# mutation-pending-guard — Design vs Implementation Gap Analysis

> gap-detector 수행 결과. Design v1.0(2026-07-29) 기준 구현 코드 대조.

## 분석 개요

| 항목 | 내용 |
|------|------|
| 대상 기능 | mutation-pending-guard (idt_front) |
| Design 문서 | `docs/02-design/features/mutation-pending-guard.design.md` (v1.0) |
| 구현 경로 | `src/components/common/LoadingButton.tsx`, `src/pages/AgentKnowledgePage/` |
| 분석일 | 2026-08-01 |

## 종합 점수

| 카테고리 | 점수 | 상태 |
|----------|:----:|:----:|
| Design 일치도 | 98.5% | ✅ |
| 아키텍처 준수 | 100% | ✅ |
| 컨벤션 준수 | 100% | ✅ |
| **Overall Match Rate** | **98%** | ✅ (임계값 90% 상회) |

---

## 1. LoadingButton 스펙 (Design §3.1) — 8/8

| # | 스펙 | 판정 | 근거 |
|---|------|:----:|------|
| 1 | `isPending` 필수 prop | ✅ | `LoadingButton.tsx:7` — optional 아님 |
| 2 | `pendingText?` optional | ✅ | `LoadingButton.tsx:9` |
| 3 | disabled 병합 `isPending \|\| disabled` | ✅ | `LoadingButton.tsx:23` |
| 4 | onClick 이중 방어 (`isPending ? undefined : onClick`) | ✅ | `LoadingButton.tsx:24` |
| 5 | `className` 통과 | ✅ (형태 차이) | 구조분해 없이 `{...rest}` 경유 — 동작 동일, 덮어쓰기 위험 없음 |
| 6 | `type="button"` 기본값 | ✅ | `LoadingButton.tsx:18,22` |
| 7 | 스피너 `aria-hidden` + `animate-spin` SVG | ✅ | `LoadingButton.tsx:28-47` |
| 8 | pendingText 미지정 시 children 유지 | ✅ | `pendingText ?? children` |

외부 의존성 0 (React type import 1건) — 설계 결정 ⑥ 준수.

## 2. AgentKnowledgePage 수정 (Design §3.2) — 10/10

| # | 스펙 | 판정 | 근거 |
|---|------|:----:|------|
| 1 | `submitError` 상태 | ✅ | `index.tsx:68` |
| 2 | `isSaving = create ∥ update` | ✅ | `index.tsx:95` |
| 3 | submitForm 조기 반환 (FR-04) | ✅ | `index.tsx:122` |
| 4 | try/catch + 고정 에러 문구 | ✅ | Design과 문구 문자 단위 일치 |
| 5 | 성공 시에만 폼 닫힘 | ✅ | try 내부 `setFormOpen(false)` |
| 6 | 에러 초기화 4지점 (FR-06) | ✅ | openCreate/openEdit/closeForm/submitForm 진입 |
| 7 | 저장 버튼 LoadingButton ("저장 중…") | ✅ | `index.tsx:233-241` |
| 8 | `role="alert"` 인라인 에러 | ✅ | `index.tsx:249-253` |
| 9 | 폐기 버튼 LoadingButton ("폐기 중…") | ✅ | `index.tsx:284-291` |
| 10 | 수정 진입 버튼 일반 유지 | ✅ | 서버 통신 아님 |

## 3. 테스트 (Design §7) — 9.5/10

- LoadingButton L1~L5: **5/5** (L2는 원문구 소멸 검증까지 추가)
- AgentKnowledgePage K1~K5: **4.5/5** — 시나리오 커버리지 5/5, 단 K1 2번째 클릭이 userEvent(disabled 요소 이벤트 미발생)라 조기 반환 가드 계층 자체는 미검증 (G1)
- MSW 경로 `*/api/v1/wiki` = `API_ENDPOINTS.WIKI_CREATE` 일치, per-file 훅 관례 준수

## 4~6. 아키텍처·컨벤션·CLAUDE.md — 전부 ✅

- LoadingButton은 hooks/services 미의존 (isPending은 prop으로만)
- 절대 경로 import, 파일 위치/네이밍/export default 규칙 준수
- CLAUDE.md 완료 파일 목록 등재 확인

---

## Gap 목록

| # | 항목 | 심각도 | 내용 | 조치 |
|---|------|:------:|------|------|
| G1 | K1 검증 강도 | Low | disabled 버튼에 userEvent 클릭은 가드 회귀와 무관하게 통과 — `submitForm` 조기 반환의 회귀 안전망 아님 (LoadingButton L3가 부분 대체) | 후속 테스트 작업 시 `fireEvent.click` 또는 submitForm 직접 2회 호출 케이스 추가 |
| G2 | className 전달 형태 | Low (문서 편차) | 구현은 `{...rest}` 경유 — 동작 동일 | 코드 유지 (Design 스니펫 편차로 기록) |
| G3 | DoD 실행 검증 | Info | type-check/lint/test 결과는 정적 분석 범위 밖 | Do 단계에서 이미 실행: type-check ✅, lint ✅, 대상 파일 테스트 15/15 ✅, 전체 회귀 신규 0 (사전 실패 8건 + 부하성 플래키 3건 격리 통과 확인) |

**Missing(설계 O, 구현 X): 없음.**

## Design에 없는 추가 구현 (긍정적 편차)

| 항목 | 평가 |
|------|------|
| `closeForm()` 헬퍼 추출 | 개선 — 에러 초기화 누락 방지 |
| L2 원문구 소멸 검증 추가 | 개선 |
| K1+K2 단일 블록 병합 (동일 delay 핸들러 재사용) | 중립 — 플래키 표면 축소 |

## 결론

Match Rate **98%** ≥ 90% — iterate 불필요. 남은 항목은 수동 검증(dev 서버에서 Network POST 1회·스피너 확인)뿐이며, `/pdca report mutation-pending-guard` 진행 가능.
