# Design: Agent Builder Visual Canvas

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | agent-builder-visual-canvas |
| Plan 참조 | `docs/01-plan/features/agent-builder-visual-canvas.plan.md` |
| 작성일 | 2026-06-30 |
| 영역 | 프론트엔드 단독 (백엔드 변경 없음) |
| 의존성 추가 | `@xyflow/react` (React Flow v12, React 19 호환) |

### Value Delivered

| 관점 | 설명 |
|------|------|
| **Problem** | 비주얼 탭이 `disabled`로 막혀 에이전트 구성을 폼으로만 확인 가능 |
| **Solution** | 폼 상태(`AgentBuilderFormData`)를 React Flow 노드 그래프로 렌더링 + 노드 버튼이 기존 모달을 재사용해 양방향 동기화 |
| **Function UX Effect** | 에이전트(허브) 중심 색상별 점선 엣지 연결, 폼↔비주얼 즉시 갱신, 드래그·줌·기본 레이아웃 리셋 |
| **Core Value** | Agent Builder 사용성 향상 + 향후 스킬/미들웨어/워크플로우 시각화 확장 기반 |

---

## 1. 아키텍처 개요

```
StudioLayout
 └─ LeftConfigPanel (수정)
     ├─ 탭바: [📋 폼] [🕸 비주얼]              ← 비주얼 enabled
     ├─ leftTab==='form'   → 기존 폼 스크롤 본문 (변경 없음)
     ├─ leftTab==='visual' → <VisualCanvas/>   ← 폼 본문 대신 렌더
     └─ 모달 3종 (ModelSettingsModal/ToolPickerModal/SubAgentManagerModal)  ← 그대로 유지
                                                    ▲
        VisualCanvas 노드 버튼 → 콜백으로 동일 모달 open 상태 토글

VisualCanvas (신규)
 ├─ ReactFlowProvider
 │   └─ ReactFlow (nodes/edges, fitView, nodesDraggable)
 │       ├─ <Background/>            (점 패턴)
 │       ├─ <Controls position="bottom-left"/>   (줌 +/−/fit)
 │       └─ <Panel position="top-right"> [↻ 기본 레이아웃] </Panel>
 ├─ nodeTypes: { agent: AgentNode, resource: ResourceNode }
 └─ buildGraph(form, catalogTools, models) → { nodes, edges }   ← 순수 함수
```

### 핵심 설계 결정

| 결정 | 내용 | 근거 |
|------|------|------|
| 단일 소스 동기화 | 폼·비주얼이 동일 `form` prop 공유, 변경은 항상 `onChange` | 별도 sync 로직 불필요, 양방향 자동 성립 |
| 모달 상태 재사용 | 캔버스는 모달을 직접 들지 않고 콜백으로 `LeftConfigPanel`의 open setter 호출 | 모달 중복 마운트 방지, 기존 적용 로직 그대로 |
| 노드 위치 비영속 | RF 내부 state로만 관리, "기본 레이아웃"으로 복원 | Plan 결정 4 — 저장 안 함 |
| 엣지 읽기전용 | 엣지는 `buildEdges()`가 폼에서 파생, 사용자가 직접 연결 불가 | 폼 데이터가 단일 진실원 |

---

## 2. 상세 설계

### 2.1 상수/타입 — `src/components/agent-builder/visual/constants.ts`

```typescript
export type VisualNodeKind =
  | 'agent' | 'skill' | 'tool' | 'subagent' | 'middleware' | 'model';

/** 노드 ID (고정 단일 인스턴스). */
export const NODE_ID = {
  agent: 'agent',
  skill: 'skill',
  tool: 'tool',
  subagent: 'subagent',
  middleware: 'middleware',
  model: 'model',
} as const;

/** 엣지 색상 (스크린샷 기준). */
export const EDGE_COLOR: Record<Exclude<VisualNodeKind, 'agent'>, string> = {
  skill: '#f59e0b',      // amber  — 스킬
  tool: '#3b82f6',       // blue   — 도구
  subagent: '#8b5cf6',   // violet — 서브에이전트
  middleware: '#a855f7', // purple — 미들웨어
  model: '#f59e0b',      // amber  — 모델
};

/** 기본 레이아웃 좌표 (허브=에이전트 중앙, 스크린샷 배치 근사). */
export const DEFAULT_LAYOUT: Record<VisualNodeKind, { x: number; y: number }> = {
  skill:      { x: 40,  y: 20 },
  tool:       { x: 440, y: 20 },
  agent:      { x: 40,  y: 220 },
  subagent:   { x: 440, y: 360 },
  model:      { x: 40,  y: 560 },
  middleware: { x: 440, y: 600 },
};

/** 빈 상태 텍스트 (스크린샷 일치). */
export const EMPTY_TEXT = {
  skill: '스킬이 설정되지 않았습니다',
  tool: '도구가 설정되지 않았습니다',
  subagent: 'No sub-agents',
  middleware: '미들웨어 없음',
  instructions: 'No instructions set',
} as const;
```

### 2.2 그래프 빌더 (순수 함수) — `src/components/agent-builder/visual/buildGraph.ts`

```typescript
import type { Node, Edge } from '@xyflow/react';
import type { AgentBuilderFormData } from '@/types/agentBuilder';
import type { CatalogTool } from '@/types/toolCatalog';
import type { LlmModel } from '@/types/llmModel';
import { DEFAULT_LAYOUT, EDGE_COLOR, NODE_ID } from './constants';

export interface AgentNodeData {
  name: string;
  description: string;
  systemPrompt: string;
}
export interface ResourceNodeData {
  kind: 'skill' | 'tool' | 'subagent' | 'middleware' | 'model';
  /** 표시 항목 (도구명/서브에이전트명 등). 모델은 [라벨]. */
  items: string[];
  /** 플레이스홀더(스킬/미들웨어)는 액션 비활성. */
  disabled: boolean;
}

/** model_name → "provider:model_name" 라벨. 매칭 실패 시 raw model. */
export function buildModelLabel(model: string, models?: LlmModel[]): string {
  const m = models?.find((x) => x.model_name === model);
  return m ? `${m.provider}:${m.model_name}` : model || '모델 미선택';
}

export function buildNodes(
  form: AgentBuilderFormData,
  catalogTools?: CatalogTool[],
  models?: LlmModel[],
): Node[] {
  const toolNames = (catalogTools ?? [])
    .filter((t) => form.tools.includes(t.tool_id))
    .map((t) => t.name);
  const subNames = (form.subAgents ?? []).map((s) => s.name);

  return [
    { id: NODE_ID.agent, type: 'agent', position: DEFAULT_LAYOUT.agent,
      data: { name: form.name, description: form.description, systemPrompt: form.systemPrompt } },
    { id: NODE_ID.skill, type: 'resource', position: DEFAULT_LAYOUT.skill,
      data: { kind: 'skill', items: [], disabled: true } },
    { id: NODE_ID.tool, type: 'resource', position: DEFAULT_LAYOUT.tool,
      data: { kind: 'tool', items: toolNames, disabled: false } },
    { id: NODE_ID.subagent, type: 'resource', position: DEFAULT_LAYOUT.subagent,
      data: { kind: 'subagent', items: subNames, disabled: false } },
    { id: NODE_ID.middleware, type: 'resource', position: DEFAULT_LAYOUT.middleware,
      data: { kind: 'middleware', items: [], disabled: true } },
    { id: NODE_ID.model, type: 'resource', position: DEFAULT_LAYOUT.model,
      data: { kind: 'model', items: [buildModelLabel(form.model, models)], disabled: false } },
  ];
}

export function buildEdges(): Edge[] {
  const kinds = ['skill', 'tool', 'subagent', 'middleware', 'model'] as const;
  return kinds.map((k) => ({
    id: `agent-${k}`,
    source: NODE_ID.agent,
    target: NODE_ID[k],
    type: 'default',          // bezier
    animated: false,
    style: { stroke: EDGE_COLOR[k], strokeWidth: 1.5, strokeDasharray: '6 6' },
  }));
}
```

> **노드 위치 동기화 주의**: `buildNodes`는 폼 변경 시 재호출되므로 `position`을 항상 `DEFAULT_LAYOUT`로 돌려보낸다. 드래그 위치를 보존하려면 캔버스가 **node `data`만 갱신**하고 `position`은 기존 RF state를 유지해야 한다 (§2.4 참조).

### 2.3 노드 컴포넌트

#### `nodes/AgentNode.tsx`
- 흰 카드 + 상단 라벨 "에이전트", 굵은 이름(`name` 또는 "새 에이전트"), 회색 설명(`description` 또는 "에이전트 설명을 입력하세요").
- 구분선 아래 `INSTRUCTIONS` 라벨 + `systemPrompt` 1~2줄 미리보기 또는 `EMPTY_TEXT.instructions`.
- 하단 "✏ Edit in Form" 버튼 → `data.onEditInForm()`.
- `<Handle type="source" position={Position.Right} />` + `Position.Top/Bottom/Left` (엣지 출발점). 핸들은 시각적으로 숨김(`opacity:0`).

#### `nodes/ResourceNode.tsx` (스킬/도구/서브/미들웨어/모델 공통)
- props: `data: ResourceNodeData & { onAction?: () => void }`.
- 종류별 헤더(아이콘+제목), 색상 토큰은 `kind`로 결정:
  | kind | 제목 | 액션 라벨 | 액션 동작 |
  |------|------|-----------|-----------|
  | skill | 📖 스킬 | + 스킬 추가 (disabled) | 없음 (준비중) |
  | tool | 🔧 도구 | + 도구 추가 | `onAction` → ToolPickerModal |
  | subagent | 👥 서브 에이전트 | ⚙ | `onAction` → SubAgentManagerModal |
  | middleware | ▥ 미들웨어 | + 미들웨어 추가 (disabled) | 없음 (준비중) |
  | model | ⚙ 모델 | (카드 클릭) | `onAction` → ModelSettingsModal |
- 본문: `items.length>0`면 목록(도구/서브에이전트명·MCP 배지 등), 아니면 `EMPTY_TEXT[kind]`. 모델은 항상 `items[0]`을 `<code>`로 표시.
- `<Handle type="target" position={Position.Left} opacity:0 />`.

#### `nodes/index.ts`
```typescript
export const nodeTypes = { agent: AgentNode, resource: ResourceNode };
```

### 2.4 캔버스 — `src/components/agent-builder/visual/VisualCanvas.tsx`

```typescript
interface VisualCanvasProps {
  form: AgentBuilderFormData;
  catalogTools?: CatalogTool[];
  models?: LlmModel[];
  onAddTool: () => void;          // → setToolModalOpen(true)
  onConfigModel: () => void;      // → setModelModalOpen(true)
  onManageSubAgents: () => void;  // → setSubAgentModalOpen(true)
  onEditInForm: () => void;       // → setLeftTab('form')
}
```

동작 설계:
1. `useNodesState`/`useEdgesState`로 노드/엣지 보유. 초기값 = `buildNodes`/`buildEdges`.
2. **폼 변경 반영**: `useEffect([form, catalogTools, models])`에서 `setNodes((prev) => mergeData(prev, buildNodes(...)))`.
   - `mergeData`: id 매칭하여 **`data`만 교체, `position`은 prev 유지** → 드래그 위치 보존 + 폼 내용 갱신.
3. **액션 주입**: 각 노드 `data`에 콜백 부착(`onEditInForm`, tool/subagent/model의 `onAction`). 콜백은 `useMemo`로 노드 빌드 시 합성.
4. **기본 레이아웃**: `Panel` 버튼 → `setNodes((prev)=> prev.map(n=>({...n, position: DEFAULT_LAYOUT[n.id]})))` + `fitView()`.
5. RF 옵션: `fitView`, `nodesDraggable`, `nodesConnectable={false}`, `edgesFocusable={false}`, `proOptions={{hideAttribution:true}}`, `minZoom=0.3`, `maxZoom=1.5`.
6. CSS: 진입 파일에서 `import '@xyflow/react/dist/style.css'` 1회.
7. 컨테이너: `<div style={{ width:'100%', height:'100%' }}>` (LeftConfigPanel 본문 flex:1 영역을 채움).

### 2.5 `LeftConfigPanel.tsx` 수정

```diff
- const [leftTab, setLeftTab] = useState<LeftTabId>('form');
+ const [leftTab, setLeftTab] = useState<LeftTabId>('form');   // 동일, 사용처 추가

  // 탭바
- <button disabled title="준비중" className="...text-zinc-300">🕸 비주얼</button>
+ <button type="button" onClick={() => setLeftTab('visual')}
+   className={`border-b-2 px-3 py-2.5 text-[13px] font-medium transition-colors ${
+     leftTab==='visual' ? 'border-zinc-900 text-zinc-900'
+                        : 'border-transparent text-zinc-400 hover:text-zinc-600'}`}>
+   🕸 비주얼
+ </button>

  // 본문 영역 — 탭에 따라 분기
- <div style={{ flex:1, overflowY:'auto' }} className="px-3 py-2"> …폼… </div>
+ {leftTab === 'form' ? (
+   <div style={{ flex:1, overflowY:'auto' }} className="px-3 py-2"> …폼(기존)… </div>
+ ) : (
+   <div style={{ flex:1, minHeight:0 }}>
+     <VisualCanvas
+       form={form} catalogTools={catalogTools} models={models}
+       onAddTool={() => setToolModalOpen(true)}
+       onConfigModel={() => setModelModalOpen(true)}
+       onManageSubAgents={() => setSubAgentModalOpen(true)}
+       onEditInForm={() => setLeftTab('form')}
+     />
+   </div>
+ )}
```

모달 3종(`ModelSettingsModal`/`ToolPickerModal`/`SubAgentManagerModal`)은 **현 위치 그대로** 유지 — 비주얼 탭에서 콜백으로 동일 open 상태를 토글하면 그대로 적용 로직(`onApply`/`onToggle`/`onAdd`)이 폼을 갱신한다.

### 2.6 의존성/설정

- `npm install @xyflow/react --legacy-peer-deps` (React 19 peer 충돌 회피, 메모리: preexisting-frontend-test-failures).
- 번들: 비주얼 탭은 `const VisualCanvas = lazy(() => import('./visual/VisualCanvas'))` + `<Suspense>` 로 지연 로딩(폼 우선 사용자 영향 최소화). 선택사항이나 권장.

---

## 3. 데이터 흐름 (시퀀스)

```
사용자: 비주얼 탭 클릭
  → leftTab='visual' → VisualCanvas 마운트 → buildNodes/buildEdges → RF 렌더

사용자: 도구 노드 "도구 추가" 클릭
  → onAddTool() → LeftConfigPanel.setToolModalOpen(true)
  → ToolPickerModal onToggle → onToolToggle(toolId)
  → AgentBuilderPage form.tools 변경 → form prop 갱신
  → VisualCanvas useEffect → mergeData → 도구 노드 data.items 갱신 (위치 유지)

사용자: "Edit in Form" 클릭
  → onEditInForm() → setLeftTab('form') → 폼 본문 표시
```

---

## 4. 테스트 설계 (TDD)

> 실행: `npm run test:run -- --pool=threads` (Windows). RF 전체 렌더는 jsdom에서 불안정 → 순수 빌더·카드 중심.

### 4.1 `buildGraph.test.ts` (P1)
- `buildNodes`: 노드 6개, id/type 정확, 도구 노드 `items`=선택 도구명, 서브에이전트 노드 `items`=subAgents 이름, 스킬/미들웨어 `disabled:true & items:[]`.
- `buildModelLabel`: 매칭 시 `provider:model_name`, 미매칭 시 raw, 빈값 시 "모델 미선택".
- `buildEdges`: 엣지 5개, `source==='agent'`, 각 `style.stroke`=EDGE_COLOR.

### 4.2 `ResourceNode.test.tsx` (P2)
- 도구 노드 빈 상태 → "도구가 설정되지 않았습니다"; 도구 있으면 도구명 렌더.
- "도구 추가" 클릭 → `onAction` 호출.
- 스킬/미들웨어 액션 버튼 `disabled` (클릭해도 콜백 미호출, `title="준비중"`).
- 모델 노드 → `items[0]` 코드 라벨 렌더.
- ※ RF `Handle`은 `ReactFlowProvider`로 감싸 렌더(테스트 래퍼 제공).

### 4.3 `VisualCanvas.test.tsx` (P3, 스모크)
- `ResizeObserver` 폴리필 후 마운트.
- "Edit in Form" → `onEditInForm` 호출, 모델 노드 클릭 → `onConfigModel` 호출.

---

## 5. 영향 범위 / 리스크

| 항목 | 영향 | 대응 |
|------|------|------|
| 백엔드/API 계약 | 없음 | 폼 데이터만 시각화 |
| 번들 크기 | `@xyflow/react` 추가 | `lazy` 지연 로딩 |
| React 19 peer | 설치 충돌 가능 | `--legacy-peer-deps` |
| jsdom RF 렌더 | 테스트 불안정 | 순수 빌더/카드 위주 + ResizeObserver 폴리필 |
| 드래그 위치 vs 폼 갱신 | position 리셋 위험 | `mergeData`로 data만 교체, position 보존 |
| 스킬/미들웨어 미연동 | 플레이스홀더 | `disabled` + 확장 지점 주석 |

---

## 6. 구현 체크리스트 (Do 단계 입력)

- [ ] `@xyflow/react` 설치 + CSS import
- [ ] `constants.ts` (색상/좌표/빈 텍스트)
- [ ] `buildGraph.ts` + 테스트(Red→Green)
- [ ] `AgentNode.tsx` / `ResourceNode.tsx` + 테스트
- [ ] `nodes/index.ts` (nodeTypes)
- [ ] `VisualCanvas.tsx` (RF + Controls + 기본 레이아웃 + mergeData)
- [ ] `LeftConfigPanel.tsx` 비주얼 탭 활성화 + 콜백 배선 + lazy
- [ ] 스크린샷 대조 (색상/배치/빈 텍스트/줌·기본레이아웃)
- [ ] `type-check` + `test:run --pool=threads` + `lint`

---

## 7. 다음 단계

```
/pdca do agent-builder-visual-canvas
```
