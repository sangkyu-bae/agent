// agent-memory: 사용자 메모리 API 서비스. 모든 호출은 authApiClient(Bearer) 경유.
import authApiClient from './api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  CreateMemoryRequest,
  Memory,
  MemoryListResponse,
  UpdateMemoryRequest,
} from '@/types/memory';

export const memoryService = {
  getMemories: async (): Promise<MemoryListResponse> => {
    const res = await authApiClient.get<MemoryListResponse>(
      API_ENDPOINTS.MEMORIES,
    );
    return res.data;
  },

  create: async (data: CreateMemoryRequest): Promise<Memory> => {
    const res = await authApiClient.post<Memory>(API_ENDPOINTS.MEMORIES, data);
    return res.data;
  },

  update: async (id: number, data: UpdateMemoryRequest): Promise<Memory> => {
    const res = await authApiClient.patch<Memory>(
      API_ENDPOINTS.MEMORY_DETAIL(id),
      data,
    );
    return res.data;
  },

  remove: async (id: number): Promise<void> => {
    await authApiClient.delete(API_ENDPOINTS.MEMORY_DETAIL(id));
  },
};
