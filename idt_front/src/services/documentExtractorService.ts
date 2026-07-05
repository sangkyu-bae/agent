// document-template-extractor Design §7-1: extract/refine/파일 다운로드 서비스
import authApiClient from './api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  ExtractDocumentResponse,
  RefineSlotsRequest,
  RefineSlotsResponse,
} from '@/types/documentExtractor';

export const documentExtractorService = {
  /** PDF/Word 업로드 → HTML + 추천 슬롯 (stateless). */
  extract: async (
    file: File,
    mcpPdfToHtmlToolId?: string,
    mcpHtmlToDocToolId?: string,
  ): Promise<ExtractDocumentResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    if (mcpPdfToHtmlToolId) {
      formData.append('mcp_pdf_to_html_tool_id', mcpPdfToHtmlToolId);
    }
    if (mcpHtmlToDocToolId) {
      formData.append('mcp_html_to_doc_tool_id', mcpHtmlToDocToolId);
    }
    const response = await authApiClient.post<ExtractDocumentResponse>(
      API_ENDPOINTS.DOCUMENT_EXTRACTOR_EXTRACT,
      formData,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 180_000, // MCP 변환 + LLM 추출
      },
    );
    return response.data;
  },

  /** 슬롯 재추천 (거절/보강, 유휴 5분 재생성). */
  refine: async (request: RefineSlotsRequest): Promise<RefineSlotsResponse> => {
    const response = await authApiClient.post<RefineSlotsResponse>(
      API_ENDPOINTS.DOCUMENT_EXTRACTOR_REFINE,
      request,
      { timeout: 120_000 },
    );
    return response.data;
  },

  /** 런타임 산출 문서 다운로드 — JWT 필요라 <a href> 대신 blob 저장. */
  downloadGeneratedFile: async (
    fileId: string,
    fallbackFilename: string,
  ): Promise<void> => {
    const response = await authApiClient.get<Blob>(
      API_ENDPOINTS.DOCUMENT_EXTRACTOR_FILE(fileId),
      { responseType: 'blob', timeout: 120_000 },
    );
    const disposition = response.headers['content-disposition'] as
      | string
      | undefined;
    const match = disposition?.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
    const filename = match
      ? decodeURIComponent(match[1])
      : fallbackFilename || 'document';

    const url = URL.createObjectURL(response.data);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  },
};
