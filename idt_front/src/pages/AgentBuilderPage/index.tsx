import { useState } from 'react';
import Sidebar from '@/components/layout/Sidebar';

type ViewMode = 'list' | 'create' | 'edit';
type AgentModel = 'claude-sonnet-4-6' | 'claude-haiku-4-5' | 'claude-opus-4-6' | 'gpt-4o';

interface Agent {
  id: string;
  name: string;
  description: string;
  model: AgentModel;
  systemPrompt: string;
  tools: string[];
  temperature: number;
  isActive: boolean;
  runCount: number;
  createdAt: string;
}

interface AgentFormData {
  name: string;
  description: string;
  model: AgentModel;
  systemPrompt: string;
  tools: string[];
  temperature: number;
}

const MODEL_LABELS: Record<AgentModel, string> = {
  'claude-sonnet-4-6': 'Claude Sonnet 4.6',
  'claude-haiku-4-5': 'Claude Haiku 4.5',
  'claude-opus-4-6': 'Claude Opus 4.6',
  'gpt-4o': 'GPT-4o',
};

const MODEL_COLORS: Record<AgentModel, string> = {
  'claude-sonnet-4-6': 'bg-violet-100 text-violet-700',
  'claude-haiku-4-5': 'bg-sky-100 text-sky-700',
  'claude-opus-4-6': 'bg-amber-100 text-amber-700',
  'gpt-4o': 'bg-emerald-100 text-emerald-700',
};

const AVAILABLE_TOOLS = [
  { id: 'web-search', label: '웹 검색', icon: 'M21 21l-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z' },
  { id: 'code-exec', label: '코드 실행', icon: 'M17.25 6.75 22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3-4.5 16.5' },
  { id: 'file-read', label: '파일 읽기', icon: 'M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z' },
  { id: 'db-query', label: 'DB 쿼리', icon: 'M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375m16.5 0c0-2.278-3.694-4.125-8.25-4.125S3.75 4.097 3.75 6.375m16.5 0v11.25c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125V6.375m16.5 5.625v5.625m-16.5-5.625v5.625' },
  { id: 'api-call', label: 'API 호출', icon: 'M13.19 8.688a4.5 4.5 0 0 1 1.242 7.244l-4.5 4.5a4.5 4.5 0 0 1-6.364-6.364l1.757-1.757m13.35-.622 1.757-1.757a4.5 4.5 0 0 0-6.364-6.364l-4.5 4.5a4.5 4.5 0 0 0 1.242 7.244' },
  { id: 'rag-retrieval', label: 'RAG 검색', icon: 'M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m5.231 13.481L15 17.25m-4.5-15H5.625c-.621 0-1.125.504-1.125 1.125v16.5c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Zm3.75 11.625a2.625 2.625 0 1 1-5.25 0 2.625 2.625 0 0 1 5.25 0Z' },
];

const MOCK_AGENTS: Agent[] = [
  {
    id: 'doc-analyst',
    name: '문서 분석가',
    description: 'PDF, Word 문서를 분석하여 핵심 내용을 요약하고 Q&A를 생성합니다.',
    model: 'claude-sonnet-4-6',
    systemPrompt: '당신은 전문 문서 분석 AI입니다. 업로드된 문서를 꼼꼼히 읽고 핵심 내용을 추출하며, 사용자의 질문에 정확하게 답변합니다.',
    tools: ['file-read', 'rag-retrieval'],
    temperature: 0.3,
    isActive: true,
    runCount: 142,
    createdAt: '2026-03-10',
  },
  {
    id: 'code-reviewer',
    name: '코드 리뷰어',
    description: '코드 품질, 보안 취약점, 성능 이슈를 분석하고 개선안을 제안합니다.',
    model: 'claude-opus-4-6',
    systemPrompt: '당신은 시니어 소프트웨어 엔지니어입니다. 코드를 리뷰할 때 버그, 보안 취약점, 성능 문제, 코드 품질을 중점적으로 분석합니다.',
    tools: ['code-exec', 'web-search'],
    temperature: 0.2,
    isActive: true,
    runCount: 87,
    createdAt: '2026-03-12',
  },
  {
    id: 'data-analyst',
    name: '데이터 분석가',
    description: '데이터셋을 분석하여 인사이트를 도출하고 시각화 보고서를 생성합니다.',
    model: 'claude-sonnet-4-6',
    systemPrompt: '당신은 데이터 분석 전문가입니다. 주어진 데이터를 분석하여 패턴을 발견하고, 비즈니스 인사이트를 도출하여 명확한 보고서를 작성합니다.',
    tools: ['code-exec', 'db-query', 'api-call'],
    temperature: 0.4,
    isActive: false,
    runCount: 31,
    createdAt: '2026-03-15',
  },
];

const DEFAULT_FORM: AgentFormData = {
  name: '',
  description: '',
  model: 'claude-sonnet-4-6',
  systemPrompt: '',
  tools: [],
  temperature: 0.7,
};

const AgentBuilderPage = () => {
  const [view, setView] = useState<ViewMode>('list');
  const [agents, setAgents] = useState<Agent[]>(MOCK_AGENTS);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<AgentFormData>(DEFAULT_FORM);

  const handleNew = () => {
    setForm(DEFAULT_FORM);
    setEditingId(null);
    setView('create');
  };

  const handleEdit = (agent: Agent) => {
    setForm({
      name: agent.name,
      description: agent.description,
      model: agent.model,
      systemPrompt: agent.systemPrompt,
      tools: agent.tools,
      temperature: agent.temperature,
    });
    setEditingId(agent.id);
    setView('edit');
  };

  const handleDelete = (id: string) => {
    setAgents((prev) => prev.filter((a) => a.id !== id));
  };

  const handleToggle = (id: string) => {
    setAgents((prev) =>
      prev.map((a) => (a.id === id ? { ...a, isActive: !a.isActive } : a))
    );
  };

  const handleSave = () => {
    if (!form.name.trim()) return;
    if (view === 'edit' && editingId) {
      setAgents((prev) =>
        prev.map((a) => (a.id === editingId ? { ...a, ...form } : a))
      );
    } else {
      const newAgent: Agent = {
        id: `agent-${Date.now()}`,
        ...form,
        isActive: false,
        runCount: 0,
        createdAt: new Date().toISOString().slice(0, 10),
      };
      setAgents((prev) => [newAgent, ...prev]);
    }
    setView('list');
  };

  const handleToolToggle = (toolId: string) => {
    setForm((prev) => ({
      ...prev,
      tools: prev.tools.includes(toolId)
        ? prev.tools.filter((t) => t !== toolId)
        : [...prev.tools, toolId],
    }));
  };

  const activeCount = agents.filter((a) => a.isActive).length;

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden', background: '#fff' }}>
      <Sidebar sessions={[]} activeSessionId={null} onSelectSession={() => {}} onNewChat={() => {}} />

      <main style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden', background: '#fff' }}>
        {/* 헤더 */}
        <header className="flex shrink-0 items-center justify-between border-b border-zinc-200 bg-white px-6 py-4">
          <div className="flex items-center gap-3">
            <div
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl shadow-md"
              style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' }}
            >
              <svg className="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 0 0-2.456 2.456Z" />
              </svg>
            </div>
            <div>
              {view === 'list' ? (
                <>
                  <h1 className="text-[15px] font-semibold text-zinc-900">에이전트 만들기</h1>
                  <p className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">
                    Agent Builder
                  </p>
                </>
              ) : (
                <>
                  <h1 className="text-[15px] font-semibold text-zinc-900">
                    {view === 'edit' ? '에이전트 수정' : '새 에이전트'}
                  </h1>
                  <p className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">
                    {view === 'edit' ? 'Edit Agent' : 'New Agent'}
                  </p>
                </>
              )}
            </div>
          </div>

          {view === 'list' ? (
            <div className="flex items-center gap-3">
              <span className="text-[12.5px] text-zinc-400">
                <span className="font-semibold text-violet-600">{activeCount}개</span> 활성 / 전체 {agents.length}개
              </span>
              <button
                onClick={handleNew}
                className="flex items-center gap-2 rounded-xl bg-violet-600 px-4 py-2 text-[13px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                </svg>
                새 에이전트
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <button
                onClick={() => setView('list')}
                className="flex items-center rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2 text-[13px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100"
              >
                취소
              </button>
              <button
                onClick={handleSave}
                disabled={!form.name.trim()}
                className="flex items-center gap-2 rounded-xl bg-violet-600 px-4 py-2 text-[13px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
              >
                저장
              </button>
            </div>
          )}
        </header>

        {/* 콘텐츠 */}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {view === 'list' ? (
            <ListView
              agents={agents}
              onEdit={handleEdit}
              onDelete={handleDelete}
              onToggle={handleToggle}
              onNew={handleNew}
            />
          ) : (
            <FormView form={form} onChange={setForm} onToolToggle={handleToolToggle} />
          )}
        </div>
      </main>
    </div>
  );
};

interface ListViewProps {
  agents: Agent[];
  onEdit: (agent: Agent) => void;
  onDelete: (id: string) => void;
  onToggle: (id: string) => void;
  onNew: () => void;
}

const ListView = ({ agents, onEdit, onDelete, onToggle, onNew }: ListViewProps) => {
  if (agents.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-32 text-center">
        <div
          className="mb-5 flex h-16 w-16 items-center justify-center rounded-2xl shadow-lg"
          style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' }}
        >
          <svg className="h-8 w-8 text-white" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
        </div>
        <p className="text-[15px] font-semibold text-zinc-900">에이전트가 없습니다</p>
        <p className="mt-1.5 text-[13px] text-zinc-400">첫 AI 에이전트를 만들어 보세요</p>
        <button
          onClick={onNew}
          className="mt-5 rounded-xl bg-violet-600 px-5 py-2.5 text-[13.5px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95"
        >
          새 에이전트 만들기
        </button>
      </div>
    );
  }

  return (
    <div className="p-6">
      <div className="grid grid-cols-3 gap-4">
        {agents.map((agent) => (
          <AgentCard
            key={agent.id}
            agent={agent}
            onEdit={onEdit}
            onDelete={onDelete}
            onToggle={onToggle}
          />
        ))}
      </div>

      {/* 활성 에이전트 요약 */}
      {agents.some((a) => a.isActive) && (
        <div className="mt-6 rounded-2xl border border-zinc-200 bg-zinc-50 p-4">
          <p className="mb-3 text-[11.5px] font-semibold uppercase tracking-widest text-zinc-400">
            활성 에이전트
          </p>
          <div className="flex flex-wrap gap-2">
            {agents.filter((a) => a.isActive).map((a) => (
              <span
                key={a.id}
                className="flex items-center gap-1.5 rounded-full border border-violet-200 bg-violet-50 px-3 py-1 text-[12px] font-medium text-violet-700"
              >
                <span className="h-1.5 w-1.5 rounded-full bg-violet-500" />
                {a.name}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

interface AgentCardProps {
  agent: Agent;
  onEdit: (agent: Agent) => void;
  onDelete: (id: string) => void;
  onToggle: (id: string) => void;
}

const AgentCard = ({ agent, onEdit, onDelete, onToggle }: AgentCardProps) => {
  const initials = agent.name.slice(0, 2);
  const gradients = [
    'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)',
    'linear-gradient(135deg, #0ea5e9 0%, #2563eb 100%)',
    'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)',
    'linear-gradient(135deg, #10b981 0%, #059669 100%)',
  ];
  const gradientIndex = agent.id.length % gradients.length;

  return (
    <div
      className={`group relative overflow-hidden rounded-2xl border bg-white p-5 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg ${
        agent.isActive ? 'border-violet-200' : 'border-zinc-200'
      }`}
    >
      {/* 카드 상단 */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-[13px] font-bold text-white shadow-md"
            style={{ background: gradients[gradientIndex] }}
          >
            {initials}
          </div>
          <div>
            <p className="text-[14px] font-semibold text-zinc-900">{agent.name}</p>
            <span className={`mt-0.5 inline-block rounded-full px-2 py-0.5 text-[10.5px] font-semibold ${MODEL_COLORS[agent.model]}`}>
              {MODEL_LABELS[agent.model]}
            </span>
          </div>
        </div>

        {/* 토글 스위치 */}
        <button
          onClick={() => onToggle(agent.id)}
          className={`relative h-5 w-9 rounded-full transition-colors duration-200 ${
            agent.isActive ? 'bg-violet-600' : 'bg-zinc-300'
          }`}
        >
          <span
            className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform duration-200 ${
              agent.isActive ? 'translate-x-4' : 'translate-x-0.5'
            }`}
          />
        </button>
      </div>

      {/* 설명 */}
      <p className="mt-3 line-clamp-2 text-[12.5px] leading-[1.6] text-zinc-500">{agent.description}</p>

      {/* 시스템 프롬프트 미리보기 */}
      <p className="mt-2.5 line-clamp-1 rounded-lg bg-zinc-50 px-3 py-2 text-[11.5px] italic text-zinc-400">
        {agent.systemPrompt}
      </p>

      {/* 도구 태그 */}
      {agent.tools.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {agent.tools.map((toolId) => {
            const tool = AVAILABLE_TOOLS.find((t) => t.id === toolId);
            return tool ? (
              <span key={toolId} className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-medium text-zinc-500">
                {tool.label}
              </span>
            ) : null;
          })}
        </div>
      )}

      {/* 메타 정보 + 액션 버튼 */}
      <div className="mt-4 flex items-center justify-between border-t border-zinc-100 pt-3">
        <div className="flex items-center gap-3 text-[11.5px] text-zinc-400">
          <span className="flex items-center gap-1">
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.347a1.125 1.125 0 0 1 0 1.972l-11.54 6.347a1.125 1.125 0 0 1-1.667-.986V5.653Z" />
            </svg>
            {agent.runCount}회 실행
          </span>
          <span>{agent.createdAt}</span>
        </div>

        <div className="flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
          <button
            onClick={() => onEdit(agent)}
            className="rounded-lg p-1.5 text-zinc-400 transition-colors hover:bg-zinc-100 hover:text-zinc-700"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125" />
            </svg>
          </button>
          <button
            onClick={() => onDelete(agent.id)}
            className="rounded-lg p-1.5 text-zinc-400 transition-colors hover:bg-red-50 hover:text-red-500"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
};

interface FormViewProps {
  form: AgentFormData;
  onChange: (form: AgentFormData) => void;
  onToolToggle: (toolId: string) => void;
}

const FormView = ({ form, onChange, onToolToggle }: FormViewProps) => {
  return (
    <div style={{ maxWidth: '720px', margin: '0 auto', padding: '2rem 1.5rem' }}>
      <div className="space-y-6">
        {/* 이름 */}
        <div>
          <label className="mb-1.5 block text-[13px] font-semibold text-zinc-700">
            에이전트 이름 <span className="text-red-400">*</span>
          </label>
          <input
            type="text"
            value={form.name}
            onChange={(e) => onChange({ ...form, name: e.target.value })}
            placeholder="예: 문서 분석가"
            className="w-full rounded-xl border border-zinc-300 bg-white px-4 py-2.5 text-[14px] text-zinc-900 placeholder-zinc-400 outline-none transition-all focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
          />
        </div>

        {/* 설명 */}
        <div>
          <label className="mb-1.5 block text-[13px] font-semibold text-zinc-700">설명</label>
          <input
            type="text"
            value={form.description}
            onChange={(e) => onChange({ ...form, description: e.target.value })}
            placeholder="에이전트의 역할과 용도를 간략히 설명하세요"
            className="w-full rounded-xl border border-zinc-300 bg-white px-4 py-2.5 text-[14px] text-zinc-900 placeholder-zinc-400 outline-none transition-all focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
          />
        </div>

        {/* 모델 선택 */}
        <div>
          <label className="mb-1.5 block text-[13px] font-semibold text-zinc-700">모델</label>
          <div className="grid grid-cols-4 gap-2">
            {(Object.keys(MODEL_LABELS) as AgentModel[]).map((model) => (
              <button
                key={model}
                onClick={() => onChange({ ...form, model })}
                className={`rounded-xl border px-3 py-2.5 text-[12px] font-medium transition-all ${
                  form.model === model
                    ? 'border-violet-400 bg-violet-50 text-violet-700 shadow-sm'
                    : 'border-zinc-200 bg-white text-zinc-600 hover:border-zinc-300 hover:bg-zinc-50'
                }`}
              >
                {MODEL_LABELS[model]}
              </button>
            ))}
          </div>
        </div>

        {/* 시스템 프롬프트 */}
        <div>
          <label className="mb-1.5 block text-[13px] font-semibold text-zinc-700">시스템 프롬프트</label>
          <div className="overflow-hidden rounded-2xl border border-zinc-300 bg-white transition-all focus-within:border-violet-400 focus-within:ring-2 focus-within:ring-violet-100">
            <textarea
              value={form.systemPrompt}
              onChange={(e) => onChange({ ...form, systemPrompt: e.target.value })}
              placeholder="에이전트의 역할, 행동 방식, 제약 사항 등을 정의하세요&#10;&#10;예: 당신은 전문 문서 분석 AI입니다..."
              rows={6}
              className="block w-full resize-none bg-transparent px-4 py-3.5 text-[14px] leading-relaxed text-zinc-900 placeholder-zinc-400 outline-none"
            />
          </div>
        </div>

        {/* 도구 연결 */}
        <div>
          <label className="mb-1.5 block text-[13px] font-semibold text-zinc-700">도구 연결</label>
          <div className="grid grid-cols-2 gap-2">
            {AVAILABLE_TOOLS.map((tool) => {
              const isSelected = form.tools.includes(tool.id);
              return (
                <button
                  key={tool.id}
                  onClick={() => onToolToggle(tool.id)}
                  className={`flex items-center gap-3 rounded-xl border px-4 py-3 text-left transition-all ${
                    isSelected
                      ? 'border-violet-300 bg-violet-50'
                      : 'border-zinc-200 bg-white hover:border-zinc-300 hover:bg-zinc-50'
                  }`}
                >
                  <div className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${isSelected ? 'bg-violet-100' : 'bg-zinc-100'}`}>
                    <svg className={`h-4 w-4 ${isSelected ? 'text-violet-600' : 'text-zinc-400'}`} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" d={tool.icon} />
                    </svg>
                  </div>
                  <span className={`text-[13px] font-medium ${isSelected ? 'text-violet-700' : 'text-zinc-600'}`}>{tool.label}</span>
                  {isSelected && (
                    <svg className="ml-auto h-4 w-4 text-violet-500" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
                    </svg>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* Temperature */}
        <div>
          <div className="mb-1.5 flex items-center justify-between">
            <label className="text-[13px] font-semibold text-zinc-700">Temperature</label>
            <span className="rounded-lg bg-zinc-100 px-2.5 py-1 text-[12.5px] font-semibold tabular-nums text-zinc-700">
              {form.temperature.toFixed(1)}
            </span>
          </div>
          <input
            type="range"
            min="0"
            max="1"
            step="0.1"
            value={form.temperature}
            onChange={(e) => onChange({ ...form, temperature: parseFloat(e.target.value) })}
            className="h-2 w-full cursor-pointer appearance-none rounded-full bg-zinc-200 accent-violet-600"
          />
          <div className="mt-1 flex justify-between text-[11px] text-zinc-400">
            <span>0.0 (정확)</span>
            <span>0.5 (균형)</span>
            <span>1.0 (창의적)</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AgentBuilderPage;
