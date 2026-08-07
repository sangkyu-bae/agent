# Agent Settings Tab Planning Document

> **Summary**: 에이전트 빌더 우측 패널의 비활성 placeholder인 **설정 탭 활성화** — Recursion Limit(최대 반복 횟수) 입력을 기존 `agent_definition.max_iterations`(agent-recursion-limit, 백엔드 완비)에 배선하고, MCP 서버·Webhook·Telegram 연동 3개 섹션은 비활성 토글 + "준비중" 스텁으로 노출 (실기능 후속)
>
> **Project**: sangplusbot (idt_front 프론트엔드 전용 — 백엔드 diff 0)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-08-07
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 빌더 우측 패널의 설정 탭이 `enabled: false` placeholder로 잠겨 있어(AgentTestPanel.tsx:60) 에이전트 실행 설정을 UI에서 만질 수 없다. 특히 supervisor 반복 한도 `max_iterations`는 백엔드가 create/update/detail 전 구간 지원(V045 + IterationLimitPolicy, 기본 25 · 범위 10~1000)함에도 프론트 폼·요청 타입에 필드 자체가 없어 **모든 에이전트가 기본값 25에 고정** — "데이터는 있고 노출 경로만 없다" 패턴의 재현 |
| **Solution** | ① 설정 탭 활성화 + SettingsPanel 신설(목표 UI: docs/img/setting.png) ② Recursion Limit 입력을 `AgentBuilderFormData.maxIterations`로 폼에 편입 — create/update 페이로드에 `max_iterations` 전송, edit 프라임 시 detail 값 역주입 (백엔드 무변경, additive 계약 확장) ③ MCP 서버·Webhook·Telegram 섹션은 레이아웃·안내문만 그리고 토글은 disabled + "준비중" 툴팁 (저장 페이로드 미포함) ④ 저장은 기존 StudioHeader 저장 버튼에 통합 (탭 내 별도 저장 없음) |
| **Function/UX Effect** | P2(에이전트 소유자)가 복잡한 작업용 에이전트의 반복 한도를 25 → 최대 1000까지 셀프서비스로 조정 가능. 무한 루프 방지 개념·기본값·범위가 안내문으로 노출되고, 곧 제공될 MCP/Webhook/Telegram 연동의 자리와 형태를 미리 보여줘 기능 로드맵이 UI에서 읽힌다 |
| **Core Value** | agent-recursion-limit(V045)이 만들어 둔 백엔드 가치의 마지막 마일 배선 — 마이그레이션 0·백엔드 0으로 회귀 반경 최소. 스텁 3종은 오해 소지 없는(비활성+준비중) 방식으로 확장 자리만 예약해 일반화 우선 원칙 유지 |

---

## 1. Overview

### 1.1 Purpose

`/agent-builder` 빌더 화면(StudioLayout) 우측 패널의 설정 탭을 활성화하고,
목표 시안(`docs/img/setting.png`)의 4개 섹션 중 **Recursion Limit만 실기능**으로,
나머지 3개(MCP 서버 / Webhook / Telegram 연동)는 **비활성 스텁**으로 구현한다.

### 1.2 Background (2026-08-07 코드 조사로 확정)

**현재 상태**:

- `AgentTestPanel.tsx:53-61` — 탭 정의에서 `{ id: 'settings', label: '설정', enabled: false }`.
  비활성 탭은 `disabled` + "준비중" 툴팁으로 렌더링되고 콘텐츠 분기 자체가 없다.
- `RightTabId` 타입(agentBuilder.ts:143)에 `'settings'`는 이미 존재 — 타입 확장 불필요.

**Recursion Limit의 백엔드 현황 (완비 — 이번 기능은 프론트 배선만)**:

| 구간 | 위치 | 상태 |
|------|------|------|
| DB | `agent_definition.max_iterations` (V045, DEFAULT 25) | ✅ |
| 도메인 정책 | `IterationLimitPolicy` — DEFAULT 25 / MIN 10 / MAX 1000, recursion_limit 파생 | ✅ |
| create API | `CreateAgentRequest.max_iterations` (ge=10, le=1000, 기본 25) | ✅ |
| update API | `UpdateAgentRequest.max_iterations` (optional) + use_case + repo update() 화이트리스트 | ✅ |
| detail API | 응답에 `max_iterations` 포함 (프론트 테스트 픽스처에서 확인) | ✅ |
| 실행 | `run_agent_use_case.py:558,660` — SupervisorConfig + LangGraph recursion_limit 파생 | ✅ |

**프론트 결손 (이번 작업 대상)**:

- `CreateBuilderAgentRequest` / `UpdateBuilderAgentRequest` / `AgentBuilderFormData`에
  max_iterations 계열 필드 없음 (agentBuilder.ts)
- `mapDetailToForm`(agentDetailMapping.ts)이 detail의 `max_iterations`를 버림
- `AgentBuilderPage.handleSave`의 create/update 페이로드에 미포함

**사전 결정 사항 (2026-08-07 사용자 확정)**:

1. **값 배선**: `model_call_limit` 미들웨어(별개 개념 — run당 LLM 호출 상한, 기본 10)가 아니라
   **기존 `max_iterations` 재사용**. 시안의 "기본값: 25 · 최대 1000"도 이와 일치.
2. **범위 표기**: 시안은 "1 - 1000"이나 백엔드 정책 MIN=10 — **UI를 10~1000으로 표기** (정책 무수정).
3. **스텁 수준**: MCP/Webhook/Telegram은 **토글 disabled + "준비중"** — 동작 착시 없는 시각 스텁.
4. **저장 방식**: 시안의 탭 내 저장 버튼은 채택하지 않고 **기존 StudioHeader 저장 버튼에 통합**
   (create=폼 일부로 staged, edit=update 페이로드 포함 — 스킬·스케줄 탭 패턴과 일관).

### 1.3 Related Documents

- 반복 한도 원설계: `docs/archive/2026-07/agent-recursion-limit/` (Plan/Design/Report)
- 빌트인 미들웨어(비채택 대안의 맥락): builtin-middleware Do (V056 `middleware_catalog.model_call_limit`)
- 화면↔API 절단면: `docs/wiki/frontend/screens/agent-screens.md` (update 화이트리스트·에코백 함정)
- 계약 확장 관례: `docs/wiki/conventions/additive-contract-extension.md` (optional 필드 additive)
- 노출 결손 패턴: `docs/wiki/conventions/data-exists-exposure-missing.md`

---

## 2. Scope

### 2.1 In Scope

- [ ] **S1. 설정 탭 활성화**: `AgentTestPanel` 탭 정의 `settings.enabled: true` + 콘텐츠 분기 추가.
      create/edit 모드 모두 활성.
- [ ] **S2. SettingsPanel 컴포넌트 신설** (`components/agent-builder/settings/SettingsPanel.tsx`):
      시안의 4개 섹션 구성 — 헤더 안내문("에이전트 실행 설정을 관리합니다") + Recursion Limit +
      MCP 서버 + Webhook + Telegram 연동. 자체 스크롤 컨테이너 (AgentChatLayout overflow:hidden 대응).
- [ ] **S3. Recursion Limit 실기능**:
      number 입력(범위 10~1000 안내) + 기본값 복원(↺) 버튼 + 설명·기본값 안내문.
      `form.maxIterations`에 바인딩 — 입력 검증(범위 이탈 시 인라인 에러 또는 blur clamp, Design 확정).
- [ ] **S4. 폼·요청 타입 배선** (`types/agentBuilder.ts` + detail 응답 타입):
      `AgentBuilderFormData.maxIterations: number`(DEFAULT_FORM=25),
      `CreateBuilderAgentRequest.max_iterations?: number`,
      `UpdateBuilderAgentRequest.max_iterations?: number`,
      detail 응답 타입에 `max_iterations` 선언(누락 시).
- [ ] **S5. 저장·프라임 배선** (`AgentBuilderPage`):
      create 페이로드에 `max_iterations: form.maxIterations` 포함,
      update 페이로드에도 포함(항상 전송 — 프라임 값 기반이라 안전),
      `mapDetailToForm`에서 detail.max_iterations → maxIterations 프라임 (결측 시 25 폴백).
- [ ] **S6. 스텁 3종 섹션**: MCP 서버 / Webhook / Telegram 연동 —
      시안의 안내문·아이콘·토글 UI를 그리되 토글은 `disabled` + "준비중" 툴팁,
      Telegram은 "연결되지 않음 / 비활성화됨" 상태 표기. 상태·페이로드 없음(순수 정적).
- [ ] **S7. 테스트** (TDD — Red 먼저):
      ① SettingsPanel 단위(렌더·입력·복원 버튼·범위 검증·스텁 disabled 단언)
      ② AgentBuilderPage 통합(create 페이로드 max_iterations 포함 / edit 프라임 → 수정 → update 페이로드 반영)
      ③ mapDetailToForm 단위(프라임·결측 폴백 25)

### 2.2 Out of Scope

- **백엔드 변경 전부** — API·스키마·정책·마이그레이션 무변경 (IterationLimitPolicy MIN=10 유지)
- **MCP 서버 / Webhook / Telegram 실기능** — 각각 별도 PDCA 사이클로 후속
  (MCP 서버 노출·API Key 발급·Telegram Bot 연결 등 백엔드 신설 필요)
- `model_call_limit` 미들웨어의 에이전트별 config 오버라이드 (`agent_middleware.config` 예약 필드) — 후속
- 시안의 탭 내 별도 "저장" 버튼 — StudioHeader 저장 통합으로 대체 (결정 4)
- 좌측 LeftConfigPanel·ModelSettingsModal 등 기존 구성 UI 변경
- 오프너·파일 탭 (여전히 비활성 placeholder 유지)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 설정 탭이 create/edit 모드 모두에서 클릭 가능하고 SettingsPanel이 렌더링된다 | High | Pending |
| FR-02 | Recursion Limit 입력 기본값은 25이며, 허용 범위 10~1000과 기본값 안내문이 표시된다 | High | Pending |
| FR-03 | 범위(10~1000) 밖 입력은 저장 페이로드에 실리지 않는다 — 인라인 에러 또는 clamp (방식은 Design 확정, 백엔드 422 방어 아님을 전제로 프론트에서 선차단) | High | Pending |
| FR-04 | 복원(↺) 버튼 클릭 시 값이 기본값 25로 되돌아간다 | Medium | Pending |
| FR-05 | create 저장 시 `max_iterations`가 요청에 포함되어 신규 에이전트에 반영된다 | High | Pending |
| FR-06 | edit 진입 시 detail의 `max_iterations`가 입력에 프라임되고, 수정 후 저장 시 update 요청에 포함된다 (결측 detail은 25 폴백) | High | Pending |
| FR-07 | MCP 서버·Webhook·Telegram 섹션이 시안 레이아웃으로 노출되되 토글은 disabled + "준비중" 툴팁이며 저장 페이로드에 어떤 값도 추가하지 않는다 | Medium | Pending |
| FR-08 | 설정 탭 추가로 기존 탭(Fix/테스트/스킬/스케줄) 동작·저장 페이로드가 변하지 않는다 (max_iterations 추가 제외) | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 회귀 안전 | 기존 vitest 무회귀 (사전 실패 8건 제외 기준), `--pool=threads` 실행 | `npm run test:run -- --pool=threads` |
| API 계약 | 백엔드 무변경 — 프론트가 기존 optional 계약(`max_iterations`)만 소비 (additive) | 타입 검사 + 통합 테스트 페이로드 단언 |
| TDD | 테스트 선행 (Red → Green → Refactor), MSW per-file listen 3종 훅 | 신규 테스트 파일 동반 |
| UI 일관성 | 프로젝트 디자인 토큰(zinc/violet 계열)·페이지 래퍼 패턴 A 준수, 시안 구조 재현 | 육안 + 컴포넌트 테스트 |
| 테스트 함정 | number 입력 음수/범위 이탈은 fireEvent 사용, 커스텀 인라인 검증 폼은 noValidate (jsdom constraint validation 회피) | 기존 관례 준수 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] 설정 탭에서 max_iterations를 500으로 바꿔 저장 → detail 재조회 시 500 반영 (create·edit 각 1회, E2E 수동)
- [ ] edit 재진입 시 500이 프라임되어 표시됨
- [ ] 범위 밖 입력(9, 1001)이 저장으로 새어나가지 않음 (테스트 단언)
- [ ] 스텁 3종 토글이 클릭 불가 + "준비중" 노출 (테스트 단언)
- [ ] 신규 테스트 전부 통과 + 기존 테스트 무회귀

### 4.2 Quality Criteria

- [ ] Gap 분석(Match Rate) >= 90%
- [ ] 컴포넌트 단일 책임 (SettingsPanel 200줄 초과 시 섹션 분리), 하드코딩 상수는 constants로

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| update에 max_iterations **항상 전송**이 의도치 않은 값 덮어쓰기 유발 (프라임 실패 시 25 전송 → 기존 500 강하) | Medium | Low | 프라임 폴백은 detail 결측 시에만 25 — detail이 항상 값을 반환하므로 실질 위험 낮음. Design에서 "프라임 성공 전 저장 차단" 여부 확정, 통합 테스트로 프라임→저장 경로 단언 |
| 시안 범위(1~1000)와 구현 범위(10~1000) 불일치로 사용자 혼선 | Low | Low | 안내문을 "범위: 10 - 1000"으로 명기 (결정 2 — 정책 무수정) |
| 스텁 토글을 실기능으로 오인 | Low | Medium | disabled + "준비중" 툴팁 + 흐린 스타일 — 동작 착시 차단 (결정 3) |
| jsdom constraint validation이 범위 검증 테스트를 왜곡 (min/required 위반 시 submit 차단) | Medium | High(알려짐) | 커스텀 인라인 검증 시 noValidate, 음수·범위 이탈 입력은 fireEvent — 기존 교훈 재사용 |
| RightTabId 'settings' 분기 추가 시 기존 탭 분기 체인(삼항 연쇄) 가독성 저하 | Low | Medium | 분기 5개 도달 — Design에서 switch/맵 방식 전환 검토 (기존 코드 스타일 존중 범위 내) |

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
| Recursion Limit 값 배선 | max_iterations 재사용 / model_call_limit config / 병행 노출 | **max_iterations 재사용** | 백엔드 전 구간 완비(diff 0), 시안 기본값 25와 일치. model_call_limit은 별개 개념(run당 LLM 호출)이며 config 오버라이드는 백엔드 확장 필요 — 후속 |
| 범위 정합 | UI 10~1000 표기 / 정책 MIN=1 완화 | **UI 10~1000** | 백엔드 정책·테스트 무수정, 회귀 위험 0 |
| 스텁 수준 | 토글 비활성+준비중 / 로컬 동작 / 범위 제외 | **비활성+준비중** | 시안 레이아웃 확보 + 동작 착시 차단 |
| 저장 방식 | StudioHeader 통합 / 탭 내 별도 저장 | **StudioHeader 통합** | create=staged·edit=update 기존 구조와 일관, 부분 PATCH 이원화 복잡도 회피 |
| update 전송 방식 | 항상 전송 / 변경 시에만(dirty 추적) | Design 확정 (기본: 항상 전송) | 프라임 기반이라 항상 전송이 단순·안전. dirty 추적은 폼 전반에 없는 관례 — 도입 신중 |

### 6.3 변경 대상 파일 (예상)

```
idt_front/src/
├── components/agent-builder/
│   ├── AgentTestPanel.tsx                       # S1: settings enabled + 분기
│   └── settings/
│       ├── SettingsPanel.tsx                    # S2·S3·S6: 신설 (4개 섹션)
│       └── SettingsPanel.test.tsx               # S7-①
├── types/agentBuilder.ts                        # S4: FormData/Create/Update 필드
├── types/agentStore.ts (또는 detail 타입 위치)   # S4: detail max_iterations 선언(누락 시)
├── utils/agentDetailMapping.ts(+test)           # S5·S7-③: 프라임 + 폴백
└── pages/AgentBuilderPage/
    ├── index.tsx                                # S5: DEFAULT_FORM + create/update 페이로드
    └── index.test.tsx                           # S7-②: 페이로드·프라임 통합 단언
```

> 정확한 검증 UX(인라인 에러 vs clamp)·분기 구조·상수 위치는 Design 단계에서 확정.

---

## 7. Convention Prerequisites

- [x] 백엔드 계약 확인 완료: create(ge=10 le=1000)·update(optional)·detail·repo 화이트리스트 전부 기존재
- [x] 프론트 테스트 관례: vitest `--pool=threads`, MSW per-file listen, jsdom noValidate 함정
- 환경변수·마이그레이션·백엔드 API 계약 변경 **없음** (api-contract-sync 불필요 — 프론트가 기존 계약 소비)
