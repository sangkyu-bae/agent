// Design Ref: stock-analysis-agents §9.1 — 면책 띠 + 자동 분석 상태 칩 + 탭 8개.
// 권한은 GET /access 로만 판단한다(can_view 없으면 "권한이 없습니다"). 쓰기 버튼은 can_manage 일 때만.
// 다른 서비스로 떼어낼 때는 이 폴더 + marketAnalysis{Service,Mocks}·useMarketAnalysis·types 만 옮긴다.
import { useState } from 'react';
import { Info } from 'lucide-react';
import Tabs from '@/components/ui/Tabs';
import Badge from '@/components/ui/Badge';
import { useMarketAnalysisAccess, useMarketDashboard } from '@/hooks/useMarketAnalysis';
import {
  MARKET_ANALYSIS_DISCLAIMER,
  MARKET_ANALYSIS_TAB_LABELS,
  MARKET_ANALYSIS_TABS,
  type MarketAnalysisTab,
} from '@/types/marketAnalysis';
import { formatKst, marketAnalysisErrorMessage } from '@/utils/marketAnalysis';
import DashboardTab from './DashboardTab';
import PositionsTab from './PositionsTab';
import WatchlistTab from './WatchlistTab';
import ReportsTab from './ReportsTab';
import InsightsTab from './InsightsTab';
import RoundsTab from './RoundsTab';
import SettingsTab from './SettingsTab';

const SwitchChip = () => {
  const dashboard = useMarketDashboard();
  const sw = dashboard.data?.switch;
  if (!sw) return null;
  return sw.enabled ? (
    <Badge tone="success" dot>
      자동 분석 켜짐{sw.next_round ? ` · 다음 ${formatKst(sw.next_round)}` : ''}
    </Badge>
  ) : (
    <Badge tone="neutral" dot>
      자동 분석 꺼짐
    </Badge>
  );
};

const MarketAnalysisPage = () => {
  const access = useMarketAnalysisAccess();
  const [tab, setTab] = useState<MarketAnalysisTab>('dashboard');
  // 다른 탭에서 리포트 상세로 건너갈 때 쓴다 (포지션 상세·회차 상세 → 리포트)
  const [reportId, setReportId] = useState<number | null>(null);

  const openReport = (id: number) => {
    setReportId(id);
    setTab('reports');
  };

  if (access.isLoading) {
    return <p className="py-16 text-center text-sm text-fg-muted">불러오는 중…</p>;
  }
  if (access.isError) {
    return (
      <p role="alert" className="m-8 rounded-xl border border-danger-border bg-danger-bg px-4 py-3 text-sm text-danger">
        {marketAnalysisErrorMessage(access.error, '시장 분석 권한을 확인하지 못했습니다.')}
      </p>
    );
  }
  const data = access.data;
  if (!data?.enabled || !data.can_view) {
    return (
      <div className="mx-auto max-w-xl px-6 py-16 text-center">
        <p className="text-md font-medium text-fg">권한이 없습니다.</p>
        <p className="mt-2 text-sm text-fg-muted">
          {data && !data.enabled
            ? '시장 분석 기능이 꺼져 있습니다.'
            : '시장 분석을 보려면 관리자에게 보기 권한을 요청하세요.'}
        </p>
      </div>
    );
  }

  const canManage = data.can_manage;

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl px-6 py-8">
        <div className="mb-4">
          <h1 className="text-xl font-semibold text-fg">시장 분석</h1>
          <p className="mt-1 text-sm text-fg-muted">
            신호가 난 종목을 에이전트가 분석하고, 판단 결과를 가상 계좌에 기록합니다.
          </p>
        </div>

        <div
          role="note"
          className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-warning-border bg-warning-bg px-4 py-2.5"
        >
          <p className="flex items-center gap-2 text-sm text-warning">
            <Info className="h-4 w-4 shrink-0" strokeWidth={1.75} aria-hidden="true" />
            {MARKET_ANALYSIS_DISCLAIMER}
          </p>
          <SwitchChip />
        </div>

        <Tabs
          aria-label="시장 분석"
          items={MARKET_ANALYSIS_TABS.map((key) => ({
            key,
            label: MARKET_ANALYSIS_TAB_LABELS[key],
          }))}
          value={tab}
          onChange={(key) => setTab(key as MarketAnalysisTab)}
          className="mb-5"
        />

        {tab === 'dashboard' && <DashboardTab onOpenRounds={() => setTab('rounds')} />}
        {tab === 'positions' && <PositionsTab status="open" onOpenReport={openReport} />}
        {tab === 'history' && <PositionsTab status="closed" onOpenReport={openReport} />}
        {tab === 'watchlist' && <WatchlistTab onOpenReport={openReport} />}
        {tab === 'reports' && (
          <ReportsTab selectedId={reportId} onSelect={setReportId} />
        )}
        {tab === 'insights' && <InsightsTab canManage={canManage} />}
        {tab === 'rounds' && <RoundsTab canManage={canManage} onOpenReport={openReport} />}
        {tab === 'settings' && <SettingsTab canManage={canManage} />}
      </div>
    </div>
  );
};

export default MarketAnalysisPage;
