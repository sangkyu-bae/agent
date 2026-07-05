# agent-builder-studio-ui Design Document

> **Summary**: AgentBuilderPage를 2-패널 Studio 에디터로 재구성하기 위한 컴포넌트 분해·props 계약·상태 머신·모달/테스트 패널 동작 설계.
>
> **Project**: idt_front (React 19 + TypeScript + Tailwind v4 + TanStack Query + Zustand)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-06-27
> **Status**: Draft
> **Planning Doc**: [agent-builder-studio-ui.plan.md](../01-plan/features/agent-builder-studio-ui.plan.md)

### Pipeline References

| Phase | Document | Status |
|-------|----------|--------|
| Phase 1 | Schema Definition | N/A (프론트 전용, 백엔드 스키마 변경 없음) |
| Phase 3 | Mockup | ✅ `docs/img/chat_build_main.png`, `docs/img/chat_model.png` |
| Phase 4 | API Spec | N/A (기존 API 재사용) |

---

## 1. Overview

### 1.1 Design Goals

- 단일 `AgentBuilderPage/index.tsx`(742줄)를 **오케스트레이션 + 분리된 프레젠테이션 컴포넌트**로 분해해 200줄 규칙을 준수한다.
- 기존 폼 상태(`AgentBuilderFormData`)·기존 훅(`useCreateBuilderAgent`/`useUpdateBuilderAgent`/`useToolCatalog`/`useLlmModels`/`useAgentRunStream`/`useAgentSkills`)을 **그대로 재사용**하고 신규 API·신규 백엔드를 도입하지 않는다.
- 활성 기능(모델·도구·스킬·테스트)과 비활성 placeholder(미들웨어·서브에이전트·오프너·스케줄·파일·버전·비주얼)를 동일한 시각 골격에 배치해 향후 확장 슬롯을 확보한다.

### 1.2 Design Principles

- **단일 책임**: 레이아웃 셸 / 좌측 구성 / 우측 테스트 / 모달 각각 독립 컴포넌트.
- **상태 끌어올리기(lift state up)**: 폼 상태는 `AgentBuilderPage`가 소유, 자식은 `value`/`onChange` 계약만.
- **무해한 placeholder**: 비활성 영역은 동작처럼 보이지 않게 `disabled` + opacity + "준비중" 툴팁.
- **회귀 0**: 저장/수정/삭제/도구토글/RAG 로직은 동작 보존, 외형만 재배치.

---

## 2. Architecture

### 2.1 Component Diagram

```
AgentBuilderPage (index.tsx)  ── 뷰 전환(list|create|edit) + 폼 상태 소유 + 저장/삭제 핸들러
│
├── ListView (기존 유지)                       … 카드 그리드 진입점
│
└── StudioLayout (신규)                         … create|edit 시 렌더되는 2-패널 셸
    ├── StudioHeader                            … 에이전트명/설명, 저장/취소, 비활성 아이콘·버전셀렉터
    ├── LeftConfigPanel (신규)                  … 좌측 스크롤 컨테이너
    │   ├── FormVisualTabs (폼 활성 / 비주얼 placeholder)
    │   ├── InstructionSection                  … 지침(systemPrompt) textarea + 카운터
    │   ├── SubAgentSection (PlaceholderSection)
    │   ├── ModelSection                        … 모델 칩 + ⚙ → ModelSettingsModal
    │   ├── ToolboxSection                      … 도구 칩 목록 + "+도구" → ToolPickerModal
    │   │   └── RagConfigPanel (기존, 조건부)
    │   └── MiddlewareSection (PlaceholderSection)
    │
    ├── AgentTestPanel (신규)                   … 우측 스크롤 컨테이너
    │   ├── RightTabBar (테스트·스킬 활성 / Fix·오프너·파일·스케줄·설정 비활성)
    │   ├── TestChatView                        … useAgentRunStream 기반 대화
    │   └── AgentSkillPanel (기존, 스킬 탭)
    │
    ├── ModelSettingsModal (신규)               … chat_model.png 팝업
    └── ToolPickerModal (신규)                  … 도구 추가 팝업
```

### 2.2 Data Flow

```
[폼 편집]
  LeftConfigPanel onChange → AgentBuilderPage.form(useState) → 자식 value 재바인딩

[모델 설정]
  ModelSection ⚙ → openModelModal → ModelSettingsModal(value=form) 
    → onApply({model, temperature}) → form 갱신 → 모달 close

[도구 추가]
  ToolboxSection "+도구" → openToolModal → ToolPickerModal(catalog, selected=form.tools)
    → onToggle(toolId) → 기존 handleToolToggle(RAG config 동기화 포함) → form 갱신

[저장]
  StudioHeader 저장 → 기존 handleSave (create→update systemPrompt, MCP 제외 규칙 유지)

[테스트] (edit 모드 한정)
  TestChatView send(query)
    → streamId=randomUUID, runId=randomUUID 발급
    → useAgentRunStream({agentId=editingId, runId, streamId, query, sessionId})
    → tokens/steps/answer 누적 렌더
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| StudioLayout | form 상태, 저장/취소 콜백 | 셸 + 헤더 |
| ModelSettingsModal | `useLlmModels`, form.model/temperature | 모델·temperature 적용 |
| ToolPickerModal | `useToolCatalog`, form.tools | 도구 추가/제거 |
| AgentTestPanel | `useAgentRunStream`, editingId | 실시간 테스트 |
| AgentSkillPanel(기존) | `useAgentSkills` | 스킬 attach/detach |
| PlaceholderSection | 없음(순수 표시) | 비활성 자리 표시 |

---

## 3. Data Model

신규 백엔드 엔티티 없음. **프론트 전용 타입만 추가** (`src/types/agentBuilder.ts` 확장).

### 3.1 신규/확장 타입

```typescript
// 우측 패널 탭 식별자
export type RightTabId =
  | 'test' | 'skill'                       // 활성
  | 'fix' | 'opener' | 'file' | 'schedule' | 'settings'; // 비활성(placeholder)

// 좌측 폼/비주얼 탭
export type LeftTabId = 'form' | 'visual'; // 'visual' 비활성

// 테스트 패널의 1개 대화 메시지(로컬 전용)
export interface TestChatMessage {
  id: string;                  // crypto.randomUUID()
  role: 'user' | 'assistant';
  content: string;
}

// 모델 설정 모달이 form에 적용하는 부분 값
export interface ModelSettingsValue {
  model: string;               // model_name
  temperature: number;
  // UI만(미저장) — 폼/요청에 포함하지 않음
  maxTokens?: number | null;
  topP?: number | null;
  topK?: number | null;
}
```

> `AgentBuilderFormData`는 **변경하지 않는다** (model/temperature/tools/toolConfigs/systemPrompt 그대로). maxTokens/topP/topK는 폼에 저장하지 않으므로 모달 로컬 state로만 보관한다.

### 3.2 비활성 placeholder 정의(표시 전용)

| 섹션 | 표시 문구 | 비고 |
|------|-----------|------|
| 서브에이전트 | "서브에이전트가 없습니다" | ⚙ disabled |
| 미들웨어 | "추가된 미들웨어가 없습니다" | "+미들웨어" disabled |
| 비주얼 탭 | (탭 자체 disabled) | "준비중" 툴팁 |
| 오프너/파일/스케줄/설정/Fix | (탭 disabled) | "준비중" 툴팁 |
| 버전 셀렉터(v0) | "v0" 고정 표시 | disabled |

---

## 4. API Specification

신규 엔드포인트 없음. **기존 API 재사용**.

| Method | Path | 사용처 | Hook |
|--------|------|--------|------|
| GET | `/api/v1/agents/tools` | 도구 모달 | `useToolCatalog` |
| GET | `/api/v1/llm-models` | 모델 모달 | `useLlmModels` |
| POST | `/api/v1/agents` | 저장(생성) | `useCreateBuilderAgent` |
| PATCH | `/api/v1/agents/{id}` | 저장(수정/프롬프트) | `useUpdateBuilderAgent` |
| DELETE | `/api/v1/agents/{id}` | 삭제 | `useDeleteBuilderAgent` |
| GET | `/api/v1/agents/my` | 목록 | `useMyBuilderAgents` |
| GET | `/api/v1/agents/{id}` | 수정 진입 상세 | `useBuilderAgentDetail` |
| WS | `WS_AGENT_RUN(runId)` | 테스트 채팅 | `useAgentRunStream` |
| GET/POST/DELETE | `/api/v1/agents/{id}/skills` | 스킬 탭 | `useAgentSkills`/`useAttachSkill`/`useDetachSkill` |

---

## 5. UI/UX Design

### 5.1 Screen Layout

```
┌──────────────────────────────────────────────────────────────────────┐
│ [✦] 새 에이전트 / 설명 입력          </> ⧉ 🗑 ⟳  [현재버전:v0▾*] [저장▾] │  StudioHeader
├───────────────────────────────────┬──────────────────────────────────┤
│ [폼] | 비주얼*                     │ Fix* | 테스트 | 오프너* | 파일*    │  탭 바
│                                   │  스킬 | 스케줄* | 설정*    [새 대화]│
│ ▾ 지침                       [⤢]  │                                   │
│  ┌─────────────────────────────┐  │         (테스트 빈 상태)           │
│  │ 시스템 프롬프트 textarea      │  │           [🤖]                    │
│  └─────────────────────────────┘  │      새 에이전트 테스트            │
│                            0자     │   에이전트와 대화를 시작하세요      │
│ ⊙ 서브에이전트   없음*       ⚙*   │                                   │
│ ⚙ 모델  anthropic:claude-haiku-4-5⚙│                                   │
│ ▾ 도구함                  [+도구] │                                   │
│   추가된 도구가 없습니다           │                                   │
│ ▾ 미들웨어*            [+미들웨어*]│  ┌─────────────────────────────┐  │
│   추가된 미들웨어가 없습니다*      │  │ 에이전트를 테스트해 보세요... ↑│  │
│                                   │  └─────────────────────────────┘  │
└───────────────────────────────────┴──────────────────────────────────┘
  (*) = 비활성 placeholder
```

좌/우 패널 분할: `flex`, 좌측 `flex-1`(또는 고정 비율) + 우측 `flex-1`, **각 패널은 자체 `overflowY:auto`** (CLAUDE.md 패턴 A — `AgentChatLayout` overflow:hidden 대응).

### 5.2 User Flow

```
목록(카드) ─ "새 에이전트"/카드클릭 → StudioLayout
  ├─ 좌측 구성: 지침 입력 / 모델 ⚙ 설정 / "+도구" 추가
  ├─ 저장 → (생성 시) 목록 복귀 또는 edit 모드 유지
  └─ (edit) 우측 테스트 탭 → 대화 입력 → 스트리밍 응답
취소 → 목록 복귀
```

### 5.3 ModelSettingsModal 동작 (chat_model.png)

```
열림: ModelSection ⚙ 클릭 → isModelModalOpen=true (로컬 state: {model, temperature, maxTokens?, topP?, topK?} = form에서 초기화)
구성:
  - 모델 선택: <select> (useLlmModels). 각 옵션 라벨 "{provider}:{display_name} [API 키 미등록]" (is_active/키 상태 표기)
  - 경고 배너: 활성 키 없을 때 "모든 모델에 필요한 API 키가 등록되지 않았습니다. 설정 > Secrets에서 키를 등록하세요." (정적 안내, 링크는 비활성/단순 텍스트)
  - 파라미터: 온도(활성, 0~1 number/range) / 최대토큰·Top P·Top K (disabled placeholder, "(선택)" )
  - "모델 관리" 링크: 비활성(준비중)
  - [취소] → 닫기(미적용)  [저장] → onApply({model, temperature}) → form 갱신 → 닫기
적용 범위: model_name + temperature만 form 반영. maxTokens/topP/topK는 적용하지 않음(모달 닫으면 폐기).
```

### 5.4 ToolPickerModal 동작

```
열림: ToolboxSection "+도구" → isToolModalOpen=true
구성: useToolCatalog 결과를 내부/MCP 그룹으로 표시. 각 항목 클릭 시 onToggle(tool_id).
규칙: 생성(create) 모드에서 source==='mcp' 도구는 disabled + "생성 후 편집에서 연결" 툴팁 (기존 규칙 보존).
RAG: RAG_TOOL_ID 토글 시 기존 handleToolToggle가 toolConfigs 동기화. 모달 닫은 뒤 좌측 ToolboxSection 아래 RagConfigPanel 노출.
닫기: [완료] 또는 오버레이 클릭 → 닫기 (선택은 즉시 form 반영되어 별도 확정 불필요).
```

### 5.5 TestChatView 동작 (edit 모드 한정)

```
create 모드: "저장 후 테스트할 수 있습니다" 안내 + 입력 비활성.
edit 모드:
  send(query):
    1. messages에 {role:'user'} 추가
    2. streamId=crypto.randomUUID(); runId=crypto.randomUUID()
    3. useAgentRunStream({agentId: editingId, runId, streamId, query, sessionId})
    4. tokens 스트리밍 → 진행 중 assistant 버블에 실시간 반영
    5. answer 확정/ isDone → 최종 assistant 메시지 확정
  "새 대화": sessionId 새로 발급 + messages 초기화
세션: 로컬 sessionId(useRef) 유지 → 멀티턴.
재사용: 진행 표시는 기존 AgentRunProgress 패턴 참고 가능(선택).
```

### 5.6 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `StudioLayout` | `src/components/agent-builder/StudioLayout.tsx` | 2-패널 셸 + 헤더 조립 |
| `StudioHeader` | `src/components/agent-builder/StudioHeader.tsx` | 타이틀/저장/취소/비활성 액션 |
| `LeftConfigPanel` | `src/components/agent-builder/LeftConfigPanel.tsx` | 좌측 섹션 묶음 + 스크롤 |
| `ModelSettingsModal` | `src/components/agent-builder/ModelSettingsModal.tsx` | 모델·온도 설정 팝업 |
| `ToolPickerModal` | `src/components/agent-builder/ToolPickerModal.tsx` | 도구 추가 팝업 |
| `AgentTestPanel` | `src/components/agent-builder/AgentTestPanel.tsx` | 우측 탭바 + 테스트/스킬 |
| `TestChatView` | `src/components/agent-builder/TestChatView.tsx` | 테스트 대화 렌더 |
| `PlaceholderSection` | `src/components/agent-builder/PlaceholderSection.tsx` | 공통 비활성 블록 |
| `CollapsibleSection` | `src/components/agent-builder/CollapsibleSection.tsx` | 접기/펼치기 공통 래퍼 |
| `AgentSkillPanel`(기존) | 동일 경로 | 스킬 탭 콘텐츠 |
| `RagConfigPanel`(기존) | 동일 경로 | RAG 도구 설정 |

### 5.7 주요 Props 계약

```typescript
interface StudioLayoutProps {
  mode: 'create' | 'edit';
  agentId: string | null;            // edit 시 저장된 agent_id
  form: AgentBuilderFormData;
  onChange: (f: AgentBuilderFormData) => void;
  onToolToggle: (toolId: string) => void;       // 기존 핸들러
  onRagConfigChange: (c: RagToolConfig) => void; // 기존 핸들러
  onSave: () => void;
  onCancel: () => void;
  isSaving: boolean;
  // 카탈로그/모델 데이터 + 로딩/에러/리트라이 (기존 FormView props 승계)
  catalogTools?: CatalogTool[]; models?: LlmModel[];
  isToolsLoading: boolean; isToolsError: boolean; onRetryTools: () => void;
  isModelsLoading: boolean; isModelsError: boolean; onRetryModels: () => void;
}

interface ModelSettingsModalProps {
  isOpen: boolean;
  models?: LlmModel[];
  current: { model: string; temperature: number };
  onApply: (v: { model: string; temperature: number }) => void;
  onClose: () => void;
}

interface ToolPickerModalProps {
  isOpen: boolean;
  catalogTools?: CatalogTool[];
  selectedIds: string[];
  isEditMode: boolean;               // MCP 비활성 규칙
  onToggle: (toolId: string) => void;
  onClose: () => void;
}

interface AgentTestPanelProps {
  mode: 'create' | 'edit';
  agentId: string | null;
  userId: string;                    // authStore에서
  agentName: string;
}
```

---

## 6. Error Handling

| 상황 | 처리 |
|------|------|
| 모델/도구 목록 로드 실패 | 기존 패턴 — 패널 내 "다시 시도" 버튼(`onRetryModels`/`onRetryTools`) |
| 저장 실패 | 기존 `saveResult` 다이얼로그(에러 variant) 재사용 |
| create 모드 테스트 시도 | 입력 비활성 + 안내 문구(요청 차단) |
| WS 연결 실패/`agent_run_failed` | `useAgentRunStream.error` → 테스트 버블에 에러 메시지 표시 |
| 활성 API 키 없는 모델 | 모달 경고 배너 + 저장은 허용(실행 시 백엔드가 판단) |

---

## 7. Security Considerations

- [x] API 키/시크릿을 프론트에 저장하지 않음 — 모달은 "키 미등록" 상태 **표시만** (값 미취급)
- [x] WS 토큰은 기존 `wsUrl(..., {token: accessToken})` 경유(`authStore`) — 신규 노출 없음
- [x] XSS: 테스트 응답은 텍스트로 렌더(기존 마크다운 렌더러 사용 시 동일 정책)
- [x] 신규 입력 필드(파라미터)는 비활성·미전송이라 검증 표면 없음

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit/Component | 신규 컴포넌트 상호작용 | Vitest + RTL |
| Integration | 모달→form 반영, 도구 토글, 테스트 스트리밍 | Vitest + RTL + MSW |
| 회귀 | 기존 생성/수정/삭제/RAG | 기존 테스트 |

> Windows 실행: `npm run test:run -- --pool=threads` (forks 워커 기동 타임아웃 회피).

### 8.2 Test Cases (Key)

- [ ] StudioHeader: 저장 버튼은 `name` 비었을 때 disabled, 클릭 시 `onSave` 호출
- [ ] ModelSettingsModal: 모델 select 변경 + 온도 변경 후 "저장" → `onApply` 정확한 값, "취소" → 미반영
- [ ] ModelSettingsModal: 최대토큰/TopP/TopK 입력은 disabled
- [ ] ToolPickerModal: 항목 클릭 → `onToggle(tool_id)`; create 모드 MCP 항목 disabled
- [ ] RAG 도구 추가 시 RagConfigPanel 노출
- [ ] TestChatView(create): 입력 비활성 + 안내 노출
- [ ] TestChatView(edit): query 전송 → token 누적 → answer 확정 렌더 (MSW/WS mock)
- [ ] PlaceholderSection: disabled + "준비중" 접근성 표기
- [ ] 우측 탭: 비활성 탭 클릭 무반응, 활성 탭(테스트/스킬) 전환 동작

---

## 9. Clean Architecture

### 9.1 Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| Studio* / *Modal / *Panel / *Section | Presentation | `src/components/agent-builder/` |
| `AgentBuilderPage` | Presentation(page) | `src/pages/AgentBuilderPage/index.tsx` |
| `useAgentBuilder`/`useToolCatalog`/`useLlmModels`/`useAgentRunStream`/`useAgentSkills` | Application | `src/hooks/` (기존) |
| 타입 확장(RightTabId 등) | Domain | `src/types/agentBuilder.ts` |
| 서비스/axios | Infrastructure | `src/services/`, `src/lib/` (기존, 변경 없음) |

### 9.2 Dependency Rules

- 컴포넌트는 컴포넌트에서 axios 직접 호출 금지 — 모두 hooks/services 경유 (기존 규칙 유지).
- 폼 상태는 page가 단일 소유 → 자식은 순수 프레젠테이션(상태 비소유, 콜백만).

---

## 10. Coding Convention Reference

### 10.1 This Feature's Conventions

| Item | Convention |
|------|-----------|
| Component naming | PascalCase 파일, arrow function, `export default` 하단 |
| Props 타입 | 파일 상단 `interface XxxProps` |
| 스타일 | `idt_front/CLAUDE.md` UI 토큰만 사용 (violet primary, rounded-xl/2xl, 모달은 `ConfirmDialog` 오버레이 패턴 `fixed inset-0 z-50 bg-black/50`) |
| 상태 | 서버=TanStack Query, 폼/모달open=useState, 절대경로 `@/` import |
| 테스트 | 소스 옆 `*.test.tsx` |

### 10.2 모달 공통 스타일(기준: ConfirmDialog)

```tsx
<div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
  <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl" onClick={(e)=>e.stopPropagation()}>
    {/* 헤더 + 본문 + 취소/저장 */}
  </div>
</div>
```

---

## 11. Implementation Guide

### 11.1 File Structure

```
src/
├── pages/AgentBuilderPage/index.tsx        # 뷰전환·폼상태·핸들러 (슬림화, FormView 제거→StudioLayout)
├── components/agent-builder/
│   ├── StudioLayout.tsx / StudioLayout.test.tsx
│   ├── StudioHeader.tsx / .test.tsx
│   ├── LeftConfigPanel.tsx / .test.tsx
│   ├── CollapsibleSection.tsx
│   ├── PlaceholderSection.tsx
│   ├── ModelSettingsModal.tsx / .test.tsx
│   ├── ToolPickerModal.tsx / .test.tsx
│   ├── AgentTestPanel.tsx / .test.tsx
│   ├── TestChatView.tsx / .test.tsx
│   ├── RagConfigPanel.tsx (기존)
│   └── AgentSkillPanel.tsx (기존)
└── types/agentBuilder.ts                   # RightTabId/LeftTabId/TestChatMessage/ModelSettingsValue 추가
```

### 11.2 Implementation Order (TDD: Red→Green→Refactor)

1. [ ] 타입 추가 (`agentBuilder.ts`) — 컴파일 기반
2. [ ] `PlaceholderSection` + `CollapsibleSection` (가장 단순, 테스트 우선)
3. [ ] `ModelSettingsModal` (테스트: onApply/취소/비활성 입력)
4. [ ] `ToolPickerModal` (테스트: onToggle/MCP 비활성)
5. [ ] `LeftConfigPanel` (지침/모델섹션/도구함 + 모달 연결)
6. [ ] `StudioHeader` + `StudioLayout` (셸 조립, 저장/취소)
7. [ ] `TestChatView` + `AgentTestPanel` (스트리밍, 스킬 탭)
8. [ ] `AgentBuilderPage` 통합: `FormView` → `StudioLayout` 치환, 기존 핸들러 연결
9. [ ] 회귀/통합 테스트 + lint + type-check + 시각 대조

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-06-27 | 초기 초안 (컴포넌트 분해·props 계약·모달/테스트 동작 설계) | 배상규 |
