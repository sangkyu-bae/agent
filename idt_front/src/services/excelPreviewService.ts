// excel-preview Design §5.3 — 산출 .xlsx 프리뷰 조회 서비스
import authApiClient from './api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type { ExcelPreviewResponse } from '@/types/excelPreview';

export const excelPreviewService = {
  /** 산출 .xlsx의 시트별 상위 N행 프리뷰 JSON 조회 (owner-only). */
  getPreview: async (fileId: string): Promise<ExcelPreviewResponse> => {
    const response = await authApiClient.get<ExcelPreviewResponse>(
      API_ENDPOINTS.DOCUMENT_EXTRACTOR_FILE_PREVIEW(fileId),
      { timeout: 30_000 },
    );
    return response.data;
  },
};
