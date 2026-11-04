# sidebar-agent-list Planning Document

> **Summary**: AppSidebar의 에이전트 목록을 2줄 압축 항목·그룹 접기로 바꾸고, 하단 메뉴를 아이콘 한 줄로 줄여 목록 높이를 확보한다.
>
> **Project**: sangplusbot (idt_front)
> **Author**: 배상규
> **Date**: 2026-11-04
> **Status**: Draft
> **시안**: https://claude.ai/artifact/LRLpeMHw5dicsiKLnz8YRk

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 사이드바에서 에이전트 이름까지 흐린 색으로 표시되고, 하단 메뉴 6줄과 사용자 영역이 세로 공간을 약 280px 차지해 한 화면에 보이는 에이전트가 적다. |
| **Solution** | 에이전트 항목을 이름(진하게)·설명(한 줄 말줄임) 2줄로 압축하고, 그룹 제목을 접기 토글로 바꾸며, 하단 메뉴를 아이콘 한 줄 도크로 바꾼다. 접기 상태는 `layoutStore`에 저장한다. |
| **Function/UX Effect** | 같은 높이에서 보이는 에이전트 수가 늘고, 이름 대비가 높아져 원하는 에이전트를 빨리 찾는다. 자주 쓰지 않는 그룹은 접어 둘 수 있다. |
| **Core Value** | 에이전트 소유자(P2)가 여러 에이전트를 오가며 쓰는 기본 동선의 탐색 비용을 줄인다. API·라우팅·데이터는 바꾸지 않는다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 에이전트 목록의 가시성이 낮고 세로 공간이 하단 메뉴에 밀린다 |
| **WHO** | 사이드바로 에이전트를 골라 대화하는 모든 로그인 사용자, 특히 에이전트를 여러 개 가진 P2 |
| **RISK** | 하단 메뉴를 아이콘만 남기면 메뉴 이름을 알아보기 어려워짐 → 툴팁·aria-label 유지, 기존 테스트의 이름 기반 조회 보존 |
| **SUCCESS** | 1440×900 기준 보이는 에이전트 수 증가, 이름 `sidebar-fg` 적용, 그룹 접기 상태 새로고침 후 유지, 기존 AppSidebar 테스트 통과 |
| **SCOPE** | 프론트 단일 컴포넌트(AppSidebar) + layoutStore 필드 1개. 백엔드·API 변경 없음 |

---

## 1. Overview

### 1.1 Purpose

사이드바 에이전트 목록을 한눈에 훑을 수 있게 만든다. 항목 높이를 줄이고 이름 대비를 높이며, 목록이 쓸 수 있는 세로 공간을 늘린다.

### 1.2 Background

- 현재 `AppSidebar.tsx:298-328`의 에이전트 항목은 버튼 전체가 `text-sidebar-fg-muted`라서 이름이 흐리다. 여백은 `py-2`다.
- 하단 보조 메뉴(즐겨찾기·역할설정·리소스·지식베이스·환경설정·관리자)가 항목당 한 줄씩 차지하고, 사용자 영역은 이메일을 두 번 표시한다.
- 참고 사이트(deepagent-builder.ai)는 하단 메뉴를 아이콘 한 줄로 묶고, 폴더 단위 접기와 이름·설명 2줄 항목을 쓴다. 이번 작업은 배치만 참고하고 색·토큰·선택 표시는 우리 디자인 시스템(`ui-redesign-chat` §5)을 따른다.

### 1.3 Related Documents

- 디자인 토큰·사이드바 규칙: `idt_front/CLAUDE.md` UI 디자인 시스템, `docs/02-design/features/ui-redesign-chat.design.md` §5.5
- 시안(현재/제안 비교): https://claude.ai/artifact/LRLpeMHw5dicsiKLnz8YRk

---

## 2. Scope

### 2.1 In Scope

- [ ] 에이전트 항목 2줄 압축: 이름 `text-sm font-medium text-sidebar-fg` 한 줄 말줄임, 설명 `text-xs` 흐린 톤 한 줄 말줄임, 여백 축소
- [ ] 선택 항목에 `SidebarItem`과 같은 좌측 2px 브랜드 바
- [ ] 이름 첫 글자 미니 아바타. 한 곳(상수 또는 prop)에서 끄면 사라지도록 분리
- [ ] 그룹 제목(고정됨·내 에이전트·구독·포크)을 접기 토글 버튼으로 변경, 개수 표시, `aria-expanded`
- [ ] 그룹 접기 상태를 `layoutStore`(persist 키 `layout-preferences`)에 저장
- [ ] 목록 헤더 오른쪽에 새로고침 아이콘 버튼 (기존 `onRetry`/refetch 재사용)
- [ ] 하단 보조 메뉴 6개를 아이콘 한 줄 도크로 변경. 툴팁(title)·aria-label·활성 표시 유지
- [ ] 사용자 영역 1줄로 압축 (이메일 중복 표시 제거)
- [ ] 설명 전체는 항목 `title` 툴팁으로 확인 가능

### 2.2 Out of Scope

- 폴더 생성·사용자 정의 폴더 (백엔드 필요, 별도 기능)
- 에이전트 관리 화면·필터·숨김 기능 (참고 사이트의 관리 아이콘)
- 접힌 레일(w-16) 상태의 동작 변경 — 현재대로 유지
- 즐겨찾기·역할설정의 실제 기능 연결 (현재 path 없음, 그대로 둠)
- 백엔드 API·스키마 변경

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 에이전트 항목은 이름과 설명 2줄로 표시하고, 각각 한 줄을 넘으면 말줄임한다 | High | Pending |
| FR-02 | 이름은 `text-sidebar-fg`, 설명은 그보다 흐린 톤으로 구분한다 | High | Pending |
| FR-03 | 선택된 에이전트는 활성 배경 + 좌측 2px 브랜드 바로 표시하고 `aria-current`를 유지한다 | High | Pending |
| FR-04 | 이름 첫 글자 아바타를 표시한다. 표시 여부는 한 곳에서 끌 수 있다 | Medium | Pending |
| FR-05 | 그룹 제목을 누르면 그룹이 접히고 펼쳐진다. 제목에 개수와 펼침 상태(`aria-expanded`)를 표시한다 | High | Pending |
| FR-06 | 그룹 접기 상태는 새로고침·재로그인 후에도 유지된다 (`layoutStore` persist) | High | Pending |
| FR-07 | 고정된 에이전트는 이름 옆 별 아이콘을 유지한다 | Medium | Pending |
| FR-08 | 목록 헤더에 새로고침 버튼을 두고 누르면 목록을 다시 불러온다 | Low | Pending |
| FR-09 | 하단 보조 메뉴를 아이콘 한 줄로 표시하고, 각 버튼은 aria-label·툴팁·활성 표시를 가진다. 관리자 버튼은 admin일 때만 보인다 | High | Pending |
| FR-10 | 사용자 영역은 아바타·이메일 한 줄·로그아웃 버튼으로 줄인다 | Medium | Pending |
| FR-11 | 로딩·오류·빈 상태 표시는 기존 동작을 유지한다 | High | Pending |
| FR-12 | 사이드바 접힘(레일) 상태의 기존 동작과 테스트(C1~C3)를 유지한다 | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Accessibility | 모든 아이콘 버튼에 접근 가능한 이름, 그룹 토글은 `aria-expanded`, 키보드로 조작 가능 | RTL `getByRole` 테스트 |
| Design tokens | hex 리터럴·`text-[Npx]`·인라인 색 style 금지, 기존 `sidebar-*`·`brand-*` 토큰만 사용 | 코드 리뷰, grep |
| Persist 호환 | `layout-preferences`에 기존 저장값이 있어도 새 필드 기본값으로 정상 동작 | store 단위 테스트 |
| Responsive | 1440·768·375 폭에서 깨짐 없음 (375에서는 기존처럼 접힌 레일) | Chrome DevTools 스크린샷 |
| Motion | 접기 화살표 회전은 `duration-150`, reduced-motion 전역 규칙 적용 | 수동 확인 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01 ~ FR-12 구현
- [ ] 새 테스트: 그룹 접기·펼치기, 접기 상태 persist, 하단 도크 버튼 이름·이동, 아바타 끄기, 선택 표시
- [ ] 기존 `AppSidebar.test.tsx`(C1~C3, A1~A4, S1~S2) 통과
- [ ] 1440×900에서 보이는 에이전트 수가 현재보다 많음 (전후 스크린샷 비교)

### 4.2 Quality Criteria

- [ ] `npm run lint`, `npm run type-check`, `npm run build` 통과
- [ ] 관련 테스트 통과 (`npm run test:run -- AppSidebar layoutStore`)
- [ ] 콘솔 오류 없음

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 하단 메뉴가 아이콘만 남아 처음 보는 사용자가 의미를 모름 | Medium | Medium | title 툴팁 + aria-label 유지, 아이콘은 기존 lucide 아이콘 그대로 사용 |
| 기존 테스트가 하단 메뉴를 텍스트로 찾음 | Medium | Low | 버튼 aria-label을 기존 라벨과 동일하게 유지해 `getByRole('button', { name })` 조회 보존 |
| persist 스키마에 필드 추가 시 기존 저장값과 충돌 | Low | Low | 새 필드는 선택적, 기본값 빈 배열. `hasPersistedSidebarPreference` 동작 영향 없음 확인 |
| AppSidebar가 400줄을 넘어 비대해짐 | Medium | High | 에이전트 그룹·항목·하단 도크를 `components/layout/sidebar/` 하위 컴포넌트로 분리 (Design에서 확정) |
| 첫 글자 아바타가 시각적으로 시끄러움 | Low | Medium | 상수 하나로 끌 수 있게 분리 (FR-04) |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `idt_front/src/components/layout/AppSidebar.tsx` | Component | 에이전트 목록 영역·하단 메뉴·사용자 영역 마크업 변경, 하위 컴포넌트 분리 |
| `idt_front/src/store/layoutStore.ts` | Zustand store (persist) | 그룹 접기 상태 필드와 토글 액션 추가 |
| `idt_front/src/components/layout/AppSidebar.test.tsx` | Test | 신규 케이스 추가 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| AppSidebar | RENDER | `components/layout/AgentChatLayout.tsx` | None — props 시그니처 유지 (`agents`, `selectedAgentId`, `onSelectAgent`, `isLoading`, `isError`, `onRetry`) |
| layoutStore | READ/WRITE | AppSidebar, AgentChatLayout, `hasPersistedSidebarPreference` | Needs verification — 기존 필드는 그대로, 새 필드만 추가 |
| 하단 메뉴 aria-label | READ | `AppSidebar.test.tsx` A1~A4 ("관리자") | None — 라벨 유지 |

### 6.3 Verification

- [ ] AgentChatLayout에서 사이드바 펼침/접힘·에이전트 선택 정상 동작
- [ ] 기존 persist 값이 있는 브라우저에서 새로고침 시 오류 없음
- [ ] 관리자/일반 사용자 각각 하단 도크 버튼 수 확인

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Selected |
|-------|:--------:|
| Starter | ☐ |
| Dynamic | ☑ (기존 idt_front 구조 그대로) |
| Enterprise | ☐ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 그룹 접기 상태 저장 | 로컬 state / layoutStore persist | layoutStore persist | 사용자 요구(유지), 기존 사이드바 접기 상태와 같은 위치 |
| 아바타 on/off | prop / 모듈 상수 | Design에서 결정 (상수 권장) | 빼기 쉬워야 함. 런타임 상수 export 규칙 준수 (`as const`는 `src/types/`) |
| 컴포넌트 분리 | 단일 파일 / 하위 컴포넌트 | 하위 컴포넌트 | 200줄 초과 시 분리 규칙 |
| 스타일 | Tailwind 토큰 | Tailwind 토큰 | 기존 디자인 시스템 |
| 테스트 | Vitest + RTL | Vitest + RTL | 프로젝트 표준 |

---

## 8. Convention Prerequisites

- [x] `idt_front/CLAUDE.md` 코딩·디자인 규칙
- [x] ESLint / TypeScript 설정
- 컴포넌트 파일에서 런타임 상수 export 금지 (memory 규칙) — 아바타 표시 상수는 파일 내부 상수 또는 `src/types/`·`src/constants/`에 둔다
- 환경변수 추가 없음

---

## 9. Next Steps

1. [ ] `/pdca design sidebar-agent-list` — 컴포넌트 분리 구조, store 필드 형태, 아바타 토글 위치 확정
2. [ ] TDD로 구현 (`/pdca do sidebar-agent-list`)
3. [ ] Chrome DevTools로 1440·768·375 전후 비교

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-04 | Initial draft (참고 사이트 확인·시안 기반) | 배상규 |
