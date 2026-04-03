import { QueryClient } from '@tanstack/react-query';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60,       // 1분 — 리패치 억제
      gcTime: 1000 * 60 * 5,      // 5분 — 캐시 보존
      retry: 1,                   // 실패 시 1회 재시도
      refetchOnWindowFocus: false, // 창 포커스 시 자동 리패치 비활성
    },
    mutations: {
      retry: 0, // mutation은 재시도 없음
    },
  },
});
