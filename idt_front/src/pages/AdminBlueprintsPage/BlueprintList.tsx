// Design §5.4 목록 — 테이블 + 비활성화 확인 다이얼로그
import { useState } from 'react';
import ConfirmDialog from '@/components/common/ConfirmDialog';
import { useBlueprints, useDeactivateBlueprint } from '@/hooks/useBlueprints';
import type { BlueprintSummary } from '@/types/blueprint';

interface BlueprintListProps {
  onEdit: (id: string) => void;
}

const BlueprintList = ({ onEdit }: BlueprintListProps) => {
  const { data, isLoading, isError, error } = useBlueprints(true);
  const deactivate = useDeactivateBlueprint();
  const [target, setTarget] = useState<BlueprintSummary | null>(null);

  if (isLoading) {
    return (
      <div className="space-y-2" aria-label="로딩 중">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-12 animate-pulse rounded-xl bg-zinc-100" />
        ))}
      </div>
    );
  }
  if (isError) {
    return (
      <p role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-[13px] text-red-700">
        {error.message}
      </p>
    );
  }
  if (!data || data.length === 0) {
    return (
      <p className="rounded-xl border border-dashed border-zinc-200 p-8 text-center text-[13px] text-zinc-400">
        등록된 blueprint 가 없습니다. 「새 blueprint」로 Golden Sample 을 올려 시작하세요.
      </p>
    );
  }

  return (
    <>
      <table className="w-full overflow-hidden rounded-xl border border-zinc-200 text-[13px]">
        <thead className="bg-zinc-50 text-left text-[12px] font-semibold text-zinc-500">
          <tr>
            <th className="px-4 py-2.5">이름</th>
            <th className="px-4 py-2.5">원본</th>
            <th className="px-4 py-2.5">페이지</th>
            <th className="px-4 py-2.5">패턴 수</th>
            <th className="px-4 py-2.5">상태</th>
            <th className="px-4 py-2.5">수정일</th>
            <th className="px-4 py-2.5" />
          </tr>
        </thead>
        <tbody>
          {data.map((b) => (
            <tr key={b.id} className="border-t border-zinc-100">
              <td className="px-4 py-2.5 font-medium text-zinc-800">{b.name}</td>
              <td className="px-4 py-2.5">
                <span className="rounded bg-zinc-100 px-1.5 py-0.5 text-[11px] uppercase text-zinc-600">
                  {b.source_kind}
                </span>
              </td>
              <td className="px-4 py-2.5 text-zinc-600">{b.page_count}</td>
              <td className="px-4 py-2.5 text-zinc-600">{b.pattern_count}</td>
              <td className="px-4 py-2.5">
                <span
                  className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${
                    b.status === 'active'
                      ? 'bg-emerald-50 text-emerald-700'
                      : 'bg-zinc-100 text-zinc-500'
                  }`}
                >
                  {b.status}
                </span>
              </td>
              <td className="px-4 py-2.5 text-zinc-500">{new Date(b.updated_at).toLocaleString()}</td>
              <td className="px-4 py-2.5 text-right">
                <button
                  type="button"
                  onClick={() => onEdit(b.id)}
                  className="mr-2 text-[12.5px] font-medium text-violet-700 hover:underline"
                >
                  편집
                </button>
                {b.status === 'active' && (
                  <button
                    type="button"
                    onClick={() => setTarget(b)}
                    className="text-[12.5px] font-medium text-red-600 hover:underline"
                  >
                    비활성화
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <ConfirmDialog
        isOpen={target !== null}
        title="blueprint 비활성화"
        description={`「${target?.name ?? ''}」를 비활성화하면 에이전트 선택 목록에서 사라지고 연결된 워커는 안내 메시지만 반환합니다.`}
        confirmLabel="비활성화"
        variant="danger"
        isPending={deactivate.isPending}
        error={deactivate.error?.message ?? null}
        onClose={() => setTarget(null)}
        onConfirm={() => {
          if (!target) return;
          deactivate.mutate(target.id, { onSuccess: () => setTarget(null) });
        }}
      />
    </>
  );
};

export default BlueprintList;
