import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { adminService } from '@/services/adminService';
import { queryKeys } from '@/lib/queryKeys';

const AdminUsersPage = () => {
  const queryClient = useQueryClient();

  const { data: pendingUsers = [], isLoading } = useQuery({
    queryKey: queryKeys.admin.pendingUsers(),
    queryFn: adminService.getPendingUsers,
  });

  const { mutate: approve, isPending: isApproving } = useMutation({
    mutationFn: adminService.approveUser,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.admin.pendingUsers() }),
  });

  const { mutate: reject, isPending: isRejecting } = useMutation({
    mutationFn: adminService.rejectUser,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.admin.pendingUsers() }),
  });

  const isActing = isApproving || isRejecting;

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      {/* 헤더 */}
      <div className="mb-6">
        <p className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">
          Admin
        </p>
        <h1 className="text-3xl font-bold tracking-tight text-zinc-900">사용자 승인 관리</h1>
        <p className="mt-1 text-[13px] text-zinc-400">
          가입 신청 후 관리자 승인을 기다리는 사용자 목록입니다.
        </p>
      </div>

      {/* 콘텐츠 */}
      {isLoading ? (
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
                <th className="px-5 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">
                  이메일
                </th>
                <th className="px-5 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">
                  가입일
                </th>
                <th className="px-5 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">
                  상태
                </th>
                <th className="px-5 py-3 text-right text-[12px] font-semibold uppercase tracking-wider text-zinc-400">
                  액션
                </th>
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
      )}
    </div>
  );
};

export default AdminUsersPage;
