import { useState, useEffect } from 'react';
import Modal from '@/components/common/Modal';
import Dropdown from '@/components/common/Dropdown';
import { COLLECTION_SCOPES, SCOPE_LABELS } from '@/types/collection';
import type { CollectionScope, UpdateScopeRequest } from '@/types/collection';
import { useDepartments } from '@/hooks/useDepartments';

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
  const { data: deptData, isLoading: isDeptLoading } = useDepartments();

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
    <Modal
      onClose={handleClose}
      title="접근 범위 변경"
      size="md"
      showCloseButton={false}
    >
        <div className="rounded-xl bg-zinc-50 px-4 py-3">
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
                  부서 선택
                </label>
                {isDeptLoading ? (
                  <p className="text-[13px] text-zinc-400">부서 목록을 불러오는 중...</p>
                ) : !deptData?.departments.length ? (
                  <p className="text-[13px] text-amber-600">등록된 부서가 없습니다. 관리자 페이지에서 부서를 먼저 등록해주세요.</p>
                ) : (
                  <Dropdown
                    value={departmentId}
                    onChange={setDepartmentId}
                    placeholder="부서를 선택하세요"
                    options={deptData.departments.map((dept) => ({ value: dept.id, label: dept.name }))}
                    className="w-full"
                  />
                )}
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
    </Modal>
  );
};

export default UpdateScopeModal;
