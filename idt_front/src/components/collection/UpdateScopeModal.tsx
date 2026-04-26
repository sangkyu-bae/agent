import { useState, useEffect } from 'react';
import { COLLECTION_SCOPES, SCOPE_LABELS } from '@/types/collection';
import type { CollectionScope, UpdateScopeRequest } from '@/types/collection';

interface UpdateScopeModalProps {
  isOpen: boolean;
  collectionName: string;
  currentScope: CollectionScope;
  onClose: () => void;
  onSubmit: (data: UpdateScopeRequest) => void;
  isPending: boolean;
  error: string | null;
}

const UpdateScopeModal = ({
  isOpen,
  collectionName,
  currentScope,
  onClose,
  onSubmit,
  isPending,
  error,
}: UpdateScopeModalProps) => {
  const [scope, setScope] = useState<CollectionScope>(currentScope);
  const [departmentId, setDepartmentId] = useState('');

  useEffect(() => {
    setScope(currentScope);
    setDepartmentId('');
  }, [currentScope, isOpen]);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      scope,
      department_id: scope === 'DEPARTMENT' ? departmentId : undefined,
    });
  };

  const handleClose = () => {
    setScope(currentScope);
    setDepartmentId('');
    onClose();
  };

  const currentInfo = SCOPE_LABELS[currentScope];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={handleClose}
    >
      <div
        className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-[15px] font-semibold text-zinc-900">
          접근 범위 변경
        </h2>

        <div className="mt-3 rounded-xl bg-zinc-50 px-4 py-3">
          <p className="text-[12px] text-zinc-400">컬렉션</p>
          <p className="text-[13.5px] font-medium text-zinc-800">
            {collectionName}
          </p>
          <p className="mt-1 text-[12px] text-zinc-400">
            현재 범위:{' '}
            <span className={`font-semibold ${currentInfo.color}`}>
              {currentInfo.label}
            </span>
          </p>
        </div>

        <form onSubmit={handleSubmit} className="mt-5 space-y-4">
          <div>
            <label className="mb-1.5 block text-[12px] font-medium text-zinc-500">
              새 접근 범위
            </label>
            <div className="space-y-2">
              {COLLECTION_SCOPES.map((s) => (
                <label key={s} className="flex cursor-pointer items-center gap-2.5">
                  <input
                    type="radio"
                    name="scope"
                    value={s}
                    checked={scope === s}
                    onChange={() => setScope(s)}
                    className="h-4 w-4 accent-violet-600"
                  />
                  <span className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11.5px] font-semibold ${SCOPE_LABELS[s].bg} ${SCOPE_LABELS[s].color}`}>
                    {SCOPE_LABELS[s].label}
                  </span>
                  <span className="text-[12px] text-zinc-400">
                    {s === 'PERSONAL' && '나만 접근 가능'}
                    {s === 'DEPARTMENT' && '소속 부서원 접근'}
                    {s === 'PUBLIC' && '전체 접근 가능'}
                  </span>
                </label>
              ))}
            </div>
            {scope === 'DEPARTMENT' && (
              <div className="mt-3">
                <label className="mb-1.5 block text-[12px] font-medium text-zinc-500">
                  부서 ID
                </label>
                <input
                  type="text"
                  value={departmentId}
                  onChange={(e) => setDepartmentId(e.target.value)}
                  placeholder="dept-uuid"
                  className="w-full rounded-xl border border-zinc-300 px-4 py-2.5 text-[15px] text-zinc-900 placeholder-zinc-400 outline-none transition-all focus:border-violet-400"
                />
              </div>
            )}
          </div>

          {error && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-[13px] text-red-600">
              {error}
            </p>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={handleClose}
              className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2.5 text-[13.5px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100"
            >
              취소
            </button>
            <button
              type="submit"
              disabled={isPending}
              className="flex items-center justify-center rounded-xl bg-violet-600 px-4 py-2.5 text-[13.5px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95 disabled:opacity-50"
            >
              {isPending ? (
                <svg
                  className="h-4 w-4 animate-spin"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                  />
                </svg>
              ) : (
                '변경'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default UpdateScopeModal;
