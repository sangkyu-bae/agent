# Wiki Navigation Planning Document

> **Summary**: 위키 관리 페이지(`/admin/wiki`) 진입 네비게이션 추가 + 정제 폼 드롭다운 개선 + 사용자용 에이전트 지식 페이지 진입점 추가 (프론트엔드 전용)
>
> **Project**: sangplusbot (idt_front)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-07-21
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 위키 관리 페이지(`WikiPage`, `/admin/wiki`)는 구현·라우팅까지 완료되어 있으나 관리자 메뉴(`ADMIN_NAV_ITEMS`)에 항목이 없어 URL 직접 입력 외에는 진입이 불가능하다. 또한 정제 실행 폼은 agent_id/컬렉션명을 수동 타이핑해야 하고, 사용자용 에이전트 지식 페이지도 스토어 모달 경유로만 접근된다 |
| **Solution** | `ADMIN_NAV_ITEMS`에 '위키 관리' 항목 1건 추가(사이드바+TopNav 동시 노출), WikiPage 정제 폼의 수동 입력을 기존 목록 API 재사용 드롭다운으로 교체, 채팅 헤더에 현재 에이전트의 지식 페이지 링크 추가 |
| **Function/UX Effect** | 관리자가 메뉴 클릭만으로 위키 관리에 진입하고, agent_id를 외우지 않고 드롭다운 선택으로 정제를 실행하며, 일반 사용자는 대화 중인 에이전트의 지식을 헤더에서 한 번에 열람 |
| **Core Value** | '기능은 있는데 노출이 없던' 위키 관리·열람 경로를 완성하여 기 구축된 위키 인프라(LLM-WIKI-001, wiki-user-facing)의 실사용률을 끌어올림 — 백엔드 변경 0, 마이그레이션 0 |

---

## 1. Overview

### 1.1 Purpose

위키 관련 화면 3곳의 **진입 동선 누락**을 해소한다. 신규 화면 개발이 아니라 기존 완성 화면(WikiPage, AgentKnowledgePage)으로 가는 길을 잇는 프론트엔드 전용 작업이다.

### 1.2 Background (현황 실측)

- `WikiPage`(`idt_front/src/pages/WikiPage/index.tsx`)는 정제 실행 + 거버넌스 목록까지 완성, `App.tsx:92`에 `/admin/wiki` 라우트 등록됨
- 그러나 `src/constants/adminNav.ts`의 `ADMIN_NAV_ITEMS`(9개 항목)에 위키 항목이 **없음** → 관리자 사이드바(`AdminLayout`)와 TopNav '관리' 드롭다운 어디에도 미노출
- `ADMIN_NAV_ITEMS`는 AdminLayout 사이드바 + TopNav 드롭다운이 공유하는 **단일 소스** → 한 곳 추가로 양쪽 해결
- WikiPage 정제 폼: `agentId`/`collectionName`을 `<input>` 수동 타이핑 (오타·ID 암기 부담)
- 사용자용 지식 페이지(`/agents/:agentId/knowledge`): 진입 경로가 에이전트 스토어 상세 모달 → 워크스페이스 → 지식 링크 경유뿐. 채팅 화면(`ChatPage`)에서 직접 진입 불가
- 재사용 가능 데이터 소스: 컬렉션 목록 `RAG_TOOL_COLLECTIONS`(`ragToolService.getCollections`), 에이전트 목록 `AGENT_STORE_LIST`/`AGENT_MY`(디자인 단계에서 확정)

### 1.3 Related Documents

- 위키 관리 페이지: `idt_front/src/pages/WikiPage/` (LLM-WIKI-001)
- 관리자 메뉴 단일 소스: `idt_front/src/constants/adminNav.ts`
- 사용자용 지식 브라우저: `idt_front/src/pages/AgentKnowledgePage/` (wiki-user-facing 완료분)
- 채팅 헤더: `idt_front/src/components/layout/ChatHeader.tsx`, 사용처 `pages/ChatPage/index.tsx:314`

---

## 2. Scope

### 2.1 In Scope

- [ ] **S1. 관리자 메뉴 항목 추가**: `ADMIN_NAV_ITEMS` 맨 뒤(Skill 관리 다음)에 '위키 관리'(`/admin/wiki`) 추가 — 사이드바·TopNav 동시 노출
- [ ] **S2. 정제 폼 드롭다운화**: WikiPage의 agent_id/컬렉션명 텍스트 입력을 기존 목록 API 재사용 드롭다운(`Dropdown` 공용 컴포넌트)으로 교체
- [ ] **S3. 사용자용 위키 진입점**: 채팅 헤더에 현재 선택 에이전트의 워크스페이스(`/agents/:id/workspace`) 링크 추가 (SUPER 에이전트 선택 시 미노출). 워크스페이스는 구성 허브로, 지식 페이지(`/knowledge`)로 가는 "전체 지식 보기" 링크를 이미 내장 → 지식 열람은 한 클릭 거리

### 2.2 Out of Scope

- 백엔드 API 신규/변경 (기존 목록 API만 재사용)
- WikiPage 거버넌스 기능(승인/반려/폐기) 자체의 변경
- AgentKnowledgePage/AgentWorkspacePage 내부 UI 변경
- 위키 목록 필터의 드롭다운화 (정제 실행 폼만 대상 — 필터 확장은 후속 판단)
- 사이드바(AppSidebar) 에이전트 목록 항목별 지식 링크 (채팅 헤더 1곳으로 시작)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `ADMIN_NAV_ITEMS` 마지막에 '위키 관리' 항목(label/path/icon/description) 추가, path=`/admin/wiki` | High | Pending |
| FR-02 | 관리자 사이드바에서 `/admin/wiki` 및 하위 경로 활성(active) 하이라이트 동작 | High | Pending |
| FR-03 | TopNav '관리' 드롭다운에 '위키 관리' 자동 노출 (단일 소스 공유 확인) | High | Pending |
| FR-04 | WikiPage 정제 폼: 에이전트 선택 드롭다운 (목록 API 재사용, 이름 표시 + id 전송) | High | Pending |
| FR-05 | WikiPage 정제 폼: 컬렉션 선택 드롭다운 (`ragToolService.getCollections` 재사용) | High | Pending |
| FR-06 | 드롭다운 로딩/에러/빈 목록 상태 처리 (기존 페이지 관례 준수) | Medium | Pending |
| FR-07 | ChatHeader에 워크스페이스 링크 노출: 사용자 에이전트 선택 시에만, `/agents/{id}/workspace` 이동 (지식은 워크스페이스 내 기존 링크로 도달) | High | Pending |
| FR-08 | SUPER(또는 에이전트 미선택) 상태에서는 워크스페이스 링크 미노출 | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 회귀 안전 | 기존 관리자 메뉴 9개 항목·기존 ChatHeader 동작 무변경 | 기존 테스트 통과 (AppSidebar/TopNav 테스트 포함) |
| 계약 유지 | 정제 요청 페이로드(`agent_id`, `collection_name`) 불변 — 입력 UI만 교체 | useWiki 훅/MSW 핸들러 기존 테스트 통과 |
| 테스트 | 신규 동작 Vitest+RTL+MSW 테스트 선행 (TDD) | `--pool=threads` 로 실행 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] 관리자 계정으로 사이드바/TopNav 양쪽에서 '위키 관리' 클릭 → WikiPage 진입 확인
- [ ] 정제 폼에서 에이전트·컬렉션을 드롭다운으로 선택해 정제 실행 가능 (수동 타이핑 제거)
- [ ] 채팅 화면에서 사용자 에이전트 선택 시 헤더 링크로 워크스페이스 진입(→ 지식 페이지 한 클릭 도달), SUPER 선택 시 링크 없음
- [ ] 신규 테스트 전부 통과 + 기존 프론트 테스트 무회귀 (사전 실패 8건 제외 기준)

### 4.2 Quality Criteria

- [ ] TDD 순서 준수 (테스트 → 실패 → 구현 → 통과)
- [ ] TypeScript 에러 0, 기존 컴포넌트 스타일 관례(아이콘·클래스) 일치

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 에이전트 목록 API 선택 오류 (스토어 목록엔 미공개 에이전트 누락 가능) | Medium | Medium | 디자인 단계에서 `AGENT_STORE_LIST` vs `AGENT_MY` 응답 범위 비교 후 확정, 드롭다운 외 직접 입력 fallback 유지 여부도 함께 결정 |
| ChatHeader props 확장이 기존 ChatPage 렌더 테스트에 영향 | Low | Low | 신규 prop은 optional로 additive 설계 (기존 호출부 무수정 시 동작 동일) |
| 관리자 메뉴 항목 증가로 사이드바 스크롤 발생 | Low | Low | 항목 1건 추가 수준 — 현행 레이아웃 유지, 문제 시 후속 |
| jsdom 폼 검증/드롭다운 테스트 함정 | Low | Medium | 기존 `Dropdown` 공용 컴포넌트 재사용으로 검증 로직 최소화 |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules | Web apps | ☐ |
| **Enterprise** | Strict layer separation | 기존 프로젝트 구조 | ☑ |

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 관리자 메뉴 노출 방식 | AdminLayout 하드코딩 / `ADMIN_NAV_ITEMS` 추가 | `ADMIN_NAV_ITEMS` 추가 | 사이드바+TopNav 단일 소스 관례 유지, 1곳 수정 |
| 메뉴 위치 | 계열별 재배치 / 맨 뒤 추가 | 맨 뒤 (Skill 관리 다음) | 기존 순서 무변경 — 사용자 확정 |
| 에이전트 드롭다운 데이터 | 신규 admin API / 기존 목록 API 재사용 | 기존 API 재사용 | 백엔드 변경 0 원칙, 구체 엔드포인트는 Design에서 확정 |
| 사용자 진입점 위치 | AppSidebar 항목별 링크 / ChatHeader 링크 | ChatHeader | 현재 대화 컨텍스트와 일치, 변경 표면 최소 |
| 진입 목적지 | `/knowledge` 직행 / `/workspace` 허브 | `/agents/:id/workspace` | 워크스페이스가 정보·스킬·지식 요약을 아우르는 허브이고 knowledge와 상호 링크 기 구축 — 헤더 버튼 1개로 전체 도달 |
| ChatHeader 확장 방식 | 내부에서 스토어 접근 / props 추가 | optional props (additive) | 기존 호출부 무영향, 테스트 용이 |

### 6.3 변경 대상 파일 (예상)

```
idt_front/src/
├── constants/adminNav.ts                 # S1: 항목 추가 (유일한 필수 변경)
├── pages/WikiPage/index.tsx              # S2: 폼 입력 → 드롭다운
├── pages/WikiPage/WikiPage.test.tsx      # S2: 테스트 갱신/추가
├── components/layout/ChatHeader.tsx      # S3: 지식 링크 (optional prop)
├── pages/ChatPage/index.tsx              # S3: agentId 전달
└── (신규) ChatHeader.test.tsx 또는 기존 테스트 확장
```

---

## 7. Convention Prerequisites

- [x] 관리자 메뉴 단일 소스 관례 (`adminNav.ts` 주석에 명시됨)
- [x] Heroicons outline path 문자열 아이콘 관례
- [x] Vitest `--pool=threads`, MSW per-file listen 관례
- [x] 공용 `Dropdown` 컴포넌트 존재 (`components/common/Dropdown`)
- 환경변수 신규 필요 없음

---

## 8. Implementation Guide

### 8.1 구현 순서

```
1. S1  adminNav.ts 항목 추가 (+ AppSidebar/TopNav 기존 테스트 확인, 필요 시 노출 테스트 추가)
2. S2  WikiPage 드롭다운: 테스트 먼저 (선택 → distill 페이로드 검증) → 구현
3. S3  ChatHeader 링크: 테스트 먼저 (agent 유/무 노출 분기) → 구현 → ChatPage 배선
4. 전체 프론트 테스트 회귀 확인
```

### 8.2 참고 선례

- '데이터는 있고 노출만 없던' 패턴: expose-user-department 사이클과 동일 유형
- active 하이라이트 하위 경로 매칭: `AdminLayout`이 이미 `startsWith` 처리 → 추가 작업 불필요

---

## 9. Next Steps

1. [ ] Write design document (`/pdca design wiki-navigation`) — 에이전트 목록 API 확정 포함
2. [ ] 구현 (TDD)
3. [ ] Gap 분석 (`/pdca analyze wiki-navigation`)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-21 | Initial draft (범위 3종 확정: 메뉴+드롭다운+사용자 진입점) | 배상규 |
