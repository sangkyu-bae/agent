import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { adminService } from '@/services/adminService';
import { queryKeys } from '@/lib/queryKeys';
import type { AdminCreateUserRequest, AdminUserListParams } from '@/types/auth';

/** 전체 사용자 목록 (admin-user-registration) */
export const useAllUsers = (params: AdminUserListParams = {}) =>
  useQuery({
    queryKey: queryKeys.admin.allUsers(params),
    queryFn: () => adminService.getAllUsers(params),
  });

/** 관리자 직접 사용자 생성 */
export const useCreateUser = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AdminCreateUserRequest) => adminService.createUser(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.admin.all });
    },
  });
};
