// agent-eval-gate: 에이전트별 만족도 + 최근 부정 피드백 관리자 위젯.
import { useAgentEvalStats, useRecentNegativeFeedback } from '@/hooks/useMessageFeedback';
import type { AgentEvalStat } from '@/types/messageFeedback';

const pct = (s: number | null): string =>
  s === null ? '평가 없음' : `${Math.round(s * 100)}%`;

const StatRow = ({ stat }: { stat: AgentEvalStat }) => (
  <div className="flex items-center justify-between border-b border-zinc-100 py-2 last:border-0">
    <span className="font-medium text-zinc-800">{stat.agent_id}</span>
    <div className="flex items-center gap-3 text-sm text-zinc-500">
      <span>👍 {stat.up}</span>
      <span>👎 {stat.down}</span>
      <span
        className={`font-semibold ${
          stat.satisfaction === null
            ? 'text-zinc-400'
            : stat.satisfaction >= 0.7
              ? 'text-emerald-600'
              : 'text-rose-600'
        }`}
      >
        {pct(stat.satisfaction)}
      </span>
    </div>
  </div>
);

const AgentSatisfactionPanel = () => {
  const { data: stats = [], isLoading } = useAgentEvalStats();
  const { data: negatives = [] } = useRecentNegativeFeedback();

  return (
    <section className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
      <h2 className="mb-3 text-base font-semibold text-zinc-900">에이전트 만족도</h2>

      {isLoading ? (
        <p className="text-sm text-zinc-400">불러오는 중…</p>
      ) : stats.length === 0 ? (
        <p className="text-sm text-zinc-400">아직 평가가 없습니다.</p>
      ) : (
        <div className="mb-4">
          {stats.map((s) => (
            <StatRow key={s.agent_id} stat={s} />
          ))}
        </div>
      )}

      {negatives.length > 0 && (
        <div className="mt-2">
          <h3 className="mb-2 text-sm font-semibold text-zinc-700">최근 부정 피드백</h3>
          <ul className="space-y-1.5">
            {negatives.map((n) => (
              <li
                key={n.message_id}
                className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-800"
              >
                <span className="mr-2 text-xs text-rose-500">{n.agent_id}</span>
                {n.comment ?? '(코멘트 없음)'}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
};

export default AgentSatisfactionPanel;
