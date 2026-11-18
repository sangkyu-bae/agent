// Design Ref: graph-rag-foundation §4.2 reject·§5.1 검토 큐 — 엔티티·주제 판정 공용.
// 거절: 연결 판정은 분리(대상 없음) 또는 다른 후보로 재연결, 신규 판정은 대상 후보가 필수.
import { useState } from 'react';
import {
  useApproveGraphReview,
  useGraphReview,
  useRejectGraphReview,
} from '@/hooks/useGraphRag';
import type { ReviewItem } from '@/types/graphRag';

const pct = (p: number | null | undefined) => (p == null ? '-' : `${Math.round(p * 100)}%`);

const ReviewCard = ({ item }: { item: ReviewItem }) => {
  const [rejecting, setRejecting] = useState(false);
  const [target, setTarget] = useState<string>('');
  const [note, setNote] = useState('');
  const approve = useApproveGraphReview();
  const reject = useRejectGraphReview();
  const isTopic = item.kind === 'topic';
  const chosen = item.candidates.find((c) => c.entity_id === item.entity_id);
  const others = item.candidates.filter((c) => c.entity_id && c.entity_id !== item.entity_id);
  // 신규로 만든 판정은 옮길 대상이 있어야 한다(분리할 수 없음)
  const needsTarget = item.created_new;
  const canReject = !reject.isPending && (!needsTarget || !!target);
  const error = approve.error ?? reject.error;

  return (
    <li className="rounded-xl border border-zinc-200 bg-white p-4 text-[13px]">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded bg-zinc-100 px-1.5 text-[11.5px] text-zinc-500">
          {isTopic ? '주제' : '엔티티'} · {item.mention_type}
        </span>
        <span className="font-semibold text-zinc-800">{item.mention_text}</span>
        <span className="text-zinc-400">→</span>
        <span className="text-zinc-700">
          {item.created_new ? '새로 만듦' : chosen?.name ?? item.chosen_label}
        </span>
        <span className="ml-auto text-[12px] text-zinc-400">
          {item.decided_by} · 확률 {pct(item.probability)}
          {item.llm_confidence && ` · LLM 확신 ${item.llm_confidence}`}
        </span>
      </div>
      {item.llm_reason && <p className="mt-1 text-[12px] text-zinc-500">LLM 사유: {item.llm_reason}</p>}
      {item.candidates.length > 0 && (
        <p className="mt-1 text-[12px] text-zinc-500">
          후보:{' '}
          {item.candidates
            .map((c) => `${c.name ?? c.label}${item.probabilities && c.label ? ` ${pct(item.probabilities[c.label])}` : ''}`)
            .join(', ')}
          {item.probabilities?.NEW != null && ` · 새로 만들기 ${pct(item.probabilities.NEW)}`}
        </p>
      )}
      <p className="mt-0.5 text-[11.5px] text-zinc-400">문서 {item.document_id.slice(0, 8)}</p>

      {!rejecting ? (
        <div className="mt-3 flex gap-2">
          <button
            type="button"
            disabled={approve.isPending}
            onClick={() => approve.mutate({ id: item.id })}
            className="rounded-lg bg-violet-600 px-3 py-1 text-[12.5px] font-medium text-white disabled:opacity-40"
          >
            승인
          </button>
          <button
            type="button"
            onClick={() => setRejecting(true)}
            className="rounded-lg border border-zinc-300 px-3 py-1 text-[12.5px]"
          >
            거절
          </button>
        </div>
      ) : (
        <fieldset className="mt-3 space-y-2 rounded-lg bg-zinc-50 p-3">
          <legend className="text-[12.5px] font-semibold text-zinc-700">거절 처리</legend>
          {!needsTarget && (
            <label className="flex items-center gap-2">
              <input
                type="radio"
                name={`target-${item.id}`}
                checked={target === ''}
                onChange={() => setTarget('')}
              />
              분리 — “{item.mention_text}”{isTopic ? ' 주제를' : '을(를)'} 새로 만든다
            </label>
          )}
          {others.map((c) => (
            <label key={c.entity_id} className="flex items-center gap-2">
              <input
                type="radio"
                name={`target-${item.id}`}
                checked={target === c.entity_id}
                onChange={() => setTarget(c.entity_id as string)}
              />
              {c.name} ({c.type})에 다시 연결
            </label>
          ))}
          {needsTarget && others.length === 0 && (
            <p className="text-[12px] text-amber-600">옮길 후보가 없어 거절할 수 없습니다.</p>
          )}
          <label className="block text-[12.5px] text-zinc-600">
            메모
            <input
              aria-label="메모"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={500}
              className="mt-1 w-full rounded-lg border border-zinc-300 px-2 py-1 text-[12.5px]"
            />
          </label>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={!canReject}
              onClick={() =>
                reject.mutate({
                  id: item.id,
                  req: { target_entity_id: target || null, note: note.trim() || null },
                })
              }
              className="rounded-lg bg-red-600 px-3 py-1 text-[12.5px] font-medium text-white disabled:opacity-40"
            >
              거절 확인
            </button>
            <button
              type="button"
              onClick={() => setRejecting(false)}
              className="rounded-lg px-3 py-1 text-[12.5px] text-zinc-600"
            >
              취소
            </button>
          </div>
        </fieldset>
      )}
      {error && (
        <p role="alert" className="mt-2 text-[12px] text-red-600">
          {error.message}
        </p>
      )}
    </li>
  );
};

const GraphRagReviewTab = () => {
  const { data, isLoading, error } = useGraphReview();
  if (isLoading) return <p className="text-[13px] text-zinc-400">불러오는 중…</p>;
  if (error) return <p className="text-[13px] text-red-600">{error.message}</p>;
  if (!data || data.items.length === 0) {
    return <p className="text-[13px] text-zinc-400">검토할 항목이 없습니다.</p>;
  }
  return (
    <div className="space-y-3">
      <p className="text-[12.5px] text-zinc-500">
        애매한 구간(LLM 재판정·대체)과 새로 만든 주제가 여기에 쌓입니다. 승인하면 그대로 두고,
        거절하면 분리하거나 다른 후보로 옮깁니다.
      </p>
      <ul className="space-y-3">
        {data.items.map((item) => (
          <ReviewCard key={item.id} item={item} />
        ))}
      </ul>
    </div>
  );
};

export default GraphRagReviewTab;
