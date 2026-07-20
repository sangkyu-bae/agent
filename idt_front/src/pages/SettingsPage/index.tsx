// agent-memory: 설정 페이지 — "AI가 기억하는 내용" 관리 (등록/수정/삭제/상한 안내).
// 여기 등록된 메모리는 General Chat 시스템 프롬프트에 상주 주입된다.
import { useState } from 'react';

import {
  useApproveMemory,
  useCreateMemory,
  useDeleteMemory,
  useMemories,
  useRejectMemory,
  useUpdateMemory,
} from '@/hooks/useMemories';
import {
  MEMORY_CONTENT_MAX,
  MEMORY_TYPE_LABELS,
  type Memory,
  type MemoryType,
} from '@/types/memory';

const errorDetail = (err: unknown): string => {
  // authApiClient 인터셉터가 detail을 ApiError(message)로 변환해 전달한다
  if (err instanceof Error && err.message) return err.message;
  return '요청 처리에 실패했습니다. 잠시 후 다시 시도하세요.';
};

interface MemoryItemProps {
  memory: Memory;
}

const MemoryItem = ({ memory }: MemoryItemProps) => {
  const [editing, setEditing] = useState(false);
  const [content, setContent] = useState(memory.content);
  const [error, setError] = useState<string | null>(null);
  const updateMutation = useUpdateMemory();
  const deleteMutation = useDeleteMemory();

  const save = () => {
    setError(null);
    updateMutation.mutate(
      { id: memory.id, data: { content } },
      {
        onSuccess: () => setEditing(false),
        onError: (err) => setError(errorDetail(err)),
      },
    );
  };

  return (
    <li className="rounded-2xl border border-zinc-200 bg-white p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1">
          <span className="rounded bg-violet-50 px-1.5 py-0.5 text-[11px] text-violet-600">
            {MEMORY_TYPE_LABELS[memory.mem_type]}
          </span>
          {editing ? (
            <div className="mt-2">
              <textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                maxLength={MEMORY_CONTENT_MAX}
                rows={2}
                className="block w-full resize-none rounded-xl border border-zinc-300 p-2 text-sm text-zinc-900 outline-none focus:border-violet-400"
              />
              <div className="mt-2 flex items-center gap-2">
                <button
                  type="button"
                  onClick={save}
                  className="rounded-xl bg-violet-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-violet-700"
                >
                  저장
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setEditing(false);
                    setContent(memory.content);
                    setError(null);
                  }}
                  className="rounded-xl border border-zinc-200 px-3 py-1.5 text-xs font-medium text-zinc-600 hover:bg-zinc-50"
                >
                  취소
                </button>
              </div>
            </div>
          ) : (
            <p className="mt-1.5 whitespace-pre-wrap text-sm leading-6 text-zinc-700">
              {memory.content}
            </p>
          )}
        </div>
        {!editing && (
          <div className="flex shrink-0 gap-1">
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="rounded-lg border border-zinc-200 px-2 py-1 text-[11px] text-zinc-600 hover:bg-zinc-50"
            >
              수정
            </button>
            <button
              type="button"
              onClick={() => deleteMutation.mutate(memory.id)}
              className="rounded-lg border border-zinc-200 px-2 py-1 text-[11px] text-zinc-600 hover:bg-red-50 hover:text-red-500"
            >
              삭제
            </button>
          </div>
        )}
      </div>
      {error && <p className="mt-1 text-xs text-red-500">{error}</p>}
    </li>
  );
};

// agent-memory-extraction: 대화에서 자동 추출된 후보 — 승인해야만 주입 대상이 된다.
const PendingSection = () => {
  const { data } = useMemories('pending');
  const approveMutation = useApproveMemory();
  const rejectMutation = useRejectMemory();
  const [error, setError] = useState<string | null>(null);

  if (!data || data.items.length === 0) return null;

  const act = (mutation: typeof approveMutation, id: number) => {
    setError(null);
    mutation.mutate(id, { onError: (err) => setError(errorDetail(err)) });
  };

  return (
    <section className="mb-8">
      <div className="mb-1 flex items-center justify-between">
        <h2 className="text-[15px] font-semibold text-zinc-900">
          승인 대기 {data.total}건
        </h2>
        <span className="text-[12px] text-zinc-400">
          {data.total}/{data.max_count}
        </span>
      </div>
      <p className="mb-4 text-[12px] text-zinc-400">
        대화에서 자동으로 추출된 후보입니다. 승인해야만 답변에 반영됩니다.
      </p>
      <ul className="space-y-2">
        {data.items.map((m) => (
          <li
            key={m.id}
            className="rounded-2xl border border-amber-200 bg-amber-50/40 p-4"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1">
                <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[11px] text-amber-700">
                  {MEMORY_TYPE_LABELS[m.mem_type]}
                </span>
                <p className="mt-1.5 whitespace-pre-wrap text-sm leading-6 text-zinc-700">
                  {m.content}
                </p>
                <p className="mt-1 text-[11px] text-zinc-400">
                  대화에서 자동 추출
                  {m.created_at && ` · ${m.created_at.slice(0, 10)}`}
                </p>
              </div>
              <div className="flex shrink-0 gap-1">
                <button
                  type="button"
                  onClick={() => act(approveMutation, m.id)}
                  className="rounded-xl bg-violet-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-violet-700"
                >
                  승인
                </button>
                <button
                  type="button"
                  onClick={() => act(rejectMutation, m.id)}
                  className="rounded-xl border border-zinc-200 px-3 py-1.5 text-xs font-medium text-zinc-600 hover:bg-red-50 hover:text-red-500"
                >
                  거부
                </button>
              </div>
            </div>
          </li>
        ))}
      </ul>
      {error && <p className="mt-1 text-xs text-red-500">{error}</p>}
    </section>
  );
};

const SettingsPage = () => {
  const { data, isLoading } = useMemories();
  const createMutation = useCreateMemory();
  const [memType, setMemType] = useState<MemoryType>('profile');
  const [content, setContent] = useState('');
  const [error, setError] = useState<string | null>(null);

  const atLimit = !!data && data.total >= data.max_count;

  const submit = () => {
    setError(null);
    createMutation.mutate(
      { mem_type: memType, content },
      {
        onSuccess: () => setContent(''),
        onError: (err) => setError(errorDetail(err)),
      },
    );
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
        <h1 className="mb-6 text-3xl font-bold tracking-tight text-zinc-900">
          설정
        </h1>

        <PendingSection />

        <section>
          <div className="mb-1 flex items-center justify-between">
            <h2 className="text-[15px] font-semibold text-zinc-900">
              AI가 기억하는 내용
            </h2>
            {data && (
              <span className="text-[12px] text-zinc-400">
                {data.total}/{data.max_count}
              </span>
            )}
          </div>
          <p className="mb-4 text-[12px] text-zinc-400">
            여기 등록한 내용은 일반 채팅 답변에 배경 정보로 반영됩니다. 언제든
            수정·삭제할 수 있습니다.
          </p>

          {isLoading ? (
            <div className="text-sm text-zinc-500">불러오는 중…</div>
          ) : (
            <ul className="space-y-2">
              {data?.items.map((m) => <MemoryItem key={m.id} memory={m} />)}
              {data?.items.length === 0 && (
                <li className="rounded-2xl border border-dashed border-zinc-300 p-5 text-center text-sm text-zinc-400">
                  아직 등록된 메모리가 없습니다.
                </li>
              )}
            </ul>
          )}

          <div className="mt-4 rounded-2xl border border-zinc-200 bg-zinc-50 p-4">
            {atLimit && (
              <p className="mb-2 text-xs text-amber-600">
                메모리 개수 상한에 도달했습니다. 기존 메모리를 삭제한 뒤 다시
                등록하세요.
              </p>
            )}
            <div className="flex flex-col gap-2">
              <label className="text-[12px] text-zinc-500" htmlFor="memory-type">
                메모리 타입
              </label>
              <select
                id="memory-type"
                value={memType}
                onChange={(e) => setMemType(e.target.value as MemoryType)}
                disabled={atLimit}
                className="w-40 rounded-xl border border-zinc-300 bg-white p-2 text-sm text-zinc-900 outline-none focus:border-violet-400"
              >
                {Object.entries(MEMORY_TYPE_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
              <label
                className="text-[12px] text-zinc-500"
                htmlFor="memory-content"
              >
                메모리 내용
              </label>
              <textarea
                id="memory-content"
                value={content}
                onChange={(e) => setContent(e.target.value)}
                maxLength={MEMORY_CONTENT_MAX}
                rows={2}
                disabled={atLimit}
                placeholder="예: '한도'는 동일인 여신한도를 의미"
                className="block w-full resize-none rounded-xl border border-zinc-300 bg-white p-2 text-sm text-zinc-900 placeholder-zinc-400 outline-none focus:border-violet-400"
              />
              <div className="flex items-center justify-between">
                <span className="text-[11px] text-zinc-400">
                  {content.length}/{MEMORY_CONTENT_MAX}
                </span>
                <button
                  type="button"
                  onClick={submit}
                  disabled={atLimit || createMutation.isPending}
                  className="rounded-xl bg-violet-600 px-4 py-2 text-[13.5px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95 disabled:cursor-not-allowed disabled:bg-zinc-300"
                >
                  등록
                </button>
              </div>
              {error && <p className="text-xs text-red-500">{error}</p>}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};

export default SettingsPage;
