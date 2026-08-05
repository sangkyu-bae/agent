# admin-nav-restructure Gap Analysis

> **Feature**: admin-nav-restructure
> **Date**: 2026-08-02
> **Design Doc**: [admin-nav-restructure.design.md](../02-design/features/admin-nav-restructure.design.md)
> **Analyzer**: gap-detector agent
> **Match Rate**: **99%** ✅ (기준 90% 통과)

---

## 1. 판정 요약

설계와 구현이 사실상 완전 일치. 상수 시그니처(`isAdminItemActive`, `findAdminGroupByPath` 등)는 설계 코드 블록과 문자 수준까지 동일하고, 탭 바/사이드바/드롭다운의 Tailwind 클래스·aria 계약도 그대로다. 단일 소스 원칙(모든 소비처가 `adminNav.ts` 파생)과 무수정 계약(`App.tsx`·11개 페이지·`AdminRoute`·`AppSidebar.tsx` 코드)이 git diff로 확인됨.

- Missing (설계 O·구현 X): **0건**
- Added (설계 X·구현 O): **0건**
- 가중치: 그룹 데이터 20 / 상수·유틸 20 / AdminLayout 15 / 탭 바 15 / TopNav 15 / 변경 범위 5 / 테스트 10

## 2. 항목별 매칭 (요약)

| 설계 섹션 | 결과 |
|-----------|------|
| §2.2 그룹 데이터 (key 순서·label·아이콘·11개 항목·대표 경로) | ✅ 완전 일치 |
| §3.1 상수/유틸 5종 시그니처 | ✅ 문자 수준 일치 |
| §3.2 AdminLayout (그룹 사이드바·flex-column 래퍼·탭 바 고정·복귀 링크) | ✅ |
| §3.3 AdminSectionTabs (tablist/tab·aria-selected·활성 스타일·텍스트 전용) | ✅ |
| §3.4 TopNav (items?/groups? 분기·isMenuActive 보강·renderDropdownItem 공유·max-h 스크롤) | ✅ |
| §3.5 변경 파일 9종 / 무수정 대상 | ✅ 정확히 일치 (M 6 + 신규 3) |
| §4 테스트 (G1~G8 + 필드 검증 1, TB1~TB4, AL1~AL4, T4·T2·A4) | ✅ 전부 존재 (AL4는 유익한 이탈, 아래 Gap #1) |

## 3. Gap 목록

| # | 심각도 | 위치 | 내용 | 조치 |
|---|--------|------|------|------|
| 1 | 🔵 Low | `AdminLayout.test.tsx` AL4 | 설계는 AL4를 "범위 외"로 선언했으나 구현은 상세 경로(`/admin/agent-runs/run-1`) 그룹·탭 활성 검증으로 채움 — FR-05/06 커버리지가 늘어난 유익한 이탈 | 설계 문서 표기만 어긋남. 수정 불요 (report에 기록) |
| 2 | 🟡 Info | `TopNav.tsx` `renderDropdownItem` | 드롭다운 항목 하이라이트가 exact 매칭이라 상세 경로에서 메뉴 버튼은 활성·항목은 비활성. 설계 요구사항 아님(기존 마크업 재사용 지시 준수) | 선택적 개선 — 후속 판단 |
| 3 | 🟡 Info | Design §5 step 7~8 | ~~type-check/lint 미확인~~ → **Do 단계에서 실행·통과 확인됨** (type-check 0 에러, 변경 파일 9종 ESLint 클린). 잔여는 수동 확인만: 11개 URL 직접 진입, 드롭다운 `max-h-[70vh]` 실측, 탭 바 배경 톤(§6 Open Items) | 수동/시각 검증 이월 |
| 4 | 🟡 Info | 워킹트리 | `src/pages/AgentKnowledgePage/index.tsx(.test.tsx)` — 이 기능과 무관한 미커밋 변경 혼재 | 커밋 시 분리 필요 |

## 4. 테스트 실행 결과 (Do 단계 실측)

- 관련 테스트 29건 통과 (adminNav 9, AdminSectionTabs 4, AdminLayout 4, TopNav 4, AppSidebar 외 layout 8)
- 전체 스위트 757건 중 749 통과 — 실패 8건은 사전 존재(collection 7 + ChatPage 1), 본 기능 무관·회귀 0
- `npm run type-check` 통과 / 변경 파일 9종 ESLint 0건 (전체 lint 33 에러는 전부 기존 파일 사전 이슈)

## 5. 결론

**Match Rate 99% ≥ 90% → Check 통과.** 코드 갭 없음. 잔여는 수동/시각 검증 이월과 커밋 분리 주의뿐.

다음 단계: `/pdca report admin-nav-restructure`
