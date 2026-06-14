/**
 * AgentRunProgress — Agent 실행 실시간 진행률 표시 컴포넌트.
 *
 * Drop-in: 어디서든 `runId/agentId/query`만 주면 동작.
 * 기존 SSE 기반 흐름과 무관 — WebSocket 전송로(/ws/agent/{run_id}) 사용.
 *
 * Design fe-websocket-integration-guide §5.4.
 */
import { useAgentRunStream } from '@/hooks/useAgentRunStream';

export interface AgentRunProgressProps {
  runId: string;
  agentId: string;
  query: string;
  sessionId?: string;
}

const AgentRunProgress = ({ runId, agentId, query, sessionId }: AgentRunProgressProps) => {
  const { status, steps, tokens, answer, error, isDone } = useAgentRunStream({
    runId,
    agentId,
    query,
    sessionId,
  });

  return (
    <div className="rounded-lg border border-zinc-200 p-4 space-y-3 text-sm">
      <div className="flex items-center gap-2">
        <span
          className={
            status === 'connected'
              ? 'inline-block h-2 w-2 rounded-full bg-emerald-500'
              : status === 'connecting'
                ? 'inline-block h-2 w-2 rounded-full bg-amber-500 animate-pulse'
                : 'inline-block h-2 w-2 rounded-full bg-zinc-400'
          }
        />
        <span className="text-zinc-500">WS: {status}</span>
        {isDone && <span className="ml-auto text-zinc-500">완료</span>}
      </div>

      {steps.length > 0 && (
        <ol className="space-y-1">
          {steps.map((s, i) => (
            <li key={i} className="flex items-center gap-2">
              <span className="text-zinc-400 w-12">{s.kind}</span>
              <span className="font-mono">{s.name}</span>
              {s.durationMs !== undefined && (
                <span className="text-xs text-zinc-400">{s.durationMs}ms</span>
              )}
            </li>
          ))}
        </ol>
      )}

      {tokens && (
        <pre className="whitespace-pre-wrap rounded bg-zinc-50 p-2 text-zinc-700">
          {tokens}
        </pre>
      )}

      {answer && (
        <div className="rounded bg-emerald-50 p-3 text-emerald-900">
          <div className="mb-1 text-xs font-semibold text-emerald-700">최종 답변</div>
          {answer}
        </div>
      )}

      {error && (
        <div className="rounded bg-rose-50 p-3 text-rose-900">
          <div className="mb-1 text-xs font-semibold text-rose-700">{error.code}</div>
          {error.message}
        </div>
      )}
    </div>
  );
};

export default AgentRunProgress;
