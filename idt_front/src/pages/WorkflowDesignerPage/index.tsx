import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Sidebar from '@/components/layout/Sidebar';
import type { Workflow, WorkflowCategory, WorkflowStepType, FlowNode, FlowEdge } from '@/types/workflow';
import { WORKFLOW_CATEGORY, WORKFLOW_CATEGORY_LABEL, WORKFLOW_STEP_TYPE } from '@/types/workflow';

// ─── Workflow → FlowNode/FlowEdge 변환 ──────────────────────────────────────

let _nodeIdCounter = 0;
const genNodeId = () => `init-node-${++_nodeIdCounter}`;

const workflowToFlow = (workflow: Workflow): { nodes: FlowNode[]; edges: FlowEdge[] } => {
  const GAP_X = 180;
  const nodes: FlowNode[] = workflow.steps.map((step, i) => ({
    id: genNodeId(),
    type: step.type,
    label: step.label,
    x: 60 + i * GAP_X,
    y: 140,
  }));
  const edges: FlowEdge[] = nodes.slice(0, -1).map((node, i) => ({
    id: `init-edge-${i}`,
    fromId: node.id,
    toId: nodes[i + 1].id,
  }));
  return { nodes, edges };
};

// ─── Step Style Map ─────────────────────────────────────────────────────────

const STEP_STYLE: Record<WorkflowStepType, { bg: string; label: string }> = {
  input:     { bg: 'bg-zinc-400',    label: '입력' },
  search:    { bg: 'bg-sky-400',     label: '검색' },
  code:      { bg: 'bg-amber-400',   label: '코드' },
  llm:       { bg: 'bg-violet-500',  label: 'LLM' },
  condition: { bg: 'bg-orange-400',  label: '조건' },
  output:    { bg: 'bg-emerald-400', label: '출력' },
  api:       { bg: 'bg-pink-400',    label: 'API' },
};

// ─── Category Style Map ──────────────────────────────────────────────────────

const CAT_STYLE: Record<WorkflowCategory, { bg: string; text: string; dot: string }> = {
  search:     { bg: 'bg-sky-50',     text: 'text-sky-600',     dot: 'bg-sky-400' },
  analysis:   { bg: 'bg-violet-50',  text: 'text-violet-600',  dot: 'bg-violet-400' },
  automation: { bg: 'bg-emerald-50', text: 'text-emerald-600', dot: 'bg-emerald-400' },
  custom:     { bg: 'bg-zinc-100',   text: 'text-zinc-600',    dot: 'bg-zinc-400' },
};

// ─── Mock Data ───────────────────────────────────────────────────────────────

const MOCK_WORKFLOWS: Workflow[] = [
  {
    id: 'rag-qa',
    name: 'RAG Q&A',
    description: '문서를 검색하여 컨텍스트를 구성하고 LLM이 정확한 답변을 생성합니다.',
    category: WORKFLOW_CATEGORY.search,
    steps: [
      { type: WORKFLOW_STEP_TYPE.input,  label: '질문 입력' },
      { type: WORKFLOW_STEP_TYPE.search, label: '문서 검색' },
      { type: WORKFLOW_STEP_TYPE.llm,    label: 'LLM 답변' },
      { type: WORKFLOW_STEP_TYPE.output, label: '결과 출력' },
    ],
    estimatedTime: '~3초',
    active: true,
    runCount: 142,
  },
  {
    id: 'web-analysis',
    name: '웹 검색 분석',
    description: '웹에서 최신 정보를 수집하고 LLM이 핵심 내용을 분석·요약합니다.',
    category: WORKFLOW_CATEGORY.search,
    steps: [
      { type: WORKFLOW_STEP_TYPE.input,  label: '쿼리 입력' },
      { type: WORKFLOW_STEP_TYPE.search, label: '웹 검색' },
      { type: WORKFLOW_STEP_TYPE.llm,    label: 'LLM 분석' },
      { type: WORKFLOW_STEP_TYPE.output, label: '보고서 출력' },
    ],
    estimatedTime: '~5초',
    active: true,
    runCount: 87,
  },
  {
    id: 'doc-summary',
    name: '문서 요약',
    description: '업로드된 문서를 청킹하여 LLM이 핵심 내용을 구조화된 형태로 요약합니다.',
    category: WORKFLOW_CATEGORY.analysis,
    steps: [
      { type: WORKFLOW_STEP_TYPE.input,  label: '파일 업로드' },
      { type: WORKFLOW_STEP_TYPE.code,   label: '청킹 처리' },
      { type: WORKFLOW_STEP_TYPE.llm,    label: 'LLM 요약' },
      { type: WORKFLOW_STEP_TYPE.output, label: '요약 출력' },
    ],
    estimatedTime: '~8초',
    active: false,
    runCount: 56,
  },
  {
    id: 'code-review',
    name: '코드 리뷰',
    description: '코드를 정적 분석 후 LLM이 버그, 개선점, 보안 취약점을 리뷰합니다.',
    category: WORKFLOW_CATEGORY.analysis,
    steps: [
      { type: WORKFLOW_STEP_TYPE.input,     label: '코드 입력' },
      { type: WORKFLOW_STEP_TYPE.code,      label: '정적 분석' },
      { type: WORKFLOW_STEP_TYPE.llm,       label: 'LLM 리뷰' },
      { type: WORKFLOW_STEP_TYPE.output,    label: '리포트 출력' },
    ],
    estimatedTime: '~6초',
    active: false,
    runCount: 23,
  },
  {
    id: 'email-automation',
    name: '이메일 자동화',
    description: '트리거 이벤트 발생 시 조건을 판단하고 LLM이 이메일을 작성하여 자동 전송합니다.',
    category: WORKFLOW_CATEGORY.automation,
    steps: [
      { type: WORKFLOW_STEP_TYPE.input,     label: '트리거' },
      { type: WORKFLOW_STEP_TYPE.condition, label: '조건 판단' },
      { type: WORKFLOW_STEP_TYPE.llm,       label: '이메일 작성' },
      { type: WORKFLOW_STEP_TYPE.api,       label: '메일 전송' },
    ],
    estimatedTime: '~4초',
    active: true,
    runCount: 310,
  },
  {
    id: 'data-pipeline',
    name: '데이터 분석 파이프라인',
    description: 'CSV 데이터를 전처리하고 통계 분석 후 LLM이 인사이트를 도출합니다.',
    category: WORKFLOW_CATEGORY.analysis,
    steps: [
      { type: WORKFLOW_STEP_TYPE.input,  label: 'CSV 업로드' },
      { type: WORKFLOW_STEP_TYPE.code,   label: '전처리' },
      { type: WORKFLOW_STEP_TYPE.code,   label: '통계 분석' },
      { type: WORKFLOW_STEP_TYPE.llm,    label: 'LLM 인사이트' },
      { type: WORKFLOW_STEP_TYPE.output, label: '대시보드' },
    ],
    estimatedTime: '~12초',
    active: false,
    runCount: 11,
  },
  {
    id: 'alert-monitor',
    name: '이상 감지 알림',
    description: '지표를 주기적으로 모니터링하여 이상 징후 발생 시 자동으로 알림을 전송합니다.',
    category: WORKFLOW_CATEGORY.automation,
    steps: [
      { type: WORKFLOW_STEP_TYPE.api,       label: '지표 수집' },
      { type: WORKFLOW_STEP_TYPE.condition, label: '임계값 판단' },
      { type: WORKFLOW_STEP_TYPE.llm,       label: '원인 분석' },
      { type: WORKFLOW_STEP_TYPE.api,       label: '슬랙 알림' },
    ],
    estimatedTime: '~2초',
    active: false,
    runCount: 0,
  },
  {
    id: 'custom-workflow',
    name: '커스텀 워크플로우',
    description: '직접 단계를 구성하여 나만의 에이전트 워크플로우를 설계합니다.',
    category: WORKFLOW_CATEGORY.custom,
    steps: [
      { type: WORKFLOW_STEP_TYPE.input,  label: '시작' },
      { type: WORKFLOW_STEP_TYPE.llm,    label: 'LLM' },
      { type: WORKFLOW_STEP_TYPE.output, label: '출력' },
    ],
    estimatedTime: '가변',
    active: false,
    runCount: 0,
  },
];

// ─── Step Flow Visualization ─────────────────────────────────────────────────

interface StepFlowProps {
  steps: Workflow['steps'];
}

const StepFlow = ({ steps }: StepFlowProps) => (
  <div className="flex items-center gap-1 flex-wrap">
    {steps.map((step, i) => (
      <div key={i} className="flex items-center gap-1">
        <div className="flex flex-col items-center gap-0.5">
          <span className={`inline-flex h-5 w-5 items-center justify-center rounded-full text-[8.5px] font-bold text-white ${STEP_STYLE[step.type].bg}`}>
            {STEP_STYLE[step.type].label.slice(0, 2)}
          </span>
        </div>
        {i < steps.length - 1 && (
          <svg className="h-3 w-3 shrink-0 text-zinc-300" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5 21 12m0 0-7.5 7.5M21 12H3" />
          </svg>
        )}
      </div>
    ))}
  </div>
);

// ─── Workflow Card ───────────────────────────────────────────────────────────

interface WorkflowCardProps {
  workflow: Workflow;
  isSelected: boolean;
  onSelect: (id: string) => void;
  onToggle: (id: string) => void;
  onEdit: (workflow: Workflow) => void;
}

const WorkflowCard = ({ workflow, isSelected, onSelect, onToggle, onEdit }: WorkflowCardProps) => {
  const cat = CAT_STYLE[workflow.category];
  return (
    <div
      onClick={() => onSelect(workflow.id)}
      className={`group relative flex cursor-pointer flex-col overflow-hidden rounded-2xl border bg-white p-5 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg ${
        isSelected ? 'border-violet-400 ring-2 ring-violet-100' : workflow.active ? 'border-violet-200' : 'border-zinc-200'
      }`}
    >
      {/* 활성 상태 표시선 */}
      {workflow.active && (
        <div className="absolute inset-x-0 top-0 h-0.5 rounded-t-2xl" style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' }} />
      )}

      {/* 상단: 이름 + 편집 버튼 + 토글 */}
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-[14px] font-semibold text-zinc-900 leading-snug">{workflow.name}</h3>
        <div className="flex items-center gap-1.5 shrink-0">
          {/* 편집 버튼 (hover 시 표시) */}
          <button
            onClick={(e) => { e.stopPropagation(); onEdit(workflow); }}
            className="flex items-center gap-1 rounded-lg border border-zinc-200 bg-zinc-50 px-2 py-1 text-[11px] font-medium text-zinc-500 opacity-0 group-hover:opacity-100 hover:border-violet-300 hover:text-violet-600 hover:bg-violet-50 transition-all"
          >
            <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125" />
            </svg>
            편집
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onToggle(workflow.id); }}
            className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors duration-200 ${workflow.active ? 'bg-violet-600' : 'bg-zinc-200'}`}
          >
            <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow-sm transition-transform duration-200 ${workflow.active ? 'translate-x-4' : 'translate-x-0.5'}`} />
          </button>
        </div>
      </div>

      {/* 설명 */}
      <p className="mt-1.5 text-[12px] leading-[1.6] text-zinc-500 flex-1">{workflow.description}</p>

      {/* 단계 시각화 */}
      <div className="mt-3.5 rounded-xl bg-zinc-50 px-3 py-2.5">
        <StepFlow steps={workflow.steps} />
        <div className="mt-1.5 flex items-center gap-3">
          {workflow.steps.map((step, i) => (
            <span key={i} className={`text-[9.5px] font-medium ${STEP_STYLE[step.type].bg.replace('bg-', 'text-').replace('-400', '-600').replace('-500', '-600')}`}>
              {step.label}
            </span>
          ))}
        </div>
      </div>

      {/* 하단: 카테고리 + 메타 */}
      <div className="mt-3 flex items-center justify-between">
        <span className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium ${cat.bg} ${cat.text}`}>
          <span className={`h-1.5 w-1.5 rounded-full ${cat.dot}`} />
          {WORKFLOW_CATEGORY_LABEL[workflow.category]}
        </span>
        <div className="flex items-center gap-3 text-[11px] text-zinc-400">
          <span>{workflow.estimatedTime}</span>
          {(workflow.runCount ?? 0) > 0 && <span>{workflow.runCount?.toLocaleString()}회 실행</span>}
          {workflow.active && <span className="flex items-center gap-1 text-emerald-500"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />활성</span>}
        </div>
      </div>
    </div>
  );
};

// ─── Step Legend ─────────────────────────────────────────────────────────────

const STEP_LEGEND = Object.entries(STEP_STYLE).map(([key, val]) => ({ type: key as WorkflowStepType, ...val }));

// ─── Filter Tabs ─────────────────────────────────────────────────────────────

type FilterType = 'all' | WorkflowCategory;

const FILTER_TABS: { key: FilterType; label: string }[] = [
  { key: 'all', label: '전체' },
  { key: WORKFLOW_CATEGORY.search, label: '검색' },
  { key: WORKFLOW_CATEGORY.analysis, label: '분석' },
  { key: WORKFLOW_CATEGORY.automation, label: '자동화' },
  { key: WORKFLOW_CATEGORY.custom, label: '커스텀' },
];

// ─── Page ────────────────────────────────────────────────────────────────────

const WorkflowDesignerPage = () => {
  const navigate = useNavigate();
  const [workflows, setWorkflows] = useState<Workflow[]>(MOCK_WORKFLOWS);
  const [activeFilter, setActiveFilter] = useState<FilterType>('all');
  const [selectedId, setSelectedId] = useState<string | null>('rag-qa');

  const activeCount = workflows.filter((w) => w.active).length;

  const filtered = activeFilter === 'all' ? workflows : workflows.filter((w) => w.category === activeFilter);

  const selectedWorkflow = workflows.find((w) => w.id === selectedId);

  const handleToggle = (id: string) =>
    setWorkflows((prev) => prev.map((w) => (w.id === id ? { ...w, active: !w.active } : w)));

  const handleEdit = (workflow: Workflow) => {
    const { nodes, edges } = workflowToFlow(workflow);
    navigate('/workflow-builder', { state: { workflow, nodes, edges } });
  };

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden', background: '#fff' }}>
      <Sidebar sessions={[]} activeSessionId={null} onSelectSession={() => {}} onNewChat={() => {}} />

      <main style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden', background: '#fff' }}>
        {/* 헤더 */}
        <header className="flex shrink-0 items-center justify-between border-b border-zinc-200 bg-white px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl shadow-md" style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' }}>
              <svg className="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 3v11.25A2.25 2.25 0 0 0 6 16.5h2.25M3.75 3h-1.5m1.5 0h16.5m0 0h1.5m-1.5 0v11.25A2.25 2.25 0 0 1 18 16.5h-2.25m-7.5 0h7.5m-7.5 0-1 3m8.5-3 1 3m0 0 .5 1.5m-.5-1.5h-9.5m0 0-.5 1.5M9 11.25v1.5M12 9v3.75m3-6v6" />
              </svg>
            </div>
            <div>
              <h1 className="text-[15px] font-semibold text-zinc-900">워크플로우 설계</h1>
              <p className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">Workflow Designer</p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* 단계 범례 */}
            <div className="flex items-center gap-2 rounded-xl border border-zinc-100 bg-zinc-50 px-3 py-1.5">
              {STEP_LEGEND.map(({ type, bg, label }) => (
                <div key={type} className="flex items-center gap-1">
                  <span className={`h-2.5 w-2.5 rounded-full ${bg}`} />
                  <span className="text-[10.5px] text-zinc-500">{label}</span>
                </div>
              ))}
            </div>
            <div className="flex items-center gap-2 rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2">
              <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
              <span className="text-[13px] font-medium text-zinc-700">{activeCount}개 활성</span>
              <span className="text-[12px] text-zinc-400">/ {workflows.length}개</span>
            </div>
            {/* 플로우 빌더 이동 버튼 */}
            <button
              onClick={() => navigate('/workflow-builder')}
              className="flex items-center gap-1.5 rounded-xl bg-violet-600 px-4 py-2 text-[13px] font-medium text-white shadow-sm hover:bg-violet-700 active:scale-95 transition-all"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
              </svg>
              플로우 빌더
            </button>
          </div>
        </header>

        {/* 콘텐츠 */}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          <div style={{ maxWidth: '1024px', margin: '0 auto', padding: '1.5rem' }}>
            {/* 필터 탭 */}
            <div className="mb-6 flex items-center gap-1.5">
              {FILTER_TABS.map(({ key, label }) => (
                <button
                  key={key}
                  onClick={() => setActiveFilter(key)}
                  className={`rounded-xl px-4 py-2 text-[13px] font-medium transition-all ${
                    activeFilter === key ? 'bg-violet-600 text-white shadow-sm' : 'bg-zinc-100 text-zinc-600 hover:bg-zinc-200'
                  }`}
                >
                  {label}
                  <span className={`ml-1.5 text-[11px] ${activeFilter === key ? 'text-violet-200' : 'text-zinc-400'}`}>
                    {key === 'all' ? workflows.length : workflows.filter((w) => w.category === key).length}
                  </span>
                </button>
              ))}
            </div>

            {/* 카드 그리드 */}
            <div className="grid grid-cols-3 gap-4">
              {filtered.map((wf) => (
                <WorkflowCard
                  key={wf.id}
                  workflow={wf}
                  isSelected={selectedId === wf.id}
                  onSelect={setSelectedId}
                  onToggle={handleToggle}
                  onEdit={handleEdit}
                />
              ))}
            </div>

            {/* 선택된 워크플로우 상세 */}
            {selectedWorkflow && (
              <div className="mt-6 overflow-hidden rounded-2xl border border-violet-200 bg-violet-50/40">
                <div className="border-b border-violet-100 px-6 py-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">선택된 워크플로우</p>
                      <h3 className="mt-0.5 text-[15px] font-semibold text-zinc-900">{selectedWorkflow.name}</h3>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="flex items-center gap-2 text-[12px] text-zinc-400">
                        <span>예상 소요: {selectedWorkflow.estimatedTime}</span>
                        {(selectedWorkflow.runCount ?? 0) > 0 && <span>· 총 {selectedWorkflow.runCount?.toLocaleString()}회 실행</span>}
                      </div>
                      <button
                        onClick={() => handleEdit(selectedWorkflow)}
                        className="flex items-center gap-1.5 rounded-xl border border-violet-300 bg-white px-3 py-1.5 text-[12.5px] font-medium text-violet-600 hover:bg-violet-50 transition-all"
                      >
                        <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125" />
                        </svg>
                        캔버스에서 편집
                      </button>
                    </div>
                  </div>
                </div>
                <div className="px-6 py-5">
                  {/* 상세 플로우 */}
                  <div className="flex items-center gap-3 overflow-x-auto pb-2">
                    {selectedWorkflow.steps.map((step, i) => (
                      <div key={i} className="flex items-center gap-3 shrink-0">
                        <div className="flex flex-col items-center gap-1.5">
                          <div className={`flex h-12 w-12 items-center justify-center rounded-2xl text-white shadow-sm ${STEP_STYLE[step.type].bg}`}>
                            <span className="text-[11px] font-bold">{STEP_STYLE[step.type].label}</span>
                          </div>
                          <span className="text-[11.5px] font-medium text-zinc-700 whitespace-nowrap">{step.label}</span>
                        </div>
                        {i < selectedWorkflow.steps.length - 1 && (
                          <svg className="h-5 w-5 shrink-0 text-zinc-300 mb-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5 21 12m0 0-7.5 7.5M21 12H3" />
                          </svg>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* 활성 워크플로우 요약 */}
            {activeCount > 0 && (
              <div className="mt-4 rounded-2xl border border-zinc-200 bg-zinc-50/60 p-5">
                <p className="mb-3 text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">활성화된 워크플로우</p>
                <div className="flex flex-wrap gap-2">
                  {workflows.filter((w) => w.active).map((w) => {
                    const cat = CAT_STYLE[w.category];
                    return (
                      <div key={w.id} className={`flex items-center gap-2 rounded-xl border px-3 py-2 ${cat.bg} border-transparent`}>
                        <span className={`h-1.5 w-1.5 animate-pulse rounded-full ${cat.dot}`} />
                        <span className={`text-[12.5px] font-medium ${cat.text}`}>{w.name}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
};

export default WorkflowDesignerPage;
