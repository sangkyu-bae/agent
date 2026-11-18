// Design Ref: graph-rag-foundation §11.9 주제 — 대분류 > 소분류 트리, 관리자 추가, 사용/사용 안 함.
// 자동으로 생긴 주제(검토 대기)는 여기서 바로 사용으로 바꾸거나 검토 큐에서 판정째로 처리한다.
import { useState } from 'react';
import { useCreateGraphTopic, useGraphTopics, useUpdateGraphTopic } from '@/hooks/useGraphRag';
import { GRAPH_TOPIC_STATUS_LABELS, type TopicItem } from '@/types/graphRag';

const STATUS_CLS: Record<string, string> = {
  active: 'bg-emerald-50 text-emerald-700',
  pending: 'bg-amber-50 text-amber-700',
  retired: 'bg-zinc-100 text-zinc-500',
};

const TopicRow = ({ topic, onStatus }: { topic: TopicItem; onStatus: (t: TopicItem, s: 'active' | 'retired') => void }) => (
  <div className="flex items-center gap-2 py-1.5 text-[13px]">
    <span className={topic.level === 1 ? 'font-semibold text-zinc-800' : 'text-zinc-700'}>{topic.name}</span>
    <span className={`rounded-full px-2 py-0.5 text-[11.5px] ${STATUS_CLS[topic.status] ?? ''}`}>
      {GRAPH_TOPIC_STATUS_LABELS[topic.status] ?? topic.status}
    </span>
    <span className="text-[11.5px] text-zinc-400">
      {topic.origin === 'auto' ? '자동' : '관리자'} · 문서 {topic.document_count}
    </span>
    <span className="ml-auto space-x-1">
      {topic.status !== 'active' && (
        <button
          type="button"
          aria-label={`${topic.name} 사용`}
          onClick={() => onStatus(topic, 'active')}
          className="rounded-md border border-zinc-300 px-2 py-0.5 text-[12px]"
        >
          사용
        </button>
      )}
      {topic.status !== 'retired' && (
        <button
          type="button"
          aria-label={`${topic.name} 사용 안 함`}
          onClick={() => onStatus(topic, 'retired')}
          className="rounded-md border border-zinc-300 px-2 py-0.5 text-[12px] text-zinc-500"
        >
          사용 안 함
        </button>
      )}
    </span>
  </div>
);

const GraphRagTopicsTab = () => {
  const [includeRetired, setIncludeRetired] = useState(false);
  const { data, isLoading, error } = useGraphTopics(includeRetired);
  const create = useCreateGraphTopic();
  const update = useUpdateGraphTopic();
  const [name, setName] = useState('');
  const [level, setLevel] = useState<1 | 2>(1);
  const [parentId, setParentId] = useState('');

  const topics = data?.items ?? [];
  const majors = topics.filter((t) => t.level === 1);
  const minorsOf = (id: string) => topics.filter((t) => t.level === 2 && t.parent_id === id);
  const orphans = topics.filter((t) => t.level === 2 && !majors.some((m) => m.id === t.parent_id));
  const canCreate = !!name.trim() && (level === 1 || !!parentId) && !create.isPending;
  const onStatus = (t: TopicItem, status: 'active' | 'retired') =>
    update.mutate({ id: t.id, req: { status } });

  return (
    <div className="space-y-4">
      <p className="text-[12.5px] text-zinc-500">
        문서가 들어오면 대분류 1개와 소분류를 자동으로 붙입니다. 맞는 주제가 없으면 새 주제를
        “검토 대기”로 만듭니다. 검색할 때 질문의 주제로 그래프 탐색 범위를 좁힙니다.
      </p>

      <form
        className="flex flex-wrap items-end gap-2 rounded-xl border border-zinc-200 bg-white p-4"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate(
            { name: name.trim(), level, parent_id: level === 2 ? parentId : null },
            { onSuccess: () => setName('') }
          );
        }}
      >
        <label className="text-[13px] text-zinc-700">
          단계
          <select
            aria-label="단계"
            value={level}
            onChange={(e) => setLevel(Number(e.target.value) as 1 | 2)}
            className="ml-2 rounded-lg border border-zinc-300 px-2 py-1.5 text-[13px]"
          >
            <option value={1}>대분류</option>
            <option value={2}>소분류</option>
          </select>
        </label>
        {level === 2 && (
          <label className="text-[13px] text-zinc-700">
            상위 주제
            <select
              aria-label="상위 주제"
              value={parentId}
              onChange={(e) => setParentId(e.target.value)}
              className="ml-2 rounded-lg border border-zinc-300 px-2 py-1.5 text-[13px]"
            >
              <option value="">— 선택 —</option>
              {majors
                .filter((m) => m.status !== 'retired')
                .map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
            </select>
          </label>
        )}
        <input
          aria-label="새 주제 이름"
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={64}
          placeholder="예: 고객"
          className="w-48 rounded-lg border border-zinc-300 px-3 py-1.5 text-[13px]"
        />
        <button
          type="submit"
          disabled={!canCreate}
          className="rounded-lg bg-violet-600 px-3 py-1.5 text-[13px] font-medium text-white disabled:opacity-40"
        >
          주제 추가
        </button>
        <label className="ml-auto flex items-center gap-1.5 text-[12.5px] text-zinc-500">
          <input
            type="checkbox"
            checked={includeRetired}
            onChange={(e) => setIncludeRetired(e.target.checked)}
          />
          사용 안 함 포함
        </label>
      </form>
      {(create.error || update.error) && (
        <p role="alert" className="text-[12.5px] text-red-600">
          {(create.error ?? update.error)?.message}
        </p>
      )}

      {isLoading ? (
        <p className="text-[13px] text-zinc-400">불러오는 중…</p>
      ) : error ? (
        <p className="text-[13px] text-red-600">{error.message}</p>
      ) : topics.length === 0 ? (
        <p className="text-[13px] text-zinc-400">주제가 없습니다. 기본 주제를 추가하거나 문서를 추출하세요.</p>
      ) : (
        <ul className="divide-y divide-zinc-100 rounded-xl border border-zinc-200 bg-white px-4">
          {[...majors, ...orphans].map((m) => (
            <li key={m.id} className="py-1">
              <TopicRow topic={m} onStatus={onStatus} />
              {m.level === 1 && minorsOf(m.id).length > 0 && (
                <ul className="ml-5 border-l border-zinc-100 pl-3">
                  {minorsOf(m.id).map((c) => (
                    <li key={c.id}>
                      <TopicRow topic={c} onStatus={onStatus} />
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

export default GraphRagTopicsTab;
