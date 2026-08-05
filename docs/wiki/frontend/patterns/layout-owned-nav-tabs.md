---
title: 2차 네비게이션은 레이아웃 소유 탭 — 경로 역산 + 단일 소스 상수
status: approved
reviewer: 배상규
source_type: conversation
source_refs:
  - idt_front/docs/archive/2026-08/admin-nav-restructure/admin-nav-restructure.report.md
  - idt_front/src/constants/adminNav.ts (ADMIN_NAV_GROUPS, findAdminGroupByPath)
  - idt_front/src/components/layout/AdminSectionTabs.tsx
  - idt_front/src/components/layout/AdminLayout.tsx
confidence: 0.9
version: 1
created: 2026-08-03
updated: 2026-08-03
verified_at: 4f650d3c
---

## 문제

관리자 사이드바가 11개 플랫 항목으로 비대해졌다. 그룹+탭 구조로 바꾸되 11개 페이지
컴포넌트·라우트·URL을 건드리지 않아야 했다.

## 검증된 사실

1. **레이아웃 소유 탭 패턴**: 탭 상태를 각 페이지가 아니라 `AdminLayout`이 소유한다 —
   `findAdminGroupByPath(pathname)`로 현재 경로에서 활성 그룹을 **역산**해
   `AdminSectionTabs`(role=tablist)를 본문 상단에 고정 렌더링. 탭 클릭은 `navigate(item.path)`
   뿐. 결과: 페이지 11개·라우트·AdminRoute **무수정**으로 2차 네비 도입 완료.
2. **단일 소스 상수**: `adminNav.ts`의 `ADMIN_NAV_GROUPS`(4그룹: 관측/조직 관리/문서·품질/
   에이전트 리소스)가 원본이고, `ADMIN_NAV_ITEMS = GROUPS.flatMap(g => g.items)`는 파생값
   (하위 호환). 사이드바·탭 바·TopNav 드롭다운이 전부 이 상수에서 파생 — 네비 개편은
   상수 하나만 수정하면 전 UI 동기화.
3. **`ADMIN_ENTRY_PATH` = `/admin/dashboard`** (`groups[0].items[0].path` 파생) —
   기존 `/admin/users`에서 의도적으로 변경됨. 관리자 진입 경로를 단언하는 테스트 주의.
4. **테스트는 관계 기반 단언**: 기존 테스트가 항목 수를 10으로 하드코딩해 실제 11개와
   어긋난 채 통과하고 있었다. 단일 소스 상수의 개수·목록은 하드코딩 대신
   `flatMap(g => g.items).length === ADMIN_NAV_ITEMS.length` 같은 원본↔파생 관계로 단언해야
   확장 시 조용한 버그를 막는다.

## 다음에 적용하는 법

- 페이지 무수정이 필요한 2차·3차 네비는 라우트 재구성 대신 레이아웃 소유 + 경로 역산으로.
- 경로 매칭(`isAdminItemActive`)·역산(`findAdminGroupByPath`) 유틸은 설계 단계에서 시그니처를
  확정하고 재사용할 것.
- 관리 기능 추가 시 사이드바에 항목을 늘리지 말고 기존 그룹의 탭으로 흡수
  (`ADMIN_NAV_GROUPS`에 item 한 줄 추가가 전부).
