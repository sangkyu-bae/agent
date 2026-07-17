import authApiClient from '@/services/api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  ChunkingProfile,
  ChunkingProfileListResponse,
  ChunkingProfileMessageResponse,
  ChunkingProfileRequest,
} from '@/types/chunkingProfile';

export const chunkingProfileService = {
  getChunkingProfiles: async (): Promise<ChunkingProfileListResponse> => {
    const { data } = await authApiClient.get<ChunkingProfileListResponse>(
      API_ENDPOINTS.ADMIN_CHUNKING_PROFILES
    );
    return data;
  },

  createChunkingProfile: async (
    req: ChunkingProfileRequest
  ): Promise<ChunkingProfile> => {
    const { data } = await authApiClient.post<ChunkingProfile>(
      API_ENDPOINTS.ADMIN_CHUNKING_PROFILES,
      req
    );
    return data;
  },

  // PUT 전체 교체 — 호출측은 반드시 전체 필드를 채워 보낸다 (Design D2)
  updateChunkingProfile: async (
    id: string,
    req: ChunkingProfileRequest
  ): Promise<ChunkingProfile> => {
    const { data } = await authApiClient.put<ChunkingProfile>(
      API_ENDPOINTS.ADMIN_CHUNKING_PROFILE_DETAIL(id),
      req
    );
    return data;
  },

  setDefaultChunkingProfile: async (
    id: string
  ): Promise<ChunkingProfileMessageResponse> => {
    const { data } = await authApiClient.put<ChunkingProfileMessageResponse>(
      API_ENDPOINTS.ADMIN_CHUNKING_PROFILE_DEFAULT(id)
    );
    return data;
  },

  deleteChunkingProfile: async (
    id: string
  ): Promise<ChunkingProfileMessageResponse> => {
    const { data } = await authApiClient.delete<ChunkingProfileMessageResponse>(
      API_ENDPOINTS.ADMIN_CHUNKING_PROFILE_DETAIL(id)
    );
    return data;
  },
};
