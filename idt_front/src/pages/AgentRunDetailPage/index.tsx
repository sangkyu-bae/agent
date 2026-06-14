import { useNavigate, useParams } from 'react-router-dom';
import { useAgentRunDetail } from '@/hooks/useAgentRunAdmin';
import StepTree from './components/StepTree';

function fmtCost(c: string | number): string {
  const v = typeof c === 'string' ? parseFloat(c) : c;
  if (Number.isNaN(v)) return '—';
  return `$${v.toFixed(4)}`;
}

function fmtLatency(ms: number | null): string {
  if (ms === null || ms === undefined) return '—';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

const STATUS_COLORS: Record<string, string> = {
  RUNNING: 'bg-sky-50 text-sky-600',
  SUCCESS: 'bg-emerald-50 text-emerald-600',
  FAILED: 'bg-red-50 text-red-600',
  CANCELLED: 'bg-zinc-100 text-zinc-500',
};

const AgentRunDetailPage = () => {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();
  const { data, isLoading, isError, error } = useAgentRunDetail(runId);

  if (isLoading) {
    return (
      <div className="p-6 text-sm text-zinc-400">Run 상세 로딩 중...</div>
    );
  }

  if (isError) {
    return (
      <div className="p-6">
        <button
          type="button"
          onClick={() => navigate(-1)}
          className="mb-3 text-sm text-violet-600 hover:underline"
        >
          ← 목록으로
        </button>
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          Run을 불러올 수 없습니다: {(error as Error)?.message ?? 'unknown'}
        </div>
      </div>
    );
  }

  if (!data) return null;

  const run = data.run;

  return (
    <div className="flex flex-col gap-4 p-6">
      <button
        type="button"
        onClick={() => navigate(-1)}
        className="self-start text-sm text-violet-600 hover:underline"
      >
        ← 목록으로
      </button>

      <header className="rounded-lg border border-zinc-200 bg-white p-4">
        <div className="flex items-center gap-3">
          <h1 className="font-mono text-sm text-zinc-700">Run {run.id}</h1>
          <span
            className={[
              'rounded-full px-2 py-0.5 text-xs font-medium',
              STATUS_COLORS[run.status] ?? 'bg-zinc-100 text-zinc-500',
            ].join(' ')}
          >
            {run.status}
          </span>
          {run.langsmith_run_url && (
            <a
              href={run.langsmith_run_url}
              target="_blank"
              rel="noreferrer"
              className="ml-auto text-xs text-violet-600 hover:underline"
            >
              🔗 LangSmith Trace
            </a>
          )}
        </div>

        <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 text-xs text-zinc-600 sm:grid-cols-4">
          <div>
            <dt className="text-zinc-400">User</dt>
            <dd className="font-mono">{run.user_id}</dd>
          </div>
          <div>
            <dt className="text-zinc-400">Agent</dt>
            <dd className="font-mono">{run.agent_id}</dd>
          </div>
          <div>
            <dt className="text-zinc-400">Started</dt>
            <dd>{new Date(run.started_at).toLocaleString('ko-KR')}</dd>
          </div>
          <div>
            <dt className="text-zinc-400">Duration</dt>
            <dd>{fmtLatency(run.latency_ms)}</dd>
          </div>
          <div>
            <dt className="text-zinc-400">Tokens</dt>
            <dd>{run.token_usage.total_tokens.toLocaleString('ko-KR')}</dd>
          </div>
          <div>
            <dt className="text-zinc-400">Cost</dt>
            <dd>{fmtCost(run.cost_usd.total_usd)}</dd>
          </div>
          <div>
            <dt className="text-zinc-400">LLM calls</dt>
            <dd>{run.llm_call_count}</dd>
          </div>
          <div>
            <dt className="text-zinc-400">Thread</dt>
            <dd className="truncate font-mono">{run.langgraph_thread_id}</dd>
          </div>
        </dl>

        {run.error_message && (
          <pre className="mt-3 max-h-32 overflow-auto rounded border border-red-200 bg-red-50 p-2 text-[11px] text-red-700">
            {run.error_message}
          </pre>
        )}
      </header>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-zinc-700">Steps</h2>
        <StepTree steps={data.steps} orphanLlmCalls={data.orphan_llm_calls} />
      </section>
    </div>
  );
};

export default AgentRunDetailPage;
