import apiClient from './api/client';
import authApiClient from './api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  AuthTokenResponse,
  RefreshTokenResponse,
  RegisterRequest,
  RegisterResponse,
  LoginRequest,
  User,
} from '@/types/auth';

export const authService = {
  // 공개 엔드포인트 — 토큰 불필요 (apiClient)
  register: (data: RegisterRequest) =>
    apiClient.post<RegisterResponse>(API_ENDPOINTS.AUTH_REGISTER, data).then((r) => r.data),

  login: (data: LoginRequest) =>
    apiClient.post<AuthTokenResponse>(API_ENDPOINTS.AUTH_LOGIN, data).then((r) => r.data),

  refresh: (refreshToken: string) =>
    apiClient
      .post<RefreshTokenResponse>(API_ENDPOINTS.AUTH_REFRESH, { refresh_token: refreshToken })
      .then((r) => r.data),

  // 인증 필요 엔드포인트 (authApiClient)
  logout: (refreshToken: string) =>
    authApiClient
      .post(API_ENDPOINTS.AUTH_LOGOUT, { refresh_token: refreshToken })
      .then((r) => r.data),

  me: () =>
    authApiClient.get<User>(API_ENDPOINTS.AUTH_ME).then((r) => r.data),
};
