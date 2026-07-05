import type { AgentBuilderFormData } from '@/types/agentBuilder';

interface StudioHeaderProps {
  mode: 'create' | 'edit';
  form: AgentBuilderFormData;
  onChange: (form: AgentBuilderFormData) => void;
  onSave: () => void;
  onCancel: () => void;
  isSaving: boolean;
}

const DISABLED_ICONS: { key: string; title: string; path: string }[] = [
  { key: 'code', title: '준비중', path: 'm6.75 7.5 3 2.25-3 2.25m4.5 0h3m-9 8.25h13.5A2.25 2.25 0 0 0 21 18V6a2.25 2.25 0 0 0-2.25-2.25H5.25A2.25 2.25 0 0 0 3 6v12a2.25 2.25 0 0 0 2.25 2.25Z' },
  { key: 'copy', title: '준비중', path: 'M15.75 17.25v3.375c0 .621-.504 1.125-1.125 1.125h-9.75a1.125 1.125 0 0 1-1.125-1.125V7.875c0-.621.504-1.125 1.125-1.125H6.75a9.06 9.06 0 0 1 1.5.124m7.5 10.376h3.375c.621 0 1.125-.504 1.125-1.125V11.25c0-4.46-3.243-8.161-7.5-8.876a9.06 9.06 0 0 0-1.5-.124H9.375c-.621 0-1.125.504-1.125 1.125v3.5m7.5 10.375H9.375a1.125 1.125 0 0 1-1.125-1.125v-9.25m12 6.625v-1.875a3.375 3.375 0 0 0-3.375-3.375h-1.5a1.125 1.125 0 0 1-1.125-1.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H9.75' },
  { key: 'delete', title: '준비중', path: 'm14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165' },
  { key: 'refresh', title: '준비중', path: 'M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99' },
];

/**
 * Studio 상단 헤더 — 에이전트명/설명(인라인 편집), 비활성 액션 아이콘,
 * 버전 셀렉터(표시용 비활성), 저장/취소.
 * agent-builder-studio-ui Design §5.1.
 */
const StudioHeader = ({ mode, form, onChange, onSave, onCancel, isSaving }: StudioHeaderProps) => {
  return (
    <header className="flex shrink-0 items-center justify-between gap-4 border-b border-zinc-200 bg-white px-5 py-3">
      <div className="flex min-w-0 items-center gap-3">
        <button
          type="button"
          onClick={onCancel}
          aria-label="뒤로"
          className="shrink-0 rounded-lg p-1.5 text-zinc-400 transition-colors hover:bg-zinc-100 hover:text-zinc-700"
        >
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5 3 12m0 0 7.5-7.5M3 12h18" />
          </svg>
        </button>
        <div className="min-w-0">
          <input
            type="text"
            value={form.name}
            onChange={(e) => onChange({ ...form, name: e.target.value })}
            placeholder="새 에이전트"
            aria-label="에이전트 이름"
            className="w-full truncate border-0 bg-transparent text-[16px] font-semibold text-zinc-900 placeholder-zinc-400 outline-none"
          />
          <input
            type="text"
            value={form.description}
            onChange={(e) => onChange({ ...form, description: e.target.value })}
            placeholder="에이전트 설명을 입력하세요"
            aria-label="에이전트 설명"
            className="w-full truncate border-0 bg-transparent text-[12.5px] text-zinc-400 placeholder-zinc-300 outline-none"
          />
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-2">
        {DISABLED_ICONS.map((ic) => (
          <button
            key={ic.key}
            type="button"
            disabled
            title={ic.title}
            className="cursor-not-allowed rounded-lg p-1.5 text-zinc-300"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.6} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d={ic.path} />
            </svg>
          </button>
        ))}

        {/* 버전 셀렉터 (표시용 비활성) */}
        <button
          type="button"
          disabled
          title="준비중"
          className="flex cursor-not-allowed items-center gap-1.5 rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-[12.5px] font-medium text-zinc-400"
        >
          현재 버전: <span className="rounded bg-zinc-200 px-1.5 py-0.5 text-zinc-600">v0</span>
        </button>

        <button
          type="button"
          onClick={onSave}
          disabled={!form.name.trim() || isSaving}
          className="flex items-center gap-2 rounded-xl bg-zinc-900 px-5 py-2 text-[13px] font-medium text-white shadow-sm transition-all hover:bg-zinc-800 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {isSaving && (
            <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          )}
          {isSaving ? '저장 중...' : '저장'}
        </button>
      </div>
    </header>
  );
};

export default StudioHeader;
