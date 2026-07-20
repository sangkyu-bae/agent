import { Card } from '@/pages/AdminAgentRunsPage/components/SummaryCards';
import type { DashboardStats } from '@/types/adminDashboard';

interface Props {
  stats: DashboardStats | undefined;
  loading?: boolean;
}

function fmt(n: number | undefined): string {
  if (n === undefined || n === null) return '—';
  return n.toLocaleString('ko-KR');
}

/** 적재/사용자 누적 KPI 4종 — MySQL 메타 기준 (기간 무관, D1) */
const StatCardsRow = ({ stats, loading }: Props) => {
  if (loading) {
    return (
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="h-24 animate-pulse rounded-lg border border-zinc-100 bg-zinc-50"
          />
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <Card
        label="지식 베이스"
        value={fmt(stats?.kb.total)}
        hint={stats ? `활성 ${fmt(stats.kb.active)}` : undefined}
        accent="violet"
      />
      <Card
        label="적재 문서"
        value={fmt(stats?.documents.total)}
        hint={
          stats
            ? `KB 소속 ${fmt(stats.documents.with_kb)} · 일반 ${fmt(stats.documents.without_kb)}`
            : undefined
        }
        accent="sky"
      />
      <Card
        label="총 청크 (메타 기준)"
        value={fmt(stats?.chunks.total)}
        hint="document_metadata 집계 — 저장소 실측 아님"
        accent="emerald"
      />
      <Card
        label="사용자"
        value={fmt(stats?.users.total)}
        hint={
          stats
            ? `승인 ${fmt(stats.users.approved)} · 대기 ${fmt(stats.users.pending)}`
            : undefined
        }
        accent="amber"
      />
    </div>
  );
};

export default StatCardsRow;
