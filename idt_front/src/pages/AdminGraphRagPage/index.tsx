// Design Ref: graph-rag-foundation §5.1 — /admin/graph-rag (docs-quality 그룹)
// 헤더(노출 단계·Neo4j 상태) + 탭 6개(설정·추출·엔티티·주제·검색 테스트·검토 큐).
import { useState } from 'react';
import { useGraphRagHealth, useGraphRagSettings, useGraphReview } from '@/hooks/useGraphRag';
import {
  GRAPH_RAG_STAGES,
  GRAPH_RAG_STAGE_LABELS,
  GRAPH_RAG_TABS,
  type GraphHealthResponse,
  type GraphRagStage,
  type GraphRagTabKey,
} from '@/types/graphRag';
import GraphRagEntitiesTab from './GraphRagEntitiesTab';
import GraphRagExtractionTab from './GraphRagExtractionTab';
import GraphRagReviewTab from './GraphRagReviewTab';
import GraphRagSearchTestTab from './GraphRagSearchTestTab';
import GraphRagSettingsTab from './GraphRagSettingsTab';
import GraphRagTopicsTab from './GraphRagTopicsTab';
import StageChangeDialog from './StageChangeDialog';

const fmt = (n: number | null) => (n == null ? '-' : n.toLocaleString('ko-KR'));

const HealthBadge = ({ health }: { health?: GraphHealthResponse }) => {
  if (!health) return <span className="text-[12.5px] text-zinc-400">Neo4j 확인 중…</span>;
  return (
    <div className="text-right text-[12.5px]">
      <p className={health.connected ? 'text-emerald-600' : 'text-red-600'}>
        Neo4j ● {health.connected ? '연결됨' : '연결 안 됨'}
        {health.connected && (
          <span className="ml-2 text-zinc-500">
            노드 {fmt(health.node_count)} / {fmt(health.node_limit)} · 관계{' '}
            {fmt(health.relationship_count)} / {fmt(health.relationship_limit)}
          </span>
        )}
      </p>
      {!health.connected && health.error && (
        <p className="mt-0.5 text-zinc-500">사유: {health.error}</p>
      )}
      {health.external && (
        <p className="mt-0.5 text-amber-600">외부 클라우드 저장(Aura) — 개인정보 문서 금지</p>
      )}
    </div>
  );
};

const AdminGraphRagPage = () => {
  const [tab, setTab] = useState<GraphRagTabKey>('settings');
  const [targetStage, setTargetStage] = useState<GraphRagStage | null>(null);
  const { data: settings } = useGraphRagSettings();
  const { data: health } = useGraphRagHealth();
  const stage = settings?.rollout_stage;
  const stageOff = stage === 'off';
  const { data: review } = useGraphReview(!!stage && !stageOff);
  const backendReady = health?.connected ?? false;
  const activeTab: GraphRagTabKey = stageOff ? 'settings' : tab;
  const pending = review?.total ?? 0;

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">Admin</p>
          <h1 className="text-3xl font-bold tracking-tight text-zinc-900">그래프 RAG (테스트)</h1>
          <p className="mt-1 text-[13px] text-zinc-400">
            문서에서 용어·관계를 뽑아 그래프로 저장하고, 기존 검색에 근거를 보태는 모듈입니다.
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          {stage && (
            <label className="flex items-center gap-2 text-[13px] text-zinc-600">
              노출 단계
              <select
                aria-label="노출 단계"
                value={stage}
                onChange={(e) => setTargetStage(e.target.value as GraphRagStage)}
                className="rounded-lg border border-zinc-300 bg-white px-2 py-1 text-[13px]"
              >
                {GRAPH_RAG_STAGES.map((s) => (
                  <option key={s} value={s}>
                    {GRAPH_RAG_STAGE_LABELS[s]}
                  </option>
                ))}
              </select>
            </label>
          )}
          <HealthBadge health={health} />
        </div>
      </div>

      {stageOff && (
        <p className="mb-4 rounded-lg bg-zinc-100 px-4 py-3 text-[13px] text-zinc-600">
          노출 단계가 꺼져 있어 설정 외 기능은 쓸 수 없습니다. 단계를 “관리자 테스트”로 바꾸면
          추출·검색 테스트를 할 수 있습니다.
        </p>
      )}

      <div role="tablist" aria-label="그래프 RAG 탭" className="mb-5 flex flex-wrap gap-1 border-b border-zinc-200">
        {GRAPH_RAG_TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            type="button"
            aria-selected={activeTab === t.key}
            disabled={stageOff && t.key !== 'settings'}
            onClick={() => setTab(t.key)}
            className={`-mb-px border-b-2 px-4 py-2 text-[14px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
              activeTab === t.key
                ? 'border-violet-600 text-violet-700'
                : 'border-transparent text-zinc-500 hover:text-zinc-800'
            }`}
          >
            {t.label}
            {t.key === 'review' && pending > 0 && (
              <span
                aria-label={`검토 대기 ${pending}건`}
                className="ml-1.5 rounded-full bg-violet-600 px-1.5 py-0.5 text-[11px] text-white"
              >
                {pending}
              </span>
            )}
          </button>
        ))}
      </div>

      <div role="tabpanel">
        {activeTab === 'settings' && <GraphRagSettingsTab />}
        {activeTab === 'extraction' && <GraphRagExtractionTab backendReady={backendReady} />}
        {activeTab === 'entities' && <GraphRagEntitiesTab entityTypes={settings?.entity_types ?? []} />}
        {activeTab === 'topics' && <GraphRagTopicsTab />}
        {activeTab === 'search' && <GraphRagSearchTestTab backendReady={backendReady} />}
        {activeTab === 'review' && <GraphRagReviewTab />}
      </div>

      {targetStage && stage && targetStage !== stage && (
        <StageChangeDialog
          current={stage}
          target={targetStage}
          onClose={() => setTargetStage(null)}
        />
      )}
    </div>
  );
};

export default AdminGraphRagPage;
