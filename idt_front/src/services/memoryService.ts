// agent-memory: 사용자 메모리 API 서비스. 모든 호출은 authApiClient(Bearer) 경유.
import authApiClient from './api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  CreateMemoryRequest,
  CreateOrgMemoryRequest,
  Memory,
  MemoryListResponse,
  UpdateMemoryRequest,
} from '@/types/memory';

export const memoryService = {
  getMemories: async (status?: 'active' | 'pending'): Promise<MemoryListResponse> => {
    const res = await authApiClient.get<MemoryListResponse>(
      API_ENDPOINTS.MEMORIES,
      { params: status ? { status } : undefined },
    );
    return res.data;
  },

  // agent-memory-extraction: 추출 후보 승인/거부
  approve: async (id: number): Promise<Memory> => {
    const res = await authApiClient.patch<Memory>(API_ENDPOINTS.MEMORY_APPROVE(id));
    return res.data;
  },

  reject: async (id: number): Promise<Memory> => {
    const res = await authApiClient.patch<Memory>(API_ENDPOINTS.MEMORY_REJECT(id));
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

  // agent-memory-org-scope: 부서 공유 메모리
  getOrgMemories: async (): Promise<MemoryListResponse> => {
    const res = await authApiClient.get<MemoryListResponse>(API_ENDPOINTS.MEMORY_ORG);
    return res.data;
  },

  createOrg: async (data: CreateOrgMemoryRequest): Promise<Memory> => {
    const res = await authApiClient.post<Memory>(API_ENDPOINTS.MEMORY_ORG, data);
    return res.data;
  },

  promote: async (id: number, deptId: string): Promise<Memory> => {
    const res = await authApiClient.post<Memory>(
      API_ENDPOINTS.MEMORY_PROMOTE(id),
      { dept_id: deptId },
    );
    return res.data;
  },
};
