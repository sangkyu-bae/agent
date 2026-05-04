import axios, { type AxiosInstance, type InternalAxiosRequestConfig } from 'axios';
import { API_BASE_URL, API_ENDPOINTS } from '@/constants/api';
import { useAuthStore } from '@/store/authStore';
import { ApiError } from './ApiError';

interface RetryConfig extends InternalAxiosRequestConfig {
  _retry?: boolean;
}

const authApiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
});

// Request interceptor — Access Token + X-User-Id 주입
authApiClient.interceptors.request.use((config) => {
  const { accessToken, user } = useAuthStore.getState();
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  if (user?.id) {
    config.headers['X-User-Id'] = String(user.id);
  }
  return config;
});

// Response interceptor — 401 시 Token 갱신 후 재시도 (1회)
authApiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config as RetryConfig;

    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      const { refreshToken, updateAccessToken, logout } = useAuthStore.getState();

      if (refreshToken) {
        try {
          // refresh 요청은 순수 axios 사용 (authApiClient 순환 참조 방지)
          const { data } = await axios.post(
            `${API_BASE_URL}${API_ENDPOINTS.AUTH_REFRESH}`,
            { refresh_token: refreshToken },
            { headers: { 'Content-Type': 'application/json' } }
          );
          updateAccessToken(data.access_token);
          originalRequest.headers.Authorization = `Bearer ${data.access_token}`;
          return authApiClient(originalRequest);
        } catch {
          logout();
          window.location.href = '/login';
        }
      } else {
        logout();
        window.location.href = '/login';
      }
    }

    const message = error.response?.data?.message ?? '알 수 없는 오류가 발생했습니다.';
    const status = error.response?.status ?? 0;
    return Promise.reject(new ApiError(message, status));
  }
);

export default authApiClient;
