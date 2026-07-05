// LLM-WIKI-001: 위키 항목 목록 테이블 + 거버넌스 액션 + 상세/편집 패널.
import { useState } from 'react';

import {
  useApproveArticle,
  useDeprecateArticle,
  useRejectArticle,
  useRestoreArticle,
  useWikiList,
} from '@/hooks/useWiki';
import { WIKI_STATUS_LABELS } from '@/types/wiki';
import type { WikiArticle, WikiStatus } from '@/types/wiki';
import WikiDetailPanel from './WikiDetailPanel';

interface WikiArticleTableProps {
  agentId: string;
  status?: WikiStatus | '';
  reviewerId: string;
}

const WikiArticleTable = ({
  agentId,
  status,
  reviewerId,
}: WikiArticleTableProps) => {
  const params = { agent_id: agentId, ...(status ? { status } : {}) };
  const { data, isLoading, isError, refetch } = useWikiList(params);
  const approve = useApproveArticle();
  const reject = useRejectArticle();
  const deprecate = useDeprecateArticle();
  const restore = useRestoreArticle();
  const [selected, setSelected] = useState<WikiArticle | null>(null);
  const actionsDisabled = reviewerId === '';

  if (isLoading) {
    return <div className="py-10 text-center text-[13px] text-zinc-400">불러오는 중…</div>;
  }
  if (isError) {
    return (
      <div className="flex items-center gap-2 py-6">
        <p className="text-[13px] text-zinc-500">목록을 불러올 수 없습니다</p>
        <button
          onClick={() => refetch()}
          className="rounded-lg bg-violet-600 px-3 py-1.5 text-[12px] font-medium text-white hover:bg-violet-700 active:scale-95"
        >
          재시도
        </button>
      </div>
    );
  }

  const items = data?.items ?? [];
  if (items.length === 0) {
    return <div className="py-10 text-center text-[13px] text-zinc-400">위키 항목이 없습니다</div>;
  }

  const renderActions = (a: WikiArticle) => {
    if (a.status === 'draft') {
      return (
        <>
          <ActionButton
            label="승인"
            tone="approve"
            disabled={actionsDisabled}
            onClick={() => approve.mutate({ id: a.id, data: { reviewer_id: reviewerId } })}
          />
          <ActionButton
            label="반려"
            tone="danger"
            disabled={actionsDisabled}
            onClick={() => reject.mutate(a.id)}
          />
        </>
      );
    }
    if (a.status === 'approved') {
      return (
        <ActionButton
          label="폐기"
          tone="danger"
          disabled={actionsDisabled}
          onClick={() => deprecate.mutate(a.id)}
        />
      );
    }
    return (
      <ActionButton
        label="복구"
        tone="approve"
        disabled={actionsDisabled}
        onClick={() => restore.mutate({ id: a.id, data: { reviewer_id: reviewerId } })}
      />
    );
  };

  return (
    <>
    <table className="w-full text-left text-[13px]">
      <thead>
        <tr className="border-b border-zinc-200 text-[12px] text-zinc-400">
          <th className="py-2 pr-3 font-medium">제목</th>
          <th className="py-2 pr-3 font-medium">상태</th>
          <th className="py-2 pr-3 font-medium">출처</th>
          <th className="py-2 pr-3 font-medium">신뢰도</th>
          <th className="py-2 pr-3 font-medium">작업</th>
        </tr>
      </thead>
      <tbody>
        {items.map((a) => {
          const badge = WIKI_STATUS_LABELS[a.status];
          return (
            <tr key={a.id} className="border-b border-zinc-100">
              <td className="py-3 pr-3">
                <button
                  onClick={() => setSelected(a)}
                  className="font-medium text-zinc-800 hover:text-violet-600 hover:underline"
                >
                  {a.title}
                </button>
              </td>
              <td className="py-3 pr-3">
                <span className={`rounded-lg px-2 py-1 text-[12px] ${badge.color}`}>
                  {badge.label}
                </span>
              </td>
              <td className="py-3 pr-3 text-zinc-500">{a.source_type}</td>
              <td className="py-3 pr-3 tabular-nums text-zinc-600">
                {a.confidence.toFixed(2)}
              </td>
              <td className="py-3 pr-3">
                <div className="flex gap-1.5">{renderActions(a)}</div>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
    {selected && (
      <WikiDetailPanel
        article={selected}
        currentUserId={reviewerId}
        onClose={() => setSelected(null)}
      />
    )}
    </>
  );
};

interface ActionButtonProps {
  label: string;
  tone: 'approve' | 'danger';
  onClick: () => void;
  disabled?: boolean;
}

const ActionButton = ({ label, tone, onClick, disabled }: ActionButtonProps) => (
  <button
    onClick={onClick}
    disabled={disabled}
    className={`rounded-lg px-2.5 py-1 text-[12px] font-medium transition-all active:scale-95 disabled:cursor-not-allowed disabled:opacity-40 ${
      tone === 'approve'
        ? 'bg-violet-600 text-white hover:bg-violet-700'
        : 'border border-zinc-200 bg-zinc-50 text-zinc-600 hover:border-red-200 hover:bg-red-50 hover:text-red-500'
    }`}
  >
    {label}
  </button>
);

export default WikiArticleTable;
