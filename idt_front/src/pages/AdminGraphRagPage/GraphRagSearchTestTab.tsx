// Design Ref: graph-rag-foundation §4.2 search-test·§5.1 — 주제 범위·연결 엔티티·경로·3열 비교
import { useState } from 'react';
import { useGraphSearchTest } from '@/hooks/useGraphRag';
import { useKnowledgeBases } from '@/hooks/useKnowledgeBases';
import {
  GRAPH_LINK_VIA_LABELS,
  GRAPH_SCOPE_REASON_LABELS,
  type SearchHitItem,
  type SearchTestResponse,
} from '@/types/graphRag';

const SOURCE_CLS: Record<string, string> = {
  graph: 'bg-violet-50 text-violet-700',
  both: 'bg-emerald-50 text-emerald-700',
};

const HitColumn = ({ title, hits, note }: { title: string; hits: SearchHitItem[]; note?: string | null }) => (
  <section aria-label={title} className="rounded-xl border border-zinc-200 bg-white p-3">
    <h3 className="mb-2 text-[13px] font-semibold text-zinc-700">
      {title} <span className="font-normal text-zinc-400">{hits.length}건</span>
    </h3>
    {note && <p className="mb-2 text-[12px] text-red-600">{note}</p>}
    <ol className="space-y-2">
      {hits.map((h, i) => (
        <li key={`${h.chunk_id}-${i}`} className="rounded-lg bg-zinc-50 p-2 text-[12.5px]">
          <div className="mb-1 flex items-center gap-1.5">
            <span className="text-zinc-400">{i + 1}</span>
            <span className="truncate font-medium text-zinc-700">{h.filename || h.document_id.slice(0, 8)}</span>
            <span className={`ml-auto rounded px-1.5 text-[11px] ${SOURCE_CLS[h.source] ?? 'bg-zinc-100 text-zinc-500'}`}>
              {h.source}
            </span>
            <span className="text-[11px] text-zinc-400">{h.score.toFixed(4)}</span>
          </div>
          <p className="line-clamp-3 text-zinc-600">{h.content_preview}</p>
        </li>
      ))}
      {hits.length === 0 && <li className="text-[12px] text-zinc-400">결과 없음</li>}
    </ol>
  </section>
);

const ScopeLine = ({ scope }: { scope: SearchTestResponse['scope'] }) => (
  <p className="text-[13px] text-zinc-700">
    <span className="font-semibold">주제 범위 </span>
    {scope.topic_ids ? (
      <>
        {scope.topic_names.map((n) => (
          <span key={n} className="mr-1 rounded-full bg-violet-50 px-2 py-0.5 text-violet-700">
            {n}
          </span>
        ))}
        <span className="text-[12px] text-zinc-400">판정: {scope.decided_by}</span>
      </>
    ) : (
      <span className="text-zinc-500">
        없음 — {GRAPH_SCOPE_REASON_LABELS[scope.reason ?? ''] ?? scope.reason ?? '범위 없이 검색'}
      </span>
    )}
  </p>
);

interface GraphRagSearchTestTabProps {
  backendReady: boolean;
}

const GraphRagSearchTestTab = ({ backendReady }: GraphRagSearchTestTabProps) => {
  const { data: kbs } = useKnowledgeBases();
  const [query, setQuery] = useState('');
  const [kbId, setKbId] = useState('');
  const [topK, setTopK] = useState(5);
  const [hops, setHops] = useState('');
  const search = useGraphSearchTest();
  const r = search.data;

  return (
    <div className="space-y-4">
      <form
        className="space-y-3 rounded-xl border border-zinc-200 bg-white p-4"
        onSubmit={(e) => {
          e.preventDefault();
          search.mutate({
            query: query.trim(),
            kb_id: kbId || null,
            top_k: topK,
            max_hops: hops ? Number(hops) : null,
          });
        }}
      >
        <textarea
          aria-label="질문"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          rows={2}
          maxLength={500}
          placeholder="예: 운전자금대출 한도는 얼마인가요?"
          className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-[13px]"
        />
        <div className="flex flex-wrap items-center gap-3 text-[13px] text-zinc-700">
          <label>
            지식베이스
            <select
              aria-label="검색 지식베이스"
              value={kbId}
              onChange={(e) => setKbId(e.target.value)}
              className="ml-2 rounded-lg border border-zinc-300 px-2 py-1"
            >
              <option value="">전체</option>
              {(kbs ?? []).map((kb) => (
                <option key={kb.kb_id} value={kb.kb_id}>
                  {kb.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            결과 수
            <input
              aria-label="결과 수"
              type="number"
              min={1}
              max={20}
              value={topK}
              onChange={(e) => setTopK(Math.min(20, Math.max(1, Number(e.target.value) || 1)))}
              className="ml-2 w-16 rounded-lg border border-zinc-300 px-2 py-1"
            />
          </label>
          <label>
            최대 단계
            <select
              aria-label="최대 단계"
              value={hops}
              onChange={(e) => setHops(e.target.value)}
              className="ml-2 rounded-lg border border-zinc-300 px-2 py-1"
            >
              <option value="">설정값</option>
              <option value="1">1</option>
              <option value="2">2</option>
              <option value="3">3</option>
            </select>
          </label>
          <button
            type="submit"
            disabled={!query.trim() || !backendReady || search.isPending}
            className="ml-auto rounded-lg bg-violet-600 px-4 py-1.5 font-medium text-white disabled:opacity-40"
          >
            {search.isPending ? '실행 중…' : '실행'}
          </button>
        </div>
        <p className="text-[11.5px] text-zinc-400">
          관리자 본인 권한으로 실행합니다. 이 테스트에서만 시간 상한을 5초로 올려 주제 판정 결과를 함께 봅니다.
        </p>
      </form>

      {search.error && (
        <p role="alert" className="text-[12.5px] text-red-600">
          {search.error.message}
        </p>
      )}

      {r && (
        <div className="space-y-4">
          <div className="space-y-2 rounded-xl border border-zinc-200 bg-white p-4">
            <ScopeLine scope={r.scope} />
            <div className="flex flex-wrap items-center gap-1.5 text-[12.5px]">
              <span className="font-semibold text-zinc-700">연결 엔티티</span>
              {r.linked_entities.length === 0 && <span className="text-zinc-400">없음</span>}
              {r.linked_entities.map((e) => (
                <span key={e.id} className="rounded-full bg-zinc-100 px-2 py-0.5 text-zinc-700">
                  {e.name} · {GRAPH_LINK_VIA_LABELS[e.via] ?? e.via} {e.score.toFixed(2)}
                </span>
              ))}
            </div>
            {r.paths.length > 0 && (
              <details className="text-[12.5px]">
                <summary className="cursor-pointer font-semibold text-zinc-700">경로 {r.paths.length}개</summary>
                <ul className="mt-1 space-y-0.5 text-zinc-600">
                  {r.paths.map((p, i) => (
                    <li key={i}>
                      <span className="mr-1 text-zinc-400">{p.hops}단계</span>
                      {p.path.join(' → ')}
                    </li>
                  ))}
                </ul>
              </details>
            )}
            <p className="text-[12px] text-zinc-500">
              권한 필터로 제외 {r.filtered_out}건 ·{' '}
              {Object.entries(r.timings_ms)
                .map(([k, v]) => `${k} ${v}ms`)
                .join(' · ')}
              {r.skip_reason && <span className="ml-2 text-amber-600">그래프 건너뜀: {r.skip_reason}</span>}
            </p>
          </div>
          <div className="grid gap-3 lg:grid-cols-3">
            <HitColumn title="그래프" hits={r.graph_hits} />
            <HitColumn title="하이브리드" hits={r.hybrid_hits} note={r.hybrid_error} />
            <HitColumn title="결합" hits={r.fused_hits} />
          </div>
        </div>
      )}
    </div>
  );
};

export default GraphRagSearchTestTab;
