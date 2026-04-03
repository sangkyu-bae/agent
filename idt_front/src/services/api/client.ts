import axios, { type AxiosInstance } from 'axios';
import { API_BASE_URL } from '@/constants/api';

const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
});

apiClient.interceptors.request.use((config) => {
  // 인증 토큰 등 공통 헤더 처리
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    // 공통 에러 처리
    const message = error.response?.data?.message ?? '알 수 없는 오류가 발생했습니다.';
    return Promise.reject(new Error(message));
  }
);

export default apiClient;
