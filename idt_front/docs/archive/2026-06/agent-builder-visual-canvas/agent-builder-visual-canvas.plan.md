# Plan: Agent Builder Visual Canvas

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | agent-builder-visual-canvas |
| 작성일 | 2026-06-30 |
| 영역 | 프론트엔드 (idt_front) — 단독 (백엔드 변경 없음) |
| 예상 소요 | 6~9시간 |
| 의존성 추가 | `@xyflow/react` (React Flow v12) |

### Value Delivered

| 관점 | 설명 |
|------|------|
| **Problem** | `/agent-builder` 스튜디오의 좌측 "비주얼" 탭이 `disabled`(`준비중`)로 막혀 있어, 에이전트 구성(모델·도구·서브에이전트)을 폼 입력으로만 확인할 수 있고 전체 구조를 한눈에 파악할 수 없다. |
| **Solution** | 기존 폼 상태(`AgentBuilderFormData`)를 React Flow 노드 그래프로 렌더링하는 비주얼 캔버스를 구현하고, 노드의 "추가/설정" 버튼이 폼과 동일한 모달을 열어 양방향 동기화되는 완전 인터랙티브 편집을 제공한다. |
| **Function UX Effect** | 에이전트(중앙)를 중심으로 스킬·도구·서브에이전트·미들웨어·모델 노드가 색상별 점선 엣지로 연결되어 표시되고, 폼에서 수정하면 비주얼이 즉시 갱신되며 비주얼에서 추가/설정해도 폼에 반영된다. 드래그 이동·줌·기본 레이아웃 리셋 지원. |
| **Core Value** | 에이전트 구성을 시각적으로 이해·편집할 수 있게 되어 Agent Builder의 사용성이 폼 단독 대비 크게 향상되고, 향후 스킬/미들웨어/워크플로우 확장의 시각화 기반을 마련한다. |

---

## 1. 현재 상황 분석

### 1.1 비주얼 탭 (현재 상태)

- **위치**: `src/components/agent-builder/LeftConfigPanel.tsx` (L103-110)
- 버튼이 `disabled` + `title="준비중"` 으로 완전 비활성. 렌더되는 캔버스 컴포넌트 없음.
- 탭 상태: `const [leftTab, setLeftTab] = useState<LeftTabId>('form')` (L52). `LeftTabId = 'form' | 'visual'` (`types/agentBuilder.ts` L116).

### 1.2 폼 상태 및 데이터 모델

- **상태 보유**: `AgentBuilderPage/index.tsx` 의 로컬 React state (`useState<AgentBuilderFormData>`). Zustand 아님.
- **데이터 셰이프** (`types/agentBuilder.ts` L91-100):

```ts
interface AgentBuilderFormData {
  name: string;            // 에이전트 이름
  description: string;     // 설명
  model: string;           // model_name (예: claude-haiku-4-5)
  systemPrompt: string;    // 지침/INSTRUCTIONS
  tools: string[];         // tool_id 목록
  temperature: number;
  toolConfigs: Record<string, RagToolConfig>;
  subAgents: SubAgentConfig[]; // { ref_agent_id, name, description }
}
```

- 비주얼 컴포넌트는 `form: AgentBuilderFormData`를 prop으로 받아 읽고, 변경은 `onChange(updatedForm)` 콜백으로 폼과 공유한다. (양방향 동기화는 단일 `form` 소스를 공유하므로 자동 성립)

### 1.3 기존 모달 (재사용 대상)

`LeftConfigPanel.tsx` 내부에 이미 다음 모달과 open 상태가 존재한다 — 비주얼 노드 버튼이 **동일 상태를 재사용**한다:

| 모달 | open 상태 | 적용 콜백 |
|------|-----------|-----------|
| `ModelSettingsModal` | `isModelModalOpen` | `onApply({model, temperature})` |
| `ToolPickerModal` | `isToolModalOpen` | `onToggle(toolId)` |
| `SubAgentManagerModal` | `isSubAgentModalOpen` | `onAdd` / `onRemove` |

### 1.4 시각화 라이브러리 현황

- `package.json`에 그래프 라이브러리 **없음** (recharts/chart.js는 통계용). reactflow/@xyflow 미설치.
- 참고 패턴: `WorkflowDesignerPage/FlowCanvas.tsx` (커스텀 SVG 베지어) — 본 기능에는 사용하지 않음(아래 결정 참고).

---

## 2. 설계 결정 (사용자 확정)

| # | 결정 항목 | 선택 | 근거 |
|---|-----------|------|------|
| 1 | 시각화 방식 | **React Flow (`@xyflow/react`) 설치** | 스크린샷의 점선 베지어 엣지·하단 줌 컨트롤·기본 레이아웃 리셋이 React Flow 기본 스타일과 동일. 줌/팬/드래그/엣지 내장으로 구현 속도·품질 우위. React 19 호환(v12). |
| 2 | 상호작용 범위 | **완전 인터랙티브** | 노드의 "추가/설정" 버튼이 폼과 같은 모달을 열고, 변경이 폼↔비주얼 양방향 즉시 반영. "Edit in Form"으로 폼 탭 이동. |
| 3 | 스킬·미들웨어 노드 | **표시 전용 플레이스홀더** | 두 항목은 현재 `AgentBuilderFormData`에 없음(스킬=우측 `AgentSkillPanel` 별도, 미들웨어=미구현). 스크린샷처럼 노드는 그리되 "준비중"으로 비활성. 에이전트/모델/도구/서브에이전트만 실제 연동. |
| 4 | 노드 위치/레이아웃 | **드래그 이동 + 기본 레이아웃 리셋, 저장 안 함** | 노드 드래그 가능, "기본 레이아웃" 버튼으로 자동 배치 복원. 위치 영속화(localStorage/백엔드) 없음 — 새로고침 시 초기화. |

---

## 3. 구현 범위

### 3.1 In Scope

1. `@xyflow/react` 의존성 추가 + CSS import.
2. 비주얼 캔버스 컴포넌트 (`VisualCanvas`) — React Flow 래핑, 노드/엣지 렌더, 줌 컨트롤, "기본 레이아웃" 버튼.
3. 6종 노드 컴포넌트: **에이전트(중앙)**, 스킬, 도구, 서브 에이전트, 미들웨어, 모델.
4. 폼 → 노드/엣지 변환 순수 함수 (`buildNodes` / `buildEdges` / 기본 레이아웃 좌표).
5. 색상별 점선 엣지 (스킬=amber, 도구=blue, 서브에이전트=violet, 미들웨어=purple, 모델=amber/orange).
6. 인터랙션 배선:
   - 도구 노드 "도구 추가" → `ToolPickerModal` open
   - 서브에이전트 노드 설정(⚙) → `SubAgentManagerModal` open
   - 모델 노드 클릭 → `ModelSettingsModal` open
   - 에이전트 노드 "Edit in Form" → `leftTab='form'` 전환
7. `LeftConfigPanel`에서 비주얼 탭 활성화 + 탭 전환 시 캔버스/폼 토글.
8. 빈 상태 텍스트(스크린샷 일치): "스킬이 설정되지 않았습니다", "도구가 설정되지 않았습니다", "No sub-agents", "미들웨어 없음".
9. TDD 테스트 (레이아웃 빌더 순수함수 + 노드 컴포넌트 + 인터랙션 콜백).

### 3.2 Out of Scope (이번 범위 제외)

- 스킬·미들웨어의 실제 데이터 연동 (플레이스홀더만).
- 노드 위치 영속화.
- 노드 간 임의 연결(엣지 직접 생성/삭제) — 엣지는 폼 데이터에서 파생되는 읽기 전용.
- 우측 패널(테스트/스킬) 변경.
- 백엔드 스키마·API 변경 (없음).

---

## 4. 아키텍처 설계

### 4.1 컴포넌트 구조

```
LeftConfigPanel (수정)
├─ 탭 버튼 [폼] [🕸 비주얼]  ← 비주얼 enabled
├─ leftTab === 'form'   → 기존 폼 스크롤 본문
└─ leftTab === 'visual' → <VisualCanvas form onAddTool onConfigModel onManageSubAgents onEditInForm />
   (모달 3종은 LeftConfigPanel에 그대로 유지, open 상태를 캔버스 콜백이 토글)

src/components/agent-builder/visual/
├─ VisualCanvas.tsx        # ReactFlowProvider + ReactFlow + Controls + 기본레이아웃 버튼
├─ nodes/
│  ├─ AgentNode.tsx        # 중앙 노드 (이름/설명/INSTRUCTIONS/Edit in Form)
│  ├─ ResourceNode.tsx     # 스킬/도구/서브에이전트/미들웨어/모델 공통 카드 노드
│  └─ index.ts             # nodeTypes 매핑
├─ buildGraph.ts           # form → nodes/edges 순수 변환 + DEFAULT_LAYOUT 좌표
└─ constants.ts            # 노드 종류·색상·핸들 위치 상수
```

> `ResourceNode`는 종류별 props(아이콘/제목/색상/본문/액션버튼)를 받는 단일 카드 컴포넌트로 통일하여 200줄 분리 규칙(`idt_front/CLAUDE.md`)을 준수한다.

### 4.2 노드 ↔ 폼 매핑

| 노드 | 폼 소스 | 본문 표시 | 액션 | 엣지색 |
|------|---------|-----------|------|--------|
| **에이전트**(center) | `name`, `description`, `systemPrompt` | 이름 / 설명 / "INSTRUCTIONS" + 프롬프트 또는 "No instructions set" | ✏ Edit in Form → 폼 탭 | — (허브) |
| 스킬 | (없음) | "스킬이 설정되지 않았습니다" | + 스킬 추가 (disabled, 준비중) | amber |
| 도구 | `tools[]` (+ `catalogTools` 라벨) | 도구 목록 또는 "도구가 설정되지 않았습니다" | + 도구 추가 → ToolPickerModal | blue |
| 서브 에이전트 | `subAgents[]` | 서브에이전트 목록 또는 "No sub-agents" | ⚙ → SubAgentManagerModal | violet |
| 미들웨어 | (없음) | "미들웨어 없음" | + 미들웨어 추가 (disabled, 준비중) | purple |
| 모델 | `model` (+ `models` → `provider:model_name`) | `anthropic:claude-haiku-4-5` 형태 코드 라벨 | 노드 클릭 → ModelSettingsModal | amber |

### 4.3 기본 레이아웃 좌표 (스크린샷 기준 근사)

```
                 스킬(좌상)          도구(우상)
   에이전트(좌중) ─────● 허브 ●───── 서브에이전트(우중)
                 모델(좌하)          미들웨어(우하)
```

- 좌표는 `DEFAULT_LAYOUT: Record<NodeKind, {x,y}>` 상수로 고정. "기본 레이아웃" 클릭 시 `setNodes`로 이 좌표 복원.
- 엣지: 에이전트(허브) → 각 리소스 노드. `type: 'default'`(bezier), `animated` 또는 `style.strokeDasharray`로 점선, `style.stroke`로 색상.

### 4.4 상호작용 데이터 흐름

```
[비주얼 노드 버튼] --onAddTool--> LeftConfigPanel.setToolModalOpen(true)
                                   --> ToolPickerModal --onToggle--> onToolToggle
                                   --> form.tools 변경 --> 폼·비주얼 동시 갱신
```

폼과 비주얼은 동일한 `form` prop을 읽으므로 한쪽 변경이 양쪽에 반영된다(단일 소스). 비주얼 노드 버튼은 신규 콜백(`onAddTool`/`onConfigModel`/`onManageSubAgents`/`onEditInForm`)으로 기존 모달 open 상태와 탭 상태만 토글한다.

---

## 5. 파일별 변경 계획

### 5.1 신규 파일

| 파일 | 책임 |
|------|------|
| `src/components/agent-builder/visual/buildGraph.ts` | `buildNodes(form, catalogTools, models)`, `buildEdges()`, `DEFAULT_LAYOUT`, 모델 라벨 계산. **순수 함수 — 핵심 테스트 대상** |
| `src/components/agent-builder/visual/constants.ts` | `NODE_KINDS`, 엣지 색상맵, 빈 상태 텍스트 |
| `src/components/agent-builder/visual/nodes/AgentNode.tsx` | 중앙 에이전트 카드 (Edit in Form 버튼) |
| `src/components/agent-builder/visual/nodes/ResourceNode.tsx` | 리소스 카드 공통 컴포넌트 (스킬/도구/서브/미들웨어/모델) |
| `src/components/agent-builder/visual/nodes/index.ts` | `nodeTypes` 매핑 |
| `src/components/agent-builder/visual/VisualCanvas.tsx` | ReactFlow 통합 + Controls + 기본 레이아웃 버튼 |
| `src/components/agent-builder/visual/buildGraph.test.ts` | 빌더 순수함수 테스트 |
| `src/components/agent-builder/visual/nodes/ResourceNode.test.tsx` | 노드 액션/빈 상태 테스트 |
| `src/components/agent-builder/visual/VisualCanvas.test.tsx` | 콜백 배선 스모크 테스트 |

### 5.2 수정 파일

| 파일 | 변경 |
|------|------|
| `LeftConfigPanel.tsx` | 비주얼 탭 `disabled` 제거 + `onClick`, `leftTab==='visual'`일 때 `<VisualCanvas/>` 렌더, 신규 콜백으로 모달/탭 토글 |
| `package.json` | `@xyflow/react` 의존성 추가 |
| `types/agentBuilder.ts` | 필요 시 비주얼 노드 종류 타입(`VisualNodeKind`) 추가 (선택) |

---

## 6. TDD 테스트 계획

> Windows에서 vitest 실행 시 `--pool=threads` 사용(메모리: frontend-vitest-forks-timeout).
> React Flow는 jsdom에서 `ResizeObserver`/치수 측정에 의존 → **순수 빌더와 노드 카드(단순 div)를 집중 테스트**하고, `VisualCanvas`는 `ResizeObserver` 폴리필 + 경량 스모크로 제한.

| 우선순위 | 테스트 | 검증 내용 |
|---------|--------|-----------|
| P1 | `buildGraph.test.ts` | 노드 6개 생성·라벨·모델 라벨(`provider:model_name`)·도구 개수·엣지 색상/개수·DEFAULT_LAYOUT 좌표 |
| P2 | `ResourceNode.test.tsx` | 빈 상태 텍스트, "도구 추가" 클릭→콜백, 스킬/미들웨어 버튼 disabled |
| P3 | `VisualCanvas.test.tsx` | 모델 노드 클릭→onConfigModel, "Edit in Form"→onEditInForm 호출 |

`Red → Green → Refactor` 순서 준수. 각 파일은 구현 전 실패 테스트 먼저 작성.

---

## 7. 구현 순서

1. `@xyflow/react` 설치 (`npm install @xyflow/react --legacy-peer-deps`) + CSS import 확인.
2. `constants.ts` + `buildGraph.ts` 테스트 작성(Red) → 구현(Green).
3. `ResourceNode.tsx` / `AgentNode.tsx` 테스트 → 구현.
4. `VisualCanvas.tsx` 통합(노드/엣지/Controls/기본 레이아웃 버튼) + 드래그.
5. `LeftConfigPanel.tsx` 비주얼 탭 활성화 + 콜백 배선.
6. 스크린샷 대조(색상/배치/빈 상태 텍스트) → 미세 조정.
7. `npm run type-check` + `npm run test:run -- --pool=threads` + `npm run lint`.

---

## 8. 주의사항 / 영향 범위

- **API 계약 영향 없음**: 백엔드 변경 없음. 폼 데이터만 시각화.
- **번들 크기**: `@xyflow/react` 추가(~50KB gzip 내외). 비주얼 탭은 코드 스플리팅(`React.lazy`) 고려 가능(선택).
- **React 19 호환**: `@xyflow/react` v12 사용. peer dep 충돌 시 `--legacy-peer-deps`(메모리: preexisting-frontend-test-failures).
- **jsdom 한계**: React Flow 전체 렌더 테스트는 불안정 → 순수 빌더/카드 위주 테스트 전략(§6).
- **스킬/미들웨어**: 플레이스홀더이므로 추후 데이터 모델 확장 시 노드만 활성화하면 됨(확장 지점 주석 명시).
- **단일 소스 동기화**: 폼·비주얼이 같은 `form`을 공유하므로 별도 동기화 로직 불필요. `onChange` 일관 사용 필수.

---

## 9. 다음 단계

```
/pdca design agent-builder-visual-canvas   # 노드 props·엣지 스펙·좌표 상세 설계
```
