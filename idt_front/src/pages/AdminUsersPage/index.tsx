import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { adminService } from '@/services/adminService';
import { queryKeys } from '@/lib/queryKeys';
import { useAllUsers, useCreateUser } from '@/hooks/useAdminUsers';
import UserRegisterModal from '@/components/admin/UserRegisterModal';
import type { AdminCreateUserRequest } from '@/types/auth';

type Tab = 'all' | 'pending';

const ROLE_LABEL: Record<string, string> = { user: '일반', admin: '관리자' };
const STATUS_LABEL: Record<string, string> = {
  approved: '활성',
  pending: '승인 대기',
  rejected: '거절',
};

const AdminUsersPage = () => {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>('all');
  const [isRegisterOpen, setIsRegisterOpen] = useState(false);
  const [registerError, setRegisterError] = useState<string | null>(null);

  // 전체 사용자
  const { data: allUsers, isLoading: isAllLoading } = useAllUsers();
  const createUser = useCreateUser();

  // 승인 대기 (기존 유지)
  const { data: pendingUsers = [], isLoading: isPendingLoading } = useQuery({
    queryKey: queryKeys.admin.pendingUsers(),
    queryFn: adminService.getPendingUsers,
  });
  const { mutate: approve, isPending: isApproving } = useMutation({
    mutationFn: adminService.approveUser,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.admin.all }),
  });
  const { mutate: reject, isPending: isRejecting } = useMutation({
    mutationFn: adminService.rejectUser,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.admin.all }),
  });
  const isActing = isApproving || isRejecting;

  const handleRegister = (body: AdminCreateUserRequest) => {
    setRegisterError(null);
    createUser.mutate(body, {
      onSuccess: () => setIsRegisterOpen(false),
      onError: (err: unknown) => {
        const e = err as { response?: { status?: number; data?: { detail?: string } } };
        if (e?.response?.status === 409) {
          setRegisterError('이미 등록된 이메일입니다.');
        } else {
          setRegisterError(e?.response?.data?.detail ?? '사용자 등록에 실패했습니다.');
        }
      },
    });
  };

  const tabBtn = (key: Tab, label: string) => (
    <button
      onClick={() => setTab(key)}
      className={`border-b-2 px-1 pb-2.5 text-[14px] font-medium transition-colors ${
        tab === key
          ? 'border-violet-600 text-violet-700'
          : 'border-transparent text-zinc-400 hover:text-zinc-600'
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      {/* 헤더 */}
      <div className="mb-6 flex items-start justify-between">
        <div>
          <p className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">
            Admin
          </p>
          <h1 className="text-3xl font-bold tracking-tight text-zinc-900">사용자 관리</h1>
          <p className="mt-1 text-[13px] text-zinc-400">
            사용자를 직접 등록하거나, 가입 신청을 승인합니다.
          </p>
        </div>
        <button
          onClick={() => {
            setRegisterError(null);
            setIsRegisterOpen(true);
          }}
          className="flex items-center gap-1.5 rounded-xl bg-violet-600 px-4 py-2.5 text-[13.5px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          사용자 등록
        </button>
      </div>

      {/* 탭 */}
      <div className="mb-5 flex gap-5 border-b border-zinc-100">
        {tabBtn('all', '전체 사용자')}
        {tabBtn('pending', `승인 대기${pendingUsers.length ? ` (${pendingUsers.length})` : ''}`)}
      </div>

      {/* 전체 사용자 탭 */}
      {tab === 'all' && (
        isAllLoading ? (
          <div className="flex h-48 items-center justify-center text-zinc-400">로딩 중...</div>
        ) : !allUsers || allUsers.items.length === 0 ? (
          <div className="flex h-48 items-center justify-center rounded-2xl border border-zinc-200 bg-zinc-50 text-[14px] text-zinc-400">
            등록된 사용자가 없습니다.
          </div>
        ) : (
          <div className="overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm">
            <table className="w-full">
              <thead>
                <tr className="border-b border-zinc-100 bg-zinc-50">
                  {['이메일', '이름', '직급', '부서', '권한', '상태', '가입일'].map((h) => (
                    <th key={h} className="px-5 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                {allUsers.items.map((u) => (
                  <tr key={u.id} className="transition-colors hover:bg-zinc-50/50">
                    <td className="px-5 py-4 text-[14px] font-medium text-zinc-900">{u.email}</td>
                    <td className="px-5 py-4 text-[13px] text-zinc-600">{u.display_name ?? <span className="text-zinc-300">—</span>}</td>
                    <td className="px-5 py-4 text-[13px] text-zinc-500">{u.position ?? <span className="text-zinc-300">—</span>}</td>
                    <td className="px-5 py-4 text-[13px] text-zinc-500">
                      {u.department_names.length ? u.department_names.join(', ') : <span className="text-zinc-300">—</span>}
                    </td>
                    <td className="px-5 py-4 text-[13px] text-zinc-600">{ROLE_LABEL[u.role] ?? u.role}</td>
                    <td className="px-5 py-4">
                      <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-medium ${
                        u.status === 'approved' ? 'bg-emerald-50 text-emerald-600'
                          : u.status === 'pending' ? 'bg-amber-50 text-amber-600'
                          : 'bg-zinc-100 text-zinc-500'
                      }`}>
                        {STATUS_LABEL[u.status] ?? u.status}
                      </span>
                    </td>
                    <td className="px-5 py-4 text-[13px] text-zinc-400">
                      {u.created_at ? new Date(u.created_at).toLocaleDateString('ko-KR') : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}

      {/* 승인 대기 탭 */}
      {tab === 'pending' && (
        isPendingLoading ? (
          <div className="flex h-48 items-center justify-center text-zinc-400">로딩 중...</div>
        ) : pendingUsers.length === 0 ? (
          <div className="flex h-48 items-center justify-center rounded-2xl border border-zinc-200 bg-zinc-50 text-[14px] text-zinc-400">
            승인 대기 중인 사용자가 없습니다.
          </div>
        ) : (
          <div className="overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm">
            <table className="w-full">
              <thead>
                <tr className="border-b border-zinc-100 bg-zinc-50">
                  <th className="px-5 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">이메일</th>
                  <th className="px-5 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">가입일</th>
                  <th className="px-5 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">상태</th>
                  <th className="px-5 py-3 text-right text-[12px] font-semibold uppercase tracking-wider text-zinc-400">액션</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                {pendingUsers.map((user) => (
                  <tr key={user.id} className="transition-colors hover:bg-zinc-50/50">
                    <td className="px-5 py-4 text-[14px] font-medium text-zinc-900">{user.email}</td>
                    <td className="px-5 py-4 text-[13px] text-zinc-400">
                      {new Date(user.created_at).toLocaleDateString('ko-KR')}
                    </td>
                    <td className="px-5 py-4">
                      <span className="inline-flex items-center rounded-full bg-amber-50 px-2.5 py-0.5 text-[11px] font-medium text-amber-600">
                        승인 대기
                      </span>
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex justify-end gap-2">
                        <button
                          onClick={() => approve(user.id)}
                          disabled={isActing}
                          className="rounded-lg bg-violet-600 px-3 py-1.5 text-[12px] font-medium text-white transition-all hover:bg-violet-700 active:scale-95 disabled:opacity-50"
                        >
                          승인
                        </button>
                        <button
                          onClick={() => reject(user.id)}
                          disabled={isActing}
                          className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-[12px] font-medium text-zinc-600 transition-all hover:border-red-200 hover:bg-red-50 hover:text-red-500 active:scale-95 disabled:opacity-50"
                        >
                          거절
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}

      <UserRegisterModal
        isOpen={isRegisterOpen}
        onClose={() => setIsRegisterOpen(false)}
        onSubmit={handleRegister}
        isPending={createUser.isPending}
        error={registerError}
      />
    </div>
  );
};

export default AdminUsersPage;
