// Design Ref: graph-rag-foundation §5.1 추출 탭·§5.4 — KB 문서별 최근 잡, 진행 중이면 5초 폴링
import { useState } from 'react';
import {
  useExtractGraphDocument,
  useGraphIntegrity,
  useGraphKbDocuments,
} from '@/hooks/useGraphRag';
import { useKnowledgeBases } from '@/hooks/useKnowledgeBases';
import { GRAPH_JOB_STATUS_LABELS, type ExtractionJob } from '@/types/graphRag';

const BUSY = new Set(['pending', 'processing']);

const STATUS_CLS: Record<string, string> = {
  pending: 'bg-zinc-100 text-zinc-600',
  processing: 'bg-blue-50 text-blue-700',
  completed: 'bg-emerald-50 text-emerald-700',
  partial: 'bg-amber-50 text-amber-700',
  failed: 'bg-red-50 text-red-700',
};

const StatusBadge = ({ job }: { job: ExtractionJob | null }) => {
  if (!job) return <span className="text-[12px] text-zinc-400">추출 안 함</span>;
  return (
    <span
      title={job.error_message ?? undefined}
      className={`rounded-full px-2 py-0.5 text-[12px] font-medium ${STATUS_CLS[job.status] ?? ''}`}
    >
      {GRAPH_JOB_STATUS_LABELS[job.status] ?? job.status}
    </span>
  );
};

const when = (job: ExtractionJob | null) =>
  (job?.finished_at ?? job?.started_at ?? job?.created_at ?? '').slice(0, 16).replace('T', ' ');

interface GraphRagExtractionTabProps {
  backendReady: boolean;
}

const GraphRagExtractionTab = ({ backendReady }: GraphRagExtractionTabProps) => {
  const [kbId, setKbId] = useState<string | null>(null);
  const { data: kbs } = useKnowledgeBases();
  const { data, isLoading, error } = useGraphKbDocuments(kbId);
  const extract = useExtractGraphDocument(kbId);
  const integrity = useGraphIntegrity();

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-[13px] font-medium text-zinc-700">
          지식베이스
          <select
            aria-label="지식베이스"
            value={kbId ?? ''}
            onChange={(e) => setKbId(e.target.value || null)}
            className="ml-2 rounded-lg border border-zinc-300 px-2 py-1.5 text-[13px]"
          >
            <option value="">— 선택 —</option>
            {(kbs ?? []).map((kb) => (
              <option key={kb.kb_id} value={kb.kb_id}>
                {kb.name}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          disabled={!backendReady || integrity.isPending}
          onClick={() => integrity.mutate(kbId)}
          className="rounded-lg border border-zinc-300 px-3 py-1.5 text-[13px] disabled:opacity-40"
        >
          정합성 점검
        </button>
        {integrity.data && (
          <span className="text-[12.5px] text-zinc-600">
            근거 청크 {integrity.data.checked}건 확인 · 검색 색인에 없는 청크 {integrity.data.missing}건
            {integrity.data.missing_document_ids.length > 0 &&
              ` (문서 ${integrity.data.missing_document_ids.join(', ')})`}
          </span>
        )}
        {!backendReady && (
          <span className="text-[12.5px] text-red-600">Neo4j 에 연결되지 않아 추출할 수 없습니다.</span>
        )}
      </div>

      {extract.error && (
        <p role="alert" className="text-[12.5px] text-red-600">
          {extract.error.message}
        </p>
      )}

      {!kbId ? (
        <p className="text-[13px] text-zinc-400">지식베이스를 고르면 문서별 추출 상태가 나옵니다.</p>
      ) : isLoading ? (
        <p className="text-[13px] text-zinc-400">불러오는 중…</p>
      ) : error ? (
        <p className="text-[13px] text-red-600">{error.message}</p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-zinc-200 bg-white">
          <table className="w-full text-left text-[13px]">
            <thead className="bg-zinc-50 text-[12px] text-zinc-500">
              <tr>
                <th className="px-3 py-2">파일명</th>
                <th className="px-3 py-2">상태</th>
                <th className="px-3 py-2">처리 / 전체</th>
                <th className="px-3 py-2">엔티티(신규·연결)</th>
                <th className="px-3 py-2">관계</th>
                <th className="px-3 py-2">LLM · Jev 호출</th>
                <th className="px-3 py-2">최근 시각</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {(data?.items ?? []).map((d) => {
                const j = d.job;
                const busy = !!j && BUSY.has(j.status);
                const disabled = !backendReady || busy || extract.isPending;
                return (
                  <tr key={d.document_id} className="border-t border-zinc-100">
                    <td className="px-3 py-2 font-medium text-zinc-800">{d.filename}</td>
                    <td className="px-3 py-2">
                      <StatusBadge job={j} />
                    </td>
                    <td className="px-3 py-2">
                      {j ? `${j.processed_chunks} / ${j.total_chunks}` : `- / ${d.chunk_count}`}
                      {j && j.failed_chunks > 0 && (
                        <span className="ml-1 text-red-600">(실패 {j.failed_chunks})</span>
                      )}
                    </td>
                    <td className="px-3 py-2">{j ? `${j.entities_created} · ${j.entities_linked}` : '-'}</td>
                    <td className="px-3 py-2">{j ? j.relations_created : '-'}</td>
                    <td className="px-3 py-2">{j ? `${j.llm_calls} · ${j.judge_calls}` : '-'}</td>
                    <td className="px-3 py-2 text-zinc-500">{when(j)}</td>
                    <td className="space-x-1 whitespace-nowrap px-3 py-2 text-right">
                      <button
                        type="button"
                        disabled={disabled}
                        onClick={() => extract.mutate({ documentId: d.document_id, mode: 'resume' })}
                        className="rounded-md border border-zinc-300 px-2 py-1 text-[12px] disabled:opacity-40"
                      >
                        이어서 실행
                      </button>
                      <button
                        type="button"
                        disabled={disabled}
                        onClick={() => extract.mutate({ documentId: d.document_id, mode: 'rebuild' })}
                        className="rounded-md border border-zinc-300 px-2 py-1 text-[12px] disabled:opacity-40"
                      >
                        다시 만들기
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {data?.items.length === 0 && (
            <p className="px-3 py-6 text-center text-[13px] text-zinc-400">문서가 없습니다.</p>
          )}
        </div>
      )}
    </div>
  );
};

export default GraphRagExtractionTab;
