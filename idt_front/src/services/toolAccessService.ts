import authApiClient from '@/services/api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  DefaultToolAccessResponse,
  DepartmentToolAccessResponse,
  UserToolAccessResponse,
} from '@/types/toolAccess';

// tool-access-control §4.1 — 관리자 도구 권한. PUT 은 전체 교체 (tool_ids 에 없는 도구는 해제).
export const toolAccessService = {
  getDefault: () =>
    authApiClient
      .get<DefaultToolAccessResponse>(API_ENDPOINTS.ADMIN_TOOL_ACCESS_DEFAULT)
      .then((r) => r.data),
  replaceDefault: (toolIds: string[]) =>
    authApiClient
      .put<DefaultToolAccessResponse>(API_ENDPOINTS.ADMIN_TOOL_ACCESS_DEFAULT, { tool_ids: toolIds })
      .then((r) => r.data),
  getDepartment: (deptId: string) =>
    authApiClient
      .get<DepartmentToolAccessResponse>(API_ENDPOINTS.ADMIN_TOOL_ACCESS_DEPARTMENT(deptId))
      .then((r) => r.data),
  replaceDepartment: (deptId: string, toolIds: string[]) =>
    authApiClient
      .put<DepartmentToolAccessResponse>(API_ENDPOINTS.ADMIN_TOOL_ACCESS_DEPARTMENT(deptId), {
        tool_ids: toolIds,
      })
      .then((r) => r.data),
  getUser: (userId: number) =>
    authApiClient
      .get<UserToolAccessResponse>(API_ENDPOINTS.ADMIN_TOOL_ACCESS_USER(userId))
      .then((r) => r.data),
  replaceUser: (userId: number, toolIds: string[]) =>
    authApiClient
      .put<UserToolAccessResponse>(API_ENDPOINTS.ADMIN_TOOL_ACCESS_USER(userId), {
        tool_ids: toolIds,
      })
      .then((r) => r.data),
};
