import { useState, useRef, useCallback } from 'react';
import type { WorkflowStepType, FlowNode, FlowEdge } from '@/types/workflow';
import { WORKFLOW_STEP_TYPE } from '@/types/workflow';

// ─── Constants ───────────────────────────────────────────────────────────────

const NODE_W = 140;
const NODE_H = 64;

const STEP_STYLE: Record<WorkflowStepType, { bg: string; border: string; text: string; dot: string; label: string; desc: string }> = {
  input:     { bg: 'bg-zinc-50',     border: 'border-zinc-300',    text: 'text-zinc-700',    dot: 'bg-zinc-400',    label: '입력',  desc: '사용자 입력 수신' },
  search:    { bg: 'bg-sky-50',      border: 'border-sky-300',     text: 'text-sky-700',     dot: 'bg-sky-400',     label: '검색',  desc: '문서/웹 검색' },
  code:      { bg: 'bg-amber-50',    border: 'border-amber-300',   text: 'text-amber-700',   dot: 'bg-amber-400',   label: '코드',  desc: '코드 실행·처리' },
  llm:       { bg: 'bg-violet-50',   border: 'border-violet-300',  text: 'text-violet-700',  dot: 'bg-violet-500',  label: 'LLM',   desc: 'LLM 추론 호출' },
  condition: { bg: 'bg-orange-50',   border: 'border-orange-300',  text: 'text-orange-700',  dot: 'bg-orange-400',  label: '조건',  desc: '분기 조건 판단' },
  output:    { bg: 'bg-emerald-50',  border: 'border-emerald-300', text: 'text-emerald-700', dot: 'bg-emerald-400', label: '출력',  desc: '결과 출력' },
  api:       { bg: 'bg-pink-50',     border: 'border-pink-300',    text: 'text-pink-700',    dot: 'bg-pink-400',    label: 'API',   desc: '외부 API 호출' },
};

const PALETTE_TYPES = Object.keys(WORKFLOW_STEP_TYPE) as WorkflowStepType[];

// ─── Helpers ─────────────────────────────────────────────────────────────────

const outPt = (n: FlowNode) => ({ x: n.x + NODE_W, y: n.y + NODE_H / 2 });
const inPt  = (n: FlowNode) => ({ x: n.x,          y: n.y + NODE_H / 2 });

const bezier = (x1: number, y1: number, x2: number, y2: number) => {
  const dx = Math.max(Math.abs(x2 - x1) * 0.5, 60);
  return `M${x1},${y1} C${x1 + dx},${y1} ${x2 - dx},${y2} ${x2},${y2}`;
};

let _idCounter = 0;
const genNodeId = () => `node-${++_idCounter}-${Date.now()}`;
const genEdgeId = () => `edge-${Date.now()}-${Math.random().toString(36).slice(2)}`;

// ─── Mock event dispatcher ────────────────────────────────────────────────────
// 서버 연동 전 Mock 이벤트: 콘솔에 출력 후 추후 서버로 전송

type FlowEvent =
  | { type: 'NODE_ADDED';   payload: FlowNode }
  | { type: 'NODE_MOVED';   payload: { id: string; x: number; y: number } }
  | { type: 'NODE_DELETED'; payload: { id: string } }
  | { type: 'EDGE_CREATED'; payload: FlowEdge }
  | { type: 'EDGE_DELETED'; payload: { id: string } }
  | { type: 'WORKFLOW_SAVED'; payload: { name: string; nodes: FlowNode[]; edges: FlowEdge[] } };

const dispatchFlowEvent = (event: FlowEvent) => {
  // TODO: 추후 서버 연동 시 이 함수를 API 호출로 교체
  console.log('[FlowEvent][MOCK]', event.type, event.payload);
};

// ─── Props ───────────────────────────────────────────────────────────────────

export interface FlowCanvasProps {
  initialName?: string;
  initialNodes?: FlowNode[];
  initialEdges?: FlowEdge[];
  onSave: (name: string, nodes: FlowNode[], edges: FlowEdge[]) => void;
  onBack: () => void;
}

// ─── FlowCanvas ──────────────────────────────────────────────────────────────

const FlowCanvas = ({ initialName = '새 워크플로우', initialNodes = [], initialEdges = [], onSave, onBack }: FlowCanvasProps) => {
  const canvasRef = useRef<HTMLDivElement>(null);

  const [nodes, setNodes] = useState<FlowNode[]>(initialNodes);
  const [edges, setEdges] = useState<FlowEdge[]>(initialEdges);
  const [workflowName, setWorkflowName] = useState(initialName);

  // Dragging a placed node
  const [dragging, setDragging] = useState<{
    nodeId: string;
    startMouseX: number;
    startMouseY: number;
    startNodeX: number;
    startNodeY: number;
  } | null>(null);

  // Pending connection (from output port to cursor)
  const [connecting, setConnecting] = useState<{ fromId: string; mx: number; my: number } | null>(null);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [savedBlink, setSavedBlink] = useState(false);

  // ── Canvas helpers ──────────────────────────────────────────────────────

  const canvasPos = useCallback((e: React.MouseEvent) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return { x: 0, y: 0 };
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  }, []);

  // ── Palette DnD ─────────────────────────────────────────────────────────

  const handleDragOver = (e: React.DragEvent) => e.preventDefault();

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const type = e.dataTransfer.getData('nodeType') as WorkflowStepType;
    if (!type || !STEP_STYLE[type]) return;
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const x = Math.max(0, e.clientX - rect.left - NODE_W / 2);
    const y = Math.max(0, e.clientY - rect.top - NODE_H / 2);
    const newNode: FlowNode = { id: genNodeId(), type, label: STEP_STYLE[type].label, x, y };
    setNodes(prev => [...prev, newNode]);
    setSelectedId(newNode.id);
    dispatchFlowEvent({ type: 'NODE_ADDED', payload: newNode });
  };

  // ── Node drag ───────────────────────────────────────────────────────────

  const handleNodeMouseDown = (e: React.MouseEvent, nodeId: string) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    const pos = canvasPos(e);
    const node = nodes.find(n => n.id === nodeId);
    if (!node) return;
    setDragging({ nodeId, startMouseX: pos.x, startMouseY: pos.y, startNodeX: node.x, startNodeY: node.y });
    setSelectedId(nodeId);
  };

  const handleCanvasMouseMove = (e: React.MouseEvent) => {
    const pos = canvasPos(e);
    if (dragging) {
      const dx = pos.x - dragging.startMouseX;
      const dy = pos.y - dragging.startMouseY;
      const newX = Math.max(0, dragging.startNodeX + dx);
      const newY = Math.max(0, dragging.startNodeY + dy);
      setNodes(prev => prev.map(n => n.id === dragging.nodeId ? { ...n, x: newX, y: newY } : n));
    }
    if (connecting) {
      setConnecting(prev => prev ? { ...prev, mx: pos.x, my: pos.y } : null);
    }
  };

  const handleCanvasMouseUp = (e: React.MouseEvent) => {
    if (dragging) {
      const pos = canvasPos(e);
      const dx = pos.x - dragging.startMouseX;
      const dy = pos.y - dragging.startMouseY;
      if (Math.abs(dx) > 2 || Math.abs(dy) > 2) {
        const movedNode = nodes.find(n => n.id === dragging.nodeId);
        if (movedNode) dispatchFlowEvent({ type: 'NODE_MOVED', payload: { id: movedNode.id, x: movedNode.x, y: movedNode.y } });
      }
      setDragging(null);
    }
  };

  // ── Port connections ────────────────────────────────────────────────────

  const handleOutPortClick = (e: React.MouseEvent, nodeId: string) => {
    e.stopPropagation();
    const node = nodes.find(n => n.id === nodeId);
    if (!node) return;
    const pt = outPt(node);
    setConnecting({ fromId: nodeId, mx: pt.x, my: pt.y });
  };

  const handleInPortClick = (e: React.MouseEvent, nodeId: string) => {
    e.stopPropagation();
    if (!connecting) return;
    if (connecting.fromId === nodeId) { setConnecting(null); return; }
    const already = edges.some(ed => ed.fromId === connecting.fromId && ed.toId === nodeId);
    if (!already) {
      const newEdge: FlowEdge = { id: genEdgeId(), fromId: connecting.fromId, toId: nodeId };
      setEdges(prev => [...prev, newEdge]);
      dispatchFlowEvent({ type: 'EDGE_CREATED', payload: newEdge });
    }
    setConnecting(null);
  };

  // ── Canvas click (deselect / cancel connection) ─────────────────────────

  const handleCanvasClick = () => {
    setSelectedId(null);
    setConnecting(null);
  };

  // ── Delete ──────────────────────────────────────────────────────────────

  const handleDeleteNode = () => {
    if (!selectedId) return;
    setNodes(prev => prev.filter(n => n.id !== selectedId));
    setEdges(prev => prev.filter(e => e.fromId !== selectedId && e.toId !== selectedId));
    dispatchFlowEvent({ type: 'NODE_DELETED', payload: { id: selectedId } });
    setSelectedId(null);
  };

  const handleDeleteEdge = (edgeId: string) => {
    setEdges(prev => prev.filter(e => e.id !== edgeId));
    dispatchFlowEvent({ type: 'EDGE_DELETED', payload: { id: edgeId } });
  };

  // ── Mock Save ───────────────────────────────────────────────────────────

  const handleSave = () => {
    dispatchFlowEvent({ type: 'WORKFLOW_SAVED', payload: { name: workflowName, nodes, edges } });
    onSave(workflowName, nodes, edges);
    setSavedBlink(true);
    setTimeout(() => setSavedBlink(false), 2000);
  };

  // ── Render ──────────────────────────────────────────────────────────────

  const isDraggingNode = dragging !== null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>

      {/* ── Toolbar ── */}
      <div className="flex shrink-0 items-center justify-between border-b border-zinc-200 bg-white px-4 py-3 gap-3">
        <div className="flex items-center gap-2">
          <button
            onClick={onBack}
            className="flex items-center gap-1.5 rounded-xl border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-[12.5px] font-medium text-zinc-600 hover:bg-zinc-100 transition-all"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5 3 12m0 0 7.5-7.5M3 12h18" />
            </svg>
            갤러리로
          </button>
          <input
            value={workflowName}
            onChange={e => setWorkflowName(e.target.value)}
            className="w-52 rounded-xl border border-zinc-200 px-3 py-1.5 text-[13.5px] font-semibold text-zinc-900 outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100 transition-all"
            placeholder="워크플로우 이름"
          />
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[12px] text-zinc-400">
            노드 {nodes.length}개 · 연결 {edges.length}개
          </span>
          {selectedId && (
            <button
              onClick={handleDeleteNode}
              className="flex items-center gap-1 rounded-xl border border-red-200 bg-red-50 px-3 py-1.5 text-[12.5px] font-medium text-red-500 hover:bg-red-100 transition-all"
            >
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
              </svg>
              노드 삭제
            </button>
          )}
          <button
            onClick={handleSave}
            className={`flex items-center gap-1.5 rounded-xl px-4 py-1.5 text-[13px] font-medium text-white shadow-sm transition-all active:scale-95 ${
              savedBlink ? 'bg-emerald-500' : 'bg-violet-600 hover:bg-violet-700'
            }`}
          >
            {savedBlink ? (
              <>
                <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
                </svg>
                저장됨
              </>
            ) : '저장'}
          </button>
        </div>
      </div>

      {/* ── Body ── */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>

        {/* Left palette */}
        <aside className="flex w-44 shrink-0 flex-col overflow-y-auto border-r border-zinc-200 bg-zinc-50 p-3">
          <p className="mb-2 text-[10.5px] font-semibold uppercase tracking-widest text-zinc-400">노드 팔레트</p>
          <div className="flex flex-col gap-1.5">
            {PALETTE_TYPES.map(type => {
              const s = STEP_STYLE[type];
              return (
                <div
                  key={type}
                  draggable
                  onDragStart={e => e.dataTransfer.setData('nodeType', type)}
                  title={s.desc}
                  className={`flex cursor-grab items-center gap-2.5 rounded-xl border px-3 py-2.5 text-[12.5px] font-medium select-none transition-all active:cursor-grabbing hover:shadow-sm hover:-translate-y-0.5 ${s.bg} ${s.border} ${s.text}`}
                >
                  <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${s.dot}`} />
                  <div>
                    <div>{s.label}</div>
                    <div className="text-[10px] font-normal opacity-60">{s.desc}</div>
                  </div>
                </div>
              );
            })}
          </div>
          <div className="mt-3 rounded-xl border border-dashed border-zinc-300 bg-white px-3 py-4 text-center text-[11px] leading-relaxed text-zinc-400">
            노드를 드래그하여<br />캔버스에 놓으세요
          </div>
        </aside>

        {/* Canvas */}
        <div
          ref={canvasRef}
          className="relative flex-1 overflow-hidden"
          style={{
            background: 'radial-gradient(circle, #d4d4d8 1px, transparent 1px)',
            backgroundSize: '24px 24px',
            backgroundColor: '#fafafa',
            cursor: connecting ? 'crosshair' : isDraggingNode ? 'grabbing' : 'default',
            userSelect: 'none',
          }}
          onDragOver={handleDragOver}
          onDrop={handleDrop}
          onMouseMove={handleCanvasMouseMove}
          onMouseUp={handleCanvasMouseUp}
          onClick={handleCanvasClick}
        >
          {/* Empty state */}
          {nodes.length === 0 && (
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-3">
              <div className="flex h-16 w-16 items-center justify-center rounded-2xl border-2 border-dashed border-zinc-300 text-2xl text-zinc-400">
                <svg className="h-7 w-7" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                </svg>
              </div>
              <p className="text-[13px] text-zinc-400">왼쪽 팔레트에서 노드를 드래그해서 시작하세요</p>
            </div>
          )}

          {/* SVG layer: edges */}
          <svg
            className="pointer-events-none absolute inset-0"
            style={{ width: '100%', height: '100%', zIndex: 1 }}
          >
            <defs>
              <marker id="fc-arrow" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
                <polygon points="0 0, 8 3, 0 6" fill="#8b5cf6" fillOpacity="0.75" />
              </marker>
              <marker id="fc-arrow-hover" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
                <polygon points="0 0, 8 3, 0 6" fill="#ef4444" fillOpacity="0.8" />
              </marker>
            </defs>

            {/* Existing edges */}
            {edges.map(edge => {
              const fromNode = nodes.find(n => n.id === edge.fromId);
              const toNode   = nodes.find(n => n.id === edge.toId);
              if (!fromNode || !toNode) return null;
              const from = outPt(fromNode);
              const to   = inPt(toNode);
              const d    = bezier(from.x, from.y, to.x, to.y);
              return (
                <g key={edge.id}>
                  {/* Invisible wide path for easy click */}
                  <path
                    d={d}
                    stroke="transparent"
                    strokeWidth={12}
                    fill="none"
                    style={{ pointerEvents: 'all', cursor: 'pointer' }}
                    onClick={e => { e.stopPropagation(); handleDeleteEdge(edge.id); }}
                    className="group"
                  />
                  {/* Visible edge */}
                  <path
                    d={d}
                    stroke="#8b5cf6"
                    strokeWidth={2}
                    strokeOpacity={0.7}
                    fill="none"
                    markerEnd="url(#fc-arrow)"
                  />
                </g>
              );
            })}

            {/* Pending connection */}
            {connecting && (() => {
              const fromNode = nodes.find(n => n.id === connecting.fromId);
              if (!fromNode) return null;
              const from = outPt(fromNode);
              return (
                <path
                  d={bezier(from.x, from.y, connecting.mx, connecting.my)}
                  stroke="#8b5cf6"
                  strokeWidth={1.5}
                  strokeDasharray="6 3"
                  strokeOpacity={0.5}
                  fill="none"
                />
              );
            })()}
          </svg>

          {/* Nodes */}
          {nodes.map(node => {
            const s = STEP_STYLE[node.type];
            const isSelected = selectedId === node.id;
            const isConnectingFrom = connecting?.fromId === node.id;
            const canReceive = connecting && connecting.fromId !== node.id;

            return (
              <div
                key={node.id}
                onClick={e => e.stopPropagation()}
                style={{
                  position: 'absolute',
                  left: node.x,
                  top: node.y,
                  width: NODE_W,
                  height: NODE_H,
                  zIndex: isSelected ? 20 : 10,
                }}
              >
                {/* Input port */}
                <button
                  onClick={e => handleInPortClick(e, node.id)}
                  style={{
                    position: 'absolute',
                    left: -8,
                    top: '50%',
                    transform: 'translateY(-50%)',
                    width: 16,
                    height: 16,
                    borderRadius: '50%',
                    zIndex: 30,
                    cursor: connecting ? 'crosshair' : 'default',
                    border: '2px solid',
                  }}
                  className={`bg-white transition-all ${
                    canReceive
                      ? 'border-violet-500 scale-125 shadow-md shadow-violet-200'
                      : 'border-zinc-300 hover:border-violet-400'
                  }`}
                />

                {/* Node body */}
                <div
                  onMouseDown={e => handleNodeMouseDown(e, node.id)}
                  className={`flex h-full w-full flex-col items-center justify-center rounded-2xl border-2 px-3 shadow-sm transition-all duration-100 ${s.bg} ${s.border} ${
                    isSelected ? 'ring-2 ring-violet-400 ring-offset-1 shadow-lg' : ''
                  } ${isConnectingFrom ? 'ring-2 ring-violet-500' : ''}`}
                  style={{ cursor: dragging?.nodeId === node.id ? 'grabbing' : 'grab' }}
                >
                  <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">{s.label}</span>
                  <span className={`mt-0.5 text-[12.5px] font-semibold ${s.text}`}>{node.label}</span>
                </div>

                {/* Output port */}
                <button
                  onClick={e => handleOutPortClick(e, node.id)}
                  style={{
                    position: 'absolute',
                    right: -8,
                    top: '50%',
                    transform: 'translateY(-50%)',
                    width: 16,
                    height: 16,
                    borderRadius: '50%',
                    zIndex: 30,
                    cursor: 'crosshair',
                    border: '2px solid',
                  }}
                  className={`transition-all ${
                    isConnectingFrom
                      ? 'bg-violet-500 border-violet-500 scale-125'
                      : 'bg-white border-zinc-300 hover:border-violet-400 hover:bg-violet-50'
                  }`}
                />
              </div>
            );
          })}
        </div>

        {/* Right help panel */}
        <aside className="flex w-44 shrink-0 flex-col border-l border-zinc-200 bg-zinc-50 p-3">
          <p className="mb-2 text-[10.5px] font-semibold uppercase tracking-widest text-zinc-400">사용 방법</p>
          <div className="flex flex-col gap-3 text-[11.5px] leading-relaxed text-zinc-500">
            {[
              { title: '노드 추가', desc: '팔레트에서 캔버스로 드래그' },
              { title: '노드 이동', desc: '노드를 드래그하여 위치 변경' },
              { title: '노드 연결', desc: '오른쪽 ○ 클릭 → 다른 노드의 왼쪽 ○ 클릭' },
              { title: '연결 삭제', desc: '연결선 클릭' },
              { title: '노드 삭제', desc: '노드 선택 후 상단 버튼' },
              { title: '연결 취소', desc: '캔버스 빈 곳 클릭' },
            ].map(item => (
              <div key={item.title} className="flex flex-col gap-0.5">
                <span className="font-semibold text-zinc-700">{item.title}</span>
                <span>{item.desc}</span>
              </div>
            ))}
          </div>

          {connecting && (
            <div className="mt-4 rounded-xl border border-violet-200 bg-violet-50 px-3 py-3 text-[11.5px] leading-relaxed text-violet-700">
              <span className="font-semibold">연결 중...</span>
              <br />다른 노드의 왼쪽 포트를 클릭하거나 빈 곳을 클릭하여 취소
            </div>
          )}

          <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-3 py-3 text-[11px] leading-relaxed text-amber-700">
            <span className="font-semibold">Mock 모드</span>
            <br />이벤트는 콘솔에 출력됩니다. 추후 서버 연동 예정.
          </div>
        </aside>
      </div>
    </div>
  );
};

export default FlowCanvas;
