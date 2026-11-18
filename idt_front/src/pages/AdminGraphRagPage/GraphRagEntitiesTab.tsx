// Design Ref: graph-rag-foundation §5.1 엔티티·관계 탭 — 검색·타입 필터·페이지, 행 펼침 상세
import { useState } from 'react';
import { useGraphEntities, useGraphEntity } from '@/hooks/useGraphRag';

const PAGE_SIZE = 20;

const EntityDetail = ({ id }: { id: string }) => {
  const { data, isLoading, error } = useGraphEntity(id);
  if (isLoading) return <p className="px-4 py-3 text-[12.5px] text-zinc-400">불러오는 중…</p>;
  if (error || !data) return <p className="px-4 py-3 text-[12.5px] text-red-600">{error?.message}</p>;
  return (
    <div className="grid gap-4 bg-zinc-50 px-4 py-3 text-[12.5px] md:grid-cols-3">
      <div>
        <p className="mb-1 font-semibold text-zinc-600">별칭</p>
        {data.aliases.length === 0 ? (
          <p className="text-zinc-400">없음</p>
        ) : (
          <ul className="space-y-0.5">
            {data.aliases.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <p className="mb-1 font-semibold text-zinc-600">관계</p>
        {data.relations.length === 0 ? (
          <p className="text-zinc-400">없음</p>
        ) : (
          <ul className="space-y-1">
            {data.relations.map((r) => (
              <li key={r.id} title={r.evidence_text}>
                <span className="text-zinc-400">{r.direction === 'out' ? '→' : '←'}</span>{' '}
                <span className="rounded bg-white px-1 text-zinc-500">{r.type}</span>{' '}
                <span>{r.other_name}</span>
                <span className="ml-1 text-[11px] text-zinc-400">문서 {r.document_id.slice(0, 8)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <p className="mb-1 font-semibold text-zinc-600">언급 근거</p>
        {data.mentions.length === 0 ? (
          <p className="text-zinc-400">없음</p>
        ) : (
          <ul className="space-y-1.5">
            {data.mentions.map((m) => (
              <li key={m.chunk_id} className="rounded bg-white p-2 text-zinc-600">
                {m.preview || <span className="text-zinc-400">(검색 색인에 없는 청크)</span>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
};

interface GraphRagEntitiesTabProps {
  entityTypes: string[];
}

const GraphRagEntitiesTab = ({ entityTypes }: GraphRagEntitiesTabProps) => {
  const [q, setQ] = useState('');
  const [query, setQuery] = useState('');
  const [type, setType] = useState('');
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<string | null>(null);
  const { data, isLoading, error } = useGraphEntities({ q: query, type, page, size: PAGE_SIZE });
  const lastPage = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <div className="space-y-4">
      <form
        className="flex flex-wrap gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setQuery(q.trim());
          setPage(1);
        }}
      >
        <input
          aria-label="엔티티 검색"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="이름으로 검색"
          className="w-64 rounded-lg border border-zinc-300 px-3 py-1.5 text-[13px]"
        />
        <select
          aria-label="타입"
          value={type}
          onChange={(e) => {
            setType(e.target.value);
            setPage(1);
          }}
          className="rounded-lg border border-zinc-300 px-2 py-1.5 text-[13px]"
        >
          <option value="">모든 타입</option>
          {entityTypes.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <button type="submit" className="rounded-lg border border-zinc-300 px-3 text-[13px]">
          검색
        </button>
        {data && <span className="self-center text-[12.5px] text-zinc-500">총 {data.total}개</span>}
      </form>

      {isLoading ? (
        <p className="text-[13px] text-zinc-400">불러오는 중…</p>
      ) : error ? (
        <p className="text-[13px] text-red-600">{error.message}</p>
      ) : (
        <ul className="divide-y divide-zinc-100 rounded-xl border border-zinc-200 bg-white">
          {(data?.items ?? []).map((e) => (
            <li key={e.id}>
              <button
                type="button"
                aria-expanded={open === e.id}
                onClick={() => setOpen(open === e.id ? null : e.id)}
                className="flex w-full items-center gap-3 px-4 py-2.5 text-left text-[13px] hover:bg-zinc-50"
              >
                <span className="font-medium text-zinc-800">{e.name}</span>
                <span className="rounded bg-zinc-100 px-1.5 text-[11.5px] text-zinc-500">{e.type}</span>
                <span className="ml-auto text-[12px] text-zinc-400">
                  관계 {e.relation_count} · 언급 {e.mention_count}
                </span>
              </button>
              {open === e.id && <EntityDetail id={e.id} />}
            </li>
          ))}
          {data?.items.length === 0 && (
            <li className="px-4 py-6 text-center text-[13px] text-zinc-400">엔티티가 없습니다.</li>
          )}
        </ul>
      )}

      {lastPage > 1 && (
        <div className="flex items-center justify-center gap-3 text-[13px]">
          <button type="button" disabled={page <= 1} onClick={() => setPage(page - 1)} className="disabled:opacity-40">
            이전
          </button>
          <span>
            {page} / {lastPage}
          </span>
          <button
            type="button"
            disabled={page >= lastPage}
            onClick={() => setPage(page + 1)}
            className="disabled:opacity-40"
          >
            다음
          </button>
        </div>
      )}
    </div>
  );
};

export default GraphRagEntitiesTab;
