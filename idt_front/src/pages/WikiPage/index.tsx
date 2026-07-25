// LLM-WIKI-001: 위키 관리 페이지 (정제 실행 + 거버넌스 목록).
import { useState } from 'react';

import Dropdown from '@/components/common/Dropdown';
import { useAgentList } from '@/hooks/useAgentStore';
import { useCollections } from '@/hooks/useRagToolConfig';
import { useDistillWiki } from '@/hooks/useWiki';
import { useAuthStore } from '@/store/authStore';
import { WIKI_STATUSES, WIKI_STATUS_LABELS } from '@/types/wiki';
import type { WikiStatus } from '@/types/wiki';
import WikiArticleTable from './WikiArticleTable';

const STATUS_OPTIONS = [
  { value: '', label: '전체 상태' },
  ...WIKI_STATUSES.map((s) => ({ value: s, label: WIKI_STATUS_LABELS[s].label })),
];

const WikiPage = () => {
  const currentUserId = useAuthStore((s) => s.user?.id);
  const reviewerId = currentUserId != null ? String(currentUserId) : '';

  const [agentId, setAgentId] = useState('');
  const [collectionName, setCollectionName] = useState('');
  const [status, setStatus] = useState<WikiStatus | ''>('');
  // wiki-navigation S2: 목록 미포함 대상(타 사용자 private 등) 정제용 수동 입력 폴백
  const [manualInput, setManualInput] = useState(false);
  const distill = useDistillWiki();

  const agentList = useAgentList({ scope: 'all', size: 100 });
  const collections = useCollections();

  const agentOptions = (agentList.data?.agents ?? []).map((a) => ({
    value: a.agent_id,
    label: a.name,
  }));
  const collectionOptions = (collections.data ?? []).map((c) => ({
    value: c.name,
    label: c.display_name,
  }));
  const listLoadFailed = agentList.isError || collections.isError;

  const canDistill = agentId.trim() !== '' && collectionName.trim() !== '';

  const handleDistill = () => {
    if (!canDistill) return;
    distill.mutate({ agent_id: agentId.trim(), collection_name: collectionName.trim() });
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      <div className="border-b border-zinc-200 px-6 py-4">
        <h1 className="text-3xl font-bold tracking-tight text-zinc-900">위키 관리</h1>
        <p className="mt-1 text-[13px] text-zinc-400">
          에이전트 지식을 정제해 위키로 누적하고, 승인된 항목만 검색에 노출합니다
        </p>

        <div className="mt-4 flex flex-wrap items-end gap-2">
          {manualInput ? (
            <>
              <label className="flex flex-col gap-1">
                <span className="text-[12px] font-medium text-zinc-500">에이전트 ID</span>
                <input
                  value={agentId}
                  onChange={(e) => setAgentId(e.target.value)}
                  placeholder="agent_id"
                  className="w-48 rounded-xl border border-zinc-300 bg-white px-3 py-2 text-[13px] outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-[12px] font-medium text-zinc-500">컬렉션</span>
                <input
                  value={collectionName}
                  onChange={(e) => setCollectionName(e.target.value)}
                  placeholder="collection_name"
                  className="w-48 rounded-xl border border-zinc-300 bg-white px-3 py-2 text-[13px] outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
                />
              </label>
            </>
          ) : (
            <>
              <div className="flex w-48 flex-col gap-1">
                <span className="text-[12px] font-medium text-zinc-500">에이전트</span>
                <Dropdown
                  value={agentId}
                  onChange={setAgentId}
                  options={agentOptions}
                  searchable
                  placeholder="에이전트 선택"
                  isLoading={agentList.isLoading}
                  emptyText="에이전트가 없습니다"
                  ariaLabel="에이전트 선택"
                  className="w-full"
                />
              </div>
              <div className="flex w-48 flex-col gap-1">
                <span className="text-[12px] font-medium text-zinc-500">컬렉션</span>
                <Dropdown
                  value={collectionName}
                  onChange={setCollectionName}
                  options={collectionOptions}
                  searchable
                  placeholder="컬렉션 선택"
                  isLoading={collections.isLoading}
                  emptyText="컬렉션이 없습니다"
                  ariaLabel="컬렉션 선택"
                  className="w-full"
                />
              </div>
            </>
          )}
          <button
            onClick={handleDistill}
            disabled={!canDistill || distill.isPending}
            className="rounded-xl bg-violet-600 px-4 py-2 text-[13px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {distill.isPending ? '정제 중…' : '정제 실행'}
          </button>
          <button
            onClick={() => setManualInput((v) => !v)}
            className="rounded-xl px-2 py-2 text-[12px] text-zinc-400 underline-offset-2 transition-all hover:text-zinc-600 hover:underline"
          >
            {manualInput ? '목록에서 선택' : '직접 입력'}
          </button>
          <div className="ml-auto w-40">
            <Dropdown
              value={status}
              onChange={(v) => setStatus(v as WikiStatus | '')}
              options={STATUS_OPTIONS}
              className="w-full"
            />
          </div>
        </div>
        {listLoadFailed && !manualInput && (
          <p className="mt-2 text-[12px] text-amber-600">
            목록을 불러오지 못했습니다 · 직접 입력으로 전환해 정제할 수 있습니다
          </p>
        )}
        {distill.isSuccess && (
          <p className="mt-2 text-[12px] text-emerald-600">
            {distill.data?.created_count}개 초안이 생성되었습니다 (승인 대기)
            {(distill.data?.skipped_count ?? 0) > 0 &&
              ` · ${distill.data?.skipped_count}건은 이미 정제되어 건너뜀`}
          </p>
        )}
      </div>

      <div style={{ flex: 1, overflowY: 'auto' }}>
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
          {agentId.trim() === '' ? (
            <div className="py-10 text-center text-[13px] text-zinc-400">
              에이전트를 선택하면 위키 목록이 표시됩니다
            </div>
          ) : (
            <div className="rounded-2xl border border-zinc-200 bg-white p-4">
              <WikiArticleTable agentId={agentId.trim()} status={status} reviewerId={reviewerId} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default WikiPage;
