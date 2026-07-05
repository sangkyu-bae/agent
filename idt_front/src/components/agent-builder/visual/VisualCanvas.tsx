import { useCallback, useEffect, useMemo } from 'react';
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  Panel,
  useNodesState,
  useEdgesState,
  useReactFlow,
  type Node,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import type { AgentBuilderFormData } from '@/types/agentBuilder';
import type { CatalogTool } from '@/types/toolCatalog';
import type { LlmModel } from '@/types/llmModel';
import { buildNodes, buildEdges } from './buildGraph';
import { DEFAULT_LAYOUT, NODE_ID } from './constants';
import { nodeTypes } from './nodes';

interface VisualCanvasProps {
  form: AgentBuilderFormData;
  catalogTools?: CatalogTool[];
  models?: LlmModel[];
  onAddTool: () => void;
  onConfigModel: () => void;
  onManageSubAgents: () => void;
  onEditInForm: () => void;
}

/** 노드별 액션 콜백을 data에 주입. */
function withCallbacks(
  nodes: Node[],
  cb: Pick<VisualCanvasProps, 'onAddTool' | 'onConfigModel' | 'onManageSubAgents' | 'onEditInForm'>,
): Node[] {
  return nodes.map((node) => {
    if (node.id === NODE_ID.agent) {
      return { ...node, data: { ...node.data, onEditInForm: cb.onEditInForm } };
    }
    const actionMap: Record<string, (() => void) | undefined> = {
      [NODE_ID.tool]: cb.onAddTool,
      [NODE_ID.subagent]: cb.onManageSubAgents,
      [NODE_ID.model]: cb.onConfigModel,
    };
    return { ...node, data: { ...node.data, onAction: actionMap[node.id] } };
  });
}

/** prev 노드의 position을 보존하면서 next의 data로 교체 (드래그 위치 유지). */
function mergeData(prev: Node[], next: Node[]): Node[] {
  const posById = new Map(prev.map((n) => [n.id, n.position]));
  return next.map((n) => ({ ...n, position: posById.get(n.id) ?? n.position }));
}

const CanvasInner = ({
  form,
  catalogTools,
  models,
  onAddTool,
  onConfigModel,
  onManageSubAgents,
  onEditInForm,
}: VisualCanvasProps) => {
  const callbacks = useMemo(
    () => ({ onAddTool, onConfigModel, onManageSubAgents, onEditInForm }),
    [onAddTool, onConfigModel, onManageSubAgents, onEditInForm],
  );

  const initialNodes = useMemo(
    () => withCallbacks(buildNodes(form, catalogTools, models), callbacks),
    // 최초 1회만 — 이후 갱신은 useEffect의 mergeData가 담당
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, , onEdgesChange] = useEdgesState(buildEdges());
  const { fitView } = useReactFlow();

  // 폼/카탈로그/모델 변경 시 data만 갱신 (position 보존)
  useEffect(() => {
    const rebuilt = withCallbacks(buildNodes(form, catalogTools, models), callbacks);
    setNodes((prev) => mergeData(prev, rebuilt));
  }, [form, catalogTools, models, callbacks, setNodes]);

  const handleResetLayout = useCallback(() => {
    setNodes((prev) =>
      prev.map((n) => ({ ...n, position: { ...DEFAULT_LAYOUT[n.id as keyof typeof DEFAULT_LAYOUT] } })),
    );
    window.requestAnimationFrame(() => fitView({ duration: 300 }));
  }, [setNodes, fitView]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      nodesConnectable={false}
      edgesFocusable={false}
      fitView
      minZoom={0.3}
      maxZoom={1.5}
      proOptions={{ hideAttribution: true }}
    >
      <Background gap={16} color="#e4e4e7" />
      <Controls position="bottom-left" showInteractive={false} />
      <Panel position="top-right">
        <button
          type="button"
          onClick={handleResetLayout}
          className="flex items-center gap-1 rounded-xl border border-zinc-200 bg-white px-3 py-1.5 text-[12.5px] font-medium text-zinc-600 shadow-sm transition-colors hover:border-zinc-300 hover:bg-zinc-50"
        >
          ↻ 기본 레이아웃
        </button>
      </Panel>
    </ReactFlow>
  );
};

/**
 * Agent Builder 비주얼 캔버스 — 폼 상태를 React Flow 노드 그래프로 시각화.
 * agent-builder-visual-canvas Design §2.4.
 */
const VisualCanvas = (props: VisualCanvasProps) => (
  <div style={{ width: '100%', height: '100%' }}>
    <ReactFlowProvider>
      <CanvasInner {...props} />
    </ReactFlowProvider>
  </div>
);

export default VisualCanvas;
