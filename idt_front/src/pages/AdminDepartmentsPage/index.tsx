import { useState } from 'react';
import { useDepartments, useCreateDepartment, useUpdateDepartment, useDeleteDepartment } from '@/hooks/useDepartments';
import ConfirmDialog from '@/components/common/ConfirmDialog';
import type { Department, CreateDepartmentRequest, UpdateDepartmentRequest } from '@/types/department';

interface DepartmentFormModalProps {
  isOpen: boolean;
  title: string;
  initialName?: string;
  initialDescription?: string;
  confirmLabel: string;
  onClose: () => void;
  onSubmit: (name: string, description: string) => void;
  isPending: boolean;
  error: string | null;
}

const DepartmentFormModal = ({
  isOpen,
  title,
  initialName = '',
  initialDescription = '',
  confirmLabel,
  onClose,
  onSubmit,
  isPending,
  error,
}: DepartmentFormModalProps) => {
  const [name, setName] = useState(initialName);
  const [description, setDescription] = useState(initialDescription);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    onSubmit(name.trim(), description.trim());
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-[15px] font-semibold text-zinc-900">{title}</h2>

        <form onSubmit={handleSubmit} className="mt-4 space-y-4">
          <div>
            <label htmlFor="dept-name" className="mb-1.5 block text-[13px] font-medium text-zinc-700">
              부서명 <span className="text-red-400">*</span>
            </label>
            <input
              id="dept-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="부서명을 입력하세요"
              maxLength={100}
              className="w-full rounded-xl border border-zinc-300 px-4 py-2.5 text-[14px] text-zinc-900 placeholder-zinc-400 outline-none transition-all focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
              autoFocus
            />
          </div>

          <div>
            <label htmlFor="dept-desc" className="mb-1.5 block text-[13px] font-medium text-zinc-700">
              설명 <span className="text-zinc-400">(선택)</span>
            </label>
            <input
              id="dept-desc"
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="부서에 대한 설명"
              maxLength={255}
              className="w-full rounded-xl border border-zinc-300 px-4 py-2.5 text-[14px] text-zinc-900 placeholder-zinc-400 outline-none transition-all focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
            />
          </div>

          {error && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-[13px] text-red-600">{error}</p>
          )}

          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2.5 text-[13.5px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100"
            >
              취소
            </button>
            <button
              type="submit"
              disabled={isPending || !name.trim()}
              className="flex items-center justify-center rounded-xl bg-violet-600 px-4 py-2.5 text-[13.5px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95 disabled:opacity-50"
            >
              {isPending ? (
                <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              ) : (
                confirmLabel
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

const AdminDepartmentsPage = () => {
  const { data, isLoading, isError, refetch } = useDepartments();
  const departments = data?.departments ?? [];

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [editingDept, setEditingDept] = useState<Department | null>(null);
  const [deletingDept, setDeletingDept] = useState<Department | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const createMutation = useCreateDepartment();
  const updateMutation = useUpdateDepartment();
  const deleteMutation = useDeleteDepartment();

  const handleCreate = (name: string, description: string) => {
    setFormError(null);
    const req: CreateDepartmentRequest = { name };
    if (description) req.description = description;

    createMutation.mutate(req, {
      onSuccess: () => setIsCreateOpen(false),
      onError: (err: unknown) => {
        const msg = (err as { response?: { status?: number; data?: { detail?: string } } })?.response?.data?.detail;
        if ((err as { response?: { status?: number } })?.response?.status === 409) {
          setFormError('이미 존재하는 부서명입니다.');
        } else {
          setFormError(msg ?? '부서 생성에 실패했습니다.');
        }
      },
    });
  };

  const handleUpdate = (name: string, description: string) => {
    if (!editingDept) return;
    setFormError(null);
    const req: UpdateDepartmentRequest = {};
    if (name !== editingDept.name) req.name = name;
    if (description !== (editingDept.description ?? '')) req.description = description;

    updateMutation.mutate(
      { deptId: editingDept.id, data: req },
      {
        onSuccess: () => setEditingDept(null),
        onError: (err: unknown) => {
          const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
          setFormError(msg ?? '부서 수정에 실패했습니다.');
        },
      },
    );
  };

  const handleDelete = () => {
    if (!deletingDept) return;
    deleteMutation.mutate(deletingDept.id, {
      onSuccess: () => setDeletingDept(null),
    });
  };

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      {/* 헤더 */}
      <div className="mb-6 flex items-start justify-between">
        <div>
          <p className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">
            Admin
          </p>
          <h1 className="text-3xl font-bold tracking-tight text-zinc-900">부서 관리</h1>
          <p className="mt-1 text-[13px] text-zinc-400">
            부서를 생성·수정·삭제합니다.
          </p>
        </div>
        <button
          onClick={() => { setFormError(null); setIsCreateOpen(true); }}
          className="flex items-center gap-1.5 rounded-xl bg-violet-600 px-4 py-2.5 text-[13.5px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          부서 추가
        </button>
      </div>

      {/* 콘텐츠 */}
      {isLoading ? (
        <div className="flex h-48 items-center justify-center text-zinc-400">로딩 중...</div>
      ) : isError ? (
        <div className="flex h-48 flex-col items-center justify-center gap-3 rounded-2xl border border-zinc-200 bg-zinc-50">
          <p className="text-[14px] text-zinc-400">부서 목록을 불러오지 못했습니다.</p>
          <button
            onClick={() => refetch()}
            className="rounded-xl border border-zinc-200 bg-white px-4 py-2 text-[13px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100"
          >
            다시 시도
          </button>
        </div>
      ) : departments.length === 0 ? (
        <div className="flex h-48 flex-col items-center justify-center gap-3 rounded-2xl border border-zinc-200 bg-zinc-50">
          <p className="text-[14px] text-zinc-400">등록된 부서가 없습니다.</p>
          <button
            onClick={() => { setFormError(null); setIsCreateOpen(true); }}
            className="rounded-xl bg-violet-600 px-4 py-2 text-[13px] font-medium text-white transition-all hover:bg-violet-700 active:scale-95"
          >
            + 첫 번째 부서 추가하기
          </button>
        </div>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm">
          <table className="w-full">
            <thead>
              <tr className="border-b border-zinc-100 bg-zinc-50">
                <th scope="col" className="px-5 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">
                  부서명
                </th>
                <th scope="col" className="px-5 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">
                  설명
                </th>
                <th scope="col" className="w-[120px] px-5 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">
                  생성일
                </th>
                <th scope="col" className="w-[120px] px-5 py-3 text-right text-[12px] font-semibold uppercase tracking-wider text-zinc-400">
                  액션
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {departments.map((dept) => (
                <tr key={dept.id} className="transition-colors hover:bg-zinc-50/50">
                  <td className="px-5 py-4 text-[14px] font-medium text-zinc-900">{dept.name}</td>
                  <td className="px-5 py-4 text-[13px] text-zinc-500">
                    {dept.description || <span className="text-zinc-300">&mdash;</span>}
                  </td>
                  <td className="px-5 py-4 text-[13px] text-zinc-400">
                    {new Date(dept.created_at).toLocaleDateString('ko-KR')}
                  </td>
                  <td className="px-5 py-4">
                    <div className="flex justify-end gap-2">
                      <button
                        onClick={() => { setFormError(null); setEditingDept(dept); }}
                        className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-[12px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100 active:scale-95"
                      >
                        수정
                      </button>
                      <button
                        onClick={() => setDeletingDept(dept)}
                        aria-label={`${dept.name} 삭제`}
                        className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-[12px] font-medium text-zinc-600 transition-all hover:border-red-200 hover:bg-red-50 hover:text-red-500 active:scale-95"
                      >
                        삭제
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* 생성 모달 */}
      <DepartmentFormModal
        isOpen={isCreateOpen}
        title="부서 추가"
        confirmLabel="추가"
        onClose={() => setIsCreateOpen(false)}
        onSubmit={handleCreate}
        isPending={createMutation.isPending}
        error={formError}
      />

      {/* 수정 모달 */}
      <DepartmentFormModal
        isOpen={!!editingDept}
        title="부서 수정"
        initialName={editingDept?.name}
        initialDescription={editingDept?.description ?? ''}
        confirmLabel="저장"
        onClose={() => setEditingDept(null)}
        onSubmit={handleUpdate}
        isPending={updateMutation.isPending}
        error={formError}
      />

      {/* 삭제 확인 */}
      <ConfirmDialog
        isOpen={!!deletingDept}
        title="부서 삭제"
        description={`"${deletingDept?.name}" 부서를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.`}
        confirmLabel="삭제"
        variant="danger"
        onClose={() => setDeletingDept(null)}
        onConfirm={handleDelete}
        isPending={deleteMutation.isPending}
      />
    </div>
  );
};

export default AdminDepartmentsPage;
