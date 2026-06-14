import type {
  LlmCallDto,
  RetrievalDto,
  StepDto,
  ToolCallDto,
} from '@/types/agentRunAdmin';

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
  STARTED: 'bg-sky-50 text-sky-600',
  SUCCESS: 'bg-emerald-50 text-emerald-600',
  FAILED: 'bg-red-50 text-red-600',
  RUNNING: 'bg-sky-50 text-sky-600',
};

const StatusBadge = ({ status }: { status: string }) => (
  <span
    className={[
      'rounded-full px-2 py-0.5 text-[10px] font-medium',
      STATUS_COLORS[status] ?? 'bg-zinc-100 text-zinc-500',
    ].join(' ')}
  >
    {status}
  </span>
);

const LlmCallItem = ({ llm }: { llm: LlmCallDto }) => (
  <li className="ml-6 flex items-center gap-2 border-l-2 border-emerald-200 pl-3 py-1 text-xs">
    <span className="text-emerald-600">⚡ LLM</span>
    <span className="font-mono">{llm.model_name}</span>
    {llm.purpose && <span className="text-zinc-400">({llm.purpose})</span>}
    <span className="ml-auto text-zinc-500">
      {llm.token_usage.total_tokens.toLocaleString('ko-KR')} tok ·{' '}
      {fmtCost(llm.cost_usd.total_usd)} · {fmtLatency(llm.latency_ms)}
    </span>
  </li>
);

const RetrievalItem = ({ r }: { r: RetrievalDto }) => (
  <li className="ml-12 border-l-2 border-amber-200 pl-3 py-0.5 text-[11px]">
    <div className="flex items-center gap-2">
      <span className="text-amber-600">📄</span>
      <span className="font-mono text-zinc-600">
        {r.collection_name}/{r.document_id ?? '?'}#{r.chunk_id ?? '?'}
      </span>
      {r.score !== null && (
        <span className="text-zinc-500">score {r.score.toFixed(3)}</span>
      )}
    </div>
    {r.content_preview && (
      <p className="mt-0.5 line-clamp-2 text-zinc-500">{r.content_preview}</p>
    )}
  </li>
);

const ToolCallItem = ({ tool }: { tool: ToolCallDto }) => (
  <li className="ml-6 border-l-2 border-violet-200 pl-3 py-1 text-xs">
    <div className="flex items-center gap-2">
      <span className="text-violet-600">🔧 {tool.tool_name}</span>
      <StatusBadge status={tool.status} />
      <span className="ml-auto text-zinc-500">{fmtLatency(tool.latency_ms)}</span>
    </div>
    {tool.result_summary && (
      <p className="mt-0.5 line-clamp-2 text-[11px] text-zinc-500">
        {tool.result_summary}
      </p>
    )}
    {(tool.retrievals.length > 0 || tool.llm_calls.length > 0) && (
      <ul className="mt-1 space-y-0.5">
        {tool.retrievals.map((r) => (
          <RetrievalItem key={r.id} r={r} />
        ))}
        {tool.llm_calls.map((llm) => (
          <LlmCallItem key={llm.id} llm={llm} />
        ))}
      </ul>
    )}
  </li>
);

const StepItem = ({ step }: { step: StepDto }) => (
  <li className="rounded-md border border-zinc-200 bg-white p-3">
    <div className="flex items-center gap-2 text-sm">
      <span className="font-mono text-zinc-500">#{step.step_index}</span>
      <span className="font-semibold text-zinc-800">{step.node_name}</span>
      <span className="text-[11px] text-zinc-400">[{step.node_type}]</span>
      <StatusBadge status={step.status} />
      <span className="ml-auto text-xs text-zinc-500">
        {fmtLatency(step.latency_ms)}
      </span>
    </div>
    {step.error_text && (
      <p className="mt-1 text-xs text-red-600">{step.error_text}</p>
    )}
    {(step.llm_calls.length > 0 || step.tool_calls.length > 0) && (
      <ul className="mt-2 space-y-1">
        {step.llm_calls.map((llm) => (
          <LlmCallItem key={llm.id} llm={llm} />
        ))}
        {step.tool_calls.map((tool) => (
          <ToolCallItem key={tool.id} tool={tool} />
        ))}
      </ul>
    )}
  </li>
);

interface Props {
  steps: StepDto[];
  orphanLlmCalls: LlmCallDto[];
}

const StepTree = ({ steps, orphanLlmCalls }: Props) => (
  <ul className="space-y-2">
    {steps.map((s) => (
      <StepItem key={s.id} step={s} />
    ))}
    {orphanLlmCalls.length > 0 && (
      <li className="rounded-md border border-dashed border-zinc-200 bg-zinc-50 p-3">
        <div className="mb-1 text-xs font-semibold text-zinc-500">
          orphan LLM calls (step 외)
        </div>
        <ul className="space-y-0.5">
          {orphanLlmCalls.map((llm) => (
            <LlmCallItem key={llm.id} llm={llm} />
          ))}
        </ul>
      </li>
    )}
  </ul>
);

export default StepTree;
