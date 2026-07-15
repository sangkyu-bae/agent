import {
  useKbSectionSummaries,
  useRetrySectionSummary,
  useSectionSummaryStatus,
} from '@/hooks/useKnowledgeBases';
import type { KbStoreSource } from '@/types/knowledgeBase';
import KbPayloadMeta from './KbPayloadMeta';

interface KbSectionSummaryListProps {
  kbId: string;
  documentId: string;
  source: KbStoreSource;
}

const STATUS_LABELS: Record<string, string> = {
  pending: '대기 중',
  processing: '생성 중',
  failed: '실패',
};

const KbSectionSummaryList = ({
  kbId,
  documentId,
  source,
}: KbSectionSummaryListProps) => {
  const statusQuery = useSectionSummaryStatus(kbId, documentId);
  const summariesQuery = useKbSectionSummaries(kbId, documentId, source);
  const retryMutation = useRetrySectionSummary(kbId, documentId);

  const job = statusQuery.data;
  const jobIncomplete = !!job && job.status !== 'completed';
  const canRetry =
    !!job && (job.status === 'failed' || job.is_stale || job.failed_sections > 0);

  return (
    <div>
      {/* 잡 상태 배너 — 미완료/실패 시에만 (Design D9). 404(요약 비활성)는 미표시 */}
      {jobIncomplete && (
        <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 p-3.5">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-[13px] font-medium text-amber-700">
                섹션 요약 {STATUS_LABELS[job.status] ?? job.status}
                {job.total_sections !== null &&
                  ` — ${job.done_sections}/${job.total_sections} 섹션 완료`}
                {job.failed_sections > 0 && ` · 실패 ${job.failed_sections}`}
                {job.is_stale && ' · 중단됨(stale)'}
              </p>
              {job.error && (
                <p className="mt-1 text-[12px] text-amber-600">{job.error}</p>
              )}
            </div>
            {canRetry && (
              <button
                type="button"
                onClick={() => retryMutation.mutate()}
                disabled={retryMutation.isPending}
                className="shrink-0 rounded-lg bg-amber-600 px-3 py-1.5 text-[12.5px] font-medium text-white hover:bg-amber-700 disabled:opacity-50"
              >
                {retryMutation.isPending ? '재시도 중...' : '재시도'}
              </button>
            )}
          </div>
          {job.total_sections !== null && job.total_sections > 0 && (
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-amber-100">
              <div
                role="progressbar"
                aria-valuenow={job.done_sections}
                aria-valuemax={job.total_sections}
                className="h-full rounded-full bg-amber-500 transition-all"
                style={{
                  width: `${Math.round((job.done_sections / job.total_sections) * 100)}%`,
                }}
              />
            </div>
          )}
        </div>
      )}

      {summariesQuery.isLoading ? (
        <p className="py-8 text-center text-[14px] text-zinc-400">
          섹션 요약을 불러오는 중...
        </p>
      ) : summariesQuery.isError ? (
        <div className="py-8 text-center">
          <p className="text-[14px] text-red-500">
            섹션 요약을 불러오지 못했습니다
          </p>
          <button
            type="button"
            onClick={() => summariesQuery.refetch()}
            className="mt-3 rounded-xl border border-zinc-200 px-4 py-2 text-[13px] font-medium text-zinc-600 hover:bg-zinc-50"
          >
            다시 시도
          </button>
        </div>
      ) : (summariesQuery.data?.items.length ?? 0) === 0 ? (
        <p className="py-8 text-center text-[14px] text-zinc-400">
          저장된 섹션 요약이 없습니다
        </p>
      ) : (
        <div className="space-y-2.5">
          {summariesQuery.data?.items.map((item) => (
            <div
              key={item.chunk_id}
              className="rounded-xl border border-zinc-200 bg-white p-3.5"
            >
              <div className="mb-1.5 flex items-center gap-2">
                <span className="flex h-5 w-6 items-center justify-center rounded bg-zinc-100 text-[10.5px] font-bold text-zinc-500">
                  {item.chunk_index}
                </span>
                <h4 className="text-[13.5px] font-semibold text-zinc-800">
                  {item.clause_title || '(제목 없음)'}
                </h4>
              </div>
              <p className="whitespace-pre-wrap text-[13px] leading-[1.65] text-zinc-600">
                {item.summary_text}
              </p>
              {item.keywords.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {item.keywords.map((kw) => (
                    <span
                      key={kw}
                      className="rounded-md bg-violet-50 px-1.5 py-0.5 text-[11px] font-medium text-violet-600"
                    >
                      {kw}
                    </span>
                  ))}
                </div>
              )}
              <KbPayloadMeta metadata={item.metadata} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default KbSectionSummaryList;
