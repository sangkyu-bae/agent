import authApiClient from '@/services/api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  Department,
  DepartmentListResponse,
  CreateDepartmentRequest,
  UpdateDepartmentRequest,
  AssignUserDepartmentRequest,
} from '@/types/department';

export const departmentService = {
  getDepartments: async (): Promise<DepartmentListResponse> => {
    const { data } = await authApiClient.get<DepartmentListResponse>(
      API_ENDPOINTS.ADMIN_DEPARTMENTS,
    );
    return data;
  },

  createDepartment: async (req: CreateDepartmentRequest): Promise<Department> => {
    const { data } = await authApiClient.post<Department>(
      API_ENDPOINTS.ADMIN_DEPARTMENTS,
      req,
    );
    return data;
  },

  updateDepartment: async (deptId: string, req: UpdateDepartmentRequest): Promise<Department> => {
    const { data } = await authApiClient.patch<Department>(
      API_ENDPOINTS.ADMIN_DEPARTMENT_DETAIL(deptId),
      req,
    );
    return data;
  },

  deleteDepartment: async (deptId: string): Promise<void> => {
    await authApiClient.delete(API_ENDPOINTS.ADMIN_DEPARTMENT_DETAIL(deptId));
  },

  assignUser: async (userId: number, req: AssignUserDepartmentRequest): Promise<void> => {
    await authApiClient.post(API_ENDPOINTS.ADMIN_USER_DEPT_ASSIGN(userId), req);
  },

  removeUser: async (userId: number, deptId: string): Promise<void> => {
    await authApiClient.delete(API_ENDPOINTS.ADMIN_USER_DEPT_REMOVE(userId, deptId));
  },
};
