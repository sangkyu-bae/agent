---
template: analysis
version: 1.0
feature: llm-register
date: 2026-07-11
author: 배상규
project: idt_front
analyzer: bkit:gap-detector
---

# llm-register Gap Analysis (Design vs Implementation)

> **Design**: [llm-register.design.md](../../02-design/features/llm-register.design.md)
> **Plan**: [llm-register.plan.md](../../01-plan/features/llm-register.plan.md)
> **Method**: 정적 코드 비교 (테스트는 사전 실행 완료 — 신규 20건 통과, 회귀 0건)

## Overall Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match | 98.3% | ✅ |
| Architecture Compliance (§9) | 100% | ✅ |
| Convention Compliance | 100% | ✅ |
| **Overall (Match Rate)** | **98.3%** | ✅ (≥90%) |

**계산**: 전체 검증 항목 89개 (Data 8 + API 15 + UI 29 + Edge 7 + Security 3 + Test 21 + DoD 6)
— Match 86 · Partial 3 · Missing 0 → (86 + 0.5×3) / 89 = **98.3%**

## 섹션별 판정 요약

| Design 섹션 | 항목 수 | Match | Partial | Missing |
|-------------|:------:|:-----:|:-------:|:-------:|
| §3 Data Model (타입/상수/쿼리키) | 8 | 8 | 0 | 0 |
| §4 API/훅/에러매핑 | 15 | 14 | 1 | 0 |
| §5 UI/UX (5.1~5.7) | 29 | 28 | 1 | 0 |
| §6 Edge Cases | 7 | 6 | 1 | 0 |
| §7 Security | 3 | 3 | 0 | 0 |
| §8 Test Plan (MSW/H1~H6/P1~P9/nav) | 21 | 21 | 0 | 0 |
| §11 DoD | 6 | 6 | 0 | 0 |

## Gap 목록 (Partial 3건 — 전부 Low)

### Gap #1 — 404 실패 시 목록 invalidate 누락

- Design §4.3·§6: 404(타 관리자 선삭제 등) 시 "인라인 에러 + invalidate로 목록 재동기화" 요구.
- 구현: `onError`에서 인라인 에러만 설정. invalidate는 `onSuccess`에만 존재 (`useLlmModels.ts:37,53,62`).
- 심각도: **Low** — 희귀 동시성 케이스, 다음 성공 뮤테이션/refetch 시 자연 동기화.
- 권장: mutation `onError`에서 404일 때 invalidate 추가, 또는 Design 문구 완화.

### Gap #2 — 단가 셀 `/1K` 접미사 누락

- Design §5.2: `$0.0025 /1K` 표기. 구현 `PriceCell`은 `${value}`만 렌더.
- 심각도: **Low** — 컬럼명("입력 단가")과 가격 모달 서브타이틀이 단위를 안내.
- 권장: `${value} /1K` 렌더 + P2 테스트 갱신, 또는 Design 표기 완화.

### Gap #3 — include_inactive 토글 로딩 UX

- Design §6: "테이블 유지 + 우측 상단 미세 스피너". 구현: 새 쿼리키 `list(true)` 첫 조회 시 캐시가 없어 전체 "로딩 중..." 표시(짧은 깜빡임).
- 심각도: **Low** — 기능 정상.
- 권장: `placeholderData: keepPreviousData` + `isFetching` 스피너, 또는 Design 문구를 현 동작에 맞춤.

## Extra (Design에 없는 추가 구현 — 무해)

| 항목 | 위치 | 비고 |
|------|------|------|
| max_tokens 양의 정수 검증 | FormModal handleSubmit | 방어적 추가, 백엔드 계약과 합치 |
| 등록 필수 검증 통합 메시지 | FormModal handleSubmit | 필드별 검사 대신 묶음 메시지 |

## 관찰 (Gap 아님)

- `getLlmModel` 서비스·`queryKeys.llmModels.detail`은 Design대로 구현되었으나 페이지 미소비(수정 모달은 행 데이터 프리필) — 계약 완비 목적의 의도된 자산.
- Plan의 "패턴 A 레이아웃"은 Design §5.1에서 "AdminLayout 자체 스크롤 → 단순 래퍼"로 명시 override — 구현은 Design 기준 Match.

## 결론

Match Rate **98.3% (≥90% 통과)**. Missing 0건, Partial 3건은 모두 Low 심각도의 표시/UX 미세 차이로 기능 결함이 아니다. 신규 회귀 없음(전체 스위트 549 통과 / 사전 실패 8건 제외), 아키텍처·컨벤션 100% 준수.

---

## Act 보정 결과 (2026-07-11, 사용자 지시로 3건 전부 구현 보정)

| Gap | 보정 내용 | 위치 | 검증 |
|-----|----------|------|------|
| #1 | `invalidateOn404` 헬퍼 신설 — update/pricing/deactivate 뮤테이션 `onError`에서 `ApiError.status === 404`일 때 `llmModels.all` invalidate | `useLlmModels.ts` | 훅 테스트 그린 |
| #2 | `PriceCell`에 `/1K` 접미사 렌더 (`$0.0025 /1K`) + P2 테스트 갱신 | `AdminLlmModelsPage/index.tsx` | P2 통과 |
| #3 | `useLlmModels`에 `placeholderData: keepPreviousData` 적용 — 토글 시 테이블 유지, 페이지 헤더에 `isFetching && !isLoading` 미세 스피너 추가 | `useLlmModels.ts` + 페이지 헤더 | P9 통과 |

보정 후 재검증: 훅/페이지 테스트 19/19 통과, `type-check` 통과, 보정 파일 lint clean.
Partial 3건 해소 → **최종 Match Rate 100% (89/89)**.
