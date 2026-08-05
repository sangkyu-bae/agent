# admin-nav-restructure Planning Document

> **Summary**: 11개 항목이 플랫하게 나열된 `/admin` 사이드바를 4개 그룹(관측/조직/문서·품질/에이전트 리소스)으로 재구성하고, 그룹 진입 후 페이지 상단 2차 탭으로 하위 기능을 전환하는 구조로 개편한다.
>
> **Project**: sangplusbot (idt_front)
> **Author**: AI Assistant
> **Date**: 2026-08-02
> **Status**: Draft

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem (문제)** | 관리자 사이드바에 11개 메뉴가 위계 없이 플랫하게 나열되어 있어(운영 대시보드~위키 관리) 관련 기능끼리 흩어져 보이고, 항목이 늘어날 때마다 목록만 길어지는 구조라 탐색성이 계속 나빠진다. TopNav "관리" 드롭다운도 동일한 11개 플랫 목록이다. |
| **Solution (해결)** | `adminNav.ts`를 그룹 구조(`ADMIN_NAV_GROUPS`)로 재편해 사이드바에는 4개 그룹만 노출하고, 그룹 클릭 시 첫 하위 페이지로 이동 + `AdminLayout`이 현재 그룹의 2차 탭 바를 본문 상단에 렌더링한다. 기존 URL(`/admin/users` 등)과 11개 페이지 컴포넌트는 그대로 유지한다. |
| **Function UX Effect (기능·UX 효과)** | 사이드바가 11항목 → 4그룹으로 줄어 한눈에 들어오고, 같은 성격의 기능(사용자↔부서, RAGAS↔청킹, MCP↔도구↔Skill↔위키↔LLM)이 탭으로 인접 배치되어 관련 작업 간 전환이 1클릭이 된다. TopNav 드롭다운도 그룹 헤더로 구분되어 스캔이 쉬워진다. |
| **Core Value (핵심 가치)** | 관리자 콘솔에 확장 가능한 정보 구조(IA)를 도입한다 — 이후 관리 기능이 추가돼도 기존 그룹의 탭 하나로 흡수되어 사이드바가 다시 비대해지지 않는다. 단일 소스(`adminNav.ts`) 원칙은 그대로 유지된다. |

---

## 1. Overview

### 1.1 Purpose

`/admin` 영역의 네비게이션을 플랫 11항목에서 **그룹 4개 + 페이지 내 2차 탭** 구조로 재구성하여
관리 기능의 탐색성과 확장성을 확보한다.

### 1.2 Background (현재 구조)

- 메뉴 단일 소스: `src/constants/adminNav.ts` — `ADMIN_NAV_ITEMS` 11개 (운영 대시보드, 사용자 관리, 부서 관리, RAGAS 평가, Agent Run 관측, LLM 모델, 청킹 프로파일, MCP 서버, 도구 관리, Skill 관리, 위키 관리)
- 소비처 2곳:
  - `AdminLayout.tsx` — 좌측 사이드바(w-56)에 11개 전부 플랫 렌더링, `startsWith` 하위 경로 활성 매칭
  - `TopNav.tsx` — `ADMIN_MENU` 드롭다운에 11개 전부 플랫 렌더링 (admin role일 때만)
- 진입점: `AppSidebar` "관리자" → `ADMIN_ENTRY_PATH` (`/admin/users`)
- 라우트: `App.tsx`에 11개 + `/admin/agent-runs/:runId` 상세 라우트

### 1.3 사용자 결정 사항 (확정)

| # | 결정 | 선택 |
|---|------|------|
| 1 | 네비게이션 패턴 | **그룹 항목 + 페이지 내 2차 탭** — 사이드바에는 그룹만, 그룹 진입 후 상단 탭으로 하위 전환 |
| 2 | 잔여 3항목 배치 | **관측 그룹**(운영 대시보드 + Agent Run 관측) 신설, **LLM 모델은 에이전트 리소스 그룹**에 포함 |
| 3 | URL 정책 | **기존 URL 전부 유지** (`/admin/users` 등) — 네비게이션 UI만 재구성, 리다이렉트 불필요 |
| 4 | TopNav 관리 드롭다운 | **그룹 헤더로 구분해 표시** — 사이드바와 동일한 그룹 체계 공유 |

### 1.4 확정 그룹 구조 (4그룹 / 11페이지)

| 그룹 | 하위 탭 (순서 = 탭 순서) | 그룹 대표 경로(첫 탭) |
|------|--------------------------|----------------------|
| **관측** | 운영 대시보드 → Agent Run 관측 | `/admin/dashboard` |
| **조직 관리** | 사용자 관리 → 부서 관리 | `/admin/users` |
| **문서·품질** | 청킹 프로파일 → RAGAS 평가 | `/admin/chunking-profiles` |
| **에이전트 리소스** | MCP 서버 → 도구 관리 → Skill 관리 → LLM 모델 → 위키 관리 | `/admin/mcp-servers` |

> 문서·품질 그룹은 "파이프라인 설정(청킹) → 결과 평가(RAGAS)" 흐름 순서로 배치.
> 에이전트 리소스는 "연결(MCP) → 도구 → Skill → 모델 → 지식(위키)" 순.

### 1.5 Related Documents

- 메뉴 단일 소스: `src/constants/adminNav.ts` (+ `adminNav.test.ts`)
- 관리자 레이아웃: `src/components/layout/AdminLayout.tsx`
- 상단 네비: `src/components/layout/TopNav.tsx`
- 메인 진입점: `src/components/layout/AppSidebar.tsx` (`ADMIN_ENTRY_PATH` 소비)
- 라우팅: `src/App.tsx`
- 선행 작업: `docs/01-plan/features/admin-navigation-entry.plan.md` (단일 소스 통합 이력)

---

## 2. Scope

### 2.1 In Scope

- [ ] `adminNav.ts` 재구조화: `ADMIN_NAV_GROUPS: AdminNavGroup[]` 도입 (`{ key, label, icon, items }`)
  - 기존 `AdminNavItem` 유지, `ADMIN_NAV_ITEMS`는 그룹 flatten 파생값으로 유지 (하위 호환)
  - `ADMIN_ENTRY_PATH`를 `/admin/dashboard`(관측 그룹 첫 탭)로 변경
- [ ] `AdminLayout` 사이드바: 그룹 4개만 렌더링, 클릭 시 그룹 첫 탭으로 이동, 현재 경로가 속한 그룹 활성 표시
- [ ] `AdminLayout` 본문 상단에 **2차 탭 바** 렌더링: 현재 그룹의 items를 탭으로 표시, 클릭 시 해당 라우트로 이동 (페이지 컴포넌트 무수정 — 레이아웃이 탭을 소유)
- [ ] 하위 경로 활성 매칭 유지 (`/admin/agent-runs/:runId` → Agent Run 탭 + 관측 그룹 활성)
- [ ] `TopNav` ADMIN_MENU: 드롭다운 내부를 그룹 헤더(섹션 라벨)로 구분해 11개 항목 표시
- [ ] 테스트 갱신/추가:
  - `adminNav.test.ts` — 그룹 구조 검증(그룹 4개, flatten 11개, path 중복 없음, entry 포함). **기존 N1 단언이 10개로 실제(11개)와 어긋나 있음 — 이번에 그룹 flatten 기준으로 정리**
  - `AdminLayout` 테스트 — 그룹 렌더링, 그룹 클릭 → 첫 탭 이동, 탭 바 렌더링·전환, 상세 경로 활성 매칭
  - `TopNav` 테스트 — 그룹 헤더 표시
  - `AppSidebar.test.tsx` A4 — entry 경로 변경(`/admin/users` → `/admin/dashboard`) 반영

### 2.2 Out of Scope

- 11개 관리자 페이지 컴포넌트 자체의 기능/디자인 변경 (각 페이지 내부 헤더는 그대로)
- URL 재편·리다이렉트 (`/admin/org/users` 식 계층 URL 도입 안 함)
- 백엔드 API 변경 (프론트 전용 작업)
- `AdminRoute` 권한 가드 로직 변경
- 메인 앱(비 admin) 영역 TopNav `NAV_MENUS`(데이터/에이전트) 재구성

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | 요구사항 | 우선순위 |
|----|----------|---------|
| FR-01 | 사이드바에 그룹 4개(관측/조직 관리/문서·품질/에이전트 리소스)만 표시된다 | P1 |
| FR-02 | 그룹 클릭 시 해당 그룹의 첫 탭 경로로 이동한다 | P1 |
| FR-03 | 현재 경로가 속한 그룹이 사이드바에서 활성 표시된다 (하위 상세 경로 포함) | P1 |
| FR-04 | 본문 상단 탭 바에 현재 그룹의 하위 항목이 순서대로 표시되고, 클릭 시 해당 페이지로 전환된다 | P1 |
| FR-05 | 현재 페이지에 해당하는 탭이 활성 표시된다 (`/admin/agent-runs/:runId`는 Agent Run 탭 활성) | P1 |
| FR-06 | 기존 11개 URL로 직접 진입해도 올바른 그룹·탭이 활성화된다 | P1 |
| FR-07 | TopNav "관리" 드롭다운이 그룹 헤더로 구분된 목록을 표시하고 각 항목 클릭 시 해당 페이지로 이동한다 | P2 |
| FR-08 | `AppSidebar` "관리자" 클릭 시 `/admin/dashboard`로 진입한다 | P2 |

### 3.2 Non-Functional Requirements

| ID | 요구사항 |
|----|----------|
| NFR-01 | 메뉴 정의는 `adminNav.ts` 단일 소스 유지 — 그룹/탭/드롭다운이 모두 동일 상수에서 파생 |
| NFR-02 | 기존 디자인 시스템 준수 (violet 활성 토큰, `rounded-xl`, `text-[13.5px]` 등 CLAUDE.md 규칙) |
| NFR-03 | 페이지 컴포넌트 11개는 무수정 — 탭 바는 `AdminLayout`이 소유 (라우트 중첩 구조 변경 없음) |
| NFR-04 | TDD: 상수·레이아웃·TopNav 테스트를 구현과 함께 작성 (Red → Green → Refactor) |

---

## 4. 구현 방향 (개요)

> 상세 설계는 Design 문서에서 확정. 여기서는 접근 방향만 기록.

1. **상수 계층** — `adminNav.ts`
   ```ts
   interface AdminNavGroup {
     key: string;          // 'observability' | 'org' | 'docs-quality' | 'agent-resources'
     label: string;        // '관측' | '조직 관리' | '문서·품질' | '에이전트 리소스'
     icon: string;         // 그룹 대표 아이콘 (사이드바용)
     items: AdminNavItem[]; // 기존 항목 재사용 (label/path/icon/description)
   }
   export const ADMIN_NAV_GROUPS: AdminNavGroup[] = [...];
   export const ADMIN_NAV_ITEMS = ADMIN_NAV_GROUPS.flatMap(g => g.items); // 하위 호환
   export const ADMIN_ENTRY_PATH = ADMIN_NAV_GROUPS[0].items[0].path;     // /admin/dashboard
   ```
2. **AdminLayout** — 사이드바는 그룹 4개 렌더링. `location.pathname` → 소속 그룹 판정 유틸(`findGroupByPath`) →
   사이드바 활성 + 본문 상단 탭 바(`<Outlet/>` 위) 렌더링. 매칭 규칙은 기존과 동일하게 exact + `startsWith(path + '/')`.
3. **TopNav** — `ADMIN_MENU` 렌더링 분기: 드롭다운 안에서 `ADMIN_NAV_GROUPS`를 순회하며 그룹 라벨(섹션 헤더) + 항목 렌더링.
   (일반 `NAV_MENUS`는 기존 플랫 렌더링 유지 — 렌더 함수 분기 또는 admin 전용 드롭다운 컴포넌트 분리)
4. **테스트** — 단일 소스 개수 단언은 "그룹 flatten = 전체 항목" 관계 단언으로 교체해
   기존의 하드코딩 개수(10) 어긋남 재발을 방지.

---

## 5. Risks & Considerations

| # | 리스크 | 대응 |
|---|--------|------|
| 1 | 각 페이지가 이미 자체 헤더(타이틀)를 갖고 있어 탭 바와 시각적으로 중복될 수 있음 | 탭 바는 얇은 보조 네비(텍스트 탭 + 하단 보더)로 디자인, 페이지 헤더는 유지. Design 단계에서 스타일 확정 |
| 2 | `adminNav.test.ts` N1이 현재 코드(11개)와 이미 어긋나 있음(10개 단언) | 이번 작업에서 관계 기반 단언으로 교체 — "단일 소스 상수 개수 단언 함정" 재발 방지 |
| 3 | `ADMIN_ENTRY_PATH` 변경으로 관리자 진입 첫 화면이 사용자 관리 → 대시보드로 바뀜 | 의도된 UX 개선 (콘솔 진입 = 현황 파악 우선). `AppSidebar.test.tsx` A4 단언 갱신 필요 |
| 4 | TopNav 드롭다운이 11항목 + 그룹 헤더로 길어짐 | 드롭다운 `max-h` + 스크롤 또는 2컬럼 검토 — Design 단계 결정 |

---

## 6. Acceptance Criteria

- [ ] 사이드바에 그룹 4개만 보이고, 각 그룹 클릭 시 첫 탭 페이지로 이동한다
- [ ] 11개 기존 URL 전부 직접 진입 시 올바른 그룹 활성 + 탭 활성 상태가 된다
- [ ] 탭 클릭으로 그룹 내 페이지 전환이 되고 URL이 기존 경로로 유지된다
- [ ] TopNav "관리" 드롭다운에 그룹 헤더가 표시된다
- [ ] `npm run test:run` — 신규/갱신 테스트 통과 (사전 실패 8건 제외, `--pool=threads`)
- [ ] `npm run type-check` / `npm run lint` 통과

---

## 7. Next Step

- `/pdca design admin-nav-restructure` — 탭 바 컴포넌트 구조·스타일, TopNav 분기 방식, 테스트 케이스 목록 상세 설계
