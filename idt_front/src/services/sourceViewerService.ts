// Design Ref: source-passage-viewer §4.1 — 원본 파일 blob 조회. JWT 가 필요해 <iframe src> 대신 blob 으로 받는다.
import { API_ENDPOINTS } from '@/constants/api';

import authApiClient from './api/authClient';

export const sourceViewerService = {
  /** 404(ORIGINAL_NOT_AVAILABLE)면 호출 측이 텍스트 뷰어로 내려간다. */
  fetchOriginal: async (kbId: string, documentId: string): Promise<Blob> => {
    const response = await authApiClient.get<Blob>(
      API_ENDPOINTS.SOURCE_VIEWER_ORIGINAL(kbId, documentId),
      { responseType: 'blob', timeout: 120_000 },
    );
    return response.data;
  },
};
