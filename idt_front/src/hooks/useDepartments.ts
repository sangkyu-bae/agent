import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { departmentService } from '@/services/departmentService';
import { queryKeys } from '@/lib/queryKeys';
import type { CreateDepartmentRequest, UpdateDepartmentRequest } from '@/types/department';

export const useDepartments = () =>
  useQuery({
    queryKey: queryKeys.admin.departments(),
    queryFn: departmentService.getDepartments,
  });

export const useCreateDepartment = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateDepartmentRequest) => departmentService.createDepartment(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.admin.departments() }),
  });
};

export const useUpdateDepartment = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ deptId, data }: { deptId: string; data: UpdateDepartmentRequest }) =>
      departmentService.updateDepartment(deptId, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.admin.departments() }),
  });
};

export const useDeleteDepartment = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (deptId: string) => departmentService.deleteDepartment(deptId),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.admin.departments() }),
  });
};
