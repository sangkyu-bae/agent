import { useState } from 'react';
import type { AdminTool, ToolSchemaParam, ToolEndpoint, AdminToolFormData } from '@/types/toolAdmin';
import {
  TOOL_PARAM_TYPE,
  TOOL_PARAM_TYPE_LABEL,
  HTTP_METHOD,
} from '@/types/toolAdmin';

// ─── Mock Data ───────────────────────────────────────────────────────────────

let nextId = 10;
const genId = () => String(nextId++);
const now = () => new Date().toISOString();

const MOCK_ADMIN_TOOLS: AdminTool[] = [
  {
    id: '1',
    name: '웹 검색',
    description: '인터넷에서 최신 정보를 검색하여 에이전트에 제공합니다.',
    category: 'search',
    schemaParams: [
      { id: 'p1', name: 'query', type: 'string', description: '검색 키워드', required: true },
      { id: 'p2', name: 'max_results', type: 'number', description: '최대 결과 수', required: false },
    ],
    endpoints: [
      { id: 'e1', method: 'GET', path: '/api/tools/web-search', description: '웹 검색 실행' },
    ],
    enabled: true,
    createdAt: '2024-01-10T09:00:00Z',
    updatedAt: '2024-01-10T09:00:00Z',
  },
  {
    id: '2',
    name: '코드 실행',
    description: 'Python 코드를 안전한 샌드박스 환경에서 실행합니다.',
    category: 'execution',
    schemaParams: [
      { id: 'p3', name: 'code', type: 'string', description: '실행할 Python 코드', required: true },
      { id: 'p4', name: 'timeout', type: 'number', description: '실행 제한 시간 (초)', required: false },
    ],
    endpoints: [
      { id: 'e2', method: 'POST', path: '/api/tools/code-execution/run', description: '코드 실행 요청' },
      { id: 'e3', method: 'GET', path: '/api/tools/code-execution/result/{job_id}', description: '실행 결과 조회' },
    ],
    enabled: true,
    createdAt: '2024-01-12T10:00:00Z',
    updatedAt: '2024-02-01T14:30:00Z',
  },
  {
    id: '3',
    name: 'HTTP 요청',
    description: '외부 REST API에 GET/POST/PUT 등의 HTTP 요청을 전송합니다.',
    category: 'api',
    schemaParams: [
      { id: 'p5', name: 'url', type: 'string', description: '요청 대상 URL', required: true },
      { id: 'p6', name: 'method', type: 'string', description: 'HTTP 메서드 (GET, POST 등)', required: true },
      { id: 'p7', name: 'headers', type: 'object', description: '요청 헤더', required: false },
      { id: 'p8', name: 'body', type: 'object', description: '요청 본문 (JSON)', required: false },
    ],
    endpoints: [
      { id: 'e4', method: 'POST', path: '/api/tools/http-request', description: 'HTTP 요청 프록시 실행' },
    ],
    enabled: false,
    createdAt: '2024-01-15T11:00:00Z',
    updatedAt: '2024-01-15T11:00:00Z',
  },
];

// ─── Category constants ──────────────────────────────────────────────────────

const CATEGORIES = ['search', 'execution', 'api', 'data', 'custom'] as const;
const CATEGORY_LABEL: Record<string, string> = {
  search: '검색',
  execution: '실행',
  api: 'API',
  data: '데이터',
  custom: '커스텀',
};
const CATEGORY_STYLE: Record<string, { bg: string; text: string }> = {
  search: { bg: 'bg-sky-50', text: 'text-sky-600' },
  execution: { bg: 'bg-amber-50', text: 'text-amber-600' },
  api: { bg: 'bg-emerald-50', text: 'text-emerald-600' },
  data: { bg: 'bg-violet-50', text: 'text-violet-600' },
  custom: { bg: 'bg-zinc-100', text: 'text-zinc-600' },
};

const METHOD_STYLE: Record<string, string> = {
  GET: 'text-emerald-600 bg-emerald-50',
  POST: 'text-blue-600 bg-blue-50',
  PUT: 'text-amber-600 bg-amber-50',
  PATCH: 'text-violet-600 bg-violet-50',
  DELETE: 'text-red-500 bg-red-50',
};

// ─── Empty form data ─────────────────────────────────────────────────────────

const EMPTY_FORM: AdminToolFormData = {
  name: '',
  description: '',
  category: 'custom',
  schemaParams: [],
  endpoints: [],
};

// ─── Delete Confirm Modal ────────────────────────────────────────────────────

interface DeleteConfirmProps {
  toolName: string;
  onConfirm: () => void;
  onCancel: () => void;
}

const DeleteConfirm = ({ toolName, onConfirm, onCancel }: DeleteConfirmProps) => (
  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
    <div className="w-[360px] overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-2xl">
      <div className="p-6">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-red-50">
          <svg className="h-6 w-6 text-red-500" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
          </svg>
        </div>
        <h3 className="mt-4 text-[15px] font-semibold text-zinc-900">도구 삭제</h3>
        <p className="mt-1.5 text-[13.5px] leading-relaxed text-zinc-500">
          <span className="font-medium text-zinc-800">"{toolName}"</span>을(를) 삭제하시겠습니까?
          이 작업은 되돌릴 수 없습니다.
        </p>
      </div>
      <div className="flex gap-2 border-t border-zinc-100 p-4">
        <button
          onClick={onCancel}
          className="flex-1 rounded-xl border border-zinc-200 bg-zinc-50 py-2.5 text-[13.5px] font-medium text-zinc-600 hover:bg-zinc-100 transition-all"
        >
          취소
        </button>
        <button
          onClick={onConfirm}
          className="flex-1 rounded-xl bg-red-500 py-2.5 text-[13.5px] font-medium text-white hover:bg-red-600 active:scale-95 transition-all"
        >
          삭제
        </button>
      </div>
    </div>
  </div>
);

// ─── Tool Form Modal ─────────────────────────────────────────────────────────

interface ToolFormModalProps {
  mode: 'create' | 'edit';
  initialData: AdminToolFormData;
  onSave: (data: AdminToolFormData) => void;
  onClose: () => void;
}

const ToolFormModal = ({ mode, initialData, onSave, onClose }: ToolFormModalProps) => {
  const [form, setForm] = useState<AdminToolFormData>(initialData);

  const updateField = <K extends keyof AdminToolFormData>(key: K, value: AdminToolFormData[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  // Schema Params
  const addParam = () => {
    updateField('schemaParams', [
      ...form.schemaParams,
      { name: '', type: TOOL_PARAM_TYPE.string, description: '', required: false },
    ]);
  };
  const removeParam = (idx: number) => {
    updateField('schemaParams', form.schemaParams.filter((_, i) => i !== idx));
  };
  const updateParam = (idx: number, patch: Partial<Omit<ToolSchemaParam, 'id'>>) => {
    updateField(
      'schemaParams',
      form.schemaParams.map((p, i) => (i === idx ? { ...p, ...patch } : p)),
    );
  };

  // Endpoints
  const addEndpoint = () => {
    updateField('endpoints', [
      ...form.endpoints,
      { method: HTTP_METHOD.GET, path: '', description: '' },
    ]);
  };
  const removeEndpoint = (idx: number) => {
    updateField('endpoints', form.endpoints.filter((_, i) => i !== idx));
  };
  const updateEndpoint = (idx: number, patch: Partial<Omit<ToolEndpoint, 'id'>>) => {
    updateField(
      'endpoints',
      form.endpoints.map((e, i) => (i === idx ? { ...e, ...patch } : e)),
    );
  };

  const handleSubmit = () => {
    if (!form.name.trim() || !form.description.trim()) return;
    onSave(form);
  };

  const isValid = form.name.trim() !== '' && form.description.trim() !== '';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="flex h-full max-h-[720px] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-2xl">
        {/* 모달 헤더 */}
        <div className="flex shrink-0 items-center justify-between border-b border-zinc-100 px-6 py-4">
          <div>
            <h2 className="text-[15px] font-semibold text-zinc-900">
              {mode === 'create' ? '도구 추가' : '도구 수정'}
            </h2>
            <p className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">
              {mode === 'create' ? 'Add Tool' : 'Edit Tool'}
            </p>
          </div>
          <button
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-zinc-400 hover:bg-zinc-100 hover:text-zinc-600 transition-all"
          >
            <svg className="h-4.5 w-4.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* 모달 본문 (스크롤) */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">

          {/* 기본 정보 */}
          <section>
            <p className="mb-3 text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">
              기본 정보
            </p>
            <div className="space-y-3">
              <div>
                <label className="mb-1.5 block text-[12.5px] font-medium text-zinc-700">
                  도구 이름 <span className="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => updateField('name', e.target.value)}
                  placeholder="예: 웹 검색"
                  className="w-full rounded-xl border border-zinc-300 bg-white px-4 py-2.5 text-[13.5px] text-zinc-900 placeholder-zinc-400 outline-none transition-all focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-[12.5px] font-medium text-zinc-700">
                  설명 <span className="text-red-400">*</span>
                </label>
                <textarea
                  value={form.description}
                  onChange={(e) => updateField('description', e.target.value)}
                  placeholder="이 도구가 수행하는 기능을 설명합니다."
                  rows={2}
                  className="w-full resize-none rounded-xl border border-zinc-300 bg-white px-4 py-2.5 text-[13.5px] text-zinc-900 placeholder-zinc-400 outline-none transition-all focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-[12.5px] font-medium text-zinc-700">카테고리</label>
                <select
                  value={form.category}
                  onChange={(e) => updateField('category', e.target.value)}
                  className="w-full rounded-xl border border-zinc-300 bg-white px-4 py-2.5 text-[13.5px] text-zinc-900 outline-none transition-all focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
                >
                  {CATEGORIES.map((cat) => (
                    <option key={cat} value={cat}>{CATEGORY_LABEL[cat]}</option>
                  ))}
                </select>
              </div>
            </div>
          </section>

          {/* 스키마 파라미터 */}
          <section>
            <div className="mb-3 flex items-center justify-between">
              <p className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">
                스키마 파라미터
              </p>
              <button
                onClick={addParam}
                className="flex items-center gap-1.5 rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-[12px] font-medium text-zinc-600 hover:bg-zinc-100 transition-all"
              >
                <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                </svg>
                파라미터 추가
              </button>
            </div>
            {form.schemaParams.length === 0 ? (
              <div className="rounded-xl border border-dashed border-zinc-200 bg-zinc-50 py-6 text-center">
                <p className="text-[12.5px] text-zinc-400">파라미터가 없습니다. 추가 버튼을 눌러 파라미터를 정의하세요.</p>
              </div>
            ) : (
              <div className="space-y-2.5">
                {form.schemaParams.map((param, idx) => (
                  <div key={idx} className="rounded-xl border border-zinc-200 bg-zinc-50/50 p-3.5">
                    <div className="flex items-start gap-2.5">
                      {/* 파라미터 이름 */}
                      <input
                        type="text"
                        value={param.name}
                        onChange={(e) => updateParam(idx, { name: e.target.value })}
                        placeholder="파라미터명"
                        className="w-32 shrink-0 rounded-lg border border-zinc-300 bg-white px-3 py-2 text-[12.5px] font-mono text-zinc-900 placeholder-zinc-400 outline-none focus:border-violet-400"
                      />
                      {/* 타입 */}
                      <select
                        value={param.type}
                        onChange={(e) => updateParam(idx, { type: e.target.value as ToolSchemaParam['type'] })}
                        className="w-28 shrink-0 rounded-lg border border-zinc-300 bg-white px-3 py-2 text-[12.5px] text-zinc-700 outline-none focus:border-violet-400"
                      >
                        {Object.values(TOOL_PARAM_TYPE).map((t) => (
                          <option key={t} value={t}>{TOOL_PARAM_TYPE_LABEL[t]}</option>
                        ))}
                      </select>
                      {/* 설명 */}
                      <input
                        type="text"
                        value={param.description}
                        onChange={(e) => updateParam(idx, { description: e.target.value })}
                        placeholder="파라미터 설명"
                        className="min-w-0 flex-1 rounded-lg border border-zinc-300 bg-white px-3 py-2 text-[12.5px] text-zinc-900 placeholder-zinc-400 outline-none focus:border-violet-400"
                      />
                      {/* 필수 여부 */}
                      <label className="flex shrink-0 cursor-pointer items-center gap-1.5 px-1">
                        <input
                          type="checkbox"
                          checked={param.required}
                          onChange={(e) => updateParam(idx, { required: e.target.checked })}
                          className="h-4 w-4 accent-violet-600"
                        />
                        <span className="text-[12px] text-zinc-500">필수</span>
                      </label>
                      {/* 삭제 */}
                      <button
                        onClick={() => removeParam(idx)}
                        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-zinc-400 hover:bg-red-50 hover:text-red-500 transition-all"
                      >
                        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                        </svg>
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* 엔드포인트 */}
          <section>
            <div className="mb-3 flex items-center justify-between">
              <p className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">
                엔드포인트
              </p>
              <button
                onClick={addEndpoint}
                className="flex items-center gap-1.5 rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-[12px] font-medium text-zinc-600 hover:bg-zinc-100 transition-all"
              >
                <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                </svg>
                엔드포인트 추가
              </button>
            </div>
            {form.endpoints.length === 0 ? (
              <div className="rounded-xl border border-dashed border-zinc-200 bg-zinc-50 py-6 text-center">
                <p className="text-[12.5px] text-zinc-400">엔드포인트가 없습니다. 추가 버튼을 눌러 API 경로를 정의하세요.</p>
              </div>
            ) : (
              <div className="space-y-2.5">
                {form.endpoints.map((ep, idx) => (
                  <div key={idx} className="rounded-xl border border-zinc-200 bg-zinc-50/50 p-3.5">
                    <div className="flex items-start gap-2.5">
                      {/* HTTP 메서드 */}
                      <select
                        value={ep.method}
                        onChange={(e) => updateEndpoint(idx, { method: e.target.value as ToolEndpoint['method'] })}
                        className="w-24 shrink-0 rounded-lg border border-zinc-300 bg-white px-3 py-2 text-[12.5px] font-semibold text-zinc-800 outline-none focus:border-violet-400"
                      >
                        {Object.values(HTTP_METHOD).map((m) => (
                          <option key={m} value={m}>{m}</option>
                        ))}
                      </select>
                      {/* 경로 */}
                      <input
                        type="text"
                        value={ep.path}
                        onChange={(e) => updateEndpoint(idx, { path: e.target.value })}
                        placeholder="/api/tools/example"
                        className="w-56 shrink-0 rounded-lg border border-zinc-300 bg-white px-3 py-2 text-[12.5px] font-mono text-zinc-900 placeholder-zinc-400 outline-none focus:border-violet-400"
                      />
                      {/* 설명 */}
                      <input
                        type="text"
                        value={ep.description}
                        onChange={(e) => updateEndpoint(idx, { description: e.target.value })}
                        placeholder="엔드포인트 설명"
                        className="min-w-0 flex-1 rounded-lg border border-zinc-300 bg-white px-3 py-2 text-[12.5px] text-zinc-900 placeholder-zinc-400 outline-none focus:border-violet-400"
                      />
                      {/* 삭제 */}
                      <button
                        onClick={() => removeEndpoint(idx)}
                        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-zinc-400 hover:bg-red-50 hover:text-red-500 transition-all"
                      >
                        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                        </svg>
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>

        {/* 모달 푸터 */}
        <div className="flex shrink-0 gap-2 border-t border-zinc-100 px-6 py-4">
          <button
            onClick={onClose}
            className="flex-1 rounded-xl border border-zinc-200 bg-zinc-50 py-2.5 text-[13.5px] font-medium text-zinc-600 hover:bg-zinc-100 transition-all"
          >
            취소
          </button>
          <button
            onClick={handleSubmit}
            disabled={!isValid}
            className="flex-1 rounded-xl bg-violet-600 py-2.5 text-[13.5px] font-medium text-white shadow-sm hover:bg-violet-700 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40 transition-all"
          >
            {mode === 'create' ? '도구 추가' : '변경 저장'}
          </button>
        </div>
      </div>
    </div>
  );
};

// ─── Tool Row ────────────────────────────────────────────────────────────────

interface ToolRowProps {
  tool: AdminTool;
  onEdit: (tool: AdminTool) => void;
  onDelete: (tool: AdminTool) => void;
}

const ToolRow = ({ tool, onEdit, onDelete }: ToolRowProps) => {
  const catStyle = CATEGORY_STYLE[tool.category] ?? CATEGORY_STYLE.custom;
  const catLabel = CATEGORY_LABEL[tool.category] ?? tool.category;

  return (
    <tr className="group border-b border-zinc-100 transition-colors hover:bg-zinc-50/60">
      {/* 이름 + 설명 */}
      <td className="py-4 pl-6 pr-4">
        <div className="flex items-center gap-3">
          <div
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl shadow-sm"
            style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' }}
          >
            <svg className="h-4.5 w-4.5 text-white" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M11.42 15.17 17.25 21A2.652 2.652 0 0 0 21 17.25l-5.877-5.877M11.42 15.17l2.496-3.03c.317-.384.74-.626 1.208-.766M11.42 15.17l-4.655 5.653a2.548 2.548 0 1 1-3.586-3.586l6.837-5.63m5.108-.233c.55-.164 1.163-.188 1.743-.14a4.5 4.5 0 0 0 4.486-6.336l-3.276 3.277a3.004 3.004 0 0 1-2.25-2.25l3.276-3.276a4.5 4.5 0 0 0-6.336 4.486c.091 1.076-.071 2.264-.904 2.95l-.102.085m-1.745 1.437L5.909 7.5H4.5L2.25 3.75l1.5-1.5L7.5 4.5v1.409l4.26 4.26m-1.745 1.437 1.745-1.437m6.615 8.206L15.75 15.75M4.867 19.125h.008v.008h-.008v-.008Z" />
            </svg>
          </div>
          <div>
            <p className="text-[13.5px] font-semibold text-zinc-900">{tool.name}</p>
            <p className="mt-0.5 max-w-xs text-[12px] leading-tight text-zinc-400">{tool.description}</p>
          </div>
        </div>
      </td>

      {/* 카테고리 */}
      <td className="px-4 py-4">
        <span className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${catStyle.bg} ${catStyle.text}`}>
          {catLabel}
        </span>
      </td>

      {/* 스키마 파라미터 */}
      <td className="px-4 py-4">
        <div className="flex flex-wrap gap-1">
          {tool.schemaParams.length === 0 ? (
            <span className="text-[12px] text-zinc-300">—</span>
          ) : (
            tool.schemaParams.slice(0, 3).map((p) => (
              <span
                key={p.id}
                className="inline-flex items-center gap-1 rounded-lg bg-zinc-100 px-2 py-0.5 text-[11.5px] font-mono text-zinc-600"
              >
                {p.name}
                {p.required && <span className="text-red-400">*</span>}
              </span>
            ))
          )}
          {tool.schemaParams.length > 3 && (
            <span className="rounded-lg bg-zinc-100 px-2 py-0.5 text-[11.5px] text-zinc-400">
              +{tool.schemaParams.length - 3}
            </span>
          )}
        </div>
        <p className="mt-1 text-[11px] text-zinc-400">{tool.schemaParams.length}개 파라미터</p>
      </td>

      {/* 엔드포인트 */}
      <td className="px-4 py-4">
        <div className="flex flex-col gap-1">
          {tool.endpoints.length === 0 ? (
            <span className="text-[12px] text-zinc-300">—</span>
          ) : (
            tool.endpoints.slice(0, 2).map((ep) => (
              <div key={ep.id} className="flex items-center gap-1.5">
                <span className={`rounded px-1.5 py-0.5 text-[10.5px] font-bold ${METHOD_STYLE[ep.method] ?? 'text-zinc-600 bg-zinc-100'}`}>
                  {ep.method}
                </span>
                <span className="max-w-[140px] truncate font-mono text-[11px] text-zinc-500">{ep.path}</span>
              </div>
            ))
          )}
          {tool.endpoints.length > 2 && (
            <span className="text-[11px] text-zinc-400">+{tool.endpoints.length - 2}개 더</span>
          )}
        </div>
      </td>

      {/* 상태 */}
      <td className="px-4 py-4">
        {tool.enabled ? (
          <span className="flex items-center gap-1.5 text-[12px] font-medium text-emerald-600">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
            활성
          </span>
        ) : (
          <span className="flex items-center gap-1.5 text-[12px] font-medium text-zinc-400">
            <span className="h-1.5 w-1.5 rounded-full bg-zinc-300" />
            비활성
          </span>
        )}
      </td>

      {/* 액션 */}
      <td className="py-4 pl-4 pr-6">
        <div className="flex items-center justify-end gap-1.5 opacity-0 transition-opacity group-hover:opacity-100">
          <button
            onClick={() => onEdit(tool)}
            className="flex items-center gap-1.5 rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-[12px] font-medium text-zinc-600 hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 transition-all"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125" />
            </svg>
            수정
          </button>
          <button
            onClick={() => onDelete(tool)}
            className="flex items-center gap-1.5 rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-[12px] font-medium text-zinc-500 hover:border-red-200 hover:bg-red-50 hover:text-red-500 transition-all"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
            </svg>
            삭제
          </button>
        </div>
      </td>
    </tr>
  );
};

// ─── Page ────────────────────────────────────────────────────────────────────

type ModalState =
  | { type: 'none' }
  | { type: 'create' }
  | { type: 'edit'; tool: AdminTool }
  | { type: 'delete'; tool: AdminTool };

const ToolAdminPage = () => {
  const [tools, setTools] = useState<AdminTool[]>(MOCK_ADMIN_TOOLS);
  const [modal, setModal] = useState<ModalState>({ type: 'none' });
  const [search, setSearch] = useState('');

  const filtered = search.trim()
    ? tools.filter(
        (t) =>
          t.name.toLowerCase().includes(search.toLowerCase()) ||
          t.description.toLowerCase().includes(search.toLowerCase()),
      )
    : tools;

  const handleCreate = (data: AdminToolFormData) => {
    const newTool: AdminTool = {
      id: genId(),
      ...data,
      schemaParams: data.schemaParams.map((p) => ({ ...p, id: genId() })),
      endpoints: data.endpoints.map((e) => ({ ...e, id: genId() })),
      enabled: true,
      createdAt: now(),
      updatedAt: now(),
    };
    setTools((prev) => [newTool, ...prev]);
    setModal({ type: 'none' });
  };

  const handleUpdate = (toolId: string, data: AdminToolFormData) => {
    setTools((prev) =>
      prev.map((t) =>
        t.id === toolId
          ? {
              ...t,
              ...data,
              schemaParams: data.schemaParams.map((p, i) => ({
                ...p,
                id: t.schemaParams[i]?.id ?? genId(),
              })),
              endpoints: data.endpoints.map((e, i) => ({
                ...e,
                id: t.endpoints[i]?.id ?? genId(),
              })),
              updatedAt: now(),
            }
          : t,
      ),
    );
    setModal({ type: 'none' });
  };

  const handleDelete = (toolId: string) => {
    setTools((prev) => prev.filter((t) => t.id !== toolId));
    setModal({ type: 'none' });
  };

  const getEditInitialData = (tool: AdminTool): AdminToolFormData => ({
    name: tool.name,
    description: tool.description,
    category: tool.category,
    schemaParams: tool.schemaParams.map(({ id: _id, ...rest }) => rest),
    endpoints: tool.endpoints.map(({ id: _id, ...rest }) => rest),
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden', background: '#fff' }}>
        {/* 헤더 */}
        <header className="flex shrink-0 items-center justify-between border-b border-zinc-200 bg-white px-6 py-4">
          <div className="flex items-center gap-3">
            <div
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl shadow-md"
              style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' }}
            >
              <svg className="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 0 1 0 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28Z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
              </svg>
            </div>
            <div>
              <h1 className="text-[15px] font-semibold text-zinc-900">도구 관리</h1>
              <p className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">
                Tool Administration
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* 검색 */}
            <div className="flex items-center gap-2 rounded-xl border border-zinc-200 bg-zinc-50 px-3.5 py-2 transition-all focus-within:border-violet-300 focus-within:bg-white">
              <svg className="h-4 w-4 text-zinc-400" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
              </svg>
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="도구 검색..."
                className="w-44 bg-transparent text-[13px] text-zinc-800 placeholder-zinc-400 outline-none"
              />
            </div>

            {/* 통계 */}
            <div className="flex items-center gap-2 rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2">
              <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
              <span className="text-[13px] font-medium text-zinc-700">
                {tools.filter((t) => t.enabled).length}개 활성
              </span>
              <span className="text-[12px] text-zinc-400">/ {tools.length}개</span>
            </div>

            {/* 추가 버튼 */}
            <button
              onClick={() => setModal({ type: 'create' })}
              className="flex items-center gap-2 rounded-xl bg-violet-600 px-4 py-2.5 text-[13.5px] font-medium text-white shadow-sm hover:bg-violet-700 active:scale-95 transition-all"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
              </svg>
              도구 추가
            </button>
          </div>
        </header>

        {/* 콘텐츠 */}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          <div style={{ maxWidth: '1100px', margin: '0 auto', padding: '1.5rem' }}>
            {filtered.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-20 text-center">
                <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-zinc-100">
                  <svg className="h-8 w-8 text-zinc-400" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
                  </svg>
                </div>
                <p className="mt-4 text-[14px] font-medium text-zinc-500">
                  {search ? `"${search}"에 대한 검색 결과가 없습니다.` : '등록된 도구가 없습니다.'}
                </p>
                {!search && (
                  <button
                    onClick={() => setModal({ type: 'create' })}
                    className="mt-4 rounded-xl bg-violet-600 px-5 py-2.5 text-[13.5px] font-medium text-white hover:bg-violet-700 transition-all"
                  >
                    첫 번째 도구 추가
                  </button>
                )}
              </div>
            ) : (
              <div className="overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-zinc-100 bg-zinc-50">
                      <th className="py-3.5 pl-6 pr-4 text-left text-[11.5px] font-semibold uppercase tracking-widest text-zinc-400">
                        도구
                      </th>
                      <th className="px-4 py-3.5 text-left text-[11.5px] font-semibold uppercase tracking-widest text-zinc-400">
                        카테고리
                      </th>
                      <th className="px-4 py-3.5 text-left text-[11.5px] font-semibold uppercase tracking-widest text-zinc-400">
                        스키마 파라미터
                      </th>
                      <th className="px-4 py-3.5 text-left text-[11.5px] font-semibold uppercase tracking-widest text-zinc-400">
                        엔드포인트
                      </th>
                      <th className="px-4 py-3.5 text-left text-[11.5px] font-semibold uppercase tracking-widest text-zinc-400">
                        상태
                      </th>
                      <th className="py-3.5 pl-4 pr-6 text-right text-[11.5px] font-semibold uppercase tracking-widest text-zinc-400">
                        액션
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((tool) => (
                      <ToolRow
                        key={tool.id}
                        tool={tool}
                        onEdit={(t) => setModal({ type: 'edit', tool: t })}
                        onDelete={(t) => setModal({ type: 'delete', tool: t })}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

      {/* 모달 */}
      {modal.type === 'create' && (
        <ToolFormModal
          mode="create"
          initialData={EMPTY_FORM}
          onSave={handleCreate}
          onClose={() => setModal({ type: 'none' })}
        />
      )}
      {modal.type === 'edit' && (
        <ToolFormModal
          mode="edit"
          initialData={getEditInitialData(modal.tool)}
          onSave={(data) => handleUpdate(modal.tool.id, data)}
          onClose={() => setModal({ type: 'none' })}
        />
      )}
      {modal.type === 'delete' && (
        <DeleteConfirm
          toolName={modal.tool.name}
          onConfirm={() => handleDelete(modal.tool.id)}
          onCancel={() => setModal({ type: 'none' })}
        />
      )}
    </div>
  );
};

export default ToolAdminPage;
