import { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import Sidebar from '@/components/layout/Sidebar';
import FlowCanvas from '@/pages/WorkflowDesignerPage/FlowCanvas';
import type { Workflow, FlowNode, FlowEdge } from '@/types/workflow';

// ─── Location state 타입 ──────────────────────────────────────────────────────

interface BuilderLocationState {
  workflow?: Workflow;
  nodes?: FlowNode[];
  edges?: FlowEdge[];
}

// ─── FlowNode/FlowEdge → WorkflowStep[] 변환 (위상 정렬) ─────────────────────

const flowToSteps = (nodes: FlowNode[], edges: FlowEdge[]) => {
  const nodeMap = new Map(nodes.map(n => [n.id, n]));
  const inDegree = new Map(nodes.map(n => [n.id, 0]));
  const nextMap = new Map<string, string>();
  edges.forEach(e => {
    inDegree.set(e.toId, (inDegree.get(e.toId) ?? 0) + 1);
    nextMap.set(e.fromId, e.toId);
  });

  const ordered: FlowNode[] = [];
  const visited = new Set<string>();
  const sources = nodes
    .filter(n => (inDegree.get(n.id) ?? 0) === 0)
    .sort((a, b) => a.x - b.x);

  const traverse = (nodeId: string) => {
    if (visited.has(nodeId)) return;
    visited.add(nodeId);
    const node = nodeMap.get(nodeId);
    if (node) ordered.push(node);
    const nextId = nextMap.get(nodeId);
    if (nextId) traverse(nextId);
  };
  sources.forEach(n => traverse(n.id));
  // 연결되지 않은 노드: x 좌표 기준 추가
  nodes.filter(n => !visited.has(n.id)).sort((a, b) => a.x - b.x).forEach(n => ordered.push(n));

  return ordered.map(n => ({ type: n.type, label: n.label }));
};

// ─── Page ────────────────────────────────────────────────────────────────────

const WorkflowBuilderPage = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const state = (location.state ?? {}) as BuilderLocationState;

  // 갤러리에서 편집으로 진입했을 때 초기 데이터 세팅
  const initialName = state.workflow?.name ?? '새 워크플로우';
  const initialNodes = state.nodes ?? [];
  const initialEdges = state.edges ?? [];

  const [saveResult, setSaveResult] = useState<{ name: string; stepCount: number } | null>(null);

  const handleSave = (name: string, nodes: FlowNode[], edges: FlowEdge[]) => {
    // FlowNode/FlowEdge → WorkflowStep[] 변환 (Mock 저장)
    const steps = flowToSteps(nodes, edges);
    console.log('[WorkflowBuilderPage][MOCK] Saved workflow:', { name, steps, nodes, edges });
    setSaveResult({ name, stepCount: steps.length });
    // TODO: 서버 연동 시 여기서 API 호출 (POST /api/workflows 또는 PUT /api/workflows/{id})
  };

  const handleBack = () => {
    navigate('/workflow-designer');
  };

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
      <Sidebar sessions={[]} activeSessionId={null} onSelectSession={() => {}} onNewChat={() => {}} />

      <main style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
        {/* 저장 결과 배너 */}
        {saveResult && (
          <div className="flex shrink-0 items-center justify-between border-b border-emerald-200 bg-emerald-50 px-6 py-2">
            <span className="text-[12.5px] text-emerald-700">
              ✓ <strong>{saveResult.name}</strong> 저장됨 (Mock) — {saveResult.stepCount}개 단계
            </span>
            <div className="flex items-center gap-2">
              <span className="text-[11.5px] text-emerald-500">추후 서버 연동 시 갤러리에 반영됩니다</span>
              <button
                onClick={() => setSaveResult(null)}
                className="text-emerald-400 hover:text-emerald-600 transition-colors"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>
        )}

        <FlowCanvas
          initialName={initialName}
          initialNodes={initialNodes}
          initialEdges={initialEdges}
          onSave={handleSave}
          onBack={handleBack}
        />
      </main>
    </div>
  );
};

export default WorkflowBuilderPage;
