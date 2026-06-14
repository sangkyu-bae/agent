import authApiClient from './api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  PendingUser,
  AdminCreateUserRequest,
  AdminCreateUserResponse,
  AdminUserListResponse,
  AdminUserListParams,
} from '@/types/auth';

export const adminService = {
  getPendingUsers: () =>
    authApiClient.get<PendingUser[]>(API_ENDPOINTS.ADMIN_USERS_PENDING).then((r) => r.data),

  approveUser: (userId: number) =>
    authApiClient.post(API_ENDPOINTS.ADMIN_USER_APPROVE(userId)).then((r) => r.data),

  rejectUser: (userId: number) =>
    authApiClient.post(API_ENDPOINTS.ADMIN_USER_REJECT(userId)).then((r) => r.data),

  // admin-user-registration
  createUser: (body: AdminCreateUserRequest) =>
    authApiClient
      .post<AdminCreateUserResponse>(API_ENDPOINTS.ADMIN_USERS_CREATE, body)
      .then((r) => r.data),

  getAllUsers: (params: AdminUserListParams = {}) =>
    authApiClient
      .get<AdminUserListResponse>(API_ENDPOINTS.ADMIN_USERS_LIST, { params })
      .then((r) => r.data),
};
