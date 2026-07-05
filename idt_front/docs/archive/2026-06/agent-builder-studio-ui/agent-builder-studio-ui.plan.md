# agent-builder-studio-ui Planning Document

> **Summary**: AgentBuilderPage를 정적 폼에서 LangSmith Studio 스타일의 2-패널 에디터(좌측 구성 패널 + 우측 테스트 채팅)로 재구성하고, 모델/도구/스킬/테스트를 팝업·탭 기반으로 연동한다.
>
> **Project**: idt_front (React 19 + TypeScript + Tailwind v4 + TanStack Query + Zustand)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-06-27
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 현재 에이전트 만들기 페이지가 단일 세로 폼이라 정적이고, 모델·도구·스킬·테스트가 한 화면에 평면 나열되어 빌더 경험이 빈약하다. |
| **Solution** | 좌측 구성 패널(지침·서브에이전트·모델·도구함·미들웨어) + 우측 테스트 채팅의 2-패널 Studio 레이아웃으로 전환. 모델/도구/미들웨어 추가는 모달 팝업, 기능 영역은 우측 탭(테스트/스킬 등)으로 분리. 백엔드 지원 기능(모델·도구·스킬·테스트)만 실제 연동하고, 미지원 영역(미들웨어·서브에이전트·오프너·스케줄·파일·버전)은 '준비중' 비활성 UI로 자리만 배치. |
| **Function/UX Effect** | 한 화면에서 구성→테스트 즉시 반복 가능. 모달 분리로 구성 패널이 간결해지고, 탭 구조로 향후 기능 확장 슬롯 확보. |
| **Core Value** | 정적 폼 → 인터랙티브 에이전트 스튜디오. 기존 백엔드 API 100% 재사용으로 빠른 프론트 전환 + 확장 가능한 골격 확보. |

---

## 1. Overview

### 1.1 Purpose

`src/pages/AgentBuilderPage/index.tsx`의 생성/수정 폼(`FormView`)을 첨부 스크린샷(`docs/img/chat_build_main.png`)과 같은 Studio형 2-패널 에디터로 재설계한다. 모델 설정은 별도 모달(`docs/img/chat_model.png`)로 띄운다.

### 1.2 Background

- 현재 화면은 이름/설명/모델/시스템프롬프트/도구/Temperature가 한 컬럼에 세로로 쌓인 폼으로, 빌더 도구로서의 인터랙션이 부족하다.
- 백엔드는 이미 모델 조회·도구 카탈로그·스킬 attach/detach·SSE/WS 실행 스트리밍을 지원하므로, 프론트 레이아웃 재구성만으로 큰 UX 개선이 가능하다.
- 미들웨어(v2 API)·서브에이전트·스케줄·오프너·모델 파라미터·버전 관리는 프론트 미지원 또는 백엔드 미구현 → 이번 범위에서는 비활성 placeholder로 시각적 자리만 확보하고 후속 PDCA로 분리한다.

### 1.3 Related Documents

- 디자인 가이드: `idt_front/CLAUDE.md` (UI 디자인 시스템 §색상 토큰/레이아웃/컴포넌트 스타일)
- 화면 참조: `docs/img/chat_build_main.png` (메인), `docs/img/chat_model.png` (모델 설정 팝업)
- 선행 연동 plan: `docs/01-plan/features/agent-builder-api-integration.plan.md`
- 백엔드 라우터: `idt/src/api/routes/agent_builder_router.py`

---

## 2. Scope

### 2.1 In Scope

- [ ] **목록 화면 유지** — 기존 카드 그리드(`ListView`)를 진입점으로 유지. 카드 클릭/"새 에이전트" 시 Studio 에디터로 전환 (라우팅/뷰 전환 최소 변경).
- [ ] **2-패널 Studio 레이아웃** — 좌측 구성 패널 + 우측 테스트 패널(분할). 상단 헤더(에이전트명/설명, 저장, 비활성 버전 셀렉터·아이콘들).
- [ ] **좌측 구성 패널 섹션** (collapsible):
  - [ ] 지침(시스템 프롬프트) — textarea, 확장 토글, 글자수 카운터
  - [ ] 모델 — 현재 모델 칩 표시 + 설정(⚙) 버튼 → **모델 설정 모달** (연동)
  - [ ] 도구함 — 추가된 도구 목록 + "+도구" 버튼 → **도구 추가 모달** (연동)
  - [ ] 서브에이전트 — "서브에이전트가 없습니다" + ⚙ (비활성 placeholder)
  - [ ] 미들웨어 — "추가된 미들웨어가 없습니다" + "+미들웨어" (비활성 placeholder)
- [ ] **모델 설정 모달** (`chat_model.png`) — 모델 선택(드롭다운, API키 미등록 경고), Temperature 실제 연동. 최대 토큰/Top P/Top K는 UI만 배치(비활성·미저장). "모델 관리" 링크는 비활성.
- [ ] **도구 추가 모달** — `useToolCatalog` 연동, 내부/MCP 도구 추가·제거. RAG 도구 선택 시 `RagConfigPanel` 연동 유지.
- [ ] **우측 테스트 패널** — 탭 바(테스트/스킬은 활성, Fix에이전트/오프너/파일/스케줄/설정은 비활성). 테스트 탭에서 `useAgentRunStream` 기반 실시간 대화. "새 대화" 버튼, 빈 상태, 입력창.
- [ ] **스킬 탭** — 기존 `AgentSkillPanel`(attach/detach) 우측 탭으로 이동/연동 (수정 모드 한정 유지).
- [ ] **폼/비주얼 탭** — '폼'만 활성, '비주얼'은 비활성 placeholder.
- [ ] **저장/취소 흐름** — 기존 `useCreateBuilderAgent`/`useUpdateBuilderAgent` 재사용. 생성 단계 MCP 도구 제외 규칙 유지.
- [ ] **테스트 코드** — 신규 컴포넌트/모달에 대한 Vitest + RTL 테스트 (TDD).

### 2.2 Out of Scope

- 미들웨어 빌더 UI 실제 연동 (v2 API 연동은 후속 plan)
- 서브에이전트 구성/연결 UI 실제 동작
- 스케줄·오프너 기능 (백엔드 미구현)
- 모델 파라미터(max_tokens/top_p/top_k) 백엔드 저장 (agent 스키마 변경 없음)
- 진짜 버전 관리(v0/v1, 버전 히스토리) — 헤더 셀렉터는 표시용 비활성
- 파일 첨부 빌더 UI, "Fix 에이전트", "설정" 탭, "비주얼" 탭
- 모델 관리 어드민 페이지

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 카드 목록에서 카드 클릭/"새 에이전트" 시 Studio 에디터(2-패널)로 전환, "취소"로 목록 복귀 | High | Pending |
| FR-02 | 좌측 구성 패널: 지침/모델/도구함 섹션이 collapsible로 렌더되고 현재 폼 상태와 양방향 바인딩 | High | Pending |
| FR-03 | 모델 ⚙ 클릭 시 모델 설정 모달 오픈, 모델 선택+Temperature 변경이 폼 상태에 반영, 저장 시 닫힘 | High | Pending |
| FR-04 | 모델 모달 내 최대토큰/Top P/Top K는 비활성 입력으로 표시(저장 영향 없음), API키 미등록 경고 노출 | Medium | Pending |
| FR-05 | "+도구" 클릭 시 도구 추가 모달 오픈, 카탈로그에서 추가/제거, 생성 모드 MCP 도구 비활성 규칙 유지 | High | Pending |
| FR-06 | RAG 도구(`internal:internal_document_search`) 추가 시 RAG 설정 패널 노출·연동 | Medium | Pending |
| FR-07 | 우측 테스트 탭에서 입력 전송 시 `useAgentRunStream`으로 토큰 스트리밍 응답 표시 (수정 모드: 저장된 agent_id 기준) | High | Pending |
| FR-08 | 우측 스킬 탭에서 `AgentSkillPanel`로 스킬 attach/detach (수정 모드 한정) | Medium | Pending |
| FR-09 | 서브에이전트/미들웨어/오프너/스케줄/파일/Fix에이전트/설정/비주얼/버전 셀렉터는 비활성 placeholder로 시각 배치 + "준비중" 툴팁 | Medium | Pending |
| FR-10 | 저장/수정/삭제 및 결과 다이얼로그 동작은 기존 동작 보존 | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Layout | `AgentChatLayout` 내부 overflow 규칙 준수 (자체 스크롤 컨테이너) | 수동 + CLAUDE.md §페이지 래퍼 규칙 |
| Design 일관성 | 색상/버튼/모달/타이포 토큰을 `idt_front/CLAUDE.md` UI 시스템에서만 사용 | 코드 리뷰 |
| 테스트 | 신규 훅/컴포넌트 단위 테스트, 모달 상호작용 RTL 테스트 | `npm run test:run` (Windows: `--pool=threads`) |
| 회귀 방지 | 기존 생성/수정/삭제/도구토글/RAG 동작 보존 | 기존 + 신규 테스트 통과 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01 ~ FR-10 구현 완료
- [ ] 신규 컴포넌트(Studio 레이아웃·모델 모달·도구 모달·테스트 패널) 테스트 작성·통과
- [ ] 기존 AgentBuilder 테스트 회귀 없음
- [ ] `npm run lint` / `npm run type-check` 통과
- [ ] 스크린샷(`chat_build_main.png`/`chat_model.png`)과 레이아웃 시각 일치

### 4.2 Quality Criteria

- [ ] 컴포넌트 단일 책임 — 200줄 초과 시 분리 (`index.tsx`에서 패널/모달 컴포넌트 분리)
- [ ] Zero lint error / 빌드 성공
- [ ] 직접 axios 호출 없음 (services/hooks 레이어 경유)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 단일 `index.tsx`(742줄)에 모든 로직 집중 → 비대화 | Medium | High | 컴포넌트 분리: `components/agent-builder/` 하위에 `StudioLayout`, `ModelSettingsModal`, `ToolPickerModal`, `AgentTestPanel`, `LeftConfigPanel` 등으로 추출 |
| 생성 전(미저장) 상태에서 테스트 패널 실행 불가 (agent_id 없음) | Medium | High | 생성 모드에서는 테스트 탭에 "저장 후 테스트 가능" 안내. 수정 모드(저장된 agent_id)에서만 스트리밍 활성 |
| placeholder가 동작하는 것처럼 보여 사용자 혼란 | Low | Medium | 비활성 스타일(opacity/disabled) + "준비중" 툴팁 명시 |
| 모델 모달의 미저장 파라미터가 저장되는 것으로 오해 | Low | Medium | 비활성 입력 + 헬퍼 텍스트로 "현재 미적용" 표기 |
| `AgentChatLayout` overflow로 2-패널 스크롤 깨짐 | Medium | Medium | 좌/우 패널 각각 자체 `overflowY:auto` 스크롤 컨테이너 적용 (패턴 A) |

---

## 6. Architecture Considerations

### 6.1 Project Level

Dynamic (React SPA + 백엔드 API 연동). 신규 백엔드 없음 — 프론트 레이어만 변경.

### 6.2 Key Architectural Decisions

| Decision | Selected | Rationale |
|----------|----------|-----------|
| 뷰 전환 | 기존 `ViewMode`('list'\|'create'\|'edit') 유지, 'create'/'edit'를 Studio 레이아웃으로 렌더 | 라우팅 변경 최소화, 기존 목록·삭제·저장 흐름 보존 |
| 상태 관리 | 기존 `form: AgentBuilderFormData` useState 유지, 모달은 로컬 open 상태 | 서버상태는 TanStack Query, 폼은 로컬 — CLAUDE.md 규칙 준수 |
| 모달 | 공통 패턴 신규 모달 컴포넌트(Portal/overlay) — `ConfirmDialog` 스타일 참조 | 일관된 모달 UX |
| 테스트 스트리밍 | 기존 `useAgentRunStream`(WS) 재사용 | 신규 스트리밍 로직 불필요 |
| 컴포넌트 위치 | `src/components/agent-builder/` 하위 신규 컴포넌트 | 기존 `RagConfigPanel`/`AgentSkillPanel`와 동일 디렉토리 |

### 6.3 Folder Structure Preview

```
src/
├── pages/AgentBuilderPage/index.tsx         # 뷰 전환 오케스트레이션 (슬림화)
├── components/agent-builder/
│   ├── RagConfigPanel.tsx                    # (기존)
│   ├── AgentSkillPanel.tsx                   # (기존, 우측 탭으로 이동)
│   ├── StudioLayout.tsx                      # (신규) 2-패널 셸 + 헤더
│   ├── LeftConfigPanel.tsx                   # (신규) 지침/모델/도구함/서브에이전트/미들웨어 섹션
│   ├── ModelSettingsModal.tsx               # (신규) chat_model.png 팝업
│   ├── ToolPickerModal.tsx                  # (신규) 도구 추가 팝업
│   ├── AgentTestPanel.tsx                   # (신규) 우측 탭바 + 테스트 채팅
│   └── PlaceholderSection.tsx               # (신규) '준비중' 공통 비활성 블록
└── (hooks/types/services는 기존 재사용)
```

---

## 7. Convention Prerequisites

### 7.1 Existing Conventions

- [x] `idt_front/CLAUDE.md` UI 디자인 시스템(색상/레이아웃/컴포넌트/타이포/간격) 존재 → 그대로 준수
- [x] TanStack Query + Zustand + 절대경로(`@/`) import 규칙 존재
- [x] Vitest + RTL + MSW 테스트 규칙 존재

### 7.2 To Verify

| Category | Current | To Apply |
|----------|---------|----------|
| 모달 패턴 | `ConfirmDialog` 존재 | 동일 overlay/포커스 스타일로 신규 모달 작성 |
| 스크롤 래퍼 | 패턴 A/B 규정 | 2-패널 각각 자체 스크롤 컨테이너 |
| 테스트 풀 | Windows forks 타임아웃 이슈 | `vitest --pool=threads`로 실행 |

### 7.3 Environment Variables

추가 없음 (기존 `VITE_API_BASE_URL`, `VITE_WS_URL` 사용).

---

## 8. Implementation Order (Design 단계 상세화 예정)

1. [ ] 컴포넌트 분리 리팩토링: `index.tsx`에서 `LeftConfigPanel`/`AgentTestPanel` 골격 추출 (테스트 우선)
2. [ ] `StudioLayout` 2-패널 셸 + 헤더(저장/취소/비활성 아이콘) 구현
3. [ ] `ModelSettingsModal` 구현 + 모델 섹션 ⚙ 연결 (Temperature 연동, 나머지 비활성)
4. [ ] `ToolPickerModal` 구현 + 도구함 "+도구" 연결 (RAG 패널 연동)
5. [ ] `AgentTestPanel` 탭바 + 테스트 채팅(`useAgentRunStream`) + 스킬 탭(`AgentSkillPanel`)
6. [ ] `PlaceholderSection`으로 서브에이전트/미들웨어/오프너/스케줄/파일/버전/비주얼 비활성 배치
7. [ ] 회귀 테스트 + lint + type-check + 시각 검증

---

## 9. Next Steps

1. [ ] 설계 문서 작성 (`/pdca design agent-builder-studio-ui`) — 컴포넌트 props 계약, 모달 상태 머신, 테스트 패널 생성/수정 모드 분기 상세화
2. [ ] 사용자 리뷰/승인
3. [ ] 구현 시작 (`/pdca do agent-builder-studio-ui`)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-06-27 | 초기 초안 (스코프 4개 의사결정 반영) | 배상규 |
